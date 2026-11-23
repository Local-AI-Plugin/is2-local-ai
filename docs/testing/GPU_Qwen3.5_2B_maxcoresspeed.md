# Rock 5T GPU Results, Max Core Speed: Qwen3.5 2B

Results of running Qwen3.5-2B on the Rock 5T's Mali GPU with all clocks locked at maximum, compared with the 2B CPU and NPU runs ([CPU-NPU_Qwen3.5_2B_maxcoresspeed.md](CPU-NPU_Qwen3.5_2B_maxcoresspeed.md)) and the 4B GPU run ([RockLocalGPU.md](RockLocalGPU.md)). The test repeats the procedure of the GPU test plan ([model-vnv-gpu.md](model-vnv-gpu.md)) with the same V&V checks.

**Date:** 2026-11-23
**Board:** Radxa ROCK 5T (RK3588, Mali-G610 MC4 GPU at 1.0 GHz, 12 GB RAM shared by CPU, NPU and GPU), heatsink with PWM fan (`pwmfan`)
**Clocks:** locked at maximum by the `rock5t-max-clocks` boot service ([hardware/processing_unit/rock5t](../../hardware/processing_unit/rock5t/README.md)): CPU `performance`, memory 2,400 MHz, NPU 1.0 GHz, GPU 1.0 GHz
**Model:** `qwen3.5:2b-q4_K_M` (Q4_K_M, 1.9B parameters, Ollama ID `1e2d21a4f03a`). The same GGUF file as the CPU 2B Q4_K_M run, read from Ollama's model store.
**Runtime:** llama.cpp b12633 (Vulkan build) in the `is2-gpu-vulkan:b12633` Docker image, Mesa 26.2.7 (PanVK), through `models/llamacpp_server.py`. All layers on the GPU (`-ngl 99`), KV cache in system RAM (`--no-kv-offload`), as in the 4B GPU run. Thinking off.
**Test:** the first 20 IFEval prompts (the same prompts as all earlier board runs), then a repeat of the first 5.

## Summary

- **The GPU is the slowest way to run the 2B model, by a wide margin.** It generated at 2.79 tokens/s, against 9.00 on the CPU and 10.09 on the NPU. An average answer took 123 s, against 29 s (CPU) and 26 s (NPU).
- **The smaller model helps the GPU too, but not enough.** Against the 4B GPU run, generation went from 1.16 to 2.79 tokens/s and the average answer from 250 s to 123 s. It is still about 3.5 times slower than the CPU and NPU.
- **Reading prompts is the GPU's weakest stage.** Short prompts ran at about 11 tokens/s and longer ones (about 90 tokens) at about 2.6 tokens/s, against 49 tokens/s on the CPU and 100 on the NPU. The first prompt after each model load took about 150 s.
- **Accuracy is the lowest of the 2B runs:** 11 of 20 prompts passed (55%), against 65% for the CPU with the same model file and 60% for the NPU. The GPU gives different answers from the CPU with the same weights, and one answer ran to the 1,280-token limit.
- **It is light on the CPU and cool:** 10% CPU use, SoC peak 61.9 °C, fan off more than half the time.
- **Recommendation: drop the GPU as an option for running the model.** The NPU 2B remains the fastest option, and the CPU 4B the most accurate.

## CPU, NPU and GPU compared (2B)

### Side by side

| Measurement | CPU 2B (Q4_K_M) | CPU 2B (Q8_0) | NPU 2B (w8a8) | GPU 2B (Q4_K_M) | GPU 4B (Q4_K_M) | Best 2B |
|---|---:|---:|---:|---:|---:|---|
| Clocks | Max | Max | Max | Max | Default | — |
| IFEval prompt-level strict | 65% | 70% | 60% | 55% | 80% | CPU Q8_0 |
| IFEval prompt-level loose | 75% | 70% | 60% | 60% | 95% | CPU Q4_K_M |
| IFEval instruction-level strict | 73.3% | 73.3% | 73.3% | 60.0% | 86.7% | CPU / NPU |
| Generation (tokens/s) | 9.00 | 6.57 | **10.09** | 2.79 | 1.16 | **NPU** |
| Prompt processing (tokens/s) | 49.3 | 50.9 | **99.9** | 3.54 | 1.75 | **NPU** |
| Average seconds per answer | 28.6 | 40.1 | **25.6** | 122.7 | 249.8 | **NPU** |
| Model load time (s) | 7.0 | 25.8 | **3.6** | 21.0 | 38.2 | **NPU** |
| System RAM increase (GB) | 3.7 | 4.3 | **2.7** | 4.6 | 7.7 | **NPU** |
| CPU used by the model (% of 8 cores) | 94 | 93 | 16 | **10** | 10 | **GPU** |
| SoC peak temperature (°C) | 66.5 | 66.5 | **61.9** | **61.9** | 61.9 | NPU / GPU |
| Fan at full speed (% of the time) | 99 | 97 | 25 | **12** | 37 | **GPU** |
| Input power while answering (W) | Not measured | Not measured | Not measured | Not measured | Not measured | — |
| Passes all validation targets | No (accuracy) | Yes (on the limit) | No (accuracy) | No (accuracy, speed) | Yes | CPU Q8_0 |

### How each option comes out

- **NPU 2B: still the best all-round 2B option.** Fastest at every stage, least memory, light on the CPU. Its weakness is accuracy (60%).
- **CPU 2B: nearly as fast, a little more accurate,** but it keeps all CPU cores busy and runs the fan at full speed.
- **GPU 2B: the slowest and least accurate.** Its only advantages are low CPU use and low heat, and the NPU gives those too at almost four times the speed.

### Why the GPU is slow

- **The GPU shares the same memory as the CPU and NPU,** so it has no extra bandwidth for reading the weights, which is what limits generation on this board.
- **The Mali GPU's Vulkan driver (PanVK) and llama.cpp's Vulkan code are not tuned for this chip.** The GPU was busy 94% of the time at its full 1.0 GHz clock, so it was not waiting for work: it is just slow per token.
- **The KV cache has to stay in system RAM** (with it on the GPU, every answer fails with an out-of-memory error), so attention runs on the CPU side and data crosses between the two for every token.
- **The first prompt after loading is very slow** (about 150 s), which points to the GPU compiling its programs on first use. Prompts of about 90 tokens took about 34 s, against about 4 s for prompts of about 50 tokens.

### Power

**Not measured.** The Rock 5T cannot measure its own power: nothing on the board measures current. Its only power-delivery sensor (on the USB-C port) reads 0 V / 0 A because the board is not powered through it, and the power chip reports the voltage it sets for each part but not the current drawn. No power meter was available for this run.

Heat gives a ranking instead. With the same heatsink and fan, a part that uses more power runs the fan harder. By that measure the GPU 2B run used the least power of the 2B runs (fan at full speed 12% of the time), then the NPU 2B (25%), then the CPU 2B (99%). This is a ranking, not a figure in watts.

To measure power in later runs, one of these is needed:

| Option | What it gives |
|---|---|
| INA219 or INA226 current-sensor board in the 12 V power lead, wired to the board's I2C pins | Input watts logged every second next to the temperatures, and energy per answer, in every report |
| Logging USB-C power meter (if the board is powered through USB-C) | The same, from the meter's own log |
| Plug-in wall meter or inline USB-C meter, read by eye | Idle, typical and peak watts for each run |

None of these can measure the CPU, NPU and GPU separately; they measure the whole board. Comparing runs (CPU, NPU, GPU) shows the difference each option makes.

## Results

### GPU 2B run against the other 2B runs (first 20 IFEval prompts, thinking off)

| Measurement | CPU 2B Q4_K_M | NPU 2B | GPU 2B | GPU 2B repeat (5 prompts) |
|---|---:|---:|---:|---:|
| Answers / truncated | 20 / 0 | 20 / 0 | 20 / 1 | 5 / 0 |
| IFEval prompt-level strict (%) | 65 | 60 | 55 | 80 |
| IFEval instruction-level strict (%) | 73.3 | 73.3 | 60.0 | 75.0 |
| IFEval prompt-level loose (%) | 75 | 60 | 60 | 80 |
| Generation speed (tokens/s) | 9.00 | 10.09 | 2.79 | 2.80 |
| Per-answer generation speed range (tokens/s) | 4.87–11.29 | 8.07–11.46 | 2.77–3.08 | 2.76–3.02 |
| Prompt processing speed (tokens/s) | 49.3 | 99.9 | 3.54 | 1.65 |
| Average seconds per answer | 28.6 | 25.6 | 122.7 | 140.0 |
| Average output tokens per answer | 245 | 251 | 300 | 269 |
| Model load time (s) | 7.0 | 3.6 | 21.0 | 19.3 |
| Peak server process memory (GB) | 3.67 | 2.56 | 1.31 | 0.66 |
| System RAM start → peak (GB) | 3.1 → 6.8 | 2.8 → 5.5 | 3.2 → 7.8 | 3.1 → 7.1 |
| System RAM increase (GB) | 3.7 | 2.7 | 4.6 | 4.0 |
| Server CPU use (% of all 8 cores) | 93.8 | 15.7 | 9.9 | 9.6 |
| GPU load average / busy share / clock | — | — | 81% / 94% / 1,000 MHz | 71% / 81% / 1,000 MHz |
| GPU temperature start / average / peak (°C) | — | — | 52.7 / 59.1 / 61.9 | 58.1 / 58.9 / 61.0 |
| SoC temperature start / peak (°C) | 54.3 / 66.5 | 54.4 / 61.9 | 53.9 / 61.9 | 59.4 / 61.0 |
| NPU temperature start / average / peak (°C) | 53.7 / 61.8 / 62.9 | 53.4 / 58.5 / 60.1 | 53.0 / 58.4 / 61.0 | 58.2 / 58.3 / 60.1 |
| Hottest CPU core peak (°C) | 68.4 | 63.8 | 62.9 | 61.0 |
| Big-core clock average (MHz, max 2304) | 2304 | 2304 | 2304 | 2304 |
| NPU interrupts in the window (per core) | 0 | about 761,000 | 0 | 0 |
| Total run time for 20 answers | 9.6 min | 8.5 min | 40.9 min | 11.7 min (5 answers) |

- **Generation speed is very steady on the GPU** (2.77–3.08 tokens/s for every answer), so the average is not skewed by a few slow answers.
- **Prompt processing is uneven.** The first prompt after each model load took 152 s (89 tokens). After that, prompts of 29–59 tokens took about 4 s each (about 11 tokens/s) and the two prompts of 87–89 tokens about 34 s each (about 2.6 tokens/s). Without the first prompt, the average is 6.9 tokens/s. The repeat run's average (1.65 tokens/s) is lower because 2 of its 5 prompts are the slow kind.
- **Memory:** the GPU's memory is part of system RAM, so the system RAM increase (4.6 GB) is the true cost, not the server process's 1.3 GB. It is slightly more than the CPU run with the same file (3.7 GB).
- **CPU use** stayed at about 10%, close to the NPU's.

### Failed prompts

| Prompt | Instructions | CPU 2B Q4 | NPU 2B | GPU 2B | Why the GPU failed |
|---|---|:---:|:---:|:---:|---|
| 1: 300+ word summary, no commas, 3 highlighted sections | No commas, highlights, word count | Pass | Fail | **Fail** | 272 words, 2 commas |
| 7: critique in all capital letters, in 2 sections | All capitals, sections | Fail | Fail | Fail | Not all in capitals (same as all runs) |
| 8: resume with capitalised key words | Capital-word frequency, quotation | Fail | Fail | Fail | Ran to the 1,280-token limit without finishing |
| 10: 500+ word email, given keywords, no commas | Keywords, word count, no commas | Fail | Fail | Fail | 399 words, missing keywords |
| 15: blog post under 300 words | Word count | Fail | Fail | Fail | 370 words |
| 16: funny list of famous mothers in JSON | JSON format | Pass | Pass | **Fail** | Invalid JSON (single quotes inside) |
| 17: two names for God, separated by `******` | Two responses | Fail | Pass | Fail | Numbered list instead of the separator |
| 18: two jokes, no commas, separated by `******` | No commas, two responses | Fail | Fail | Fail | Commas (same answer as the CPU, word for word) |
| 20: tweet with no capital letters | Letter frequency | Fail | Fail | Fail | Same as all runs |

- **The GPU failed every prompt the CPU 2B Q4_K_M failed, plus 1 and 16.** Both extra failures are precise rules: a word count with no commas, and valid JSON.
- **Same weights, different answers.** Only 3 of 20 answers are word for word the same as the CPU run with the same model file (prompts 5, 18 and 20). Most start the same and drift apart after a few dozen to a few hundred characters. This is normal for a different processor: small rounding differences in the GPU's arithmetic change which word is picked once two choices are close, and from then on the answer diverges.
- **The repeat scored 4 of 5 (80%)** because the first 5 prompts are among the easier ones. Its answers are identical to the first run's (see V-09).

### Thermal and fan behaviour

| | CPU 2B Q4 | NPU 2B | GPU 2B | GPU 2B repeat | GPU 4B |
|---|---:|---:|---:|---:|---:|
| SoC peak (°C) | 66.5 | 61.9 | 61.9 | 61.0 | 61.9 |
| GPU peak (°C) | — | — | 61.9 | 61.0 | 61.9 |
| NPU peak (°C) | 62.9 | 60.1 | 61.0 | 60.1 | — |
| Hottest CPU core peak (°C) | 68.4 | 63.8 | 62.9 | 61.0 | — |
| Fan at full speed (PWM 255) | 99% | 25% | 12% | 8% | 37% |
| Fan at a lower step (PWM 64–192) | 0% | 33% | 30% | 29% | 40% |
| Fan off (PWM 0) | 1% | 42% | 58% | 63% | 23% |

- **The GPU 2B run was the coolest of all runs so far:** the fan was off 58% of the time and at full speed only 12%.
- **The GPU, NPU and SoC sensors all read within about 1 °C of each other,** because they share one chip and one heatsink. The NPU's reading rose with the GPU's even though the NPU was idle (0 interrupts).
- **No throttling:** the big cores stayed at 2,304 MHz and the GPU at 1,000 MHz in every sample.

## V&V outcome

### Verification

| ID | Check | GPU 2B | Evidence |
|---|---|:---:|---|
| V-01 | Runtime and driver versions | **Pass** | llama.cpp b12633 Vulkan, image `is2-gpu-vulkan:b12633` (ID `88467877…`), Mesa 26.2.7 (`manifest.json`), panthor kernel driver |
| V-02 | Expected weights | **Pass** | Ollama ID `1e2d21a4f03a`, the same as the CPU 2B Q4_K_M run; GGUF SHA-256 `20cb277f…938f4c` checked by the server before loading |
| V-03 | Same harness and settings | **Pass** | lm_eval 0.4.13, greedy, seed 42, presence penalty 1.5, 16k context, 1,280-token limit, thinking off, limit 20; evaluator unchanged |
| V-04 | Completed without errors | **Pass** | `Results saved to ...` printed for both runs; no failed requests; no errors, timeouts or out-of-memory messages in the llama-server container log (the kernel log needs root and was not checked) |
| V-05 | No truncated answers | **Fail (1 of 20)** | Prompt 8 ran to the 1,280-token limit (a looping answer). That prompt also fails on the CPU and NPU, so the score is unchanged by it. 0 of 5 in the repeat |
| V-06 | Resource log complete | **Pass** | 2,471 and 717 rows; largest gap 1.0 s; no `unreachable` entries |
| V-07 | Model was actually loaded | **Pass** | System RAM +4.6 GB; GPU busy 94% of the time |
| V-08 | Local only | **Pass** | Servers on `127.0.0.1:11437` (shim) and `127.0.0.1:8090` (llama-server); offline flags set; dataset from local cache |
| V-09 | Repeatable | **Pass** | First 5 answers identical, word for word, in the repeat run |
| V-10 | Ran on the intended processor | **Pass** | GPU load 81% average at 1,000 MHz; NPU interrupts 0; server CPU use 10% |

The run's `manifest.json` labels the model as 4.2B because the GPU server had the 4B size written in. The Ollama ID and file hash confirm that the 2B file was used. The server now reads the size and quantization from Ollama's model record, so later runs show the right label.

### Validation

| ID | Measure | Proposed target | CPU 2B Q4_K_M | NPU 2B | GPU 2B |
|---|---|---|---|---|---|
| VAL-01 | IFEval prompt-level strict | ≥ 70% | 65% Fail | 60% Fail | 55% **Fail** |
| VAL-02 | Generation speed | ≥ 3 tokens/s | 9.00 Pass | 10.09 Pass | 2.79 **Fail** |
| VAL-03 | Seconds per answer | Report | 28.6 s | 25.6 s | 122.7 s |
| VAL-04 | Peak model memory | ≤ 8 GB | 3.7 GB Pass | 2.7 GB Pass | 4.6 GB **Pass** |
| VAL-05 | Thermal | SoC < 85 °C, no sustained throttling | 66.5 °C Pass | 61.9 °C Pass | 61.9 °C **Pass** |
| VAL-06 | Offline operation | No network needed | Pass | Pass | **Pass** |
| VAL-07 | Answers against other runs | Report | — | 1 of 20 same as CPU 2B Q4 | 3 of 20 same as CPU 2B Q4; 1 of 20 same as NPU 2B |

## Setup notes

- **Same evaluator and procedure as the earlier runs.** `evaluate_ollama.py` ran unchanged against `llamacpp_server.py`, with the same monitor, analysis and fan log. There was a 2-minute idle period after the server started and before the first prompt.
- **Same settings as the 4B GPU run:** all layers on the GPU, KV cache in system RAM, repeat penalty 1.0 (Ollama's value), prompt caching off. The model (and container) is loaded on the first request and stopped at the end of each run, as Ollama does with `keep_alive 0`.
- **Clocks locked at maximum** by the `rock5t-max-clocks` boot service; the session log records CPU `performance`, memory 2,400 MHz, NPU 1.0 GHz and GPU 1.0 GHz at the start.
- **Ollama and the NPU server were not running** during the GPU runs. The idle `local-ai-ollama` container and the desktop (KDE, VS Code over remote desktop) were running, as in the earlier runs. The VS Code renderer was not moved, as in the 4B GPU run.
- **No power data.** The board has no current sensors and no meter was available (see [Power](#power)).

## Next steps

1. **Drop the GPU as a way to run the model,** unless a later Mesa or llama.cpp release changes the picture. It could still run other work (for example the user interface or image tasks) while the NPU runs the model.
2. **Fit a current sensor or meter** (see [Power](#power)) and measure the CPU 2B, NPU 2B and GPU 2B, so energy per answer can be compared.
3. **Continue with the NPU 2B and CPU 4B** on planner-style prompts, as recommended in [CPU-NPU_Qwen3.5_2B_maxcoresspeed.md](CPU-NPU_Qwen3.5_2B_maxcoresspeed.md).

## Raw data

On the board, in `~/is2-local-ai/benchmark_results/` (gitignored):

| Run | Folder | Resource log | Console log |
|---|---|---|---|
| GPU 2B, 20 prompts | `20261123T162607400295Z` | `resources_20261123T162606Z.csv` | `gpu2b_20.log` |
| GPU 2B, 5-prompt repeat | `20261123T170719809966Z` | `resources_20261123T170718Z.csv` | `gpu2b_5_repeat.log` |
| Fan log (both runs) | — | `fan_20261123T162349Z.csv` | — |
| GPU server and container logs | — | — | `gpu2b_server.log`, `gpu2b_llama_server_container.log` |

Each run folder holds `manifest.json`, `analysis.json` and, per model, `results.json` and `requests.jsonl`.
