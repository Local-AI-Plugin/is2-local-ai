"""LTC2945 driver and PMS board tests (fake I2C bus).

Run from the repo root:  python3 -m unittest discover -s tests -t .
"""
import unittest

from firmware.drivers import ltc2945 as L
from firmware.drivers.pms_board import PMSBoard
from tests.firmware.fakes import FakeBus, set_reading


class LTC2945Test(unittest.TestCase):
    def setUp(self):
        self.bus = FakeBus()
        self.bus.add_chip(0x6F)
        self.chip = L.LTC2945(self.bus, 0x6F, 0.010)

    def test_scaling_constants(self):
        self.assertAlmostEqual(self.chip.lsb_a, 2.5e-3)       # 2.5 mA per count with 10 mΩ
        self.assertAlmostEqual(self.chip.lsb_w, 62.5e-6)      # 62.5 µW per count

    def test_left_aligned_12_bit_decode(self):
        self.bus.chips[0x6F][L.REG_VIN:L.REG_VIN + 2] = [0xAB, 0xC0]   # code 0xABC = 2748
        self.assertAlmostEqual(self.chip.voltage_v(), 2748 * 0.025)

    def test_reading_matches_guide_example(self):
        set_reading(self.bus, 0x6F, 48.10, 0.210)
        v, a, w = self.chip.read()
        self.assertAlmostEqual(v, 48.10, places=2)
        self.assertAlmostEqual(a, 0.210, places=3)
        self.assertAlmostEqual(w, 48.10 * 0.210, delta=0.01)

    def test_full_scale_does_not_overflow(self):
        set_reading(self.bus, 0x6F, 0xFFF * 0.025, 0xFFF * 2.5e-3)
        v, a, w = self.chip.read()
        self.assertAlmostEqual(v, 102.375)
        self.assertAlmostEqual(a, 10.2375)
        self.assertAlmostEqual(w, 0xFFF * 0xFFF * 62.5e-6, places=6)

    def test_max_power_alert_writes_threshold_and_keeps_other_alert_bits(self):
        self.bus.chips[0x6F][L.REG_ALERT] = 0x04
        code = self.chip.set_max_power_alert(11.0)
        self.assertEqual(code, int(11.0 / 62.5e-6))
        regs = self.bus.chips[0x6F]
        got = (regs[0x0E] << 16) | (regs[0x0F] << 8) | regs[0x10]
        self.assertEqual(got, code)
        self.assertEqual(regs[L.REG_ALERT], 0x84)

    def test_present(self):
        self.assertTrue(self.chip.present())
        self.assertFalse(L.LTC2945(self.bus, 0x6C, 0.010).present())


class PMSBoardTest(unittest.TestCase):
    def test_read_both_sides_and_efficiency(self):
        bus = FakeBus()
        bus.add_chip(0x6F)
        bus.add_chip(0x6C)
        set_reading(bus, 0x6F, 48.0, 0.25)
        set_reading(bus, 0x6C, 12.0, 0.93)
        board = PMSBoard(bus=bus)
        self.assertEqual(board.missing(), [])
        r = board.read()
        self.assertAlmostEqual(r.battery.volts, 48.0)
        self.assertAlmostEqual(r.output.amps, 0.93, places=3)
        self.assertAlmostEqual(r.efficiency, (12.0 * 0.93) / (48.0 * 0.25), places=2)

    def test_missing_chip_named(self):
        bus = FakeBus()
        bus.add_chip(0x6F)
        board = PMSBoard(bus=bus)
        self.assertEqual(board.missing(), ["IC2 12 V side 0x6C"])
        with self.assertRaises(OSError):
            board.read()


if __name__ == "__main__":
    unittest.main()
