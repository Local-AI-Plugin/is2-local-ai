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

# Register addresses (datasheet register table). Multi-byte values start at the address
# given and continue in the next registers; the chip auto-increments during a block read.
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

# Size of one ADC count. Current and power also depend on the shunt, so they are
# worked out per chip in LTC2945.__init__.
DSENSE_LSB_V = 25e-6
VIN_LSB_V = 25e-3


class LTC2945:
    """One LTC2945 chip at a fixed I2C address.

    bus          an open smbus2.SMBus (or a fake with the same methods)
    addr         the chip's 7-bit I2C address, e.g. 0x6F
    r_shunt_ohm  the current-sense resistor on the board (0.010 Ω on Rev D)

    Every read method raises OSError if the chip does not answer.
    """

    def __init__(self, bus, addr, r_shunt_ohm):
        self.bus = bus
        self.addr = addr
        # Amps per count = sense-voltage step / shunt (2.5 mA with 10 mΩ).
        self.lsb_a = DSENSE_LSB_V / r_shunt_ohm
        # Watts per count: the chip's power value is current code × voltage code
        # (62.5 µW with 10 mΩ).
        self.lsb_w = self.lsb_a * VIN_LSB_V

    def present(self):
        """True if the chip answers at its address (used for the bring-up checks)."""
        try:
            self.bus.read_byte_data(self.addr, REG_CONTROL)
            return True
        except OSError:
            return False

    def _read12(self, reg):
        """Read a 12-bit result stored left-aligned in two registers (see module docstring)."""
        msb, lsb = self.bus.read_i2c_block_data(self.addr, reg, 2)
        return (msb << 4) | (lsb >> 4)

    def _read24(self, reg):
        """Read a 24-bit value from three registers, most significant byte first."""
        b2, b1, b0 = self.bus.read_i2c_block_data(self.addr, reg, 3)
        return (b2 << 16) | (b1 << 8) | b0

    def voltage_v(self):
        """Voltage on SENSE+ in volts (the side of the board this chip watches)."""
        return self._read12(REG_VIN) * VIN_LSB_V

    def current_a(self):
        """Current through the shunt in amps."""
        return self._read12(REG_DSENSE) * self.lsb_a

    def power_w(self):
        """Power in watts, as multiplied by the chip itself."""
        return self._read24(REG_POWER) * self.lsb_w

    def read(self):
        """(volts, amps, watts) from one pass over the three result registers."""
        return self.voltage_v(), self.current_a(), self.power_w()

    def set_max_power_alert(self, watts):
        """Pull the shared ALERT line low whenever power goes above `watts`.

        Writes the 24-bit threshold, then sets only the max-power bit in the ALERT
        register (read-modify-write, so other alert bits are kept). Returns the raw
        threshold code that was written.
        """
        # Clamp to the 24-bit register range before splitting into three bytes.
        code = max(0, min(0xFFFFFF, int(watts / self.lsb_w)))
        self.bus.write_i2c_block_data(self.addr, REG_MAX_POWER_THR,
                                      [(code >> 16) & 0xFF, (code >> 8) & 0xFF, code & 0xFF])
        alert = self.bus.read_byte_data(self.addr, REG_ALERT)
        self.bus.write_byte_data(self.addr, REG_ALERT, alert | ALERT_MAX_POWER)
        return code

    def clear_faults(self):
        """Read and clear the fault register (also releases the ALERT line).

        Returns the fault bits that were set, as read before clearing.
        """
        return self.bus.read_byte_data(self.addr, REG_FAULT_COR)
