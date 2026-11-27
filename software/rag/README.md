# Local RAG

Implementation of [docs/Local_AI_Plugin_RAG_Tutorial.md](../../docs/Local_AI_Plugin_RAG_Tutorial.md), adapted to the Ollama server used for the model evaluation.

## Differences from the tutorial

- **Generation goes through Ollama** (`/api/chat` on `127.0.0.1:11434`), not `llama-server`. Default model: `qwen3:4b-instruct-2507-q4_K_M`. Choose another with `--model`.
- **Token budgeting:** Ollama has no `/apply-template` or `/tokenize`, so prompts are counted with the model's Hugging Face tokenizer and chat template, downloaded once at a pinned revision. Each run logs both this preflight count and Ollama's `prompt_eval_count`. They matched on the fixture.
- **`num_ctx` is sent with every request**, so the server context always equals `--context-size` (default 4096). Ollama reloads the model when this value changes.
- Hybrid models are sent `think: false`. Any thinking output prints a warning. The preflight copies what Ollama's `qwen3` template does with thinking off: it appends ` /no_think` to the last user message and adds an empty `<think></think>` block. Other hybrid templates (such as `qwen3.5`) may differ, so compare the preflight with `prompt_eval_count` the first time you use one.
- Questions longer than the embedding model's 512-token limit are rejected rather than silently truncated.
- Each run log records a UTC timestamp, the Ollama version, the model digest, `k`, and the index manifest with its SHA-256. Rebuilding the index overwrites `manifest.json`, so the log's copy shows which index a run used.
- Ollama silently truncates over-long prompts. A warning prints if the prompt fills the context.

## Setup (once, online)

```powershell
$python = "C:\Users\clarka14\.venvs\is2-local-ai\Scripts\python.exe"
& $python -m pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu
& $python -m pip install -r software/rag/requirements.txt
& $python software/rag/download_models.py
```

`download_models.py --model qwen3:8b --skip-embedding` fetches another model's tokenizer. Qwen3.5 tags (`qwen3.5:2b-q4_K_M`, `qwen3.5:2b`, `qwen3.5:4b`) are mapped too. Their Ollama renderer adds no ` /no_think` with thinking off, so the preflight leaves it out for them; on the Rock 5T it matched `prompt_eval_count` exactly for `qwen3.5:2b-q4_K_M` ([docs/testing/CPU-Qwen2B-Rag.md](../../docs/testing/CPU-Qwen2B-Rag.md)).

## Use

Put `.txt`/`.pdf` files in `software/rag/data/documents/`, then:

```powershell
& $python software/rag/rag.py ingest
& $python software/rag/rag.py search "What connection does Cedar use to communicate with its host?"
& $python software/rag/rag.py ask "What connection does Cedar use to communicate with its host?"
& $python software/rag/rag.py baseline "What connection does Cedar use to communicate with its host?"
```

`data/`, `models/` and `logs/` are gitignored. Each `ask`/`baseline` run appends to `logs/runs.jsonl`.

## Docker stack

The RAG pipeline is part of the root stack (`compose.yaml` at the repo root, `app` service). See the root `README.md`, "Docker stack", for setup. From the repo root:

```powershell
docker compose up -d --build
docker compose build app
docker compose run --rm app software/rag/download_models.py   # once, online; skip if models/ is populated
docker compose run --rm app software/rag/rag.py ingest
docker compose run --rm app software/rag/rag.py ask "What connection does Cedar use to communicate with its host?"
```

`data/`, `models/` and `logs/` here are mounted into `app`, so the existing corpus, index, tokenizers and run log are reused. `rag.py --server` defaults to `$OLLAMA_URL`, which the stack sets to its `ollama` service. Outside Docker it falls back to `127.0.0.1:11434`.

`Dockerfile` here is a standalone RAG-only image for boards where the stack's Ollama isn't used (`docker run --network host -e OLLAMA_URL=...`, as in `docs/testing/CPU-Qwen2B-Rag.md`).
