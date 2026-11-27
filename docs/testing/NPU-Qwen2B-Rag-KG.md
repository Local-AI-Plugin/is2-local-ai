# Rock 5T NPU Results with RAG and Knowledge Graph: Qwen3.5 2B

Results of running the local AI stack on the Rock 5T with the LLM (Qwen3.5-2B) on the NPU, and the RAG pipeline ([software/rag](../../software/rag/README.md)) and the knowledge graph (Apache Jena Fuseki, [software/knowledge_base](../../software/knowledge_base/README.md)) on the CPU. Clocks were locked at maximum. The tests are exactly those of the all-CPU run ([CPU-Qwen2B-Rag-KG.md](CPU-Qwen2B-Rag-KG.md)): the doctrine RAG evaluation, and the team's two knowledge-graph (KG) tests. Only the LLM server changes: the NPU model runs in RKLLM through `models/rkllm_server.py`. The RAG-only NPU results are in [NPU-Qwen2B-Rag.md](NPU-Qwen2B-Rag.md).

**Date:** 2026-11-27
**Board:** Radxa ROCK 5T (RK3588, 3-core 6 TOPS NPU at 1.0 GHz, 12 GB RAM), heatsink with PWM fan (`pwmfan`)
**Clocks:** locked at maximum by the `rock5t-max-clocks` boot service ([hardware/processing_unit/rock5t](../../hardware/processing_unit/rock5t/README.md))
**Model:** `qwen3.5-2b_w8a8_rk3588.rkllm` (w8a8, Q-engineering conversion, RKLLM toolkit 1.3.0, SHA-256 `3185384c…`), the same file as the NPU RAG test
**LLM server:** RKLLM runtime 1.3.1, rknpu driver 0.9.8, through `models/rkllm_server.py` (`127.0.0.1:11436`), with its new OpenAI-compatible `/v1/chat/completions` endpoint for the KG scripts (see Setup notes). Greedy (`top_k 1`), presence penalty 1.5, context 4,096 tokens, thinking off, inference threads on the big cores (CPU 4–7)
**Knowledge graph (CPU):** Apache Jena Fuseki 6.2.0 (Java 21) in Docker (image `78c310c6…`), 1 CPU and 1 GB limit, `127.0.0.1:3030`; UGV Mission Planning ontology and Scenario 1 individuals (1,325 triples). Running for the whole session
**RAG pipeline (CPU):** `software/rag/rag.py` in the `is2-local-ai-rag` Docker image (ID `703bbd2a…`), embedding model `BAAI/bge-small-en-v1.5`, top 5 passages, the same 4,473-chunk index (manifest SHA-256 `dc5b9553…`)
**KG client (CPU):** the team's `kg_query.py` and `kg_agent.py`, unchanged (Qwen-Agent 0.0.34, rdflib 7.6.0)
**Tests:**
- RAG: 20 doctrine questions ([software/rag/eval/doctrine_questions.json](../../software/rag/eval/doctrine_questions.json)) in RAG and baseline mode, then Q01–Q05 again (45 answers)
- KG Test 1: competency question CQ1.1 ("Which vehicle capabilities does the assigned task require?"), 3 runs plus 1 run with a named task and mission
- KG Test 2: the 5 paraphrased questions in `queries/paraphrases.json`, two passes (10 questions)

## Summary

- **RAG accuracy is unchanged: 17 of 20 right (85%),** the same as on the CPU. All 45 answers are word for word the same as in the 2026-11-23 NPU RAG test.
- **The NPU is the faster choice for both RAG and the knowledge graph:**
  - A RAG answer takes 54 s against 73 s on the CPU (26% faster).
  - A KG Test 1 answer takes 6.5 s against 7–8 s.
  - A KG agent question takes 16.5 s against 26.8 s (38% faster).
- **KG Test 1 passed 4 of 4,** with correct answers and identical repeats.
- **KG Test 2 passed 10 of 10,** and the NPU model needed fewer retries than the CPU model (2 against 5). It wrote "MissionAlpha" correctly the first time.
- **KG answer quality: right conclusion in 10 of 10, fully correct in 6 of 10.** Two answers said the observe task was "specifically under MissionAlpha" although the graph listed two missions. Two others reached the right conclusion for the move task ("no specific vehicle capability is required") but added a false claim that the move task is not linked to Mission Alpha. The CPU model made no such claims, but reached no conclusion on the move task.
- **The CPU stays mostly free:** server CPU use 14% during RAG and 20% during the KG tests (CPU: 76% and 94%). System RAM rose 3.2 GB against 5.8 GB, and the fan was off about half the time during RAG.
- **The knowledge graph and RAG retrieval on the CPU did not slow the NPU:** RAG speed is within 1% of the RAG-only NPU test.
- **The NPU server needed a new endpoint** for the KG scripts: the OpenAI-style API with streaming and native tool calls, using Qwen's own chat template. It was checked to give identical output to the existing RAG path.

## NPU compared with the CPU

### Side by side

| Measurement | CPU (all on CPU) | NPU LLM, RAG and KG on CPU | Better |
|---|---:|---:|---|
| RAG correct answers (of 20) | 17 (85%) | 17 (85%) | Even |
| RAG serious unsupported claims | 1 (Q16) | 1 (Q03) | Even |
| RAG answers cut off at 512 tokens | 0 | 4 | CPU |
| RAG prompt processing (tokens/s) | 53.0 | **149.6** | **NPU** |
| RAG generation (tokens/s) | 10.28 | **12.38** | **NPU** |
| RAG total time per question (s) | 72.6 | **53.7** | **NPU** |
| KG Test 1: rows check | 3 of 3 | 3 of 3 | Even |
| KG Test 1: correct answers | 4 of 4 | 4 of 4 | Even |
| KG Test 1: time per answer (s) | 7.3–8.1 (15.3 with model load) | **6.3–6.8** | **NPU** |
| KG Test 2: correct tool call | 10 of 10 | 10 of 10 | Even |
| KG Test 2: questions needing a retry | 5 of 10 | **2 of 10** | **NPU** |
| KG Test 2: right conclusion | 8 of 10 | **10 of 10** | **NPU** |
| KG Test 2: fully correct (complete, nothing unsupported) | **8 of 10** | 6 of 10 | **CPU** |
| KG Test 2: unsupported claims | **0** | 2 | **CPU** |
| KG Test 2: time per question (s) | 26.8 | **16.5** | **NPU** |
| KG answer generation (tokens/s) | 10.9 | **12.6** | **NPU** |
| Server CPU use, RAG / KG (% of 8 cores) | 76 / 94 | **14 / 20** | **NPU** |
| System RAM increase during RAG (GB) | 5.8 | **3.2** | **NPU** |
| SoC peak, RAG / KG (°C) | 66.5 / 65.6 | **63.8 / 61.9** | **NPU** |
| Fan at full speed, RAG / KG (% of the time) | 76 / 96 | **30 / 30** | **NPU** |

- **Speed and load clearly favour the NPU.** It reads prompts about 2.8 times as fast, which matters most for RAG's long prompts and for the KG agent's tool descriptions.
- **KG quality is mixed.** The NPU model chooses the tool more cleanly and always reaches a conclusion, but it twice added a detail not in the graph results. The CPU model added nothing unsupported but twice failed to conclude. With only 5 distinct questions, neither difference is strong evidence.
- **RAG quality is a tie,** as in the RAG-only tests.

## Results

### RAG (main pass, 20 questions)

Answers and supplied evidence are identical to [NPU-Qwen2B-Rag.md](NPU-Qwen2B-Rag.md), so the per-question scoring there applies unchanged:

| Measurement | 2026-11-27 (with KG) | 2026-11-23 (RAG only) |
|---|---:|---:|
| Correct answers (of 20) | **17 (85%)** | 17 (85%) |
| Correct answers to answerable questions (of 17) | 14 | 14 |
| Proper "not in the documents" (of 3) | 3 | 3 |
| Answers identical to the 2026-11-23 run | **45 of 45** | — |
| Serious unsupported claims | 1 (Q03) | 1 (Q03) |
| RAG answers cut off at 512 tokens | 4 (Q02, Q03, Q10, Q12) | 4 (same) |

The server now reports cut-off answers correctly (`length`), after the fix described in the RAG-only report. This run flagged the 4 RAG answers above, Q02 and Q03 in the repeat, and 3 baseline answers (Q02, Q04, Q06). All of these had already been found by inspection in the earlier run.

### RAG speed

| Measurement | 2026-11-27 (with KG) | 2026-11-23 (RAG only) |
|---|---:|---:|
| Prompt tokens (server's count) | 1,260–2,589 (average 1,771) | same |
| Prompt processing | 149.6 tokens/s (11.8 s) | 148.3 tokens/s (11.9 s) |
| Average output tokens | 375 | 375 |
| Generation speed | 12.38 tokens/s (30.3 s) | 12.19 tokens/s (30.7 s) |
| Retrieval-model load per question (CPU) | 10.1 s | 10.2 s |
| Retrieval (CPU) | 0.11 s | 0.11 s |
| Total time per RAG question | **53.7 s** (31–68 s) | 53.3 s |
| Total time per baseline question | 34.0 s | 34.7 s |
| Model load (first question) | 24.3 s | 3.0 s |
| RAG run (45 requests) | 36.0 min | 36.1 min |

- **The slower first load (24 s)** was most likely the model file being read from the eMMC: the CPU session had just run, so the 2.4 GB file was no longer in the operating system's file cache. Later questions were unaffected.
- **Repeats take full time on the NPU** (58.8 s), because RKLLM does not reuse an identical earlier prompt. Ollama on the CPU does, so its repeats were twice as fast. Repeats are left out of the averages above.

### KG Test 1: Qwen explains the graph rows

| Run | Rows check | Total (s) | First token (s) | Output tokens | Answer |
|---|:---:|---:|---:|---:|---|
| CQ1.1, run 1 | **Pass** | 6.8 | 1.3 | 66 | Correct: Camera observation, requirement `s1:ReqCameraObservation` |
| CQ1.1, run 2 | **Pass** | 6.3 | 1.1 | 66 | Identical to run 1 |
| CQ1.1, run 3 | **Pass** | 6.4 | 1.0 | 66 | Identical to run 1 |
| CQ1.1 with task "Observe an inspection area", mission MissionAlphaBravo | — | 6.5 | 1.3 | 66 | Correct |

- The model was already loaded from the RAG run, so run 1 has no load time. Each answer read about 116 prompt tokens in 1.0–1.25 s on the NPU, then wrote at 12.0–12.6 tokens/s.
- The answers add "the vehicle must be equipped with a camera", a fair restatement of "Camera observation" rather than a new fact.

### KG Test 2: Qwen chooses the graph lookup

| Question | Pass (both passes) | Tool calls (pass 1 / 2) | Answer | Time (s, pass 1 / 2) |
|---|:---:|:---:|---|---:|
| Q1 Capabilities for the observe-area task in Mission Alpha | **Yes** | 1 / 1 | Correct | 15.2 / 15.2 |
| Q2 What the UGV must do for area observation in Mission Alpha | **Yes** | 1 / 1 | Correct | 12.7 / 12.8 |
| Q3 Capabilities required by "Observe an inspection area" | **Yes** | 1 / 1 | Capability correct, but **said "specifically under MissionAlpha"**; the rows listed MissionAlpha and MissionAlphaBravo | 14.4 / 14.1 |
| Q4 Capabilities ObserveAreaTask needs on MissionAlphaBravo | **Yes** | 1 / 1 | Correct | 15.0 / 15.0 |
| Q5 Does the move task in Mission Alpha need a capability? | **Yes** | 2 / 2 | Right conclusion ("no specific vehicle capability is required") after retrying "Move" as `MoveTask`, but **claimed the move task is not linked to Mission Alpha**. The graph assigns it to Mission Alpha; the empty result cannot show either way | 25.1 / 25.3 |

- **Tool selection: 10 of 10.** Only Q5 needed a retry; the model passed `MissionAlpha` correctly from the start.
- **Both passes were identical,** word for word and call for call.

### KG speed

| Measurement | NPU | CPU |
|---|---:|---:|
| Test 1 answer | **6.3–6.8 s** | 7.3–8.1 s (15.3 s with model load) |
| Test 2 question | **16.5 s** on average (12.7–25.3 s) | 26.8 s (19.6–34.1 s) |
| Model calls per Test 2 question | 2.2 (22 for 10) | 2.5 (25 for 10) |
| Tool-call turn | **8.1 s** | 12.6 s |
| Answer turn (first token / total) | **1.2 s / 6.7 s** | 2.7 s / 7.7 s |
| Answer generation | **12.6 tokens/s** | 10.9 tokens/s |
| NPU prompt processing (RKLLM's counters) | 131.7 tokens/s | — |
| KG test session | **3.2 min** | 5.2 min |

- **Prompt reuse works on both servers.** When a call continues the previous conversation exactly (the answer turn after a tool call), RKLLM keeps the earlier work and only processes the new part. Its token counts then show only the new tokens (about 160 per answer turn), while Ollama reports the full prompt (about 715). Comparisons here therefore use measured times, which are fair to both.

### Resources

| Measurement | RAG run | KG tests |
|---|---:|---:|
| Peak NPU server memory | 2.41 GB | 2.41 GB |
| System RAM start → peak | 3.6 → 6.8 GB (+3.2 GB) | 6.2 → 6.5 GB (+0.3 GB, model already loaded) |
| Server CPU use (% of all 8 cores) | 14.5% | 20.1% |
| Whole-system CPU use | 21% | 28% |
| NPU interrupts in the window (per core) | about 2.55 million | about 266,000 |
| NPU clock | 1,000 MHz in every sample | 1,000 MHz in every sample |
| Fuseki CPU use (% of one core) | 0.19% | 1.0% (peak 10.3%) |
| Fuseki memory | 603 MiB | 411 MiB average, 673 MiB peak |

- **Fuseki stayed light** (0.04% of one core while idle), so running the knowledge graph next to the NPU model costs almost nothing.
- **The KG client and the RAG container run on the CPU,** which explains the 14–20% server CPU use (RKLLM's own threads) plus the rest of the system's share.

### Thermal and fan behaviour

| | RAG run | KG tests | Idle (120 s before the RAG run) |
|---|---:|---:|---:|
| SoC start / average / peak (°C) | 54.5 / 59.4 / 63.8 | 57.3 / 59.9 / 61.9 | — |
| NPU zone start / average / peak (°C) | 52.7 / 58.4 / 61.9 | 56.4 / 58.8 / 60.1 | — |
| Hottest CPU core peak (°C) | 66.5 | 64.7 | — |
| GPU peak (°C) | 61.0 | 59.2 | — |
| Fan at full speed (PWM 255) | 30% | 30% | 0% |
| Fan at a lower step | 17% | 41% | 0% |
| Fan off | 53% | 29% | 100% |

- **No throttling:** the big cores stayed at 2,304 MHz and the NPU at 1,000 MHz in every sample.

## V&V outcome

### Verification

| ID | Check | Result | Evidence |
|---|---|:---:|---|
| V-01 | Software versions | **Pass** | RKLLM runtime 1.3.1, rknpu driver 0.9.8, toolkit 1.3.0, platform RK3588, W8A8 (server log); RAG image `703bbd2a…`; Fuseki image `78c310c6…`; Qwen-Agent 0.0.34 |
| V-02 | Expected weights | **Pass** | Model file SHA-256 `3185384c…` in every RAG log record |
| V-03 | Same tests and settings as the CPU run | **Pass** | Same questions, index, k = 5, 512-token RAG limit, greedy, seed 42, thinking off, context 4,096; same KG tests and harness |
| V-04 | Completed without errors | **Pass** | 45 of 45 RAG requests; 14 KG runs (26 model calls through `/v1`), no errors |
| V-05 | Truncated answers | **Fail (4 RAG)** | Q02, Q03, Q10, Q12 RAG answers (and Q02, Q03 in the repeat) reached 511 tokens, now correctly reported as `length`; 3 baseline answers too. KG answers were 56–68 tokens |
| V-06 | Resource logs complete | **Pass** | RAG 2,161 rows, KG 194 rows; largest gap 2.0 s |
| V-07 | Model was actually loaded | **Pass** | Server process 2.41 GB |
| V-08 | Local only | **Pass** | NPU server on `127.0.0.1:11436`, Fuseki on `127.0.0.1:3030`; RAG pipeline offline |
| V-09 | Repeatable | **Pass** | RAG repeats identical; KG Test 1 identical in all 3 runs; Test 2 identical in both passes |
| V-10 | Ran on the intended processor | **Pass** | About 2.55 million interrupts per NPU core during RAG and 266,000 during the KG tests; NPU at 1.0 GHz; server CPU use 14–20% |
| V-11 | Knowledge graph loaded correctly | **Pass** | 1,325 triples; CQ1.1 rows matched the expected file in all 3 runs |
| V-12 | Accuracy unchanged by the added services | **Pass** | All 45 RAG answers identical to the 2026-11-23 NPU run |
| V-13 | New `/v1` endpoint matches the existing path | **Pass** | Before the run, the same system and user message through `/api/chat` and `/v1/chat/completions` gave the identical answer and token counts (30 in, 7 out); the template's plain layout matches the RAG path exactly |

### Validation

| ID | Measure | Proposed target | CPU (all on CPU) | NPU LLM |
|---|---|---|---|---|
| RAG-01 | Correct answers to answerable questions | ≥ 80% | 14 of 17 (82%) Pass | 14 of 17 (82%) **Pass** |
| RAG-02 | Proper abstention on unanswerable questions | 3 of 3 | Pass | **Pass** |
| RAG-03 | Citations point only to supplied sources | All answers | Pass | **Pass** |
| RAG-04 | Serious unsupported claims | 0 | 1 Fail | 1 **Fail** |
| RAG-05 | RAG better than baseline | More correct, fewer invented | Pass | **Pass** |
| RAG-06 | Evidence hit rate@5 | ≥ 90% | 82% Fail | 82% **Fail** |
| RAG-08 | Time per RAG answer | Report | 72.6 s | **53.7 s** |
| KG-01 | Graph returns the expected rows | 100% | 3 of 3 Pass | 3 of 3 **Pass** |
| KG-02 | Correct tool call (Test 2) | ≥ 80% | 10 of 10 Pass | 10 of 10 **Pass** |
| KG-03 | Correct final answer from the graph | ≥ 80% | Test 1: 4 of 4; Test 2: 8 of 10 Pass | Test 1: 4 of 4; Test 2: 10 of 10 **Pass** |
| KG-04 | Unsupported claims in KG answers | 0 | 0 Pass | 2 (Q5, both passes) **Fail** |
| KG-05 | Time per KG answer | Report | 7–8 s / 27 s | **6.5 s / 16.5 s** |
| VAL-04 | Peak model memory | ≤ 8 GB | 5.3 GB Pass | 2.4 GB **Pass** |
| VAL-05 | Thermal | SoC < 85 °C | 66.5 °C Pass | 63.8 °C **Pass** |

The KG targets are proposed here; the team should confirm them. KG-03 counts the right conclusion; incomplete answers (Q3 on the NPU) count as correct there but not as fully correct.

## Setup notes

- **New OpenAI-compatible endpoint in `rkllm_server.py`.** The KG scripts use Qwen-Agent, which talks to the OpenAI-style `/v1/chat/completions` API, streams responses, and (for Test 2) sends multi-turn conversations with tool calls. The server previously offered only Ollama's `/api/chat` with one user message. The new endpoint:
  - renders the messages and tools with the model's own Hugging Face chat template (`chat_template.jinja`, passed with `--chat-template`), exactly as the transformers library would, and runs the result with an empty RKLLM template so nothing is added;
  - turns the model's XML tool calls (`<tool_call><function=…><parameter=…>`) into standard `tool_calls`, as Ollama does;
  - streams each token as it is generated, holding back only text that may start a tool call, so the client's time to first token is real;
  - reports usage, including RKLLM's own timing counters.

  The existing `/api/chat` path, used by the RAG pipeline and IFEval, is unchanged.
- **Same two client settings as on the CPU** (thinking off, native tool calls), set by the test harness; no team code changed. See [CPU-Qwen2B-Rag-KG.md](CPU-Qwen2B-Rag-KG.md#setup-notes).
- **Ollama was stopped** before the NPU session. The VS Code window's rendering process was moved to the little cores (CPU 0–3) during the run and back afterwards, as in earlier NPU runs.
- **Same session layout as the CPU run:** 120 s idle, the RAG evaluation, then the KG tests, with Fuseki running throughout and the fan, the Fuseki container and system resources logged.
- **No power data:** the board cannot measure its own power, and no meter was available.

## Next steps

1. **Use the NPU for the LLM in the combined RAG + KG system:** the same RAG accuracy, 26% faster RAG answers, 38% faster KG agent answers, and the CPU left mostly free for retrieval and the knowledge graph.
2. **Tighten the KG answer prompt** so the model states only what the rows show. For example: "If the rows are empty, say no capability is recorded; do not say whether the task belongs to the mission." That targets the NPU's Q5 claim and the CPU's non-answer.
3. **Add more competency questions and paraphrases.** One query and 5 questions are too few to separate the two models' KG quality.
4. **Make empty results explicit and add a "Mission Alpha" label** to the graph (see [CPU-Qwen2B-Rag-KG.md](CPU-Qwen2B-Rag-KG.md#next-steps)).
5. **Shorten RAG answers** on the NPU to avoid the 4 cut-off answers and save time ([NPU-Qwen2B-Rag.md](NPU-Qwen2B-Rag.md#next-steps)).

## Raw data

On the board:

| Item | Location |
|---|---|
| RAG run log | `software/rag/logs/doctrine_npu_ragkg_runs.jsonl` |
| KG run log (rows, resolved names, tool calls, answers) | `software/knowledge_base/logs/kg_npu_runs.jsonl` |
| KG per-call timings (with RKLLM counters) | `~/is2-local-ai/benchmark_results/kg_metrics_npu.jsonl` |
| Console logs | `~/is2-local-ai/benchmark_results/ragkg_rag_npu.log`, `ragkg_kg_npu.log` |
| NPU server log | `~/is2-local-ai/benchmark_results/ragkg_npu_server.log` |
| Session log | `~/is2-local-ai/benchmark_results/ragkg_driver.log` |
| Resource logs | `~/is2-local-ai/benchmark_results/resources_20261127T184922Z.csv` (RAG), `resources_20261127T192524Z.csv` (KG) |
| Fan log | `~/is2-local-ai/benchmark_results/fan_npu_20261127T184722Z.csv` |
| Fuseki container log | `~/is2-local-ai/benchmark_results/fuseki_npu_20261127T184722Z.csv` |
| Test and analysis scripts (session driver, KG harness, analysis) | `~/is2-local-ai/benchmark_results/ragkg_scripts/` |

`software/rag/logs/` and `software/knowledge_base/logs/` are gitignored.
