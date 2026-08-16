# VeriGraph run guide

Run every command from the `verigraph/` directory.

## Prepare before travel

```bash
./run-verigraph --check
./run-verigraph --prepare
./run-verigraph --start
```

`--prepare` installs dependencies and downloads:

- `qwen2.5:3b` in the host Ollama installation (the default CPU-friendly model)
- `BAAI/bge-small-en-v1.5` in `data/models/bge-small-en-v1.5`
- `MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli` in `data/models/deberta-v3-base-mnli-fever-anli`
- the pinned spaCy parser in `backend/.venv`

Those generated assets are ignored by Git. Once preparation finishes, the
live pipeline needs no external document or model request.

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

The recorder calls the local FastAPI backend directly for all 22 approved
cases across the four reference labels. It saves the resulting atoms, candidate
evidence, NLI relations, and linguistic analyses under
`frontend/public/walkthrough/`. The launcher enforces a complete 22-case
snapshot before succeeding. Review and commit those changes before deploying
to Vercel.

## Vercel checklist

- Project root: `frontend`
- No `VERIGRAPH_BACKEND_URL` environment variable
- Build mode: set by `frontend/vercel.json` to `walkthrough`
- Static snapshot: `frontend/public/walkthrough/manifest.json` reports 22 cases
  and 22 recorded runs

The online UI is illustrative only: “Demo mode — results are precomputed. Live
analysis is available locally.”

## API contracts in local live mode

- `GET /api/v1/health`
- `GET /api/v1/demo-cases`
- `GET /api/v1/demo-cases/{id}`
- `POST /api/v1/decompose`
- `POST /api/v1/retrieve`
- `POST /api/v1/classify-support`
- `POST /api/v1/analyze-linguistics`

The browser reaches these endpoints only through the same-origin Next proxy.
The Vercel walkthrough neither requests nor exposes them.
