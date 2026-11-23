# Rock 5T NPU Results with RAG: Qwen3.5 2B

Results of running the project's RAG pipeline ([software/rag](../../software/rag/README.md)) on the Rock 5T with Qwen3.5-2B on the NPU, with all clocks locked at maximum, over the project's doctrine corpus ([docs/sources](../sources/README.md)). The test repeats the CPU RAG test ([CPU-Qwen2B-Rag.md](CPU-Qwen2B-Rag.md)) exactly: the same corpus and index, the same 20 questions and answer key, RAG and baseline modes, and a repeat of Q01–Q05. Only the model server changes: the NPU model runs in RKLLM through `models/rkllm_server.py` instead of Ollama. The model-only NPU results are in [CPU-NPU_Qwen3.5_2B_maxcoresspeed.md](CPU-NPU_Qwen3.5_2B_maxcoresspeed.md).

**Date:** 2026-11-23
**Board:** Radxa ROCK 5T (RK3588, 3-core 6 TOPS NPU at 1.0 GHz, 12 GB RAM), heatsink with PWM fan (`pwmfan`)
**Clocks:** locked at maximum by the `rock5t-max-clocks` boot service ([hardware/processing_unit/rock5t](../../hardware/processing_unit/rock5t/README.md))
**Model:** `qwen3.5-2b_w8a8_rk3588.rkllm` (w8a8, Q-engineering conversion, RKLLM toolkit 1.3.0, SHA-256 `3185384c…`), the same file as the NPU 2B run
**Runtime:** RKLLM runtime 1.3.1, rknpu driver 0.9.8, through `models/rkllm_server.py` (`127.0.0.1:11436`). Greedy (`top_k 1`), presence penalty 1.5, context 4,096 tokens (to match the pipeline), answers limited to 512 tokens, thinking off, inference threads on the big cores (CPU 4–7)
**RAG pipeline:** as in the CPU test: `software/rag/rag.py` in the `is2-local-ai-rag` Docker image (ID `703bbd2a…`), embedding model `BAAI/bge-small-en-v1.5`, top 5 passages, the same 4,473-chunk index (manifest SHA-256 `dc5b9553…`)
**Test:** 20 questions ([software/rag/eval/doctrine_questions.json](../../software/rag/eval/doctrine_questions.json)): 17 answerable from the documents and 3 not answerable. Each was asked in RAG and baseline mode, then Q01–Q05 again in RAG mode as a repeat

## Summary

- **The NPU scores the same as the CPU: 17 of 20 right with RAG (85%).** It answered 14 of the 17 answerable questions correctly and said "not in the documents" for all 3 unanswerable ones. It missed the same 3 questions as the CPU, because retrieval supplied the same passages to both.
- **Without RAG, it got none right,** and invented figures for all 3 unanswerable questions, as on the CPU.
- **The NPU is about 26% faster per RAG answer:** 53 s against 72 s on the CPU. It reads the 1,700-token prompt in 12 s instead of 32 s (148 against 52 tokens/s) and writes at 12.2 tokens/s instead of 10.4.
- **It leaves the CPU almost free and runs cooler:** 14% CPU use against 76%, system RAM +2.8 GB against +5.6 GB, and the fan was off half the time.
- **One serious unsupported claim (Q03):** with only index pages retrieved, the NPU model invented five "paragraphs" from the index entries. The CPU model said the evidence was insufficient for the same question. On the other hand, for Q16 the NPU correctly said the evidence was insufficient without adding an invented answer, where the CPU did not.
- **4 RAG answers ran to the 512-token limit** (Q02, Q03, Q10, Q12). The NPU model writes longer answers (375 tokens on average, against 304 on the CPU). In three of them the correct answer came before the cut.
- **Two server changes were needed** for the RAG pipeline: support for its system message, and the empty "thinking off" block (see Setup notes). A check before the run caught the second.

## NPU compared with the CPU (RAG)

### Side by side

| Measurement | CPU 2B RAG | NPU 2B RAG | Better |
|---|---:|---:|---|
| Correct answers (of 20) | 17 (85%) | 17 (85%) | Even |
| Correct answers to answerable questions (of 17) | 14 | 14 | Even |
| Proper "not in the documents" (of 3) | 3 | 3 | Even |
| Evidence hit rate@5 | 14 of 17 | 14 of 17 (same passages) | Even |
| Serious unsupported claims | 1 (Q16) | 1 (Q03) | Even |
| Answers cut off at the 512-token limit | 0 | 4 | CPU |
| Average output tokens | 304 | 375 | CPU (shorter) |
| Average prompt tokens (server's count) | 1,690 | 1,771 | — |
| Prompt processing (tokens/s) | 52.5 | **148.3** | **NPU** |
| Average prompt-reading time (s) | 32.2 | **11.9** | **NPU** |
| Generation speed (tokens/s) | 10.44 | **12.19** | **NPU** |
| Average model time per answer (s) | 61.7 | **43.0** | **NPU** |
| Average total time per question (s) | 72.1 | **53.3** | **NPU** |
| Model load (first question, s) | 6.1 | **3.0** | **NPU** |
| Server CPU use (% of all 8 cores) | 76 | **14** | **NPU** |
| System RAM increase (GB) | 5.6 | **2.8** | **NPU** |
| SoC peak temperature (°C) | 66.5 | **63.8** | **NPU** |
| Fan at full speed (% of the time) | 77 | **28** | **NPU** |
| Total run time (45 requests, min) | 41.2 | **36.1** | **NPU** |

- **Quality is a tie.** Both servers got the same 17 questions right, from the same evidence. Each made one serious unsupported claim, on a question where retrieval had failed.
- **The NPU is faster where RAG needs it most.** RAG prompts are long, and the NPU reads them 2.8 times as fast as the CPU. That is the biggest single saving (about 20 s per answer).
- **The NPU writes longer answers,** so some of its speed advantage is spent on extra words. Its answers are about 23% longer and 4 ran into the token limit.
- **None of the 40 main-pass answers is word for word the same** between CPU and NPU. That is expected: they are different conversions of the model (Q4_K_M against w8a8) on different hardware.

### RAG against baseline on the NPU

| Measurement | NPU RAG | NPU baseline (no documents) |
|---|---:|---:|
| Correct answers (of 20) | **17 (85%)** | 0 (1 partly right) |
| Invented figures on unanswerable questions (of 3) | **0** | 3 |
| Average total time per question (s) | 53.3 | 34.7 |
| Average output tokens | 375 | 323 |

The baseline answers made the same kinds of mistakes as on the CPU: military terms read as cybersecurity (Q07, Q08), physics (Q13), business (Q06, Q17) or video games (Q15), with invented expansions for METT-TC and SINCGARS and invented figures for the Abrams, the budget and the Bradley.

## Results

### Answers scored (main pass)

| Question | RAG correct? | Evidence in top 5? | RAG notes | Baseline correct? | RAG total (s) | Baseline total (s) |
|---|:---:|:---:|---|:---:|---:|---:|
| Q01 MDMP steps | **Yes** | Yes | All 7 steps with short descriptions | No | 46.4 | 44.7 |
| Q02 TLP steps | **Yes** | Yes | All 8 steps; cut off at the limit in a later note | No | 73.2 | 48.8 |
| Q03 OPORD paragraphs | No | **No** | **Invented five "paragraphs" from index entries**; cut off | No | 66.6 | 45.5 |
| Q04 One-third, two-thirds rule | No | **No** | Said the rule is not in the documents, then speculated how it "might be derived" | No | 61.0 | 49.0 |
| Q05 Valid COA criteria | **Yes** | Yes | | No | 57.8 | 45.8 |
| Q06 Operations process | **Yes** | Yes | | No | 62.8 | 49.1 |
| Q07 Types of security operations | **Yes** | Yes | | No | 34.4 | 28.2 |
| Q08 Purpose of security operations | **Yes** | Yes | | No | 62.3 | 29.1 |
| Q09 Principles of mission command | **Yes** | Yes | All 7 | No | 47.3 | 38.0 |
| Q10 METT-TC | **Yes** | Yes | Listed terrain and weather separately at first, then corrected; cut off | No | 65.1 | 21.6 |
| Q11 PMESII-PT | **Yes** | Yes | All 8 variables | No | 58.8 | 47.5 |
| Q12 CCIR | **Yes** | Yes | Definition quoted; cut off later | No | 64.3 | 38.6 |
| Q13 Center of gravity | **Yes** | Yes | Gave both wordings, without naming the editions | No | 49.4 | 27.4 |
| Q14 Commander's intent | **Yes** | Yes | 2018 wording, with a phrase from the 2004 wording mixed in | Partly | 59.7 | 22.6 |
| Q15 Battle rhythm | **Yes** | Yes | Also answered a question that was not asked (battle rhythm against tempo) | No | 45.2 | 32.7 |
| Q16 SINCGARS | No | **No** | Said the acronym is not in the supplied text; nothing invented | No | 40.7 | 14.9 |
| Q17 Decisive point | **Yes** | Yes | | No | 54.7 | 35.8 |
| Q18 Abrams main gun range (not in documents) | **Yes** | — | Said not in the documents | No (invented) | 41.5 | 30.7 |
| Q19 Army FY2022 budget (not in documents) | **Yes** | — | Said not in the documents | No (invented) | 44.4 | 16.6 |
| Q20 Bradley top road speed (not in documents) | **Yes** | — | Said not in the documents | No (invented) | 30.8 | 26.8 |

Retrieval does not depend on the model server, so every question received exactly the same 5 passages as in the CPU test. The 3 retrieval misses (Q03, Q04, Q16) are described in [CPU-Qwen2B-Rag.md](CPU-Qwen2B-Rag.md#answers-scored-main-pass).

### Speed (RAG main pass, 20 questions)

| Measurement | NPU | CPU |
|---|---:|---:|
| Prompt tokens (server's count) | 1,260–2,589 (average 1,771) | 1,195–2,511 (average 1,690) |
| Prompt processing | 148.3 tokens/s (11.9 s) | 52.5 tokens/s (32.2 s) |
| Output tokens | average 375 | average 304 |
| Generation speed | 12.19 tokens/s (range 11.46–12.56) | 10.44 tokens/s (range 6.65–11.28) |
| Model time per answer | 43.0 s | 61.7 s |
| Retrieval-model load per question | 10.2 s | 10.2 s |
| Retrieval | 0.11 s | 0.12 s |
| Total time per question | 53.3 s (range 31–73 s) | 72.1 s (range 44–90 s) |

- **The NPU's generation speed is very steady** (11.5–12.6 tokens/s), as in the model-only NPU run.
- **Generation is faster than in the model-only NPU run** (12.2 against 10.1 tokens/s), because the context is 4,096 instead of 16,384 tokens.
- **The repeat answers were read at full cost** (151 tokens/s): unlike Ollama, the NPU server does not cache prompts, so its repeat timings match the main pass.

### Resources

| Measurement | NPU | CPU |
|---|---:|---:|
| Peak server process memory | 2.41 GB | 5.27 GB |
| System RAM start → peak | 3.4 → 6.2 GB (increase 2.8 GB) | 3.3 → 8.9 GB (increase 5.6 GB) |
| Server CPU use (% of all 8 cores) | 14% | 76% |
| Whole-system CPU use | 21% | 81% |
| NPU interrupts in the window (per core) | about 2.55 million | 0 |
| NPU clock | 1,000 MHz in every sample | — |

### Thermal and fan behaviour

| | NPU RAG run | CPU RAG run |
|---|---:|---:|
| SoC start / average / peak (°C) | 54.5 / 59.4 / 63.8 | 52.7 / 63.5 / 66.5 |
| NPU start / average / peak (°C) | 52.7 / 58.4 / 61.9 | 51.8 / 61.0 / 63.8 |
| Hottest CPU core peak (°C) | 66.5 | 69.3 |
| GPU peak (°C) | 61.0 | 61.9 |
| Fan at full speed (PWM 255) | 28% | 77% |
| Fan at a lower step (PWM 64–192) | 21% | 4% |
| Fan off (PWM 0) | 51% | 19% |

- **No throttling:** the big cores stayed at 2,304 MHz and the NPU at 1,000 MHz in every sample.
- **The hottest CPU core still reached 66.5 °C,** because each question's RAG container (PyTorch, embedding model) runs on the CPU.

## V&V outcome

### Verification

| ID | Check | Result | Evidence |
|---|---|:---:|---|
| V-01 | Runtime and driver versions | **Pass** | RKLLM runtime 1.3.1, rknpu driver 0.9.8, toolkit 1.3.0, platform RK3588, w8a8 (server log); `rkllm-1.3.1` in every log record; RAG image ID `703bbd2a…` |
| V-02 | Expected weights | **Pass** | Model file SHA-256 `3185384c…` in every log record, the same as the NPU 2B run |
| V-03 | Same settings as the CPU test | **Pass** | Same questions, index (`dc5b9553…`), k = 5, 512-token limit, greedy, seed 42, thinking off; context 4,096 on both |
| V-04 | Completed without errors | **Pass** | All 45 requests answered; no failed requests, invalid citation IDs or thinking output |
| V-05 | Truncated answers | **Fail (4 RAG)** | Q02, Q03, Q10 and Q12 RAG answers (and Q02, Q03 in the repeat) stopped at 511 tokens. The server reported them as `stop` rather than `length`; this is fixed (see Setup notes). 3 baseline answers were cut off too |
| V-06 | Resource log complete | **Pass** | 2,168 rows; largest gap 2.0 s; no `unreachable` entries |
| V-07 | Model was actually loaded | **Pass** | Server process up to 2.4 GB; system RAM +2.8 GB |
| V-08 | Local only | **Pass** | Server on `127.0.0.1:11436`; the pipeline forces Hugging Face offline mode and loads local files only |
| V-09 | Repeatable | **Pass** | Q01–Q05 RAG answers identical, word for word, in the repeat |
| V-10 | Ran on the intended processor | **Pass** | About 2.55 million interrupts per NPU core; NPU at 1.0 GHz; server CPU use 14% |
| V-11 | Prompt budget measured correctly | **Pass, with a known offset** | The NPU counts 2–8% more prompt tokens than the pipeline's preflight (3.1–6.8% for RAG prompts), because the RKLLM conversion's tokenizer splits some text differently from Qwen's own tokenizer. The chat layout itself matches exactly (checked with short prompts). The largest prompt plus the answer limit (3,101 tokens) stays within the 4,096-token context, and every RAG prompt kept all 5 passages |
| V-12 | Chat format checked before the run | **Pass** | A check question before the main run confirmed the system message was applied, no thinking text appeared, and the prompt fitted the context |

### Validation

| ID | Measure | Proposed target | CPU 2B RAG | NPU 2B RAG |
|---|---|---|---|---|
| RAG-01 | Correct answers to answerable questions | ≥ 80% | 14 of 17 (82%) Pass | 14 of 17 (82%) **Pass** |
| RAG-02 | Proper abstention on unanswerable questions | 3 of 3 | Pass | **Pass** |
| RAG-03 | Citations point only to supplied sources | All answers | Pass | **Pass** |
| RAG-04 | Serious unsupported claims | 0 | 1 Fail | 1 **Fail** |
| RAG-05 | RAG better than baseline | More correct, fewer invented | Pass | **Pass** |
| RAG-06 | Evidence hit rate@5 | ≥ 90% | 82% Fail | 82% **Fail** (same retrieval) |
| RAG-07 | Offline restart | Works after a disconnected restart | Not run | **Not run** |
| RAG-08 | Time per RAG answer | Report | 72 s | **53 s** |
| VAL-04 | Peak model memory | ≤ 8 GB | 5.6 GB Pass | 2.8 GB **Pass** |
| VAL-05 | Thermal | SoC < 85 °C | 66.5 °C Pass | 63.8 °C **Pass** |

## Setup notes

- **System message support added to `rkllm_server.py`.** The RAG pipeline sends a system message (answer only from the evidence, cite sources, treat documents as untrusted) and a user message. The server previously accepted only a single user message (enough for IFEval). It now applies a system message with RKLLM's `rkllm_set_chat_template` in Qwen's ChatML layout, the same layout Ollama renders. Requests without a system message still use the model's built-in template, so the IFEval runs are unaffected.
- **Empty think block.** Setting a custom chat template turns off RKLLM's own "thinking off" handling (the runtime logs a warning saying so). In the first check run the model then wrote an empty `<think></think>` block into its answer. The server now adds that empty block to the template when thinking is off, as Ollama's renderer and the built-in template do. The check before the main run caught this; the main run used the fixed server.
- **Token limit reporting fixed after the run.** When the answer limit is reached, RKLLM reports one token fewer than the limit (511 of 512), so the server reported those answers as `stop` instead of `length`, and the pipeline did not warn. The server now treats the limit minus one as reaching the limit. The truncated answers above were found by inspection.
- **Context 4,096** on the NPU server to match the pipeline (the server rejects a request whose context differs from its own), against 16,384 in the IFEval NPU run.
- **Tokenizer for the NPU tag.** The pipeline looks up a tokenizer by model name; `download_models.py` now maps `qwen3.5:2b-w8a8-npu` to `Qwen/Qwen3.5-2B`. For this run, the already-downloaded Qwen3.5-2B tokenizer (revision `15852e8c`) was copied under that name instead of downloading it again.
- **Ollama was stopped** before the NPU run, and the VS Code window's rendering process was moved to the little cores (CPU 0–3) during the run and moved back afterwards, as in the earlier NPU runs.
- **Same RAG container and index as the CPU test,** pointed at the NPU server through `OLLAMA_URL`. Retrieval was identical: all 20 questions received the same 5 passages as on the CPU.
- **No power data:** the board cannot measure its own power, and no meter was available.

## Next steps

1. **Use the NPU for RAG:** same accuracy as the CPU, 26% faster per answer, far less CPU and memory.
2. **Improve retrieval,** which caused all 3 misses on both processors (see [CPU-Qwen2B-Rag.md](CPU-Qwen2B-Rag.md#next-steps)).
3. **Shorten the NPU's answers,** for example by asking for a short, direct answer in the system prompt, or lower the answer limit for planner use. That would cut its time further and avoid the 4 cut-off answers.
4. **Tighten the system prompt** so the model does not build an answer from unrelated passages (Q03) or speculate after saying the evidence is insufficient (Q04).
5. **Keep the pipeline running as a service** to save the 10 s retrieval-model load per question; a RAG answer on the NPU would then take about 43 s, or much less with shorter answers.

## Raw data

On the board:

| Item | Location |
|---|---|
| Run log (every question, answer, supplied evidence, token counts and timings) | `software/rag/logs/doctrine_npu_runs.jsonl` |
| Answer key | `software/rag/eval/doctrine_questions.json` (in the repository) |
| Console log (answers as printed) | `~/is2-local-ai/benchmark_results/rag_doctrine_npu.log` |
| NPU server log | `~/is2-local-ai/benchmark_results/rag_npu_server.log` |
| Resource log | `~/is2-local-ai/benchmark_results/resources_20261123T212906Z.csv` |
| Fan log | `~/is2-local-ai/benchmark_results/fan_20261123T212706Z.csv` |

`software/rag/data/`, `models/` and `logs/` are gitignored.
