"""One-time download of the embedding model and the chat model's tokenizer.

Run once while online. Do not rerun during an experiment: a newer revision
would require reindexing (embedding) or change token budgeting (tokenizer).
"""
import argparse
import json
from pathlib import Path
from huggingface_hub import HfApi, snapshot_download

ROOT = Path(__file__).resolve().parent
EMBEDDING_REPO = "BAAI/bge-small-en-v1.5"
# Ollama tag -> Hugging Face repo holding the same tokenizer and chat template.
TOKENIZER_REPOS = {
    "qwen3:4b-instruct-2507-q4_K_M": "Qwen/Qwen3-4B-Instruct-2507",
    "qwen3:8b": "Qwen/Qwen3-8B",
}


def tokenizer_dir(model):
    return ROOT / "models" / "tokenizers" / model.replace(":", "_").replace("/", "_")


def download(repo, target, patterns):
    revision = HfApi().model_info(repo).sha
    snapshot_download(repo_id=repo, revision=revision,
                      local_dir=str(target), allow_patterns=patterns)
    (target / "download_manifest.json").write_text(
        json.dumps({"repo": repo, "revision": revision}, indent=2),
        encoding="utf-8")
    print(f"Downloaded {repo} revision {revision} to {target}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="qwen3:4b-instruct-2507-q4_K_M",
                        choices=sorted(TOKENIZER_REPOS),
                        help="Ollama model whose tokenizer to download")
    parser.add_argument("--skip-embedding", action="store_true",
                        help="Only download the tokenizer")
    args = parser.parse_args()
    if not args.skip_embedding:
        download(EMBEDDING_REPO, ROOT / "models" / "embedding",
                 ["*.json", "*.txt", "*.safetensors", "*.model"])
    # Tokenizer and chat template only; no weights (Ollama holds the GGUF).
    download(TOKENIZER_REPOS[args.model], tokenizer_dir(args.model),
             ["*.json", "*.txt", "*.jinja"])


if __name__ == "__main__":
    main()
