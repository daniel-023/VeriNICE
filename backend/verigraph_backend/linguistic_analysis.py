from __future__ import annotations

import importlib
import threading
from typing import Any, Iterable, List, Optional, Sequence, Tuple, Union

from .schemas import (
    AtomLinguisticAnalysis,
    ClaimComposition,
    DecomposedAtom,
    LinguisticAnalysisResponse,
    LinguisticArgument,
    LinguisticCue,
    LinguisticEntity,
    LinguisticModifier,
    LinguisticSpan,
    LinguisticToken,
    LinguisticWarningCode,
    ObligationLinguisticSummary,
    ObligationRole,
    PipelineAtom,
    PropositionFrame,
    RoleAuditStatus,
)
from .text_offsets import utf16_offset


MODEL_PACKAGE = "en_core_web_sm"
MODEL_ID = "en_core_web_sm@3.8.0"


class LinguisticAnalysisError(RuntimeError):
    pass


class LinguisticAnalysisConfigurationError(LinguisticAnalysisError):
    pass


_nlp: Optional[Any] = None
_load_error: Optional[str] = None
_load_lock = threading.Lock()

_SUBJECT_DEPS = {"nsubj", "nsubjpass", "nsubj:pass", "csubj", "csubjpass", "csubj:pass", "expl"}
_DIRECT_OBJECT_DEPS = {"obj", "dobj"}
_INDIRECT_OBJECT_DEPS = {"iobj", "dative"}
_SUBJECT_COMPLEMENT_DEPS = {"attr", "acomp"}
_OBJECT_COMPLEMENT_DEPS = {"oprd"}
_CLAUSAL_COMPLEMENT_DEPS = {"xcomp", "ccomp"}
_MODIFIER_DEPS = {"advcl", "advmod", "npadvmod", "obl", "prep"}
_NEGATIONS = {"no", "not", "never", "none", "neither", "without", "cannot"}
_QUANTIFIERS = {
    "all", "every", "each", "any", "some", "no", "none", "only", "both",
    "either", "neither", "most", "many", "much", "few", "fewer", "several",
    "multiple",
}
_MODALITY = {
    "may", "might", "could", "should", "would", "must", "can", "possibly",
    "probably", "perhaps", "likely", "allegedly", "reportedly", "apparently",
    "seem", "appear", "suggest",
}
_ATTRIBUTION = {"say", "state", "claim", "report", "announce", "allege", "tell", "write"}
_TEMPORAL_LABELS = {"DATE", "TIME"}
_NUMERIC_LABELS = {"CARDINAL", "ORDINAL", "MONEY", "PERCENT", "QUANTITY"}
_TEMPORAL_MARKERS = {"after", "before", "during", "until", "when", "whenever", "while"}
_CONDITIONAL_MARKERS = {"if", "unless", "provided", "providing"}
_CAUSAL_MARKERS = {"because", "cause", "due", "owing"}
_PURPOSE_PHRASES = {"in order to", "so that", "for the purpose of"}
_LOCATIVE_ADVERBS = {
    "abroad", "away", "everywhere", "here", "locally", "nearby", "nowhere",
    "overseas", "there", "underground", "worldwide",
}
_DEGREE_ADVERBS = {
    "almost", "barely", "enough", "extremely", "fairly", "hardly", "just",
    "nearly", "quite", "rather", "really", "so", "too", "very",
}


def _load_model() -> Any:
    global _nlp, _load_error
    if _nlp is not None:
        return _nlp
    with _load_lock:
        if _nlp is not None:
            return _nlp
        try:
            package = importlib.import_module(MODEL_PACKAGE)
            nlp = package.load()
            # Force the complete packaged pipeline to initialize while startup is controlled.
            nlp("VeriTrace parser warm-up.")
        except Exception as error:
            _load_error = str(error)
            raise LinguisticAnalysisConfigurationError(
                "Linguistic analysis is unavailable. Run ./run-verigraph --setup "
                f"to install the pinned {MODEL_ID} package."
            ) from error
        _nlp = nlp
        _load_error = None
        return nlp


def warm() -> None:
    _load_model()


def is_available() -> bool:
    return _nlp is not None


def _char_span(text: str, atom_id: str, feature_id: str, start: int, end: int) -> LinguisticSpan:
    if not 0 <= start < end <= len(text):
        raise LinguisticAnalysisError("The parser returned an invalid linguistic span.")
    exact = text[start:end]
    if not exact:
        raise LinguisticAnalysisError("The parser returned an empty linguistic span.")
    return LinguisticSpan(
        id=f"{atom_id}-{feature_id}",
        text=exact,
        start=utf16_offset(text, start),
        end=utf16_offset(text, end),
    )


def _token_span(text: str, atom_id: str, token: Any, feature_id: str) -> LinguisticSpan:
    return _char_span(text, atom_id, feature_id, token.idx, token.idx + len(token.text))


def _phrase_bounds(token: Any) -> Tuple[int, int]:
    members = [member for member in token.subtree if not member.is_space]
    while members and members[0].is_punct:
        members.pop(0)
    while members and members[-1].is_punct:
        members.pop()
    if not members:
        return token.idx, token.idx + len(token.text)
    return members[0].idx, members[-1].idx + len(members[-1].text)


def _phrase_span(text: str, atom_id: str, token: Any, feature_id: str) -> LinguisticSpan:
    start, end = _phrase_bounds(token)
    return _char_span(text, atom_id, feature_id, start, end)


def _core_phrase_span(
    text: str,
    atom_id: str,
    token: Any,
    feature_id: str,
) -> LinguisticSpan:
    # Preserve nominal material inside an argument. A prepositional phrase in
    # "the president of France" belongs to the participant; only modifiers
    # attached to the predicate itself are classified separately below.
    return _phrase_span(text, atom_id, token, feature_id)


def _copular_complement_span(
    text: str,
    atom_id: str,
    head: Any,
    feature_id: str,
) -> LinguisticSpan:
    excluded: set[int] = set()
    for child in head.children:
        clear_adjunct = child.dep_ in _MODIFIER_DEPS and _modifier_kind(child) is not None
        if (
            child.dep_ in _SUBJECT_DEPS
            or child.dep_ in {"cop", "punct"}
            or child.is_punct
            or clear_adjunct
        ):
            excluded.update(member.i for member in child.subtree)
    members = [
        member
        for member in head.subtree
        if member.i not in excluded
        and not member.is_space
        and not member.is_punct
        and member.dep_ != "punct"
    ]
    if not members:
        return _token_span(text, atom_id, head, feature_id)
    return _char_span(text, atom_id, feature_id, members[0].idx, members[-1].idx + len(members[-1].text))


def _dedupe_tokens(tokens: Iterable[Any]) -> List[Any]:
    seen: set[int] = set()
    result: List[Any] = []
    for token in sorted(tokens, key=lambda item: item.i):
        if token.i not in seen:
            seen.add(token.i)
            result.append(token)
    return result


def _subjects(predicate: Any) -> List[Any]:
    direct = [child for child in predicate.children if child.dep_ in _SUBJECT_DEPS]
    if direct or predicate.dep_ != "conj":
        return _dedupe_tokens(direct)
    ancestor = predicate.head
    while ancestor != ancestor.head and ancestor.dep_ == "conj":
        ancestor = ancestor.head
    inherited = [child for child in ancestor.children if child.dep_ in _SUBJECT_DEPS]
    return _dedupe_tokens(inherited)


def _predicate_tokens(doc: Any) -> List[Any]:
    predicates: List[Any] = []
    clause_predicate_deps = {"advcl", "ccomp", "xcomp", "conj"}
    try:
        sentences = list(doc.sents)
    except ValueError:
        sentences = [doc[:]]
    for sentence in sentences:
        root = sentence.root
        if root.pos_ in {"VERB", "AUX"}:
            predicates.append(root)
        else:
            copulas = [child for child in root.children if child.dep_ == "cop"]
            predicates.extend(copulas)
        predicates.extend(
            token
            for token in sentence
            if token.dep_ in clause_predicate_deps and token.pos_ in {"VERB", "AUX"}
        )
    return _dedupe_tokens(predicates)


def _argument_span(
    atom: PipelineAtom,
    token: Any,
    feature_id: str,
    role: str,
    *,
    copular: bool = False,
) -> LinguisticArgument:
    if copular:
        span = _copular_complement_span(atom.text, atom.id, token, feature_id)
    elif role in {
        "direct_object",
        "indirect_object",
        "subject_complement",
        "object_complement",
    }:
        span = _core_phrase_span(atom.text, atom.id, token, feature_id)
    else:
        span = _phrase_span(atom.text, atom.id, token, feature_id)
    return LinguisticArgument(**span.model_dump(), role=role)


def _subtree_text(token: Any) -> str:
    members = [member.text for member in token.subtree if not member.is_space]
    return " ".join(members).lower()


def _modifier_kind(token: Any) -> Optional[str]:
    members = [member for member in token.subtree if not member.is_space]
    lowers = {member.text.lower() for member in members}
    lemmas = {member.lemma_.lower() for member in members}
    phrase = _subtree_text(token)

    if any(member.ent_type_ in _TEMPORAL_LABELS for member in members):
        return "temporal"
    if lowers & _CONDITIONAL_MARKERS:
        return "conditional"
    if lowers & _CAUSAL_MARKERS or lemmas & _CAUSAL_MARKERS:
        return "causal"
    if any(marker in phrase for marker in _PURPOSE_PHRASES):
        return "purpose"
    if lowers & _TEMPORAL_MARKERS:
        return "temporal"
    if token.dep_ == "advmod" and token.text.lower() in _LOCATIVE_ADVERBS:
        return "locative"
    if (
        token.dep_ == "advmod"
        and token.pos_ == "ADV"
        and token.text.lower() not in _DEGREE_ADVERBS
        and token.text.lower() not in _MODALITY
        and token.lemma_.lower() not in _MODALITY
    ):
        return "manner"
    return None


def _modifier_span(
    atom: PipelineAtom,
    token: Any,
    feature_id: str,
    kind: str,
) -> LinguisticModifier:
    span = _phrase_span(atom.text, atom.id, token, feature_id)
    return LinguisticModifier(**span.model_dump(), kind=kind)


def _frames(atom: PipelineAtom, doc: Any) -> tuple[List[PropositionFrame], List[str]]:
    frames: List[PropositionFrame] = []
    predicates = _predicate_tokens(doc)
    unresolved: List[str] = []
    if not predicates:
        unresolved.append("predicate")

    for frame_index, predicate in enumerate(predicates, start=1):
        frame_id = f"{atom.id}-frame-{frame_index}"
        subject_tokens = _subjects(predicate)
        # In a copular parse the semantic complement is the syntactic head of the copula.
        copular_head = predicate.head if predicate.dep_ == "cop" else None
        argument_tokens: List[tuple[Any, str, bool]] = []
        modifier_tokens: List[tuple[Any, str]] = []
        other_modifier_tokens: List[Any] = []
        seen_modifiers: set[tuple[int, str]] = set()

        def add_modifier(token: Any, kind: str) -> None:
            key = (token.i, kind)
            if key not in seen_modifiers:
                seen_modifiers.add(key)
                modifier_tokens.append((token, kind))

        for child in predicate.children:
            if child.dep_ in _DIRECT_OBJECT_DEPS:
                argument_tokens.append((child, "direct_object", False))
            elif child.dep_ in _INDIRECT_OBJECT_DEPS:
                argument_tokens.append((child, "indirect_object", False))
            elif child.dep_ in _SUBJECT_COMPLEMENT_DEPS:
                argument_tokens.append((child, "subject_complement", False))
            elif child.dep_ in _OBJECT_COMPLEMENT_DEPS:
                argument_tokens.append((child, "object_complement", False))
            elif child.dep_ in _CLAUSAL_COMPLEMENT_DEPS:
                argument_tokens.append((child, "clausal_complement", False))
            elif child.dep_ == "agent":
                argument_tokens.append((child, "passive_agent", False))
            elif child.dep_ in _MODIFIER_DEPS:
                kind = _modifier_kind(child)
                if kind is None:
                    other_modifier_tokens.append(child)
                else:
                    add_modifier(child, kind)
        if copular_head is not None:
            subject_tokens = _dedupe_tokens(
                list(subject_tokens)
                + [child for child in copular_head.children if child.dep_ in _SUBJECT_DEPS]
            )
            argument_tokens.append((copular_head, "subject_complement", True))
        # A copular complement is the syntactic head of the clause. Separate
        # only clearly typed adjuncts from it; retain ambiguous nominal PPs as
        # part of the complement rather than guessing noun or verb valency.
        for argument_token, _role, copular in argument_tokens:
            if not copular:
                continue
            for child in argument_token.children:
                if child.dep_ not in _MODIFIER_DEPS:
                    continue
                kind = _modifier_kind(child)
                if kind is not None:
                    add_modifier(child, kind)

        subjects = [
            _phrase_span(atom.text, atom.id, token, f"frame-{frame_index}-subject-{index}")
            for index, token in enumerate(_dedupe_tokens(subject_tokens), start=1)
        ]
        seen_arguments: set[tuple[int, str]] = set()
        core_arguments: List[LinguisticArgument] = []
        for token, role, copular in sorted(argument_tokens, key=lambda item: item[0].i):
            key = (token.i, role)
            if key in seen_arguments:
                continue
            seen_arguments.add(key)
            core_arguments.append(
                _argument_span(
                    atom,
                    token,
                    f"frame-{frame_index}-argument-{len(core_arguments) + 1}",
                    role,
                    copular=copular,
                )
            )
        adjuncts = [
            _modifier_span(
                atom,
                token,
                f"frame-{frame_index}-adjunct-{index}",
                kind,
            )
            for index, (token, kind) in enumerate(
                sorted(modifier_tokens, key=lambda item: item[0].i), start=1
            )
        ]
        other_modifiers = [
            _phrase_span(
                atom.text,
                atom.id,
                token,
                f"frame-{frame_index}-other-modifier-{index}",
            )
            for index, token in enumerate(_dedupe_tokens(other_modifier_tokens), start=1)
        ]
        frames.append(
            PropositionFrame(
                id=frame_id,
                predicate=_token_span(
                    atom.text, atom.id, predicate, f"frame-{frame_index}-predicate"
                ),
                subjects=subjects,
                core_arguments=core_arguments,
                adjuncts=adjuncts,
                other_modifiers=other_modifiers,
            )
        )
        if not subjects and "subject" not in unresolved:
            unresolved.append("subject")

    if not frames and "subject" not in unresolved:
        unresolved.append("subject")
    return frames, [field for field in ("subject", "predicate") if field in unresolved]


def _cue_span(
    atom: PipelineAtom,
    kind: str,
    start: int,
    end: int,
) -> LinguisticCue:
    span = _char_span(atom.text, atom.id, f"cue-{kind}-{start}-{end}", start, end)
    return LinguisticCue(**span.model_dump(), kind=kind)


def _cues(atom: PipelineAtom, doc: Any) -> List[LinguisticCue]:
    raw: List[tuple[int, int, str]] = []
    for token in doc:
        lower = token.text.lower()
        lemma = token.lemma_.lower()
        if token.dep_ == "neg" or lower in _NEGATIONS:
            raw.append((token.idx, token.idx + len(token.text), "negation"))
        if lower in _QUANTIFIERS:
            raw.append((token.idx, token.idx + len(token.text), "quantifier"))
        if token.tag_ == "MD" or lower in _MODALITY or lemma in _MODALITY:
            raw.append((token.idx, token.idx + len(token.text), "modality"))
        if lemma in _ATTRIBUTION:
            raw.append((token.idx, token.idx + len(token.text), "attribution"))

    token_list = list(doc)
    for index, token in enumerate(token_list[:-1]):
        pair = f"{token.text.lower()} {token_list[index + 1].text.lower()}"
        if pair in {"at least", "at most"}:
            raw.append((token.idx, token_list[index + 1].idx + len(token_list[index + 1].text), "quantifier"))
        if pair in {"according to", "more than", "less than"}:
            kind = "attribution" if pair == "according to" else "quantifier"
            raw.append((token.idx, token_list[index + 1].idx + len(token_list[index + 1].text), kind))

    for entity in doc.ents:
        if entity.label_ in _TEMPORAL_LABELS:
            raw.append((entity.start_char, entity.end_char, "temporal"))
        elif entity.label_ in _NUMERIC_LABELS:
            raw.append((entity.start_char, entity.end_char, "numeric"))

    seen: set[tuple[int, int, str]] = set()
    return [
        _cue_span(atom, kind, start, end)
        for start, end, kind in sorted(raw, key=lambda item: (item[0], item[1], item[2]))
        if not ((start, end, kind) in seen or seen.add((start, end, kind)))
    ]


def _entities(atom: PipelineAtom, doc: Any) -> List[LinguisticEntity]:
    entities: List[LinguisticEntity] = []
    for entity in doc.ents:
        if entity.label_ in _TEMPORAL_LABELS | _NUMERIC_LABELS:
            continue
        span = _char_span(
            atom.text,
            atom.id,
            f"entity-{entity.label_.lower()}-{entity.start_char}-{entity.end_char}",
            entity.start_char,
            entity.end_char,
        )
        entities.append(LinguisticEntity(**span.model_dump(), label=entity.label_))
    return entities


_AnalyzedText = Union[PipelineAtom, DecomposedAtom]


def analysis_from_doc(atom: _AnalyzedText, doc: Any) -> AtomLinguisticAnalysis:
    if doc.text != atom.text:
        raise LinguisticAnalysisError("The parser changed the atom text unexpectedly.")
    frames, unresolved = _frames(atom, doc)
    tokens: List[LinguisticToken] = []
    for token in doc:
        if token.is_space:
            continue
        span = _token_span(atom.text, atom.id, token, f"token-{token.i}")
        tokens.append(
            LinguisticToken(
                **span.model_dump(),
                lemma=token.lemma_,
                pos=token.pos_,
                tag=token.tag_,
                dependency=token.dep_,
                head="ROOT" if token.head == token else token.head.text,
            )
        )
    return AtomLinguisticAnalysis(
        atom_id=atom.id,
        frames=frames,
        cues=_cues(atom, doc),
        entities=_entities(atom, doc),
        tokens=tokens,
        status="partial" if unresolved else "complete",
        unresolved=unresolved,
    )


def _has_cue(analysis: AtomLinguisticAnalysis, kind: str) -> bool:
    return any(cue.kind == kind for cue in analysis.cues)


def _has_modifier(analysis: AtomLinguisticAnalysis, kind: str) -> bool:
    return any(modifier.kind == kind for frame in analysis.frames for modifier in frame.adjuncts)


def _has_location_signal(analysis: AtomLinguisticAnalysis) -> bool:
    return _has_modifier(analysis, "locative") or any(
        entity.label in {"FAC", "GPE", "LOC"} for entity in analysis.entities
    )


def _has_attribution_signal(analysis: AtomLinguisticAnalysis) -> bool:
    return _has_cue(analysis, "attribution") or any(
        token.lemma.lower() in _ATTRIBUTION for token in analysis.tokens
    )


def _has_incompatible_qualifier(analysis: AtomLinguisticAnalysis, expected: str) -> bool:
    signals = {
        "NUMERIC_CONSTRAINT": _has_cue(analysis, "numeric") or _has_cue(analysis, "quantifier"),
        "TEMPORAL_CONSTRAINT": _has_cue(analysis, "temporal"),
        "ATTRIBUTION": _has_attribution_signal(analysis),
        "LOCATION_CONSTRAINT": _has_location_signal(analysis),
        "CAUSAL_RELATION": _has_modifier(analysis, "causal"),
        "CONDITIONAL": _has_modifier(analysis, "conditional"),
        "MODALITY_CONSTRAINT": _has_cue(analysis, "modality"),
    }
    return any(found for role, found in signals.items() if role != expected)


def audit_role(atom: DecomposedAtom, analysis: AtomLinguisticAnalysis) -> RoleAuditStatus:
    """Audit the model-selected role without changing it."""

    if atom.role is ObligationRole.core:
        return RoleAuditStatus.match if analysis.frames else RoleAuditStatus.inconclusive

    expected = {
        ObligationRole.numeric_constraint: _has_cue(analysis, "numeric")
        or _has_cue(analysis, "quantifier"),
        ObligationRole.temporal_constraint: _has_cue(analysis, "temporal"),
        ObligationRole.attribution: _has_attribution_signal(analysis),
        ObligationRole.location_constraint: _has_location_signal(analysis),
        ObligationRole.causal_relation: _has_modifier(analysis, "causal"),
        ObligationRole.conditional: _has_modifier(analysis, "conditional"),
        ObligationRole.modality_constraint: _has_cue(analysis, "modality"),
    }[atom.role]
    if expected:
        return RoleAuditStatus.match
    if _has_incompatible_qualifier(analysis, atom.role.value):
        return RoleAuditStatus.mismatch
    # No cue for the declared role and no competing cue either: the parse cannot
    # confirm or refute the role, so the audit stays deliberately non-committal.
    return RoleAuditStatus.inconclusive


def obligation_warnings(
    atom: DecomposedAtom,
    analysis: AtomLinguisticAnalysis,
    role_audit: RoleAuditStatus,
) -> list[LinguisticWarningCode]:
    warnings: list[LinguisticWarningCode] = []
    if role_audit is RoleAuditStatus.mismatch:
        warnings.append(LinguisticWarningCode.role_cue_mismatch)
    if len(analysis.frames) > 1:
        warnings.append(LinguisticWarningCode.multiple_proposition_frames)
    if "subject" in analysis.unresolved:
        warnings.append(LinguisticWarningCode.unresolved_subject)
    if "predicate" in analysis.unresolved:
        warnings.append(LinguisticWarningCode.unresolved_predicate)
    if analysis.status == "partial":
        warnings.append(LinguisticWarningCode.partial_linguistic_analysis)
    if _has_cue(analysis, "negation") and (not analysis.frames or "predicate" in analysis.unresolved):
        warnings.append(LinguisticWarningCode.negation_scope_unclear)
    if _has_attribution_signal(analysis) and len(analysis.frames) > 1:
        warnings.append(LinguisticWarningCode.attribution_scope_unclear)
    if (
        (_has_cue(analysis, "numeric") or _has_cue(analysis, "temporal"))
        and len(analysis.frames) > 1
    ):
        warnings.append(LinguisticWarningCode.qualifier_attachment_unclear)
    return warnings


def _normalized(value: str) -> str:
    return " ".join(value.lower().split())


def _all_obligation_text(atoms: Sequence[DecomposedAtom]) -> str:
    return " ".join(_normalized(f"{atom.text} {atom.source_text}") for atom in atoms)


def _cue_preserved(
    claim_analysis: AtomLinguisticAnalysis,
    analyses: Sequence[AtomLinguisticAnalysis],
    atoms: Sequence[DecomposedAtom],
    kind: str,
) -> bool:
    claim_cues = [cue for cue in claim_analysis.cues if cue.kind == kind]
    if not claim_cues:
        return True
    atom_text = _all_obligation_text(atoms)
    return all(
        any(cue.kind == kind and _normalized(cue.text) == _normalized(claim_cue.text)
            for analysis in analyses for cue in analysis.cues)
        or _normalized(claim_cue.text) in atom_text
        for claim_cue in claim_cues
    )


def claim_preservation_warnings(
    claim_analysis: AtomLinguisticAnalysis,
    atoms: Sequence[DecomposedAtom],
    analyses: Sequence[AtomLinguisticAnalysis],
) -> list[LinguisticWarningCode]:
    warnings: list[LinguisticWarningCode] = []
    checks = (
        ("negation", LinguisticWarningCode.negation_not_preserved),
        ("numeric", LinguisticWarningCode.numeric_information_not_preserved),
        ("quantifier", LinguisticWarningCode.numeric_information_not_preserved),
        ("temporal", LinguisticWarningCode.temporal_information_not_preserved),
        ("attribution", LinguisticWarningCode.attribution_not_preserved),
        ("modality", LinguisticWarningCode.modality_not_preserved),
    )
    for kind, warning in checks:
        if not _cue_preserved(claim_analysis, analyses, atoms, kind) and warning not in warnings:
            warnings.append(warning)
    claim_locations = [entity for entity in claim_analysis.entities if entity.label in {"FAC", "GPE", "LOC"}]
    atom_text = _all_obligation_text(atoms)
    if claim_locations and any(_normalized(entity.text) not in atom_text for entity in claim_locations):
        warnings.append(LinguisticWarningCode.location_not_preserved)
    atom_predicates = {
        predicate
        for analysis in analyses
        for predicate in (
            [frame.predicate.text.lower() for frame in analysis.frames if frame.predicate]
            + [token.lemma.lower() for token in analysis.tokens]
        )
    }
    if any(
        frame.predicate is not None
        and frame.predicate.text.lower() not in atom_predicates
        for frame in claim_analysis.frames
    ):
        warnings.append(LinguisticWarningCode.claim_frame_not_covered)
    return warnings


def summary_from_analysis(
    atom: DecomposedAtom,
    analysis: AtomLinguisticAnalysis,
    role_audit: RoleAuditStatus,
    warnings: Sequence[LinguisticWarningCode],
) -> ObligationLinguisticSummary:
    return ObligationLinguisticSummary(
        atom_id=atom.id,
        analysis_status=analysis.status,
        role_audit=role_audit,
        subjects=list(dict.fromkeys(subject.text for frame in analysis.frames for subject in frame.subjects)),
        predicates=list(
            dict.fromkeys(
                token.lemma for token in analysis.tokens
                if any(
                    frame.predicate
                    and frame.predicate.start == token.start
                    and frame.predicate.end == token.end
                    for frame in analysis.frames
                )
            )
        ),
        cue_kinds=list(dict.fromkeys(cue.kind for cue in analysis.cues)),
        modifier_kinds=list(
            dict.fromkeys(modifier.kind for frame in analysis.frames for modifier in frame.adjuncts)
        ),
        entity_labels=list(dict.fromkeys(entity.label for entity in analysis.entities)),
        warnings=list(warnings),
    )


def analyze_decomposition(
    claim_text: str,
    composition: ClaimComposition,
    atoms: Sequence[DecomposedAtom],
) -> LinguisticAnalysisResponse:
    if not atoms:
        raise LinguisticAnalysisError("At least one atom is required for linguistic analysis.")
    del composition  # Flat composition is retained for downstream graph work, not interpreted here.
    nlp = _load_model()
    claim_atom = PipelineAtom(id="claim", text=claim_text)
    try:
        docs = list(nlp.pipe([claim_text, *(atom.text for atom in atoms)], batch_size=len(atoms) + 1))
        if len(docs) != len(atoms) + 1:
            raise LinguisticAnalysisError("The parser returned an incomplete analysis batch.")
        claim_analysis = analysis_from_doc(claim_atom, docs[0])
        analyses = [analysis_from_doc(atom, doc) for atom, doc in zip(atoms, docs[1:])]
        audits = [audit_role(atom, analysis) for atom, analysis in zip(atoms, analyses)]
        atom_warnings = [
            obligation_warnings(atom, analysis, audit)
            for atom, analysis, audit in zip(atoms, analyses, audits)
        ]
        summaries = [
            summary_from_analysis(atom, analysis, audit, warnings)
            for atom, analysis, audit, warnings in zip(atoms, analyses, audits, atom_warnings)
        ]
        claim_warnings = claim_preservation_warnings(claim_analysis, atoms, analyses)
    except LinguisticAnalysisError:
        raise
    except Exception as error:
        raise LinguisticAnalysisError("Local linguistic analysis failed.") from error
    return LinguisticAnalysisResponse(
        claim_analysis=claim_analysis,
        analyses=analyses,
        summaries=summaries,
        claim_warnings=claim_warnings,
        model=MODEL_ID,
    )


def analyze_atoms(atoms: Sequence[PipelineAtom]) -> LinguisticAnalysisResponse:
    """Compatibility adapter for callers that only need atom-level parsing.

    The live API always uses ``analyze_decomposition`` so it can audit the
    original claim. Keeping this adapter preserves the extractor's established
    batching contract for internal callers and regression tests.
    """

    if not atoms:
        raise LinguisticAnalysisError("At least one atom is required for linguistic analysis.")
    nlp = _load_model()
    try:
        docs = list(nlp.pipe((atom.text for atom in atoms), batch_size=len(atoms)))
        if len(docs) != len(atoms):
            raise LinguisticAnalysisError("The parser returned an incomplete analysis batch.")
        analyses = [analysis_from_doc(atom, doc) for atom, doc in zip(atoms, docs)]
        typed_atoms = [
            DecomposedAtom(
                id=atom.id,
                text=atom.text,
                source_text=atom.text,
                start=0,
                end=utf16_offset(atom.text, len(atom.text)),
                role=ObligationRole.core,
            )
            for atom in atoms
        ]
        audits = [audit_role(atom, analysis) for atom, analysis in zip(typed_atoms, analyses)]
        warnings = [
            obligation_warnings(atom, analysis, audit)
            for atom, analysis, audit in zip(typed_atoms, analyses, audits)
        ]
        claim_analysis = analyses[0].model_copy(update={"atom_id": "claim"})
        return LinguisticAnalysisResponse(
            claim_analysis=claim_analysis,
            analyses=analyses,
            summaries=[
                summary_from_analysis(atom, analysis, audit, warning)
                for atom, analysis, audit, warning in zip(typed_atoms, analyses, audits, warnings)
            ],
            claim_warnings=[],
            model=MODEL_ID,
        )
    except LinguisticAnalysisError:
        raise
    except Exception as error:
        raise LinguisticAnalysisError("Local linguistic analysis failed.") from error


analyze_linguistics = analyze_decomposition
