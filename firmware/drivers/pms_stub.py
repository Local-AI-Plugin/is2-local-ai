#!/usr/bin/env python3
"""Pretend PMS board for testing without hardware.

Linux's i2c-stub module creates a fake I2C bus with fake chips whose registers we can
write. This tool fills two of them (0x6F and 0x6C) with the values a real LTC2945 would
hold, so the real code path (smbus2 -> kernel -> i2cdetect / ltc2945_test.py /
power_manager.py) can be exercised end to end. Only the chips are fake.

1. Load the fake bus (once per boot; needs sudo):
       sudo modprobe i2c-stub chip_addr=0x6c,0x6f
2. Fill the fake chips (no sudo; the 'i2c' group may use the bus):
       python3 firmware/drivers/pms_stub.py                 # one fixed reading
       python3 firmware/drivers/pms_stub.py --profile llm   # changes every second like an LLM run
       python3 firmware/drivers/pms_stub.py --bat-v 41      # e.g. a low battery
3. In another terminal, point the real tools at the fake bus number this prints:
       python3 firmware/drivers/ltc2945_test.py <bus>
4. Remove the fake bus when done:
       sudo modprobe -r i2c-stub
"""
import argparse
import glob
import math
import os
import sys
import time
from pathlib import Path

# Lets it also run as a plain script (see the same lines in power_manager.py).
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from firmware.drivers import ltc2945 as L
from firmware.drivers.pms_board import ADDR_BATTERY, ADDR_OUTPUT, R_SHUNT_OHM


def find_stub_bus():
    """Bus number of the i2c-stub adapter, or None if the module isn't loaded."""
    for d in glob.glob("/sys/bus/i2c/devices/i2c-*"):
        try:
            with open(os.path.join(d, "name")) as f:
                if "stub" in f.read().lower():
                    return int(d.rsplit("-", 1)[1])
        except (OSError, ValueError):
            continue
    return None


def chip_bytes(volts, amps, r_shunt=R_SHUNT_OHM):
    """{register: [bytes]} a real LTC2945 would hold for this voltage and current.

    Mirrors the chip: 12-bit codes stored left-aligned in two registers, and the 24-bit
    power register holding the product of the current and voltage codes.
    """
    v = max(0, min(0xFFF, round(volts / L.VIN_LSB_V)))
    i = max(0, min(0xFFF, round(amps * r_shunt / L.DSENSE_LSB_V)))
    p = v * i
    return {L.REG_VIN: [v >> 4, (v & 0xF) << 4],
            L.REG_DSENSE: [i >> 4, (i & 0xF) << 4],
            L.REG_POWER: [(p >> 16) & 0xFF, (p >> 8) & 0xFF, p & 0xFF]}


def load(bus, addr, volts, amps):
    """Write one chip's result registers on the fake bus."""
    for reg, data in chip_bytes(volts, amps).items():
        bus.write_i2c_block_data(addr, reg, data)


def llm_watts(t):
    """A repeating 30 s pattern of 12 V watts: idle, a prompt burst, then generation."""
    phase = t % 30
    if phase < 10:
        return 7.0 + 0.3 * math.sin(t)          # idle
    if phase < 13:
        return 16.0                             # reading the prompt (prefill)
    return 12.5 + 0.5 * math.sin(3 * t)         # writing the answer (generate)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", choices=("fixed", "llm"), default="fixed")
    ap.add_argument("--bat-v", type=float, default=48.10, help="battery-side volts (IC1)")
    ap.add_argument("--out-v", type=float, default=12.02, help="12 V-side volts (IC2)")
    ap.add_argument("--out-w", type=float, default=9.37, help="12 V-side watts for --profile fixed")
    ap.add_argument("--eff", type=float, default=0.93, help="converter efficiency used to derive IC1")
    args = ap.parse_args()

    bus_num = find_stub_bus()
    if bus_num is None:
        sys.exit("No fake bus found. Load it first:  sudo modprobe i2c-stub chip_addr=0x6c,0x6f")
    from smbus2 import SMBus

    with SMBus(bus_num) as bus:
        print(f"Fake PMS on I2C bus {bus_num}. Test with:  python3 firmware/drivers/ltc2945_test.py {bus_num}")
        while True:
            w12 = llm_watts(time.time()) if args.profile == "llm" else args.out_w
            # Derive the battery side from the 12 V side: same power plus converter loss.
            bat_w = w12 / args.eff
            load(bus, ADDR_OUTPUT, args.out_v, w12 / args.out_v)
            load(bus, ADDR_BATTERY, args.bat_v, bat_w / args.bat_v)
            if args.profile == "fixed":
                print(f"Loaded: IC1 {args.bat_v:.2f} V {bat_w:.2f} W | IC2 {args.out_v:.2f} V {w12:.2f} W. "
                      "Values stay until changed or the module is removed.")
                return
            print(f"\rIC2 {w12:5.2f} W  IC1 {bat_w:5.2f} W  (Ctrl+C to stop)", end="", flush=True)
            time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
