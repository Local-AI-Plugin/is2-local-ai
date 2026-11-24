#!/usr/bin/env python3
"""Calibrate the throttle table: measure the ROCK's 12 V watts at every throttle step.

Hold each step for --seconds while an LLM load runs, record mean and peak watts, then
print the fastest step whose peak stays under each level's budget. Paste the printed
LEVEL_START_STEP into config.py.

Run the load yourself in another terminal, or give it with --load-cmd (restarted
whenever it finishes). Stop the power manager service first: both would set the clocks.

    sudo systemctl stop pms-power
    sudo python3 -m firmware.power_manager.calibrate --load-cmd "bash my_llm_load.sh"

Clocks are put back to what they were when it finishes or is interrupted.
"""
import argparse
import csv
import subprocess
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from firmware.drivers.pms_board import PMSBoard
from firmware.power_manager.config import LEVEL_BUDGET_W, Config
from firmware.power_manager.throttle import Throttle


def suggest(rows, budgets=LEVEL_BUDGET_W):
    """Level -> fastest step whose peak watts stay under that level's budget (step 0 if none)."""
    out = {}
    for level, budget in budgets.items():
        ok = [r["step"] for r in rows if r["w12_peak"] <= budget]
        out[level] = max(ok) if ok else 0
    return out


def main():
    cfg = Config.from_env()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bus", type=int, default=cfg.i2c_bus)
    ap.add_argument("--seconds", type=float, default=20.0, help="measurement time per step")
    ap.add_argument("--settle", type=float, default=3.0, help="wait after each clock change")
    ap.add_argument("--load-cmd", help="shell command that keeps the LLM busy")
    ap.add_argument("--out", default="pms_calibration.csv")
    args = ap.parse_args()

    throttle = Throttle(cfg.n_steps, cfg.frac_min, cfg.clock_backup)
    load = None
    rows = []
    try:
        with PMSBoard(args.bus, cfg.addr_battery, cfg.addr_output, cfg.r_shunt_ohm) as board:
            if board.missing():
                sys.exit(f"PMS chips not answering: {board.missing()}")
            for k in range(cfg.n_steps):
                throttle.apply_step(k)
                time.sleep(args.settle)
                if args.load_cmd and (load is None or load.poll() is not None):
                    load = subprocess.Popen(args.load_cmd, shell=True)
                watts = []
                end = time.time() + args.seconds
                while time.time() < end:
                    if args.load_cmd and load.poll() is not None:
                        load = subprocess.Popen(args.load_cmd, shell=True)
                    watts.append(board.read().output.watts)
                    time.sleep(cfg.sample_s)
                row = dict(step=k, fraction=round(throttle.fraction(k), 3),
                           w12_mean=round(sum(watts) / len(watts), 3), w12_peak=round(max(watts), 3),
                           **{f"cap_{n}": v for n, v in throttle.caps().items()})
                rows.append(row)
                print(f"step {k:2d}  {row['fraction'] * 100:5.1f} %  mean {row['w12_mean']:6.2f} W"
                      f"  peak {row['w12_peak']:6.2f} W", flush=True)
    except KeyboardInterrupt:
        print("\ninterrupted")
    finally:
        if load and load.poll() is None:
            load.terminate()
        throttle.restore()
    if rows:
        with open(args.out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"\nWrote {args.out}\nPaste into firmware/power_manager/config.py:")
        print(f"LEVEL_START_STEP = {suggest(rows)}")


if __name__ == "__main__":
    main()
