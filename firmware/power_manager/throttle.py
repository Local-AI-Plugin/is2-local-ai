"""CPU and NPU clock caps on the ROCK 5T (RK3588), through the kernel's cpufreq/devfreq files.

Step k = 0 .. n_steps-1 caps every clock at a fraction of its maximum:
    fraction(k) = frac_min + (1 - frac_min) * k / (n_steps - 1)     (step 0 slowest, last = full)

Why the minimum is lowered too: rock5t-max-clocks.service locks clocks by raising each
minimum up to the maximum (A55 cores 1.8 GHz, NPU 1 GHz). A lower maximum alone would then
be ignored or rejected, so each step sets min = lowest frequency and max = the cap.

The limits found at start are saved to `backup_file` (in /run, cleared at reboot) and
restored on exit. If the process is killed and restarted, the saved file is used, so a
throttled state is never mistaken for the original one.

Memory (dmc) and GPU clocks are not touched: memory speed is what limits LLM speed.
"""
import glob
import json
import os

CPUFREQ_ROOT = "/sys/devices/system/cpu/cpufreq"
DEVFREQ_ROOT = "/sys/class/devfreq"


class Domain:
    """One clock: a cpufreq policy (kHz) or a devfreq device (Hz)."""

    def __init__(self, name, path, kind):
        self.name, self.path, self.kind = name, path, kind
        if kind == "cpufreq":
            avail, self.min_file, self.max_file = "scaling_available_frequencies", "scaling_min_freq", "scaling_max_freq"
        else:
            avail, self.min_file, self.max_file = "available_frequencies", "min_freq", "max_freq"
        self.freqs = sorted(int(x) for x in self._read(avail).split())

    def _read(self, fname):
        with open(os.path.join(self.path, fname)) as f:
            return f.read().strip()

    def _write(self, fname, value):
        with open(os.path.join(self.path, fname), "w") as f:
            f.write(str(value))

    def limits(self):
        return int(self._read(self.min_file)), int(self._read(self.max_file))

    def set_limits(self, lo, hi):
        """Write min and max in the order the kernel accepts (never min > max in between)."""
        cur_lo, _ = self.limits()
        if hi < cur_lo:
            self._write(self.min_file, lo)
            self._write(self.max_file, hi)
        else:
            self._write(self.max_file, hi)
            self._write(self.min_file, lo)

    def cap_for(self, frac):
        """Highest available frequency at or below frac * max (the lowest one if none)."""
        limit = self.freqs[-1] * frac
        return max([f for f in self.freqs if f <= limit] or [self.freqs[0]])


def discover(cpufreq_root=CPUFREQ_ROOT, devfreq_root=DEVFREQ_ROOT, devfreq_match=("npu",)):
    out = []
    for p in sorted(glob.glob(os.path.join(cpufreq_root, "policy*"))):
        out.append(Domain(os.path.basename(p), p, "cpufreq"))
    for p in sorted(glob.glob(os.path.join(devfreq_root, "*"))):
        if any(m in os.path.basename(p).lower() for m in devfreq_match):
            out.append(Domain(os.path.basename(p), p, "devfreq"))
    return out


class Throttle:
    def __init__(self, n_steps=12, frac_min=0.30, backup_file=None, domains=None):
        self.n_steps, self.frac_min = n_steps, frac_min
        self.domains = discover() if domains is None else domains
        self.backup_file = backup_file
        self.original = self._load_or_save_original()
        self.step = None
        self.errors = []

    def _load_or_save_original(self):
        current = {d.name: list(d.limits()) for d in self.domains}
        if self.backup_file:
            try:
                with open(self.backup_file) as f:
                    saved = json.load(f)
                if set(saved) == set(current):
                    return saved
            except (OSError, ValueError):
                pass
            try:
                os.makedirs(os.path.dirname(self.backup_file), exist_ok=True)
                with open(self.backup_file, "w") as f:
                    json.dump(current, f)
            except OSError:
                pass
        return current

    def fraction(self, k):
        return self.frac_min + (1.0 - self.frac_min) * k / (self.n_steps - 1)

    def _set(self, d, lo, hi):
        try:
            d.set_limits(lo, hi)
        except OSError as e:
            self.errors.append(f"{d.name}: {e}")

    def apply_step(self, k):
        k = max(0, min(self.n_steps - 1, k))
        frac = self.fraction(k)
        for d in self.domains:
            self._set(d, d.freqs[0], d.cap_for(frac))
        self.step = k
        return k

    def restore(self):
        """Put every clock back to the limits found at start (e.g. the max-clocks lock)."""
        for d in self.domains:
            lo, hi = self.original[d.name]
            self._set(d, lo, hi)
        self.step = None
        if self.backup_file:
            try:
                os.remove(self.backup_file)
            except OSError:
                pass

    def caps(self):
        """{clock name: current max} for the log."""
        out = {}
        for d in self.domains:
            try:
                out[d.name] = d.limits()[1]
            except OSError:
                out[d.name] = None
        return out
