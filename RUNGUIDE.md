# VeriNICE run guide

Run every command from the `verigraph/` directory.

## Prepare before travel

```bash
./run-verigraph --check
./run-verigraph --prepare
./run-verigraph --start
```

`--prepare` installs dependencies and downloads:

- `qwen2.5:7b` in the host Ollama installation (about 4.7 GB)
- `BAAI/bge-small-en-v1.5` in `data/models/bge-small-en-v1.5`
- the pinned spaCy parser in `backend/.venv`

Those generated assets are ignored by Git. Once preparation finishes, the
live pipeline needs no external document or model request.

`qwen2.5:7b` is the decomposition model of record: it is what the published
walkthrough was recorded with, so it is what reproduces those runs. A smaller
model fits in less memory and still works, but it decomposes differently and
will not reproduce the recording — set it deliberately, and re-record if you
intend to present with it:

```bash
VERIGRAPH_OLLAMA_MODEL=qwen2.5:3b ./run-verigraph --start
```

## Run the in-person live demo

```bash
./run-verigraph --start
```

Open <http://localhost:3000>. Stop it with `Ctrl-C`; the launcher terminates
both native server processes.

## Record the public walkthrough

Start from a healthy prepared stack, then run:

```bash
./run-verigraph --record-walkthrough
```

The recorder calls the local FastAPI backend directly for all 18 showcase
cases. It saves the resulting typed
atomic claims, candidate evidence, evidence assessments, symbolic results,
linguistic analyses, and the deterministic verdict under
`frontend/public/walkthrough/`. The launcher requires a complete run for every
curated case before succeeding.

Prepared case documents contain recovered source text only. AVeriTeC's gold
question-answer annotations are read solely during offline dataset preparation
and evaluation; they are never serialized into runtime or walkthrough inputs.

Walkthrough mode computes nothing in the browser, so the verdict has to travel
with the run. A recording made before stage 05 existed will build, but it
renders no current reasoning graph — check that
`frontend/public/walkthrough/runs/*.json` carry `"schemaVersion": 5`, an
`assessment`, `reasoning`, `composition`, a `role` on every atom, and an
aggregation-schema-v3 `verdict`.

The full 32-case local recording can still be summarized for internal error
analysis when needed:

```bash
python3 scripts/summarize_runs.py --output artifacts/evaluation-table.md
```

## Vercel checklist

- Project root: `frontend`
- No `VERIGRAPH_BACKEND_URL` environment variable
- Build mode: set by `frontend/vercel.json` to `walkthrough`
- Static snapshot: `frontend/public/walkthrough/manifest.json` reports 18 cases
  and 18 recorded runs, and every run is schema version 6 with evidence scope
  assessment, symbolic reasoning, and a recorded verdict

The online UI states: “Illustrative recorded run — no live inference on this
website.”

## API contracts in local live mode

- `GET /api/v1/health`
- `GET /api/v1/demo-cases`
- `GET /api/v1/demo-cases/{id}`
- `POST /api/v1/decompose`
- `POST /api/v1/retrieve`
- `POST /api/v1/assess-evidence`
- `POST /api/v1/reason`
- `POST /api/v1/aggregate-verdict`
- `POST /api/v1/analyze-linguistics`

The browser reaches these endpoints only through the same-origin Next proxy.
The Vercel walkthrough neither requests nor exposes them.

`POST /api/v1/retrieve` accepts `retrievalMethod` as `HYBRID`, `SEMANTIC`, or
`LEXICAL`. Hybrid is the default. The selected method is returned with the
retrieval result and recorded in walkthrough provenance.
