# Rock 5T Local NPU Results with Fan: Qwen3.5 4B

Results of the NPU V&V run defined in [model-vnv-npu.md](model-vnv-npu.md). The method follows [model-evaluation.md](model-evaluation.md). The baseline is the CPU-only run with the fan, [RockLocalCPUWithFAN.md](RockLocalCPUWithFAN.md). All board tests from here on use the fan.

**Date:** 2026-11-22
**Board:** Radxa ROCK 5T (RK3588, 4× A76 at 2.3 GHz + 4× A55 at 1.8 GHz, 3-core 6 TOPS NPU at 1.0 GHz, 12 GB RAM), heatsink with PWM fan (`pwmfan`)
**Model:** Qwen3.5-4B, RKLLM w8a8 build `qwen3.5-4b_w8a8_rk3588.rkllm` (Q-engineering conversion, RKLLM toolkit 1.3.0), thinking off
**Runtime:** RKLLM runtime 1.3.1 on the NPU, rknpu driver 0.9.8, through `models/rkllm_server.py` (Ollama-compatible)
**Test:** the first 20 IFEval prompts (the same prompts as the CPU runs), then a repeat of the first 5. An extra 20-prompt run without the presence penalty shows what that setting costs. Same evaluator, settings and fan log as the CPU-with-fan run.

## Summary

- **The model runs on the NPU, entirely on the board.** All three NPU cores handled about 1.06 million interrupts each during the run. The runtime reported `platform: RK3588, npu_core_num: 3`. The server process used only 9% of the CPU, against 92% for Ollama.
- **Generation is slower than on the CPU.** It averaged 3.02 tokens/s, against 4.45 on the CPU, which only just passes the 3 tokens/s target. Without the presence penalty it was 3.52 tokens/s. Rockchip's published 6.2 tokens/s for this model was not reached on this board with the desktop running.
- **Prompt processing is faster.** It ran at 22.4 tokens/s, against 15.8 on the CPU (1.4×). This matters for RAG prompts, which carry retrieved text.
- **Accuracy is lower but still passes.** 14 of 20 prompts passed (70%), against 17 of 20 (85%) on the CPU. That is exactly on the 70% target. All three prompts that failed on the CPU also failed on the NPU. The three new failures were near misses. With IFEval's loose scoring, the NPU scores 85%, the same as the CPU.
- **Less memory and cooler running.** Peak model memory was 5.59 GB (against 6.95 GB). The SoC peaked at 61.9 °C and the NPU at 60.1 °C. The fan ran at full speed only 10% of the time, against 53% on the CPU.
- **The board passes every V&V check,** but speed and accuracy only just pass. The CPU remains the faster option for generation. The NPU's advantages are prompt processing, free CPU and lower memory.

## Results

### NPU compared with the CPU-with-fan run (first 20 IFEval prompts, thinking off)

| Measurement | CPU with fan (2026-11-13) | NPU (this run) | NPU, no presence penalty |
|---|---:|---:|---:|
| IFEval prompt-level strict (%) | 85 | 70 | 70 |
| IFEval instruction-level strict (%) | 86.7 | 80.0 | 80.0 |
| IFEval prompt-level loose (%) | 85 | 85 | 80 |
| Generation speed (tokens/s) | 4.45 | 3.02 | 3.52 |
| Prompt processing speed (tokens/s) | 15.8 | 22.4 | 24.7 |
| Average seconds per answer | 62.6 | 91.0 | 77.4 |
| Average output tokens per answer | 253 | 263 | 260 |
| Model load time (s) | 47.0 | 30.1 | 30.4 |
| Peak model (server process) memory (GB) | 6.95 | 5.59 | 5.57 |
| Peak system RAM (GB) | 10.3 of 12 | 8.7 of 12 | 8.6 of 12 |
| System RAM increase (GB) | 7.0 | 6.0 | 5.7 |
| Server CPU use (% of all 8 cores) | 92.4 | 9.2 | 8.9 |
| SoC temperature start / average / peak (°C) | 40.9 / 58.5 / 61.0 | 56.9 / 59.5 / 61.9 | 58.6 / 59.5 / 61.9 |
| NPU temperature start / average / peak (°C) | — | 55.7 / 58.4 / 60.1 | 57.2 / 58.4 / 60.1 |
| Hottest CPU core peak (°C) | 63.8 | 63.8 | 63.8 |
| Time at or above 85 °C | 0% | 0% | 0% |
| Big-core clock average (MHz, max 2304) | 2301 | 2302 | 2281 |
| Time with big cores below max clock | 0.2% | 0.1% | 1.4% |
| NPU clock average (MHz, max 1000) | — | 1000 | 1000 |
| Total run time for 20 answers | 20.9 min | 30.3 min | 25.8 min |

- The **SoC start temperature** is higher than in the CPU run (56.9 against 40.9 °C) because the board had just run the NPU smoke tests. The CPU run started soon after a reboot. The peaks are almost the same.
- The NPU has its own temperature sensor (`npu-thermal`), logged every second alongside the SoC and CPU sensors. It stayed about 25 °C below the 85 °C throttle point.
- **Memory** is the server process's RSS, as for Ollama in the CPU run. RKLLM's own peak figure (VmHWM) agrees: 5.3 GB.
- **CPU use** is the share of all 8 cores. Ollama kept nearly all of them busy. RKLLM used less than one core on average, leaving the CPU free for the RAG pipeline and the rest of the plug-in.

### Failed prompts

| Prompt | Instructions | CPU | NPU | Why the NPU failed |
|---|---|:---:|:---:|---|
| 4: repeat the request, then an email with a `<<title>>` | Repeat prompt, title | Pass | **Fail** | Wrote "i. e." for "i.e." and repeated a sentence it was told to leave out |
| 7: critique in all capital letters, in 2 sections | All capitals, multiple sections | Fail | Fail | Same as CPU. The NPU passed the sections instruction, which the CPU failed |
| 8: resume with capitalised key words | Capital-word frequency | Fail | Fail | Same as CPU |
| 14: film review in all lower case | Lower case | Pass | **Fail** | One capital letter ("Eisenberg") in a long answer that also mixed up facts |
| 15: blog post under 300 words | Word count | Pass | **Fail** | 299 words by a plain count, but just over 300 by IFEval's word counter |
| 20: tweet with no capital letters | Letter frequency | Fail | Fail | Same as CPU |

Prompts 14 and 15 pass under IFEval's loose scoring, which is why the loose score is 85% for both runtimes. In the no-penalty run, prompt 7 failed and prompt 12 (a paragraph count) failed instead, so the score stayed at 70%.

Only 2 of the 20 answers (prompts 17 and 19) are word for word the same as the CPU's. That is expected: the NPU model has different weights (8-bit w8a8 against Q4_K_M), and it runs on a different runtime with its own chat template. The answers are similar in length (263 tokens on average, against 253).

### Speed

- Per-answer generation speed ranged from 2.56 to 3.73 tokens/s, and from 2.86 to 3.95 tokens/s without the presence penalty.
- **The presence penalty costs about 15%** (3.02 against 3.52 tokens/s). RKLLM applies it on the CPU for every token. The CPU run used the same penalty (1.5, the model's Ollama default), so the main run keeps it for a like-for-like test.
- **Desktop load matters more on the NPU than on the CPU.** RKLLM still does part of each token on the 4 big cores. In smoke tests before the run, the VS Code window's renderer (busy redrawing over the remote desktop session) took one big core, and generation dropped to 1.3 tokens/s. For the run, that one process was moved to the little cores (see setup notes). The KDE desktop, VS Code and the remote desktop session otherwise stayed open, as in the CPU runs.
- **Below Rockchip's figure.** Rockchip lists 6.22 tokens/s for Qwen3.5-4B w8a8 on the RK3588. Its benchmark used a 128-token prompt, only 64 output tokens, and all clocks fixed at maximum, with nothing else running. Here the CPU and NPU clocks were already at maximum, the memory clock rose to its 2,400 MHz maximum during generation, and there was no swapping or disk activity. The most likely remaining causes are the open desktop and the longer answers (about 260 tokens), but this is not confirmed. A run with the desktop closed would show it (next steps).

### Thermal and fan behaviour

| | CPU with fan | NPU (20 prompts) | NPU repeat (5 prompts) | NPU, no penalty |
|---|---:|---:|---:|---:|
| SoC peak (°C) | 61.0 | 61.9 | 61.0 | 61.9 |
| NPU peak (°C) | — | 60.1 | 60.1 | 60.1 |
| Fan at full speed (PWM 255) | 53% | 10% | 8% | 11% |
| Fan at a lower step (PWM 64–192) | 24% | 42% | 43% | 35% |
| Fan off (PWM 0) | 23% | 48% | 49% | 54% |

- The NPU run produces less heat than the CPU run. The fan spent about half the time off and reached full speed only 10% of the time, against 53% with the CPU doing the work.
- The few clock dips (2 samples in the main run) are governor changes, not throttling: the SoC stayed below 62 °C.

## V&V outcome

### Verification

| ID | Check | Result | Evidence |
|---|---|---|---|
| V-01 | Runtime and driver versions | **Pass** | RKLLM runtime 1.3.1, rknpu driver 0.9.8, platform RK3588 (server log and `manifest.json`); no driver-version warning |
| V-02 | Expected weights | **Pass** | SHA-256 `31ebf6a0…14b8ca` in `manifest.json`, the same as the file's Hugging Face hash. Runtime library SHA-256 `f25e9b09…eb32c` |
| V-03 | Same harness and settings | **Pass** | lm_eval 0.4.13, greedy (top_k 1), presence penalty 1.5, 16k context, 1,280-token limit, thinking off, limit 20. Evaluator unchanged from the CPU run |
| V-04 | Completed without errors | **Pass** | `Results saved to ...` printed for all three runs; no failed requests, warnings or thinking output |
| V-05 | No truncated answers | **Pass** | 0 of 20, 0 of 5, and 0 of 20 |
| V-06 | Resource log complete | **Pass** | 1,850 rows, largest gap 2.0 s, no `unreachable` entries |
| V-07 | Model was actually loaded | **Pass** | System RAM 2.7 → 8.7 GB (+6.0 GB); server process 0.03 → 5.59 GB |
| V-08 | Local only | **Pass** | Server at `127.0.0.1:11436`; `HF_HUB_OFFLINE=1` and `HF_DATASETS_OFFLINE=1`; model and dataset read from disk |
| V-09 | Repeatable | **Pass** | First 5 answers identical, word for word, in the repeat run |
| V-10 | Inference ran on the NPU | **Pass** | Interrupts in the window: core 0 1,061,803, core 1 1,061,435, core 2 1,061,435 (0 before the first load); runtime log `npu_core_num: 3, target_platform: RK3588`; server CPU use 9% |

### Validation

The targets are proposals, because the project has no requirements document yet.

| ID | Measure | Proposed target | CPU with fan | NPU | Verdict |
|---|---|---|---|---|---|
| VAL-01 | IFEval prompt-level strict | ≥ 70% | 85% | 70% (85% loose) | **Pass** (on the limit) |
| VAL-02 | Generation speed | ≥ 3 tokens/s | 4.45 | 3.02 (3.28 in the repeat, 3.52 without the penalty) | **Pass** (on the limit) |
| VAL-03 | Seconds per answer | Report | 62.6 s | 91.0 s | Recorded |
| VAL-04 | Peak model memory | ≤ 8 GB | 6.95 GB | 5.59 GB | **Pass** |
| VAL-05 | Thermal | SoC < 85 °C, no sustained throttling | 61.0 °C | 61.9 °C (NPU 60.1 °C); full clock 99.9% | **Pass** |
| VAL-06 | Offline operation | No network needed | Ran offline | Ran offline | **Pass** |
| VAL-07 | Answers against the CPU run | Report | — | 2 of 20 identical; the 3 CPU failures also fail; 3 new near-miss failures | Recorded |

## Setup notes

- **Same evaluator and procedure as the CPU runs.** `rkllm_server.py` answers the Ollama API calls the evaluator uses, so `evaluate_ollama.py` ran unchanged. The commands are in [model-vnv-npu.md](model-vnv-npu.md#procedure).
- **Model file:** `Qengineering/Qwen3.5-4B-rk3588` at revision `ee09c44b`, downloaded straight to the board. Rockchip's conversion tool runs only on x86_64 PCs, so a published conversion was used to keep the test on the board.
- **Runtime settings:** context 16,384, `embed_flash` on, inference threads on the 4 big cores (CPU 4–7), greedy (`top_k 1`), presence penalty 1.5, repeat penalty 1.0, thinking off. In the smoke tests, `embed_flash` on was faster than off.
- **VS Code renderer moved to the little cores.** For the run, the VS Code window's `gpu-process` was moved to CPU 0–3 (`taskset`), so it would not take a big core from RKLLM. The CPU runs did not need this, because Ollama spread its work over all 8 cores. The change resets when VS Code restarts.
- **NPU logging added to the monitor:** NPU and GPU temperature, NPU clock, and per-core NPU interrupt counts. The kernel's NPU "load" figure reads 100% all the time on this board, so it is logged but not used.
- **RKLLM warnings.** The server log shows "KV cache reuse failed … Cache cleared" before most prompts. RKLLM tries to reuse the previous prompt's cache, finds that the prompts differ, and starts fresh. No answer carries anything over from the previous one, which the identical repeat answers confirm.
- **The Ollama server on port 11434** (root, 0.40.16) stayed running and idle, with no model loaded.
- **No energy data.** The board has no battery, and its USB-C power-delivery sensor reads 0 V / 0 A.

## Next steps

1. **Run once with the desktop closed** (or over SSH only), for both the NPU and the CPU, to find out how much of the gap to Rockchip's 6.2 tokens/s is caused by desktop load.
2. **Add a USB-C power meter.** The NPU's lower CPU use and fan duty suggest it uses less energy per answer, even though it is slower. Only a measurement can confirm that.
3. **Measure time to first word with RAG-sized prompts** (1,000–4,000 tokens). The NPU's faster prompt processing should matter most there.
4. **Try a smaller model on the NPU** (Qwen3.5-2B, about 13.6 tokens/s in Rockchip's figures) and check its accuracy on the same 20 prompts.
5. **Convert the model ourselves** on an x86 PC (w8a8, and w4a16 for speed) and rerun, to remove the dependence on a third-party conversion.

## Raw data

On the board, in `~/is2-local-ai/benchmark_results/` (gitignored):

| Run | Folder | Resource log | Console log |
|---|---|---|---|
| 20 prompts | `20261122T203442907099Z` | `resources_20261122T203438Z.csv` | `npu_20.log` |
| 5-prompt repeat | `20261122T210532261697Z` | `resources_20261122T210529Z.csv` | `npu_5_repeat.log` |
| 20 prompts, no presence penalty | `20261122T211307571923Z` | `resources_20261122T211305Z.csv` | `npu_20_pp0.log` |
| Fan log (all runs) | — | `fan_20261122T203236Z.csv` | — |
| Server logs | — | — | `npu_server.log` (penalty 1.5), `npu_server_pp0.log` (penalty 0) |

Folder names use UTC; the runs were on the afternoon of 2026-11-22 local time. Each run folder holds `manifest.json`, `analysis.json` and, per model, `results.json` and `requests.jsonl`. The model file and runtime are in `~/rkllm/`.
