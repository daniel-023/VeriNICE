from __future__ import annotations

import threading
import re
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
MIN_NON_NEUTRAL_CONFIDENCE = 0.58

_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "but", "by",
    "did", "do", "does", "for", "from", "had", "has", "have", "he", "her", "his",
    "i", "in", "is", "it", "its", "of", "on", "or", "our", "she", "that", "the",
    "their", "them", "they", "this", "to", "was", "we", "were", "will", "with", "you",
}
_CONTEXT_DEPENDENT_WORDS = {"he", "her", "hers", "him", "his", "it", "its", "she", "their", "theirs", "them", "they", "this", "that", "these", "those"}
_NEGATIONS = {"no", "not", "never", "none", "neither", "without"}
_OPPOSING_TERMS = {
    frozenset(("increase", "decrease")),
    frozenset(("rise", "fall")),
    frozenset(("more", "less")),
    frozenset(("before", "after")),
    frozenset(("open", "closed")),
    frozenset(("approve", "reject")),
    frozenset(("include", "exclude")),
}
_NUMBER = re.compile(r"\b\d+(?:[.,]\d+)*(?:%|\b)")


def _stem(word: str) -> str:
    """Small deterministic normalizer for topical gating, not semantic inference."""
    for suffix in ("ments", "ment", "ingly", "edly", "ing", "ied", "ed", "ies", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            stem = word[: -len(suffix)]
            return stem + "y" if suffix in {"ied", "ies"} else stem
    return word


def _content_terms(text: str) -> set[str]:
    return {
        _stem(word)
        for word in (item.casefold() for item in _WORD.findall(text))
        if word not in _STOP_WORDS
    }


def _is_topically_relevant(sentence: str, obligation: str, context: str | None = None) -> bool:
    """Require several shared content anchors before asking NLI for a relation.

    The exact retrieved sentence is used here so neighboring context cannot make
    an unrelated highlighted span appear relevant. Context is still supplied to
    NLI after this gate for pronoun, temporal, and attribution resolution.
    """
    raw_sentence_words = [item.casefold() for item in _WORD.findall(sentence)]
    sentence_terms = _content_terms(sentence)
    obligation_terms = _content_terms(obligation)
    if not obligation_terms:
        return True
    required = 1 if len(obligation_terms) == 1 else 2 if len(obligation_terms) <= 3 else 3
    begins_with_context_reference = bool(raw_sentence_words) and raw_sentence_words[0] in _CONTEXT_DEPENDENT_WORDS
    if len(sentence_terms & obligation_terms) < required and begins_with_context_reference and context:
        sentence_terms |= _content_terms(context)
    return len(sentence_terms & obligation_terms) >= required


def _has_explicit_contradiction_anchor(
    sentence: str, obligation: str, context: str | None = None
) -> bool:
    """Require an inspectable conflict cue before emitting CONTRADICTION.

    Generic NLI models sometimes treat a related-but-different sentence as a
    contradiction.  VeriGraph is deliberately conservative: contradiction must
    be grounded in polarity, incompatible constraints, or mismatched entities.
    """
    premise = context if context and sentence.split()[:1] and sentence.split()[0].casefold() in _CONTEXT_DEPENDENT_WORDS else sentence
    premise_words = [item.casefold() for item in _WORD.findall(premise)]
    obligation_words = [item.casefold() for item in _WORD.findall(obligation)]
    if bool(_NEGATIONS & set(premise_words)) != bool(_NEGATIONS & set(obligation_words)):
        return True
    premise_numbers = set(_NUMBER.findall(premise))
    obligation_numbers = set(_NUMBER.findall(obligation))
    if premise_numbers and obligation_numbers and premise_numbers != obligation_numbers:
        return True
    premise_terms = {_stem(item) for item in premise_words}
    obligation_terms = {_stem(item) for item in obligation_words}
    if any(pair <= (premise_terms | obligation_terms) and pair & premise_terms and pair & obligation_terms
           for pair in _OPPOSING_TERMS):
        return True
    premise_names = {item.casefold() for item in _WORD.findall(premise) if item[:1].isupper()}
    obligation_names = {item.casefold() for item in _WORD.findall(obligation) if item[:1].isupper()}
    shared_names = premise_names & obligation_names
    return (
        len(premise_names) == len(obligation_names)
        and len(shared_names) >= max(1, len(obligation_names) // 2)
        and premise_names != obligation_names
    )


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


def _predict_with_confidence(pairs: Sequence[Tuple[str, str]]) -> List[Tuple[NLIRelation, float]]:
    tokenizer, model, labels = _load_components()
    if not pairs:
        return []
    predictions: List[Tuple[NLIRelation, float]] = []
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
                logits = model(**encoded).logits
                probabilities = torch.softmax(logits, dim=-1)
                confidence, indices = probabilities.max(dim=-1)
                predictions.extend(
                    (labels[int(index)], float(score))
                    for index, score in zip(
                        indices.detach().cpu().tolist(),
                        confidence.detach().cpu().tolist(),
                    )
                )
    except NLIClassificationConfigurationError:
        raise
    except Exception as error:
        raise NLIClassificationError("Local NLI inference failed.") from error
    if len(predictions) != len(pairs):
        raise NLIClassificationError("The NLI model returned an incomplete prediction batch.")
    return predictions


def _predict(pairs: Sequence[Tuple[str, str]]) -> List[NLIRelation]:
    return [relation for relation, _confidence in _predict_with_confidence(pairs)]


def classify_support(
    atoms: Sequence[PipelineAtom],
    evidence: Sequence[NLIAtomEvidence],
) -> SupportClassificationResponse:
    # Load even for an empty span set so readiness and provider identity remain truthful.
    _load_components()
    evidence_by_atom = {item.atom_id: item for item in evidence}
    pairs: List[Tuple[str, str]] = []
    metadata: List[Tuple[str, str, str, bool]] = []
    for atom in atoms:
        item = evidence_by_atom[atom.id]
        for span in item.spans:
            relevant = _is_topically_relevant(span.text, atom.text, span.context)
            # An isolated sentence strands pronouns and ellipsis, which the model
            # reads as disagreement. Judge it inside its immediate context.
            if relevant:
                pairs.append((span.context or span.text, atom.text))
            metadata.append((atom.id, span.id, span.document_id, relevant))

    predicted = _predict_with_confidence(pairs)
    relations_by_atom: Dict[str, List[EvidenceRelation]] = {
        atom.id: [] for atom in atoms
    }
    prediction_index = 0
    for atom_id, span_id, document_id, relevant in metadata:
        if relevant:
            relation, confidence = predicted[prediction_index]
            atom_text = next(atom.text for atom in atoms if atom.id == atom_id)
            span = next(item for item in evidence_by_atom[atom_id].spans if item.id == span_id)
            if relation != NLIRelation.neutral and confidence < MIN_NON_NEUTRAL_CONFIDENCE:
                relation = NLIRelation.neutral
            if relation == NLIRelation.contradiction and not _has_explicit_contradiction_anchor(
                span.text, atom_text, span.context
            ):
                relation = NLIRelation.neutral
        else:
            relation = NLIRelation.neutral
        if relevant:
            prediction_index += 1
        relations_by_atom[atom_id].append(
            EvidenceRelation(
                span_id=span_id,
                document_id=document_id,
                relation=relation,
                relevance_filtered=not relevant,
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
