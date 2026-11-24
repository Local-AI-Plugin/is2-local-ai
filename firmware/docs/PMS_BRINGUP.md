# PMS board bring-up on the ROCK 5T (Rev D)

The power board turns 48 V from the battery into 12 V for the ROCK 5T. Two LTC2945 chips on it measure volts, amps and watts, one on each side. The board has no processor: the ROCK reads the chips over I2C. Do the steps in order and stop at the first one that fails.

This is the team's Rev D bring-up guide, corrected for the ROCK 5T. **The I2C pins are 13 and 15 and the bus is 3.** The original guide's pins 3 and 5 have no I2C function on this board.

## What you need
- The assembled power board, with IC1, IC2, IC3, C1 and C7 soldered on
- A ROCK 5T with this repo checked out on the `firmware` branch
- A 48 V supply: a battery or a bench supply (18–75 V works)
- A multimeter, 5 female-to-female jumper wires, and a wire from J2 to the ROCK's 12 V DC input

## Step 1: check for shorts (no power)
Set the multimeter to continuity.
- **J1:** `+48V` to `GND` must **not** beep.
- **J2:** `+12V` to `GND` must **not** beep.

If either beeps, stop and look for a solder bridge.

Then check the hand-soldered parts:
- **IC1, IC2:** the pin-1 dot is at the top-left and no legs are bridged.
- **C1, C7:** the stripe (−) is on the **top** pad.
- **IC3:** pin 1 is on the square pad.

## Step 2: power the board alone (ROCK not connected)
1. Connect 48 V to **J1**, matching the `+48V` and `GND` labels on the board.
2. The green **LED1** should light.
3. Measure **J2**. It should read about 12 V.

If the LED doesn't light or J2 doesn't read 12 V, turn the power off, then check F1, IC3's solder joints and the J1 polarity.

## Step 3: wire J3 to the ROCK 5T header
Turn the power off first.

| Power board J3 | ROCK 5T 40-pin header |
|---|---|
| J3.1 `+3V3` | **pin 1** (3.3 V) |
| J3.2 `SDA` | **pin 15** (I2C3_SDA_M1) |
| J3.3 `SCL` | **pin 13** (I2C3_SCL_M1) |
| J3.4 `ALERT` | **pin 7** (GPIO3_C3; not read by the software yet) |
| J3.5 `GND` | **pin 9** |

- The header logic is **3.3 V, with a maximum of 3.63 V**. Never put 5 V on SDA or SCL.
- SDA and SCL need pull-up resistors to 3.3 V, 2.2–4.7 kΩ, on one board only. With the board powered and nothing talking, both should measure about 3.3 V to GND.
- Keep the J3 wires short and away from the buck converter.

Then connect **J2** (`+12V` / `GND`) to the ROCK's 12 V DC input. Check the polarity with the multimeter before plugging in.

## Step 4: turn on I2C on the ROCK (done once; already done on our board)
Check that `/dev/i2c-3` exists:
```
ls /dev/i2c-3
```
If it's missing, enable the overlay and reboot:
```
sudo mv /boot/dtbo/rk3588-i2c3-m1.dtbo.disabled /boot/dtbo/rk3588-i2c3-m1.dtbo
```
```
sudo u-boot-update
```
```
sudo reboot
```
`sudo rsetup` → Overlays → "Enable I2C3-M1" does the same thing.

## Step 5: find the two chips
Install the Python I2C library. On Debian 12, `pip3 install` system-wide is blocked, so use apt:
```
sudo apt install -y python3-smbus2
```
Scan bus 3. `i2cdetect` is in `/usr/sbin`, which isn't on a normal user's PATH:
```
/usr/sbin/i2cdetect -y 3
```

| You see | Meaning |
|---|---|
| `6c` and `6f` | Both chips answer. Go to step 6. |
| Only one of them | The missing chip has a bad solder joint (`6f` is IC1, `6c` is IC2). |
| All `--` | Board not powered, J3 wired wrong (SDA/SCL swapped?), no common GND, or no pull-ups. |

In the grid, the row label is the first hex digit and the column is the second, so row `60`, column `c` is address 0x6C. `--` means nothing answered at that address.

## Step 6: run the test script
From the repo root (no sudo needed; your user is in the `i2c` group):
```
python3 firmware/drivers/ltc2945_test.py
```
It prints one line per second:
```
IC1 battery (48 V):  48.10 V  0.210 A  10.10 W | IC2 12 V output:  12.02 V  0.780 A   9.37 W  eff 92.8 %
```
**Pass:**
- IC1 volts match J1 within about 1 V.
- IC2 volts read about 12 V.
- IC2 watts are a little lower than IC1 watts, by roughly 7% converter loss.

## Step 7: run the power manager by hand
From the repo root, in monitor mode, which reads and logs and never changes the clocks:
```
sudo PMS_V_SHUTDOWN=15 python3 -m firmware.power_manager.power_manager
```
`PMS_V_SHUTDOWN=15` is for a bench supply below 42 V. Without it the ROCK shuts itself down after 5 s. Leave it out on the real battery.

It logs one line per second to `/var/log/pms/power.jsonl`. Watch it with `tail -f /var/log/pms/power.jsonl`, and stop it with Ctrl+C.

Optional live page: in a second terminal run `sudo python3 -m firmware.power_manager.dashboard`, then open `http://<rock-ip>:8080`. To find the IP, run `hostname -I`.

## Step 8: install as services (after step 7 works)
```
sudo mkdir -p /opt/pms
```
```
sudo cp -r firmware /opt/pms/
```
```
sudo cp firmware/power_manager/system/pms-power.service firmware/power_manager/system/pms-dashboard.service /etc/systemd/system/
```
```
sudo cp firmware/power_manager/system/pms-tmpfiles.conf /etc/tmpfiles.d/pms.conf
```
```
sudo cp firmware/power_manager/system/pms-logrotate /etc/logrotate.d/pms
```
```
sudo systemd-tmpfiles --create /etc/tmpfiles.d/pms.conf
```
Edit `/etc/systemd/system/pms-power.service` and set `PMS_PACK_WH` and `PMS_V_SHUTDOWN` for your battery. Use the same values in `pms-dashboard.service`. Then:
```
sudo systemctl daemon-reload
```
```
sudo systemctl enable --now pms-power pms-dashboard
```
After changing the code, copy `firmware` to `/opt/pms/` again and run `sudo systemctl restart pms-power pms-dashboard`.

## Step 9 (later): manage mode
Only after:
1. the LLM servers write their AI state (see FILE_GUIDE.md, "Modes"), and
2. the throttle table is calibrated:
   ```
   sudo systemctl stop pms-power
   sudo python3 -m firmware.power_manager.calibrate --load-cmd "<command that runs an LLM query>"
   ```
   Paste the printed `LEVEL_START_STEP` into `firmware/power_manager/config.py`.

Then set `Environment=PMS_MODE=manage` in `pms-power.service` and restart it. For V&V benchmarks, switch back to `monitor` so the clocks stay at maximum.

## What to send back to the team
1. Step 2: the J2 voltage, and whether LED1 lit
2. Step 5: a screenshot of `i2cdetect -y 3`
3. Step 6: a few lines of `ltc2945_test.py` output, plus multimeter readings at J1 and J2
