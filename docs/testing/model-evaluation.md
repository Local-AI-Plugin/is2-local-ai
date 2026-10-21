# Model Evaluation Plan

Results so far: [model-evaluation-results.md](model-evaluation-results.md).

## Purpose

Choose the starting language model for the Local AI Plug-In by measuring, for each candidate:

- **Instruction-following accuracy** (IFEval)
- **Speed** (tokens per second, seconds per answer)
- **RAM use**
- **Energy per answer and per token**

The tests run on a laptop that stands in for the device. The figures compare the candidates with each other; they are not predictions of how the models will perform on the final hardware.

## Test machine

| Item | Value |
|---|---|
| Laptop | Lenovo 21HJ, Intel Core i7-1355U (10 cores / 12 threads), Intel Iris Xe (no dedicated GPU), 32 GB RAM |
| Battery | 64.9 Wh full-charge capacity (read from WMI on 2026-10-13) |
| Inference | CPU only |
| Ollama | 0.40.3 in Docker container `local-ai-ollama` (image `ollama/ollama`), models in volume `local-ai-models`, served on `127.0.0.1:11434` |
| Docker limit | WSL2 VM capped at about 15.5 GB RAM |
| Python | 3.12 venv with `lm_eval[ifeval]` 0.4.13, `requests`, `nltk`, `psutil` |

## Candidate models

| Ollama tag | Size | Thinking mode |
|---|---|---|
| `qwen3.5:4b` | 3.3 GB | Hybrid (on/off) |
| `qwen3:4b-instruct-2507-q4_K_M` | 2.5 GB | Never thinks. Ollama wrongly lists "thinking" as a capability. |
| `qwen3:8b` | 5.2 GB | Hybrid (on/off) |

## Tools

All three scripts are in [`models/`](../../models/). Run them from the repository root so they all read and write the same `benchmark_results/` folder.

| Script | What it does | Output |
|---|---|---|
| `evaluate_ollama.py` | Runs lm-evaluation-harness tasks against Ollama, one chat message per prompt. Greedy decoding, seed 42, 16k context, no RAG, tools or retries. Stops on any error instead of scoring it as a wrong answer, and stops if thinking text appears in an answer. | `benchmark_results/<UTC time>[_think]/` with a manifest and, per model, `results.json` (scores) and `requests.jsonl` (every request and response, with Ollama's token counts and timings) |
| `monitor_resources.py` | Wraps the evaluator and samples once a second: loaded model, container RAM/CPU (`docker stats`), system RAM/CPU, battery state and discharge rate. Records the battery's full-charge capacity. | `benchmark_results/resources_<time>.csv` and `_summary.json` |
| `analyze_run.py` | Combines one run with its resources CSV. Each model's window runs from its first request's start to its last request's end. | `analysis.json` in the run folder |

`analyze_run.py` reports, per model:

- **Accuracy:** IFEval prompt-level and instruction-level, strict and loose.
- **Speed:** generation and prompt tokens/s, average output tokens and seconds per answer, model load time, answers that hit the token limit.
- **Resources:** starting, peak and increase for both container memory and system RAM, plus average container CPU. "Starting" is the average of the 10 s before the first request, before the model loads.
- **Energy (battery runs only):** average and peak power, total Wh (with the battery's charge drop as a cross-check), joules per output token, Wh per answer, and the same figures with the idle baseline subtracted.

Only text-generation tasks work (`ifeval`, `gsm8k`, `mmlu_pro`). The adapter cannot read token probabilities, so multiple-choice tasks scored that way (classic `mmlu`, `hellaswag`, `arc`) will not run.

## Approach

**Thinking off for all three models first.** `instruct-2507` cannot think, and mixing modes would confuse the effect of the model with the effect of the mode. Thinking also costs several times more tokens. Thinking runs come later, as a separate comparison for the two hybrid models.

**Two run groups, reported separately:**

| Group | Prompts per model | Power | What it gives |
|---|---|---|---|
| Battery screen | 20 (the same first 20 for every model) | Unplugged | Whole-laptop energy, battery-mode speed, RAM, rough accuracy |
| AC screen | 100 (the same first 100 for every model) | Plugged in | Better accuracy estimate, AC-mode speed, RAM. No power data. |

Do not merge the two groups into one "120-prompt" result. The first 20 AC prompts are the same as the battery prompts. Because decoding is greedy and seeded, their answers should match exactly, which makes a useful reproducibility check.

**Why these sizes.** The usable battery between 80% and 25% charge is about 64.9 Wh × 0.55 ≈ 36 Wh, roughly 1.8 hours at 20 W. Time estimates from early tests:

| Prompts | At 95 s per answer | At 2× that |
|---:|---:|---:|
| 20 | 32 min | 63 min |
| 50 | 79 min | 2.6 h |
| 100 | 2.6 h | 5.3 h |
| 541 (full IFEval) | 14.3 h | 28.6 h |

A 50-prompt 8B run may not fit on one charge, so the battery screen uses 20. These estimates rest on very few answers. One `qwen3.5:4b` answer on a loaded machine generated only 1.2 tokens/s (about 7 minutes per answer), so time the first run and adjust.

## Procedure

Commands are for PowerShell in VS Code, with the project venv active.

### 1. Before every measured session

1. **Stop other workloads.** Stop the Supabase stack (pulse-app) from Docker Desktop or with `docker stop`, and close heavy apps. Check that only the Ollama container is running:
   ```powershell
   docker ps --format "{{.Names}}"
   ```
   Then check in Task Manager that memory use has dropped and the machine is not paging heavily.
2. **Keep settings the same for every run,** including the idle baseline:
   - Windows power mode (check with `powercfg /getactivescheme`)
   - Battery Saver setting
   - screen brightness and screen-off timeout
   - 16k context, thinking off
3. **Let the laptop cool** for a few minutes if it has just been busy.
4. **Use offline mode** so the evaluation library does not hang on a network check (the IFEval dataset is already cached):
   ```powershell
   $env:HF_HUB_OFFLINE = '1'; $env:HF_DATASETS_OFFLINE = '1'
   ```
5. **Check Ollama is up** and nothing is loaded:
   ```powershell
   Invoke-RestMethod http://127.0.0.1:11434/api/ps
   ```
   Always use `127.0.0.1`. `localhost` added about 2 s per request on this machine.

### 2. Battery screen (one model per charge)

1. **Charge to about 80%, then unplug.** Check the charge:
   ```powershell
   (Get-CimInstance Win32_Battery).EstimatedChargeRemaining
   ```
2. **Record a 5-minute idle baseline.** Docker is running, no model is loaded, nothing else is active. Stop it with Ctrl+C:
   ```powershell
   python models/monitor_resources.py
   ```
   Note `power_w_avg` for `(none)` in the printed summary. This is the baseline wattage for step 4.
3. **Run 20 prompts on one model:**
   ```powershell
   python models/monitor_resources.py -- python models/evaluate_ollama.py --models qwen3:4b-instruct-2507-q4_K_M --limit 20
   ```
   After the first few answers, check the charge again. If the projected finish is below about 25%, stop and lower `--limit` for **all three** models. Windows turns Battery Saver on at 20%, which would change the measurement mid-run.
4. **Analyze:**
   ```powershell
   python models/analyze_run.py benchmark_results/<run folder> --baseline-w <idle W>
   ```
5. **Check the run** (see [Checks after every run](#4-checks-after-every-run)).
6. **Recharge, then repeat steps 1–5** for `qwen3.5:4b` and `qwen3:8b`.

### 3. AC screen (overnight, one model per night)

1. Plug in and follow [Before every measured session](#1-before-every-measured-session).
2. Run 100 prompts on one model:
   ```powershell
   python models/monitor_resources.py -- python models/evaluate_ollama.py --models <model> --limit 100
   ```
3. Analyze without a baseline (there is no power data on AC):
   ```powershell
   python models/analyze_run.py benchmark_results/<run folder>
   ```
4. Check the run, and compare its first 20 answers with the battery run's answers for the same model. They should be identical.
5. Repeat for the other two models on later nights.

### 4. Checks after every run

- **Truncated answers:** `truncated_answers` in `analysis.json` should be 0. The evaluator also prints `WARNING: output budget reached` during the run.
- **Errors:** the evaluator stops on any failed request, context overflow or thinking output. A run that finished printed `Results saved to ...`.
- **Resource log gaps:** the resources CSV should have about one row per second for the whole run, with no long gaps or `unreachable` model entries.
- **Power source (battery runs):** if the laptop was on AC for any part of a model's window, `analyze_run.py` reports no energy figures. Rerun that model.
- **Model actually loaded:** `ollama_mem_gb_peak` should be well above the idle value.

### 5. Later steps (only after the screens above are sound)

- **Thinking screen:** `--think` on `qwen3.5:4b` and `qwen3:8b` with a small `--limit` (about 10). A thinking answer can take up to about 20 minutes at 4 tokens/s, so 50 prompts would not fit on battery. If many answers hit the limit, raise `--think-budget`. Do full thinking runs only if accuracy clearly improves.
- **Full IFEval (541 prompts):** more than one night per model on this CPU. It is better run on the target hardware or a GPU machine.
- **Other benchmarks:** generation tasks only, with limits, e.g. `--tasks gsm8k mmlu_pro --limit 100`. MMLU-Pro alone has about 12,000 questions.

## Reporting

Use one table per run group. Do not compare tokens/s between battery and AC runs, because power mode changes CPU speed.

| Measurement | qwen3:4b-instruct-2507 | qwen3.5:4b | qwen3:8b |
|---|---|---|---|
| IFEval prompt-level strict (%) | | | |
| IFEval instruction-level strict (%) | | | |
| Generation speed (tokens/s) | | | |
| Average seconds per answer | | | |
| Peak container memory (GB) | | | |
| Peak system RAM (GB) | | | |
| Average whole-laptop power (W) | | | |
| Net energy per answer (Wh) | | | |
| Net energy per output token (J) | | | |

Label the figures as follows:

- **RAM** is "peak container memory reported by `docker stats`." Docker leaves out some cache, so this is not the full Windows/WSL memory footprint, and not the RAM the device will need.
- **Power and energy** are "whole-laptop battery estimates," screen included. Subtracting the idle baseline estimates the energy the model adds; it does not isolate the CPU. Battery readings are averaged over several seconds, so peak power misses short spikes.
- **Energy per answer** and **energy per token** should be shown together. A model that writes longer answers can look better per token while costing more per answer.

## Limitations

- **Small samples.** With 20 prompts, accuracy is only a rough check of the pipeline and of large differences (roughly ±18 points). With 100 prompts it is a better screen but still preliminary.
- **First N, not random.** `--limit` takes the first N prompts, so all models see the same questions, but the error ranges above are not formal confidence intervals for the full benchmark.
- **Not the target hardware.** Speed and energy are specific to this laptop's CPU.
- **Not a reproduction of model-card scores.** Prompts are sent through Ollama's chat template, without the exact settings used by model publishers.

## Open items

- A USB-C power meter between the charger and the laptop (about $20–30) would give power data for overnight AC runs.
- A 10-prompt run of one model with Battery Saver on and then off would show how much it changes speed and energy.
