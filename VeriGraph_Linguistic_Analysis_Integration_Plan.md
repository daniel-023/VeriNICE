# VeriGraph Linguistic Analysis Integration Plan

## Scope

This plan covers the second implementation stage, after structured claim decomposition is complete and schema version 2 is stable.

The objective is to adapt the existing spaCy-based linguistic analysis so that it:

- Annotates the new typed verification obligations
- Audits whether decomposition preserved important linguistic information
- Produces compact metadata for later argumentation-graph nodes
- Preserves the existing detailed linguistic panel
- Remains verdict-neutral

This stage must not create support or attack relations, change NLI predictions, construct the argumentation graph, or aggregate a verdict.

## Prerequisites

Begin this stage only when:

- The claim decomposition schema is frozen at version 2.
- Qwen returns `composition` and typed verification obligations.
- The backend assigns stable atom IDs and UTF-16 source offsets.
- Retrieval, NLI, and the existing linguistic-analysis endpoint accept the new `PipelineAtom` model.
- All 22 recorded demo cases have migrated decomposition fixtures.

## Target workflow

```text
Original claim
    -> Qwen verification obligations
    -> spaCy analysis of original claim and obligations
    -> Per-obligation linguistic annotations
    -> Decomposition audit
    -> Compact graph-ready summaries
    -> Existing linguistic panel
```

## Design principles

1. Qwen remains the source of verification obligations.
2. spaCy annotates and audits those obligations.
3. spaCy does not silently create, delete, split, or relabel obligations.
4. Disagreements between the Qwen role and linguistic cues become warnings.
5. Full linguistic detail remains available for human inspection.
6. Only compact summaries are prepared for the later graph stage.
7. Linguistic warnings do not determine support, refutation, or the final verdict.
8. The stage remains optional and best-effort, as in the current architecture.

## 1. Preserve the existing extractor

Do not rewrite the current proposition-frame and cue extraction logic unless a regression is found.

Continue extracting:

- Proposition frames
- Subjects
- Predicates
- Core arguments
- Typed adjuncts
- Other modifiers
- Negation cues
- Quantifiers
- Modality
- Attribution
- Temporal cues
- Numeric cues
- Named entities
- Raw token, dependency, lemma, tag, and head information
- Complete or partial analysis status
- Unresolved subject or predicate markers
- UTF-16 offsets

The existing output should remain available to `LinguisticPanel`.

## 2. Expand the request contract

The current endpoint receives only a list of atoms. Update it to receive the original claim and the complete normalized decomposition response.

### Proposed request

```json
{
  "schemaVersion": 2,
  "claimId": "case-001",
  "claimText": "The government reduced taxes by 50% in 2023.",
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
  ]
}
```

### Compatibility option

If a direct request replacement is disruptive, introduce a versioned endpoint or accept both request shapes temporarily:

- Version 1: atoms only
- Version 2: original claim plus normalized decomposition

Remove version 1 only after the frontend and recorded fixtures have migrated.

## 3. Analyse the original claim and obligations together

Analyse the original claim once, followed by all obligation texts, using one `nlp.pipe` batch where practical.

This enables two outputs:

1. The existing per-obligation linguistic analysis
2. A claim-level audit comparing the original claim with the generated obligations

Recommended processing order:

```text
batch item 0      -> original claim
batch items 1..n -> obligation texts
```

Validate that the returned document count matches `1 + number_of_atoms`.

## 4. Add per-obligation role auditing

Compare each Qwen role with the cues and frames extracted by spaCy.

### Expected linguistic signals

| Qwen role | Expected signal |
| --- | --- |
| `CORE` | At least one usable proposition frame |
| `NUMERIC_CONSTRAINT` | Numeric cue, quantifier, or numeric entity |
| `TEMPORAL_CONSTRAINT` | Temporal cue, DATE entity, or TIME entity |
| `ATTRIBUTION` | Attribution cue or reporting predicate |
| `LOCATION_CONSTRAINT` | Locative modifier or location entity |
| `CAUSAL_RELATION` | Causal modifier or causal marker |
| `CONDITIONAL` | Conditional modifier or conditional marker |
| `MODALITY_CONSTRAINT` | Modal auxiliary or modality cue |

### Role-audit status

Use three states:

```text
MATCH
MISMATCH
INCONCLUSIVE
```

- `MATCH`: the expected signal is found.
- `MISMATCH`: the required signal is clearly absent while another incompatible role is indicated.
- `INCONCLUSIVE`: the small spaCy model or heuristic rules cannot determine the result reliably.

Do not automatically change the Qwen role when a mismatch is found.

## 5. Add deterministic audit warnings

Use stable warning codes so the frontend, fixtures, and later graph stage do not depend on natural-language messages.

### Per-obligation warnings

| Code | Trigger |
| --- | --- |
| `ROLE_CUE_MISMATCH` | Proposed role conflicts with extracted linguistic cues |
| `MULTIPLE_PROPOSITION_FRAMES` | An obligation contains multiple independently checkable frames |
| `UNRESOLVED_SUBJECT` | The analysis cannot resolve a subject |
| `UNRESOLVED_PREDICATE` | The analysis cannot resolve a predicate |
| `PARTIAL_LINGUISTIC_ANALYSIS` | The existing analysis status is partial |
| `NEGATION_SCOPE_UNCLEAR` | Negation is present but its target cannot be resolved confidently |
| `ATTRIBUTION_SCOPE_UNCLEAR` | Reporting predicate and embedded proposition cannot be separated confidently |
| `QUALIFIER_ATTACHMENT_UNCLEAR` | A number, date, or modifier may attach to the wrong predicate |

### Claim-level preservation warnings

| Code | Trigger |
| --- | --- |
| `NEGATION_NOT_PRESERVED` | A negation cue in the claim is absent from all relevant obligation text or source spans |
| `NUMERIC_INFORMATION_NOT_PRESERVED` | A material number or quantifier is absent from the obligation set |
| `TEMPORAL_INFORMATION_NOT_PRESERVED` | A material date or time expression is absent from the obligation set |
| `ATTRIBUTION_NOT_PRESERVED` | A reporting or attribution cue is absent from the obligation set |
| `MODALITY_NOT_PRESERVED` | A material modal cue is absent from the obligation set |
| `LOCATION_NOT_PRESERVED` | A material location is absent from the obligation set |
| `CLAIM_FRAME_NOT_COVERED` | A proposition frame from the original claim has no plausible obligation counterpart |

Warnings must remain descriptive. They must not change retrieval, NLI, graph relations, or verdicts during this stage.

## 6. Define a compact graph-ready summary

The full linguistic output is too detailed to embed directly into every graph node. Add a compact summary derived from the existing analysis.

### Proposed summary

```json
{
  "atomId": "a2",
  "analysisStatus": "complete",
  "roleAudit": "MATCH",
  "subjects": [
    "The tax reduction"
  ],
  "predicates": [
    "be"
  ],
  "cueKinds": [
    "numeric"
  ],
  "modifierKinds": [],
  "entityLabels": [],
  "warnings": []
}
```

The summary should contain:

- Atom ID
- Complete or partial analysis status
- Role-audit status
- Deduplicated subject texts
- Deduplicated predicate lemmas
- Deduplicated cue kinds
- Deduplicated modifier kinds
- Deduplicated entity labels
- Stable warning codes

Do not include the full token table in the summary.

## 7. Define the response contract

Preserve the existing detailed analyses and add claim-level audit information and graph-ready summaries.

```json
{
  "schemaVersion": 2,
  "claimId": "case-001",
  "provider": "spacy",
  "model": "en_core_web_sm@3.8.0",
  "claimAnalysis": {
    "frames": [],
    "cues": [],
    "entities": [],
    "tokens": [],
    "status": "complete",
    "unresolved": []
  },
  "analyses": [],
  "summaries": [
    {
      "atomId": "a2",
      "analysisStatus": "complete",
      "roleAudit": "MATCH",
      "subjects": ["The tax reduction"],
      "predicates": ["be"],
      "cueKinds": ["numeric"],
      "modifierKinds": [],
      "entityLabels": [],
      "warnings": []
    }
  ],
  "claimWarnings": []
}
```

If returning the complete original-claim token table is unnecessary for the UI, `claimAnalysis` may use a compact form. Keep the full detailed form for atoms because it already supports the linguistic panel.

## 8. Update backend models

Add models equivalent to:

```python
class RoleAuditStatus(str, Enum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    INCONCLUSIVE = "INCONCLUSIVE"


class LinguisticWarningCode(str, Enum):
    ROLE_CUE_MISMATCH = "ROLE_CUE_MISMATCH"
    MULTIPLE_PROPOSITION_FRAMES = "MULTIPLE_PROPOSITION_FRAMES"
    UNRESOLVED_SUBJECT = "UNRESOLVED_SUBJECT"
    UNRESOLVED_PREDICATE = "UNRESOLVED_PREDICATE"
    PARTIAL_LINGUISTIC_ANALYSIS = "PARTIAL_LINGUISTIC_ANALYSIS"
    NEGATION_SCOPE_UNCLEAR = "NEGATION_SCOPE_UNCLEAR"
    ATTRIBUTION_SCOPE_UNCLEAR = "ATTRIBUTION_SCOPE_UNCLEAR"
    QUALIFIER_ATTACHMENT_UNCLEAR = "QUALIFIER_ATTACHMENT_UNCLEAR"
    NEGATION_NOT_PRESERVED = "NEGATION_NOT_PRESERVED"
    NUMERIC_INFORMATION_NOT_PRESERVED = "NUMERIC_INFORMATION_NOT_PRESERVED"
    TEMPORAL_INFORMATION_NOT_PRESERVED = "TEMPORAL_INFORMATION_NOT_PRESERVED"
    ATTRIBUTION_NOT_PRESERVED = "ATTRIBUTION_NOT_PRESERVED"
    MODALITY_NOT_PRESERVED = "MODALITY_NOT_PRESERVED"
    LOCATION_NOT_PRESERVED = "LOCATION_NOT_PRESERVED"
    CLAIM_FRAME_NOT_COVERED = "CLAIM_FRAME_NOT_COVERED"


class ObligationLinguisticSummary(BaseModel):
    atom_id: str
    analysis_status: Literal["complete", "partial"]
    role_audit: RoleAuditStatus
    subjects: list[str]
    predicates: list[str]
    cue_kinds: list[LinguisticCueKind]
    modifier_kinds: list[LinguisticModifierKind]
    entity_labels: list[str]
    warnings: list[LinguisticWarningCode]


class LinguisticAnalysisV2Response(BaseModel):
    schema_version: Literal[2] = 2
    claim_id: str
    analyses: list[AtomLinguisticAnalysis]
    summaries: list[ObligationLinguisticSummary]
    claim_warnings: list[LinguisticWarningCode]
    provider: Literal["spacy"] = "spacy"
    model: str
```

Use the project's existing alias conventions for snake-case backend fields and camel-case frontend fields.

## 9. Implement pure audit helpers

Keep audit logic separate from parsing logic so it can be unit-tested without loading the spaCy model.

Suggested pure functions:

```python
audit_role(atom, analysis) -> RoleAuditStatus

obligation_warnings(atom, analysis) -> list[LinguisticWarningCode]

claim_preservation_warnings(
    claim_text,
    claim_analysis,
    atoms,
    atom_analyses,
) -> list[LinguisticWarningCode]

summary_from_analysis(
    atom,
    analysis,
    role_audit,
    warnings,
) -> ObligationLinguisticSummary
```

These helpers should consume typed Pydantic models rather than unvalidated dictionaries.

## 10. Preserve optional and non-blocking execution

Retain the current runtime behavior:

- Lazy, thread-safe spaCy model loading
- Startup pre-warming
- A dedicated single-slot executor or semaphore
- Non-fatal configuration errors
- Parallel execution with evidence retrieval
- Retry support in the frontend
- Stale-result protection in the React hook
- Recorded-demo loading

If linguistic analysis fails, retrieval and NLI must continue.

## 11. Update the frontend without changing the graph

During this stage, update only the linguistic UI and types.

### Type updates

Add frontend equivalents for:

- `RoleAuditStatus`
- `LinguisticWarningCode`
- `ObligationLinguisticSummary`
- Version 2 request and response types

### Linguistic panel updates

For the selected obligation, display:

- Proposed Qwen role
- spaCy role-audit status
- Stable warnings rendered as readable messages
- Existing proposition frames, cues, entities, and syntax details

Retain the disclaimer that linguistic cues do not determine whether an obligation is true or supported.

### Graph boundary

Do not update graph topology in this stage. The graph plan will later consume `ObligationLinguisticSummary` and decide how to display badges, borders, warnings, and tooltips.

## 12. Migrate recorded fixtures

Update each of the 22 recorded demo cases with:

- Linguistic response schema version 2
- Claim-level preservation warnings
- Per-obligation summaries
- Per-obligation role audits
- Stable warning codes

Regenerate the outputs through the updated pipeline, then manually review all warnings. Do not hand-author warning results unless a fixture specifically tests an error condition.

## 13. Testing plan

### 13.1 Preserve existing tests

All existing tests for the following behavior must continue passing:

- Active and passive frames
- Copular frames
- Coordinated predicates
- Nested clauses
- Controlled infinitives
- Typed modifiers
- Negation
- Quantifiers
- Modality
- Attribution
- Temporal and numeric entities
- Named entities
- UTF-16 offsets
- Batch mismatch failures
- Model configuration errors

### 13.2 Role-audit unit tests

Add cases for:

- Numeric role with a percentage
- Numeric role with `at least`
- Temporal role with a year
- Temporal role with a duration
- Attribution role with `said`
- Attribution role with `according to`
- Location role with a GPE or locative modifier
- Causal role with `because`
- Conditional role with `if`
- Modality role with `may`
- Correct role match
- Clear role mismatch
- Inconclusive parse

### 13.3 Decomposition-audit tests

Add cases for:

- Negation lost from all obligations
- Number lost from all obligations
- Date lost from all obligations
- Attribution lost from all obligations
- Modality lost from all obligations
- Original claim frame not covered
- Multiple frames remaining in one obligation
- Partial subject resolution
- Partial predicate resolution

### 13.4 Integration tests

Run the packaged spaCy model over representative version 2 decomposition responses and verify:

- Every atom receives exactly one analysis and one summary.
- Summary atom IDs match decomposition atom IDs.
- Warning codes are deterministic.
- UTF-16 offsets remain valid.
- The frontend can render complete and partial analyses.
- Failure of linguistic analysis does not block retrieval or NLI.

## 14. Manual review plan

Review the 22 demo cases using a compact table:

| Case | Atom | Qwen role | spaCy audit | Warnings | Reviewer decision |
| --- | --- | --- | --- | --- | --- |
| Case ID | Atom ID | Proposed role | Match status | Warning codes | Accept or investigate |

Review specifically for:

- False role-mismatch warnings
- Incorrect negation scope
- Attribution errors
- Numbers or dates attached to the wrong predicate
- Multiple propositions incorrectly treated as one obligation
- Expected limitations of `en_core_web_sm`

## 15. Acceptance criteria

Complete this stage only when:

- All existing linguistic-analysis tests still pass.
- Every version 2 obligation receives one detailed analysis and one compact summary.
- Claim-level and obligation-level warnings use stable enums.
- Qwen role mismatches are flagged but never silently corrected.
- No linguistic output changes retrieval or NLI behavior.
- Failure remains non-fatal to the main pipeline.
- All 22 recorded cases load with the version 2 linguistic schema.
- Warnings have been manually reviewed for all 22 cases.
- The later graph stage can attach summaries by atom ID without reprocessing text.

## 16. Implementation order

1. Confirm claim decomposition schema version 2 is frozen.
2. Define role-audit and warning enums.
3. Add the version 2 linguistic request and response models.
4. Analyse the original claim alongside the obligations.
5. Implement pure role-audit helpers.
6. Implement per-obligation warning helpers.
7. Implement claim-level preservation auditing.
8. Generate compact obligation summaries.
9. Update the API endpoint while preserving non-fatal execution.
10. Update TypeScript types and the linguistic-analysis hook.
11. Update the linguistic panel.
12. Add unit and integration tests.
13. Regenerate the 22 recorded fixtures.
14. Manually review warnings and role audits.
15. Freeze linguistic-analysis schema version 2.
16. Begin the argumentation-graph update only after these criteria pass.

## Deliverables

- Version 2 linguistic request and response schemas
- Original-claim linguistic analysis
- Per-obligation role auditing
- Stable obligation-level warning codes
- Stable claim-level preservation warnings
- Compact graph-ready linguistic summaries
- Updated Pydantic and TypeScript types
- Updated linguistic panel
- Updated recorded fixtures
- Unit, integration, and manual-review results

## Out of scope

The following work belongs to later stages:

- Analysing retrieved evidence sentences with spaCy
- Creating or changing graph nodes
- Creating `DECOMPOSES_TO`, `SUPPORTS`, or `ATTACKS` edges
- Allowing linguistic warnings to override NLI
- Four-way verdict aggregation
- Replacing `en_core_web_sm`
- Moving graph construction to FastAPI

