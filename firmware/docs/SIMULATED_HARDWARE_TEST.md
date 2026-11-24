# Simulated hardware test (no PMS board needed)

This test runs the real firmware on the ROCK 5T against a **simulated PMS board**. Linux's `i2c-stub` module creates a fake I2C bus, and `firmware/drivers/pms_stub.py` fills it with the register values the two LTC2945 chips would hold. Everything else is the real code that will run on the real board, unchanged.

Use it to check the software before the board is wired, or after changing the code. For the real board, follow [PMS_BRINGUP.md](PMS_BRINGUP.md).

## What is simulated and what is real

| Part of the system | In this test | On the real board |
|---|---|---|
| I2C wires (J3 → pins 13/15) and pull-ups | **Simulated:** the kernel's `i2c-stub` bus, a software-only bus | Bus 3, wired to J3 |
| IC1 LTC2945, battery side (0x6F) | **Simulated:** fake chip at 0x6F | IC1 measuring the 48 V input |
| IC2 LTC2945, 12 V side (0x6C) | **Simulated:** fake chip at 0x6C | IC2 measuring the ROCK's 12 V supply |
| The chips' measurements | **Simulated:** `pms_stub.py` writes register values for chosen volts and amps, encoded exactly as the chip stores them | The chips' own ADCs |
| 48 V → 12 V converter loss | **Simulated:** battery-side power = 12 V power ÷ 0.93 | The real converter |
| An LLM run changing the ROCK's power | **Simulated:** `--profile llm` repeats a 30 s cycle: 10 s idle at about 7 W, 3 s reading the prompt at 16 W, 17 s writing the answer at about 12.5 W | The ROCK's real draw |
| Linux I2C driver and `/dev/i2c-N` | Real | Real |
| `smbus2` library | Real | Real |
| `ltc2945.py`, `pms_board.py` (driver, unit conversion) | Real | Real |
| `ltc2945_test.py` (bring-up test) | Real | Real |
| `power_manager.py` (reading, averaging, energy count, log) | Real, in monitor mode | Real |
| `dashboard.py` | Real | Real |

**Not tested here:** wiring, pull-ups, the 3.3 V levels, noise, the chips' real accuracy and timing, low-battery shutdown, and clock control (manage mode). The unit tests cover the shutdown and clock logic; the rest needs the real board. See [POSSIBLE_SHORTCOMINGS.md](POSSIBLE_SHORTCOMINGS.md).

## Before you start

- Run all commands from the repo root: `cd ~/is2-local-ai/is2-local-ai`.
- You need `python3-smbus2` (`sudo apt install -y python3-smbus2`) and to be in the `i2c` group.
- You need **three terminals open at the same time**. In VS Code, the **+** in the terminal panel opens another. A program that keeps running holds its terminal, and anything typed there is ignored until it stops. So each running program needs its own terminal.

## Part 1: load the fake board and run the bring-up test (Terminal 1)

```
sudo modprobe i2c-stub chip_addr=0x6c,0x6f
```
```
N=$(python3 -c "from firmware.drivers.pms_stub import find_stub_bus; print(find_stub_bus())"); echo "fake bus = $N"
```
```
python3 firmware/drivers/pms_stub.py
```
```
/usr/sbin/i2cdetect -y $N
```
```
python3 firmware/drivers/ltc2945_test.py $N
```

**Expected:**
- `fake bus = 12`. The number may differ; `None` means the `modprobe` failed.
- `i2cdetect` shows `6c` and `6f` in row `60`.
- The bring-up test prints `OK` for both chips, then the same line every second:
  ```
  IC1 battery (48 V):  48.10 V  0.210 A  10.10 W | IC2 12 V output:  12.03 V  0.780 A   9.38 W  eff 92.9 %
  ```
  The values don't change because the fake reading is fixed. Stop the test with **Ctrl+C**.

## Part 2: the power manager with a changing load

**Terminal 1: start the simulated LLM load and leave it running:**
```
python3 firmware/drivers/pms_stub.py --profile llm
```
Expect a line that updates in place every second, for example `IC2 12.75 W  IC1 13.70 W`.

**Terminal 2: start the power manager and leave it running.** It uses monitor mode (clocks untouched), logs to your home folder (no sudo), and has shutdown disabled for the test:
```
cd ~/is2-local-ai/is2-local-ai
```
```
N=$(python3 -c "from firmware.drivers.pms_stub import find_stub_bus; print(find_stub_bus())")
```
```
PMS_I2C_BUS=$N PMS_LOG_PATH=$HOME/pms_test/power.jsonl PMS_BATTERY_FILE=$HOME/pms_test/battery.json PMS_SHUTDOWN_ENABLED=0 python3 -m firmware.power_manager.power_manager
```
Expect one line, `PMS power manager: mode=monitor bus=12 ...`, then nothing more. It writes to the log instead of the screen.

**Terminal 3: watch the log:**
```
tail -f ~/pms_test/power.jsonl
```

**Expected:** a new line every second, for example:
```
{"t": ..., "mode": "monitor", "ai": "idle", "level": null, "budget_w": null, "step": null, "bat_v": 48.1, "bat_a": 0.2825, "bat_w": 13.588, "v12": 12.025, "a12": 1.0525, "w12": 12.656, "w12_peak": 12.656, "eff": 0.931, "soc": 0.9975, "energy_j": 4465.1, "samples": 10}
```

| Field | What to see |
|---|---|
| `w12` | Over 30 s it cycles about 12.5 → 7 → 16 → 12.5 (answer, idle, prompt, answer) |
| `bat_w` | About 7% above `w12` |
| `eff` | 0.93 ± 0.01 |
| `energy_j` | Rises every second, by about `bat_w` |
| `samples` | About 10 (ten 100 ms readings averaged per line) |
| `mode`, `level`, `step` | `"monitor"`, `null`, `null`: clocks not managed |
| Lines with `"error"` | None |

Values in between, such as 9.4 or 13.5, are normal. They appear when the load changes partway through a second, because each line is an average.

Reference run on 2026-11-24, `w12` over 58 s:
```
12.7 12.7 12.2 12.9 12.1 12.9 12.1 12.8 12.3 12.6 12.4 12.6 9.4 7.1 6.8 6.8 7.0 7.3 7.3 7.1 6.8 8.4 16.0 16.0 15.4 12.7 12.3 12.6 12.5 ... 7.2 7.2 7.0 6.8 6.8 7.0 7.2 7.2 7.0 13.5 16.0 16.0 12.4 ...
```
`eff` was 0.927–0.937, with 0 errors.

**Optional, Terminal 4: the dashboard** on the simulated data:
```
PMS_LOG_PATH=$HOME/pms_test/power.jsonl python3 -m firmware.power_manager.dashboard
```
Open `http://<rock-ip>:8080`; `hostname -I` shows the IP. The power chart should show the repeating pattern, and the page should say "Monitor mode".

## Troubleshooting

| What you see | Cause | Fix |
|---|---|---|
| `tail -f` shows the same few lines and nothing new | `tail` prints the last lines of the file, then waits. If the power manager (Terminal 2) isn't running, nothing new arrives. | Check the timestamps (`t`) are current; restart Terminal 2 |
| `w12` never changes | The simulated load (Terminal 1) has stopped, and the fake chips keep their last values | Restart `pms_stub.py --profile llm` in Terminal 1 |
| A command typed into a terminal does nothing | That terminal is busy running a program | Use another terminal (the **+** in VS Code) |
| `No fake bus found` | `i2c-stub` isn't loaded, for example after a reboot | `sudo modprobe i2c-stub chip_addr=0x6c,0x6f` |
| `smbus2 is missing` | Library not installed | `sudo apt install -y python3-smbus2` |

## Clean up

Press Ctrl+C in every terminal, then:
```
sudo modprobe -r i2c-stub
```
```
rm -rf ~/pms_test
```
`ls /dev/i2c-3` should still list the real bus, ready for the board.

## Also run the unit tests

They need no fake bus and no sudo, and they cover the logic this test can't, such as shutdown, clock control and the I2C fail-safe:
```
python3 -m unittest discover -s tests -t .
```
Expect `Ran 30 tests ... OK`.
