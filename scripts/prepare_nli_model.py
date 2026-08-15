"""Materialize the pinned local NLI model for offline runtime use."""

from __future__ import annotations

from huggingface_hub import snapshot_download

from verigraph_backend.settings import settings


IGNORED = ["*.bin", "*.h5", "*.ot", "*.msgpack", "onnx/*", "openvino/*"]


def main() -> int:
    destination = settings.nli_model_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    print(
        f"Downloading {settings.nli_model}@{settings.nli_model_revision} "
        f"into {destination}"
    )
    snapshot_download(
        repo_id=settings.nli_model,
        revision=settings.nli_model_revision,
        local_dir=str(destination),
        ignore_patterns=IGNORED,
    )
    print(f"NLI model ready at {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
