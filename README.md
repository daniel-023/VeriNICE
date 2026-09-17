<p align="center">
  <img src="verinice-readme-banner.jpg" alt="VeriNICE — Verification via Neurosymbolic Inference with Compositional Evidence" width="100%">
</p>

# VeriNICE

VeriNICE (**Verification via Neurosymbolic Inference with Compositional
Evidence**) is an inspectable claim-verification demonstrator. Given a claim
and supplied source documents, it decomposes the claim, retrieves relevant
passages, assesses their relations to each atomic claim, applies eligible
symbolic rules, and deterministically composes a four-way verdict:
`SUPPORTED`, `REFUTED`, `NOT_ENOUGH_EVIDENCE`, or `CONFLICTING_EVIDENCE`.

Verdict-bearing support and refutation remain traceable to exact source spans
or to deterministic checks over source-linked premises. Reference verdicts are
shown only for comparison and never enter inference.

## Pipeline

```mermaid
flowchart TB
    claim[/Claim/] --> decompose["01 · Decompose claim"]
    sources[/Supplied sources/] --> retrieve["02 · Retrieve evidence"]
    decompose --> retrieve
    retrieve --> assess["03 · Assess evidence"]
    assess --> reason["04 · Apply symbolic rules"]
    assess --> compose["05 · Compose verdict"]
    reason --> compose
    compose --> verdict(["Four-way verdict"])
```

Hybrid retrieval combines semantic similarity from normalized BGE embeddings
with BM25 lexical scores through reciprocal-rank fusion. Evidence is
assessed per atomic claim, and support or refutation affects the verdict only
when its evidence bundle is sufficient. When a symbolic rule is
applicable, the model proposes a mapping among backend-generated candidates and
premises; Python validates the operands and executes the rule deterministically.

## Demonstration modes


| Mode                     | Description                                                                    |
| -------------------------- | -------------------------------------------------------------------------------- |
| **Local live mode**      | Runs the complete pipeline locally with Ollama, BGE, FastAPI, and Next.js.     |
| **Recorded walkthrough** | Replays the 18 prepared showcase runs at `/walkthrough` without live inference. |

## Quick start

Requirements: Python 3.11 or 3.12, Node.js/npm, and Ollama. Run commands from
the repository root.

```bash
./run-verinice --check
./run-verinice --prepare
./run-verinice --start
```

Open [http://localhost:3000](http://localhost:3000). Preparation installs the
pinned dependencies, downloads `BAAI/bge-small-en-v1.5` into the ignored
`data/models/` directory, and pulls `qwen2.5:7b` through Ollama.

See the [operations guide](docs/RUN_GUIDE.md) for testing, recording the
walkthrough, model overrides, API endpoints, and Vercel configuration.

## Showcase data

The showcase contains 18 qualitative examples: 15 authored, source-grounded
cases across five subject categories and three cases derived from
[AVeriTeC](https://github.com/MichSchli/AVeriTeC). The examples exercise multi-part claims, direct and conflicting evidence, source-scope filtering,
symbolic rules, and abstention. Source details are retained for traceability.

## Documentation

- [Running VeriNICE](docs/RUN_GUIDE.md)
- [Neurosymbolic components and operator library](docs/NEUROSYMBOLIC_COMPONENTS.md)
- [Dataset and source-material notice](DATA_NOTICE.md)

## Licences

VeriNICE code is released under the [MIT License](LICENSE). Dataset records and
source excerpts are covered separately by the [data notice](DATA_NOTICE.md).
