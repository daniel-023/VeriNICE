"""Download the retrieval embedding model into the repository data directory.

Run through `./run-verinice --prepare`. The backend never reaches the
network at runtime, so the model is materialised in the local data directory.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile

from huggingface_hub import snapshot_download

from verinice_backend.settings import ROOT, settings


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
MODEL_LOCK = ROOT / "data" / "manifests" / "model-lock.json"
LOCAL_METADATA = ".verinice-model.json"


def locked_model() -> tuple[str, str]:
    lock = json.loads(MODEL_LOCK.read_text(encoding="utf-8"))["bge"]
    repository = str(lock["repository"])
    revision = str(lock["revision"])
    if len(revision) != 40 or any(character not in "0123456789abcdef" for character in revision):
        raise RuntimeError("The BGE model lock must contain a full lowercase commit SHA.")
    return repository, revision


def model_is_ready(destination: Path, repository: str, revision: str) -> bool:
    if not all((destination / relative_path).is_file() for relative_path in REQUIRED_FILES):
        return False
    try:
        metadata = json.loads((destination / LOCAL_METADATA).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False
    return metadata == {"repository": repository, "revision": revision}


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
    repository, revision = locked_model()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if settings.embedding_model != repository:
        raise RuntimeError(
            f"Configured embedding model {settings.embedding_model!r} does not match "
            f"the locked repository {repository!r}."
        )
    if model_is_ready(destination, repository, revision):
        print(f"Embedding model already ready at {destination}")
        return 0
    print(f"Downloading {repository}@{revision} into {destination}")
    # Stage the complete download away from the destination before copying it;
    # this also makes interrupted downloads unable to leave partial model files.
    with tempfile.TemporaryDirectory(prefix="verinice-bge-") as temporary:
        source = Path(temporary) / "model"
        snapshot_download(
            repo_id=repository,
            revision=revision,
            local_dir=str(source),
            ignore_patterns=IGNORED,
        )
        materialize_download(source=source, destination=destination)
    (destination / LOCAL_METADATA).write_text(
        json.dumps({"repository": repository, "revision": revision}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Embedding model ready at {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
