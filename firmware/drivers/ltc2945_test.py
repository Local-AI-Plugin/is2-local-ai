#!/usr/bin/env python3
"""PMS bring-up test: checks both LTC2945 chips answer, then prints V / A / W once per second.

Run from the repo root, before the power manager:
    python3 firmware/drivers/ltc2945_test.py          # bus 3 (pins 13/15)
    python3 firmware/drivers/ltc2945_test.py 3

No sudo needed when your user is in the 'i2c' group. Ctrl+C stops it.
"""
import sys
import time
from pathlib import Path

# When run as a plain script (python3 firmware/drivers/ltc2945_test.py), Python only
# searches this file's folder. Add the repo root so `firmware.…` imports work too.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from firmware.drivers.pms_board import DEFAULT_BUS, PMSBoard


def fmt(name, side):
    """One side of a reading as a fixed-width text column."""
    return f"{name}: {side.volts:6.2f} V {side.amps:6.3f} A {side.watts:6.2f} W"


def main(argv):
    """Check both chips, then print readings until Ctrl+C. Returns the exit code."""
    bus = int(argv[1]) if len(argv) > 1 else DEFAULT_BUS
    print(f"Using I2C bus {bus}")
    try:
        board = PMSBoard(bus).open()
    except ImportError as e:
        print(e)
        return 1
    except OSError as e:
        print(f"Cannot open /dev/i2c-{bus}: {e}\nIs the I2C3-M1 overlay enabled? (see firmware/docs/PMS_BRINGUP.md)")
        return 1
    try:
        # Report each chip separately so a bad solder joint points at one part.
        missing = board.missing()
        for name, addr in (("IC1 battery (48 V)", board.addr_battery), ("IC2 12 V output", board.addr_output)):
            ok = not any(f"0x{addr:02X}" in m for m in missing)
            print(f"  {'OK     ' if ok else 'MISSING'}  {name} at 0x{addr:02X}")
        if len(missing) == 2:
            print("\nNo chips answered. Check: board powered? J3 wired to pins 13/15? GND connected?")
            return 1
        if missing:
            print("\nOne chip is missing: check its solder joints. Readings below will fail for it.")
            return 1
        print("\nReading once per second (Ctrl+C to stop)\n")
        while True:
            r = board.read()
            eff = f"  eff {r.efficiency * 100:4.1f} %" if r.efficiency else ""
            print(f"{fmt('IC1 battery (48 V)', r.battery)} | {fmt('IC2 12 V output', r.output)}{eff}", flush=True)
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nstopped")
        return 0
    finally:
        board.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
