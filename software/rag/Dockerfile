# RAG CLI image (CPU only). Ollama runs in its own container; see compose.yaml.
# Corpus, downloaded models, index and logs are mounted, not baked in.
FROM python:3.12.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# CPU-only torch first, from the PyTorch index (same as README.md setup).
RUN pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY rag.py download_models.py ./

RUN useradd --create-home app \
 && mkdir -p data models logs \
 && chown -R app:app /app
USER app

ENTRYPOINT ["python", "rag.py"]
CMD ["--help"]
