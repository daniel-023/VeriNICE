"""Download the retrieval embedding model into the repository data directory.

Run through `./run-verigraph --prepare`. The backend never reaches the
network at runtime, so the model is materialised in the local data directory.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile

from huggingface_hub import snapshot_download

from verigraph_backend.settings import settings


# Formats the backend never loads. Skipping them keeps the copied directory to
# the safetensors weights and their tokenizer and pooling configuration.
IGNORED = ["*.bin", "*.h5", "*.ot", "*.msgpack", "onnx/*", "openvino/*"]
REQUIRED_FILES = (
    "config.json",
    "config_sentence_transformers.json",
    "model.safetensors",
    "modules.json",
    "tokenizer.json",
    "1_Pooling/config.json",
)


def model_is_ready(destination: Path) -> bool:
    return all((destination / relative_path).is_file() for relative_path in REQUIRED_FILES)


def materialize_download(*, source: Path, destination: Path) -> None:
    """Copy a completed internal download to the host-mounted model directory."""
    stale_cache = destination / ".cache"
    if stale_cache.exists():
        shutil.rmtree(stale_cache)
    destination.mkdir(parents=True, exist_ok=True)
    for entry in source.iterdir():
        if entry.name == ".cache":
            continue
        target = destination / entry.name
        if entry.is_dir():
            shutil.copytree(entry, target, dirs_exist_ok=True)
        else:
            shutil.copy2(entry, target)


def main() -> int:
    destination = settings.embedding_model_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    if model_is_ready(destination):
        print(f"Embedding model already ready at {destination}")
        return 0
    print(f"Downloading {settings.embedding_model} into {destination}")
    # Stage the complete download away from the destination before copying it;
    # this also makes interrupted downloads unable to leave partial model files.
    with tempfile.TemporaryDirectory(prefix="verigraph-bge-") as temporary:
        source = Path(temporary) / "model"
        snapshot_download(
            repo_id=settings.embedding_model,
            local_dir=str(source),
            ignore_patterns=IGNORED,
        )
        materialize_download(source=source, destination=destination)
    print(f"Embedding model ready at {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
