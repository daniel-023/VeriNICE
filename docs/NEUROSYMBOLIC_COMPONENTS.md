# VeriNICE Neurosymbolic Components and Operator Library

VeriNICE uses learned models for structured interpretation and deterministic code for retrieval constraints, symbolic execution, and verdict composition. Reference labels are displayed only for comparison; they are not inputs to the pipeline.

## Pipeline overview

```text
Claim and supplied documents
  → Qwen2.5 7B decomposes the claim
  → BGE and BM25 retrieve candidate sentences
  → Qwen2.5 7B assesses evidence relations and sufficiency
  → Python generates eligible symbolic rule candidates
  → Qwen2.5 7B maps candidates to permitted premises
  → Python validates and executes the selected rules
  → Python composes the final verdict
```

The three Qwen stages use separate prompts and response schemas. Each response is parsed and validated independently.

## Neural components

| Stage | Component | Default model | Role | Implementation |
| :---: | --- | --- | --- | --- |
| **01** | **Claim decomposition** | `qwen2.5:7b` | Produces at most 12 atomic claims, each with a contiguous `sourceText` span that occurs uniquely in the original claim, and identifies their composition as `SINGLE`, `AND`, or `OR`. | [`claim_decomposition.py`](../backend/verinice_backend/claim_decomposition.py), [`claim_decomposition_prompt.py`](../backend/verinice_backend/claim_decomposition_prompt.py), [`claim_decomposition_validation.py`](../backend/verinice_backend/claim_decomposition_validation.py) |
| **02** | **Semantic retrieval** | `BAAI/bge-small-en-v1.5` | Encodes atomic claims and candidate sentences. Cosine similarity between normalized embeddings supplies the semantic ranking, not an entailment decision. | [`embeddings.py`](../backend/verinice_backend/embeddings.py), [`evidence_retrieval.py`](../backend/verinice_backend/evidence_retrieval.py) |
| **03** | **Evidence assessment** | `qwen2.5:7b` | Assigns supplied candidate identifiers to `SUPPORTS`, `REFUTES`, or `CONTEXT` and rates each evidence bundle as `SUFFICIENT`, `PARTIAL`, or `INSUFFICIENT`. Unassigned candidates are recorded as `NOT_SELECTED`. | [`grounded_evidence_audit.py`](../backend/verinice_backend/grounded_evidence_audit.py) |
| **04** | **Symbolic rule mapping** | `qwen2.5:7b` | Selects up to three mappings from the rule candidates and permitted premises supplied by the backend. Python generates the candidates and permitted premises. | [`symbolic_reasoning/compiler.py`](../backend/verinice_backend/symbolic_reasoning/compiler.py) |

The backend validates decomposition schemas and source locators and records coverage warnings. Invalid decomposition output receives one repair attempt. If structural repair fails, the complete input is retained as one flagged atomic claim; if semantic repair fails, the original flagged decomposition is retained.

Evidence relations affect the verdict only when the bundle is `SUFFICIENT`. The symbolic mapper cannot create operators or premises, and it does not execute rules. Python rejects unknown candidates and unissued premises before execution.

## Deterministic retrieval and filtering

| Component | Role |
| --- | --- |
| **Sentence segmentation** | PySBD creates sentence candidates while preserving exact source offsets. |
| **BM25 lexical retrieval** | Scores term matches using corpus rarity and sentence-length normalization. Numeric tokens are normalized, and structured-list rows receive a small boost for list-related queries. |
| **Reciprocal-rank fusion** | Combines the BGE semantic and BM25 lexical rankings with equal weights in `HYBRID` mode. |
| **Evidence-scope validation** | Withholds passages with an explicit jurisdiction mismatch from evidence assessment and symbolic reasoning while leaving them visible for inspection. |

## Symbolic operator library

An operator performs a deterministic operation. Each supported language pattern corresponds to an implementation profile. Profiles constrain how inputs may be extracted; they do not introduce other operators or relax operator preconditions. Python validates candidate identifiers, premise identifiers, source offsets, profiles, operand alignment, and operator-specific preconditions before execution.

| Operator | Supported pattern (profile) | Decision rule | Abstains when |
| --- | --- | --- | --- |
| `SET_MEMBERSHIP` | Structured-list membership (`GENERIC_SET_MEMBERSHIP`) | Tests whether a normalized item, or a source-stated alias, occurs in a structured list. Presence may support membership; absence may refute it only when the source states that the list is complete. | The list is incomplete, the item is ambiguous, or the completeness information conflicts. |
| `NUMERIC_COMPARE` | Explicit numeric threshold (`GENERIC_NUMERIC_THRESHOLD`) | Applies an explicit comparator to decimal values after checking parsed units, years stated in the claim, and lexical overlap for named entities and the claimed measure. | Alignment is missing or ambiguous, units or scopes are incompatible, or units are unsupported. No implicit unit conversion is performed. |
| `TEMPORAL_COMPARE` | Absolute dates or event ordering (`GENERIC_ABSOLUTE_DATE`, `GENERIC_EVENT_ORDER`) | Compares absolute date intervals or dates attached to two named events. It returns a result only when interval bounds make the requested relation logically certain. | Dates are relative, interval boundaries are missing, coarse dates overlap, or event-to-date mappings are ambiguous. |
| `ATTRIBUTE_COMPARE` | Explicit negation, location, purpose, award recipient, or award motivation (`EXPLICIT_NEGATION`, `COUNTRY_LOCATION`, `EXCLUSIVE_PURPOSE`, `AWARD_RECIPIENT`, `AWARD_MOTIVATION`) | Compares attributes extracted through registered patterns after aligning the subject and operands. | The claim is outside those patterns or the premises do not provide one unambiguous aligned value. |
| `COUNT_DISTINCT` | Distinct values (`GENERIC_DISTINCT_VALUES`) | Extracts and deduplicates explicit values aligned with the claim's subject, predicate, and category. The count can establish a lower bound such as “at least two.” | Too few aligned values are available. Exact-count claims remain unresolved without evidence that the value set is complete. |
| `EXTREMUM_COMPARE` | Counterexample to a largest or smallest claim (`GENERIC_EXTREMUM_COUNTEREXAMPLE`) | Refutes a largest or smallest claim when a value from a source premise is strictly larger or smaller and uses the same parsed unit of measurement. A specific guard prevents comparison of height-above-sea-level with base-to-summit measurements. | The subject value is missing, measurement definitions are incompatible, or no counterexample is available. Failure to find a counterexample does not prove a superlative. |

For `ATTRIBUTE_COMPARE` and `COUNT_DISTINCT`, Python may evaluate an unselected backend-generated candidate against no more than ten permitted premises. This recovery path contributes to the verdict only when it produces `PROVED` or `DISPROVED`; it cannot introduce candidates or premises.

## Symbolic result states

| State | Meaning | Verdict contribution |
| --- | --- | --- |
| `PROVED` | The validated operands establish the atomic claim under the implemented rule. | Support |
| `DISPROVED` | The validated operands contradict the atomic claim under the implemented rule. | Refutation |
| `UNRESOLVED` | Inputs or preconditions are insufficient, ambiguous, or conflicting. | None |
| `NOT_APPLICABLE` | The atomic claim does not match the operator's supported form. | None |

These states describe a bounded implemented operation; they do not establish source authority or logical completeness.

## Verdict aggregation

Each atomic claim receives support and refutation signals from `SUPPORTS` and `REFUTES` relations in a `SUFFICIENT` evidence bundle and from symbolic results of `PROVED` and `DISPROVED`.

| Support | Refutation | Atomic verdict |
| :---: | :---: | --- |
| Yes | No | `SUPPORTED` |
| No | Yes | `REFUTED` |
| Yes | Yes | `CONFLICTING_EVIDENCE` |
| No | No | `NOT_ENOUGH_EVIDENCE` |

A validated material-omission record indicates that otherwise sufficient support depends on omitted qualifying context. It is a separate claim-level condition that produces `CONFLICTING_EVIDENCE`.

- `SINGLE` inherits its atomic verdict.
- `AND` is `REFUTED` if any atomic claim is refuted; otherwise it is `CONFLICTING_EVIDENCE` if any atomic claim is conflicting, `SUPPORTED` if every atomic claim is supported, and `NOT_ENOUGH_EVIDENCE` otherwise.
- `OR` is `SUPPORTED` if any atomic claim is supported; otherwise it is `CONFLICTING_EVIDENCE` if any atomic claim is conflicting, `REFUTED` if every atomic claim is refuted, and `NOT_ENOUGH_EVIDENCE` otherwise.

These rules are implemented in [`verdict_aggregation.py`](../backend/verinice_backend/verdict_aggregation.py). The final verdict is not generated by another language-model call.

## Limitations

- VeriNICE considers only the documents supplied with the request, and retrieval or operand extraction may omit or misinterpret relevant content.
- Schema and source-grounding checks do not guarantee that a decomposition, evidence relation, or premise mapping is semantically correct.
- Deterministic execution is repeatable for validated operands but does not establish that they represent the intended real-world fact.
- The symbolic library is limited to its registered operators, profiles, units, and comparison conditions.
- The recorded walkthrough uses the versions in [`data/manifests/model-lock.json`](../data/manifests/model-lock.json); other model configurations require separate validation.
