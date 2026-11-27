# Rock 5T Local GPU Results with Fan: qwen3.5:4b

Results of the GPU V&V run defined in [model-vnv-gpu.md](model-vnv-gpu.md). The method follows [model-evaluation.md](model-evaluation.md). The baseline is the CPU-only run with the fan, [RockLocalCPUWithFAN.md](RockLocalCPUWithFAN.md). The NPU results are in [RockLocalNPU.md](RockLocalNPU.md).

**Date:** 2026-11-22 (evening, local time)
**Board:** Radxa ROCK 5T (RK3588, 4× A76 at 2.3 GHz + 4× A55 at 1.8 GHz, Mali-G610 MC4 GPU at up to 1.0 GHz, 12 GB RAM), heatsink with PWM fan (`pwmfan`)
**Model:** `qwen3.5:4b` (Q4_K_M, ID `d8b0f5e9760c`), **the same GGUF file as the CPU runs**, thinking off
**Runtime:** llama.cpp `b12633` (Vulkan), Mesa 26.2.7 GPU driver, in Docker, through `models/llamacpp_server.py` (Ollama-compatible). Model weights on the GPU, KV cache in system RAM.
**Test:** the first 20 IFEval prompts (the same prompts as the CPU and NPU runs), then a repeat of the first 5. Same evaluator, settings and fan log as the CPU-with-fan run.

## Summary

- **The model runs on the GPU, entirely on the board.** The GPU averaged 75% load at its full 1.0 GHz clock and was busy in 97% of the samples. The server process used 10% of the CPU, and the NPU was idle (0 interrupts).
- **Getting it to run took a newer GPU driver and one compromise.** The board's own Mesa is too old for llama.cpp, so the test ran in Docker with Mesa 26.2.7. With the KV cache on the GPU, every answer failed, so the KV cache (and the attention maths over it) stayed in system RAM on the CPU.
- **It is much slower than the CPU.** Generation averaged 1.16 tokens/s, against 4.45 on the CPU, which fails the 3 tokens/s target. Prompt processing was 1.75 tokens/s, against 15.8. An average answer took 250 s, against 63 s.
- **Accuracy is good.** 16 of 20 prompts passed (80%), against 17 of 20 (85%) on the CPU. With IFEval's loose scoring, the GPU scored 95%, the best of the three runs.
- **It used the most memory.** System RAM in use rose by 7.7 GB, against 7.0 GB for the CPU and 6.0 GB for the NPU.
- **The board passes every V&V check except speed (VAL-02).** On this board, with today's drivers, the GPU is the slowest of the three ways to run the model.

## CPU, NPU and GPU compared: best option going forward

This section brings the three Rock 5T runs together for discussion: the CPU with fan ([RockLocalCPUWithFAN.md](RockLocalCPUWithFAN.md)), the NPU ([RockLocalNPU.md](RockLocalNPU.md)) and the GPU (this report). All three used the same 20 IFEval prompts, the same evaluator, greedy decoding, a 16k context, the fan, and the desktop left open.

### Side by side

| Measurement | CPU with fan | NPU | GPU | Best |
|---|---:|---:|---:|---|
| Runtime | Ollama 0.40.3 | RKLLM 1.3.1 | llama.cpp b12633 (Vulkan) in Docker | — |
| Model file | Q4_K_M GGUF | w8a8 `.rkllm` (third-party conversion) | Same Q4_K_M GGUF as the CPU | CPU / GPU |
| IFEval prompt-level strict | 85% | 70% | 80% | CPU |
| IFEval prompt-level loose | 85% | 85% | 95% | GPU |
| Generation speed (tokens/s) | 4.45 | 3.02 | 1.16 | **CPU** |
| Prompt processing (tokens/s) | 15.8 | 22.4 | 1.75 | **NPU** |
| Average seconds per answer | 62.6 | 91.0 | 249.8 | **CPU** |
| Model load time (s) | 47.0 | 30.1 | 38.2 | NPU |
| System RAM increase (GB) | 7.0 | 6.0 | 7.7 | **NPU** |
| CPU used by the model (% of 8 cores) | 92 | 9 | 10 | **NPU** (GPU close) |
| SoC peak temperature (°C) | 61.0 | 61.9 | 61.9 | Even |
| Fan at full speed (% of the time) | 53 | 10 | 37 | **NPU** |
| Sensitivity to other load | Low | High (needs the 4 big cores free) | Low | CPU / GPU |
| Set-up effort | Ollama only | Custom server, pre-converted model | Docker, newer Mesa, workaround | **CPU** |
| V&V checks failed | None | None (speed and accuracy on the limit) | VAL-02 (speed) | CPU |

### How each option comes out

- **CPU (Ollama): the best option today.** It is the fastest at writing answers and the most accurate on the strict score, and it is the simplest to set up and maintain. Its costs are that it keeps the CPU almost fully busy and runs the fan hardest.
- **NPU (RKLLM): the most promising for the device.** It reads prompts fastest, uses the least memory, leaves the CPU free and runs coolest. But it was slower than the CPU at writing answers (3.02 tokens/s, against Rockchip's published 6.2), it lost some accuracy with its 8-bit model, and it slows down sharply when other software uses the big CPU cores.
- **GPU (llama.cpp Vulkan): not practical on this board now.** It kept good accuracy and freed the CPU, but it was the slowest by far, needed a newer driver in Docker and could not hold the KV cache on the GPU. Driver updates could change this, but the shared memory limits how fast any of the three can write answers.

### Recommendation

1. **Use the CPU with Ollama as the working set-up** for the plug-in on the RK3588 for now.
2. **Keep the NPU as the main candidate to replace it,** and settle it with two short tests before deciding:
   - CPU and NPU with the desktop closed, to see whether the NPU gets close to Rockchip's 6.2 tokens/s.
   - CPU and NPU with RAG-sized prompts (1,000–4,000 tokens), where the NPU's faster prompt processing should count most.
3. **Drop the GPU from the plan for this chip,** and recheck it only after a kernel or Mesa update. The Docker image makes that a quick rerun.
4. **Look at a smaller model** (Qwen3.5-2B) on the CPU and NPU. Memory bandwidth limits generation on all three, so a model half the size should be roughly twice as fast. Its accuracy would need checking.

### Questions for the team

- **Which matters more for the plug-in:** how fast the first words appear (prompt processing, where the NPU wins), or how fast the whole answer is written (generation, where the CPU wins)?
- **Does the plug-in need the CPU for other work while it answers,** such as the RAG search, the knowledge base or a user interface? If so, the NPU's 9% CPU use counts strongly in its favour.
- **Is the lower NPU accuracy acceptable** (70% against 85% strict, the same 85% loose), or should the NPU use a model converted by the project, possibly at a different quantization?
- **Will the final device use an RK3588 at all?** If not, these results mainly show that memory bandwidth and NPU software support should be key points when choosing the processor.
- **Is a power measurement needed before deciding?** The NPU's low CPU use and fan duty suggest it uses the least energy, but this has not been measured.

## Overall: GPU compared with CPU and NPU

On this board, **the GPU did worse than both the CPU and the NPU** for running the model. Its accuracy was good, and it freed the CPU as the NPU did, but it was about four times slower than the CPU at writing answers and about nine times slower at reading prompts. It needed a newer driver in Docker and a workaround even to run. For now, the GPU is not a practical option for the plug-in on the RK3588.

### Benefits of the GPU

| Benefit | GPU | CPU | NPU | Why it matters |
|---|---:|---:|---:|---|
| Same weights as the CPU | Same GGUF file | — | Different (w8a8) | A like-for-like comparison, with no third-party conversion |
| Good accuracy | 80% strict, 95% loose | 85% / 85% | 70% / 85% | Passes the 70% target comfortably |
| Leaves the CPU mostly free | 10% CPU | 92% | 9% | Other parts of the plug-in can use the CPU |
| Uses standard tools | llama.cpp (Vulkan), the engine inside Ollama | Ollama | RKLLM only | The same model files and settings as the CPU set-up |

### Shortfalls of the GPU

| Shortfall | GPU | CPU | NPU | Why it matters |
|---|---:|---:|---:|---|
| Slowest generation | 1.16 tokens/s | 4.45 | 3.02 | Fails the 3 tokens/s target; answers take 250 s on average |
| Very slow prompt processing | 1.75 tokens/s | 15.8 | 22.4 | RAG prompts with retrieved text would take minutes before the first word |
| Most memory | +7.7 GB system RAM | +7.0 GB | +6.0 GB | Least headroom on a 12 GB board |
| Needs a newer driver than the OS has | Mesa 26.2.7 in Docker | — | — | Extra moving parts, and the desktop still uses the older driver |
| Not fully on the GPU | KV cache and attention on the CPU | — | — | The only set-up that ran; a full-GPU run fails with "out of device memory" |
| Young, fragile driver stack | GPU job timeouts with Mesa 26.0 | — | — | Results could change a lot, either way, with kernel or Mesa updates |

### What would change the verdict

1. **A newer kernel.** The board runs a 6.1 kernel with a back-ported `panthor` GPU driver. A Radxa image with a 6.12+ kernel and an up-to-date `panthor` may allow the KV cache on the GPU and fix the slow prompt processing.
2. **Rockchip's proprietary Mali driver with an OpenCL engine** (for example MLC-LLM, which has Mali-tuned code). This needs the kernel's GPU driver switched from `panthor` to Rockchip's `mali` driver, so it was not tried.
3. **Even with perfect drivers, generation is limited by memory bandwidth.** The CPU, GPU and NPU share the same LPDDR memory, so a GPU is unlikely to beat the CPU by much at writing answers on this chip. Prompt processing is where a working GPU could help.

## Results

### GPU compared with the CPU-with-fan and NPU runs (first 20 IFEval prompts, thinking off)

| Measurement | CPU with fan (2026-11-13) | NPU (2026-11-22) | GPU (this run) |
|---|---:|---:|---:|
| IFEval prompt-level strict (%) | 85 | 70 | 80 |
| IFEval instruction-level strict (%) | 86.7 | 80.0 | 86.7 |
| IFEval prompt-level loose (%) | 85 | 85 | 95 |
| Generation speed (tokens/s) | 4.45 | 3.02 | 1.16 |
| Prompt processing speed (tokens/s) | 15.8 | 22.4 | 1.75 |
| Average seconds per answer | 62.6 | 91.0 | 249.8 |
| Average output tokens per answer | 253 | 263 | 253 |
| Model load time (s) | 47.0 | 30.1 | 38.2 |
| System RAM increase (GB) | 7.0 | 6.0 | 7.7 |
| Peak system RAM (GB) | 10.3 of 12 | 8.7 of 12 | 10.6 of 12 |
| Server CPU use (% of all 8 cores) | 92.4 | 9.2 | 10.3 |
| GPU load average / clock average | — | — | 75% / 977 MHz |
| Share of samples with the GPU busy (load > 10%) | — | — | 97% |
| GPU temperature start / average / peak (°C) | — | — | 58.3 / 59.0 / 61.9 |
| SoC temperature start / average / peak (°C) | 40.9 / 58.5 / 61.0 | 56.9 / 59.5 / 61.9 | 60.5 / 59.7 / 61.9 |
| Hottest CPU core peak (°C) | 63.8 | 63.8 | 63.8 |
| Time at or above 85 °C | 0% | 0% | 0% |
| Big-core clock average (MHz, max 2304) | 2301 | 2302 | 2271 |
| NPU interrupts in the window (per core) | — | about 1.06 million | 0 |
| Total run time for 20 answers | 20.9 min | 30.3 min | 83.3 min |

- **Memory.** GPU buffers are not counted in the server process's RSS (2.65 GB here), so **system RAM in use** is the figure to compare. It rose 7.7 GB, partly because the KV cache sits in system RAM next to the GPU's copy of the model.
- **Prompt processing** ranged from 0.4 to 5.1 tokens/s per answer. Short prompts were slowest, because fixed GPU set-up costs per answer outweigh the few tokens.
- **CPU use** is low because the weights' maths runs on the GPU. The CPU still does the attention maths over the KV cache, which is small for these short prompts.
- **SoC start temperature** was higher than in the CPU run (60.5 against 40.9 °C), because the board had been running tests for several hours. The peaks are almost the same.

### Failed prompts

| Prompt | Instructions | CPU | NPU | GPU | Why the GPU failed |
|---|---|:---:|:---:|:---:|---|
| 4: repeat the request, then an email with a `<<title>>` | Repeat prompt, title | Pass | Fail | Pass | — |
| 7: critique in all capital letters, in 2 sections | All capitals, multiple sections | Fail | Fail | **Pass** | — (the GPU passed both instructions) |
| 8: resume with capitalised key words | Capital-word frequency | Fail | Fail | Fail | Same as the CPU; passes under loose scoring |
| 12: diaper advertisement, all in JSON | JSON format | Pass | Pass | **Fail** | Invalid JSON: a closing brace is missing |
| 14: film review in all lower case | Lower case | Pass | Fail | Pass | — |
| 15: blog post under 300 words | Word count | Pass | Fail | **Fail** | 312 words; passes under loose scoring |
| 20: tweet with no capital letters | Letter frequency | Fail | Fail | Fail | Same as the CPU; passes under loose scoring |

Only prompt 12 fails under loose scoring, which is why the GPU's loose score is 95%. Only 3 of the 20 answers (prompts 17, 18 and 19, all short) are word for word the same as the CPU's. The weights are identical, but llama.cpp `b12633` is much newer than the llama.cpp inside Ollama 0.40.3, and the GPU's arithmetic differs slightly from the CPU's. With greedy decoding, one different word early on changes the rest of the answer. The settings check before the run showed the same thing on the CPU alone (see [model-vnv-gpu.md](model-vnv-gpu.md#settings-check-before-the-run)).

### Speed

- Per-answer generation speed was steady, from 1.12 to 1.36 tokens/s. The repeat run averaged 1.21 tokens/s.
- **Fixes and settings tried before the run** (all with the whole model on the GPU):

| Set-up | Result |
|---|---|
| Board's own Mesa 25.0.7 | GPU offers only Vulkan 1.1; llama.cpp needs 1.2 |
| Mesa 26.0.8 (Ubuntu 26.04) in Docker | GPU found (Vulkan 1.4). More than about 8 layers: GPU jobs time out (`panthor ... job timeout`), reported as `ErrorOutOfDeviceMemory` |
| Mesa 26.0.8 with smaller GPU submissions, allocation limits, no host-visible memory, or no chunked delta-net | Same failure |
| Mesa 26.2.7 (kisak PPA), short benchmark | Whole model runs: 9.2 tokens/s prompt, 1.75 tokens/s generation |
| Mesa 26.2.7, flash attention on, or a different matrix-vector path | No speed change |
| Mesa 26.2.7, `llama-server` with the KV cache on the GPU (2k, 4k, 16k context, 8-bit cache) | Every answer fails with `ErrorOutOfDeviceMemory` |
| Mesa 26.2.7, `llama-server` with the KV cache in system RAM | **Works; used for this run** |

- With the KV cache in system RAM, generation (1.16 tokens/s) is a little slower than the short benchmark with everything on the GPU (1.75 tokens/s). Prompt processing is far slower (1.75 against 9.2 tokens/s).

### Thermal and fan behaviour

| | CPU with fan | NPU | GPU (20 prompts) | GPU repeat (5 prompts) |
|---|---:|---:|---:|---:|
| SoC peak (°C) | 61.0 | 61.9 | 61.9 | 62.9 |
| GPU peak (°C) | — | — | 61.9 | 61.9 |
| Fan at full speed (PWM 255) | 53% | 10% | 37% | 37% |
| Fan at a lower step (PWM 64–192) | 24% | 42% | 40% | 33% |
| Fan off (PWM 0) | 23% | 48% | 23% | 29% |

- The GPU run ran the fan more than the NPU run but less than the CPU run, and the SoC stayed more than 20 °C below the throttle point.
- The big cores dipped below their maximum clock in 1.8% of the samples (90 samples). These are governor changes, not throttling: the SoC stayed below 63 °C.

## V&V outcome

### Verification

| ID | Check | Result | Evidence |
|---|---|---|---|
| V-01 | Runtime and driver versions | **Pass** | llama.cpp `b12633` Vulkan, Mesa `26.2.7~kisak1~r`, image `is2-gpu-vulkan:b12633` (`sha256:88467877…`) in `manifest.json`; device `Vulkan0: Mali-G610 MC4` |
| V-02 | Same weights as the CPU run | **Pass** | Ollama ID `d8b0f5e9760c…` and GGUF SHA-256 `a9d0a3e1d8c9…` in `manifest.json`; hash checked by the server before serving |
| V-03 | Same harness and settings | **Pass** | lm_eval 0.4.13, temperature 0, seed 42, presence penalty 1.5, top_k 20, top_p 0.95, 16k context, 1,280-token limit, thinking off, limit 20. Evaluator unchanged |
| V-04 | Completed without errors | **Pass** | `Results saved to ...` printed for both runs; no failed requests, warnings or thinking output |
| V-05 | No truncated answers | **Pass** | 0 of 20, 0 of 5 |
| V-06 | Resource log complete | **Pass** | 5,025 rows, largest gap 2.0 s, no `unreachable` entries |
| V-07 | Model was actually loaded | **Pass** | System RAM 2.9 → 10.6 GB (+7.7 GB) |
| V-08 | Local only | **Pass** | Server at `127.0.0.1:11437`, llama-server on `127.0.0.1:8090`; offline flags set; dataset from local cache |
| V-09 | Repeatable | **Pass** | First 5 answers identical, word for word, in the repeat run |
| V-10 | Inference ran on the GPU | **Pass** | GPU load 75% average, busy in 97% of samples, clock 977 MHz average (idle: about 6% at 300 MHz); server CPU use 10%; NPU interrupts 0 |

### Validation

The targets are proposals, because the project has no requirements document yet.

| ID | Measure | Proposed target | CPU with fan | GPU | Verdict |
|---|---|---|---|---|---|
| VAL-01 | IFEval prompt-level strict | ≥ 70% | 85% | 80% (95% loose) | **Pass** |
| VAL-02 | Generation speed | ≥ 3 tokens/s | 4.45 | 1.16 (1.21 in the repeat) | **Fail** |
| VAL-03 | Seconds per answer | Report | 62.6 s | 249.8 s | Recorded |
| VAL-04 | Peak model memory | ≤ 8 GB | 7.0 GB | 7.7 GB (system RAM increase) | **Pass** |
| VAL-05 | Thermal | SoC < 85 °C, no sustained throttling | 61.0 °C | 61.9 °C (GPU 61.9 °C) | **Pass** |
| VAL-06 | Offline operation | No network needed | Ran offline | Ran offline | **Pass** |
| VAL-07 | Answers against the CPU run | Report | — | 3 of 20 identical; passed 1 prompt the CPU failed, failed 2 the CPU passed | Recorded |

## Setup notes

- **Same evaluator and procedure as the CPU runs.** `llamacpp_server.py` answers the Ollama API calls the evaluator uses, so `evaluate_ollama.py` ran unchanged. The commands are in [model-vnv-gpu.md](model-vnv-gpu.md#procedure).
- **Docker.** The user `radxa` was added to the `docker` group for this test. The image is built from [models/gpu-vulkan.Dockerfile](../../models/gpu-vulkan.Dockerfile), with Ubuntu 26.04, the llama.cpp release and the Mesa version all pinned. The container gets `/dev/dri` and runs as `radxa` (with the `render` and `video` groups). It reads the model from Ollama's store, read-only.
- **Runtime settings:** all layers on the GPU (`-ngl 99`), KV cache in system RAM (`--no-kv-offload`), 16,384 context, 4 CPU threads, one slot, prompt cache off, `repeat_penalty 1.0`.
- **First attempt failed.** The first 20-prompt run (folder `20261122T234606086836Z`) stopped on prompt 1 with `ErrorOutOfDeviceMemory`, because the KV cache was on the GPU. That run was discarded, the cause was found, and the full run was repeated with the KV cache in system RAM.
- **Monitor additions:** GPU clock and load (devfreq). Unlike the NPU's load figure, the GPU's tracks real use.
- **Other software running:** the KDE desktop, VS Code over remote desktop, and an idle Ollama container (`local-ai-ollama`, port 11434, no model loaded), as in the earlier runs. The desktop keeps using the board's own Mesa 25.0.7.
- **No energy data.** The board has no battery, and its USB-C power-delivery sensor reads 0 V / 0 A.

## Next steps

1. **Keep the GPU out of the plug-in's plans for the RK3588 for now.** The CPU (fastest generation) and the NPU (fastest prompt processing, lowest CPU use) are the practical options.
2. **Recheck the GPU after a kernel or Mesa update.** The Docker image makes the test quick to repeat: rebuild it with a newer Mesa, then run the procedure.
3. **If the GPU matters for the final device,** try Rockchip's proprietary Mali driver with an OpenCL engine on a spare SD card, so the working set-up is not disturbed.
4. **Run all three with the desktop closed and with RAG-sized prompts,** so the comparison reflects the plug-in's real use.

## Raw data

On the board, in `~/is2-local-ai/benchmark_results/` (gitignored):

| Run | Folder | Resource log | Console log |
|---|---|---|---|
| 20 prompts | `20261123T002030111146Z` | `resources_20261123T002026Z.csv` | `gpu_20.log` |
| 5-prompt repeat | `20261123T014416448473Z` | `resources_20261123T014413Z.csv` | `gpu_5_repeat.log` |
| Failed first attempt (20 prompts, then the repeat it started) | `20261122T234606086836Z`, `20261122T234859550002Z` | `resources_20261122T234602Z.csv` | — (overwritten by the second run) |
| Fan log (both runs) | — | `fan_20261123T001823Z.csv` | — |
| Server and container logs | — | — | `gpu_server.log`, `gpu_llama_server_container.log`, `gpu_settings_check_rp1.0.log`, `gpu_settings_check_rp1.1.log` |

Folder names use UTC, so they are dated 2026-11-23 although the runs were on the evening of 2026-11-22 local time. Each run folder holds `manifest.json`, `analysis.json` and, per model, `results.json` and `requests.jsonl`.
