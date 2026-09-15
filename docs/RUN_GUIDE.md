# Running VeriNICE

VeriNICE supports two execution modes:

| Mode | Purpose |
| --- | --- |
| **Local live mode** | Runs decomposition, retrieval, evidence assessment, symbolic reasoning, and verdict composition locally. |
| **Deployed walkthrough** | Replays validated, checked-in results without calling the local FastAPI backend or running model inference. |

The launcher is `run-verinice`. Run all commands from the repository root.

## Prerequisites

- Python 3.11 or 3.12
- Node.js and npm
- [Ollama](https://ollama.com/) for local model inference

Check the native tools before installing project dependencies:

```bash
./run-verinice --check
```

## Prepare the local environment

```bash
./run-verinice --prepare
```

Preparation installs the pinned Python and Node dependencies, downloads
`BAAI/bge-small-en-v1.5` to `data/models/bge-small-en-v1.5`, and pulls
`qwen2.5:7b` through Ollama. Generated model and environment files are ignored
by Git. Once preparation is complete, the live pipeline does not need to fetch
documents or models.

To refresh the constructed showcase sources separately, run:

```bash
./run-verinice --prepare-showcase
```

This is an offline preparation operation, not part of a live verification run.
It validates the prepared source bundle and its traceability metadata.

## Start local live mode

```bash
./run-verinice --start
```

Open [http://localhost:3000](http://localhost:3000). The launcher starts
FastAPI on port 8001 and Next.js on port 3000, and the frontend sends API
requests through its same-origin proxy. Press `Ctrl-C` to stop the managed
processes. Interactive API documentation is available at
[http://localhost:8001/docs](http://localhost:8001/docs) while the backend is
running.

### Model override

The recorded walkthrough was produced with `qwen2.5:7b`. A different Ollama
model can be selected explicitly:

```bash
VERINICE_OLLAMA_MODEL=qwen2.5:3b ./run-verinice --start
```

Changing the model can change decomposition, assessment, and rule mapping;
results will not necessarily reproduce the checked-in walkthrough. Re-record
the walkthrough if a changed configuration is intended for deployment.

## Tests

Run the backend and frontend test suites with:

```bash
./run-verinice --test
```

The launcher uses the pinned local environments prepared by `--prepare`.

## Record and validate the walkthrough

Start the local stack with `./run-verinice --start`, then run the recorder in
a second terminal:

```bash
./run-verinice --record-walkthrough
```

The recorder runs all 18 showcase cases against the local FastAPI backend and
writes their typed decomposition, retrieval, assessment, symbolic reasoning,
composition, and verdict data under `frontend/public/walkthrough/`. It then
builds the static walkthrough assets and fails rather than publishing an
incomplete case set.

Each recorded run must use walkthrough schema version 7 and contain its
assessment, reasoning, composition, atom roles, and recorded verdict. The
Vercel build runs the same walkthrough verifier before compiling the frontend:

```bash
cd frontend
node scripts/verify-walkthrough.mjs
```

AVeriTeC reference annotations used during offline preparation are not written
into runtime inputs. A case's displayed reference verdict is kept separate from
the inference request and result.

## Vercel configuration

Use `frontend` as the Vercel project root. `frontend/vercel.json` installs with
`npm ci`, verifies the recorded runs, sets walkthrough mode for the build, and
executes the Next.js production build.

Do not set `VERINICE_BACKEND_URL` for the static deployment. The deployed
walkthrough replays checked-in schema-v7 runs and does not expose or call the
local FastAPI service. The manifest must report all 18 cases and 18 runs before
deployment succeeds.

## Local API endpoints

The local live service exposes:

- `GET /api/v1/health`
- `GET /api/v1/demo-cases`
- `GET /api/v1/demo-cases/{id}`
- `POST /api/v1/decompose`
- `POST /api/v1/retrieve`
- `POST /api/v1/assess-evidence`
- `POST /api/v1/reason`
- `POST /api/v1/aggregate-verdict`

`POST /api/v1/retrieve` accepts `HYBRID`, `SEMANTIC`, or `LEXICAL` as its
`retrievalMethod`; `HYBRID` is the default. The selected method is returned in
the response and retained in walkthrough provenance.

## Common failures

### A prerequisite check fails

Run `./run-verinice --check` and install the reported missing or unsupported
native dependency. Python must be version 3.11 or 3.12.

### Ollama or the model is unavailable

Confirm that Ollama is running and that `qwen2.5:7b` is installed. Re-running
`./run-verinice --prepare` pulls the configured model.

### A port is already in use

Stop the process occupying port 3000 or 8001, then restart the launcher. The
launcher reports failed health checks instead of silently attaching to an
incompatible service.

### Walkthrough verification fails

Do not hand-edit recorded outputs. Start a healthy local stack, run
`./run-verinice --record-walkthrough`, and address the reported missing case,
schema-v7 mismatch, or invalid result before rebuilding.

### A model override changes results

Return to `qwen2.5:7b` to reproduce the checked-in configuration, or validate
the new results and record the entire walkthrough under the new configuration.

## Related documentation

- [Neural components](NEURAL_COMPONENTS.md)
- [Symbolic reasoning](SYMBOLIC_REASONING.md)
