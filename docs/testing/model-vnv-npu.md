# Model V&V: Dev Board NPU (qwen3.5 4B)

Verification and validation plan for running the candidate model on the RK3588 NPU of the dev board. It repeats the CPU test in [model-vnv-dev-board.md](model-vnv-dev-board.md) with the NPU doing the inference, and carries out step 4 of the [CPU-with-fan next steps](RockLocalCPUWithFAN.md#next-steps). Results are in [RockLocalNPU.md](RockLocalNPU.md). The baseline for comparison is the CPU run with the fan, [RockLocalCPUWithFAN.md](RockLocalCPUWithFAN.md). All board tests from here on use the fan.

- **Verification** asks whether the evaluation was run correctly on the board: right software, right weights, no errors, complete logs, repeatable results, and **inference really on the NPU**.
- **Validation** asks whether the model is fit for the device: accuracy, speed, memory and thermal behaviour.

## Scope

| Item | In scope |
|---|---|
| Model | Qwen3.5-4B, RKLLM w8a8 build for the RK3588 (`qwen3.5-4b_w8a8_rk3588.rkllm`), thinking off |
| Benchmark | IFEval, first 20 prompts (the same prompts as the laptop and CPU board runs), then a repeat of the first 5 |
| Not in scope yet | The vision encoder (`.rknn`), other models on the NPU, w4a16 builds, the 100-prompt screen, thinking mode, energy |

## Test article and environment

| Item | Value |
|---|---|
| Board | Radxa ROCK 5T, Rockchip RK3588 (4× Cortex-A76 + 4× Cortex-A55, 3-core 6 TOPS NPU), 12 GB LPDDR |
| OS | Debian 12, Linux 6.1 (Rockchip BSP), aarch64 |
| Cooling | Board heatsink with PWM fan (`pwmfan`), CPU governor `ondemand`, NPU governor `rknpu_ondemand` |
| NPU driver | `rknpu` 0.9.8 (kernel, already on the board) |
| NPU runtime | RKLLM runtime 1.3.1 (`librkllmrt.so`, from `airockchip/rknn-llm` tag `release-v1.3.1`), in `~/rkllm` |
| Model file | `Qengineering/Qwen3.5-4B-rk3588`, revision `ee09c44b`, converted with RKLLM 1.3.0, w8a8, KV cache up to 16,384 |
| Server | `models/rkllm_server.py`: an Ollama-compatible server over RKLLM, on `127.0.0.1:11436`, model tag `qwen3.5:4b-w8a8-npu` |
| Python | Same 3.11 venv (`.venv`) with `lm_eval[ifeval]` 0.4.13, `requests`, `nltk`, `psutil` |
| Monitor | `monitor_resources.py --container "" --process rkllm_server.py`: server RAM/CPU, SoC/CPU temperature, CPU clocks, **NPU clock, NPU load and per-core NPU interrupt counts**, once a second |

### What is the same as the CPU test

- The evaluator, `models/evaluate_ollama.py`, **unchanged**. The NPU server answers the same Ollama API calls (`/api/chat`, `/api/tags`, `/api/show`, `/api/ps`, `/api/version`), so the prompts, settings, error checks and output files are exactly the CPU test's.
- The analysis, `models/analyze_run.py`, with NPU figures added (it gives the same numbers as before for the CPU runs).
- Prompts, harness version, greedy decoding, seed 42, 16k context, 1,280-token answer limit, thinking off, offline mode, fan, procedure.

### What differs, and why

- **Runtime.** Ollama cannot use the NPU, so the model runs on Rockchip's RKLLM runtime through `rkllm_server.py`.
- **Quantization.** The NPU model is w8a8 (8-bit weights and activations). The CPU model is Q4_K_M (about 4.5-bit weights). The base model (Qwen3.5-4B) is the same, but the weights are not identical, so answers can differ. Accuracy is checked again, not assumed.
- **Pre-converted model.** Rockchip's conversion tool runs only on x86_64 PCs, so a published conversion is used to keep the whole test on the board. Its SHA-256 is recorded (V-02).
- **Sampling.** Ollama applied temperature 0 plus the qwen3.5 Modelfile's `presence_penalty 1.5`. RKLLM has no temperature-0 mode, so greedy is `top_k 1`, with the same `presence_penalty 1.5`. The penalty window may differ between the two runtimes.
- **Speed source.** Token counts and times come from RKLLM's own performance counters (prefill and generate time), not Ollama's.
- **Memory.** The server process's RSS and system RAM in use are both reported. Some NPU buffers may not count towards process RSS, so system RAM in use is the main memory figure for this run.

## Verification

| ID | Check | Method | Pass criterion |
|---|---|---|---|
| V-01 | Runtime and driver versions | `/api/version` in `manifest.json`; server log | RKLLM runtime 1.3.1, rknpu driver 0.9.8, no driver-version warning |
| V-02 | Expected weights | SHA-256 of the `.rkllm` in `manifest.json` | `31ebf6a003675c82c72a2893bf46136720a0ae052a40bb12814e1bf67314b8ca` (the file's Hugging Face LFS hash) |
| V-03 | Same harness and settings | `manifest.json`, `requirements-frozen.txt`, logged requests | lm_eval 0.4.13, greedy, seed 42, 16k context, 1,280-token limit, thinking off, first 20 IFEval prompts |
| V-04 | Run completed without errors | Evaluator output | `Results saved to ...` printed; no failed request, context overflow or thinking output |
| V-05 | No truncated answers | `analysis.json` | `truncated_answers` = 0 |
| V-06 | Resource log complete | `resources_*.csv` | About 1 row per second; no gaps over 5 s; no `unreachable` model entries |
| V-07 | Model was actually loaded | `analysis.json` | System RAM in use rises by more than 2 GB from the start |
| V-08 | Local only | Evaluator URL check; `HF_HUB_OFFLINE=1`, `HF_DATASETS_OFFLINE=1` | Loopback server only; harness ran offline from the cached dataset |
| V-09 | Repeatable | Rerun the first 5 prompts and compare answer text with the 20-prompt run | All 5 answers identical |
| V-10 | **Inference ran on the NPU** | `analysis.json` NPU figures; server log | Interrupt counts rise on all 3 NPU cores during the window; NPU load above 0 during answers; runtime log reports the RK3588 platform |

## Validation

The targets are the same proposed working targets as the CPU test, because the project still has no requirements document.

| ID | Measure | Proposed target | Compare with (CPU with fan) |
|---|---|---|---|
| VAL-01 | IFEval prompt-level strict, 20 prompts | ≥ 70% (≥ 14/20) | 85% |
| VAL-02 | Generation speed | ≥ 3 tokens/s | 4.45 tokens/s |
| VAL-03 | Average seconds per answer | Report | 62.6 s |
| VAL-04 | Peak model memory | ≤ 8 GB | 6.95 GB (process) / 7.0 GB system increase |
| VAL-05 | Thermal | Peak SoC temperature < 85 °C, no sustained clock drop | 61.0 °C, full clock 99.8% |
| VAL-06 | Offline operation | No network needed (V-08) | Ran offline |
| VAL-07 | Answers compared with the CPU run | Report how many of the 20 answers match the CPU run, and which prompts pass or fail in each | 17/20 passed |

Prompt processing speed is also reported (CPU with fan: 15.8 tokens/s), because it sets how long a RAG prompt with retrieved context takes before the first word appears.

## Procedure

Run from `~/is2-local-ai` with the venv active (`source .venv/bin/activate`).

1. **One-time setup:** download `librkllmrt.so` and `rkllm.h` (RKLLM `release-v1.3.1`) to `~/rkllm`, and the `.rkllm` file to `~/rkllm/models`.
2. **Before the session:** close heavy apps; make sure Ollama has no model loaded; let the board idle a few minutes.
3. **Start the NPU server** (it loads the model on the first request, like Ollama):
   ```bash
   python is2-local-ai/models/rkllm_server.py \
     --model ~/rkllm/models/qwen3.5-4b_w8a8_rk3588.rkllm --lib ~/rkllm/librkllmrt.so \
     --name qwen3.5:4b-w8a8-npu --port 11436 \
     --source "hf:Qengineering/Qwen3.5-4B-rk3588@ee09c44b" > benchmark_results/npu_server.log 2>&1 &
   ```
4. **Offline mode:** `export HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1`
5. **Run 20 prompts:**
   ```bash
   python is2-local-ai/models/monitor_resources.py --container "" --process rkllm_server.py \
     --base-url http://127.0.0.1:11436 -- \
     python is2-local-ai/models/evaluate_ollama.py --models qwen3.5:4b-w8a8-npu --limit 20 \
     --base-url http://127.0.0.1:11436 > benchmark_results/npu_20.log 2>&1
   ```
6. **Analyze:** `python is2-local-ai/models/analyze_run.py benchmark_results/<run folder>`
7. **Repeatability (V-09):** repeat step 5 with `--limit 5` and compare each answer's `message.content` with the 20-prompt run.
8. **Compare with the CPU run (VAL-07):** compare answers and per-prompt pass/fail with run `20261114T014816631879Z`.
9. **Record** the results against every V and VAL item in [RockLocalNPU.md](RockLocalNPU.md).

## Limitations

- **20 prompts** give only a rough accuracy check (about ±18 points).
- **Different quantization** (w8a8 against Q4_K_M), so this compares NPU and CPU *deployments* of the same model, not identical weights.
- **Third-party conversion.** The `.rkllm` file was converted by Q-engineering, not by this project. Converting it ourselves on an x86 PC and rerunning would confirm it.
- **NPU load from devfreq** is the driver's utilisation estimate. The per-core interrupt counts are the direct evidence that the NPU ran.
- **No energy figures** until a USB-C power meter is added.
