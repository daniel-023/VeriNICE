# VeriGraph Claim Decomposition Plan

> **Status: delivered.** This plan is kept as the design record for the stage. Current behaviour is documented in `PIPELINE.md`; the implementation is in `backend/verigraph_backend/claim_decomposition.py`.

## Scope

This plan covers only the claim decomposition stage. Linguistic analysis, argumentation-graph construction, and verdict aggregation should not be modified until this stage is stable.

The objective is to replace the current flat list of atomic claims with a versioned, structured decomposition containing:

- Standalone verification obligations
- Exact grounding in the original claim
- A verification role for each obligation
- The logical composition of the claim
- Server-generated identifiers and offsets

## Target workflow

```text
Input claim
    -> Qwen structured generation
    -> Schema validation
    -> Server normalization
    -> Validated decomposition response
    -> Existing retrieval pipeline
```

## Design principles

1. Qwen performs only the semantic decomposition.
2. The backend owns identifiers, offsets, warnings, and schema versions.
3. Every obligation must be independently verifiable.
4. Every obligation must be grounded in exact text from the original claim.
5. Qwen must not create support or attack relations.
6. The existing retrieval, NLI, and linguistic-analysis stages should continue consuming atom IDs and atom text.
7. Invalid model output must not stop the rest of the pipeline.

## 1. Separate the LLM schema from the API schema

Do not ask Qwen to reproduce server-owned information such as claim IDs, atom IDs, offsets, warnings, or schema versions.

### 1.1 Qwen output schema

Qwen should produce only semantic decomposition content:

```json
{
  "composition": "AND",
  "obligations": [
    {
      "text": "The government reduced taxes.",
      "sourceText": "The government reduced taxes",
      "role": "CORE"
    },
    {
      "text": "The tax reduction was 50%.",
      "sourceText": "by 50%",
      "role": "NUMERIC_CONSTRAINT"
    },
    {
      "text": "The tax reduction occurred in 2023.",
      "sourceText": "in 2023",
      "role": "TEMPORAL_CONSTRAINT"
    }
  ]
}
```

Use this JSON Schema:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ClaimDecompositionDraft",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "composition",
    "obligations"
  ],
  "properties": {
    "composition": {
      "type": "string",
      "enum": [
        "SINGLE",
        "AND",
        "OR"
      ]
    },
    "obligations": {
      "type": "array",
      "minItems": 1,
      "maxItems": 12,
      "items": {
        "$ref": "#/$defs/obligation"
      }
    }
  },
  "$defs": {
    "obligation": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "text",
        "sourceText",
        "role"
      ],
      "properties": {
        "text": {
          "type": "string",
          "minLength": 1,
          "description": "A standalone, independently verifiable proposition."
        },
        "sourceText": {
          "type": "string",
          "minLength": 1,
          "description": "An exact contiguous substring copied from the original claim."
        },
        "role": {
          "type": "string",
          "enum": [
            "CORE",
            "NUMERIC_CONSTRAINT",
            "TEMPORAL_CONSTRAINT",
            "ATTRIBUTION",
            "LOCATION_CONSTRAINT",
            "CAUSAL_RELATION",
            "CONDITIONAL",
            "MODALITY_CONSTRAINT"
          ]
        }
      }
    }
  }
}
```

### 1.2 Normalized API response

After validating Qwen's output, the backend adds stable IDs, offsets, warnings, and the schema version.

```json
{
  "schemaVersion": 2,
  "claimId": "case-001",
  "composition": "AND",
  "atoms": [
    {
      "id": "a1",
      "text": "The government reduced taxes.",
      "sourceText": "The government reduced taxes",
      "sourceStart": 0,
      "sourceEnd": 28,
      "role": "CORE"
    },
    {
      "id": "a2",
      "text": "The tax reduction was 50%.",
      "sourceText": "by 50%",
      "sourceStart": 29,
      "sourceEnd": 35,
      "role": "NUMERIC_CONSTRAINT"
    },
    {
      "id": "a3",
      "text": "The tax reduction occurred in 2023.",
      "sourceText": "in 2023",
      "sourceStart": 36,
      "sourceEnd": 43,
      "role": "TEMPORAL_CONSTRAINT"
    }
  ],
  "warnings": []
}
```

The server should:

- Assign IDs sequentially as `a1`, `a2`, and so on.
- Calculate offsets from `sourceText`.
- Use UTF-16 offsets to remain compatible with JavaScript highlighting.
- Preserve the existing `atoms` field name to minimize downstream changes.
- Include `schemaVersion` for recorded-fixture migration.

## 2. Define role semantics

| Role | Use when |
| --- | --- |
| `CORE` | The central factual proposition |
| `NUMERIC_CONSTRAINT` | A quantity, percentage, threshold, ranking, or comparison |
| `TEMPORAL_CONSTRAINT` | A date, duration, sequence, frequency, or time range |
| `ATTRIBUTION` | The claim concerns who said, reported, announced, or alleged something |
| `LOCATION_CONSTRAINT` | A location is material to the claim |
| `CAUSAL_RELATION` | The claim asserts that one event caused or affected another |
| `CONDITIONAL` | The proposition holds only under an explicit condition |
| `MODALITY_CONSTRAINT` | Possibility, probability, obligation, or uncertainty is part of what is claimed |

### Attribution rule

If a claim only reports that a person said something, verify the speech event. Do not automatically convert the quoted content into a separate factual assertion.

For example:

> The minister said unemployment had fallen.

Should normally produce:

```json
{
  "composition": "SINGLE",
  "obligations": [
    {
      "text": "The minister said that unemployment had fallen.",
      "sourceText": "The minister said unemployment had fallen",
      "role": "ATTRIBUTION"
    }
  ]
}
```

It should not assume that the original claim independently asserts that unemployment fell.

## 3. Rewrite the Qwen prompt

Use a concise system instruction followed by diverse few-shot examples.

### Core instruction

```text
Decompose the input claim into the smallest set of standalone
verification obligations required to verify the complete claim.

Each obligation must:
1. Express one independently verifiable proposition.
2. Preserve the meaning, polarity, attribution, modality, quantities,
   dates, locations, and causal relations in the original claim.
3. Contain no information that is absent from the original claim.
4. Include sourceText copied exactly from one contiguous span of the
   original claim.
5. Receive the most specific applicable verification role.

Separate a material qualifier when it can be independently checked,
such as a number, date, location, or causal relation.

Do not create obligations for isolated entities, predicates, dates,
numbers, or linguistic tokens. Every obligation must be a complete
natural-language proposition.

Use:
- SINGLE when there is one obligation.
- AND when every obligation must hold.
- OR when any one obligation is sufficient.

Return only JSON conforming to the supplied schema.
```

### Few-shot coverage

Include at least four compact examples:

1. A single factual claim
2. A core claim with numeric and temporal constraints
3. An attributed quotation
4. A conjunctive or disjunctive claim

Add one example involving negation or modality if the context budget permits.

## 4. Add validation in two levels

### 4.1 Hard validation

A hard validation failure triggers one repair attempt.

Validate that:

- The response is valid JSON.
- It conforms to the schema.
- There are between 1 and 12 obligations.
- Every `sourceText` is an exact substring of the original claim.
- Every obligation has a valid role.
- `SINGLE` contains exactly one obligation.
- `AND` and `OR` contain at least two obligations.
- Obligation texts are not exact duplicates.
- Source spans are not empty.

### 4.2 Soft validation

These issues produce warnings but do not immediately fail:

- Two obligations appear semantically duplicated.
- An obligation contains several independent clauses.
- One source span is reused by several obligations.
- A very short `sourceText` may be ambiguous.
- The decomposition appears to omit claim content.
- A qualifier role appears inconsistent with its text.

The later spaCy stage will provide more reliable linguistic warnings. Do not duplicate the full linguistic-analysis logic here.

## 5. Add repair and fallback behavior

If Qwen produces invalid output:

1. Return the validation errors to Qwen.
2. Ask it to repair only the JSON.
3. Validate the repaired output.
4. If it still fails, use a safe fallback.

Fallback:

```json
{
  "composition": "SINGLE",
  "obligations": [
    {
      "text": "<original claim>",
      "sourceText": "<original claim>",
      "role": "CORE"
    }
  ]
}
```

Record a warning:

```json
{
  "code": "DECOMPOSITION_FALLBACK",
  "message": "Structured decomposition failed; the original claim was retained as one obligation."
}
```

This fallback keeps retrieval and NLI operational when decomposition fails.

## 6. Update backend types

Add or revise models equivalent to:

```python
class ClaimComposition(str, Enum):
    SINGLE = "SINGLE"
    AND = "AND"
    OR = "OR"


class ObligationRole(str, Enum):
    CORE = "CORE"
    NUMERIC_CONSTRAINT = "NUMERIC_CONSTRAINT"
    TEMPORAL_CONSTRAINT = "TEMPORAL_CONSTRAINT"
    ATTRIBUTION = "ATTRIBUTION"
    LOCATION_CONSTRAINT = "LOCATION_CONSTRAINT"
    CAUSAL_RELATION = "CAUSAL_RELATION"
    CONDITIONAL = "CONDITIONAL"
    MODALITY_CONSTRAINT = "MODALITY_CONSTRAINT"


class ObligationDraft(BaseModel):
    text: str
    source_text: str
    role: ObligationRole


class ClaimDecompositionDraft(BaseModel):
    composition: ClaimComposition
    obligations: list[ObligationDraft]


class PipelineAtom(BaseModel):
    id: str
    text: str
    source_text: str
    source_start: int
    source_end: int
    role: ObligationRole


class ClaimDecompositionResponse(BaseModel):
    schema_version: Literal[2] = 2
    claim_id: str
    composition: ClaimComposition
    atoms: list[PipelineAtom]
    warnings: list[DecompositionWarning] = []
```

Use the project's existing snake-case and camel-case alias conventions rather than duplicating fields.

## 7. Maintain downstream compatibility

During this stage:

- Retrieval should continue receiving `PipelineAtom`.
- NLI should continue receiving the atom ID and text.
- Linguistic analysis should continue receiving the same atom ID and text.
- The graph should not yet interpret `role` or `composition`.
- Existing atom selection and evidence highlighting should continue working.

This isolates the decomposition change from later stages.

## 8. Migrate recorded fixtures

Update the 22 prerecorded demo cases to include:

- `schemaVersion`
- `composition`
- `role`
- Server-calculated source offsets

Regenerate the fixtures through the updated pipeline and manually inspect them before committing the changes. Do not manually invent roles without reviewing the decompositions.

## 9. Testing plan

### 9.1 Unit tests

Test:

- Valid schema output
- Invalid role
- Missing required field
- More than 12 obligations
- Invalid `SINGLE` count
- Invalid `AND` or `OR` count
- `sourceText` absent from the claim
- Repeated source text
- Duplicate obligations
- UTF-16 offset calculation
- Successful repair
- Failed repair followed by fallback

### 9.2 Curated decomposition tests

Include claims containing:

- One simple proposition
- Conjunction
- Disjunction
- Negation
- Percentage
- `At least` or `more than`
- Date and duration
- Attribution
- Location
- Causality
- Conditional language
- Modality

### 9.3 Integration tests

Run Qwen with deterministic settings over a fixed suite and verify:

- JSON validity
- Stable obligation counts
- Exact source grounding
- No lost negation
- No lost numbers or dates
- No introduced facts

## 10. Acceptance criteria

Complete the claim decomposition stage only when:

- 100% of tested responses are schema-valid after at most one repair.
- 100% of `sourceText` values resolve to the original claim.
- All offsets correctly highlight the intended source span.
- Negation, numbers, dates, and attribution are preserved in the curated tests.
- Retrieval, NLI, and linguistic analysis still run without changes to their core logic.
- Invalid model output falls back safely.
- All 22 recorded cases load under schema version 2.
- Repeated runs produce acceptably stable decompositions.

## 11. Implementation order

1. Add the draft and API schemas.
2. Add role and composition enums.
3. Rewrite the Qwen prompt and few-shot examples.
4. Enable structured JSON generation.
5. Implement validation and normalization.
6. Add repair and fallback behavior.
7. Update API and frontend types.
8. Update unit and integration tests.
9. Regenerate the 22 recorded fixtures.
10. Manually review the decompositions.
11. Freeze schema version 2.
12. Begin the linguistic-analysis update only after these criteria pass.

## Deliverables

- Versioned Qwen decomposition schema
- Updated Qwen prompt and few-shot examples
- Draft and normalized Pydantic models
- Server-side validator and normalizer
- One-attempt repair flow
- Safe fallback flow
- Updated TypeScript types
- Migrated demo fixtures
- Unit, curated, and integration test suites
- Manual review record for the 22 demo cases

## Out of scope

The following work belongs to later stages:

- Changing spaCy proposition extraction
- Adding linguistic audit warnings
- Updating argumentation-graph topology
- Generating `SUPPORTS` or `ATTACKS` edges
- Four-way verdict aggregation
- Moving graph construction to FastAPI

