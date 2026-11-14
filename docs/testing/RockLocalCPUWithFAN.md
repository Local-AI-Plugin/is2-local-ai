# Rock 5T Local CPU-Only Results with Fan: qwen3.5:4b

Results of the dev-board V&V run defined in [model-vnv-dev-board.md](model-vnv-dev-board.md), repeated with the fan fitted. The method follows [model-evaluation.md](model-evaluation.md). The no-fan results are in [RockLocalCPUOnly.md](RockLocalCPUOnly.md), and laptop figures come from [model-evaluation-results.md](model-evaluation-results.md).

**Date:** 2026-11-13
**Board:** Radxa ROCK 5T (RK3588, 4× A76 at 2.3 GHz + 4× A55 at 1.8 GHz, 12 GB RAM), heatsink with PWM fan (`pwmfan`)
**Model:** `qwen3.5:4b` (Q4_K_M, ID `d8b0f5e9760c`), thinking off
**Runtime:** Ollama 0.40.3, CPU only (no NPU, no GPU)
**Test:** first 20 IFEval prompts (the same prompts as the laptop battery screen), then a repeat of the first 5. Same commands and settings as the earlier board runs, plus a fan log.

## Summary

- **The fan solves the heat problem.** The SoC peaked at 61 °C, against 85.9 °C in the earlier board run, and never came near the 85 °C throttle point. The big cores stayed at their full 2.30 GHz for 99.8% of the run.
- **Accuracy is unchanged.** 17 of 20 prompts passed (85%), the same three prompts failed, and all 20 answers are word for word the same as in the earlier board run.
- **Speed did not improve.** Generation averaged 4.45 tokens/s, against 4.60 in the earlier run, even though the cores were no longer throttled. Generation speed on this board seems to be set mainly by memory bandwidth, not by clock speed or temperature.
- **The board now passes every V&V check,** including the thermal target it failed before.

## Results

### With fan, compared with the earlier board run and the laptop (first 20 IFEval prompts, thinking off)

| Measurement | Laptop (i7-1355U, battery) | Board, earlier run (2026-11-11) | Board with fan (this run) |
|---|---:|---:|---:|
| IFEval prompt-level strict (%) | 85 | 85 | 85 |
| IFEval instruction-level strict (%) | 90.0 | 86.7 | 86.7 |
| Generation speed (tokens/s) | 4.36 | 4.60 | 4.45 |
| Prompt processing speed (tokens/s) | — | 14.4 | 15.8 |
| Average seconds per answer | 63.2 | 60.1 | 62.6 |
| Average output tokens per answer | 253 | 253 | 253 |
| Model load time (s) | 15.7 | 24.9 | 47.0 |
| Peak model memory (GB) | 6.61 (container) | 6.70 | 6.95 |
| Peak system RAM (GB) | 32.2 of 32 | 10.8 of 12 | 10.3 of 12 |
| SoC temperature start / average / peak (°C) | — | 56.9 / 83.3 / 85.9 | 40.9 / 58.5 / 61.0 |
| Hottest CPU core peak (°C) | — | 88.6 | 63.8 |
| Time at or above 85 °C | — | 16% | 0% |
| Big-core clock average (MHz, max 2304) | — | 1822 | 2301 |
| Time with big cores below max clock | — | 95% | 0.2% |
| Total run time for 20 answers | — | 20.0 min | 20.9 min |

Memory is measured differently on each machine (`docker stats` on the laptop, process RSS on the board), so compare the laptop and board memory rows with care. The longer model load (47 s) is probably because the board had just restarted, so the weights were read from storage rather than from the file cache.

### Failed prompts

The same three prompts failed as in the earlier board run:

| Prompt | Instructions failed |
|---|---|
| 6: critique in all capital letters, in 2 sections | All capitals, multiple sections |
| 7: resume with capitalised key words | Capital-word frequency (passed the other 2 instructions) |
| 19: tweet with no capital letters | Letter frequency (passed the no-capitals instruction) |

### Thermal and fan behaviour

| | Main run (20 prompts) | Repeat run (5 prompts) |
|---|---:|---:|
| SoC temperature start / average / peak (°C) | 40.9 / 58.5 / 61.0 | 51.8 / 59.3 / 61.9 |
| Hottest CPU core peak (°C) | 63.8 | 63.8 |
| Big-core clock average (MHz, max 2304) | 2301 | 2294 |
| Time with big cores below max clock | 0.2% (2 samples) | 0.6% (2 samples) |
| Fan at full speed (PWM 255) | 53% of the time | 77% of the time |
| Fan at a lower step (PWM 64–192) | 24% | 5% |
| Fan off (PWM 0) | 23% | 18% |
| Generation speed (tokens/s) | 4.45 | 4.98 |

- The fan follows the kernel's thermal steps, so it cycles between off and full speed as the SoC warms and cools. It ran at full speed for about half of the main run.
- The SoC settled at about 58–61 °C, more than 20 °C below the throttle point, so there is room for warmer surroundings or a closed case.
- The two brief clock dips (2 samples per run) are normal governor changes, not thermal throttling: the SoC was below 62 °C throughout.

### Speed

- Per-answer speed varied from 2.75 to 5.38 tokens/s across the 20 answers. In the earlier run it stayed between 4.06 and 5.15, while the board was throttling.
- The cores ran at full clock throughout, so the variation was not caused by heat. The most likely cause is other activity on the board (the KDE desktop and VS Code were open during both runs). The test does not log which processes were active, so this is not confirmed.
- Removing the throttling did not raise the average speed, which confirms that generation on this CPU is limited by memory bandwidth more than by clock speed. A faster memory path, a smaller model or the NPU would do more for speed than extra cooling.

## V&V outcome

### Verification

| ID | Check | Result | Evidence |
|---|---|---|---|
| V-01 | Ollama version matches the laptop | **Pass** | 0.40.3 (`/api/version` and `manifest.json`) |
| V-02 | Same weights as the laptop | **Pass** | Digest `d8b0f5e9760c…` in `manifest.json` |
| V-03 | Same harness and settings | **Pass** | lm_eval 0.4.13, temperature 0, seed 42, 16k context, thinking off, limit 20 |
| V-04 | Completed without errors | **Pass** | `Results saved to ...` printed for both runs; no failed requests, warnings or thinking output |
| V-05 | No truncated answers | **Pass** | 0 of 20 (and 0 of 5 in the repeat) |
| V-06 | Resource log complete | **Pass** | 1,278 rows, largest gap 2.0 s, no `unreachable` entries |
| V-07 | Model was actually loaded | **Pass** | Ollama memory 0.07 → 6.95 GB |
| V-08 | Local only | **Pass** | Server at `127.0.0.1:11435`; `HF_HUB_OFFLINE=1` and `HF_DATASETS_OFFLINE=1`; dataset read from local cache |
| V-09 | Repeatable | **Pass** | First 5 answers identical, word for word, in the repeat run; all 20 identical to the 2026-11-11 board run |

### Validation

The targets are proposals, because the project has no requirements document yet.

| ID | Measure | Proposed target | Earlier run | With fan | Verdict |
|---|---|---|---|---|---|
| VAL-01 | IFEval prompt-level strict | ≥ 70% | 85% | 85% | **Pass** |
| VAL-02 | Generation speed | ≥ 3 tokens/s | 4.60 | 4.45 (4.98 in the repeat) | **Pass** |
| VAL-03 | Seconds per answer | Report | 60.1 s | 62.6 s | Recorded |
| VAL-04 | Peak model memory | ≤ 8 GB | 6.70 GB | 6.95 GB | **Pass** |
| VAL-05 | Thermal | SoC < 85 °C, no sustained throttling | 85.9 °C; throttled 95% of the run | 61.0 °C; full clock 99.8% of the run | **Pass** (was Fail) |
| VAL-06 | Offline operation | No network needed | Ran offline | Ran offline | **Pass** |

## Setup notes

- **Same procedure as the earlier board runs.** The commands are in [model-vnv-dev-board.md](model-vnv-dev-board.md#procedure), with the same model, settings and prompts.
- **Ollama 0.40.3** was restarted after the board rebooted, with the same settings as before: user `radxa`, port **11435**, models in `~/.ollama/models`.
- **Fan log.** A separate logger recorded the fan's PWM level (`/sys/class/hwmon/hwmon8/pwm1`, 0–255) and thermal cooling state (0–4) every 2 seconds.
- **No energy data.** The board has no battery, and its USB-C power-delivery sensor reads 0 V / 0 A.
- The KDE desktop and VS Code were open during the run (3.3 GB system RAM in use at the start).

## Next steps

1. **Add a USB-C power meter** between the supply and the board to get energy per answer and per token, including what the fan costs.
2. **Run the other two candidates** (`qwen3:4b-instruct-2507-q4_K_M`, `qwen3:8b`) on the board with the fan, then the 100-prompt screen. The 8B (about 11 GB peak on the laptop) may not fit in 12 GB alongside the desktop.
3. **Run once with the desktop closed** (or log CPU use per process) to find out why per-answer speed varied.
4. **Try the RK3588 NPU** (6 TOPS) through Rockchip's RKLLM runtime. Speed is limited by memory, not heat, so a different runtime is the main way left to speed up generation.
5. **Write the requirements** (speed, memory and thermal targets) so the V&V targets above can be confirmed.

## Raw data

On the board, in `benchmark_results/` (gitignored):

| Run | Folder | Resource log | Console log |
|---|---|---|---|
| 20 prompts | `20261114T014816631879Z` | `resources_20261114T014812Z.csv` | `board_fan_20.log` |
| 5-prompt repeat | `20261114T020933921637Z` | `resources_20261114T020931Z.csv` | `board_fan_5_repeat.log` |
| Fan log (both runs) | — | `fan_20261114T014811Z.csv` | — |

Folder names use UTC, so they are dated 2026-11-14 although the runs were on the evening of 2026-11-13 local time. Each run folder holds `manifest.json`, `analysis.json` and, per model, `results.json` and `requests.jsonl`.
