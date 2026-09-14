# VeriNICE pipeline reference

## Current scope

```text
Claim + documents
  → Decompose Claim          Qwen via Ollama
  → Retrieve Evidence        BGE + lexical anchors
  → Assess Evidence          Qwen, restricted to supplied span IDs
  → Apply Symbolic Rules     Qwen rule mapping + Python execution
  → Verdict                  deterministic composition rules
```

The symbolic registry covers set membership, numeric and temporal comparison,
registered attribute comparisons, distinct-value lower bounds, and
largest/smallest counterexamples. Reusable executors are separated from named
extraction profiles; a profile defines the narrow claim and source pattern that
is eligible for an executor.
Programs use a small versioned IR with grounded lookup, equality/inequality,
numeric comparison, before/after comparison, membership, distinct counting,
and extremum-counterexample steps. Qwen can only map server-issued candidate
and premise IDs into a typed program. Python validates source grounding,
profile preconditions, operand alignment, types, scope, units, and completeness
before computing a result. An unresolved or inapplicable program never affects
the verdict.

## Components

| Stage | Implementation | Output |
| --- | --- | --- |
| Decomposition | Schema-constrained Qwen2.5 through local Ollama | `SINGLE`, `AND`, or `OR` composition and up to 12 atomic claims |
| Segmentation | PySBD | Whole sentences with document-relative UTF-16 offsets |
| Retrieval | User-selectable Hybrid (default), Semantic, or Lexical ranking. Hybrid uses equal-weight reciprocal rank fusion over normalized `BAAI/bge-small-en-v1.5` similarity and exact lexical anchors. | 1–12 candidate anchors per atom; default 6; method is included in provenance; adaptive adjacent reading context remains separate |
| Assessment | Schema-constrained Qwen2.5 | Atom-scoped support, refute, context, sufficiency, missing-information, and material-omission fields |
| Scope validation | Deterministic Python with an offline ISO country/subdivision registry | Match, mismatch, unresolved, or not applicable for each candidate; explicit mismatches are excluded from assessment |
| Symbolic reasoning | Qwen maps eligible inputs to typed rules; a Python operator registry checks premises and executes them | Results marked proved, disproved, unresolved, or not applicable |
| Graph | Frontend schema version 4 | Claim, obligation, inference, evidence, and collapsed context nodes; attempted programs expand to their typed steps and premises |
| Verdict | Deterministic Python aggregation | Four-way verdict plus composition rule trace |

The evidence assessment considers one or more selected sentences jointly while
preserving atomic-claim and source identity. It is not sentence-pair NLI.

## Composition rules

- `AND`: a refuted-only atom refutes the conjunction; otherwise a two-sided
  atom produces conflict; every atom must be support-only for support.
- `OR`: a support-only atom supports the disjunction; otherwise a two-sided
  atom produces conflict; every atom must be refuted-only for refutation.
- `SINGLE`: use the one atomic claim's assessed evidence relations and resolved
  rule results directly.
- A separately grounded material-omission certificate may produce
  `CONFLICTING_EVIDENCE`.

Only support and refute relations from sufficient evidence bundles affect the
graph and verdict. Partial or insufficient selections remain visible as
provisional annotations. Resolved Python symbolic results remain independently
decisive. Reference labels are display-only.

## Terminology

- **Atomic claim** is the public name for a decomposed claim unit. Existing API
  fields that use `obligation` remain unchanged for schema compatibility.
- **Candidate evidence** is a retrieved sentence. Qwen may assess it as
  supporting, refuting, context, or unselected.
- **Symbolic check** covers every attempted operator. A resolved check produces
  a **rule result**; unresolved and inapplicable checks do not affect the verdict.
- The **reasoning graph** displays evidence relations and rule results. It is
  not a formal argumentation semantics.
- **Verdict** is the system output. **Reference label** means the AVeriTeC label
  used only for display and evaluation.

## Orchestration and failure boundaries

1. Decomposition starts retrieval.
2. Successful retrieval starts evidence assessment.
3. Successful assessment starts program-guided reasoning.
4. The reasoning graph and verdict combine assessed relations with resolved rule results.
5. Each stage has its own retry. Claim edits clear all derived results;
   document edits retain decomposition but clear later stages.
6. Reviewer relation edits immediately recompute the graph and verdict while
   retaining symbolic results whose premises remain valid.

## Public API

- `GET /api/v1/health`
- `GET /api/v1/demo-cases`
- `GET /api/v1/demo-cases/{id}`
- `POST /api/v1/decompose`
- `POST /api/v1/retrieve`
- `POST /api/v1/assess-evidence`
- `POST /api/v1/reason`
- `POST /api/v1/aggregate-verdict`

## Deployment

The local demo runs Next.js, FastAPI, Ollama, and BGE natively. Vercel
serves only schema-version-7 runs recorded by the local pipeline. Source sites
and model registries are never accessed during inference.
