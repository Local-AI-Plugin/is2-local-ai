# Python tooling for the Local AI Plug-In: RAG pipeline (software/rag),
# knowledge-base client (software/knowledge_base) and the mode runner
# (software/runtime/ask.py). CPU only. Ollama and Fuseki are separate
# services in compose.yaml, which also sets OLLAMA_URL and FUSEKI_URL.
#
# Run:  docker compose run --rm app <script> [args]   (see README.md)
FROM python:3.12.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/software/rag:/app/software/knowledge_base

WORKDIR /app

# CPU-only torch first, from the PyTorch index (same as software/rag/README.md).
RUN pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu

COPY software/rag/requirements.txt software/rag/requirements.txt
COPY software/knowledge_base/requirements.txt software/knowledge_base/requirements.txt
RUN pip install -r software/rag/requirements.txt \
                -r software/knowledge_base/requirements.txt

COPY software/ software/

# Corpus, models, index, ontology files and logs are mounted, not baked in.
RUN useradd --create-home app \
 && mkdir -p software/rag/data software/rag/models software/rag/logs \
             software/knowledge_base/logs software/runtime/logs docs/knowledge \
 && chown -R app:app /app
USER app

ENTRYPOINT ["python"]
CMD ["software/runtime/ask.py", "--help"]
