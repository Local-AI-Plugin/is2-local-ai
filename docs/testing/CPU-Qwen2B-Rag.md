# Rock 5T CPU Results with RAG: Qwen3.5 2B

Results of running the project's RAG pipeline ([software/rag](../../software/rag/README.md)) on the Rock 5T with Qwen3.5-2B on the CPU, with all clocks locked at maximum. The test follows the evaluation steps of the RAG tutorial ([Local_AI_Plugin_RAG_Tutorial.md](../Local_AI_Plugin_RAG_Tutorial.md), Steps 6–9): each question is asked with retrieved document evidence (RAG) and without it (baseline), and the answers are scored for correctness, citations, unsupported claims and abstention. Speed, memory and temperature were logged as in the earlier board runs. The model-only results for the same model are in [CPU-NPU_Qwen3.5_2B_maxcoresspeed.md](CPU-NPU_Qwen3.5_2B_maxcoresspeed.md).

**Date:** 2026-11-23
**Board:** Radxa ROCK 5T (RK3588, 4× A76 at 2.3 GHz + 4× A55 at 1.8 GHz, 12 GB RAM), heatsink with PWM fan (`pwmfan`)
**Clocks:** locked at maximum by the `rock5t-max-clocks` boot service ([hardware/processing_unit/rock5t](../../hardware/processing_unit/rock5t/README.md))
**Model:** `qwen3.5:2b-q4_K_M` (Q4_K_M, 1.9B parameters, Ollama ID `1e2d21a4f03a`), the same file as the CPU 2B run
**Runtime:** Ollama 0.40.3 on the CPU (`127.0.0.1:11435`). Thinking off, temperature 0, seed 42, context 4,096 tokens, answers limited to 512 tokens (the RAG pipeline's settings)
**RAG pipeline:** `software/rag/rag.py` in the `is2-local-ai-rag` Docker image (Python 3.12.10, image ID `703bbd2a…`). Embedding model `BAAI/bge-small-en-v1.5` (revision `5c38ec7c`), FAISS index, top 5 passages, chat tokenizer `Qwen/Qwen3.5-2B` (revision `15852e8c`)
**Test:** the tutorial's test document and its 4 questions (3 answerable, 1 not answerable from the document), each asked in RAG and baseline mode, then the 4 RAG questions again as a repeat

## Summary

- **With RAG, the 2B model answered all 4 questions correctly.** It gave the right answer to the 3 answerable questions, cited the document each time, and correctly said the document does not give the battery capacity.
- **Without RAG, it answered none of them correctly, and invented answers for 2.** It described "Cedar Storage" cloud servers and a chestnut moth instead of the fictional Cedar Module. For the other 2 it said it did not know. RAG is what keeps the answers tied to the documents.
- **One unsupported claim in 4 RAG answers.** In question 2 the model linked the USB-C connection to the power-cable rule, which the document does not say.
- **RAG answers are short and quick.** Generation ran at about 11.7 tokens/s, and an answer took about 8–15 s once the model was loaded. The full RAG question, including loading the retrieval model, took about 18–25 s.
- **About half of each RAG question's time is start-up, not the model.** The pipeline runs as a new process for each question and spends about 10 s loading the embedding model and tokenizer. Retrieval itself takes about 0.1 s. Kept running as a service, a RAG answer would take about 8–15 s.
- **All verification checks pass,** and the answers were identical in the repeat.
- **This is a small test.** One short document and 4 questions show that the pipeline works on the board with the 2B model. They do not measure retrieval quality: the document is a single passage, so retrieval cannot miss. A real corpus with 15–20 questions is needed for that.

## RAG compared with the model alone

### Side by side

| Measurement | RAG | Baseline (no documents) |
|---|---:|---:|
| Correct answers (of 4) | **4** | 0 |
| Correct answers to answerable questions (of 3) | **3** | 0 |
| Invented answers (of 4) | **0** | 2 |
| Proper "not known" on the unanswerable question | **Yes** | Yes (asked for more details) |
| Answers citing a supplied source | **4 of 4** | — |
| Unsupported claims | 1 | 2 answers made up entirely |
| Average output tokens per answer | **76** | 241 |
| Generation speed (tokens/s) | 11.8 | 11.8 |
| Average model time per answer (s) | **11.4** | 21.5 |
| Average total time per question, including start-up (s) | **21.7** | 30.3 |
| Prompt tokens | 182–186 | 44–48 |

- **RAG makes answers shorter and faster.** The document gives the model a clear answer, so it writes about 76 tokens instead of 241. That more than covers the time spent reading the longer prompt (about 3 s for 185 tokens).
- **Baseline answers sound confident even when wrong.** Question 2's baseline answer was 408 tokens about moths, including a wrong scientific name. This is the main risk RAG removes.

### Against the model-only (IFEval) CPU 2B run

| Measurement | CPU 2B with RAG (this run) | CPU 2B, IFEval (model only) |
|---|---:|---:|
| Generation speed (tokens/s) | 11.7 | 9.00 |
| Prompt processing (tokens/s) | about 58 | 49.3 |
| Average output tokens per answer | 76 (RAG) | 245 |
| Average seconds per answer (model only) | 11.4 | 28.6 |
| System RAM increase (GB) | 3.4 | 3.7 |
| SoC peak temperature (°C) | 65.6 | 66.5 |

- **Generation is faster here** (11.7 against 9.00 tokens/s) because the model stayed loaded between questions and the answers and context are much shorter. The IFEval runs unloaded the model after every answer and used a 16k context.
- **Memory and heat are similar** to the model-only run.

## Results

### Answers scored (main pass)

| Question | Expected | Mode | Correct? | Evidence retrieved? | Citation supports the claim? | Unsupported claims | Proper abstention? | Model time (s) | Total (s) |
|---|---|---|:---:|:---:|:---:|---|:---:|---:|---:|
| Q1: Where does Cedar store uploaded documents? | Local disk | RAG | **Yes** | Yes | Yes [S1] | None | — | 15.2 | 25.4 |
| | | Baseline | No | — | — | Invented "Cedar Storage" on cloud providers | — | 29.3 | 38.0 |
| Q2: What connection does Cedar use to communicate with its host? | USB-C | RAG | **Yes** | Yes | Yes [S1] | 1: links USB-C to the power-cable rule | — | 10.1 | 20.4 |
| | | Baseline | No | — | — | Invented a chestnut-moth answer | — | 35.7 | 44.6 |
| Q3: What must happen before Cedar's enclosure is opened? | Disconnect the power cable | RAG | **Yes** | Yes | Yes [S1] | None | — | 12.3 | 22.5 |
| | | Baseline | No | — | — | None (said it had no information) | — | 7.1 | 15.9 |
| Q4: What is Cedar's battery capacity? | Not specified in the document | RAG | **Yes** | Yes | Yes [S1] | None | **Yes** | 8.1 | 18.3 |
| | | Baseline | Yes (did not guess) | — | — | None (asked for the manufacturer and model) | Yes | 13.8 | 22.5 |

"Model time" is the generation stage (prompt count plus the Ollama request). "Total" adds loading the embedding model, tokenizer and index, and retrieval. It does not include starting the container. Q1 RAG includes loading the model into Ollama (6.3 s).

- **Retrieval:** the test document is one passage, so every RAG question received it ([S1]). Evidence hit rate@5 is 3 of 3 answerable questions, but this says nothing about retrieval quality on a real corpus.
- **Citations:** every RAG answer cited [S1], and no answer cited a source that was not supplied.
- **Unsupported claim in Q2:** "this connection requires the power cable to be disconnected before opening the enclosure, confirming the physical interface used for communication and power delivery." The document gives the two facts separately; it does not connect them or mention power delivery.
- **Q3 RAG** added a note that the document does not cover the battery capacity. That is true and harmless.

### Speed and resources (all 12 questions)

| Measurement | Value |
|---|---:|
| Generation speed range (tokens/s) | 9.91–12.07 (average 11.7) |
| Prompt processing (tokens/s) | about 50–60 (one repeat reused Ollama's cached prompt: 1,501) |
| Model load into Ollama (first question) | 6.3 s |
| Embedding model, tokenizer and index load, per RAG question | 10.0–10.2 s |
| Tokenizer load, per baseline question | 8.8 s |
| Retrieval (embed the question and search) | 0.10–0.13 s |
| Prompt count check: the pipeline's preflight against Ollama's count | Equal for all 12 (182–186 RAG, 44–48 baseline) |
| Peak Ollama process memory | 3.01 GB |
| System RAM start → peak | 3.4 → 6.7 GB (increase 3.4 GB) |
| Ollama CPU use while loaded (% of all 8 cores) | 50% (the model is idle between questions while the next container starts) |
| Answers / truncated | 12 / 0 |
| Total run time (12 questions) | 5.3 min |

### Thermal and fan behaviour

| | RAG run | CPU 2B IFEval run |
|---|---:|---:|
| SoC start / average / peak (°C) | 54.5 / 60.6 / 65.6 | 54.3 / 64.5 / 66.5 |
| Hottest CPU core peak (°C) | 68.4 | 68.4 |
| NPU / GPU peak (°C) | 62.8 / 61.0 | 62.9 / — |
| Fan at full speed (PWM 255) | 51% | 99% |
| Fan at a lower step (PWM 64–192) | 3% | 0% |
| Fan off (PWM 0) | 46% | 1% |

- **Cooler than the IFEval run:** the answers are short, and the CPU rests while each new question's container starts, so the fan was off almost half the time.
- **No throttling:** the big cores stayed at 2,304 MHz in every sample.

## V&V outcome

### Verification

| ID | Check | Result | Evidence |
|---|---|:---:|---|
| V-01 | Runtime and pipeline versions | **Pass** | Ollama 0.40.3 in every log record; RAG image `is2-local-ai-rag` ID `703bbd2a…` from `software/rag/Dockerfile` (Python 3.12.10, pinned packages) |
| V-02 | Expected weights | **Pass** | Ollama ID `1e2d21a4f03a` in every log record, the same as the CPU 2B run; embedding and tokenizer revisions recorded (`5c38ec7c`, `15852e8c`) |
| V-03 | Same settings for every question | **Pass** | Temperature 0, seed 42, context 4,096, 512-token limit, thinking off, k = 5, same index (manifest SHA-256 `70b7ef03…` in every RAG record) |
| V-04 | Completed without errors | **Pass** | All 12 questions answered; no failed requests, citation warnings or thinking output |
| V-05 | No truncated answers | **Pass** | `finish_reason` `stop` for all 12 |
| V-06 | Resource log complete | **Pass** | 317 rows; largest gap 1.0 s; no `unreachable` entries |
| V-07 | Model was actually loaded | **Pass** | Ollama process at 2.6–3.0 GB; system RAM +3.4 GB |
| V-08 | Local only | **Pass** | Ollama on `127.0.0.1:11435`; the pipeline forces Hugging Face offline mode and loads local files only |
| V-09 | Repeatable | **Pass** | The 4 RAG answers in the repeat are identical, word for word, to the main pass |
| V-10 | Ran on the intended processor | **Pass** | NPU interrupts 0; GPU load 0.5%; Ollama CPU use 50% |
| V-11 | Prompt budget measured correctly | **Pass** | The pipeline's preflight count equals Ollama's `prompt_eval_count` for all 12 questions (after the Qwen3.5 fix in Setup notes) |

### Validation

The tutorial's "definition of done" gives the checks; the targets below are proposals for this fixture.

| ID | Measure | Proposed target | Result |
|---|---|---|---|
| RAG-01 | Correct answers to answerable questions, RAG | 3 of 3 | 3 of 3 **Pass** |
| RAG-02 | Proper abstention on the unanswerable question, RAG | Says the document does not specify it | **Pass** |
| RAG-03 | Citations point to supplied sources and support the main claim | All answers | 4 of 4 **Pass** |
| RAG-04 | Unsupported claims, RAG | Report | 1 (Q2) |
| RAG-05 | RAG better than baseline | More correct answers, fewer invented ones | 4 against 0 correct; 0 against 2 invented **Pass** |
| RAG-06 | Evidence hit rate@5 | 3 of 3 | 3 of 3 **Pass** (cannot fail with a one-passage document) |
| RAG-07 | Offline restart (tutorial Step 10) | Works after a disconnected restart | **Not run.** Offline mode was forced and all requests were local, but the board was not disconnected from the network |
| VAL-04 | Peak model memory | ≤ 8 GB | 3.4 GB **Pass** |
| VAL-05 | Thermal | SoC < 85 °C, no sustained throttling | 65.6 °C **Pass** |

## Setup notes

- **Docker image instead of a Python environment.** The pipeline's pinned packages need Python 3.12, and the board has 3.11, so the pipeline ran in the project's `software/rag/Dockerfile` image. Each question is a new `docker run` with `--network host`, pointed at the board's Ollama through `OLLAMA_URL`. The compose stack's own Ollama service was not used, so the same Ollama 0.40.3 and model files as the earlier CPU runs served the model.
- **Qwen3.5-2B added to the pipeline.** `download_models.py` now maps `qwen3.5:2b-q4_K_M`, `qwen3.5:2b` and `qwen3.5:4b` to their Hugging Face tokenizers. The default model (`qwen3:4b-instruct-2507-q4_K_M`) is unchanged.
- **Prompt count fix for Qwen3.5.** The pipeline added ` /no_think` to the question when counting tokens, as Ollama's Qwen3 template does. Ollama's Qwen3.5 renderer does not, so the count was 4 tokens too high (190 against 186). `rag.py` now leaves it out for Qwen3.5 models, and the counts match exactly. Qwen3 models are counted as before.
- **Ollama setting:** `keep_alive` was 10 minutes (the pipeline's setting), so the model stayed loaded between questions. The IFEval runs unloaded it after each answer.
- **Test document:** `software/rag/data/documents/tutorial_sample.txt`, copied from Step 3 of the tutorial (gitignored, like all corpus files). It is indexed as 1 chunk.
- **A smoke test** (one RAG question) ran before the evaluation, to check the set-up. Its log was kept separately (`software/rag/logs/smoke_test_runs.jsonl`) and is not part of the results.
- **Scoring** was done by hand against the tutorial's answer key, as the tutorial says.
- **No power data:** the board cannot measure its own power, and no meter was available.

## Next steps

1. **Build a real corpus:** 5–10 project documents from one area, with 15–20 questions, expected answers and supporting passages, including some unanswerable ones (tutorial Step 11). This is needed to measure retrieval quality and the unsupported-claim rate.
2. **Run the same RAG test on the NPU 2B** through `rkllm_server.py`, which accepts the same requests, to compare speed and answer quality with the CPU.
3. **Keep the pipeline running as a service.** Loading the embedding model for each question costs about 10 s; a resident process would cut a RAG answer to about 8–15 s on the CPU.
4. **Run the offline restart check** (tutorial Step 10) with the board disconnected from the network.

## Raw data

On the board:

| Item | Location |
|---|---|
| Run log (every question, answer, supplied evidence, token counts and timings) | `software/rag/logs/runs.jsonl` |
| Index and manifest | `software/rag/data/index/` |
| Console log (answers as printed) | `~/is2-local-ai/benchmark_results/rag_cpu2b.log` |
| Resource log | `~/is2-local-ai/benchmark_results/resources_20261123T192726Z.csv` and `_summary.json` |
| Fan log | `~/is2-local-ai/benchmark_results/fan_20261123T192526Z.csv` |

`software/rag/data/`, `models/` and `logs/` are gitignored.
