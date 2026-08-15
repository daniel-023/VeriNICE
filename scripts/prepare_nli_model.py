"""Materialize the pinned local NLI model for offline runtime use."""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile

from huggingface_hub import snapshot_download

from verigraph_backend.settings import settings


IGNORED = ["*.bin", "*.h5", "*.ot", "*.msgpack", "onnx/*", "openvino/*"]
REQUIRED_FILES = (
    "config.json",
    "model.safetensors",
    "spm.model",
    "tokenizer.json",
    "tokenizer_config.json",
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
    destination = settings.nli_model_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    if model_is_ready(destination):
        print(f"NLI model already ready at {destination}")
        return 0
    print(
        f"Downloading {settings.nli_model}@{settings.nli_model_revision} "
        f"into {destination}"
    )
    # Stage the Hugging Face download away from the destination before copying
    # it persistently.
    with tempfile.TemporaryDirectory(prefix="verigraph-nli-") as temporary:
        source = Path(temporary) / "model"
        snapshot_download(
            repo_id=settings.nli_model,
            revision=settings.nli_model_revision,
            local_dir=str(source),
            ignore_patterns=IGNORED,
        )
        materialize_download(source=source, destination=destination)
    print(f"NLI model ready at {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
