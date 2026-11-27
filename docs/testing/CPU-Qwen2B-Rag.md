# Rock 5T CPU Results with RAG: Qwen3.5 2B

Results of running the project's RAG pipeline ([software/rag](../../software/rag/README.md)) on the Rock 5T with Qwen3.5-2B on the CPU, with all clocks locked at maximum, over the project's doctrine corpus ([docs/sources](../sources/README.md)). The test follows the evaluation steps of the RAG tutorial ([Local_AI_Plugin_RAG_Tutorial.md](../Local_AI_Plugin_RAG_Tutorial.md), Steps 6–9): each question is asked with retrieved document evidence (RAG) and without it (baseline), and the answers are scored for correctness, retrieval, citations, unsupported claims and abstention. Speed, memory and temperature were logged as in the earlier board runs. The model-only results for the same model are in [CPU-NPU_Qwen3.5_2B_maxcoresspeed.md](CPU-NPU_Qwen3.5_2B_maxcoresspeed.md), and the same test on the NPU is in [NPU-Qwen2B-Rag.md](NPU-Qwen2B-Rag.md).

**Date:** 2026-11-23
**Board:** Radxa ROCK 5T (RK3588, 4× A76 at 2.3 GHz + 4× A55 at 1.8 GHz, 12 GB RAM), heatsink with PWM fan (`pwmfan`)
**Clocks:** locked at maximum by the `rock5t-max-clocks` boot service ([hardware/processing_unit/rock5t](../../hardware/processing_unit/rock5t/README.md))
**Model:** `qwen3.5:2b-q4_K_M` (Q4_K_M, 1.9B parameters, Ollama ID `1e2d21a4f03a`), the same file as the CPU 2B run
**Runtime:** Ollama 0.40.3 on the CPU (`127.0.0.1:11435`). Thinking off, temperature 0, seed 42, context 4,096 tokens, answers limited to 512 tokens (the RAG pipeline's settings)
**RAG pipeline:** `software/rag/rag.py` in the `is2-local-ai-rag` Docker image (Python 3.12.10, image ID `703bbd2a…`). Embedding model `BAAI/bge-small-en-v1.5` (revision `5c38ec7c`), FAISS index, top 5 passages per question, chat tokenizer `Qwen/Qwen3.5-2B` (revision `15852e8c`)
**Corpus:** the 5 PDFs in `docs/sources`: ADP 5-0, FM 5-0, FM 3-98, the 2004 DoD Dictionary (JP 1-02) and the 2018 DOD Dictionary. Indexed as 4,473 chunks of about 300 tokens (index manifest SHA-256 `dc5b9553…`)
**Test:** 20 questions with an answer key ([software/rag/eval/doctrine_questions.json](../../software/rag/eval/doctrine_questions.json)): 17 answerable from the documents and 3 not answerable. Each was asked in RAG and baseline mode, then Q01–Q05 again in RAG mode as a repeat

## Summary

- **With RAG, the 2B model got 17 of 20 right (85%).** It answered 14 of the 17 answerable questions correctly with citations, and said "not in the documents" for all 3 unanswerable ones.
- **Without RAG, it got none right.** It misread most of the military terms as business, cybersecurity, physics or video-game terms, and invented confident figures for all 3 unanswerable questions (for example a "155 mm" Abrams main gun and a "$1,378 billion" Army budget).
- **All 3 RAG misses were retrieval misses.** For Q03 (OPORD paragraphs), Q04 (one-third, two-thirds rule) and Q16 (SINCGARS), the passage with the answer was not among the 5 retrieved. When the evidence was there, the model answered correctly every time (14 of 14). For Q03 and Q04 it correctly said the evidence was insufficient. For Q16 it also added an invented expansion of SINCGARS, which is the one serious unsupported claim.
- **A RAG answer takes about 72 s on the CPU.** About 32 s goes to reading the 1,700-token prompt of retrieved passages, 29 s to writing the answer (about 300 tokens at 10.4 tokens/s) and 10 s to loading the retrieval model. Retrieval itself takes 0.1 s.
- **It uses more memory and heat than the model alone:** system RAM rose by 5.6 GB, and the fan ran at full speed 77% of the time. The SoC peaked at 66.5 °C, far below the throttle point.
- **All verification checks pass,** and the repeat answers were identical.

## RAG compared with the model alone

### Side by side

| Measurement | RAG | Baseline (no documents) |
|---|---:|---:|
| Correct answers (of 20) | **17 (85%)** | 0 |
| Correct answers to answerable questions (of 17) | **14 (82%)** | 0 (1 partly right) |
| Proper "not in the documents" on unanswerable questions (of 3) | **3** | 0 (3 invented figures) |
| Evidence hit rate@5 (answerable questions) | 14 of 17 (82%) | — |
| Correct when the evidence was retrieved | **14 of 14** | — |
| Answers citing only supplied sources | 20 of 20 | — |
| Serious unsupported claims | 1 (Q16) | Most answers |
| Answers cut off at the 512-token limit | 0 | 3 |
| Average prompt tokens | 1,690 | 48 |
| Average output tokens | 304 | 310 |
| Generation speed (tokens/s) | 10.44 | 11.50 |
| Prompt processing (tokens/s) | 52.5 | 54.3 |
| Average model time per answer (s) | 61.7 | 28.0 |
| Average total time per question (s) | 72.1 | 36.9 |

- **RAG is what makes the 2B model usable for doctrine questions.** Without the documents it does not even recognise most of the terms as military.
- **RAG doubles the time per answer** on the CPU, almost all of it in reading the retrieved passages (about 1,700 tokens at 52 tokens/s).
- **Retrieval is now the weak point,** not the model. Improving retrieval (see Next steps) would raise the score more than changing the model.

### Against the earlier CPU runs

| Measurement | CPU 2B with RAG (doctrine) | CPU 2B with RAG (tutorial fixture) | CPU 2B, IFEval (model only) |
|---|---:|---:|---:|
| Generation speed (tokens/s) | 10.44 | 11.7 | 9.00 |
| Prompt processing (tokens/s) | 52.5 | about 58 | 49.3 |
| Average prompt tokens | 1,690 | 184 | about 50 |
| Average output tokens | 304 | 76 | 245 |
| Average model time per answer (s) | 61.7 | 11.4 | 28.6 |
| System RAM increase (GB) | 5.6 | 3.4 | 3.7 |
| SoC peak temperature (°C) | 66.5 | 65.6 | 66.5 |

- **Longer prompts slow generation a little:** 10.44 tokens/s with 1,700-token prompts, against 11.7 with 184-token prompts.

## Results

### Answers scored (main pass)

| Question | Expected (short) | RAG correct? | Evidence in top 5? | RAG notes | Baseline correct? | Baseline notes | RAG total (s) | Baseline total (s) |
|---|---|:---:|:---:|---|:---:|---|---:|---:|
| Q01 MDMP steps | 7 steps, receipt of mission … orders production | **Yes** | Yes | Cites FM 5-0 p22, p87 | No | Invented steps | 78.6 | 37.6 |
| Q02 TLP steps | 8 steps, receive the mission … supervise and refine | **Yes** | Yes | | No | Invented steps, credited to Patton; cut off | 73.8 | 53.9 |
| Q03 OPORD paragraphs | Situation, mission, execution, sustainment, command and signal | No | **No** | Said the evidence was insufficient (retrieved index pages) | No | Invented sections | 64.3 | 50.6 |
| Q04 One-third, two-thirds rule | One-third of planning time for the HQ, two-thirds for subordinates | No | **No** | Said the rule is not in the supplied text | No | Described a supply rule | 58.1 | 43.4 |
| Q05 Valid COA criteria | Feasible, acceptable, suitable, distinguishable, complete | **Yes** | Yes | | No | Generic decision-making criteria | 86.6 | 44.2 |
| Q06 Operations process | Plan, prepare, execute, assess | **Yes** | Yes | | No | Business operations; cut off | 73.1 | 54.2 |
| Q07 Types of security operations | Screen, guard, cover, area security | **Yes** | Yes | | No | Cybersecurity | 83.6 | 38.5 |
| Q08 Purpose of security operations | Early warning, reaction time and maneuver space, develop the situation | **Yes** | Yes | | No | Cybersecurity | 84.2 | 32.6 |
| Q09 Principles of mission command | 7 principles | **Yes** | Yes | | No | Invented principles, credited to John Boyd | 69.8 | 41.4 |
| Q10 METT-TC | Mission, enemy, terrain and weather, troops and support available, time available, civil considerations | **Yes** | Yes | | No | Wrong expansion | 89.8 | 25.6 |
| Q11 PMESII-PT | Political … physical environment, time | **Yes** | Yes | Added short descriptions of each variable that are not from the documents | No | Wrong (repeated "political", added "internal security") | 82.9 | 45.6 |
| Q12 CCIR | Information requirement critical to timely decision making | **Yes** | Yes | | No | Vague and partly invented; cut off | 84.7 | 54.2 |
| Q13 Center of gravity | 2018 and 2004 wording | **Yes** | Yes | Gave both editions' wording | No | Physics definition | 79.6 | 30.6 |
| Q14 Commander's intent | 2018 wording | **Yes** | Yes | | Partly | General idea right, invented history | 75.3 | 28.6 |
| Q15 Battle rhythm | Deliberate daily schedule … synchronize staff actions | **Yes** | Yes | | No | Described music in video games | 54.3 | 40.2 |
| Q16 SINCGARS | Single-channel ground and airborne radio system | No | **No** | Said insufficient evidence, then gave an invented expansion "from external knowledge" | No | Invented expansion | 43.9 | 17.7 |
| Q17 Decisive point | Geographic place, key event, critical factor or function … | **Yes** | Yes | | No | Business "turning point" | 71.8 | 35.9 |
| Q18 Abrams main gun range (not in documents) | Should say not given | **Yes** | — | Said not in the documents | No | Invented "155 mm, 3,000 m" | 55.3 | 21.9 |
| Q19 Army FY2022 budget (not in documents) | Should say not given | **Yes** | — | Said not in the documents | No | Invented "$1,378.4 billion" | 70.1 | 19.4 |
| Q20 Bradley top road speed (not in documents) | Should say not given | **Yes** | — | Said not in the documents | No | Invented "50 mph" | 61.5 | 21.9 |

"Evidence in top 5" means at least one of the 5 supplied passages contains the expected answer; it was checked by searching the supplied passages for the answer's key phrase. The answers were scored by hand against the answer key.

- **The 3 retrieval misses:** for Q03 the search returned index pages of FM 5-0 that list "paragraph" many times; for Q04 it returned other planning-time passages; for Q16 it returned other dictionary entries instead of the acronym list. In all three, the answer is in the corpus (FM 5-0 p14 and p33, both dictionaries' acronym lists) but did not rank in the top 5.
- **Citations:** every RAG answer cited only the supplied sources ([S1]–[S5]); none cited a source that was not supplied.
- **Q13 handled the two dictionary editions well:** it quoted the 2018 definition from FM 5-0 and ADP 5-0 and the 2004 one from JP 1-02.
- **Baseline answers sound confident even when wrong,** including invented history (Patton, John Boyd) and invented figures. This is the main risk RAG removes.

### Speed (RAG main pass, 20 questions)

| Measurement | Value |
|---|---:|
| Prompt tokens (5 passages + question + instructions) | 1,195–2,511 (average 1,690) |
| Prompt processing | 52.5 tokens/s (average 32.2 s per answer) |
| Output tokens | 86–508 (average 304) |
| Generation speed | 10.44 tokens/s (range 6.65–11.28) |
| Model time per answer (prompt count + Ollama request) | average 61.7 s |
| Embedding model, tokenizer and index load, per question | 10.2 s |
| Retrieval (embed the question and search 4,473 chunks) | 0.12 s |
| Total time per question | average 72.1 s (range 44–90 s) |
| Model load into Ollama (first question) | 6.1 s |
| The pipeline's prompt count against Ollama's | Equal for all 45 requests |
| Total run time (45 requests) | 41.2 min |

- **Reading the passages is the biggest cost.** At 52 tokens/s, 1,700 tokens take about 32 s before the first word of the answer.
- **The repeat answers' prompts took about 0.1 s,** because Ollama reused prompts it had cached from the main pass. Their generation speed (10.54 tokens/s) is comparable; their prompt times are not, so they are left out of the averages above.

### Resources

| Measurement | Value |
|---|---:|
| Peak Ollama process memory | 5.27 GB |
| System RAM start → peak | 3.3 → 8.9 GB (increase 5.6 GB) |
| Ollama CPU use (% of all 8 cores) | 76% |
| Whole-system CPU use | 81% |
| NPU interrupts in the window | 0 (NPU not used) |
| Big-core clock (MHz, max 2304) | 2304 in every sample |

- **Memory is higher than in the model-only run** (5.6 against 3.7 GB): Ollama grew to 5.3 GB with the longer prompts and its prompt cache, and the RAG container (PyTorch, embedding model and index) adds about 1 GB while it runs. It is still within the 8 GB target.

### Thermal and fan behaviour

| | RAG doctrine run | RAG fixture run | CPU 2B IFEval run |
|---|---:|---:|---:|
| SoC start / average / peak (°C) | 52.7 / 63.5 / 66.5 | 54.5 / 60.6 / 65.6 | 54.3 / 64.5 / 66.5 |
| Hottest CPU core peak (°C) | 69.3 | 68.4 | 68.4 |
| NPU / GPU peak (°C) | 63.8 / 61.9 | 62.8 / 61.0 | 62.9 / — |
| Fan at full speed (PWM 255) | 77% | 51% | 99% |
| Fan at a lower step (PWM 64–192) | 4% | 3% | 0% |
| Fan off (PWM 0) | 19% | 46% | 1% |

- **No throttling:** the SoC stayed below 67 °C, far from 85 °C, and the big cores stayed at 2,304 MHz.

## V&V outcome

### Verification

| ID | Check | Result | Evidence |
|---|---|:---:|---|
| V-01 | Runtime and pipeline versions | **Pass** | Ollama 0.40.3 in every log record; RAG image `is2-local-ai-rag` ID `703bbd2a…` |
| V-02 | Expected weights | **Pass** | Ollama ID `1e2d21a4f03a` in every record; embedding `5c38ec7c` and tokenizer `15852e8c` revisions recorded |
| V-03 | Same settings for every question | **Pass** | Temperature 0, seed 42, context 4,096, 512-token limit, thinking off, k = 5, same index (`dc5b9553…`) in every RAG record |
| V-04 | Completed without errors | **Pass** | All 45 requests answered; no failed requests, invalid citation IDs or thinking output |
| V-05 | Truncated answers | **Pass (RAG)** | 0 of 25 RAG answers hit the limit. 3 of 20 baseline answers did (Q02, Q06, Q12), all of them wrong anyway |
| V-06 | Resource log complete | **Pass** | 2,472 rows; largest gap 2.0 s; no `unreachable` entries |
| V-07 | Model was actually loaded | **Pass** | Ollama process up to 5.3 GB; system RAM +5.6 GB |
| V-08 | Local only | **Pass** | Ollama on `127.0.0.1:11435`; the pipeline forces Hugging Face offline mode and loads local files only |
| V-09 | Repeatable | **Pass** | Q01–Q05 RAG answers identical, word for word, in the repeat |
| V-10 | Ran on the intended processor | **Pass** | NPU interrupts 0; Ollama CPU use 76% |
| V-11 | Prompt budget measured correctly | **Pass** | The pipeline's preflight count equals Ollama's `prompt_eval_count` for all 45 requests; every RAG prompt kept all 5 passages |
| V-12 | Answer key grounded in the corpus | **Pass** | Every expected answer was found in the indexed text at the listed pages before the run |

### Validation

The tutorial's "definition of done" gives the checks; the targets below are proposals.

| ID | Measure | Proposed target | Result |
|---|---|---|---|
| RAG-01 | Correct answers to answerable questions, RAG | ≥ 80% | 14 of 17 (82%) **Pass** |
| RAG-02 | Proper abstention on unanswerable questions, RAG | 3 of 3 | 3 of 3 **Pass** |
| RAG-03 | Citations point only to supplied sources | All answers | 20 of 20 **Pass** |
| RAG-04 | Serious unsupported claims, RAG | 0 | 1 (Q16) **Fail** |
| RAG-05 | RAG better than baseline | More correct answers, fewer invented ones | 17 against 0 correct; 1 against 3+ invented **Pass** |
| RAG-06 | Evidence hit rate@5 | ≥ 90% | 14 of 17 (82%) **Fail** |
| RAG-07 | Offline restart (tutorial Step 10) | Works after a disconnected restart | **Not run** |
| RAG-08 | Time per RAG answer | Report | 72 s (61.7 s model, 10.2 s load) |
| VAL-04 | Peak model memory | ≤ 8 GB | 5.6 GB **Pass** |
| VAL-05 | Thermal | SoC < 85 °C, no sustained throttling | 66.5 °C **Pass** |

## Pipeline check: tutorial fixture

Before the corpus was added, the pipeline was checked on the RAG tutorial's fictional "Cedar Module" document (4 sentences, 4 questions), with the same model and settings. RAG answered all 4 correctly with citations, including saying the document does not give the battery capacity. The baseline answered none correctly and invented answers for 2. The answers were identical in a repeat. There was one minor unsupported claim (linking the USB-C connection to the power-cable rule). Generation ran at 11.7 tokens/s and a RAG answer took about 11 s of model time. That run's log is `software/rag/logs/fixture_cpu_runs.jsonl`.

## Setup notes

- **Corpus:** the 5 PDFs from `docs/sources` copied into `software/rag/data/documents/` (gitignored) and indexed with `rag.py ingest`. Indexing took 16.4 min on the board. 6 pages had no extractable text (blank or image-only pages): JP 1-02 p736, DOD Dictionary 2018 p2, p393 and p394, FM 3-98 p203 and FM 5-0 p403.
- **Question set:** written for this test from the corpus, with each expected answer checked in the indexed text first. Three questions (Q13, Q14, Q17) have different wording in the 2004 and 2018 dictionaries; the answer key accepts either if the edition is clear. Three are deliberately not answerable from the corpus (Q18–Q20); their absence was checked by searching the indexed text.
- **Docker image instead of a Python environment.** The pipeline's pinned packages need Python 3.12, and the board has 3.11, so the pipeline ran in the project's `software/rag/Dockerfile` image. Each question is a new `docker run` with `--network host`, pointed at the board's Ollama through `OLLAMA_URL`. The compose stack's own Ollama service was not used.
- **Qwen3.5 changes to the pipeline** (committed earlier): `download_models.py` maps the Qwen3.5 tokenizers, and the preflight leaves out ` /no_think` for Qwen3.5, which makes the preflight equal Ollama's count. The default model (`qwen3:4b-instruct-2507-q4_K_M`) is unchanged.
- **Ollama setting:** `keep_alive` was 10 minutes (the pipeline's setting), so the model stayed loaded between questions.
- **Scoring** was done by hand against the answer key, as the tutorial says. Retrieval hits were checked automatically by searching the supplied passages for each answer's key phrase.
- **No power data:** the board cannot measure its own power, and no meter was available.

## Next steps

1. **Improve retrieval,** which caused all 3 misses. Options: retrieve more passages (k = 8–10, which still fits the 4,096-token context with 300-token chunks), add keyword (BM25) search alongside the embedding search, or leave the index pages and acronym lists out of the corpus or chunk them separately.
2. **Stop the model adding outside knowledge** after saying the evidence is insufficient (Q16), for example by tightening the system prompt, and recheck.
3. **Keep the pipeline running as a service.** Loading the retrieval model for each question costs about 10 s.
4. **Cut the prompt-reading time:** the NPU reads the same prompts 2.8 times as fast (148 against 52 tokens/s) and answers in 53 s instead of 72 s with the same accuracy ([NPU-Qwen2B-Rag.md](NPU-Qwen2B-Rag.md)); fewer or shorter passages also help.
5. **Run the offline restart check** (tutorial Step 10) with the board disconnected from the network.

## Raw data

On the board:

| Item | Location |
|---|---|
| Run log (every question, answer, supplied evidence, token counts and timings) | `software/rag/logs/doctrine_cpu_runs.jsonl` |
| Answer key | `software/rag/eval/doctrine_questions.json` (in the repository) |
| Index and manifest | `software/rag/data/index/` |
| Console log (answers as printed) | `~/is2-local-ai/benchmark_results/rag_doctrine_cpu.log` |
| Resource log | `~/is2-local-ai/benchmark_results/resources_20261123T204118Z.csv` |
| Fan log | `~/is2-local-ai/benchmark_results/fan_20261123T203918Z.csv` |

`software/rag/data/`, `models/` and `logs/` are gitignored.
