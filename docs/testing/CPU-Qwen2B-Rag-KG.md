# Rock 5T CPU Results with RAG and Knowledge Graph: Qwen3.5 2B

Results of running the whole local AI stack on the Rock 5T's CPU: the LLM (Qwen3.5-2B in Ollama), the RAG pipeline ([software/rag](../../software/rag/README.md)) and the knowledge graph (Apache Jena Fuseki with the UGV mission-planning ontology, [software/knowledge_base](../../software/knowledge_base/README.md)). Clocks were locked at maximum. The RAG part repeats the CPU RAG test ([CPU-Qwen2B-Rag.md](CPU-Qwen2B-Rag.md)) exactly, now with the knowledge graph server running alongside. The knowledge-graph (KG) part runs the team's two KG tests: Qwen explains the rows a saved graph query returns (Test 1), and Qwen chooses the graph lookup itself (Test 2). The same tests with the LLM on the NPU are in [NPU-Qwen2B-Rag-KG.md](NPU-Qwen2B-Rag-KG.md).

**Date:** 2026-11-27
**Board:** Radxa ROCK 5T (RK3588, 4× Cortex-A76 at 2.3 GHz + 4× Cortex-A55 at 1.8 GHz, 12 GB RAM), heatsink with PWM fan (`pwmfan`)
**Clocks:** locked at maximum by the `rock5t-max-clocks` boot service ([hardware/processing_unit/rock5t](../../hardware/processing_unit/rock5t/README.md))
**Model:** `qwen3.5:2b-q4_K_M` (Ollama digest `1e2d21a4…`), the same as the CPU RAG test
**LLM server:** Ollama 0.40.3, native, `127.0.0.1:11435`. RAG through Ollama's `/api/chat` (unchanged); KG through Ollama's OpenAI-compatible `/v1` API, which the KG scripts use. Greedy (temperature 0), seed 42, thinking off, context 4,096 tokens
**Knowledge graph:** Apache Jena Fuseki 6.2.0 (Java 21) in Docker, built from `software/knowledge_base/Dockerfile` (image `78c310c6…`), limited to 1 CPU and 1 GB as in `compose.yaml`, on `127.0.0.1:3030`. Loaded with `load_kg.py`: the UGV Mission Planning ontology and the Scenario 1 individuals from `docs/knowledge/` (1,325 triples). Running for the whole session
**RAG pipeline:** `software/rag/rag.py` in the `is2-local-ai-rag` Docker image (ID `703bbd2a…`), embedding model `BAAI/bge-small-en-v1.5`, top 5 passages, the same 4,473-chunk doctrine index (manifest SHA-256 `dc5b9553…`)
**KG client:** the team's `kg_query.py` and `kg_agent.py`, unchanged, with Qwen-Agent 0.0.34, rdflib 7.6.0 and requests 2.34.2 (the versions in `requirements.txt`)
**Tests:**
- RAG: 20 doctrine questions ([software/rag/eval/doctrine_questions.json](../../software/rag/eval/doctrine_questions.json)) in RAG and baseline mode, then Q01–Q05 again (45 answers)
- KG Test 1: competency question CQ1.1 ("Which vehicle capabilities does the assigned task require?"), 3 runs plus 1 run with a named task and mission
- KG Test 2: the 5 paraphrased questions in `queries/paraphrases.json`, two passes (10 questions)

## Summary

- **RAG accuracy is unchanged: 17 of 20 right (85%).** All 45 answers are word for word the same as in the 2026-11-23 CPU RAG test, from the same evidence, so the earlier scoring holds: 14 of 17 answerable questions right, 3 of 3 unanswerable ones correctly declined, and one serious unsupported claim (Q16).
- **Running the knowledge graph alongside costs nothing measurable.** RAG speed is within 1–2% of the earlier test (72.6 s against 72.1 s per question). Fuseki used 0.2% of one core and about 440 MiB while idle or during RAG.
- **KG Test 1 passed 4 of 4.** The graph returned the expected rows every time, and Qwen's answers were correct (the task needs Camera observation, requirement `ReqCameraObservation`). The 3 repeat runs gave identical answers. A graph answer took 7–8 s, or 15 s including the first model load.
- **KG Test 2 passed 10 of 10:** Qwen called the graph tool with the right query, task and mission for every question. It needed a second try in 5 of 10. It first wrote "Mission Alpha" or "Move", which do not match a graph name, then retried with the names the tool suggested, as designed.
- **KG answer quality: 8 of 10 agent answers fully correct.** For the move-task question (twice), the graph correctly returned no rows (the move task needs no capability), but Qwen did not conclude that and asked for more information instead. Nothing was invented.
- **An agent question takes 27 s on average** (20–34 s), because each needs 2–3 model calls (tool call, sometimes a retry, then the answer).
- **The CPU runs hot and busy:** 76% CPU use during RAG and 94% during the KG tests, with the fan at full speed 76% and 96% of the time. No throttling; SoC peak 66.5 °C.
- **Two client settings were needed for Qwen3.5** (set by the test harness; no team code changed): thinking off (otherwise one KG answer ran over 7 minutes), and native tool calling (Qwen-Agent's default tool format makes Ollama's Qwen3.5 parser fail with HTTP 500).

## Results

### RAG (main pass, 20 questions)

Answers and supplied evidence are identical to [CPU-Qwen2B-Rag.md](CPU-Qwen2B-Rag.md), so the per-question scoring there applies unchanged:

| Measurement | 2026-11-27 (with KG) | 2026-11-23 (RAG only) |
|---|---:|---:|
| Correct answers (of 20) | **17 (85%)** | 17 (85%) |
| Correct answers to answerable questions (of 17) | 14 | 14 |
| Proper "not in the documents" (of 3) | 3 | 3 |
| Answers identical to the 2026-11-23 run | **45 of 45** | — |
| Serious unsupported claims | 1 (Q16) | 1 (Q16) |
| Baseline correct (no documents) | 0 | 0 |

### RAG speed

| Measurement | 2026-11-27 (with KG) | 2026-11-23 (RAG only) |
|---|---:|---:|
| Average prompt tokens | 1,690 | 1,690 |
| Prompt processing | 53.0 tokens/s (31.9 s) | 52.5 tokens/s (32.2 s) |
| Average output tokens | 304 | 304 |
| Generation speed | 10.28 tokens/s (29.5 s) | 10.44 tokens/s (29.1 s) |
| Retrieval-model load per question | 10.5 s | 10.2 s |
| Retrieval | 0.17 s | 0.12 s |
| Total time per RAG question | **72.6 s** | 72.1 s |
| Total time per baseline question | 36.6 s | 36.9 s |
| Model load (first question) | 6.2 s | 6.1 s |
| RAG run (45 requests) | 41.3 min | 41.2 min |

- **The repeat answers (Q01–Q05) took 36 s instead of 73 s,** because Ollama 0.40.3 keeps recent prompts cached: the repeated prompts were read in 0.2 s instead of about 32 s. The answers were identical. Repeat timings are left out of all averages above.

### KG Test 1: Qwen explains the graph rows

`kg_query.py cq1_1` runs the saved SPARQL query, checks the rows against `cq1_1.expected.json`, then asks Qwen to answer from the rows only.

| Run | Rows check | Total (s) | First token (s) | Output tokens | Answer |
|---|:---:|---:|---:|---:|---|
| CQ1.1, run 1 | **Pass** | 15.3 | 9.2 | 68 | Correct: Camera observation (`s1:CameraObservation`), requirement `s1:ReqCameraObservation` |
| CQ1.1, run 2 | **Pass** | 7.6 | 0.25 | 68 | Identical to run 1 |
| CQ1.1, run 3 | **Pass** | 7.3 | 0.20 | 68 | Identical to run 1 |
| CQ1.1 with task "Observe an inspection area", mission MissionAlphaBravo | — (no expected rows for variants) | 8.1 | 2.9 | 58 | Correct |

- Run 1 includes loading the model (the Ollama server had just started). Runs 2 and 3 started answering in 0.2 s because of Ollama's prompt cache.
- One awkward sentence in every run ("The entity supporting this requirement is the Camera observation capability itself"), but no unsupported facts.

### KG Test 2: Qwen chooses the graph lookup

`kg_agent.py` gives Qwen a `query_kg` tool. A question passes if any of Qwen's tool calls names the expected query, task and mission (names are resolved to graph IRIs by the team's code).

| Question | Pass (both passes) | Tool calls (pass 1 / 2) | Answer | Time (s, pass 1 / 2) |
|---|:---:|:---:|---|---:|
| Q1 Capabilities for the observe-area task in Mission Alpha | **Yes** | 2 / 1 | Correct. Pass 1 first wrote "Mission Alpha" (unknown name), then retried with `s1:MissionAlpha` | 31.3 / 22.1 |
| Q2 What the UGV must do for area observation in Mission Alpha | **Yes** | 2 / 2 | Correct, after the same "Mission Alpha" retry | 30.3 / 31.8 |
| Q3 Capabilities required by "Observe an inspection area" | **Yes** | 1 / 1 | Correct, and named both missions the rows list (MissionAlpha, MissionAlphaBravo) | 22.6 / 22.5 |
| Q4 Capabilities ObserveAreaTask needs on MissionAlphaBravo | **Yes** | 1 / 1 | Correct | 20.0 / 19.6 |
| Q5 Does the move task in Mission Alpha need a capability? | **Yes** | 2 / 2 | **No conclusion.** First wrote "Move" (unknown), retried with `s1:MoveTask`; the query correctly returned no rows, but Qwen said it "cannot determine which capability is required" and asked for the mission ID. Nothing invented | 34.1 / 34.0 |

- **Tool selection: 10 of 10.** Final answers: **8 of 10 fully correct,** 2 without a conclusion (Q5).
- **The retry path worked as designed:** when a name did not match, the tool returned the known names, and Qwen picked the right one on the next call.
- **Pass 2 differed from pass 1 only in Q1** (one call instead of two, with a slightly different answer). The other 4 questions were identical. The likely cause is Ollama's prompt cache: reusing cached computation can change the arithmetic slightly, which can flip a greedy choice.

### KG speed

| Measurement | Value |
|---|---:|
| Test 1 answer (runs 2–3, prompt cached) | 7.3–7.6 s |
| Test 1 answer (new prompt: variant) | 8.1 s (first token 2.9 s) |
| Test 2 question (2–3 model calls) | 26.8 s on average (19.6–34.1 s) |
| Model calls per Test 2 question | 2.5 on average (25 calls for 10 questions) |
| Tool-call turn | 12.6 s on average (555 prompt tokens, 57 output tokens) |
| Answer turn | 7.7 s on average, first token after 2.7 s (715 prompt tokens, 55 output tokens) |
| Generation speed (answer turns) | 10.9 tokens/s |
| Graph query (Fuseki) | 12 ms (saved query), 62 ms with name resolution (median of 20; measured separately on the idle board after the run) |
| KG test session (14 runs, 29 model calls) | 5.2 min |

- **Most of a Test 2 question is spent on the tool call.** Qwen3.5 must read the tool description (about 500 tokens) before it can call the tool, and each retry repeats that.
- Answer turns start quickly (2.7 s for 715 tokens) because llama.cpp reuses the shared beginning of the conversation from the previous call.

### Resources

| Measurement | RAG run | KG tests |
|---|---:|---:|
| Peak Ollama memory | 5.27 GB | 2.86 GB |
| System RAM start → peak | 3.3 → 9.2 GB (+5.8 GB) | 3.4 → 6.5 GB (+3.1 GB) |
| Ollama CPU use (% of all 8 cores) | 76% | 94% |
| Whole-system CPU use | 81% | 97% |
| Fuseki CPU use (% of one core) | 0.17% (peak 0.5%) | 1.0% (peak 17.8%) |
| Fuseki memory | 442 MiB | 382 MiB average, 598 MiB peak |
| NPU interrupts | 0 | 0 |

- **Ollama's memory grows during the RAG run** (2.9 → 5.3 GB) because it keeps recent prompts cached; the KG run started with a fresh server.
- **Fuseki is light:** 0.07% of one core and 442 MiB while idle, a short burst (under 18% of one core) per graph query. Its 1 GB Docker limit was never approached.
- System RAM includes Fuseki (already running at the start) and the RAG container (started per question).

### Thermal and fan behaviour

| | RAG run | KG tests | Idle (120 s before the RAG run) |
|---|---:|---:|---:|
| SoC start / average / peak (°C) | 52.7 / 63.1 / 66.5 | 53.6 / 64.2 / 65.6 | — |
| NPU zone start / average / peak (°C) | 51.8 / 60.7 / 63.8 | 52.7 / 61.5 / 62.8 | — |
| Hottest CPU core peak (°C) | 69.3 | 68.4 | — |
| GPU peak (°C) | 61.9 | 61.0 | — |
| Fan at full speed (PWM 255) | 76% | 96% | 0% |
| Fan at a lower step | 3% | 1% | 0% |
| Fan off | 20% | 3% | 100% |

- **No throttling:** the big cores stayed at 2,304 MHz in every sample.
- **The KG tests keep the CPU almost fully busy** (back-to-back model calls), so the fan ran at full speed almost the whole time.

## V&V outcome

### Verification

| ID | Check | Result | Evidence |
|---|---|:---:|---|
| V-01 | Software versions | **Pass** | Ollama 0.40.3 in every RAG log record; RAG image `703bbd2a…`; Fuseki image `78c310c6…` (Jena 6.2.0, Java 21); Qwen-Agent 0.0.34, rdflib 7.6.0, requests 2.34.2 |
| V-02 | Expected weights | **Pass** | Model digest `1e2d21a4…` in every RAG log record, the same as the CPU RAG test |
| V-03 | Same settings as the CPU RAG test | **Pass** | Same questions, index (`dc5b9553…`), k = 5, 512-token limit, greedy, seed 42, thinking off, context 4,096 |
| V-04 | Completed without errors | **Pass** | 45 of 45 RAG requests; 14 KG runs (29 model calls), no errors. A first KG attempt stopped on a path error in the test harness before any test completed and was rerun (see Setup notes) |
| V-05 | Truncated answers | **Pass** | No RAG answer reached the 512-token limit (3 baseline answers did, as before); KG answers were 55–70 tokens |
| V-06 | Resource logs complete | **Pass** | RAG 2,476 rows, KG 310 rows; largest gap 2.0 s |
| V-07 | Model was actually loaded | **Pass** | Ollama up to 5.27 GB (RAG) and 2.86 GB (KG) |
| V-08 | Local only | **Pass** | Ollama on `127.0.0.1:11435`, Fuseki on `127.0.0.1:3030`; the RAG pipeline runs Hugging Face offline |
| V-09 | Repeatable | **Pass, with one difference** | RAG repeats identical; KG Test 1 identical in all 3 runs; Test 2 identical in 4 of 5 questions between passes (Q1 differed, see above) |
| V-10 | Ran on the intended processor | **Pass** | Ollama at 76–94% CPU; 0 NPU interrupts |
| V-11 | Knowledge graph loaded correctly | **Pass** | 1,325 triples; `kg_smoke.py` passed (expected rows, name resolution, empty result, input rejection); CQ1.1 rows matched the expected file in all 3 runs |
| V-12 | Accuracy unchanged by the added services | **Pass** | All 45 RAG answers identical to the 2026-11-23 CPU run |

### Validation

| ID | Measure | Proposed target | Result |
|---|---|---|---|
| RAG-01 | Correct answers to answerable questions | ≥ 80% | 14 of 17 (82%) **Pass** |
| RAG-02 | Proper abstention on unanswerable questions | 3 of 3 | **Pass** |
| RAG-03 | Citations point only to supplied sources | All answers | **Pass** |
| RAG-04 | Serious unsupported claims | 0 | 1 (Q16) **Fail** |
| RAG-05 | RAG better than baseline | More correct, fewer invented | **Pass** |
| RAG-06 | Evidence hit rate@5 | ≥ 90% | 82% **Fail** |
| RAG-08 | Time per RAG answer | Report | 72.6 s |
| KG-01 | Graph returns the expected rows | 100% | 3 of 3 **Pass** |
| KG-02 | Correct tool call (Test 2) | ≥ 80% | 10 of 10 **Pass** |
| KG-03 | Correct final answer from the graph | ≥ 80% | Test 1: 4 of 4; Test 2: 8 of 10 (80%) **Pass** |
| KG-04 | Unsupported claims in KG answers | 0 | 0 **Pass** |
| KG-05 | Time per KG answer | Report | 7–8 s (Test 1), 27 s (Test 2) |
| VAL-04 | Peak model memory | ≤ 8 GB | 5.3 GB **Pass** |
| VAL-05 | Thermal | SoC < 85 °C | 66.5 °C **Pass** |

The KG targets are proposed here; the team should confirm them.

## Setup notes

- **Fuseki ran in Docker without Compose.** The board has no `docker compose` plugin, so the image was built from `software/knowledge_base/Dockerfile` and run with `docker run` using the compose file's settings (1 GB memory, 1 CPU, `127.0.0.1:3030`, the `kg-data` and `kg-run` volumes).
- **KG client packages** from `software/knowledge_base/requirements.txt` were installed into a separate folder (`~/is2-local-ai/.kg-deps`) and used with the benchmark virtual environment through `PYTHONPATH`, so the benchmark tools were not changed.
- **Thinking off for Qwen3.5.** The KG scripts default to `qwen3:4b-instruct-2507`, which does not think. Through Ollama's `/v1` API, Qwen3.5 thinks by default: a first probe ran for over 7 minutes without finishing. The test harness adds `reasoning_effort: "none"` to every call, which matches the RAG pipeline's `think: false`.
- **Native tool calling.** Qwen-Agent's default writes tool calls as JSON inside `<tool_call>` tags in the prompt. Ollama's Qwen3.5 parser reads any `<tool_call>` text as Qwen3.5's own XML tool format and fails with HTTP 500 (`EOF`). The harness sets `QWEN_AGENT_USE_RAW_API=true`, so the tool goes to Ollama in the API's `tools` field and Qwen3.5 writes calls in the format it was trained on.
- **Test harness:** a wrapper (`kg_bench.py`) imports the team's `kg_query.py` and `kg_agent.py`, unchanged, adds the two settings above, and records per-call timing (time to first token, total time, prompt and output tokens) by wrapping Qwen-Agent's client.
- **KG rerun.** The first KG attempt stopped on a path error in the harness (its metrics file path was relative to the wrong folder). The KG tests were rerun in a new session two minutes later: Ollama restarted, 120 s idle, then the tests. So KG run 1 includes a fresh model load.
- **No power data:** the board cannot measure its own power, and no meter was available.

## Next steps

1. **Use the NPU for the LLM** in the combined system: same RAG accuracy, 26% faster RAG answers and 38% faster KG agent answers, with far less CPU load ([NPU-Qwen2B-Rag-KG.md](NPU-Qwen2B-Rag-KG.md)).
2. **Add more competency questions.** There is only one saved query (CQ1.1) with 5 paraphrases, so the KG accuracy figures rest on very few cases.
3. **Make empty results explicit.** CQ1.1 returns no rows both when a task needs no capability and when the task is not in the mission. Qwen could not tell which on Q5. A query or field that says "task found, no capability required" would remove the guesswork.
4. **Let "Mission Alpha" resolve.** Users and the model write "Mission Alpha", but the graph only knows `MissionAlpha`; adding a label (`rdfs:label "Mission Alpha"`) would save a retry (5 of 10 questions needed one).
5. **Put the two Qwen3.5 settings into the KG scripts** (thinking off, raw-API tool calls) if the team moves the KG path to Qwen3.5-2B.
6. **Improve RAG retrieval,** which caused all 3 RAG misses (see [CPU-Qwen2B-Rag.md](CPU-Qwen2B-Rag.md#next-steps)).

## Raw data

On the board:

| Item | Location |
|---|---|
| RAG run log (every question, answer, evidence, token counts, timings) | `software/rag/logs/doctrine_cpu_ragkg_runs.jsonl` |
| KG run log (rows, resolved names, tool calls, answers) | `software/knowledge_base/logs/kg_cpu_runs.jsonl` |
| KG per-call timings | `~/is2-local-ai/benchmark_results/kg_metrics_cpu.jsonl` |
| Console logs | `~/is2-local-ai/benchmark_results/ragkg_rag_cpu.log`, `ragkg_kg_cpu.log` |
| Session logs | `~/is2-local-ai/benchmark_results/ragkg_driver_attempt1.log` (RAG), `ragkg_driver.log` (KG) |
| Resource logs | `~/is2-local-ai/benchmark_results/resources_20261127T175735Z.csv` (RAG), `resources_20261127T184207Z.csv` (KG) |
| Fan logs | `~/is2-local-ai/benchmark_results/fan_cpu_20261127T175535Z.csv` (RAG), `fan_cpu_20261127T184006Z.csv` (KG) |
| Fuseki container logs | `~/is2-local-ai/benchmark_results/fuseki_cpu_20261127T175535Z.csv`, `fuseki_cpu_20261127T184006Z.csv` |
| Test and analysis scripts (session driver, KG harness, analysis) | `~/is2-local-ai/benchmark_results/ragkg_scripts/` |

`software/rag/logs/` and `software/knowledge_base/logs/` are gitignored.
