# Possible shortcomings to consider: ROCK 5T ↔ PMS integration

These are the things that could go wrong, or limit what the system can do, when the PMS board (Rev D, two LTC2945 monitors) is connected to the ROCK 5T and run with the code in `firmware/`. Each item says what the risk is, why it matters, and what to do about it.

Each item has a status:
- **Handled:** the code or docs already deal with it.
- **Check on hardware:** confirm it when the board is wired.
- **Open:** not solved yet; a decision or more work is needed.

See [FILE_GUIDE.md](FILE_GUIDE.md) for what each file does and [PMS_BRINGUP.md](PMS_BRINGUP.md) for the wiring steps.

## Summary

| # | Shortcoming | Status |
|---|---|---|
| 1 | Original guide wires I2C to pins 3/5, which have no I2C on the ROCK 5T | Handled |
| 2 | 3.3 V logic limit on the ROCK header | Check on hardware |
| 3 | Pull-up resistors on SDA/SCL | Check on hardware |
| 4 | LTC2945 has split SDA pins (SDAI/SDAO) | Check on hardware |
| 5 | Chip addresses set by the ADR pin straps | Check on hardware |
| 6 | Ground path between the boards | Check on hardware |
| 7 | I2C noise from the buck converter | Check on hardware |
| 8 | I2C bus stuck after a glitch | Open |
| 9 | Board unpowered while the ROCK drives the bus | Check on hardware |
| 10 | ALERT line is wired but not used | Open |
| 11 | Chip settings rely on power-on defaults | Open |
| 12 | Low current reads coarsely on the battery side | Check on hardware |
| 13 | Chips refresh slower than the loop; short spikes are missed | Open |
| 14 | `V_FULL` assumes an input diode drop | Check on hardware |
| 15 | Clock caps conflict with `rock5t-max-clocks.service` | Handled |
| 16 | LLM software doesn't report its state yet | Open |
| 17 | Throttle table and budgets are placeholders | Open |
| 18 | Memory and GPU clocks aren't controlled | Open |
| 19 | The power limit is a soft limit, not protection | Handled (by design) |
| 20 | Energy count uses wall-clock time | Handled |
| 21 | Battery charge estimate drifts and can't see charging | Open |
| 22 | Shutdown margin and timing on LiFePO4 | Check on hardware |
| 23 | A halted ROCK still drains the battery | Open |
| 24 | One failed chip stops all readings | Open |
| 25 | Two programs controlling the clocks at once | Handled (in docs) |
| 26 | V&V benchmarks need fixed clocks | Handled |
| 27 | Dashboard is open to the whole network | Open |
| 28 | Code in `/opt/pms` can drift from the repo | Handled (in docs) |

---

## A. Wiring and electrical

### 1. Original guide wires I2C to pins 3/5 (Handled)
The Rev D guide was written for the Raspberry Pi layout. On the ROCK 5T, pins 3 and 5 have no I2C function, so the bus would never work. The correct pins are **SDA on pin 15 and SCL on pin 13** (I2C3-M1, Linux bus 3). `PMS_BRINGUP.md`, `pms_board.py` and the service files all use these.

### 2. 3.3 V logic limit on the ROCK header (Check on hardware)
The ROCK's GPIO pins are 3.3 V, with an absolute maximum of 3.63 V. If the PMS pulls SDA/SCL up to 5 V, for example from the LTC2945's internal 5 V supply or a 5 V rail, the RK3588 can be damaged.
- **Check:** with the board powered and nothing transmitting, SDA and SCL must read about 3.3 V to GND, never 5 V.

### 3. Pull-up resistors on SDA/SCL (Check on hardware)
I2C needs pull-up resistors, typically 2.2–4.7 kΩ to 3.3 V. The ROCK's internal pull-ups are too weak to rely on. With no pull-ups the bus reads nothing. With pull-ups on both boards in parallel, the combined value can get too low.
- **Check:** in the schematic, confirm one set of pull-ups to J3's +3V3.
- **Check:** `i2cdetect -y 3` shows 6c and 6f.

### 4. LTC2945 has split SDA pins (Check on hardware)
The LTC2945 has separate **SDAI** (data in) and **SDAO** (data out) pins, intended for opto-isolated buses. On a normal bus they must be tied together on the board. If they aren't, the chip receives commands but can never answer, so i2cdetect shows nothing.
- **Check:** SDAI and SDAO are connected to each other and to J3.2, for both IC1 and IC2.

### 5. Chip addresses set by the ADR pin straps (Check on hardware)
The addresses 0x6F (IC1) and 0x6C (IC2) come from how each chip's ADR0/ADR1 pins are tied: high, low or left open. A wrong strap or a bad joint on an ADR pin moves the chip to another address in the 0x67–0x6F range. The code would then report it as missing.
- **Check:** if `i2cdetect` shows a different address, compare the straps with the datasheet's address table. Either fix the board or set `PMS_ADDR_BATTERY` / `PMS_ADDR_OUTPUT`.

### 6. Ground path between the boards (Check on hardware)
The ROCK's full current, up to about 3 A, returns to the PMS through the J2 ground wire. If that connection is loose or thin, part of the current returns through the J3 GND jumper instead. That can heat the jumper and shift the I2C signal levels.
- **Mitigation:** use a solid J2 ground wire rated for at least 3 A. Keep J3 GND as the signal reference only.

### 7. I2C noise from the buck converter (Check on hardware)
The 48 V → 12 V converter switches fast, and the I2C lines carry 3.3 V signals over jumper wires. Noise can corrupt or abort transfers, which shows up as `OSError` read failures.
- **Mitigation:** keep the J3 wires short, twisted with GND, and routed away from the converter and its inductor.
- **If errors appear:** `"error"` lines in the log mean failed reads. Lower the bus speed with a device-tree change (default is 100 kHz).

### 8. I2C bus stuck after a glitch (Open)
If a transfer is cut off half-way, for example by noise or a reset during a read, a chip can keep holding SDA low. Every later read then fails until the chip is power-cycled. The software only notices that reads fail: it releases the clock caps after 2 s and logs the error, but it can't free the bus.
- **Options:** power-cycle the PMS, or add bus recovery (clocking SCL 9 times). The Linux rk3x I2C driver may not do this automatically.

### 9. Board unpowered while the ROCK drives the bus (Check on hardware)
On the bench, the ROCK may run from a different supply while the PMS is off. J3's +3V3 from the ROCK then feeds the pull-ups into unpowered LTC2945s. Most I2C parts tolerate this, but it should be confirmed in the datasheet. Otherwise the chips can be back-powered through their I/O pins.
- **Check:** confirm the LTC2945 I/O ratings with VDD at 0 V. Otherwise, don't connect J3 until the PMS is powered.

### 10. ALERT line is wired but not used (Open)
J3.4 ALERT goes to pin 7, and the code programs IC2's power alert. But the software checks the power limit by itself every 100 ms and never reads pin 7. So ALERT adds no speed today. The pin is also open-drain and needs a pull-up if it's ever read.
- Pin 7 can also act as I2C8 or UART7. Don't enable those overlays, or they'll take the pin.
- **Option:** read pin 7 as an interrupt for a faster reaction, if issue 13 or 19 turns out to matter.

## B. Measurement

### 11. Chip settings rely on power-on defaults (Open)
The code never writes the LTC2945 CONTROL register. It assumes the power-on defaults: continuous measuring, with voltage taken from SENSE+ and power multiplied using that voltage. If a chip is reset into another mode, or someone changes CONTROL, the volts and watts would use the wrong source or scale, with no error.
- **Option:** at start-up, write CONTROL explicitly and read it back, once the register bits have been checked against the datasheet.

### 12. Low current reads coarsely on the battery side (Check on hardware)
With a 10 mΩ shunt, one current count is 2.5 mA. On the 48 V side, an idle ROCK draws only about 0.1–0.2 A, which is just 40–80 counts. On top of that comes the chip's offset error, so idle battery current and efficiency can be off by several percent.
- The code only reports efficiency above 1 W on the battery side.
- **Check:** compare idle readings with a multimeter. If accuracy matters, a larger shunt on IC1 would help, but it raises the full-scale limit's loss.

### 13. Chips refresh slower than the loop; short spikes are missed (Open)
The LTC2945 updates its results only a few times per second (the reference code assumes about 7.5 Hz; confirm in the datasheet). The loop reads every 100 ms, so some readings are repeats. A load spike shorter than one conversion can be missed completely, and the power value is a snapshot rather than an average.
- **Effect:** energy and joules per query are approximate (fine at the 1-second scale), and the closed loop reacts to spikes late.
- **Option:** the LTC2945 also keeps min/max power registers, which could be read to catch peaks.

### 14. `V_FULL` assumes an input diode drop (Check on hardware)
`PMS_V_FULL = 57.6 V` assumes IC1 reads about 0.5 V below the pack because of a series diode. The design notes (`hardware/power/01_Input_Protection_Design_Notes.md`) show a TPS48111 controller with back-to-back FETs and list D1 as a TVS, not a series diode.
- **Effect:** if there is no drop, a full 58.4 V pack resets the charge count correctly. But if the real full reading is below 57.6 V, it never resets and the charge estimate drifts (see 21).
- **Check:** read IC1 with a fully charged pack and set `PMS_V_FULL` just below it.

## C. Software on the ROCK

### 15. Clock caps conflict with `rock5t-max-clocks.service` (Handled)
The max-clocks service locks clocks by raising each minimum up to the maximum. Lowering only the maximum would then be ignored. `throttle.py` lowers the minimum too, writes the two in an order the kernel accepts, saves the original limits, and puts them back on exit or after a crash.
- **Remaining risk:** if the max-clocks script is run again by hand while manage mode is active, it overrides the caps until the next level change.

### 16. LLM software doesn't report its state yet (Open)
In manage mode the power manager slows the clocks when it sees `idle`. `rkllm_server.py` and `rag.py` don't write their state yet, so **every query would look idle and run throttled**, adding delay.
- The default monitor mode is safe, because it never touches the clocks.
- **To do before manage mode:**
  - Add `ai_state` hooks to `models/rkllm_server.py`, which can report prefill and generate exactly.
  - Add hooks to `software/rag/rag.py`. Ollama can't report prefill versus generate separately, so it will report one busy state for the whole request.
  - Mount `/run/pms` into the RAG Docker container.

### 17. Throttle table and budgets are placeholders (Open)
`LEVEL_START_STEP` in `config.py` is a guess until `calibrate.py` has been run on the real board. The budgets (10 / 16.5 / 23 / 29.5 / 36 W) come from the board's 36 W limit, not from what the ROCK draws.
- If the ROCK's highest real draw during an LLM run is well under 29.5 W, levels 4 and 5 never limit anything.
- Level 1's 10 W might sit close to or above idle draw, so it saves less than expected.
- **To do:** run `calibrate.py` with a real LLM load, then review whether the budgets match the measured range.

### 18. Memory and GPU clocks aren't controlled (Open)
Only the CPU and NPU are throttled. The memory clock stays locked at 2.4 GHz, because memory speed limits LLM speed. That keeps queries fast but limits how much power idle can save, since memory is a large share of idle power.
- **Option:** lower the memory clock only at level 1 (idle), and restore it the moment a request arrives.

### 19. The power limit is a soft limit, not protection (Handled by design)
The loop reacts within about 100–350 ms: one sample, smoothing, then a step every 0.25 s at most. During that time the ROCK can go over its budget.
- That's acceptable because the budget is an energy-saving target, not a safety limit. Overcurrent and short circuits are handled by the TPS48111 on the board in microseconds.
- Nobody should treat the software budget as protection for the battery or cables.

### 20. Energy count uses wall-clock time (Handled)
`power_manager.py` measures the time between samples with `time.time()`, the wall clock. If the clock jumps, for example when NTP corrects the time after boot or someone sets the date, one sample would get a huge time gap. Hours of battery energy would then be added in one step, wrecking the charge estimate.
- **Fixed:** each gap is clamped to 0–1 s (`MAX_DT_S`). A jump now adds at most one second of energy, and a backwards jump adds none. The test `test_clock_jump_does_not_add_energy` checks this.
- **Remaining effect:** a forward jump can end the 2 s idle hold or the 5 s low-voltage timer early, once. That's harmless.

## D. Battery and shutdown

### 21. Battery charge estimate drifts and can't see charging (Open)
The charge estimate counts energy drawn from the pack.
- **It drifts:** `PMS_PACK_WH` is set by hand, and small measurement errors add up between full charges.
- **It can't see charging:** the LTC2945 measures current in one direction only, so charging current reads as zero. The estimate only corrects itself when IC1 reaches `PMS_V_FULL`.
- **Voltage can't fix it:** LiFePO4 voltage stays almost flat from about 90% down to 20%, so voltage alone says little about charge.
- **Mitigation:** set `PMS_PACK_WH` from the real pack capacity, and charge fully now and then so the count resets. Treat the shown percentage as an estimate.
- **Option:** if the BMS (JBD) can report its own charge level over UART or Bluetooth, use that instead.

### 22. Shutdown margin and timing on LiFePO4 (Check on hardware)
The ROCK shuts down once the pack stays below 42 V for 5 s. The board's own cut-off is near 39.7 V, and the BMS has its own undervoltage trip.
- LiFePO4 voltage drops steeply near empty. The time from 42 V down to the cut-off may be short under LLM load.
- An OS shutdown takes several seconds.
- **Check:** measure how long the pack takes to fall from 42 V to 40 V under a typical load. Make sure that's comfortably longer than 5 s plus the shutdown time, and raise `PMS_V_SHUTDOWN` if not.
- **On the bench:** below 42 V, set `PMS_V_SHUTDOWN=15`, or the ROCK powers itself off 5 s after starting.

### 23. A halted ROCK still drains the battery (Open)
After `shutdown -h now`, the ROCK halts, but the PMS keeps supplying 12 V. The ROCK and the converter keep drawing some power until the BMS or the board's UVLO cuts off. Over a long time that can run the pack all the way down to the BMS trip.
- **Option (hardware):** add a ROCK GPIO to the PMS that switches off the 12 V output, or the TPS48111's enable, after shutdown. This needs a board change.

### 24. One failed chip stops all readings (Open)
`PMSBoard.read()` reads both chips together. If one chip fails, for example a bad joint on IC1, the whole reading fails. The power manager then logs no data at all and, in manage mode, releases the clock caps. The working chip's data is lost too.
- **Option:** read each chip separately and log whichever side works, marking the other side as missing.

## E. Operations

### 25. Two programs controlling the clocks at once (Handled in docs)
Running `calibrate.py`, or a second `power_manager.py` by hand, while the `pms-power` service runs in manage mode means two programs writing the same clock files and fighting each other.
- **Rule:** `sudo systemctl stop pms-power` before calibrating or testing by hand. This is stated in `calibrate.py` and `PMS_BRINGUP.md`.
- In monitor mode the service never writes clocks, so only the duplicate log lines would matter.

### 26. V&V benchmarks need fixed clocks (Handled)
All earlier CPU/GPU/NPU reports ran with clocks locked at maximum. If manage mode throttled during a benchmark, the speed results couldn't be compared with those reports.
- **Rule:** run benchmarks in monitor mode, which is the default. That also adds real watts and joules per token to the reports.

### 27. Dashboard is open to the whole network (Open)
The dashboard listens on all network interfaces on port 8080, with no password. Anyone on the same network can see battery level, power and AI activity. It's read-only, so nothing can be changed through it.
- **Option:** for field use, bind it to `127.0.0.1`, put it behind a firewall rule, or only start it when needed.

### 28. Code in `/opt/pms` can drift from the repo (Handled in docs)
The services run a copy of `firmware/` in `/opt/pms`. Changes in the repo don't take effect until the folder is copied again and the services are restarted. It's easy to test new code by hand while the service still runs the old copy.
- **Rule:** after changing the code, copy it again and run `sudo systemctl restart pms-power pms-dashboard`, as in `PMS_BRINGUP.md`.
