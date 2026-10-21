# Model Evaluation Results

Results of the battery screen described in [model-evaluation.md](model-evaluation.md).

## Battery screen (2026-10-19)

The first 20 IFEval prompts per model, with thinking off, on battery, run with `evaluate_ollama.py`, `monitor_resources.py` and `analyze_run.py`.

| Measurement | qwen3:4b-instruct-2507 | qwen3.5:4b | qwen3:8b |
|---|---:|---:|---:|
| IFEval prompt-level strict (%) | 90 | 85 | 95 |
| IFEval instruction-level strict (%) | 93.3 | 90.0 | 96.7 |
| Generation speed (tokens/s) | 5.32 | 4.36 | 2.82 |
| Average seconds per answer | 61.5 | 63.2 | 105.6 |
| Average output tokens per answer | 308 | 253 | 274 |
| Model load time (s) | 16.5 | 15.7 | 42.2 |
| Peak container memory (GB) | 6.17 | 6.61 | 11.22 |
| Container memory increase (GB) | 6.14 | 6.47 | 8.58 |
| Peak system RAM (GB) | 30.8 | 32.2 | 32.0 |
| Average whole-laptop power (W) | 20.3 | 20.9 | 19.1 |
| Energy per answer, whole laptop (Wh) | 0.35 | 0.37 | 0.56 |
| Energy per output token, whole laptop (J) | 4.1 | 5.2 | 7.4 |
| Battery during run (%) | 74 → 61 | 61 → 48 | 67 → 45 |

All three runs passed the [checks](model-evaluation.md#4-checks-after-every-run): no errors, truncated answers or thinking output, and on battery for the whole window.

## Findings

- **Accuracy is not separated yet.** The 8B passed 19 of 20 prompts, instruct-2507 18 and qwen3.5:4b 17. With 20 prompts the standard error is 5–8 points, so these gaps are within noise.
- **Speed, energy and memory are clearly separated.** The 8B is about 1.9× slower than instruct-2507, uses about 1.6× the energy per answer, and needs about 2.4 GB more container memory.
- **qwen3:4b-instruct-2507 leads on this screen.** It is the fastest, uses the least energy per answer and per token, needs the least memory, and its accuracy is within noise of the others.

## How to read these figures

- **Energy:** use the whole-laptop figures (screen included). The idle baseline was 16.87 W on the first charge (instruct-2507, qwen3.5:4b) and 12.67 W on the second (qwen3:8b). Net figures depend heavily on which baseline is used, so they are left out of the table. The 8B's lower average power probably reflects the screen being off for more of its longer run, not the model itself.
- **RAM:** system RAM sat at about 23.5 GB before each run and peaked at 31–32 GB of 32 GB, so Windows was probably paging. That likely slowed the speed figures somewhat and makes the system RAM increase unreliable per model. Compare models on the container memory increase instead (from `docker stats`, so not the full footprint). The 8B started with 2.64 GB in the container, probably cached data from earlier runs, and its increase excludes that.
- **Battery capacity** read 62.26 Wh, down from the 64.9 Wh in the plan.

## Problems found during the runs

- **Slow start-up:** lm_eval indexes every task file before the first prompt, which took 5–15 minutes on this laptop and looks like a hang. It falls outside the measured window.
- **Sleep:** Windows sleeps after 3 minutes idle on battery, and inference does not count as activity. The laptop slept once during the 8B's start-up (outside the window). Keep the system awake for future runs without changing power settings, for example with `SetThreadExecutionState`.
- **Logging:** in Windows PowerShell 5.1, piping the run's output to a file hid lm_eval's messages. Launch from bash with `> log 2>&1`.

## Estimated run times

From the speeds above, plus about 15 minutes of start-up per run. All of these need to run plugged in.

| Prompts | instruct-2507 | qwen3.5:4b | qwen3:8b | All three | Std. error at 90% accuracy |
|---:|---:|---:|---:|---:|---:|
| 100 | 1.7 h | 1.8 h | 2.9 h | 6.4 h | 3.0 points |
| 200 | 3.4 h | 3.5 h | 5.9 h | 12.8 h | 2.1 points |
| 300 | 5.1 h | 5.3 h | 8.8 h | 19.2 h | 1.7 points |
| 541 (full IFEval) | 9.3 h | 9.5 h | 15.9 h | 34.6 h | 1.3 points |

Thinking runs (hybrid models only) are estimated at about 4–7 minutes per prompt for qwen3.5:4b and 6–10 minutes for qwen3:8b, but this has not been measured.

## Next steps

1. AC screen: 100 prompts per model. All three fit in one night in a single run (`--models` with all three tags).
2. Thinking screen: about 10 prompts each for qwen3.5:4b and qwen3:8b. Time the first answers before committing to more.

## Raw data

`benchmark_results/` is gitignored, so the raw data is only on the test laptop:

| Model | Run folder |
|---|---|
| qwen3:4b-instruct-2507 | `20261019T163134406147Z` |
| qwen3.5:4b | `20261019T165547589357Z` |
| qwen3:8b | `20261019T193832731135Z` |

Each folder has `analysis.json`, plus `results.json` and `requests.jsonl` per model. The resource logs are `resources_20261019T*.csv` in the same parent folder.
