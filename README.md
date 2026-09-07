# VeriTrace

VeriTrace shows how a claim-verification result is produced. It decomposes a
complex claim, retrieves candidate evidence, assesses the evidence against each
atomic claim, applies supported symbolic rules, and exposes the deterministic
aggregation behind the verdict.

The reasoning graph links atomic claims to assessed evidence, reading context,
and resolved rule results. Linguistic analysis flags entities, qualifiers, and
role changes, but it does not supply evidence or affect the verdict.

The current live pipeline is:

```text
Claim + source documents
        ↓
Claim decomposition (Qwen2.5 via Ollama)
        ↓
Candidate evidence retrieval (user-selectable Hybrid, Semantic, or Lexical ranking)
        ↓
Jurisdiction scope check (offline ISO data + deterministic Python)
        ↓
Evidence assessment (Qwen2.5 selects only retrieved sentence IDs)
        ↓
Symbolic rule mapping (Qwen2.5) and deterministic execution (Python)
        ↓
Version-4 reasoning graph and deterministic four-way verdict (SUPPORTED / REFUTED / NOT_ENOUGH_EVIDENCE /
CONFLICTING_EVIDENCE)
```

Claim Structure is an optional local spaCy sidecar. It heuristically describes
atom syntax and cues; it is not evidence or a verdict input. Explicit
jurisdiction mismatches remain visible but are excluded from assessment,
symbolic reasoning, the graph, and the verdict. Relations from insufficient
evidence remain visible as provisional annotations.

The retrieval stage defaults to **Hybrid**, which combines normalized BGE
similarity with exact terms, names, dates, and numbers using equal-weight
reciprocal rank fusion. Its collapsed settings
control also supports **Semantic** (BGE only) and **Lexical** (exact-anchor
ranking only); changing the method reruns retrieval and the dependent stages.

## Two intentional modes


| Mode        | Where                           | What is live                                                               |
| ------------- | --------------------------------- | ---------------------------------------------------------------------------- |
| Walkthrough | Vercel                          | Nothing. It presents 18 recorded local runs: 15 source-grounded constructed examples and three AVeriTeC cases. |
| Live demo   | Native processes on your laptop | Qwen/Ollama decomposition, evidence assessment, and rule mapping; BGE retrieval; Python rule execution; spaCy analysis. |

The Vercel UI always states: **“Illustrative recorded run — no live inference
on this website.”** It never attempts to connect to a laptop or
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
which proxies to FastAPI on port 8001. BGE is stored in the gitignored
`data/models/` directory; Ollama stores Qwen in its normal host
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

`--record-walkthrough` uses the already-running native services to record all
18 showcase cases and writes the static assets consumed by Vercel.
The full 32-case bundle remains available locally for internal audits. Recording
must complete successfully before deploying a new walkthrough.

## Vercel deployment

1. Create a Git repository with **`verigraph/` as its root**.
2. Import it into Vercel and set the project root directory to `frontend`.
3. Vercel reads `frontend/vercel.json`, which builds walkthrough mode with no
   backend URL.
4. Commit `frontend/public/walkthrough/` only after
   `./run-verigraph --record-walkthrough` has generated a complete snapshot.

Vercel does not host FastAPI, Ollama, or BGE in this design. This
keeps the permanent public site inexpensive and the in-person demonstration
independent of a fragile remote GPU arrangement.

Every Vercel deployment is Basic Auth-gated by default via
`frontend/proxy.ts`, which protects the app, API proxy, walkthrough JSON,
and generated assets. You must set `BASIC_AUTH_USER` and `BASIC_AUTH_PASSWORD`
in the Vercel project environment, or the deployment serves a 503 to every
visitor. Native local runs remain open unless `VERIGRAPH_AUTH_REQUIRED=1` is
set.

## Demo data and licences

The default showcase is a qualitative collection of 18 cases grouped under
Science, History, Geography, Technology, and Current Affairs. Fifteen are
constructed claims paired with two 150--400-word excerpts from distinct
authoritative sources; six are curated AVeriTeC cases retained for realism.
The claim and intended interpretation may be authored, but quoted evidence is
stored source text rather than an evidence card, paraphrase, or synthetic
quotation. Publisher, canonical URL, retrieval date, extraction offsets, and
content hashes are recorded by the offline preparation process. Maintainers
must review redistribution permission before publishing an excerpt.

The approved 32-case AVeriTeC bundle is stored in `data/demo/averitec/` and
contains claims, reference labels, recovered source documents, source metadata,
audit metadata, and a digest. Inference uses only extracted source text.
AVeriTeC's human question-answer annotations remain in the pinned upstream
dataset for optional offline evaluation and are never copied into demo
documents or model inputs. Reference labels remain dataset metadata and are
never used as pipeline inputs.

The interface offers five category buttons and one selector grouped into
source-grounded examples and AVeriTeC cases. The separate 32-case AVeriTeC
bundle remains available for internal regression and error analysis; it is not
presented as the public showcase or as a benchmark result.

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for AVeriTeC attribution,
source-text clearance, and model notices. VeriTrace code is released under the
[MIT License](LICENSE).

See [PIPELINE.md](PIPELINE.md) for model and API detail, and
[RUNGUIDE.md](RUNGUIDE.md) for operational checks. The AAAI-27 positioning,
submission checklist, and acceptance-focused revisions are in
[AAAI27_DEMO.md](AAAI27_DEMO.md).
