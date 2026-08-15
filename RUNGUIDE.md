# VeriGraph run guide

Run every command from the `verigraph/` directory.

## Prepare before travel

```bash
./run-verigraph --check
./run-verigraph --prepare
./run-verigraph --start
```

`--prepare` downloads and persists:

- `qwen2.5:7b` in `data/runtime/ollama/`
- `BAAI/bge-small-en-v1.5` in `data/models/`
- `MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli` in `data/models/`
- the pinned spaCy parser in the backend image

Those generated assets are ignored by Git. Once preparation and image builds
finish, the live pipeline needs no external document or model request.

## Run the in-person live demo

```bash
./run-verigraph --start
```

Open <http://127.0.0.1:3000>. Stop it with `Ctrl-C` or, from another terminal:

```bash
docker compose down
```

If a port is occupied, change `VERIGRAPH_PORT` in a local `.env` file.

## Record the public walkthrough

Start from a healthy prepared stack, then run:

```bash
./run-verigraph --record-walkthrough
```

The recorder uses the current local API for four representative cases, one per
reference label. It saves the resulting atoms, candidate evidence, NLI
relations, and linguistic analyses under `frontend/public/walkthrough/`. The
build fails if a curated case lacks a complete recorded run. Review those
changes before committing and deploying to Vercel.

## Vercel checklist

- Project root: `frontend`
- No `VERIGRAPH_BACKEND_URL` environment variable
- Build mode: set by `frontend/vercel.json` to `walkthrough`
- Static snapshot: `frontend/public/walkthrough/manifest.json` reports 4 cases
  and 4 recorded runs

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
