#!/usr/bin/env python3
"""PMS power manager: runs on the ROCK 5T, talks to the power board over I2C.

Every 100 ms:
  1. Read both LTC2945 chips (battery side and 12 V side).
  2. Count battery energy and estimate the state of charge.
  3. Shut the OS down cleanly if the pack stays below PMS_V_SHUTDOWN for PMS_SHUTDOWN_HOLD_S.
  4. manage mode only: pick a power level from the AI state and the battery, then move the
     CPU/NPU clock caps so the measured 12 V watts stay within that level's budget.
Once per second: write one averaged line to the log (PMS_LOG_PATH).

Run from the repo root (root needed for the clock files, the log and shutdown):
    sudo python3 -m firmware.power_manager.power_manager                 # monitor mode
    sudo PMS_MODE=manage python3 -m firmware.power_manager.power_manager
Bench supply below 42 V: add PMS_V_SHUTDOWN=15.

Control logic (levels, closed loop, start steps) is the team's NOMAD reference design.
"""
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# When run as a plain script, Python only searches this file's folder. Add the repo root
# so the `firmware.…` imports below also work that way (python3 -m … doesn't need it).
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from firmware.communication import ai_state
from firmware.drivers.pms_board import PMSBoard
from firmware.power_manager.battery import Battery
from firmware.power_manager.config import (DEMAND_LEVEL, LEVEL_START_STEP, Config, budget_w)

# Closed-loop settings (manage mode)
ALPHA = 0.3          # smoothing of measured 12 V watts
STEP_DOWN_S = 0.25   # minimum time between down steps
STEP_UP_S = 1.0      # minimum time between up steps (slower up than down: no oscillation)
HEADROOM = 0.85      # step up only if smoothed watts < 85 % of budget
RETRY_S = 10.0       # after a step was over budget, do not climb back to it for this long
I2C_FAIL_LIMIT = 20  # consecutive failed reads (2 s) before releasing the clock caps


def battery_ceiling(soc):
    """Highest level the battery allows: the emptier the pack, the lower the cap, so the
    remaining charge lasts longer at the cost of LLM speed."""
    if soc > 0.50:
        return 5
    if soc > 0.30:
        return 4
    if soc > 0.15:
        return 3
    if soc > 0.05:
        return 2
    return 1


def choose_level(state, now, last_busy, soc, idle_hold_s):
    """The power level to use now, or None to keep the current one.

    state        busiest AI state (from ai_state.current_state)
    now          current time
    last_busy    last time the state was not idle
    soc          battery state of charge 0..1
    idle_hold_s  how long to stay at the busy level after work stops

    The hold stops the level bouncing down and up in the short gaps between two
    requests (e.g. between retrieval and the LLM call). The result is never above
    what the battery allows.
    """
    want = DEMAND_LEVEL.get(state, 1) if state != "idle" else 1
    if state == "idle" and now - last_busy < idle_hold_s:
        want = None                                   # caller keeps the current level
    return want if want is None else min(want, battery_ceiling(soc))


class PowerLoop:
    """Keeps the measured 12 V power at or under the budget by moving the throttle step.

    This is a closed loop: it doesn't trust a table of "step k uses X watts", it measures
    the real watts each cycle and corrects. Step down quickly when over budget, step up
    slowly when there is clear headroom, and remember steps that were too hot so it
    doesn't keep climbing back into them (that would oscillate).

    State kept between cycles:
      k       current throttle step
      p       smoothed 12 V watts
      t_down  time of the last step down, t_up of the last step up
      bad     {step: time} steps that went over budget recently
    """

    def __init__(self, throttle):
        self.throttle = throttle
        self.n = throttle.n_steps
        self.k = None
        self.p = None
        self.t_down = self.t_up = -1e9      # "long ago", so the first step is never blocked
        self.bad = {}

    def enter_level(self, level):
        """Jump straight to the level's start step (a new level means different work,
        so the old too-hot history no longer applies)."""
        self.k = min(LEVEL_START_STEP[level], self.n - 1)
        self.bad = {}
        self.throttle.apply_step(self.k)

    def update(self, p12, budget, t, alert=False):
        """Feed one measurement; move at most one step (two if far over). Returns the step.

        p12     measured 12 V watts this cycle
        budget  the level's budget in watts
        t       current time
        alert   True if this cycle went over budget × alert margin (forces a step down)
        """
        # Exponential smoothing: one spike can't throttle the ROCK, a sustained rise will.
        self.p = p12 if self.p is None else ALPHA * p12 + (1 - ALPHA) * self.p
        new = self.k
        if (alert or self.p > budget) and self.k > 0 and t - self.t_down >= STEP_DOWN_S:
            # Over budget: step down, two steps if more than 20 % over.
            self.bad[self.k] = t                                   # this step was too hot
            new = self.k - (2 if self.p > 1.2 * budget else 1)
            self.t_down = t
        elif (self.p < HEADROOM * budget and self.k < self.n - 1 and t - self.t_up >= STEP_UP_S
              and t - self.bad.get(self.k + 1, -1e9) >= RETRY_S):
            # Clear headroom, not too soon after the last step up, and the next step
            # hasn't been too hot in the last RETRY_S seconds: step up.
            new = self.k + 1
            self.t_up = t
        new = max(0, min(self.n - 1, new))
        if new != self.k:
            self.k = new
            self.throttle.apply_step(new)
        return self.k


class ShutdownGuard:
    """True once the pack voltage has stayed below the limit for `hold_s` seconds."""

    def __init__(self, v_limit, hold_s):
        self.v_limit, self.hold_s = v_limit, hold_s
        self.low_since = None          # when the voltage first went low, None while it is fine

    def update(self, volts, now):
        """Feed one voltage reading. A pack under load sags briefly (e.g. at the start of
        an LLM prompt), so only a voltage that *stays* low counts; any reading back above
        the limit restarts the timer."""
        if volts >= self.v_limit:
            self.low_since = None
            return False
        if self.low_since is None:
            self.low_since = now
        return now - self.low_since >= self.hold_s


class LogWindow:
    """Averages the 10 Hz samples into one log line per interval.

    Averaging (not just logging the last sample) keeps the energy in the log correct,
    and the peak catches short spikes the average would hide.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        """Start a new interval."""
        self.n = 0
        self.sum = {"bat_w": 0.0, "w12": 0.0, "bat_a": 0.0, "a12": 0.0}
        self.w12_peak = 0.0

    def add(self, r):
        """Add one board Reading to the interval."""
        self.n += 1
        self.sum["bat_w"] += r.battery.watts
        self.sum["w12"] += r.output.watts
        self.sum["bat_a"] += r.battery.amps
        self.sum["a12"] += r.output.amps
        self.w12_peak = max(self.w12_peak, r.output.watts)

    def mean(self, k):
        """Average of field `k` over the interval (None if no samples)."""
        return self.sum[k] / self.n if self.n else None


class PowerManager:
    """Ties everything together: board readings, battery, shutdown, logging and, in
    manage mode, the power level and closed loop.

    cfg           Config
    board         an open PMSBoard
    throttle      Throttle (required in manage mode, ignored in monitor mode)
    log           open text file for the JSON log (None = don't log)
    shutdown_cmd  command run on low battery; None in the tests so they don't power off

    tick() does one 100 ms cycle and is what the tests call directly with made-up
    times; run() just calls tick() on a timer.
    """

    def __init__(self, cfg, board, throttle=None, log=None, shutdown_cmd=("shutdown", "-h", "now")):
        if cfg.mode == "manage" and throttle is None:
            raise ValueError("manage mode needs a Throttle")
        self.cfg, self.board, self.throttle, self.log = cfg, board, throttle, log
        self.shutdown_cmd = shutdown_cmd
        self.battery = Battery(cfg.pack_wh, cfg.v_full, cfg.battery_file)
        self.guard = ShutdownGuard(cfg.v_shutdown, cfg.shutdown_hold_s)
        self.loop = PowerLoop(throttle) if cfg.mode == "manage" else None
        self.window = LogWindow()
        self.level = None          # current power level (stays None in monitor mode)
        self.last_busy = -1e9      # last time the AI was busy ("long ago" at start)
        self.t_prev = None         # time of the previous good reading, for energy dt
        self.t_log = None          # start of the current log interval
        self.fails = 0             # consecutive failed I2C reads
        self.released = False      # clock caps released after I2C failures
        self.shut_down = False
        self.last = None           # last good Reading

    # ---- one 100 ms cycle -------------------------------------------------------------
    def tick(self, now):
        """Run one cycle. Returns the log record if one was written, else None."""
        try:
            r = self.board.read()
        except OSError as e:
            return self._on_read_error(now, e)
        if self.released and self.loop:          # bus is back: resume control
            self.released = False
            self.loop.enter_level(self.level)
        self.fails = 0
        self.last = r

        # Energy: watts × time since the previous good reading (0 on the first one).
        dt = 0.0 if self.t_prev is None else now - self.t_prev
        self.t_prev = now
        self.battery.update(r.battery.watts, r.battery.volts, dt, now)
        self.window.add(r)

        state = ai_state.current_state(self.cfg.state_dir, now)
        if state != "idle":
            self.last_busy = now
        if self.loop:                             # manage mode only
            self._manage(r, state, now)

        if self.cfg.shutdown_enabled and self.guard.update(r.battery.volts, now):
            self._shutdown(now, r)
            return None

        # One averaged log line per log interval.
        if self.t_log is None:
            self.t_log = now
        if now - self.t_log >= self.cfg.log_every_s:
            rec = self._record(now, r, state)
            self._write(rec)
            self.window.reset()
            self.t_log = now
            return rec
        return None

    def _manage(self, r, state, now):
        """Manage mode: pick the level, then let the closed loop adjust the clocks."""
        want = choose_level(state, now, self.last_busy, self.battery.soc, self.cfg.idle_hold_s)
        if self.level is None:
            want = want or 5        # first cycle with no level yet: start at full power
        if want is not None and want != self.level:
            self.level = want
            self.loop.enter_level(self.level)
            self._set_alert()
        budget = budget_w(self.level)
        # Same condition that makes IC2 pull ALERT low; clear the chip's fault latch so
        # the line releases once power is back under the limit.
        alert = r.output.watts > budget * self.cfg.alert_margin
        if alert:
            try:
                self.board.output.clear_faults()
            except OSError:
                pass
        self.loop.update(r.output.watts, budget, now, alert)

    def _set_alert(self):
        """Program IC2's hardware power alert to the current level's budget plus margin.
        Best effort: a failed write is ignored (the software check above still works)."""
        try:
            self.board.output.set_max_power_alert(budget_w(self.level) * self.cfg.alert_margin)
        except OSError:
            pass

    def _on_read_error(self, now, err):
        """Count a failed read. At I2C_FAIL_LIMIT in a row, release the clock caps (we can't
        see the watts, so full speed is the safe choice) and log the error once."""
        self.fails += 1
        if self.fails == I2C_FAIL_LIMIT:
            if self.loop and not self.released:
                self.throttle.restore()          # fail safe: no caps while we are blind
                self.released = True
            rec = {"t": round(now, 2), "mode": self.cfg.mode, "error": f"I2C read failed {self.fails}x: {err}"}
            self._write(rec)
            return rec
        return None

    def _shutdown(self, now, r):
        """Low battery confirmed: save the charge count, log why, then power the OS off
        cleanly (before the board's hardware cut-off drops the 12 V without warning)."""
        self.shut_down = True
        self.battery.save()
        self._write({"t": round(now, 2), "mode": self.cfg.mode, "event": "low_battery_shutdown",
                     "bat_v": round(r.battery.volts, 3), "v_shutdown": self.cfg.v_shutdown})
        if self.shutdown_cmd:
            subprocess.run(list(self.shutdown_cmd), check=False)

    def _record(self, now, r, state):
        """Build one log line: averages from the window, voltages from the latest reading.
        Field meanings are listed in firmware/docs/FILE_GUIDE.md."""
        w = self.window
        bat_w, w12 = w.mean("bat_w"), w.mean("w12")
        rec = dict(t=round(now, 2), mode=self.cfg.mode, ai=state,
                   level=self.level, budget_w=budget_w(self.level) if self.level else None,
                   step=self.loop.k if self.loop else None,
                   bat_v=round(r.battery.volts, 3), bat_a=round(w.mean("bat_a"), 4), bat_w=round(bat_w, 3),
                   v12=round(r.output.volts, 3), a12=round(w.mean("a12"), 4), w12=round(w12, 3),
                   w12_peak=round(w.w12_peak, 3),
                   eff=round(w12 / bat_w, 3) if bat_w > 1.0 else None,
                   soc=round(self.battery.soc, 4), energy_j=round(self.battery.total_j, 1),
                   samples=w.n)
        # Report clock-write failures (at most the last 3) once, then forget them.
        if self.throttle and self.throttle.errors:
            rec["clock_errors"] = self.throttle.errors[-3:]
            self.throttle.errors.clear()
        return rec

    def _write(self, rec):
        """Append one JSON line to the log and flush, so the dashboard sees it at once."""
        if self.log:
            self.log.write(json.dumps(rec) + "\n")
            self.log.flush()

    def close(self):
        """On exit: save the battery count and, in manage mode, give the clocks back."""
        self.battery.save()
        if self.throttle and self.cfg.mode == "manage":
            self.throttle.restore()

    # ---- main loop ----------------------------------------------------------------------
    def run(self, stop):
        """Call tick() every sample_s seconds until stop() returns True or the OS is
        shutting down. Manage mode starts at level 5 so nothing is slowed at boot."""
        if self.loop:
            self.level = 5
            self.loop.enter_level(5)
            self._set_alert()
        # Schedule against a fixed timeline (next_t += period) rather than sleeping a
        # fixed time, so the time spent inside tick() doesn't make the loop drift slower.
        next_t = time.monotonic()
        while not stop() and not self.shut_down:
            self.tick(time.time())
            next_t += self.cfg.sample_s
            time.sleep(max(0.0, next_t - time.monotonic()))


def open_log(path):
    """Open the log for appending (line-buffered), creating its folder if needed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return open(path, "a", buffering=1)


def main():
    """Entry point: read the config, open the board and log, run until stopped."""
    cfg = Config.from_env()
    # systemd stops the service with SIGTERM, Ctrl+C sends SIGINT. Both just set a flag;
    # the loop then exits normally so close() can restore the clocks and save the battery.
    stopping = []
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stopping.append(1))

    # Only manage mode creates a Throttle, so monitor mode never even opens a clock file.
    throttle = None
    if cfg.mode == "manage":
        from firmware.power_manager.throttle import Throttle
        throttle = Throttle(cfg.n_steps, cfg.frac_min, cfg.clock_backup)

    print(f"PMS power manager: mode={cfg.mode} bus={cfg.i2c_bus} log={cfg.log_path} "
          f"v_shutdown={cfg.v_shutdown} V", flush=True)
    with PMSBoard(cfg.i2c_bus, cfg.addr_battery, cfg.addr_output, cfg.r_shunt_ohm) as board, \
            open_log(cfg.log_path) as log:
        # Don't exit if a chip is missing: as a service it should start anyway and begin
        # logging as soon as the board answers (e.g. board powered after the ROCK).
        missing = board.missing()
        if missing:
            print("WARNING: not answering:", ", ".join(missing), "(will keep retrying)", flush=True)
        pm = PowerManager(cfg, board, throttle, log)
        try:
            pm.run(lambda: bool(stopping))
        finally:
            pm.close()
    print("stopped", flush=True)


if __name__ == "__main__":
    main()
