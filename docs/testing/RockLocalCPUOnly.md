# Rock 5T Local CPU-Only Results: qwen3.5:4b

Results of the dev-board V&V run defined in [model-vnv-dev-board.md](model-vnv-dev-board.md). The method follows [model-evaluation.md](model-evaluation.md), and laptop figures come from [model-evaluation-results.md](model-evaluation-results.md).

**Date:** 2026-11-11 (second board run of the same test)
**Board:** Radxa ROCK 5T (RK3588, 4× A76 at 2.3 GHz + 4× A55 at 1.8 GHz, 12 GB RAM), heatsink with fan
**Model:** `qwen3.5:4b` (Q4_K_M, ID `d8b0f5e9760c`), thinking off
**Runtime:** Ollama 0.40.3, CPU only (no NPU, no GPU)
**Test:** first 20 IFEval prompts (the same prompts as the laptop battery screen), then a repeat of the first 5

## Summary

- **The model runs well on the board.** It scored the same IFEval accuracy as the laptop (17 of 20 prompts), generated slightly faster (4.60 vs 4.36 tokens/s), and fit in RAM (6.7 GB peak of 12 GB).
- **Heat is the main limit.** The SoC passed 80 °C within 48 seconds of the first prompt, averaged 83 °C and peaked at 85.9 °C, past its 85 °C throttle point. The big cores ran below their 2.30 GHz maximum for 95% of the run (1.82 GHz on average) and dipped as low as 408 MHz.
- **The results repeat exactly.** All 20 answers are word for word the same as in the earlier board run, and the first 5 answers were the same again in the repeat run. The setup also passes every other verification check: same Ollama version and weights as the laptop, no errors, no cut-off answers, and a complete resource log.

## Results

### Board compared with the laptop (first 20 IFEval prompts, thinking off)

| Measurement | Laptop (i7-1355U, battery) | ROCK 5T board |
|---|---:|---:|
| IFEval prompt-level strict (%) | 85 | 85 |
| IFEval instruction-level strict (%) | 90.0 | 86.7 |
| IFEval prompt / instruction-level loose (%) | — | 85 / 86.7 |
| Generation speed (tokens/s) | 4.36 | 4.60 |
| Prompt processing speed (tokens/s) | — | 14.4 |
| Average seconds per answer | 63.2 | 60.1 |
| Average output tokens per answer | 253 | 253 |
| Model load time (s) | 15.7 | 24.9 |
| Peak model memory (GB) | 6.61 (container) | 6.70 (Ollama processes) |
| Model memory increase (GB) | 6.47 | 6.67 |
| Peak system RAM (GB) | 32.2 of 32 | 10.8 of 12 (4.7 at start) |
| Average Ollama CPU use (%) | — | 95 |
| SoC temperature, start → peak (°C) | — | 56.9 → 85.9 |
| Hottest CPU core peak (°C) | — | 88.6 |
| Energy per answer | 0.37 Wh (whole laptop) | not measured |
| Total run time for 20 answers | — | 20.0 min |

Memory is measured differently on each machine (`docker stats` on the laptop, process RSS on the board), so compare the two memory rows with care.

### Failed prompts (board)

| Prompt | Instructions failed |
|---|---|
| 6: critique in all capital letters, in 2 sections | All capitals, multiple sections |
| 7: resume with capitalised key words | Capital-word frequency (passed the other 2 instructions) |
| 19: tweet with no capital letters | Letter frequency (passed the no-capitals instruction) |

Both machines failed 3 of 20 prompts, but the board passed fewer individual instructions (86.7% vs 90.0%). The weights and settings are the same, so the answers probably differ slightly because floating-point maths on an ARM CPU differs from an x86 CPU. With 20 prompts, a gap this size is within noise.

### Thermal behaviour

| | Main run (started cool) | Repeat run (started warm) |
|---|---:|---:|
| Prompts | 20 | 5 |
| SoC temperature start / average / peak (°C) | 56.9 / 83.3 / 85.9 | 69.0 / 81.3 / 85.0 |
| Seconds from first prompt to 80 °C | 48 | 46 |
| Time at or above 85 °C | 16% | 3% |
| Big-core clock average (MHz, max 2304) | 1822 | 1543 |
| Time with big cores below max clock | 95% | 89% |
| Time with big cores at or below 1.2 GHz | 5% | 24% |
| Lowest big-core clock (MHz) | 408 | 408 |
| Generation speed (tokens/s) | 4.60 | 4.42 |

- The SoC reached 80 °C within a minute of the model starting, then held at about 83–85 °C, at the throttle point, for the rest of the run.
- Per-answer speed stayed between 4.06 and 5.15 tokens/s across all 20 answers, so the throttling did not show up as a clear slowdown. Generation on this CPU seems to be limited more by memory bandwidth than by clock speed. The big-core clock column is the lowest of the big clusters, so one cluster may be throttled while the other runs faster.
- The repeat run, started 7 minutes after the main run on a warm board, was 4% slower and ran with the big cores much lower (24% of the time at or below 1.2 GHz).
- **Sustained use on this cooler is thermally limited.** For an always-on device, the cooling needs to keep the SoC under about 80 °C.

### Compared with the earlier board run

| | Earlier run | This run |
|---|---:|---:|
| IFEval prompt / instruction-level strict (%) | 85 / 86.7 | 85 / 86.7 |
| Answers identical to the other run | 20 of 20 | 20 of 20 |
| Generation speed (tokens/s) | 4.34 | 4.60 |
| Average seconds per answer | 63.8 | 60.1 |
| Peak Ollama memory (GB) | 6.89 | 6.70 |
| SoC peak (°C) | 85.9 | 85.9 |
| Repeat-run speed (tokens/s) | 3.24 | 4.42 |

The answers and scores match exactly. Speed varies by about 6% for the main run, and much more for the repeat run, which started on a hotter board last time.

## V&V outcome

### Verification

| ID | Check | Result | Evidence |
|---|---|---|---|
| V-01 | Ollama version matches the laptop | **Pass** | 0.40.3 (`/api/version` and `manifest.json`) |
| V-02 | Same weights as the laptop | **Pass** | Digest `d8b0f5e9760c…` in `manifest.json` |
| V-03 | Same harness and settings | **Pass** | lm_eval 0.4.13, temperature 0, seed 42, 16k context, thinking off, limit 20 |
| V-04 | Completed without errors | **Pass** | `Results saved to ...` printed for both runs; no failed requests, warnings or thinking output |
| V-05 | No truncated answers | **Pass** | 0 of 20 (and 0 of 5 in the repeat) |
| V-06 | Resource log complete | **Pass** | 1,227 rows, largest gap 1.0 s, no `unreachable` entries |
| V-07 | Model was actually loaded | **Pass** | Ollama memory 0.03 → 6.70 GB |
| V-08 | Local only | **Pass** | Server at `127.0.0.1:11435`; `HF_HUB_OFFLINE=1` and `HF_DATASETS_OFFLINE=1`; dataset read from local cache |
| V-09 | Repeatable | **Pass** | First 5 answers identical, word for word, in the repeat run; all 20 identical to the earlier board run |

### Validation

The targets are proposals, because the project has no requirements document yet.

| ID | Measure | Proposed target | Result | Verdict |
|---|---|---|---|---|
| VAL-01 | IFEval prompt-level strict | ≥ 70% | 85% | **Pass** |
| VAL-02 | Generation speed | ≥ 3 tokens/s | 4.60 (cool start), 4.42 (warm start) | **Pass** |
| VAL-03 | Seconds per answer | Report | 60.1 s (laptop 63.2 s) | Recorded |
| VAL-04 | Peak model memory | ≤ 8 GB | 6.70 GB | **Pass** |
| VAL-05 | Thermal | SoC < 85 °C, no sustained throttling | 85.9 °C peak; big cores below max clock 95% of the run | **Fail** |
| VAL-06 | Offline operation | No network needed | Ran offline | **Pass** |

## Setup notes

- **Ollama 0.40.3** is installed under `~/.local/ollama-0.40.3` and runs as user `radxa` on port **11435**. `setup_board.sh` needs sudo, which isn't available. A separate root-owned Ollama 0.40.16 on port 11434 was left alone and not used.
- **The Python venv** (`.venv`) was set up without the `python3-venv` package, which also needs sudo. pip was installed into the venv with `get-pip.py`.
- **`monitor_resources.py`** logs SoC temperature, the hottest CPU core, the lowest clock of any cluster and the lowest big-core clock on Linux. On Windows these columns stay blank.
- **`analyze_run.py`** reports start and peak temperature and the big-core clock, and doesn't say "laptop on AC" when the board simply has no battery.
- **No energy data.** The board has no battery, and its USB-C power-delivery sensor reads 0 V / 0 A.
- The KDE desktop and VS Code were open during the run (4.7 GB system RAM in use at the start).

## Next steps

1. **Improve the cooling, then repeat the 20-prompt run** to see whether the board can hold full clock speed: a larger heatsink, better thermal paste or pad, and more airflow.
2. **Add a USB-C power meter** between the supply and the board to get energy per answer and per token.
3. **Run the other two candidates** (`qwen3:4b-instruct-2507-q4_K_M`, `qwen3:8b`) on the board, then the 100-prompt screen. The 8B (about 11 GB peak on the laptop) may not fit in 12 GB alongside the desktop.
4. **Try the RK3588 NPU** (6 TOPS) through Rockchip's RKLLM runtime. It could be faster and cooler than the CPU.
5. **Write the requirements** (speed, memory and thermal targets) so the V&V targets above can be confirmed.

## Raw data

On the board, in `benchmark_results/` (gitignored):

| Run | Folder | Resource log | Console log |
|---|---|---|---|
| 20 prompts | `20261111T154417864163Z` | `resources_20261111T154415Z.csv` | `board_run2_20.log` |
| 5-prompt repeat | `20261111T160505540457Z` | `resources_20261111T160502Z.csv` | `board_run2_5_repeat.log` |
| Earlier 20 prompts | `20261111T144259968591Z` | `resources_20261111T144258Z.csv` | `board_run_20.log` |
| Earlier 5-prompt repeat | `20261111T150453763622Z` | `resources_20261111T150514Z.csv` | `board_run_5_repeat.log` |

Each run folder holds `manifest.json`, `analysis.json` and, per model, `results.json` and `requests.jsonl`.
