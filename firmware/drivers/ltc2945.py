"""Driver for one LTC2945 power monitor on the power management board (PMS).

The LTC2945 measures the voltage on its SENSE+ pin, the current through a shunt
resistor, and their product (power). The ROCK 5T reads it over I2C.

Register map and scaling follow the LTC2945 datasheet (register table):
  ΔSENSE (current)  12 bits, 25 µV per count  -> amps  = counts * 25 µV / R_shunt
  VIN    (voltage)  12 bits, 25 mV per count  -> volts = counts * 25 mV
  POWER             24 bits, product of the two -> watts = counts * 25 µV * 25 mV / R_shunt
12-bit values are left-aligned: the MSB register holds bits 11..4 and the top
nibble of the LSB register holds bits 3..0.

The `bus` argument is anything with the smbus2.SMBus read/write methods, so the
tests can pass a fake bus instead of real hardware.
"""

REG_CONTROL = 0x00
REG_ALERT = 0x01
REG_STATUS = 0x02
REG_FAULT = 0x03
REG_FAULT_COR = 0x04          # reading it returns the faults and clears them
REG_POWER = 0x05              # 0x05..0x07, 24 bits
REG_MAX_POWER_THR = 0x0E      # 0x0E..0x10, 24 bits
REG_DSENSE = 0x14             # 0x14..0x15
REG_VIN = 0x1E                # 0x1E..0x1F

ALERT_MAX_POWER = 0x80        # ALERT register bit 7: alert when power > max power threshold

DSENSE_LSB_V = 25e-6
VIN_LSB_V = 25e-3


class LTC2945:
    def __init__(self, bus, addr, r_shunt_ohm):
        self.bus = bus
        self.addr = addr
        self.lsb_a = DSENSE_LSB_V / r_shunt_ohm
        self.lsb_w = self.lsb_a * VIN_LSB_V

    def present(self):
        """True if the chip answers at its address."""
        try:
            self.bus.read_byte_data(self.addr, REG_CONTROL)
            return True
        except OSError:
            return False

    def _read12(self, reg):
        msb, lsb = self.bus.read_i2c_block_data(self.addr, reg, 2)
        return (msb << 4) | (lsb >> 4)

    def _read24(self, reg):
        b2, b1, b0 = self.bus.read_i2c_block_data(self.addr, reg, 3)
        return (b2 << 16) | (b1 << 8) | b0

    def voltage_v(self):
        return self._read12(REG_VIN) * VIN_LSB_V

    def current_a(self):
        return self._read12(REG_DSENSE) * self.lsb_a

    def power_w(self):
        return self._read24(REG_POWER) * self.lsb_w

    def read(self):
        """(volts, amps, watts) from one pass over the three result registers."""
        return self.voltage_v(), self.current_a(), self.power_w()

    def set_max_power_alert(self, watts):
        """Pull the shared ALERT line low whenever power goes above `watts`."""
        code = max(0, min(0xFFFFFF, int(watts / self.lsb_w)))
        self.bus.write_i2c_block_data(self.addr, REG_MAX_POWER_THR,
                                      [(code >> 16) & 0xFF, (code >> 8) & 0xFF, code & 0xFF])
        alert = self.bus.read_byte_data(self.addr, REG_ALERT)
        self.bus.write_byte_data(self.addr, REG_ALERT, alert | ALERT_MAX_POWER)
        return code

    def clear_faults(self):
        """Read and clear the fault register (also releases the ALERT line)."""
        return self.bus.read_byte_data(self.addr, REG_FAULT_COR)
