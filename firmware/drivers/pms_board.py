"""The power management board (PMS) as the ROCK 5T sees it: two LTC2945 chips on one I2C bus.

  IC1 at 0x6F  battery side (48 V in): pack voltage, battery current, battery power
  IC2 at 0x6C  output side (12 V out): 12 V voltage, ROCK current, ROCK power

Wiring (PMS J3 -> ROCK 5T 40-pin header), I2C3-M1 overlay, Linux bus 3:
  J3.1 +3V3 -> pin 1   J3.2 SDA -> pin 15   J3.3 SCL -> pin 13
  J3.4 ALERT -> pin 7  J3.5 GND -> pin 9

Usage:
    with PMSBoard(bus_num=3) as board:
        r = board.read()
        print(r.battery.watts, r.output.watts, r.efficiency)
"""
import time
from dataclasses import dataclass

from firmware.drivers.ltc2945 import LTC2945

DEFAULT_BUS = 3
ADDR_BATTERY = 0x6F
ADDR_OUTPUT = 0x6C
R_SHUNT_OHM = 0.010


@dataclass(frozen=True)
class Side:
    """One side of the board at one moment: volts, amps and watts."""
    volts: float
    amps: float
    watts: float


@dataclass(frozen=True)
class Reading:
    """Both sides of the board read together. `t` is Unix time of the reading."""
    t: float
    battery: Side
    output: Side

    @property
    def efficiency(self):
        """12 V watts out / battery watts in, or None when the load is too small to judge."""
        return self.output.watts / self.battery.watts if self.battery.watts > 1.0 else None


class PMSBoard:
    """Opens the I2C bus and gives access to both chips.

    Normally it opens /dev/i2c-<bus_num> itself (call open(), or use it in a with-block).
    Passing `bus` instead uses an already-open bus or a fake one; the tests do this.
    After opening, `board.battery` (IC1) and `board.output` (IC2) are LTC2945 objects.
    """

    def __init__(self, bus_num=DEFAULT_BUS, addr_battery=ADDR_BATTERY, addr_output=ADDR_OUTPUT,
                 r_shunt_ohm=R_SHUNT_OHM, bus=None):
        self.bus_num = bus_num
        self.addr_battery = addr_battery
        self.addr_output = addr_output
        self.r_shunt_ohm = r_shunt_ohm
        self.bus = bus
        self._owns_bus = False      # True only if we opened the bus, so only then do we close it
        self.battery = self.output = None
        if bus is not None:
            self._make_chips()

    def _make_chips(self):
        """Create the two chip objects on the current bus."""
        self.battery = LTC2945(self.bus, self.addr_battery, self.r_shunt_ohm)
        self.output = LTC2945(self.bus, self.addr_output, self.r_shunt_ohm)

    def open(self):
        """Open /dev/i2c-<bus_num> unless a bus was passed in. Returns self.

        Raises ImportError if smbus2 is not installed and OSError if the bus device
        does not exist (I2C overlay not enabled).
        """
        if self.bus is None:
            try:
                from smbus2 import SMBus     # imported here so tests run without smbus2 installed
            except ImportError as e:
                raise ImportError("smbus2 is missing: sudo apt install python3-smbus2") from e
            self.bus = SMBus(self.bus_num)
            self._owns_bus = True
            self._make_chips()
        return self

    def close(self):
        """Close the bus if this object opened it."""
        if self._owns_bus and self.bus is not None:
            self.bus.close()
            self.bus = None
            self._owns_bus = False

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.close()

    def missing(self):
        """Names of the chips that do not answer (empty list = both fine)."""
        out = []
        if not self.battery.present():
            out.append(f"IC1 battery side 0x{self.addr_battery:02X}")
        if not self.output.present():
            out.append(f"IC2 12 V side 0x{self.addr_output:02X}")
        return out

    def read(self):
        """One reading of both sides. Raises OSError if the bus or a chip fails."""
        t = time.time()
        return Reading(t, Side(*self.battery.read()), Side(*self.output.read()))
