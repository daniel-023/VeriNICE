from __future__ import annotations

import asyncio
import threading
from functools import lru_cache
from typing import Any, List, Optional, Sequence, Tuple

import numpy as np

from .errors import EvidenceRetrievalConfigurationError, EvidenceRetrievalError
from .settings import settings


QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "
PASSAGE_CACHE_SIZE = 8

_model: Optional[Any] = None
_model_lock = threading.Lock()


def is_available() -> bool:
    return settings.embedding_model_path.is_dir()


def warm() -> None:
    """Load the local model and run one content-free inference before readiness."""
    _encode(["A source contains relevant evidence."])


def _load_model() -> Any:
    global _model
    if _model is not None:
        return _model
    if not is_available():
        raise EvidenceRetrievalConfigurationError(
            "The local evidence embedding model is missing. Run ./run-verinice --prepare."
        )
    with _model_lock:
        if _model is not None:
            return _model
        try:
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(
                str(settings.embedding_model_path),
                device="cpu",
                local_files_only=True,
            )
        except Exception as error:
            raise EvidenceRetrievalConfigurationError(
                "The packaged evidence embedding model could not be loaded. "
                "Run ./run-verinice --prepare."
            ) from error
        _model = model
        return model


def _encode(texts: Sequence[str], instruction: str = "") -> np.ndarray:
    if not texts:
        return np.empty((0, 0), dtype="float32")
    model = _load_model()
    try:
        vectors = model.encode(
            [f"{instruction}{text}" for text in texts],
            batch_size=max(1, min(32, len(texts))),
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype="float32")
    except EvidenceRetrievalConfigurationError:
        raise
    except Exception as error:
        raise EvidenceRetrievalError("Local evidence embedding inference failed.") from error


@lru_cache(maxsize=PASSAGE_CACHE_SIZE)
def _cached_passage_vectors(
    passages: Tuple[str, ...], cache_key: str
) -> np.ndarray:
    # cache_key deliberately participates in the key so immutable demo cases do not collide.
    return _encode(passages)


def _passage_vectors(
    passages: Tuple[str, ...], cache_key: Optional[str]
) -> np.ndarray:
    if cache_key is None:
        return _encode(passages)
    return _cached_passage_vectors(passages, cache_key)


async def similarity_matrix(
    queries: Sequence[str],
    passages: Sequence[str],
    *,
    cache_key: Optional[str] = None,
) -> List[List[float]]:
    if not queries or not passages:
        return [[0.0 for _ in passages] for _ in queries]
    passage_tuple = tuple(passages)
    passage_vectors, query_vectors = await asyncio.to_thread(
        lambda: (
            _passage_vectors(passage_tuple, cache_key),
            _encode(queries, QUERY_INSTRUCTION),
        )
    )
    if (
        not isinstance(passage_vectors, np.ndarray)
        or not isinstance(query_vectors, np.ndarray)
        or passage_vectors.ndim != 2
        or query_vectors.ndim != 2
        or passage_vectors.shape[0] != len(passages)
        or query_vectors.shape[0] != len(queries)
        or passage_vectors.shape[1] != query_vectors.shape[1]
    ):
        raise EvidenceRetrievalError(
            "The embedding model returned an invalid evidence score matrix."
        )
    if not np.isfinite(query_vectors).all() or not np.isfinite(passage_vectors).all():
        raise EvidenceRetrievalError(
            "The embedding model returned non-finite evidence vectors."
        )
    # einsum avoids spurious overflow warnings emitted by some macOS BLAS
    # builds for this small normalized dot product.
    scores = np.einsum("qd,pd->qp", query_vectors, passage_vectors, optimize=False)
    if not np.isfinite(scores).all():
        raise EvidenceRetrievalError(
            "The embedding model returned non-finite evidence scores."
        )
    return scores.tolist()
