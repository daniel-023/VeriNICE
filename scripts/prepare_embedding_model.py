"""Download the retrieval embedding model into the repository data directory.

Run through `./run-verigraph --prepare`. The backend never reaches the network,
so the model is materialised in the local data directory and mounted read-only
into the live backend container.
"""

from __future__ import annotations

from huggingface_hub import snapshot_download

from verigraph_backend.settings import settings


# Formats the backend never loads. Skipping them keeps the copied directory to
# the safetensors weights and their tokenizer and pooling configuration.
IGNORED = ["*.bin", "*.h5", "*.ot", "*.msgpack", "onnx/*", "openvino/*"]


def main() -> int:
    destination = settings.embedding_model_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {settings.embedding_model} into {destination}")
    snapshot_download(
        repo_id=settings.embedding_model,
        local_dir=str(destination),
        ignore_patterns=IGNORED,
    )
    print(f"Embedding model ready at {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
