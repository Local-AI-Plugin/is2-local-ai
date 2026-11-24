"""Power manager tests: AI state, config, throttle, battery, shutdown and the control loop.
Fake I2C bus and a fake clock tree in a temp folder; the real board is never touched.

Run from the repo root:  python3 -m unittest discover -s tests -t .
"""
import io
import json
import os
import tempfile
import unittest

from firmware.communication import ai_state
from firmware.drivers.pms_board import PMSBoard
from firmware.power_manager import throttle as T
from firmware.power_manager.battery import Battery
from firmware.power_manager.calibrate import suggest
from firmware.power_manager.config import Config
from firmware.power_manager.power_manager import (I2C_FAIL_LIMIT, PowerLoop, PowerManager,
                                                  ShutdownGuard, choose_level)
from tests.firmware.fakes import FakeBus, make_sysfs, set_reading


class AIStateTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def test_busiest_writer_wins(self):
        ai_state.set_state("rag", "retrieve", self.d, now=100)
        ai_state.set_state("rkllm_server", "prefill", self.d, now=100)
        self.assertEqual(ai_state.current_state(self.d, now=101), "prefill")
        ai_state.set_state("rkllm_server", "idle", self.d, now=102)
        self.assertEqual(ai_state.current_state(self.d, now=103), "retrieve")

    def test_stale_busy_state_counts_as_idle(self):
        ai_state.set_state("rkllm_server", "generate", self.d, now=100)
        self.assertEqual(ai_state.current_state(self.d, now=100 + ai_state.MAX_AGE_S + 1), "idle")

    def test_missing_folder_never_raises(self):
        missing = os.path.join(self.d, "nope")
        self.assertFalse(ai_state.set_state("x", "prefill", missing))
        self.assertEqual(ai_state.current_state(missing), "idle")

    def test_busy_context_returns_to_idle(self):
        with ai_state.busy("rag", "retrieve", self.d):
            self.assertEqual(ai_state.current_state(self.d), "retrieve")
        self.assertEqual(ai_state.current_state(self.d), "idle")

    def test_unknown_state_rejected(self):
        with self.assertRaises(ValueError):
            ai_state.set_state("x", "thinking", self.d)


class ConfigTest(unittest.TestCase):
    def test_env_overrides(self):
        cfg = Config.from_env({"PMS_MODE": "manage", "PMS_I2C_BUS": "3", "PMS_ADDR_BATTERY": "0x6f",
                               "PMS_V_SHUTDOWN": "15", "PMS_SHUTDOWN_ENABLED": "no"})
        self.assertEqual((cfg.mode, cfg.i2c_bus, cfg.addr_battery, cfg.v_shutdown, cfg.shutdown_enabled),
                         ("manage", 3, 0x6F, 15.0, False))

    def test_defaults_are_safe(self):
        cfg = Config.from_env({})
        self.assertEqual((cfg.mode, cfg.i2c_bus), ("monitor", 3))

    def test_bad_mode(self):
        with self.assertRaises(ValueError):
            Config(mode="turbo")


class ThrottleTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.cpu, self.dev = make_sysfs(self.root)
        self.backup = os.path.join(self.root, "run", "clock_limits.json")

    def make(self):
        """A Throttle on the fake clock tree. Plain files accept any value, unlike the
        kernel, so each domain's _write is wrapped to fail the test if min ever ends up
        above max between two writes (the kernel would reject that write)."""
        doms = T.discover(self.cpu, self.dev)
        for d in doms:                     # fail if min > max at any moment, like the kernel
            orig = d._write

            def checked(fname, value, d=d, orig=orig):
                orig(fname, value)
                lo, hi = d.limits()
                if lo > hi:
                    raise AssertionError(f"{d.name}: min {lo} > max {hi} after writing {fname}")
            d._write = checked
        return T.Throttle(12, 0.30, self.backup, doms)

    def test_discovers_cpus_and_npu_but_not_memory(self):
        self.assertEqual([d.name for d in T.discover(self.cpu, self.dev)], ["policy0", "policy4", "fdab0000.npu"])

    def test_slowest_step_lowers_min_and_max_even_when_locked(self):
        th = self.make()
        th.apply_step(0)
        lim = {d.name: d.limits() for d in th.domains}
        self.assertEqual(lim["policy4"], (408000, 408000))           # 30 % of 2.304 GHz -> 408 MHz
        self.assertEqual(lim["fdab0000.npu"], (300000000, 300000000))
        self.assertEqual(th.errors, [])

    def test_full_step_and_restore(self):
        th = self.make()
        th.apply_step(5)
        th.apply_step(11)
        self.assertEqual(th.domains[1].limits(), (408000, 2304000))
        th.restore()
        self.assertEqual(th.domains[1].limits(), (2304000, 2304000))  # back to the max-clocks lock
        self.assertFalse(os.path.exists(self.backup))

    def test_restart_after_crash_uses_saved_original(self):
        th = self.make()
        th.apply_step(0)                   # crash here: clocks left throttled, backup kept
        th2 = self.make()
        self.assertEqual(th2.original["policy4"], [2304000, 2304000])
        th2.restore()
        self.assertEqual(th2.domains[1].limits(), (2304000, 2304000))


class BatteryTest(unittest.TestCase):
    def test_soc_persists_and_resets_when_full(self):
        f = os.path.join(tempfile.mkdtemp(), "battery.json")
        b = Battery(pack_wh=1.0, v_full=57.6, state_file=f)
        b.update(watts=10.0, volts=50.0, dt=180.0, now=0)            # 1800 J of 3600 J
        self.assertAlmostEqual(b.soc, 0.5)
        b.save()
        self.assertAlmostEqual(Battery(1.0, 57.6, f).soc, 0.5)
        b.update(10.0, 57.7, 0.1, 1)
        self.assertEqual(b.soc, 1.0)


class LogicTest(unittest.TestCase):
    def test_shutdown_needs_sustained_low_voltage(self):
        g = ShutdownGuard(42.0, 5.0)
        self.assertFalse(g.update(41.0, 0.0))
        self.assertFalse(g.update(43.0, 1.0))      # a dip that recovers resets the timer
        self.assertFalse(g.update(41.0, 2.0))
        self.assertFalse(g.update(41.0, 6.9))
        self.assertTrue(g.update(41.0, 7.0))

    def test_choose_level(self):
        self.assertEqual(choose_level("prefill", 10, 10, 0.9, 2.0), 5)
        self.assertEqual(choose_level("generate", 10, 10, 0.9, 2.0), 4)
        self.assertEqual(choose_level("prefill", 10, 10, 0.2, 2.0), 3)    # battery caps it
        self.assertIsNone(choose_level("idle", 11, 10, 0.9, 2.0))         # hold after work
        self.assertEqual(choose_level("idle", 13, 10, 0.9, 2.0), 1)

    def test_power_loop_steps_down_over_budget_and_back_up(self):
        # Rec stands in for a Throttle and just records which steps were applied.
        class Rec:
            n_steps = 12

            def __init__(self):
                self.steps = []

            def apply_step(self, k):
                self.steps.append(k)
        th = Rec()
        loop = PowerLoop(th)
        loop.enter_level(1)                                   # start step 1, budget 10 W
        self.assertEqual(loop.update(14.0, 10.0, t=0.0), 0)   # over budget -> down
        loop.p = None                                         # forget the smoothed 14 W
        self.assertEqual(loop.update(5.0, 10.0, t=20.0), 1)   # lots of room -> up
        self.assertEqual(th.steps, [1, 0, 1])

    def test_calibration_suggestion(self):
        rows = [dict(step=k, w12_peak=6.0 + 2.5 * k) for k in range(12)]
        self.assertEqual(suggest(rows), {1: 1, 2: 4, 3: 6, 4: 9, 5: 11})


class PowerManagerTest(unittest.TestCase):
    """Whole-program tests: a fake board reading 50 V / 0.20 A (10 W) on the battery side
    and 12 V / 0.75 A (9 W) on the 12 V side, a temp AI-state folder, and the log written
    to memory. tick() is called with made-up times, so no test waits in real time."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.bus = FakeBus()
        self.bus.add_chip(0x6F)
        self.bus.add_chip(0x6C)
        set_reading(self.bus, 0x6F, 50.0, 0.20)
        set_reading(self.bus, 0x6C, 12.0, 0.75)
        self.board = PMSBoard(bus=self.bus)
        self.state_dir = os.path.join(self.tmp, "state")
        os.makedirs(self.state_dir)
        self.log = io.StringIO()

    def cfg(self, **kw):
        """Config with every file path inside the temp folder, plus any overrides."""
        base = dict(battery_file=os.path.join(self.tmp, "battery.json"), state_dir=self.state_dir,
                    clock_backup=os.path.join(self.tmp, "clocks.json"))
        base.update(kw)
        return Config(**base)

    def records(self):
        return [json.loads(x) for x in self.log.getvalue().splitlines()]

    def test_monitor_mode_logs_once_per_second_and_never_touches_clocks(self):
        pm = PowerManager(self.cfg(), self.board, throttle=None, log=self.log, shutdown_cmd=None)
        for i in range(25):
            pm.tick(1000.0 + i * 0.1)
        recs = self.records()
        self.assertEqual(len(recs), 2)
        r = recs[0]
        self.assertEqual((r["mode"], r["level"], r["step"]), ("monitor", None, None))
        self.assertAlmostEqual(r["w12"], 9.0, places=2)
        self.assertAlmostEqual(r["bat_w"], 10.0, places=2)
        self.assertAlmostEqual(r["eff"], 0.9, places=2)
        self.assertGreater(r["energy_j"], 0)

    def test_clock_jump_does_not_add_energy(self):
        pm = PowerManager(self.cfg(), self.board, None, self.log, shutdown_cmd=None)
        pm.tick(1000.0)
        pm.tick(1000.1)
        before = pm.battery.total_j
        pm.tick(1000.1 + 3600.0)            # wall clock jumps forward one hour
        self.assertLessEqual(pm.battery.total_j - before, 10.0 * 1.0 + 1e-6)   # ≤ 10 W × 1 s
        pm.tick(500.0)                      # and backwards
        self.assertGreaterEqual(pm.battery.total_j, before)

    def test_manage_mode_follows_ai_state(self):
        cpu, dev = make_sysfs(os.path.join(self.tmp, "sys"))
        th = T.Throttle(12, 0.30, os.path.join(self.tmp, "clocks.json"), T.discover(cpu, dev))
        pm = PowerManager(self.cfg(mode="manage"), self.board, th, self.log, shutdown_cmd=None)
        pm.level = 5
        pm.loop.enter_level(5)
        ai_state.set_state("rkllm_server", "prefill", self.state_dir, now=0)
        pm.tick(1.0)
        self.assertEqual(pm.level, 5)
        ai_state.set_state("rkllm_server", "idle", self.state_dir, now=2)
        pm.tick(2.5)                    # inside the 2 s hold: stays at 5
        self.assertEqual(pm.level, 5)
        pm.tick(5.0)
        self.assertEqual(pm.level, 1)
        pm.close()
        self.assertEqual(th.domains[1].limits(), (2304000, 2304000))

    def test_i2c_loss_releases_clock_caps(self):
        cpu, dev = make_sysfs(os.path.join(self.tmp, "sys"))
        th = T.Throttle(12, 0.30, os.path.join(self.tmp, "clocks.json"), T.discover(cpu, dev))
        pm = PowerManager(self.cfg(mode="manage"), self.board, th, self.log, shutdown_cmd=None)
        pm.level = 1
        pm.loop.enter_level(1)
        self.bus.fail = True
        for i in range(I2C_FAIL_LIMIT):
            pm.tick(i * 0.1)
        self.assertTrue(pm.released)
        self.assertEqual(th.domains[1].limits(), (2304000, 2304000))
        self.assertIn("error", self.records()[-1])

    def test_low_battery_shutdown_after_hold(self):
        set_reading(self.bus, 0x6F, 41.0, 0.25)
        pm = PowerManager(self.cfg(shutdown_hold_s=1.0), self.board, None, self.log, shutdown_cmd=None)
        for i in range(10):
            pm.tick(i * 0.1)
        self.assertFalse(pm.shut_down)
        pm.tick(1.0)
        self.assertTrue(pm.shut_down)
        self.assertEqual(self.records()[-1]["event"], "low_battery_shutdown")


if __name__ == "__main__":
    unittest.main()
