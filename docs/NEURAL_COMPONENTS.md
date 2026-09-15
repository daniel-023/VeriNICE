# Neural components

This guide describes where learned models are used in VeriNICE and the
constraints placed around their outputs. Neural components propose structured
interpretations; source validation and verdict composition remain explicit.

The learned components are concentrated in the first three pipeline stages:

| Stage | Learned operation | Constrained output |
| --- | --- | --- |
| **01 · Claim decomposition** | Interpret the claim's verification obligations. | Validated atomic claims and `SINGLE`, `AND`, or `OR` composition. |
| **02 · Evidence retrieval** | Encode the query and passages for semantic ranking. | Source-linked candidates ranked separately for each atomic claim. |
| **03 · Evidence assessment** | Classify candidate relations and bundle sufficiency. | Server-issued span identifiers, relation labels, and a bounded sufficiency state. |

## Claim decomposition

VeriNICE asks a local Qwen2.5 model to convert a claim into a flat composition:

- `SINGLE` for one verification obligation;
- `AND` when every atomic obligation must hold; or
- `OR` when any atomic obligation is sufficient.

The response is constrained by a JSON schema and contains no arbitrary nested
program. Atomic claims retain exact, contiguous locators into the original
claim, and the backend validates the returned structure and offsets. A run can
contain at most 12 atoms.

If the first response is invalid, VeriNICE makes one repair attempt. If repair
also fails, it preserves the full claim as a `SINGLE` atom and records a
`DECOMPOSITION_FALLBACK` warning. This makes failure visible, but it does not
guarantee that a valid decomposition is semantically correct.

## Sentence segmentation and retrieval

PySBD divides supplied documents into sentence-aligned passages while the
backend retains exact source offsets. Retrieval then ranks candidates for each
atomic claim.

Semantic retrieval uses `BAAI/bge-small-en-v1.5`. The query is encoded with
the model's retrieval instruction and passages are encoded without that
instruction. Both vectors are L2-normalized, so their dot product is equal to
cosine similarity.

Lexical retrieval scores coverage of claim terms and gives explicit treatment
to names, dates, numbers, and structured lists. The default hybrid method
combines dense and lexical ranks with equal-weight reciprocal-rank fusion:

```text
hybrid(i,j) = 1 / (60 + dense_rank(i,j))
            + 1 / (60 + lexical_rank(i,j))
```

`SEMANTIC` and `LEXICAL` can also be selected independently. Evidence budgets
range from 1 to 12 passages per atom, with 6 as the default. Global ranking is
combined with per-document diversity, and adjacent sentences may be retained
as reading context.

Retrieval operates only over documents supplied with the request or prepared
for the selected case; it is not open-web search. A deterministic scope check
withholds identifiable jurisdiction mismatches from assessment and reasoning
while leaving them visible for inspection.

## Evidence assessment

Qwen2.5 assesses candidates separately for each atomic claim by selecting
supporting, refuting, and contextual spans. The interface reports four
relations:

- **Supports** — directly establishes the atomic claim.
- **Refutes** — directly contradicts the atomic claim.
- **Context** — helps interpret evidence but establishes neither truth value.
- **Not used** — derived for a retrieved passage that the model did not select
  for assessment.

The model also judges the selected evidence bundle as `SUFFICIENT`, `PARTIAL`,
or `INSUFFICIENT`. A support or refutation is verdict-bearing only when the
bundle for that atom is sufficient; otherwise the relation remains
provisional. Assessment rationales and premise identifiers are retained for
inspection.

The assessor receives only the original claim, validated atoms, and supplied
candidate identifiers and text. It cannot introduce an unprovided source.
Source bounding protects provenance, but it does not make the selected source
authoritative or the model's relation label correct.

## Restricted role in symbolic reasoning

The model does not write or execute unrestricted code. The backend first
generates eligible rule candidates and permissible source premises. Qwen2.5
may propose only mappings among those candidates and premises. Python then
validates each mapping, extracts registered operands, checks the rule's
preconditions, and executes the operation deterministically. Conservative
attribute and distinct-count candidates omitted by the model may be recovered
only when Python independently obtains a decisive result from the complete
server-issued candidate. Unsupported or ambiguous mappings remain unresolved.

The available rules, their eligibility conditions, and their abstention
behaviour are documented in [Symbolic reasoning](SYMBOLIC_REASONING.md).

## Limitations and reproducibility

- Decomposition, retrieval ranking, evidence relations, sufficiency, and rule
  mapping can be wrong even when their outputs satisfy the schema.
- Evidence is bounded by the supplied documents. A verdict is not a claim that
  every relevant source on the open web was considered.
- Deterministic execution guarantees repeatable calculation from validated
  operands, not that the operands express the intended real-world fact.
- Reference labels are displayed for comparison only. They are never provided
  to decomposition, retrieval, assessment, symbolic reasoning, or verdict
  composition.
- The checked-in walkthrough records one fixed configuration. Changing the
  model may change neural outputs and requires renewed validation.
