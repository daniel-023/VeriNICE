# VeriGraph

VeriGraph makes fact-verification steps inspectable without presenting a
premature verdict. The current live pipeline is:

```text
Claim + source documents
        ↓
LLM claim decomposition (Qwen2.5 via Ollama)
        ↓
Semantic candidate matching (BGE embeddings)
        ↓
Sentence-level NLI (DeBERTa)
        ↓
Argumentation graph and four-way verdict — pending
```

Linguistic structure is an optional local spaCy sidecar. It describes atom
syntax and cues; it is not evidence or a verdict input.

## Two intentional modes

| Mode | Where | What is live |
| --- | --- | --- |
| Walkthrough | Vercel | Nothing. It presents recorded local runs of approved AVeriTeC cases. |
| Live demo | Docker Compose on your laptop | Qwen/Ollama decomposition, BGE retrieval, DeBERTa NLI, and spaCy analysis. |

The Vercel UI always states: **“Demo mode — results are precomputed. Live
analysis is available locally.”** It never attempts to connect to a laptop or
to a public inference service.

## Local live demo

Requirements: Docker Desktop with its daemon running and sufficient local disk
space for Qwen2.5 7B plus the BGE and DeBERTa weights.

Optional local overrides can be placed in `.env`:

```bash
cp .env.example .env
```

```bash
cd verigraph
./run-verigraph --prepare  # one-time model download
./run-verigraph --start
```

Open <http://127.0.0.1:3000>. The browser talks only to the local Next.js
container; it proxies to FastAPI inside Docker Compose. The source documents,
embedding model, NLI model, and Ollama model cache are local after preparation,
so the conference demo does not require Internet access.

If the live stack is unavailable, open the local `/walkthrough` route for the
same recorded fallback used by Vercel.

Useful commands:

```bash
./run-verigraph --check
./run-verigraph --test
./run-verigraph --record-walkthrough
```

`--record-walkthrough` runs four representative cases—one per reference
label—through the local pipeline and writes the static assets consumed by
Vercel. It must complete successfully before deploying a new walkthrough.

## Vercel deployment

1. Create a Git repository with **`verigraph/` as its root**.
2. Import it into Vercel and set the project root directory to `frontend`.
3. Vercel reads `frontend/vercel.json`, which builds walkthrough mode with no
   backend URL.
4. Commit `frontend/public/walkthrough/` only after
   `./run-verigraph --record-walkthrough` has generated a complete snapshot.

Vercel does not host FastAPI, Ollama, BGE, or DeBERTa in this design. This
keeps the permanent public site inexpensive and the in-person demonstration
independent of a fragile remote GPU arrangement.

## Demo data and licences

The approved 22-case AVeriTeC bundle is stored in `data/demo/averitec/` and
contains claims, reference labels, full source documents, titles, URLs, audit
metadata, and a digest. Reference labels remain dataset metadata and are never
used as pipeline outputs.

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for AVeriTeC attribution,
source-text clearance, and model notices. VeriGraph code is released under the
[MIT License](LICENSE).

See [PIPELINE.md](PIPELINE.md) for model and API detail, and
[RUNGUIDE.md](RUNGUIDE.md) for operational checks.
