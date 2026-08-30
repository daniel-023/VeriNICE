# VeriGraph run guide

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
- optional compatibility model `MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli`
  in `data/models/deberta-v3-base-mnli-fever-anli` (not used by the standard
  claim-audit workflow)
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

The recorder calls the local FastAPI backend directly for every approved case
in the private bundle (32, with eight per reference verdict). It saves the resulting typed
obligations, candidate evidence, audited relations, linguistic analyses, and the
deterministic draft status under `frontend/public/walkthrough/`. The launcher
enforces a complete 22-case snapshot before succeeding.

Walkthrough mode computes nothing in the browser, so the status has to travel
with the run. A recording made before stage 05 existed will build, but it
renders no status panel and no typed obligations — check that
`frontend/public/walkthrough/runs/*.json` carry `"schemaVersion": 2`, a
`composition`, a `role` on every atom, and a `verdict`.

Regenerate the demonstration-set summary afterwards, then review and commit
both before deploying to Vercel:

```bash
python3 scripts/summarize_runs.py --output artifacts/evaluation-table.md
```

## Vercel checklist

- Project root: `frontend`
- No `VERIGRAPH_BACKEND_URL` environment variable
- Build mode: set by `frontend/vercel.json` to `walkthrough`
- Static snapshot: `frontend/public/walkthrough/manifest.json` reports 32 cases
  and 32 recorded runs, and every run is schema version 2 with a recorded
  verdict

The online UI is illustrative only: “Demo mode — results are precomputed. Live
analysis is available locally.”

## API contracts in local live mode

- `GET /api/v1/health`
- `GET /api/v1/demo-cases`
- `GET /api/v1/demo-cases/{id}`
- `POST /api/v1/decompose`
- `POST /api/v1/retrieve`
- `POST /api/v1/classify-support`
- `POST /api/v1/aggregate-verdict`
- `POST /api/v1/analyze-linguistics`

The browser reaches these endpoints only through the same-origin Next proxy.
The Vercel walkthrough neither requests nor exposes them.
