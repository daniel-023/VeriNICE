# Third-party data and model notices

## AVeriTeC demo bundle

The bundled demo cases are derived from the AVeriTeC development set at commit
`7c62d1ec8df3fb560d6efe2b85fa191135636f81`, released under
[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/). Cite:

> Schlichtkrull, Guo, and Vlachos. *AVeriTeC: A Dataset for Real-world Claim
> Verification with Evidence from the Web.* NeurIPS Datasets and Benchmarks, 2023.

The bundle includes source URLs, recovered source text, and human-written
AVeriTeC question-answer evidence cards. The cards preserve benchmark evidence
when archived pages drift and omit reference labels and gold justifications.
Bundled data is included only under the repository owner’s confirmed
redistribution clearance; it is not relicensed by the MIT licence covering
VeriGraph code.

## Local models

- Qwen2.5 7B (the default; overridable via `VERIGRAPH_OLLAMA_MODEL`) is
  obtained by Ollama during `./run-verigraph --prepare`.
- `BAAI/bge-small-en-v1.5` is used for semantic candidate matching.
- `MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli` remains available for the
  compatibility relation-only endpoint; the standard claim audit uses Qwen.
- `en_core_web_sm` is used for local linguistic analysis.

Model weights are not committed to this repository. Consult each upstream model
card before redistribution or use outside this demonstration.
