"""Power manager settings.

Every value can be overridden by an environment variable named PMS_<FIELD IN CAPITALS>
(the systemd service sets them), so nothing here needs editing on the board:
    PMS_MODE=manage PMS_V_SHUTDOWN=15 python3 -m firmware.power_manager.power_manager

Modes
  monitor (default)  Read the board, log watts, track the battery, shut down on low battery.
                     Never touches the clocks: the max-clocks service keeps them at maximum,
                     so benchmark (V&V) results stay comparable with earlier tests.
  manage             Also cap the CPU/NPU clocks so the ROCK stays within the power level's
                     budget (slow between queries, full speed while the LLM works).
"""
import os
from dataclasses import dataclass, fields

MODES = ("monitor", "manage")

# Power level -> 12 V budget in watts (10 + 6.5 * (level - 1)).
LEVEL_BUDGET_W = {1: 10.0, 2: 16.5, 3: 23.0, 4: 29.5, 5: 36.0}

# Throttle step each level starts at; the closed loop corrects it from the measured watts.
# PLACEHOLDER until calibrate.py has been run on the real board (fastest step under budget).
LEVEL_START_STEP = {1: 1, 2: 4, 3: 7, 4: 9, 5: 11}

# AI state -> level it asks for.
DEMAND_LEVEL = {"idle": 1, "retrieve": 4, "generate": 4, "prefill": 5}


@dataclass
class Config:
    """Every setting the power manager uses, with its default.

    Build it with Config.from_env() on the board (reads PMS_* variables), or
    Config(field=value, ...) in tests. An unknown mode raises ValueError.
    """
    # I2C (ROCK 5T pins 13/15, I2C3-M1 overlay)
    i2c_bus: int = 3
    addr_battery: int = 0x6F
    addr_output: int = 0x6C
    r_shunt_ohm: float = 0.010

    mode: str = "monitor"

    # Battery (16S LiFePO4)
    pack_wh: float = 500.0          # usable energy; set to the real pack
    v_full: float = 57.6            # IC1 reading at full charge; resets the charge count
    v_shutdown: float = 42.0        # clean OS shutdown below this (board cuts off near 39.7 V)
    shutdown_hold_s: float = 5.0    # voltage must stay low this long (ignores load dips)
    shutdown_enabled: bool = True

    # Timing
    sample_s: float = 0.1           # control loop period
    log_every_s: float = 1.0        # one averaged log line per second
    idle_hold_s: float = 2.0        # stay at the busy level this long after work ends

    # Throttle ladder (manage mode)
    n_steps: int = 12
    frac_min: float = 0.30          # slowest step = 30 % of each clock's maximum
    alert_margin: float = 1.10      # ALERT fires at budget * this

    # Files
    log_path: str = "/var/log/pms/power.jsonl"
    battery_file: str = "/var/lib/pms/battery.json"
    clock_backup: str = "/run/pms/clock_limits.json"
    state_dir: str = "/run/pms/ai_state.d"

    def __post_init__(self):
        """Runs after the fields are set: reject a mistyped mode instead of guessing."""
        if self.mode not in MODES:
            raise ValueError(f"PMS_MODE must be one of {MODES}, got {self.mode!r}")

    @classmethod
    def from_env(cls, env=None):
        """Defaults, overridden by any PMS_<FIELD> variable that is set and not empty.

        env  a dict to read instead of os.environ (the tests use this)

        Each value is converted to the field's type: bools accept 1/true/yes/on,
        ints accept decimal or hex ("3", "0x6F").
        """
        env = os.environ if env is None else env
        kwargs = {}
        # Walk the dataclass fields so a new setting is picked up from the environment
        # automatically, without editing this function.
        for f in fields(cls):
            raw = env.get("PMS_" + f.name.upper())
            if raw in (None, ""):
                continue
            if f.type in (bool, "bool"):
                kwargs[f.name] = raw.strip().lower() in ("1", "true", "yes", "on")
            elif f.type in (int, "int"):
                kwargs[f.name] = int(raw, 0)          # accepts 3 or 0x6F
            elif f.type in (float, "float"):
                kwargs[f.name] = float(raw)
            else:
                kwargs[f.name] = raw
        return cls(**kwargs)


def budget_w(level):
    """12 V watt budget for a power level (1..5)."""
    return LEVEL_BUDGET_W[level]
