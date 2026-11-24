"""Fake hardware for the firmware tests: an I2C bus with LTC2945 register files, and a
cpufreq/devfreq folder tree. Nothing here touches the real board."""
import os

from firmware.drivers import ltc2945 as L


class FakeBus:
    """Mimics smbus2.SMBus for byte and block reads/writes. Unknown addresses raise OSError."""

    def __init__(self):
        self.chips = {}
        self.fail = False

    def add_chip(self, addr):
        self.chips[addr] = [0] * 0x32
        self.chips[addr][L.REG_CONTROL] = 0x05
        return self.chips[addr]

    def _regs(self, addr):
        if self.fail or addr not in self.chips:
            raise OSError(121, "Remote I/O error")
        return self.chips[addr]

    def read_byte_data(self, addr, reg):
        return self._regs(addr)[reg]

    def write_byte_data(self, addr, reg, val):
        self._regs(addr)[reg] = val

    def read_i2c_block_data(self, addr, reg, n):
        return list(self._regs(addr)[reg:reg + n])

    def write_i2c_block_data(self, addr, reg, data):
        self._regs(addr)[reg:reg + len(data)] = list(data)

    def close(self):
        pass


def set_reading(bus, addr, volts, amps, r_shunt=0.010):
    """Load a chip's result registers as the LTC2945 would for this voltage and current."""
    regs = bus.chips[addr]
    v = round(volts / L.VIN_LSB_V)
    i = round(amps * r_shunt / L.DSENSE_LSB_V)
    p = v * i                                     # the chip multiplies the two codes
    regs[L.REG_VIN], regs[L.REG_VIN + 1] = v >> 4, (v & 0xF) << 4
    regs[L.REG_DSENSE], regs[L.REG_DSENSE + 1] = i >> 4, (i & 0xF) << 4
    regs[L.REG_POWER:L.REG_POWER + 3] = [(p >> 16) & 0xFF, (p >> 8) & 0xFF, p & 0xFF]


def make_sysfs(root):
    """A small RK3588-like clock tree, locked at max like rock5t-max-clocks.service does."""
    cpu = os.path.join(root, "cpufreq")
    dev = os.path.join(root, "devfreq")
    a55 = [408000, 816000, 1200000, 1608000, 1800000]
    a76 = [408000, 816000, 1200000, 1608000, 2016000, 2304000]
    npu = [300000000, 500000000, 700000000, 1000000000]
    for name, freqs, files in (
            (os.path.join(cpu, "policy0"), a55, ("scaling_available_frequencies", "scaling_min_freq", "scaling_max_freq")),
            (os.path.join(cpu, "policy4"), a76, ("scaling_available_frequencies", "scaling_min_freq", "scaling_max_freq")),
            (os.path.join(dev, "fdab0000.npu"), npu, ("available_frequencies", "min_freq", "max_freq")),
            (os.path.join(dev, "dmc"), npu, ("available_frequencies", "min_freq", "max_freq"))):
        os.makedirs(name)
        avail, lo, hi = files
        for fname, val in ((avail, " ".join(map(str, freqs))), (lo, freqs[-1]), (hi, freqs[-1])):
            with open(os.path.join(name, fname), "w") as f:
                f.write(f"{val}\n")
    return cpu, dev
