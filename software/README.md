# Running the software

This folder holds the Local AI Plug-In's software: a small local LLM (served by Ollama) that can answer from a document corpus (RAG), from a knowledge graph (KG), or from both.

| Folder | What it does |
|---|---|
| [`rag/`](rag/) | Document retrieval: embeds PDFs/text into a FAISS index and passes the top passages to the LLM |
| [`knowledge_base/`](knowledge_base/) | Knowledge graph: Apache Jena Fuseki holds the UGV mission-planning ontology. Saved SPARQL queries give the LLM graph rows |
| [`runtime/`](runtime/) | `ask.py`: asks one question in a chosen mode (LLM only, + RAG, + KG, + both) and logs the run |

Everything runs in Docker from **one compose stack at the repo root** ([`compose.yaml`](../compose.yaml)). Run every `docker compose` command below from the repo root.

## How the pieces connect

```text
            docker compose network
 ┌──────────────────────────────────────────────┐
 │  app  ──►  ollama:11434   (LLM)              │
 │   │                                          │
 │   ├──►  fuseki:3030/kg    (knowledge graph)  │
 │   └──►  software/rag/data (FAISS index, a    │
 │          mounted folder, not a service)      │
 └──────────────────────────────────────────────┘
   ollama and fuseki also listen on 127.0.0.1
   so scripts run from a host Python venv work too
```

| Service | Role | Host port |
|---|---|---|
| `ollama` | Serves the LLM. Models live in the Docker volume `local-ai-models` | `127.0.0.1:11434` |
| `ollama-pull` | Runs once at startup and pulls `$LLM_MODEL` if missing | none |
| `fuseki` | Knowledge-graph server. Data lives in the volume `kg-data` | `127.0.0.1:3030` (web UI too) |
| `app` | Python image with all the scripts. Not a server: each `docker compose run --rm app ...` runs one script and exits | none |

The `app` container finds the others through `OLLAMA_URL=http://ollama:11434` and `FUSEKI_URL=http://fuseki:3030/kg`, which compose sets.

## Requirements

- Docker Desktop (or Docker Engine with Compose v2.20+), running.
- Several GB of free RAM: the default 4B model (q4) needs about 3 GB, plus Fuseki (up to 1 GB) and the app's embedding model. No GPU needed.
- Internet for the first setup only (image builds, model pull, embedding/tokenizer download). After that, everything runs offline.
- **No other Ollama using port 11434 or the `local-ai-models` volume.** If you used the old standalone container, stop it first: `docker stop local-ai-ollama`.

## First-time setup

```bash
# 1. Start Ollama (pulls the default model) and Fuseki
docker compose up -d --build
docker compose ps                      # ollama and fuseki should show "healthy"

# 2. Build the app image (installs CPU torch; takes a few minutes the first time)
docker compose build app

# 3. RAG: download the embedding model and tokenizer into software/rag/models/
docker compose run --rm app software/rag/download_models.py

# 4. RAG: copy the corpus into software/rag/data/documents/ and build the index
#    (reference copies of the PDFs are in docs/sources/)
docker compose run --rm app software/rag/rag.py ingest

# 5. KG: load the UGV ontology and Scenario 1 into Fuseki, then check it
docker compose run --rm app software/knowledge_base/load_kg.py
docker compose run --rm app software/knowledge_base/kg_smoke.py   # should print PASS
```

Steps 3–5 only need repeating when the inputs change: a new model, new documents, or a changed ontology. `software/rag/data/`, `software/rag/models/` and the logs folders are bind-mounted from your checkout and gitignored, so they persist between runs and are shared with host-venv runs.

## Asking questions: the four modes

`software/runtime/ask.py` answers one question with a fixed source of context. You choose the source, not the model, so a test never depends on the model picking the right one.

```bash
# LLM only: no extra context
docker compose run --rm app software/runtime/ask.py --mode llm \
  "What are the seven steps of the military decision-making process (MDMP)?"

# LLM + RAG: top-k document passages, cited [S1], [S2], ...
docker compose run --rm app software/runtime/ask.py --mode rag --k 5 \
  "What are the seven steps of the military decision-making process (MDMP)?"

# LLM + KG: rows from a saved graph query, cited [G1], [G2], ...
docker compose run --rm app software/runtime/ask.py --mode kg \
  --query-id cq1_1 --task "Observe an inspection area"

# LLM + RAG + KG: both
docker compose run --rm app software/runtime/ask.py --mode rag+kg \
  --query-id cq1_1 --task "Observe an inspection area"
```

- **KG modes need `--query-id`**, one of the queries in [`knowledge_base/queries/registry.json`](knowledge_base/queries/registry.json) (currently only `cq1_1`). `--task` and `--mission` narrow it to named entities. The question defaults to the query's wording; pass your own as the positional argument.
- **Every mode sends identical model settings** (temperature 0, seed 42, same context size and output limit). Only the context changes, so answers are comparable.
- **The output** is the answer, then the sources it was given (`[S1] file (page N)`, `[G1] row values`), then any warnings: invalid citations, truncation, or a full context window.
- **Each run appends one JSON line to `software/runtime/logs/runs.jsonl`** with the mode, full prompt, evidence, answer, model digest, token counts and timings. Use it to compare modes side by side.
- Options: `--k` (passages, default 5), `--context-size` (default 4096), `--model` (default `$LLM_MODEL`).

Test questions with checked answers: [`rag/eval/doctrine_questions.json`](rag/eval/doctrine_questions.json) (documents) and [`knowledge_base/queries/paraphrases.json`](knowledge_base/queries/paraphrases.json) (graph).

## Component tests

The individual pipelines can still be run on their own:

```bash
# RAG only
docker compose run --rm app software/rag/rag.py search   "question"   # retrieval, no LLM
docker compose run --rm app software/rag/rag.py ask      "question"   # RAG answer
docker compose run --rm app software/rag/rag.py baseline "question"   # LLM only

# KG only
docker compose run --rm app software/knowledge_base/kg_query.py cq1_1 --rows-only  # graph rows vs expected
docker compose run --rm app software/knowledge_base/kg_query.py cq1_1              # rows + LLM answer
docker compose run --rm app software/knowledge_base/kg_agent.py                    # LLM picks the query; scores paraphrases.json
```

Details: [`rag/README.md`](rag/README.md), [`knowledge_base/README.md`](knowledge_base/README.md).

## Using another model

```bash
# PowerShell: $env:LLM_MODEL = "qwen3:8b"     bash: export LLM_MODEL=qwen3:8b
docker compose up -d                                                  # pulls it
docker compose run --rm app software/rag/download_models.py --model qwen3:8b --skip-embedding
docker compose run --rm app software/runtime/ask.py --mode rag "question"
```

The model needs a matching tokenizer in `software/rag/models/tokenizers/` for prompt budgeting. `download_models.py` maps the supported tags; add new ones to `TOKENIZER_REPOS` there.

## Running from a host Python venv instead

Ollama and Fuseki are published on `127.0.0.1`, so the same scripts work outside Docker with the stack up. Install `software/rag/requirements.txt` (CPU torch first, see [`rag/README.md`](rag/README.md)) and `software/knowledge_base/requirements.txt`, then run, for example, `python software/runtime/ask.py --mode kg --query-id cq1_1`. Use `127.0.0.1`, not `localhost`: on Windows, `localhost` adds about 2 s per request.

## Day-to-day commands

| Task | Command |
|---|---|
| Start / check the stack | `docker compose up -d` / `docker compose ps` |
| Free RAM for `llm`/`rag` measurements | `docker compose stop fuseki` |
| Follow logs | `docker compose logs -f ollama` (or `fuseki`) |
| Rebuild after code changes | `docker compose build app` |
| Stop everything (data kept) | `docker compose down` |

**Don't run `docker compose down -v`.** It deletes the Fuseki database and can delete `local-ai-models`, which forces the models to be downloaded again.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `up` fails: port 11434 already allocated | Another Ollama is running. Stop it (`docker stop local-ai-ollama`, or quit the Ollama desktop app) |
| `error: no Fuseki at http://fuseki:3030/kg` | `docker compose up -d fuseki`, then `load_kg.py` if the graph is empty |
| `kg_smoke.py` fails or KG rows are empty | Reload the graph: `docker compose run --rm app software/knowledge_base/load_kg.py` |
| `No tokenizer for <model>` | `download_models.py --model <tag> --skip-embedding` |
| `Embedding model changed` / `Index/metadata mismatch` | `rag.py ingest` again |
| Code changes not picked up | `docker compose build app`: scripts are baked into the image, only data/logs are mounted |
| The first answer takes minutes | Normal on CPU: Ollama loads the model on first use and keeps it loaded for 10 minutes |
