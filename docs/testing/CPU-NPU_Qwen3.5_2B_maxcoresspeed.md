# Rock 5T CPU/NPU Results, Max Core Speed: Qwen3.5 2B

Results of running Qwen3.5-2B on the Rock 5T's CPU and NPU with all clocks locked at maximum. The aim was to find out how much faster a smaller model is, and how much accuracy it costs, after the 4B tests showed generation of only 3–4.5 tokens/s. The tests repeat the procedure of the CPU-with-fan test ([model-vnv-dev-board.md](model-vnv-dev-board.md)) and the NPU test ([model-vnv-npu.md](model-vnv-npu.md)), with the same V&V checks. The 4B baselines are [RockLocalCPUWithFAN.md](RockLocalCPUWithFAN.md) and [RockLocalNPU.md](RockLocalNPU.md); the GPU, which is not tested here, is in [RockLocalGPU.md](RockLocalGPU.md).

**Date:** 2026-11-22 (evening, local time)
**Board:** Radxa ROCK 5T (RK3588, 4× A76 at 2.3 GHz + 4× A55 at 1.8 GHz, 3-core 6 TOPS NPU at 1.0 GHz, 12 GB RAM), heatsink with PWM fan (`pwmfan`)
**Clocks:** locked at maximum by the `rock5t-max-clocks` boot service ([hardware/processing_unit/rock5t](../../hardware/processing_unit/rock5t/README.md)): CPU `performance`, memory 2,400 MHz, NPU 1.0 GHz, GPU 1.0 GHz
**Models:**
- CPU (main): `qwen3.5:2b-q4_K_M` (Q4_K_M, 1.9B parameters, Ollama ID `1e2d21a4f03a`), the same 4-bit format as the 4B CPU run
- CPU (extra): `qwen3.5:2b` (Q8_0, Ollama ID `0689d44085e0`), 8-bit like the NPU model
- NPU: `qwen3.5-2b_w8a8_rk3588.rkllm` (Q-engineering conversion, RKLLM toolkit 1.3.0), the same source as the 4B NPU model

**Runtimes:** Ollama 0.40.3 (CPU); RKLLM runtime 1.3.1 with rknpu driver 0.9.8 through `models/rkllm_server.py` (NPU). Thinking off.
**Test:** the first 20 IFEval prompts (the same prompts as all earlier board runs), then a repeat of the first 5, for the CPU Q4_K_M and the NPU. One extra 20-prompt run for the CPU Q8_0.

## Summary

- **The 2B model is about twice as fast as the 4B.** On the CPU, generation went from 4.45 to 9.00 tokens/s and the average answer from 63 s to 29 s. On the NPU, generation went from 3.02 to **10.09 tokens/s**, and the average answer from 91 s to **26 s**.
- **The NPU is now the fastest option.** With the 2B model it beats the CPU at both writing answers (10.09 against 9.00 tokens/s) and reading prompts (99.9 against 49.3 tokens/s). It also used the least memory (2.7 GB) and only 16% of the CPU.
- **Accuracy drops below the target.** 13 of 20 prompts passed on the CPU (65%) and 12 of 20 on the NPU (60%), against the 70% target and 85% for the 4B on the CPU. The 8-bit CPU version passed 14 of 20 (70%), exactly on the target, but it is slower (6.57 tokens/s). Most of the extra failures are precise limits: word counts, no commas, exact formats.
- **Answers are still too slow for a responsive planner at full length,** but much closer. A 250-token answer takes about 25 s. With short structured answers (about 80 tokens) it would take about 8 s on the NPU.
- **All verification checks pass.** Speed, memory and thermal targets pass for every 2B run; accuracy fails for the CPU Q4_K_M and the NPU.

## CPU and NPU compared: best option going forward

This section brings together the 2B runs and the earlier 4B runs. The 4B runs used the board's default clocks; locking the clocks was measured to add about 6% to generation on the CPU, so the 4B-to-2B gains are mostly from the smaller model.

### Side by side

| Measurement | CPU 4B (Q4_K_M) | NPU 4B (w8a8) | CPU 2B (Q4_K_M) | CPU 2B (Q8_0) | NPU 2B (w8a8) | Best |
|---|---:|---:|---:|---:|---:|---|
| Clocks | Default | Default | Max | Max | Max | — |
| IFEval prompt-level strict | 85% | 70% | 65% | 70% | 60% | CPU 4B |
| IFEval prompt-level loose | 85% | 85% | 75% | 70% | 60% | CPU 4B / NPU 4B |
| IFEval instruction-level strict | 86.7% | 80.0% | 73.3% | 73.3% | 73.3% | CPU 4B |
| Generation (tokens/s) | 4.45 | 3.02 | 9.00 | 6.57 | **10.09** | **NPU 2B** |
| Prompt processing (tokens/s) | 15.8 | 22.4 | 49.3 | 50.9 | **99.9** | **NPU 2B** |
| Average seconds per answer | 62.6 | 91.0 | 28.6 | 40.1 | **25.6** | **NPU 2B** |
| Model load time (s) | 47.0 | 30.1 | 7.0 | 25.8 | **3.6** | **NPU 2B** |
| System RAM increase (GB) | 7.0 | 6.0 | 3.7 | 4.3 | **2.7** | **NPU 2B** |
| CPU used by the model (% of 8 cores) | 92 | 9 | 94 | 93 | 16 | NPU 4B / NPU 2B |
| SoC peak temperature (°C) | 61.0 | 61.9 | 66.5 | 66.5 | 61.9 | CPU 4B |
| Fan at full speed (% of the time) | 53 | 10 | 99 | 97 | 25 | NPU 4B |
| Passes all validation targets | Yes | Yes (on the limit) | No (accuracy) | Yes (on the limit) | No (accuracy) | CPU 4B |

### How each option comes out

- **NPU 2B: the fastest and most efficient.** It writes answers fastest (10.09 tokens/s), reads prompts twice as fast as the CPU (99.9 tokens/s), loads in under 4 s, uses the least memory and leaves the CPU almost free. Its weakness is accuracy: 60%, the lowest of all runs, and it fails the target.
- **CPU 2B Q4_K_M: almost as fast, slightly more accurate.** 9.00 tokens/s and 65% accuracy. It keeps the CPU fully busy and ran the fan at full speed almost the whole time.
- **CPU 2B Q8_0: the only 2B set-up that meets the accuracy target, just.** 70% strict, but it is the slowest 2B option (6.57 tokens/s) and also keeps the CPU busy.
- **CPU 4B: still the most accurate.** 85%, but at 4.45 tokens/s an average answer takes a minute.

### Benefits of the 2B model

| Benefit | 2B (best run) | 4B (best run) | Why it matters |
|---|---:|---:|---|
| About twice the generation speed | 10.09 tokens/s (NPU) | 4.45 tokens/s (CPU) | Answers in about 26 s instead of 63 s |
| Much faster prompt processing | 99.9 tokens/s (NPU) | 22.4 tokens/s (NPU) | RAG prompts with retrieved text start answering sooner |
| Less than half the memory | 2.7 GB (NPU) | 6.0 GB (NPU) | Room for the RAG pipeline, knowledge base and a larger context |
| Fast load | 3.6 s (NPU) | 30.1 s (NPU) | The model can be loaded on demand |
| The NPU now beats the CPU | NPU faster at both stages | CPU faster at generation | Speed and a free CPU no longer have to be traded against each other |

### Shortfalls of the 2B model

| Shortfall | 2B | 4B (CPU) | Why it matters |
|---|---:|---:|---|
| Lower accuracy | 60–70% strict | 85% | Two of the three 2B set-ups fail the 70% target |
| Worse at precise limits | Fails word counts, no-comma rules, exact formats | Passes most of them | A planner's structured output (fixed formats, limits) needs these |
| Lower loose score too | 60–75% loose | 85% | The extra failures are not near misses, unlike the 4B NPU's |
| Still not interactive at full length | About 25 s per 250-token answer | About 63 s | Needs shorter answers, or streaming, for a responsive planner |

### Recommendation

1. **Treat NPU 2B as the speed candidate and CPU 4B as the accuracy reference.** Neither alone meets both a speed target suited to a planner and the 70% accuracy target.
2. **Test the 2B models on planner-style prompts,** not only IFEval. IFEval checks strict formatting rules. A short, fixed-format planning answer may suit a 2B model better, and that is what the plug-in needs.
3. **Shorten and structure the answers.** At about 80 tokens per answer, the NPU 2B would answer in about 8 s, plus well under a second to read a typical prompt.
4. **Try a middle size or a better conversion if accuracy is too low:** Qwen3.5-4B with short answers on the CPU, or a 2B NPU model converted by the project at a higher-precision setting.
5. **Keep the clocks locked** (the `rock5t-max-clocks` service), and stream answers to the user interface.

### Questions for the team

- **Is 60–65% on IFEval acceptable** if the 2B model does well on the plug-in's own planning prompts? IFEval scores strict formatting, not planning quality.
- **What response time does the planner need?** For example, "first words in 2 s, full answer in 10 s" would point to the NPU 2B with short answers.
- **Does the plug-in need the CPU for other work while it answers?** If so, the NPU's 16% CPU use counts strongly for it.
- **Should the next test be planner prompts on NPU 2B and CPU 4B,** to compare the most likely candidates on the task itself?

## Results

### All runs (first 20 IFEval prompts, thinking off)

| Measurement | CPU 4B | NPU 4B | CPU 2B Q4_K_M | CPU 2B Q8_0 | NPU 2B |
|---|---:|---:|---:|---:|---:|
| Date | 2026-11-13 | 2026-11-22 | 2026-11-22 | 2026-11-22 | 2026-11-22 |
| Clocks | Default | Default | Max | Max | Max |
| Answers / truncated | 20 / 0 | 20 / 0 | 20 / 0 | 20 / 0 | 20 / 0 |
| IFEval prompt-level strict (%) | 85 | 70 | 65 | 70 | 60 |
| IFEval instruction-level strict (%) | 86.7 | 80.0 | 73.3 | 73.3 | 73.3 |
| IFEval prompt-level loose (%) | 85 | 85 | 75 | 70 | 60 |
| Generation speed (tokens/s) | 4.45 | 3.02 | 9.00 | 6.57 | 10.09 |
| Per-answer generation speed range (tokens/s) | 2.75–5.38 | 2.56–3.73 | 4.87–11.29 | 3.48–7.74 | 8.07–11.46 |
| Prompt processing speed (tokens/s) | 15.8 | 22.4 | 49.3 | 50.9 | 99.9 |
| Average seconds per answer | 62.6 | 91.0 | 28.6 | 40.1 | 25.6 |
| Average output tokens per answer | 253 | 263 | 245 | 248 | 251 |
| Model load time (s) | 47.0 | 30.1 | 7.0 | 25.8 | 3.6 |
| Peak server process memory (GB) | 6.95 | 5.59 | 3.67 | 4.52 | 2.56 |
| System RAM start → peak (GB) | 3.3 → 10.3 | 2.7 → 8.7 | 3.1 → 6.8 | 3.1 → 7.4 | 2.8 → 5.5 |
| System RAM increase (GB) | 7.0 | 6.0 | 3.7 | 4.3 | 2.7 |
| Server CPU use (% of all 8 cores) | 92.4 | 9.2 | 93.8 | 92.8 | 15.7 |
| SoC temperature start / average / peak (°C) | 40.9 / 58.5 / 61.0 | 56.9 / 59.5 / 61.9 | 54.3 / 64.5 / 66.5 | 58.4 / 64.9 / 66.5 | 54.4 / 59.4 / 61.9 |
| NPU temperature start / average / peak (°C) | — | 55.7 / 58.4 / 60.1 | 53.7 / 61.8 / 62.9 | 57.2 / 62.0 / 63.8 | 53.4 / 58.5 / 60.1 |
| Hottest CPU core peak (°C) | 63.8 | 63.8 | 68.4 | 69.3 | 63.8 |
| Big-core clock average (MHz, max 2304) | 2301 | 2302 | 2304 | 2304 | 2304 |
| NPU interrupts in the window (per core) | — | about 1.06 million | 0 | 0 | about 761,000 |
| Total run time for 20 answers | 20.9 min | 30.3 min | 9.6 min | 13.4 min | 8.5 min |

- **Memory:** the 2B models need about half the RAM of the 4B. The Q8_0 CPU model needs more than the Q4_K_M (4.3 against 3.7 GB), and the NPU model the least (2.7 GB).
- **CPU use and heat:** on the CPU, the 2B runs kept all cores busy and ran the fan at full speed nearly all the time, with the CPU cores up to 69 °C. That is warmer than the 4B CPU run (64 °C), because the locked clocks and the faster model keep the cores fully loaded. All runs stayed far below the 85 °C throttle point.
- **NPU temperature during the CPU runs** rose to about 63 °C because the whole SoC warmed up, not because the NPU was used: its interrupt count stayed at 0.

### Failed prompts

| Prompt | Instructions | CPU 4B | CPU 2B Q4 | CPU 2B Q8 | NPU 2B | Why the 2B runs failed |
|---|---|:---:|:---:|:---:|:---:|---|
| 1: 300+ word summary, no commas, 3 highlighted sections | No commas, highlights, word count | Pass | Pass | **Fail** | **Fail** | Q8: 230 words; NPU: one comma |
| 4: repeat the request, then an email with a `<<title>>` | Repeat prompt, title | Pass | Pass | Pass | **Fail** | NPU: did not repeat the request exactly |
| 7: critique in all capital letters, in 2 sections | All capitals, sections | Fail | Fail | Fail | Fail | Same as the 4B |
| 8: resume with capitalised key words | Capital-word frequency | Fail | Fail | Fail | Fail | Same as the 4B |
| 10: 500+ word email, given keywords, no commas | Keywords, word count, no commas | Pass | **Fail** | **Fail** | **Fail** | CPU: under 500 words with commas; NPU: commas |
| 15: blog post under 300 words | Word count | Pass | **Fail** | **Fail** | **Fail** | 304, 336 and 347 words |
| 17: two names for God, separated by `******` | Two responses | Pass | **Fail** | Pass | Pass | Q4: did not follow the separator format |
| 18: two jokes, no commas, separated by `******` | No commas, two responses | Pass | **Fail** | Pass | **Fail** | Q4: commas; NPU: separator format |
| 20: tweet with no capital letters | Letter frequency | Fail | Fail | Fail | Fail | Same as the 4B |

- **The 2B models failed every prompt the 4B CPU failed (7, 8, 20),** plus 3–5 more each.
- **The extra failures are mostly precise limits:** word counts (prompts 1, 10, 15), no-comma rules (1, 10, 18) and exact formats (4, 17, 18). Some miss by a little (304 words against a 300 limit); others miss by a lot (230 words against a 300 minimum).
- **Instruction-level accuracy is the same for all three 2B runs (73.3%).** They pass the same share of individual instructions, but fail on different prompts.
- **Answers differ between runtimes and quantizations.** Only 1 of 20 answers is the same for CPU Q4_K_M and NPU, 0 for CPU Q8_0 and NPU, and 1 for Q4_K_M and Q8_0. That is expected with different weights.

### Speed

- **Model size is the main lever.** Halving the model roughly doubled generation speed on both the CPU (4.45 → 9.00 tokens/s) and the NPU (3.02 → 10.09 tokens/s). Generation on this board is limited by how fast the weights can be read from memory, so a smaller model is faster in proportion.
- **The NPU gains more than the CPU.** The NPU went from slower than the CPU (4B) to faster than it (2B). Its prompt processing (99.9 tokens/s) is twice the CPU's and 4.5× the 4B NPU's.
- **8-bit is slower than 4-bit on the CPU.** Q8_0 (2.0 GB of weights) generated at 6.57 tokens/s against 9.00 for Q4_K_M (1.3 GB). The NPU only supports 8-bit (w8a8) on the RK3588 and was still the fastest.
- **Clock locking** adds about 6% to generation and 12% to prompt processing (measured on the CPU with the 4B model). The 4B baselines used default clocks, so about 6% of the 4B-to-2B gain comes from the clocks.
- **Repeat runs** were slightly faster: CPU Q4_K_M 9.15 tokens/s, NPU 11.65 tokens/s (5 prompts each).

### Thermal and fan behaviour

| | CPU 4B | NPU 4B | CPU 2B Q4 | CPU 2B Q4 repeat | CPU 2B Q8 | NPU 2B | NPU 2B repeat |
|---|---:|---:|---:|---:|---:|---:|---:|
| SoC peak (°C) | 61.0 | 61.9 | 66.5 | 66.5 | 66.5 | 61.9 | 61.9 |
| NPU peak (°C) | — | 60.1 | 62.9 | 63.8 | 63.8 | 60.1 | 60.1 |
| Fan at full speed (PWM 255) | 53% | 10% | 99% | 96% | 97% | 25% | 25% |
| Fan at a lower step (PWM 64–192) | 24% | 42% | 0% | 1% | 0% | 33% | 48% |
| Fan off (PWM 0) | 23% | 48% | 1% | 2% | 3% | 42% | 27% |

- **The CPU runs worked the fan hardest:** it ran at full speed almost all the time, with the SoC at 64–67 °C.
- **The NPU 2B run stayed cool:** the fan was off or on a low step three quarters of the time, and the SoC peaked at 61.9 °C, the same as the 4B NPU run.
- **No throttling in any run:** the big cores stayed at 2,304 MHz in every sample.

## V&V outcome

### Verification

| ID | Check | CPU 2B Q4_K_M | CPU 2B Q8_0 | NPU 2B | Evidence |
|---|---|:---:|:---:|:---:|---|
| V-01 | Runtime and driver versions | **Pass** | **Pass** | **Pass** | Ollama 0.40.3 (`manifest.json`); RKLLM runtime 1.3.1, rknpu driver 0.9.8, toolkit 1.3.0, platform RK3588, no driver warning (server log) |
| V-02 | Expected weights | **Pass** | **Pass** | **Pass** | Ollama IDs `1e2d21a4f03a`, `0689d44085e0`; NPU file SHA-256 `3185384c…62172`, the same as its Hugging Face hash |
| V-03 | Same harness and settings | **Pass** | **Pass** | **Pass** | lm_eval 0.4.13, greedy, seed 42, presence penalty 1.5 (the 2B Modelfile's value too), 16k context, 1,280-token limit, thinking off, limit 20; evaluator unchanged |
| V-04 | Completed without errors | **Pass** | **Pass** | **Pass** | `Results saved to ...` printed for every run; no failed requests, warnings or thinking output |
| V-05 | No truncated answers | **Pass** | **Pass** | **Pass** | 0 of 20 in every run, 0 of 5 in the repeats |
| V-06 | Resource log complete | **Pass** | **Pass** | **Pass** | 598, 818 and 536 rows; largest gap 2.0 s; no `unreachable` entries |
| V-07 | Model was actually loaded | **Pass** | **Pass** | **Pass** | System RAM +3.7, +4.3 and +2.7 GB |
| V-08 | Local only | **Pass** | **Pass** | **Pass** | Servers on `127.0.0.1:11435` (Ollama) and `127.0.0.1:11436` (NPU); offline flags set; dataset from local cache |
| V-09 | Repeatable | **Pass** | Not run | **Pass** | First 5 answers identical, word for word, in the repeat runs |
| V-10 | Ran on the intended processor | **Pass** | **Pass** | **Pass** | NPU interrupts 0 in the CPU runs; about 761,000 per core in the NPU run, NPU at 1.0 GHz, server CPU use 16% |

### Validation

The targets are the same proposals as for the 4B runs.

| ID | Measure | Proposed target | CPU 4B | CPU 2B Q4_K_M | CPU 2B Q8_0 | NPU 2B |
|---|---|---|---|---|---|---|
| VAL-01 | IFEval prompt-level strict | ≥ 70% | 85% Pass | 65% **Fail** | 70% **Pass** (on the limit) | 60% **Fail** |
| VAL-02 | Generation speed | ≥ 3 tokens/s | 4.45 Pass | 9.00 **Pass** | 6.57 **Pass** | 10.09 **Pass** |
| VAL-03 | Seconds per answer | Report | 62.6 s | 28.6 s | 40.1 s | 25.6 s |
| VAL-04 | Peak model memory | ≤ 8 GB | 7.0 GB Pass | 3.7 GB **Pass** | 4.3 GB **Pass** | 2.7 GB **Pass** |
| VAL-05 | Thermal | SoC < 85 °C, no sustained throttling | 61.0 °C Pass | 66.5 °C **Pass** | 66.5 °C **Pass** | 61.9 °C **Pass** |
| VAL-06 | Offline operation | No network needed | Pass | **Pass** | **Pass** | **Pass** |
| VAL-07 | Answers against other runs | Report | — | 1 of 20 same as NPU 2B | 0 of 20 same as NPU 2B | 1 of 20 same as CPU 2B Q4 |

## Setup notes

- **Same evaluator and procedure as the earlier runs.** `evaluate_ollama.py` ran unchanged against Ollama (CPU) and against `rkllm_server.py` (NPU), with the same monitor, analysis and fan log.
- **Clocks locked at maximum** for all runs by the `rock5t-max-clocks` boot service. The session log records CPU `performance`, memory 2,400 MHz and NPU 1.0 GHz at the start.
- **CPU model choice.** Ollama's default `qwen3.5:2b` tag is Q8_0. The main CPU run used `qwen3.5:2b-q4_K_M` so that, against the 4B CPU run, only the model size changes. The Q8_0 run was added because it matches the NPU's 8-bit format.
- **NPU model.** `Qengineering/Qwen3.5-2B-rk3588` at revision `52d292f0`, downloaded to the board. Runtime settings as for the 4B NPU run: context 16,384, `embed_flash` on, inference threads on CPU 4–7, greedy (`top_k 1`), presence penalty 1.5, thinking off.
- **VS Code renderer.** As in the 4B NPU run, the VS Code window's rendering process was moved to the little cores (CPU 0–3) for the NPU runs, and moved back afterwards.
- **NPU model download during the CPU runs.** The NPU model file (3 GB) was still downloading during the CPU Q4_K_M runs, at about 1 MB/s. The file's hash check then ran during prompts 9 and 10 of the CPU Q8_0 run and was stopped. Prompt 9 ran at 4.17 tokens/s against 5.6–7.1 for most others, so the Q8_0 average (6.57 tokens/s) is slightly low. The NPU runs started after the download had finished and its hash had been checked.
- **Ollama was stopped** before the NPU runs, so it held no memory during them.
- **Desktop running** (KDE, VS Code over remote desktop) and an idle Ollama container (`local-ai-ollama`), as in the earlier runs.
- **No energy data.** The board has no battery, and its USB-C power-delivery sensor reads 0 V / 0 A.

## Next steps

1. **Test planner-style prompts** on the NPU 2B and the CPU 4B: short, structured courses of action with fixed fields. Score them for correctness and format, not only IFEval.
2. **Measure short-answer timing:** an 80-token answer limit and streamed output, to see the time to first word and to a full answer.
3. **Try Qwen3.5-0.8B on the NPU** (Rockchip lists about 21.6 tokens/s) as a speed ceiling, with the same accuracy check.
4. **Convert a 2B model ourselves** (x86 PC) to remove the dependence on a third-party conversion, and to compare conversion settings for accuracy.
5. **Run the 100-prompt IFEval screen** on the shortlisted options. 20 prompts only give about ±18 points, so the 60–70% scores are rough.

## Raw data

On the board, in `~/is2-local-ai/benchmark_results/` (gitignored):

| Run | Folder | Resource log | Console log |
|---|---|---|---|
| CPU 2B Q4_K_M, 20 prompts | `20261123T032938573369Z` | `resources_20261123T032934Z.csv` | `cpu2b_q4_20.log` |
| CPU 2B Q4_K_M, 5-prompt repeat | `20261123T033935519748Z` | `resources_20261123T033934Z.csv` | `cpu2b_q4_5_repeat.log` |
| CPU 2B Q8_0, 20 prompts | `20261123T034239142784Z` | `resources_20261123T034238Z.csv` | `cpu2b_q8_20.log` |
| NPU 2B, 20 prompts | `20261123T040044033274Z` | `resources_20261123T040041Z.csv` | `npu2b_20.log` |
| NPU 2B, 5-prompt repeat | `20261123T040939141146Z` | `resources_20261123T040938Z.csv` | `npu2b_5_repeat.log` |
| Fan log (all runs) | — | `fan_20261123T032734Z.csv` | — |
| NPU server log | — | — | `npu2b_server.log` |

Folder names use UTC, so they are dated 2026-11-23 although the runs were on the evening of 2026-11-22 local time. Each run folder holds `manifest.json`, `analysis.json` and, per model, `results.json` and `requests.jsonl`. The NPU model file is in `~/rkllm/models/`.
