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
    """One clock: a cpufreq policy (kHz) or a devfreq device (Hz).

    name  folder name, e.g. "policy4" (A76 cores 4-5) or "fdab0000.npu"
    path  the folder holding its control files
    kind  "cpufreq" or "devfreq"; the two kernel interfaces name their files differently

    `freqs` is the sorted list of frequencies the hardware supports. Caps are always
    picked from this list because the kernel rejects or rounds other values.
    """

    def __init__(self, name, path, kind):
        self.name, self.path, self.kind = name, path, kind
        # Same three settings, different file names in the two kernel interfaces.
        if kind == "cpufreq":
            avail, self.min_file, self.max_file = "scaling_available_frequencies", "scaling_min_freq", "scaling_max_freq"
        else:
            avail, self.min_file, self.max_file = "available_frequencies", "min_freq", "max_freq"
        self.freqs = sorted(int(x) for x in self._read(avail).split())

    def _read(self, fname):
        """Contents of one control file, whitespace stripped."""
        with open(os.path.join(self.path, fname)) as f:
            return f.read().strip()

    def _write(self, fname, value):
        """Write one control file. Needs root; raises OSError if the kernel refuses."""
        with open(os.path.join(self.path, fname), "w") as f:
            f.write(str(value))

    def limits(self):
        """(current minimum, current maximum) frequency."""
        return int(self._read(self.min_file)), int(self._read(self.max_file))

    def set_limits(self, lo, hi):
        """Write min and max in the order the kernel accepts (never min > max in between).

        Lowering: the new max may be below the current min (e.g. min locked at the top),
        so lower the min first. Raising: raise the max first, then the min.
        """
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
    """Find the clocks to throttle: every CPU policy, plus devfreq devices whose name
    contains one of `devfreq_match` (only the NPU by default, so memory and GPU are left
    alone). The roots can point at a fake folder tree for the tests."""
    out = []
    for p in sorted(glob.glob(os.path.join(cpufreq_root, "policy*"))):
        out.append(Domain(os.path.basename(p), p, "cpufreq"))
    for p in sorted(glob.glob(os.path.join(devfreq_root, "*"))):
        if any(m in os.path.basename(p).lower() for m in devfreq_match):
            out.append(Domain(os.path.basename(p), p, "devfreq"))
    return out


class Throttle:
    """Moves all throttled clocks together along a ladder of `n_steps` steps.

    n_steps      number of steps (step 0 = slowest, n_steps-1 = full speed)
    frac_min     fraction of max frequency at step 0
    backup_file  where the original limits are kept between restarts (None = don't keep)
    domains      clocks to control (default: discover() on the real board)

    Write failures do not raise; they are collected in `errors` so the power manager
    can log them and keep running.
    """

    def __init__(self, n_steps=12, frac_min=0.30, backup_file=None, domains=None):
        self.n_steps, self.frac_min = n_steps, frac_min
        self.domains = discover() if domains is None else domains
        self.backup_file = backup_file
        self.original = self._load_or_save_original()
        self.step = None
        self.errors = []

    def _load_or_save_original(self):
        """The limits to restore later: {clock name: [min, max]}.

        If a backup from an earlier run exists for the same clocks, that run may have
        died while throttled, so the backup (not the current, throttled limits) is the
        true original. Otherwise the current limits are saved as the backup.
        """
        current = {d.name: list(d.limits()) for d in self.domains}
        if self.backup_file:
            try:
                with open(self.backup_file) as f:
                    saved = json.load(f)
                if set(saved) == set(current):
                    return saved
            except (OSError, ValueError):
                pass          # no backup yet, or unreadable: fall through and make one
            try:
                os.makedirs(os.path.dirname(self.backup_file), exist_ok=True)
                with open(self.backup_file, "w") as f:
                    json.dump(current, f)
            except OSError:
                pass
        return current

    def fraction(self, k):
        """Fraction of max frequency at step k (linear from frac_min to 1.0)."""
        return self.frac_min + (1.0 - self.frac_min) * k / (self.n_steps - 1)

    def _set(self, d, lo, hi):
        """Set one clock's limits, recording (not raising) any failure."""
        try:
            d.set_limits(lo, hi)
        except OSError as e:
            self.errors.append(f"{d.name}: {e}")

    def apply_step(self, k):
        """Cap every clock for step k (clamped to the valid range). Returns the step used.

        The minimum goes to the lowest frequency so the clock can drop under load
        changes, and the maximum goes to the step's cap.
        """
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
        # Clean exit: the next start should record whatever limits are set then.
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
