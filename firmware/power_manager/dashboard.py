#!/usr/bin/env python3
"""PMS live dashboard: a web page showing the power board and the ROCK in real time.

    sudo python3 -m firmware.power_manager.dashboard          # real data from the power log
    python3 -m firmware.power_manager.dashboard --demo        # simulated data, any computer

Then open http://<rock-ip>:8080 on a phone or laptop on the same network.
Standard library only. Read-only: the page has no controls.

Data sources:
  PMS_LOG_PATH (/var/log/pms/power.jsonl)   written by power_manager.py
  /sys/devices/system/cpu/cpufreq/*         CPU frequency caps
  /sys/class/devfreq/*npu*                  NPU frequency cap
  /sys/class/thermal/thermal_zone*          ROCK temperature (the PMS has no temperature sensor)
"""
import glob
import json
import os
import random
import sys
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.environ.get("PMS_LOG_PATH", "/var/log/pms/power.jsonl")
PORT = int(os.environ.get("PMS_DASH_PORT", "8080"))
PACK_WH = float(os.environ.get("PMS_PACK_WH", "500"))        # same value as the power service
V_SHUTDOWN = float(os.environ.get("PMS_V_SHUTDOWN", "42.0"))  # same value as the power service
DEMO = "--demo" in sys.argv
STALE_S = 5.0          # log older than this = power_manager.py is not running
HISTORY_S = 120        # seconds of chart history kept in memory

history = deque(maxlen=HISTORY_S)
latest = {}
lock = threading.Lock()


def read_last_record(path):
    """Newest complete measurement line of the log, or None."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 8192))
            lines = f.read().splitlines()
    except OSError:
        return None
    for raw in reversed(lines):
        try:
            rec = json.loads(raw)
        except ValueError:
            continue          # half-written line
        if "w12" in rec:      # skip error / event lines
            return rec
    return None


def _num(path):
    try:
        with open(path) as f:
            return float(f.read().split()[0])
    except (OSError, ValueError, IndexError):
        return None


def rock_stats():
    cpu = [v for v in (_num(p) for p in glob.glob("/sys/devices/system/cpu/cpufreq/policy*/scaling_max_freq")) if v]
    npu = [v for v in (_num(os.path.join(p, "max_freq")) for p in glob.glob("/sys/class/devfreq/*")
                       if "npu" in p.lower()) if v]
    temps = [v for v in (_num(p) for p in glob.glob("/sys/class/thermal/thermal_zone*/temp")) if v is not None]
    return dict(cpu_ghz=round(max(cpu) / 1e6, 2) if cpu else None,      # kHz
                npu_ghz=round(max(npu) / 1e9, 2) if npu else None,      # Hz
                temp_c=round(max(temps) / 1000, 1) if temps else None)  # millidegrees


class Demo:
    """Fake data that behaves like power_manager.py in manage mode."""
    PHASES = ["idle", "retrieve", "prefill", "generate", "generate", "idle"]
    START_STEP = {1: 1, 2: 4, 3: 7, 4: 9, 5: 11}

    def __init__(self):
        self.t0 = time.time()
        self.soc = 0.82

    def record(self):
        t = time.time()
        ai = self.PHASES[int((t - self.t0) // 10) % len(self.PHASES)]
        level = {"prefill": 5, "generate": 4, "retrieve": 4}.get(ai, 1)
        budget = 10.0 + 6.5 * (level - 1)
        if ai == "idle":
            w12 = 7 + random.random() * 1.5
        else:
            w12 = budget * (0.78 + random.random() * 0.17)
            if random.random() < 0.04:
                w12 = budget * 1.12            # occasional overshoot -> alert
        eff = 0.93
        bat_w = w12 / eff
        self.soc = max(0.0, self.soc - bat_w / (PACK_WH * 3600) * 20)
        bat_v = 40 + self.soc * 14
        step = max(0, self.START_STEP[level] - (1 if w12 > budget else 0))
        frac = 0.3 + 0.7 * step / 11
        return dict(t=t, mode="manage", level=level, budget_w=budget, step=step, ai=ai,
                    bat_v=round(bat_v, 3), bat_a=round(bat_w / bat_v, 4), bat_w=round(bat_w, 3),
                    v12=round(12 + random.random() * 0.04, 3), a12=round(w12 / 12, 4), w12=round(w12, 3),
                    eff=eff, soc=round(self.soc, 4),
                    cpu_ghz=round(2.3 * frac, 2), npu_ghz=round(1.0 * frac, 2), temp_c=round(40 + w12 * 0.4, 1))


def sampler():
    demo = Demo() if DEMO else None
    while True:
        rec = demo.record() if demo else read_last_record(LOG)
        if rec:
            if not demo:
                rec.update(rock_stats())
            rec["stale"] = time.time() - rec.get("t", 0) > STALE_S
            bw = rec.get("bat_w") or 0
            rec["runtime_h"] = round(rec.get("soc", 0) * PACK_WH / bw, 1) if bw > 0.5 else None
            budget = rec.get("budget_w")
            if rec.get("bat_v", 99) < V_SHUTDOWN + 2:
                rec["alert"] = "battery_low"
            elif budget and rec.get("w12", 0) > budget * 1.10:
                rec["alert"] = "over_budget"
            else:
                rec["alert"] = None
        with lock:
            latest.clear()
            latest.update(rec or {"missing": True})
            if rec and not rec["stale"]:
                history.append(dict(t=round(rec["t"], 1), w12=rec.get("w12"), budget_w=rec.get("budget_w")))
        time.sleep(1.0)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            with open(os.path.join(HERE, "dashboard.html"), "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
        elif path == "/api/latest":
            with lock:
                body = json.dumps(dict(latest=dict(latest), history=list(history),
                                       pack_wh=PACK_WH, demo=DEMO, log=LOG))
            self._send(200, body.encode(), "application/json")
        else:
            self._send(404, b"not found", "text/plain")

    def log_message(self, *args):
        pass          # keep the terminal quiet


def main():
    threading.Thread(target=sampler, daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"PMS dashboard {'(DEMO DATA) ' if DEMO else ''}on http://localhost:{PORT}")
    print(f"From another device: http://<this computer's IP>:{PORT}   (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
