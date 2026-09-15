from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env.local")


def _csv_env(name: str, default: str = "") -> tuple[str, ...]:
    return tuple(item.strip() for item in os.getenv(name, default).split(",") if item.strip())


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _path_env(name: str, default: Path) -> Path:
    path = Path(os.getenv(name, str(default)))
    return path if path.is_absolute() else ROOT / path


@dataclass(frozen=True)
class Settings:
    ollama_url: str = os.getenv(
        "VERINICE_OLLAMA_URL", os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    )
    ollama_model: str = os.getenv("VERINICE_OLLAMA_MODEL", "qwen2.5:7b")
    ollama_keep_alive: str = os.getenv("VERINICE_OLLAMA_KEEP_ALIVE", "10m")
    # The structured schema and compact few-shot examples need room alongside
    # the input claim and JSON response. This remains configurable for smaller
    # CPU-only Ollama installations.
    ollama_context_size: int = int(os.getenv("VERINICE_OLLAMA_CONTEXT_SIZE", "4096"))
    evidence_audit_context_size: int = int(
        os.getenv("VERINICE_EVIDENCE_AUDIT_CONTEXT_SIZE", "12288")
    )
    embedding_model: str = os.getenv(
        "VERINICE_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"
    )
    embedding_model_path: Path = _path_env(
        "VERINICE_EMBEDDING_MODEL_PATH",
        ROOT / "data" / "models" / "bge-small-en-v1.5",
    )
    request_timeout_seconds: float = float(
        os.getenv("VERINICE_REQUEST_TIMEOUT_SECONDS", "240")
    )
    max_llm_concurrency: int = int(
        os.getenv("VERINICE_MAX_LLM_CONCURRENCY", "4")
    )
    max_retrieval_concurrency: int = int(
        os.getenv("VERINICE_MAX_RETRIEVAL_CONCURRENCY", "1")
    )
    max_request_bytes: int = int(
        os.getenv("VERINICE_MAX_REQUEST_BYTES", "1100000")
    )
    rate_limit_per_minute: int = int(
        os.getenv("VERINICE_RATE_LIMIT_PER_MINUTE", "0")
    )
    allowed_origins: tuple[str, ...] = _csv_env(
        "VERINICE_ALLOWED_ORIGINS",
        "http://127.0.0.1:3000,http://localhost:3000",
    )
    public_demo_data_path: Path = ROOT / "data" / "demo_cases.json"
    private_demo_bundle_path: Path = _path_env(
        "VERINICE_DEMO_BUNDLE_PATH",
        ROOT / "data" / "demo" / "showcase",
    )
    require_private_catalog: bool = _bool_env(
        "VERINICE_REQUIRE_PRIVATE_CATALOG", False
    )
    expected_bundle_digest: str | None = os.getenv(
        "VERINICE_EXPECTED_BUNDLE_DIGEST"
    )


settings = Settings()
