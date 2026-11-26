# Python tooling for the Local AI Plug-In: RAG pipeline (software/rag) and
# knowledge-base client (software/knowledge_base). CPU only.
# Ollama and Fuseki run outside this image (Fuseki has its own Dockerfile in
# software/knowledge_base/).
#
# Build:  docker build -t is2-local-ai .
# Run:    see the "Docker" section of README.md
FROM python:3.12.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FUSEKI_URL=http://host.docker.internal:3030/kg

WORKDIR /app

# CPU-only torch first, from the PyTorch index (same as software/rag/README.md).
RUN pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu

COPY software/rag/requirements.txt software/rag/requirements.txt
COPY software/knowledge_base/requirements.txt software/knowledge_base/requirements.txt
RUN pip install -r software/rag/requirements.txt \
                -r software/knowledge_base/requirements.txt

COPY software/ software/

# Corpus, downloaded models, index and logs live in volumes, not the image.
RUN useradd --create-home app \
 && mkdir -p software/rag/data software/rag/models software/rag/logs \
 && chown -R app:app /app
USER app
VOLUME ["/app/software/rag/data", "/app/software/rag/models", "/app/software/rag/logs"]

ENTRYPOINT ["python", "software/rag/rag.py"]
CMD ["--help"]
