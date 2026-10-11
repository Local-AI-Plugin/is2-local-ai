#!/usr/bin/env python3
"""Record RAM, CPU and battery power while a command (e.g. the evaluator) runs.

Wrap the evaluation so sampling starts and stops with it:
  python models/monitor_resources.py -- python models/evaluate_ollama.py --limit 5
Or run standalone (Ctrl+C to stop), e.g. to measure an idle baseline:
  python models/monitor_resources.py
Each sample is tagged with the model Ollama currently has loaded (/api/ps), so
the summary breaks results down per model.

Ollama memory/CPU: read from `docker stats` for --container (default
local-ai-ollama), because a containerized server runs inside the Docker WSL2
VM where Windows process tools cannot see it. Pass --container "" for a native
Ollama install; its processes are then measured with psutil instead.

Power comes from the laptop battery (Windows WMI BatteryStatus) and is
whole-system power, screen included. It is only reported while unplugged; on
AC the battery reports no discharge. Battery firmware refreshes these readings
every several seconds, so treat power_w as a coarse trace and energy_wh
(capacity drop) as the better total. Measure an idle baseline and subtract it.
"""
import argparse
import csv
import json
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil
import requests

FIELDS = ['utc', 'elapsed_s', 'loaded_model', 'ollama_model_size_gb',
          'ollama_mem_gb', 'ollama_cpu_pct', 'system_ram_used_gb',
          'system_ram_pct', 'cpu_pct', 'on_ac', 'power_w', 'battery_mwh']
UNITS = {'B': 1, 'KIB': 2**10, 'MIB': 2**20, 'GIB': 2**30, 'TIB': 2**40,
         'KB': 1e3, 'MB': 1e6, 'GB': 1e9, 'TB': 1e12}


class StreamReader:
    """Runs a long-lived command and keeps the latest parsed line. Spawning a
    process per sample (PowerShell/WMI, docker) costs more than the interval."""

    def __init__(self, command, parse):
        self.latest = None
        self.parse = parse
        self.proc = subprocess.Popen(command, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True,
                                     encoding='utf-8', errors='replace')
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.proc.stdout:
            value = self.parse(line)
            if value is not None:
                self.latest = value

    def close(self):
        self.proc.kill()


def battery_reader(interval):
    if sys.platform != 'win32':
        return None
    loop = ('while($true){$b=Get-CimInstance -Namespace root\\wmi '
            '-ClassName BatteryStatus|Select-Object -First 1;'
            'if($b){"{0},{1},{2}" -f [int]$b.PowerOnline,$b.DischargeRate,'
            '$b.RemainingCapacity};'
            f'Start-Sleep -Milliseconds {int(interval * 1000)}}}')

    def parse(line):  # -> (on_ac, discharge mW, remaining mWh)
        parts = line.strip().split(',')
        if len(parts) == 3:
            return parts[0] == '1', int(parts[1]), int(parts[2])
    return StreamReader(['powershell', '-NoProfile', '-Command', loop], parse)


def docker_reader(container):
    def parse(line):  # -> (memory GB, CPU %); lines carry ANSI clear codes
        m = re.search(r'([\d.]+)\s*([KMGT]?i?B)\s*/.*\|\s*([\d.]+)%', line)
        if m:
            return float(m[1]) * UNITS[m[2].upper()] / 1e9, float(m[3])
    return StreamReader(['docker', 'stats', container, '--format',
                         '{{.MemUsage}}|{{.CPUPerc}}'], parse)


class NativeOllama:
    """psutil fallback for a non-Docker Ollama. Walking every process is slow
    (seconds on Windows), so the PID list is refreshed only periodically."""

    def __init__(self):
        self.procs, self.last_scan = [], 0

    def sample(self):
        if time.monotonic() - self.last_scan > 15:
            self.procs = [p for p in psutil.process_iter(['name'])
                          if 'llama' in (p.info['name'] or '').lower()
                          and 'ollama app' not in p.info['name'].lower()]
            self.last_scan = time.monotonic()
        mem = cpu = 0
        for p in self.procs:
            try:
                mem += p.memory_info().rss
                cpu += p.cpu_percent(interval=None)
            except psutil.Error:
                self.last_scan = 0  # Process exited (model unload); rescan.
        return mem / 1e9, cpu / psutil.cpu_count()


def loaded_model(base_url):
    try:
        models = requests.get(base_url + '/api/ps', timeout=2).json().get('models', [])
    except (requests.RequestException, ValueError):
        return 'unreachable', None
    if not models:
        return '(none)', None
    return ('+'.join(m['name'] for m in models),
            sum(m.get('size', 0) for m in models) / 1e9)


def summarize(rows, interval):
    # Each sample stands for the time until the next one. Battery capacity
    # drops are attributed in time order, so a model loaded in several
    # stretches is still counted correctly.
    spans = [b['elapsed_s'] - a['elapsed_s'] for a, b in zip(rows, rows[1:])] + [interval]
    drops = [0] + [max(a['battery_mwh'] - b['battery_mwh'], 0)
                   if a['battery_mwh'] is not None and b['battery_mwh'] is not None
                   else 0 for a, b in zip(rows, rows[1:])]
    by_model = {}
    for r, span, drop in zip(rows, spans, drops):
        by_model.setdefault(r['loaded_model'], []).append((r, span, drop))
    summary = {}
    for model, items in by_model.items():
        rs = [r for r, _, _ in items]

        def stat(key, fn):
            vals = [r[key] for r in rs if r[key] is not None]
            return round(fn(vals), 2) if vals else None

        def avg(vals):
            return sum(vals) / len(vals)
        on_battery = all(r['on_ac'] is False for r in rs)
        summary[model] = {
            'samples': len(rs),
            'seconds': round(sum(s for _, s, _ in items), 1),
            'ollama_mem_gb_peak': stat('ollama_mem_gb', max),
            'ollama_mem_gb_avg': stat('ollama_mem_gb', avg),
            'ollama_cpu_pct_avg': stat('ollama_cpu_pct', avg),
            'system_ram_used_gb_peak': stat('system_ram_used_gb', max),
            'cpu_pct_avg': stat('cpu_pct', avg),
            'power_w_avg': stat('power_w', avg),
            'energy_wh_from_capacity': (round(sum(d for _, _, d in items) / 1000, 2)
                                        if on_battery else None),
            'on_battery_whole_time': on_battery,
        }
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--interval', type=float, default=1.0, help='Seconds between samples.')
    parser.add_argument('--base-url', default='http://127.0.0.1:11434')
    parser.add_argument('--container', default='local-ai-ollama',
                        help='Ollama Docker container; "" for a native install.')
    parser.add_argument('--out', default='benchmark_results')
    parser.add_argument('command', nargs=argparse.REMAINDER,
                        help='Command to run and monitor, after "--".')
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    base_url = args.base_url.rstrip('/')

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    csv_path = out / f'resources_{stamp}.csv'
    summary_path = out / f'resources_{stamp}_summary.json'

    battery = battery_reader(args.interval)
    docker = docker_reader(args.container) if args.container else None
    native = None if docker else NativeOllama()
    child = subprocess.Popen(command) if command else None
    psutil.cpu_percent(interval=None)  # First call primes the counter.
    start = time.perf_counter()
    rows = []
    print(f'Sampling every {args.interval}s -> {csv_path}', flush=True)
    try:
        with csv_path.open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction='ignore')
            writer.writeheader()
            while child is None or child.poll() is None:
                tick = time.perf_counter()
                model, size_gb = loaded_model(base_url)
                mem_gb, ollama_cpu = (docker.latest or (None, None)) if docker else native.sample()
                on_ac, discharge_mw, remaining_mwh = (battery and battery.latest) or (None,) * 3
                vm = psutil.virtual_memory()
                row = {
                    'utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                    'elapsed_s': round(tick - start, 2),
                    'loaded_model': model,
                    'ollama_model_size_gb': round(size_gb, 2) if size_gb else None,
                    'ollama_mem_gb': round(mem_gb, 3) if mem_gb is not None else None,
                    'ollama_cpu_pct': ollama_cpu,
                    'system_ram_used_gb': round(vm.used / 1e9, 3),
                    'system_ram_pct': vm.percent,
                    'cpu_pct': psutil.cpu_percent(interval=None),
                    'on_ac': on_ac,
                    'power_w': (discharge_mw / 1000
                                if on_ac is False and discharge_mw else None),
                    'battery_mwh': remaining_mwh,
                }
                rows.append(row)
                writer.writerow(row)
                f.flush()
                time.sleep(max(0, args.interval - (time.perf_counter() - tick)))
    except KeyboardInterrupt:
        print('Stopped.', flush=True)
    finally:
        for reader in (battery, docker):
            if reader:
                reader.close()
        if rows:
            summary = {'command': command, 'interval_s': args.interval,
                       'container': args.container or None,
                       'samples_csv': str(csv_path),
                       'per_model': summarize(rows, args.interval)}
            summary_path.write_text(json.dumps(summary, indent=2), encoding='utf-8')
            print(json.dumps(summary['per_model'], indent=2))
            print(f'Summary saved to {summary_path.resolve()}')
            if any(r['on_ac'] for r in rows):
                print('NOTE: laptop was on AC power for some samples; no power '
                      'reading is available for those. Unplug for power numbers.')
            if docker and all(r['ollama_mem_gb'] is None for r in rows):
                print(f'NOTE: no docker stats for container "{args.container}". '
                      'Is it running? Use --container "" for a native Ollama.')
    if child is not None:
        if child.poll() is None:
            child.wait()
        sys.exit(child.returncode)


if __name__ == '__main__':
    main()
