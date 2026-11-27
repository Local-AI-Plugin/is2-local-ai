# Model V&V: Dev Board GPU (qwen3.5:4b)

Verification and validation plan for running the candidate model on the Mali-G610 GPU of the dev board. It repeats the CPU test in [model-vnv-dev-board.md](model-vnv-dev-board.md) with the GPU doing the inference, after the NPU test in [model-vnv-npu.md](model-vnv-npu.md). Results are in [RockLocalGPU.md](RockLocalGPU.md). The baseline for comparison is the CPU run with the fan, [RockLocalCPUWithFAN.md](RockLocalCPUWithFAN.md).

- **Verification** asks whether the evaluation was run correctly on the board: right software, right weights, no errors, complete logs, repeatable results, and **inference really on the GPU**.
- **Validation** asks whether the model is fit for the device: accuracy, speed, memory and thermal behaviour.

## Scope

| Item | In scope |
|---|---|
| Model | `qwen3.5:4b` (Q4_K_M, Ollama ID `d8b0f5e9760c`), **the same GGUF file as the CPU runs**, thinking off |
| Benchmark | IFEval, first 20 prompts (the same prompts as the CPU and NPU runs), then a repeat of the first 5 |
| Not in scope yet | Other models, the 100-prompt screen, thinking mode, energy, OpenCL or Rockchip's proprietary Mali driver |

## Test article and environment

| Item | Value |
|---|---|
| Board | Radxa ROCK 5T, Rockchip RK3588 (4× Cortex-A76 + 4× Cortex-A55, Mali-G610 MC4 GPU at up to 1.0 GHz), 12 GB LPDDR shared by CPU, GPU and NPU |
| OS | Debian 12, Linux 6.1 (Rockchip BSP), aarch64 |
| Cooling | Board heatsink with PWM fan (`pwmfan`), CPU governor `ondemand`, GPU governor `simple_ondemand` |
| GPU kernel driver | `panthor` (open-source Mali driver, part of the board's kernel) |
| GPU user-space driver | Mesa 26.2.7 (`26.2.7~kisak1~r`, PanVK Vulkan driver), **inside Docker** |
| Runtime | llama.cpp release `b12633`, prebuilt Ubuntu Vulkan ARM64 build (SHA-256 `8968356a…5c3e6`), `llama-server` |
| Container | `is2-gpu-vulkan:b12633`, built from [models/gpu-vulkan.Dockerfile](../../models/gpu-vulkan.Dockerfile) (Ubuntu 26.04 base, pinned by digest) |
| Server | `models/llamacpp_server.py`: an Ollama-compatible server on `127.0.0.1:11437` that starts the container on the first request, model tag `qwen3.5:4b-gpu` |
| Python | Same 3.11 venv (`.venv`) with `lm_eval[ifeval]` 0.4.13, `requests`, `nltk`, `psutil` |
| Monitor | `monitor_resources.py --container "" --process llama-server`: server RAM/CPU, SoC/CPU/NPU/GPU temperature, CPU clocks, **GPU clock and load**, NPU interrupt counts, once a second |

### Why Docker, and why these versions

- **The board's own Mesa (25.0.7) is too old.** It gives the GPU only Vulkan 1.1, and llama.cpp needs Vulkan 1.2. Nothing newer is in the board's package sources.
- **llama.cpp's prebuilt Vulkan build needs glibc 2.38.** Debian 12 has 2.36, so it cannot run on the board directly.
- **A container solves both without changing the board.** Ubuntu 26.04's Mesa 26.0.8 gives Vulkan 1.4, but its GPU jobs time out (`panthor fb000000.gpu: [drm] job timeout` in the kernel log) once more than about 8 of the model's layers are on the GPU. **Mesa 26.2.7** (kisak PPA) runs the whole model.

### What is the same as the CPU test

- The evaluator, `models/evaluate_ollama.py`, **unchanged**. The GPU server answers the same Ollama API calls.
- **The weights:** the server reads Ollama's own GGUF blob (`sha256-a9d0a3e1…`) and checks its SHA-256 before serving.
- The analysis, `models/analyze_run.py`, with GPU figures added (same numbers as before for the CPU and NPU runs).
- Prompts, harness version, greedy decoding (temperature 0), seed 42, presence penalty 1.5, 16k context, 1,280-token answer limit, thinking off, offline mode, fan, procedure.

### What differs, and why

- **Runtime.** The board's Ollama has no GPU support for this chip, so the model runs on a newer llama.cpp (the engine inside Ollama) with its Vulkan backend.
- **KV cache in system RAM (`--no-kv-offload`).** With the KV cache on the GPU, `llama-server` fails on the first answer with `ErrorOutOfDeviceMemory` at every context size tried (2k, 4k, 16k, and 4k with an 8-bit cache). The model weights and their maths run on the GPU, while the attention maths over the KV cache runs on the CPU.
- **llama.cpp version.** llama.cpp `b12633` is much newer than the llama.cpp inside Ollama 0.40.3, with small numerical differences. A settings check (below) showed the same prompt tokens but answers that diverge after about the first 25 words.
- **Memory measure.** GPU buffers do not count towards the server process's RSS, so **system RAM in use** is the memory figure for this run.

### Settings check before the run

The CPU version of the same llama.cpp (GPU hidden) was given IFEval prompt 1 and compared with the Ollama CPU run's answer:

| Setting | Prompt tokens | First difference | Answer tokens (Ollama: 413) |
|---|---:|---:|---:|
| `repeat_penalty 1.0` | 89 (Ollama: 89) | after 122 characters | 464 |
| `repeat_penalty 1.1` | 89 | after 110 characters | 490 |

The prompt template matches exactly. `repeat_penalty 1.0` is closer, so it is used. Answers are not expected to match the CPU run word for word.

## Verification

| ID | Check | Method | Pass criterion |
|---|---|---|---|
| V-01 | Runtime and driver versions | `/api/version` in `manifest.json`; container log | llama.cpp `b12633` Vulkan, Mesa 26.2.7, device `Mali-G610 MC4 (panvk)` |
| V-02 | Same weights as the CPU run | GGUF SHA-256 and Ollama ID in `manifest.json` | Blob `a9d0a3e1…`, ID `d8b0f5e9760c` |
| V-03 | Same harness and settings | `manifest.json`, logged requests | lm_eval 0.4.13, temperature 0, seed 42, presence penalty 1.5, 16k context, 1,280-token limit, thinking off, first 20 IFEval prompts |
| V-04 | Run completed without errors | Evaluator output | `Results saved to ...` printed; no failed request, context overflow or thinking output |
| V-05 | No truncated answers | `analysis.json` | `truncated_answers` = 0 |
| V-06 | Resource log complete | `resources_*.csv` | About 1 row per second; no gaps over 5 s; no `unreachable` entries |
| V-07 | Model was actually loaded | `analysis.json` | System RAM in use rises by more than 2 GB from the start |
| V-08 | Local only | Evaluator URL check; offline flags | Loopback server only; harness ran offline from the cached dataset |
| V-09 | Repeatable | Rerun the first 5 prompts and compare answer text | All 5 answers identical |
| V-10 | **Inference ran on the GPU** | `analysis.json` GPU figures; container log | GPU busy (load above 10%) for most of the window; GPU at or near its 1.0 GHz clock; container log reports the Vulkan device; NPU interrupts 0; server CPU use low |

## Validation

The same proposed working targets as the CPU and NPU tests.

| ID | Measure | Proposed target | Compare with (CPU with fan) |
|---|---|---|---|
| VAL-01 | IFEval prompt-level strict, 20 prompts | ≥ 70% (≥ 14/20) | 85% |
| VAL-02 | Generation speed | ≥ 3 tokens/s | 4.45 tokens/s |
| VAL-03 | Average seconds per answer | Report | 62.6 s |
| VAL-04 | Peak model memory | ≤ 8 GB (system RAM increase for this run) | 7.0 GB system increase |
| VAL-05 | Thermal | Peak SoC temperature < 85 °C, no sustained clock drop | 61.0 °C |
| VAL-06 | Offline operation | No network needed (V-08) | Ran offline |
| VAL-07 | Answers compared with the CPU run | Report matches and per-prompt pass/fail | 17/20 passed |

## Procedure

Run from `~/is2-local-ai` with the venv active, as a user in the `docker` group.

1. **One-time setup:** `docker build -f is2-local-ai/models/gpu-vulkan.Dockerfile -t is2-gpu-vulkan:b12633 is2-local-ai/models/`. The model must already be in Ollama's store (`ollama pull qwen3.5:4b`).
2. **Before the session:** close heavy apps; make sure no Ollama or NPU server has a model loaded; let the board idle a few minutes.
3. **Start the GPU server** (it starts the container on the first request):
   ```bash
   python is2-local-ai/models/llamacpp_server.py --ollama-model qwen3.5:4b --name qwen3.5:4b-gpu \
     --port 11437 --ngl 99 --kv-on-cpu --repeat-penalty 1.0 \
     --log benchmark_results/gpu_llama_server_container.log > benchmark_results/gpu_server.log 2>&1 &
   ```
4. **Offline mode:** `export HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1`
5. **Run 20 prompts:**
   ```bash
   python is2-local-ai/models/monitor_resources.py --container "" --process llama-server \
     --base-url http://127.0.0.1:11437 -- \
     python is2-local-ai/models/evaluate_ollama.py --models qwen3.5:4b-gpu --limit 20 \
     --base-url http://127.0.0.1:11437 > benchmark_results/gpu_20.log 2>&1
   ```
6. **Analyze:** `python is2-local-ai/models/analyze_run.py benchmark_results/<run folder>`
7. **Repeatability (V-09):** repeat step 5 with `--limit 5` and compare each answer with the 20-prompt run.
8. **Compare with the CPU run (VAL-07)** and **record** the results in [RockLocalGPU.md](RockLocalGPU.md).

## Limitations

- **20 prompts** give only a rough accuracy check (about ±18 points).
- **KV cache and attention on the CPU.** This is the only configuration that ran, so the result is "weights on the GPU", not a full-GPU run. A newer kernel or Mesa may lift this.
- **Young driver stack.** The board's 6.1 kernel carries a back-ported `panthor` driver, and PanVK support for this GPU is recent. Results may change a lot with driver updates.
- **Container GPU driver differs from the board's.** The desktop keeps using the board's Mesa 25.0.7; only the test uses Mesa 26.2.7.
- **No energy figures** until a USB-C power meter is added.
