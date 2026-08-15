from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .schemas import (
    AtomSupportClassification,
    EvidenceRelation,
    NLIAtomEvidence,
    NLIRelation,
    PipelineAtom,
    SupportClassificationResponse,
)
from .settings import settings


MAX_SEQUENCE_LENGTH = 512
BATCH_SIZE = 16


class NLIClassificationError(RuntimeError):
    pass


class NLIClassificationConfigurationError(NLIClassificationError):
    pass


_tokenizer: Optional[Any] = None
_model: Optional[Any] = None
_labels: Optional[Dict[int, NLIRelation]] = None
_load_error: Optional[str] = None
_load_lock = threading.Lock()


def _relation_for_label(label: str) -> NLIRelation:
    normalized = label.strip().lower()
    aliases = {
        "entailment": NLIRelation.entailment,
        "entails": NLIRelation.entailment,
        "contradiction": NLIRelation.contradiction,
        "contradicts": NLIRelation.contradiction,
        "neutral": NLIRelation.neutral,
    }
    try:
        return aliases[normalized]
    except KeyError as error:
        raise NLIClassificationConfigurationError(
            f"The configured NLI model exposes an unsupported label: {label}."
        ) from error


def _label_mapping(config: Any) -> Dict[int, NLIRelation]:
    raw = getattr(config, "id2label", None)
    if not isinstance(raw, dict):
        raise NLIClassificationConfigurationError(
            "The configured NLI model does not expose an id2label mapping."
        )
    mapping = {int(index): _relation_for_label(str(label)) for index, label in raw.items()}
    if set(mapping.values()) != set(NLIRelation):
        raise NLIClassificationConfigurationError(
            "The configured NLI model must expose entailment, contradiction, and neutral labels."
        )
    return mapping


def is_available() -> bool:
    return settings.nli_model_path.is_dir() and _load_error is None


def _load_components() -> Tuple[Any, Any, Dict[int, NLIRelation]]:
    global _tokenizer, _model, _labels, _load_error
    if _tokenizer is not None and _model is not None and _labels is not None:
        return _tokenizer, _model, _labels
    if not settings.nli_model_path.is_dir():
        raise NLIClassificationConfigurationError(
            "The local NLI model is missing. Run ./run-verigraph --prepare."
        )
    with _load_lock:
        if _tokenizer is not None and _model is not None and _labels is not None:
            return _tokenizer, _model, _labels
        try:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            tokenizer = AutoTokenizer.from_pretrained(
                str(settings.nli_model_path),
                local_files_only=True,
            )
            model = AutoModelForSequenceClassification.from_pretrained(
                str(settings.nli_model_path),
                local_files_only=True,
            )
            model.eval()
            labels = _label_mapping(model.config)
        except NLIClassificationConfigurationError as error:
            _load_error = str(error)
            raise
        except Exception as error:
            _load_error = str(error)
            raise NLIClassificationConfigurationError(
                "The packaged NLI model could not be loaded. Run ./run-verigraph --prepare."
            ) from error
        _tokenizer = tokenizer
        _model = model
        _labels = labels
        _load_error = None
        return tokenizer, model, labels


def warm() -> None:
    global _load_error
    try:
        _predict([("A source states a fact.", "A source states a fact.")])
    except NLIClassificationError as error:
        _load_error = str(error)
        raise
    _load_error = None


def _predict(pairs: Sequence[Tuple[str, str]]) -> List[NLIRelation]:
    tokenizer, model, labels = _load_components()
    if not pairs:
        return []
    predictions: List[NLIRelation] = []
    try:
        import torch

        with torch.inference_mode():
            for start in range(0, len(pairs), BATCH_SIZE):
                batch = pairs[start : start + BATCH_SIZE]
                encoded = tokenizer(
                    [premise for premise, _ in batch],
                    [hypothesis for _, hypothesis in batch],
                    padding=True,
                    truncation=True,
                    max_length=MAX_SEQUENCE_LENGTH,
                    return_tensors="pt",
                )
                indices = model(**encoded).logits.argmax(dim=-1).detach().cpu().tolist()
                predictions.extend(labels[int(index)] for index in indices)
    except NLIClassificationConfigurationError:
        raise
    except Exception as error:
        raise NLIClassificationError("Local NLI inference failed.") from error
    if len(predictions) != len(pairs):
        raise NLIClassificationError("The NLI model returned an incomplete prediction batch.")
    return predictions


def classify_support(
    atoms: Sequence[PipelineAtom],
    evidence: Sequence[NLIAtomEvidence],
) -> SupportClassificationResponse:
    # Load even for an empty span set so readiness and provider identity remain truthful.
    _load_components()
    evidence_by_atom = {item.atom_id: item for item in evidence}
    pairs: List[Tuple[str, str]] = []
    metadata: List[Tuple[str, str, str]] = []
    for atom in atoms:
        item = evidence_by_atom[atom.id]
        for span in item.spans:
            pairs.append((span.text, atom.text))
            metadata.append((atom.id, span.id, span.document_id))

    predicted = _predict(pairs)
    relations_by_atom: Dict[str, List[EvidenceRelation]] = {
        atom.id: [] for atom in atoms
    }
    for (atom_id, span_id, document_id), relation in zip(metadata, predicted):
        relations_by_atom[atom_id].append(
            EvidenceRelation(
                span_id=span_id,
                document_id=document_id,
                relation=relation,
            )
        )
    return SupportClassificationResponse(
        classifications=[
            AtomSupportClassification(
                atom_id=atom.id,
                relations=relations_by_atom[atom.id],
            )
            for atom in atoms
        ],
        model=settings.nli_model,
    )
