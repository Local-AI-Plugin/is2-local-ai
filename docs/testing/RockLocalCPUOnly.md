# Rock 5T Local CPU-Only Results: qwen3.5:4b

Results of the dev-board V&V run defined in [model-vnv-dev-board.md](model-vnv-dev-board.md). The method follows [model-evaluation.md](model-evaluation.md), and laptop figures come from [model-evaluation-results.md](model-evaluation-results.md).

**Date:** 2026-11-11
**Board:** Radxa ROCK 5T (RK3588, 4× A76 at 2.3 GHz + 4× A55 at 1.8 GHz, 12 GB RAM), heatsink with fan
**Model:** `qwen3.5:4b` (Q4_K_M, ID `d8b0f5e9760c`), thinking off
**Runtime:** Ollama 0.40.3, CPU only (no NPU, no GPU)
**Test:** first 20 IFEval prompts (the same prompts as the laptop battery screen), then a repeat of the first 5

## Summary

- **The model runs well on the board.** It scored the same IFEval accuracy as the laptop (17 of 20 prompts) at the same speed (4.34 vs 4.36 tokens/s) and fits easily in RAM (6.9 GB peak of 12 GB).
- **Heat is the main limit.** With the fan at 100%, the SoC averaged 84 °C and reached 85.9 °C, past its 85 °C throttle point. In a run started on an already hot board, the big cores averaged 2.04 GHz instead of 2.30 GHz and speed fell by about a quarter, to 3.24 tokens/s.
- **The test setup is sound.** Same Ollama version and weights as the laptop, no errors or cut-off answers, a complete resource log, and identical answers when the first 5 prompts were rerun.

## Results

### Board compared with the laptop (first 20 IFEval prompts, thinking off)

| Measurement | Laptop (i7-1355U, battery) | ROCK 5T board |
|---|---:|---:|
| IFEval prompt-level strict (%) | 85 | 85 |
| IFEval instruction-level strict (%) | 90.0 | 86.7 |
| Generation speed (tokens/s) | 4.36 | 4.34 |
| Prompt processing speed (tokens/s) | — | 14.1 |
| Average seconds per answer | 63.2 | 63.8 |
| Average output tokens per answer | 253 | 253 |
| Model load time (s) | 15.7 | 35.3 |
| Peak model memory (GB) | 6.61 (container) | 6.89 (Ollama processes) |
| Model memory increase (GB) | 6.47 | 6.83 |
| Peak system RAM (GB) | 32.2 of 32 | 10.4 of 12 |
| SoC temperature, start → peak (°C) | — | 55 → 85.9 |
| Hottest CPU core peak (°C) | — | 87.7 |
| Energy per answer | 0.37 Wh (whole laptop) | not measured |
| Total run time for 20 answers | — | 21.3 min |

Memory is measured differently on each machine (`docker stats` on the laptop, process RSS on the board), so compare the two memory rows with care.

### Failed prompts (board)

| Prompt | Instructions failed |
|---|---|
| 6: critique in all capital letters, in 2 sections | All capitals, multiple sections |
| 7: resume with capitalised key words | Capital-word frequency (passed the other 2 instructions) |
| 19: tweet with no capital letters | Letter frequency (passed the no-capitals instruction) |

Both machines failed 3 of 20 prompts, but the board passed fewer individual instructions (86.7% vs 90.0%). The weights and settings are the same, so the answers probably differ slightly because floating-point maths on an ARM CPU differs from an x86 CPU. With 20 prompts, a gap this size is within noise.

### Thermal behaviour

| | Main run (started cool) | Repeat run (started hot) |
|---|---:|---:|
| Prompts | 20 | 5 |
| SoC temperature average / peak (°C) | 84.0 / 85.9 | 83.7 / 85.0 |
| Time at or above 85 °C | 41% | 5% |
| Big-core clock average (MHz, max 2304) | not logged* | 2042 |
| Time with big cores below max clock | not logged* | 94% |
| Generation speed (tokens/s) | 4.34 | 3.24 |

\*The big-core clock column was added to the monitor after the main run.

- The SoC went from 55 °C to over 80 °C within 30 seconds of the model starting, then held at about 84–85 °C, at the passive throttle point, for the rest of the run.
- Speed held at about 4.0–4.8 tokens/s for most of the main run, but the last two answers dropped to 2.3 and 3.1 tokens/s.
- The repeat run, started straight after the main run, was about 25% slower and was throttled for almost its whole length.
- **Sustained use on this cooler is thermally limited.** For an always-on device, the cooling needs to keep the SoC under about 80 °C.

## V&V outcome

### Verification

| ID | Check | Result | Evidence |
|---|---|---|---|
| V-01 | Ollama version matches the laptop | **Pass** | 0.40.3 |
| V-02 | Same weights as the laptop | **Pass** | ID `d8b0f5e9760c` |
| V-03 | Same harness and settings | **Pass** | lm_eval 0.4.13, greedy, seed 42, 16k context, thinking off, limit 20 |
| V-04 | Completed without errors | **Pass** | `Results saved to ...`; no failed requests or thinking output |
| V-05 | No truncated answers | **Pass** | 0 of 20 |
| V-06 | Resource log complete | **Pass** | 1,294 rows, largest gap 1.03 s, no `unreachable` entries |
| V-07 | Model was actually loaded | **Pass** | Ollama memory 0.06 → 6.89 GB |
| V-08 | Local only | **Pass** | Loopback server only; Hugging Face offline mode on; dataset read from local cache |
| V-09 | Repeatable | **Pass** | First 5 answers identical, word for word, between the two runs |

### Validation

The targets are proposals, because the project has no requirements document yet.

| ID | Measure | Proposed target | Result | Verdict |
|---|---|---|---|---|
| VAL-01 | IFEval prompt-level strict | ≥ 70% | 85% | **Pass** |
| VAL-02 | Generation speed | ≥ 3 tokens/s | 4.34 (cool), 3.24 (hot) | **Pass**, with little margin when hot |
| VAL-03 | Seconds per answer | Report | 63.8 s (laptop 63.2 s) | Recorded |
| VAL-04 | Peak model memory | ≤ 8 GB | 6.89 GB | **Pass** |
| VAL-05 | Thermal | SoC < 85 °C, no sustained throttling | 85.9 °C peak; big cores throttled 94% of the hot run | **Fail** |
| VAL-06 | Offline operation | No network needed | Ran offline | **Pass** |

## What was changed to run this

- **Ollama 0.40.3** was installed under `~/.local/ollama-0.40.3` and runs as user `radxa` on port **11435**. `setup_board.sh` needs sudo, which wasn't available. A separate root-owned Ollama 0.40.16 was already running on port 11434 before this work. It was left alone and not used.
- **The Python venv** (`.venv`) was set up without the `python3-venv` package, which also needs sudo. pip was installed into the venv with `get-pip.py`.
- **`monitor_resources.py`** now logs SoC temperature, the hottest CPU core, the lowest clock of any cluster and the lowest big-core clock on Linux. On Windows these columns stay blank.
- **`analyze_run.py`** reports start and peak temperature and the big-core clock, and no longer says "laptop on AC" when the board simply has no battery.
- **No energy data.** The board has no battery, and its USB-C power-delivery sensor reads 0 V / 0 A.

## Next steps

1. **Improve the cooling, then repeat the 20-prompt run** to see the speed without throttling: a larger heatsink, better thermal paste or pad, and more airflow. Log the big-core clock for the whole run.
2. **Add a USB-C power meter** between the supply and the board to get energy per answer and per token.
3. **Run the other two candidates** (`qwen3:4b-instruct-2507-q4_K_M`, `qwen3:8b`) on the board, then the 100-prompt screen. The 8B (about 11 GB peak on the laptop) may not fit in 12 GB alongside the desktop.
4. **Try the RK3588 NPU** (6 TOPS) through Rockchip's RKLLM runtime. It could be faster and cooler than the CPU.
5. **Write the requirements** (speed, memory and thermal targets) so the V&V targets above can be confirmed.

## Raw data

On the board, in `benchmark_results/` (gitignored):

| Run | Folder | Resource log |
|---|---|---|
| 20 prompts | `20261111T144259968591Z` | `resources_20261111T144258Z.csv` |
| 5-prompt repeat | `20261111T150453763622Z` | `resources_20261111T150514Z.csv` |

Run logs: `board_run_20.log`, `board_run_5_repeat.log`. Each run folder holds `manifest.json`, `analysis.json` and, per model, `results.json` and `requests.jsonl`.
