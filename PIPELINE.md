# VeriGraph pipeline reference

## Current scope

VeriGraph currently runs three model-backed verification stages, a deterministic
atom–evidence argumentation graph, a deterministic four-way draft status, and
one optional linguistic sidecar.

```text
Claim + documents
  → claim decomposition       live
  → candidate retrieval       live
  → grounded claim audit      live, constrained to supplied span IDs
  → argumentation graph       derived from audited selections
  → draft case status         deterministic FastAPI mapping

Atomic claims
  ↘ linguistic structure      live, verdict-neutral sidecar
```

## Stages

| Stage | Implementation | Model / library | Output |
| --- | --- | --- | --- |
| Claim decomposition | Schema-constrained, contextualized prompting through the local Ollama `/api/chat` endpoint | `qwen2.5:7b` by default, overridable with `VERIGRAPH_OLLAMA_MODEL` | A flat `SINGLE`/`AND`/`OR` decomposition of up to 12 standalone obligations; each atom has a verification role and exact UTF-16-grounded `sourceText` |
| Document segmentation | Python sentence segmentation with server-owned character spans | PySBD `0.3.4` | Whole sentences with document-relative UTF-16 offsets |
| Candidate retrieval | Batched normalized embeddings and cosine ranking; up to six sentences per atom, capped at three per document in multidocument cases | Sentence Transformers `3.4.1`, `BAAI/bge-small-en-v1.5` | Semantically nearest candidate sentences; no threshold or scores |
| Grounded claim audit | Schema-constrained local prompting over the claim, obligations, and retrieved candidates; unknown IDs and ungrounded decisive positions are rejected | `qwen2.5:7b` via Ollama | One of `SUPPORT_ONLY`, `ATTACK_ONLY`, `MIXED_OR_MISLEADING`, or `INSUFFICIENT`, a concise rationale, and only supplied support/attack/context span IDs |
| Linguistic structure | Batched dependency parsing and conservative decomposition auditing | spaCy `3.8.7`, `en_core_web_sm@3.8.0` | Claim and atom frames, cues, entities, syntax tokens, role-audit statuses, stable warnings, and compact graph-ready atom summaries |
| Argumentation graph | Frontend-derived version-2 graph; no additional model inference | Existing decomposition, linguistic summaries, retrieval, and audited evidence selections | Case-claim, typed-obligation, and evidence nodes linked by `DECOMPOSES_TO`, `SUPPORTS`, and `ATTACKS`; unselected candidates remain in the evidence pane |
| Four-way draft status | Deterministic FastAPI aggregation; no model call | Validated overall evidence position plus stored selections | Version-1 `SUPPORTED`, `REFUTED`, `NOT_ENOUGH_EVIDENCE`, or `CONFLICTING_EVIDENCE`, with obligation states and a fixed trace; legacy relation-only requests retain composition-aware rules |

All model-generated or parsed spans are validated against unchanged source text
and converted to UTF-16 offsets at the API boundary for exact browser
highlighting. Invalid decomposition output receives one JSON-only repair attempt;
if that also fails, the original claim is retained as one `CORE` atom with a
machine-readable warning so retrieval and the grounded audit can still run.

Candidate retrieval now fuses dense similarity with lexical anchors, including
exact numbers, through reciprocal-rank fusion. Source diversity is a soft
preference rather than a quota. The grounded auditor must preserve exact scope,
comparison, time, quantity, and preliminary-evidence distinctions, and every
decisive position must cite retrieved spans.

## Orchestration

1. The user selects an AVeriTeC sample or supplies an editable claim and up to
   eight documents.
2. Clicking **Decompose Claim** asks Ollama for a schema-constrained,
   source-grounded decomposition.
3. Successful decomposition starts candidate retrieval and a separate
   claim-plus-obligation linguistic audit concurrently.
4. Successful retrieval automatically starts the provenance-constrained claim
   evidence audit.
5. Retrieval, evidence auditing, and linguistics have independent error and retry states.
   Claim edits clear all derived results; document edits retain decomposition
   and linguistics but clear retrieval and evidence auditing.
6. Once the audit completes, the frontend derives the versioned argumentation graph
   and requests the backend-owned verdict aggregation result directly from
   typed obligations, linguistic summaries, candidate evidence, and
   validated claim position and selected relations.
7. In walkthrough mode nothing is computed in the browser: the recorded run
   carries its own aggregation result, so stage 05 renders from the snapshot.

The dataset's reference label is displayed only as metadata. It never supplies
an evidence position, relation, or computed status.

## Application stack

- Frontend: Next.js `16.2.12`, React `18.3.1`, TypeScript, and a server-side
  same-origin `/api/v1/*` proxy.
- Backend: Python `3.9–3.13`, FastAPI `0.115.8`, Pydantic `2.10.6`, Uvicorn,
  HTTPX, NumPy, PyTorch `2.6.0`, and local CPU inference.
- Demo data: an approved, immutable 32-case AVeriTeC dev bundle containing
  claims, four-way reference labels, source metadata, extracted full-text
  documents, and human-written AVeriTeC evidence cards. The cards preserve
  question-answer evidence across page drift and omit gold labels and
  justifications. Source sites are not fetched during requests.
- Deployment: Vercel serves an interactive static walkthrough of recorded
  local runs. The native launcher runs Next.js and FastAPI on the demonstration
  laptop and connects to host Ollama. BGE and DeBERTa weights remain local;
  Vercel hosts no inference backend.

## Public API

- `GET /api/v1/health`
- `GET /api/v1/demo-cases`
- `GET /api/v1/demo-cases/{id}`
- `POST /api/v1/decompose`
- `POST /api/v1/retrieve`
- `POST /api/v1/classify-support`
- `POST /api/v1/aggregate-verdict`
- `POST /api/v1/analyze-linguistics`

## Interpretation limits

- Retrieval means semantic proximity, not evidence relevance or truth.
- An `INSUFFICIENT` audit position is a model-generated draft, not the AVeriTeC
  `NOT_ENOUGH_EVIDENCE` reference label.
- Status aggregation uses only the validated audit position. Reference labels
  and linguistic warnings remain verdict-neutral; a linguistic warning is surfaced
  for inspection and never changes an obligation state.
- The argumentation graph visualizes selected evidence links; it does not infer new
  argument relationships or produce a verdict.
- Absence from an apparently complete list and other closed-world/set reasoning
  are deferred to the argumentation stage.
- Linguistic features describe claim structure and audit preservation; they do
  not influence support classification, graph relations, or verdicts.

## Decomposition basis and evaluation

WiCE remains relevant prior work for real-world entailment and subclaim
verification, but it is not the name of VeriGraph's current method. The
implemented method is **schema-constrained, contextualized decomposition**:
every obligation must be standalone, must preserve the original context, and
must point back to exact source text. Its diagnostic report uses transparent
proxies for the qualities emphasized by newer fine-grained verification work:
atomicity, coverage, sufficiency, non-fabrication, non-redundancy, and
readability. These proxies are engineering checks, not a substitute for human
annotation or the FactLens evaluator.

See Wanner et al. (2024), Mitra et al. (2025), and Hu et al. (2025) in the
[AAAI-27 submission notes](AAAI27_DEMO.md#research-positioning).
