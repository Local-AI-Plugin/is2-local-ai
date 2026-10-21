#!/usr/bin/env python3
"""Combine an evaluate_ollama.py run with monitor_resources.py samples.

  python models/analyze_run.py benchmark_results/<run folder>
  python models/analyze_run.py benchmark_results/<run folder> --baseline-w 6.5

Per model it reports accuracy, speed from Ollama's own token counts and
timings (requests.jsonl), and RAM/CPU/power from the resource samples taken
while that model was answering. Each model's window runs from its first
request's start to its last request's end, using Ollama's timestamps, so
harness start-up and dataset loading are excluded.

Starting RAM (system and container) is the average of the samples in the 10 s
before the first request, before the model loads; the increase is the
window's peak minus that. When RAM is nearly full, Windows pages other apps
out, so the system RAM increase can understate what the model needs.

Peak power is the highest battery reading in the window; the firmware
averages over several seconds, so short spikes are smoothed out.
Energy per token = average power x window length / generated tokens. It
includes prompt processing, and needs the laptop on battery for the whole
window. --baseline-w (idle power from a standalone monitor run) is subtracted
to give the extra energy the model costs. The resources CSV is picked from
the run's parent folder automatically; pass --resources to choose one.
"""
import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path

STARTING_RAM_S = 10  # Seconds of samples before a model's first request.

def parse_utc(text):
    # Ollama writes nanoseconds; fromisoformat accepts at most microseconds.
    text = re.sub(r'(\.\d{6})\d+', r'\1', text.replace('Z', '+00:00'))
    return datetime.fromisoformat(text)


def load_requests(path):
    records = []
    with path.open(encoding='utf-8') as f:
        for line in f:
            rec = json.loads(line)
            if 'response' in rec:
                records.append(rec['response'])
    return records


def load_samples(path):
    def num(v):
        return float(v) if v not in ('', None) else None
    with path.open(encoding='utf-8') as f:
        return [{'utc': parse_utc(r['utc']),
                 'on_ac': {'True': True, 'False': False}.get(r['on_ac']),
                 'power_w': num(r.get('power_w')),
                 'battery_mwh': num(r.get('battery_mwh')),
                 'ollama_mem_gb': num(r.get('ollama_mem_gb')),
                 'ollama_cpu_pct': num(r.get('ollama_cpu_pct')),
                 'system_ram_used_gb': num(r.get('system_ram_used_gb'))}
                for r in csv.DictReader(f)]


def pick_resources(run_dir, start, end):
    best, best_hits = None, 0
    for path in sorted(run_dir.parent.glob('resources_*Z.csv')):
        hits = sum(start <= s['utc'] <= end for s in load_samples(path))
        if hits > best_hits:
            best, best_hits = path, hits
    return best


def accuracy(results_path):
    if not results_path.exists():
        return {}
    results = json.loads(results_path.read_text(encoding='utf-8'))['results']
    return {f'{task}/{metric.split(",")[0]}': round(value, 4)
            for task, metrics in results.items()
            for metric, value in metrics.items()
            if isinstance(value, (int, float)) and 'stderr' not in metric}


def analyze_model(records, samples, baseline_w):
    starts = [parse_utc(r['created_at']).timestamp() - r['total_duration'] / 1e9
              for r in records]
    ends = [parse_utc(r['created_at']).timestamp() for r in records]
    start, end = min(starts), max(ends)
    seconds = end - start
    gen_tokens = sum(r.get('eval_count', 0) for r in records)
    prompt_tokens = sum(r.get('prompt_eval_count', 0) for r in records)
    out = {
        'answers': len(records),
        'truncated_answers': sum(r.get('done_reason') == 'length' for r in records),
        'window_seconds': round(seconds, 1),
        'model_load_seconds': round(sum(r.get('load_duration', 0) for r in records) / 1e9, 1),
        'avg_seconds_per_answer': round(sum(r['total_duration'] for r in records)
                                        / 1e9 / len(records), 1),
        'avg_output_tokens_per_answer': round(gen_tokens / len(records), 1),
        'generation_tokens_per_s': round(
            gen_tokens / (sum(r.get('eval_duration', 0) for r in records) / 1e9), 2),
        'prompt_tokens_per_s': round(
            prompt_tokens / max(sum(r.get('prompt_eval_duration', 0) for r in records) / 1e9,
                                1e-9), 2),
    }
    window = [s for s in samples if start <= s['utc'].timestamp() <= end]
    if not window:
        out['resources'] = 'no resource samples in this window'
        return out

    def peak(key):
        vals = [s[key] for s in window if s[key] is not None]
        return round(max(vals), 2) if vals else None

    # Starting RAM: samples in the STARTING_RAM_S seconds before the first
    # request. Model loading counts as part of that request, so these come
    # before the model is in memory.
    before = [s for s in samples if start - STARTING_RAM_S <= s['utc'].timestamp() < start]

    def starting(key):
        vals = [s[key] for s in before if s[key] is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    def increase(peak_val, start_val):
        return round(peak_val - start_val, 2) if None not in (peak_val, start_val) else None

    cpu = [s['ollama_cpu_pct'] for s in window if s['ollama_cpu_pct'] is not None]
    mem_peak, mem_start = peak('ollama_mem_gb'), starting('ollama_mem_gb')
    ram_peak, ram_start = peak('system_ram_used_gb'), starting('system_ram_used_gb')
    out.update({
        'ollama_mem_gb_start': mem_start,
        'ollama_mem_gb_peak': mem_peak,
        'ollama_mem_gb_increase': increase(mem_peak, mem_start),
        'system_ram_used_gb_start': ram_start,
        'system_ram_used_gb_peak': ram_peak,
        'system_ram_used_gb_increase': increase(ram_peak, ram_start),
        'ollama_cpu_pct_avg': round(sum(cpu) / len(cpu), 1) if cpu else None,
    })
    powers = [s['power_w'] for s in window if s['power_w'] is not None]
    if not all(s['on_ac'] is False for s in window) or not powers:
        out['power'] = 'laptop on AC for part of this window; no energy figures'
        return out
    avg_w = sum(powers) / len(powers)
    energy_j = avg_w * seconds
    caps = [s['battery_mwh'] for s in window if s['battery_mwh'] is not None]
    out.update({
        'power_w_avg': round(avg_w, 2),
        # Peak of the battery's few-second averages, not an instantaneous peak.
        'power_w_peak': round(max(powers), 2),
        'energy_wh': round(energy_j / 3600, 3),
        'energy_wh_battery_capacity_drop': (round((caps[0] - caps[-1]) / 1000, 3)
                                            if len(caps) > 1 else None),
        'joules_per_output_token': round(energy_j / gen_tokens, 3) if gen_tokens else None,
        'wh_per_answer': round(energy_j / 3600 / len(records), 4),
    })
    if baseline_w is not None:
        net_j = max(avg_w - baseline_w, 0) * seconds
        out.update({
            'net_power_w_avg': round(avg_w - baseline_w, 2),
            'net_joules_per_output_token': round(net_j / gen_tokens, 3) if gen_tokens else None,
            'net_wh_per_answer': round(net_j / 3600 / len(records), 4),
        })
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('run_dir', type=Path, help='Folder created by evaluate_ollama.py.')
    parser.add_argument('--resources', type=Path, help='resources_*.csv to use.')
    parser.add_argument('--baseline-w', type=float,
                        help='Idle whole-laptop power (W) to subtract.')
    args = parser.parse_args()

    models = {d.name: load_requests(d / 'requests.jsonl')
              for d in sorted(args.run_dir.iterdir())
              if (d / 'requests.jsonl').exists()}
    models = {name: recs for name, recs in models.items() if recs}
    if not models:
        raise SystemExit(f'No answered requests found under {args.run_dir}')
    all_recs = [r for recs in models.values() for r in recs]
    start = min(parse_utc(r['created_at']) for r in all_recs)
    end = max(parse_utc(r['created_at']) for r in all_recs)
    resources = args.resources or pick_resources(args.run_dir, start, end)
    samples = load_samples(resources) if resources else []
    if not resources:
        print('NOTE: no matching resources_*.csv found; reporting speed and accuracy only.')

    report = {'run': str(args.run_dir), 'resources_csv': str(resources) if resources else None,
              'baseline_w': args.baseline_w, 'models': {}}
    for name, records in models.items():
        report['models'][name] = {'accuracy': accuracy(args.run_dir / name / 'results.json'),
                                  **analyze_model(records, samples, args.baseline_w)}
    out_path = args.run_dir / 'analysis.json'
    out_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report['models'], indent=2))
    print(f'Saved to {out_path.resolve()}')


if __name__ == '__main__':
    main()
