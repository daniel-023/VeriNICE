# VeriGraph pipeline reference

## Current scope

VeriGraph currently runs three model-backed verification stages, a deterministic
atom–evidence argumentation graph, an authoritative deterministic four-way
verdict, and one optional linguistic sidecar.

```text
Claim + documents
  → claim decomposition       live
  → candidate retrieval       live
  → sentence-level NLI        live
  → argumentation graph       derived from NLI outputs
  → case verdict              deterministic FastAPI aggregation

Atomic claims
  ↘ linguistic structure      live, verdict-neutral sidecar
```

## Stages

| Stage | Implementation | Model / library | Output |
| --- | --- | --- | --- |
| Claim decomposition | Versioned structured prompting through the local Ollama `/api/chat` endpoint | `qwen2.5:3b` by default | A flat `SINGLE`/`AND`/`OR` decomposition of up to 12 standalone obligations; each atom has a verification role and exact UTF-16-grounded `sourceText` |
| Document segmentation | Python sentence segmentation with server-owned character spans | PySBD `0.3.4` | Whole sentences with document-relative UTF-16 offsets |
| Candidate retrieval | Batched normalized embeddings and cosine ranking; up to six sentences per atom, capped at three per document in multidocument cases | Sentence Transformers `3.4.1`, `BAAI/bge-small-en-v1.5` | Semantically nearest candidate sentences; no threshold or scores |
| NLI support classification | Each candidate sentence is the premise and its atom is the hypothesis; three-way argmax | Transformers `4.48.3`, `MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli`, revision `6f5cf0a2b59cabb106aca4c287eed12e357e90eb` | `ENTAILMENT`, `CONTRADICTION`, or `NEUTRAL` for every atom–sentence pair |
| Linguistic structure | Batched dependency parsing and conservative decomposition auditing | spaCy `3.8.7`, `en_core_web_sm@3.8.0` | Claim and atom frames, cues, entities, syntax tokens, role-audit statuses, stable warnings, and compact graph-ready atom summaries |
| Argumentation graph | Frontend-derived version-2 graph; no additional model inference | Existing decomposition, linguistic summaries, retrieval, and NLI outputs | Case-claim, typed-obligation, and evidence nodes linked by `DECOMPOSES_TO`, `SUPPORTS`, and `ATTACKS`; neutral candidates remain in the evidence pane |
| Four-way verdict | Deterministic FastAPI aggregation; no model call | Stored decomposition, retrieval, and NLI labels | Version-1 composition-aware `SUPPORTED`, `REFUTED`, `NOT_ENOUGH_EVIDENCE`, or `CONFLICTING_EVIDENCE`, with obligation states and fixed rule trace |

All model-generated or parsed spans are validated against unchanged source text
and converted to UTF-16 offsets at the API boundary for exact browser
highlighting. Invalid decomposition output receives one JSON-only repair attempt;
if that also fails, the original claim is retained as one `CORE` atom with a
machine-readable warning so retrieval and NLI can still run.

## Orchestration

1. The user selects an AVeriTeC sample or supplies an editable claim and up to
   eight documents.
2. Clicking **Decompose Claim** calls Ollama.
3. Successful decomposition starts candidate retrieval and a separate
   claim-plus-obligation linguistic audit concurrently.
4. Successful retrieval automatically starts NLI over every retrieved
   sentence–atom pair.
5. Retrieval, NLI, and linguistics have independent error and retry states.
   Claim edits clear all derived results; document edits retain decomposition
   and linguistics but clear retrieval and NLI.
6. Once NLI completes, the frontend derives the versioned argumentation graph
   and requests the backend-owned verdict aggregation result.
directly from typed obligations, linguistic summaries, candidate evidence, and
sentence-level relations.

The dataset's reference label is displayed only as metadata. It never supplies
an NLI relation or computed verdict.

## Application stack

- Frontend: Next.js `16.2.12`, React `18.3.1`, TypeScript, and a server-side
  same-origin `/api/v1/*` proxy.
- Backend: Python `3.9–3.13`, FastAPI `0.115.8`, Pydantic `2.10.6`, Uvicorn,
  HTTPX, NumPy, PyTorch `2.6.0`, and local CPU inference.
- Demo data: an approved, immutable 22-case AVeriTeC dev bundle containing
  claims, four-way reference labels, source metadata, and extracted full-text
  documents. Trafilatura is used only during preparation; source sites are not
  fetched during requests.
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
- `NEUTRAL` is a sentence-level NLI relation, not the AVeriTeC
  `NOT_ENOUGH_EVIDENCE` label.
- Relations from multiple sentences are not yet aggregated into an atom or case
  verdict. Verdict aggregation uses only stored NLI labels; reference labels and
  linguistic warnings remain verdict-neutral.
- The argumentation graph visualizes observed NLI links; it does not infer new
  argument relationships or produce a verdict.
- Absence from an apparently complete list and other closed-world/set reasoning
  are deferred to the argumentation stage.
- Linguistic features describe claim structure and audit preservation; they do
  not influence support classification, graph relations, or verdicts.
