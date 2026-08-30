# VeriGraph

VeriGraph lets an audience follow a fact check instead of asking them to trust
one opaque score. It turns a complex claim into grounded verification
obligations, finds candidate passages, audits the overall evidence position
with exact span citations, and exposes the deterministic mapping that produces
the draft case status.

The main contribution is the inspectable bridge from language models to a
rule-governed argument graph. Linguistic analysis is useful supporting
instrumentation: it catches lost entities, qualifiers, and role drift, but it
does not supply evidence and cannot change a verdict.

The current live pipeline is:

```text
Claim + source documents
        ↓
Schema-constrained claim decomposition (Qwen2.5 via Ollama)
        ↓
Hybrid candidate retrieval (BGE embeddings + lexical anchors)
        ↓
Provenance-constrained claim audit (Qwen2.5 selects only supplied span IDs)
        ↓
Deterministic atom–evidence argumentation graph
        ↓
Deterministic four-way verdict (SUPPORTED / REFUTED / NOT_ENOUGH_EVIDENCE /
CONFLICTING_EVIDENCE)
```

Linguistic structure is an optional local spaCy sidecar. It describes atom
syntax and cues; it is not evidence or a verdict input.

## Two intentional modes


| Mode        | Where                           | What is live                                                               |
| ------------- | --------------------------------- | ---------------------------------------------------------------------------- |
| Walkthrough | Vercel                          | Nothing. It presents recorded local runs of approved AVeriTeC cases.       |
| Live demo   | Native processes on your laptop | Qwen/Ollama decomposition and evidence audit, BGE retrieval, and spaCy analysis. |

The Vercel UI always states: **“Demo mode — results are precomputed. Live
analysis is available locally.”** It never attempts to connect to a laptop or
to a public inference service.

## Local live demo

Requirements: Python 3, Node.js/npm, and Ollama Desktop. Native execution keeps
the backend and model files on the host instead of in a container. Docker
Desktop on macOS shares files into containers through a slow virtualized
layer, which stalls model loads and file-watching; running natively avoids
that entirely. Decomposition uses `qwen2.5:7b`, the model the published
walkthrough was recorded with; `VERIGRAPH_OLLAMA_MODEL` overrides it, at the
cost of no longer reproducing those runs.

Optional local overrides can be placed in `.env.local`:

```bash
cp .env.example .env.local
```

```bash
cd verigraph
./run-verigraph --prepare  # one-time dependency/model setup
./run-verigraph --start
```

Open [http://localhost:3000](http://localhost:3000). The browser talks to the local Next.js process,
which proxies to FastAPI on port 8001. BGE and the compatibility NLI model are stored in the
gitignored `data/models/` directory; Ollama stores its model in its normal host
installation. After preparation, inference is local and does not fetch source
documents or model files.

If the live stack is unavailable, open the local `/walkthrough` route for the
same recorded fallback used by Vercel.

Useful commands:

```bash
./run-verigraph --check
./run-verigraph --test
./run-verigraph --record-walkthrough
```

`--record-walkthrough` uses the already-running native services to run all 32
approved cases—eight per reference label—and writes the static assets
consumed by Vercel. It must complete successfully before deploying a new
walkthrough.

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

Every Vercel deployment is Basic Auth-gated by default via
`frontend/proxy.ts`, which protects the app, API proxy, walkthrough JSON,
and generated assets. You must set `BASIC_AUTH_USER` and `BASIC_AUTH_PASSWORD`
in the Vercel project environment, or the deployment serves a 503 to every
visitor. Native local runs remain open unless `VERIGRAPH_AUTH_REQUIRED=1` is
set.

## Demo data and licences

The approved 32-case AVeriTeC bundle is stored in `data/demo/averitec/` and
contains claims, reference labels, recovered source documents, human-written
AVeriTeC evidence cards with their source URLs, audit metadata, and a digest.
The cards preserve evidence when archived pages drift; they never contain the
reference label or gold justification. Reference labels remain dataset
metadata and are never used as pipeline inputs.

The sample browser supports plain-language search plus topic, challenge, and
reference-verdict filters. The private catalog is now balanced at eight cases
per verdict and preserves every case from the earlier 22-case release. The
static walkthrough contains complete recorded runs for all 32 cases. Generate
the descriptive run audit with `python3 scripts/summarize_runs.py`; the report
is explicit that this curated demonstration set is not a held-out benchmark.

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for AVeriTeC attribution,
source-text clearance, and model notices. VeriGraph code is released under the
[MIT License](LICENSE).

See [PIPELINE.md](PIPELINE.md) for model and API detail, and
[RUNGUIDE.md](RUNGUIDE.md) for operational checks. The AAAI-27 positioning,
submission checklist, and acceptance-focused revisions are in
[AAAI27_DEMO.md](AAAI27_DEMO.md).
