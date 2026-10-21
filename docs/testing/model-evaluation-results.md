# Model Evaluation Results

Results of the battery screen and a short thinking-mode screen, run on the test laptop as described in [model-evaluation.md](model-evaluation.md).

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

## Thinking screen (2026-10-21)

qwen3.5:4b on the first 5 IFEval prompts with `--think --think-budget 8192`, on battery. It is compared with the same 5 prompts from the thinking-off run. qwen3:8b was not run.

| First 5 IFEval prompts | Thinking off | Thinking on |
|---|---:|---:|
| Prompts passed (strict) | 5 / 5 | 5 / 5 |
| Total output tokens | 1,428 | 16,992 |
| Average seconds per answer | 78 | 792 |
| Seconds per answer (prompts 0–4) | 127, 30, 134, 85, 13 | 1,869, 850, 691, 249, 299 |
| Generation speed (tokens/s) | 4.36 | 4.33 |
| Energy per answer, whole laptop (Wh) | ~0.45* | 4.28 |
| Peak container memory (GB) | 6.61 | 8.57 |
| Average whole-laptop power (W) | 20.9 | 19.5 |

\*Estimated from the thinking-off run's average power over these five answers.

- **Thinking cost about 12× the tokens, 10× the time and 9.5× the energy per answer, with no accuracy gain on these prompts.** Five prompts cannot show an accuracy gain, but on this CPU the cost is too high for IFEval. Thinking evaluation stopped here.
- **Thinking length varies widely:** 1,200–7,800 tokens per answer, so a single prompt can take over 30 minutes.
- **The default 4,096-token thinking budget is too small.** In an earlier attempt, prompt 0 used the whole budget (19 minutes) and returned an empty answer. With 8,192, no answer hit the limit.
- The run was on battery throughout, with no log gaps or standby. Power-based energy (21.4 Wh) matched the battery's charge drop (21.8 Wh). Idle baseline: 13.8 W, screen on.

## How to read these figures

- **Energy:** use the whole-laptop figures (screen included). The idle baseline was 16.87 W on the first charge (instruct-2507, qwen3.5:4b) and 12.67 W on the second (qwen3:8b). Net figures depend heavily on which baseline is used, so they are left out of the table. The screen was on for nearly all of each run (see Sleep below). The 8B's slightly lower average power, and the lower idle baseline on its charge, are not explained; screen brightness or background load may have differed between charges.
- **RAM:** system RAM sat at about 23.5 GB before each run and peaked at 31–32 GB of 32 GB, so Windows was probably paging. That likely slowed the speed figures somewhat and makes the system RAM increase unreliable per model. Compare models on the container memory increase instead (from `docker stats`, so not the full footprint). The 8B started with 2.64 GB in the container, probably cached data from earlier runs, and its increase excludes that.
- **Battery capacity** read 62.26 Wh, down from the 64.9 Wh in the plan.

## Problems found during the runs

- **Slow start-up:** lm_eval indexes every task file before the first prompt, which took 5–15 minutes on this laptop and looks like a hang. It falls outside the measured window.
- **Sleep:** this laptop uses Modern Standby, which starts when the screen turns off (3 minutes on battery), with the lid open or closed. Windows logged 31 s of standby during the instruct-2507 window and 16 s during the 8B window (negligible), and a longer standby during the 8B's start-up, outside the window. For future runs, keep both the system and the display awake (`SetThreadExecutionState` with `ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED`) for the baseline and the run. Blocking system sleep alone is not enough.
- **Logging:** in Windows PowerShell 5.1, piping the run's output to a file hid lm_eval's messages. Launch from bash with `> log 2>&1`.

## Estimated run times

From the speeds above, plus about 15 minutes of start-up per run. All of these need to run plugged in.

| Prompts | instruct-2507 | qwen3.5:4b | qwen3:8b | All three | Std. error at 90% accuracy |
|---:|---:|---:|---:|---:|---:|
| 100 | 1.7 h | 1.8 h | 2.9 h | 6.4 h | 3.0 points |
| 200 | 3.4 h | 3.5 h | 5.9 h | 12.8 h | 2.1 points |
| 300 | 5.1 h | 5.3 h | 8.8 h | 19.2 h | 1.7 points |
| 541 (full IFEval) | 9.3 h | 9.5 h | 15.9 h | 34.6 h | 1.3 points |

With thinking on, qwen3.5:4b averaged about 13 minutes per answer (see the thinking screen above).

## Next steps

Laptop testing is paused. Tests will be rerun on the dev board once it is set up, which is closer to the target hardware.

1. On the dev board: repeat the IFEval screens (thinking off), then the 100-prompt screen.
2. Consider PlanBench. It is not part of lm_eval, so it needs its own runner and a plan validator (VAL).

## Raw data

`benchmark_results/` is gitignored, so the raw data is only on the test laptop:

| Model | Run folder |
|---|---|
| qwen3:4b-instruct-2507 | `20261019T163134406147Z` |
| qwen3.5:4b | `20261019T165547589357Z` |
| qwen3:8b | `20261019T193832731135Z` |
| qwen3.5:4b, thinking on | `20261021T131437448463Z_think` |

Each folder has `analysis.json`, plus `results.json` and `requests.jsonl` per model. The resource logs are `resources_*.csv` in the same parent folder. Stopped attempts are in `aborted/`.
