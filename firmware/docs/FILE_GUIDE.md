# Firmware file guide

This guide covers what each file under `firmware/` does, how the files fit together, and how to run them. The firmware connects the ROCK 5T (the compute module) to the power management system (PMS) board.

To bring up new hardware, follow [PMS_BRINGUP.md](PMS_BRINGUP.md).

## How it fits together

```
 LLM software on the ROCK                Power manager on the ROCK                PMS board
 (rkllm_server.py, rag.py)                                                        (no processor)

 "prefill" / "generate" /   state files   power_manager.py   I2C bus 3     IC1 LTC2945 0x6F  battery side, 48 V
 "retrieve" / "idle"  ───────────────────►  reads the AI   ◄──────────────► IC2 LTC2945 0x6C  12 V side, ROCK power
 communication/ai_state.py  /run/pms/       state and the     pins 13/15
                            ai_state.d/     watts
                                                │
                                                ├─► log: /var/log/pms/power.jsonl ──► dashboard (port 8080)
                                                └─► CPU/NPU clock caps (manage mode only)
```

There are two links:

1. **ROCK ↔ PMS, over I2C.** The ROCK is the I2C controller. It reads the volts, amps and watts that the two LTC2945 chips measure, and it can set the 12 V chip's power alert limit. The PMS board never starts a conversation; it only answers.
2. **LLM software ↔ power manager, through small state files.** Each AI program writes what it is doing into a file. The power manager reads those files to decide how much power the ROCK may use.

## Files

### `drivers/` (talking to the PMS chips)

| File | What it does |
|---|---|
| `ltc2945.py` | Driver for one LTC2945 chip. It holds the register addresses and converts raw readings into volts (25 mV per count), amps (25 µV per count ÷ 10 mΩ shunt = 2.5 mA) and watts (62.5 µW per count). It can also set the max-power alert limit and clear faults. It is the same job as a sensor driver written on top of STM32 HAL; here Linux and `smbus2` take the place of HAL. |
| `pms_board.py` | The whole PMS board as the ROCK sees it: opens I2C bus 3 and creates both chips (0x6F battery side, 0x6C 12 V side). `read()` returns one reading of both sides plus the converter efficiency. `missing()` names any chip that doesn't answer. |
| `ltc2945_test.py` | Bring-up test. It checks both chips answer, then prints V / A / W for both sides once per second. Run it first when the board is wired: `python3 firmware/drivers/ltc2945_test.py` |

### `communication/` (talking to the LLM software)

| File | What it does |
|---|---|
| `ai_state.py` | Shared by both sides. LLM programs call `set_state("rkllm_server", "prefill")`, or use `with busy("rag", "retrieve"):`. Each program writes its own file in `/run/pms/ai_state.d/`. The power manager calls `current_state()`, which returns the busiest state across all programs: `prefill` > `generate` > `retrieve` > `idle`. A busy state older than 15 minutes counts as idle, so a crashed program can't hold full power forever. If the folder doesn't exist, writing does nothing and never raises an error, so the LLM still works without the PMS. |

### `power_manager/` (the program that runs on the ROCK)

| File | What it does |
|---|---|
| `power_manager.py` | The main program. Every 100 ms it reads both chips, counts battery energy and checks for low battery. In manage mode it also picks a power level and adjusts the clocks. Once a second it writes one averaged line to the log. If I2C fails for 2 s, it removes all clock caps (fail-safe at full speed) and logs the error. |
| `config.py` | All settings in one place: bus 3, chip addresses, shunt value, mode, battery size and voltages, timing, power levels (10 / 16.5 / 23 / 29.5 / 36 W), and the throttle start steps. Every setting can be overridden with an environment variable `PMS_<NAME>`, for example `PMS_MODE=manage`. |
| `throttle.py` | Sets the CPU and NPU clock caps through the kernel's `cpufreq` and `devfreq` files. Each step lowers the minimum clock as well as the maximum. Without that, `rock5t-max-clocks.service`, which locks clocks by raising the minimum, would block the cap. It saves the original clock limits and puts them back on exit, including after a crash and restart. It leaves the memory and GPU clocks alone. |
| `battery.py` | Battery state of charge, counted from the energy measured on the battery side. It is saved to `/var/lib/pms/battery.json` so a reboot doesn't reset it to 100%, and it resets to full when the pack reaches `PMS_V_FULL`. |
| `calibrate.py` | Fills in the throttle table. It holds each of the 12 throttle steps for 20 s while an LLM load runs, records the mean and peak watts, and prints the `LEVEL_START_STEP` values to paste into `config.py`. It needs the board wired. |
| `dashboard.py` | Live web page on port 8080, showing battery, ROCK watts, efficiency, level, AI state, clock caps and temperature. It only reads the log. `--demo` shows simulated data on any computer. |
| `dashboard.html` | The page that `dashboard.py` serves. |
| `system/pms-power.service` | systemd unit that starts the power manager at boot, in monitor mode by default. |
| `system/pms-dashboard.service` | systemd unit for the dashboard. |
| `system/pms-tmpfiles.conf` | Creates `/run/pms/ai_state.d/` at every boot, writable by the `radxa` group so the LLM servers can write their state. |
| `system/pms-logrotate` | Rotates the power log daily and keeps 14 days, about 25 MB per day before compression. |

### `docs/`

| File | What it is |
|---|---|
| `FILE_GUIDE.md` | This file. |
| `PMS_BRINGUP.md` | Step-by-step hardware bring-up for the ROCK 5T: wiring, enabling I2C, the first readings, and installing the services. |

### Tests: `tests/firmware/` (repo root)

| File | What it checks |
|---|---|
| `fakes.py` | A fake I2C bus that behaves like two LTC2945 chips, and a fake clock-file tree locked at maximum. |
| `test_drivers.py` | Register decoding, unit scaling, the alert threshold, and missing-chip detection. |
| `test_power_manager.py` | AI-state priority and timeouts, config parsing, clock-cap ordering, restore after a crash, battery persistence, the shutdown delay, level choice, the closed loop, the I2C fail-safe, and logging once per second. |

Run them from the repo root. They need no board and no root:
```
python3 -m unittest discover -s tests -t .
```

## Modes

| Mode | What it does | When to use it |
|---|---|---|
| `monitor` (default) | Reads, logs, tracks the battery and shuts down on low battery. **Never changes the clocks**, so `rock5t-max-clocks.service` keeps them at maximum. | Now, and for every V&V benchmark, so speed results stay comparable with the earlier CPU/GPU/NPU reports while power gets measured. |
| `manage` | Everything in monitor mode, plus it caps the CPU/NPU clocks to keep the ROCK within the power level's budget. That means full power while the LLM works (`prefill` → level 5, `generate`/`retrieve` → level 4) and level 1 (10 W) 2 s after it goes idle. | On battery, after `calibrate.py` has been run and the LLM servers write their AI state. |

In manage mode, an LLM program that doesn't write its state looks idle, so its queries would run throttled. Don't switch to manage until the hooks in `models/rkllm_server.py` and `software/rag/rag.py` are in place.

## Log format

There is one JSON line per second in `/var/log/pms/power.jsonl`:

| Field | Meaning |
|---|---|
| `t` | Unix time |
| `mode` | `monitor` or `manage` |
| `ai` | Busiest AI state |
| `level`, `budget_w`, `step` | Power level, its budget and the throttle step (`null` in monitor mode) |
| `bat_v`, `bat_a`, `bat_w` | Battery side: volts, and mean amps and watts over the second |
| `v12`, `a12`, `w12`, `w12_peak` | 12 V side: volts, mean amps and watts, and peak watts |
| `eff` | `w12 / bat_w`, the converter efficiency |
| `soc` | Battery state of charge, 0–1 |
| `energy_j` | Battery energy since the power manager started. The difference between two lines gives the joules for a query. |
| `samples` | Number of readings averaged into the line (about 10) |

Lines containing `error` (I2C trouble), `event` (low-battery shutdown) or `clock_errors` mark problems.

## Origin

The control logic is the team's NOMAD Rev D reference design, kept as it was: the levels and budgets, the closed loop, the start steps, battery-based level limits and the register maths. The changes made for the ROCK 5T:
- I2C bus 3 on pins 13/15, instead of pins 3/5, which have no I2C on this board.
- Clock caps that work with the max-clocks service.
- State files the LLM servers can write as `radxa`.
- Shutdown only after the voltage stays low for 5 s.
- One log line per second, plus log rotation.
- Battery charge saved across reboots.
- Monitor mode as the default.
- Fail-safe release of the clock caps when I2C is lost.
