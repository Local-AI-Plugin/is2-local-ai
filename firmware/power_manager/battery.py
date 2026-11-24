"""Battery state of charge from the energy measured on the battery side (IC1).

Charge = 1 - (energy used since last full charge) / (usable pack energy).
The energy count is saved to `state_file` every `save_every_s` seconds and on exit, so a
reboot continues from where it was instead of assuming a full battery.
The count resets to zero whenever the pack voltage reaches `v_full` (charged).
"""
import json
import os


class Battery:
    def __init__(self, pack_wh, v_full, state_file=None, save_every_s=30.0):
        self.pack_j = pack_wh * 3600.0
        self.v_full = v_full
        self.state_file = state_file
        self.save_every_s = save_every_s
        self.used_j = 0.0
        self.total_j = 0.0          # battery energy since this process started (for J/query)
        self._last_save = None
        self._load()

    def _load(self):
        if not self.state_file:
            return
        try:
            with open(self.state_file) as f:
                self.used_j = max(0.0, float(json.load(f)["used_j"]))
        except (OSError, ValueError, KeyError, TypeError):
            pass

    def save(self):
        if not self.state_file:
            return
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            tmp = self.state_file + ".tmp"
            with open(tmp, "w") as f:
                json.dump({"used_j": round(self.used_j, 1)}, f)
            os.replace(tmp, self.state_file)
        except OSError:
            pass

    def update(self, watts, volts, dt, now):
        energy = max(0.0, watts) * max(0.0, dt)
        self.used_j += energy
        self.total_j += energy
        if volts >= self.v_full:
            self.used_j = 0.0
        if self._last_save is None:
            self._last_save = now
        elif now - self._last_save >= self.save_every_s:
            self.save()
            self._last_save = now

    @property
    def soc(self):
        return max(0.0, 1.0 - self.used_j / self.pack_j)
