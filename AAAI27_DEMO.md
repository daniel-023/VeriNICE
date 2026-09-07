# VeriTrace at the AAAI-27 Demonstrations Program

This is the working submission brief for the September 18, 2026 deadline. It
separates what is implemented from what still needs evidence, so paper and
video claims stay defensible.

## The one-sentence pitch

VeriTrace turns a fact-verification prediction into an inspectable, editable
chain of atomic claims, cited evidence, rule results, and a deterministic
verdict that an audience can challenge in real time.

## What is novel

The strongest contribution is not linguistic analysis by itself. It is the
connection between several AI methods in one audience-facing system:

1. schema-constrained, contextualized claim decomposition;
2. hybrid dense and lexical evidence retrieval;
3. evidence assessment over atom-scoped bundles with explicit sufficiency;
4. Qwen mapping grounded inputs into a versioned typed program, followed by
   deterministic Python validation and execution;
5. an evidence–inference graph with composition-first four-way verdict aggregation;
6. reviewer-editable support, refute, context, and unselected relations; and
7. exact source spans and an audit trail for every displayed result.

The linguistic view is supporting instrumentation. It helps a user notice
lost entities, qualifiers, negation, modality, and role drift. It never counts
as evidence and cannot alter the verdict. That boundary is important: it makes
the system easier to inspect without overstating what a parser can prove.

## Research positioning

- WiCE (Kamoi et al., 2023) remains related work for real-world entailment and
  subclaim verification. VeriTrace no longer describes its decomposition as
  “WiCE-style.”
- Wanner et al. (2024) show that downstream factuality results are sensitive
  to the decomposition method and frame decomposition quality through coverage,
  coherence, and atomicity.
- FactLens (Mitra et al., 2025) is the primary contemporary reference for
  fine-grained verification and subclaim quality. VeriTrace's diagnostic report
  follows its concerns—atomicity, coverage, sufficiency, non-fabrication,
  non-redundancy, and readability—but clearly labels the implemented checks as
  deterministic proxies rather than the FactLens evaluator.
- Hu et al. (2025) show that decomposition can introduce noise as well as
  improve verification. VeriTrace responds by exposing decomposition warnings,
  retaining exact source grounding, and measuring downstream verdict behavior.
- ProgramFC (Pan et al., 2023) motivates generating reasoning programs that
  invoke specialized functions. VeriTrace adopts that design principle through
  a small typed IR and a conservative operator registry; it does not implement
  ProgramFC wholesale.
- CHECKWHY (Si et al., 2024) motivates explicit evidence-to-inference argument
  structure. VeriTrace does not perform its causal verification task or claim
  formal argumentation semantics.

References:

- Kamoi et al. [WiCE](https://aclanthology.org/2023.emnlp-main.470/)
- Wanner et al. [A Closer Look at Claim Decomposition](https://aclanthology.org/2024.starsem-1.13/)
- Mitra et al. [FactLens](https://aclanthology.org/2025.findings-acl.929/)
- Hu et al. [Decomposition Dilemmas](https://aclanthology.org/2025.naacl-long.320/)
- Pan et al. [ProgramFC](https://aclanthology.org/2023.acl-long.386/)
- Si et al. [CHECKWHY](https://aclanthology.org/2024.acl-long.835/)

## Acceptance criteria translated into work

The AAAI call emphasizes clarity, significance, relevance, audience engagement,
new ideas, and a convincing live demonstration. VeriTrace addresses those
criteria as follows:

| Criterion | Evidence in the demo | Remaining proof before submission |
| --- | --- | --- |
| Clarity | Five plain-language stages, exact spans, visible rule trace | Five-user dry run; remove any explanation that needs prompting |
| Significance | Shows where a verdict came from and where the pipeline abstained | Short comparison against an opaque label-only baseline |
| AI relevance | NLP, retrieval, evidence assessment, symbolic execution, and human-AI inspection | State the bridge across methods in abstract and first video minute |
| Engagement | Five intuitive categories, grouped examples, and live custom input | Rehearse three audience-selected branches under five minutes |
| New ideas | Typed obligations connected to deterministic, inspectable aggregation | Avoid claiming novelty for standard models or linguistic parsing |
| Reliability | Local models, preflight command, recorded walkthrough fallback | Full offline rehearsal on the actual conference laptop |

## Implemented in this revision

- Added category controls and one selector grouped into source-grounded examples
  and AVeriTeC cases.
- Added an 18-case qualitative showcase: 15 constructed claims with two
  authentic authoritative-source excerpts each, plus six curated AVeriTeC cases.
- Built and validated a balanced 32-case private bundle: eight cases per
  reference verdict, preserving all 22 cases from the earlier release.
- Added hybrid retrieval so exact numbers and other lexical anchors can recover
  passages that dense similarity alone can miss.
- Replaced the failing sentence-only prediction path with atom-scoped evidence
  assessment that can select only supplied evidence IDs and cannot see reference labels.
- Added deterministic jurisdiction checks and kept relations from insufficient
  evidence visible but verdict-neutral.
- Replaced hidden fixed neighbour windows with visible, cue-triggered reading
  context and kept every evidence selection scoped to its own atomic claim.
- Added reviewer controls that relabel cited spans and recompute the graph and
  verdict through deterministic composition rules.
- Kept AVeriTeC's human question-answer annotations outside runtime documents
  and model inputs. The demo operates only on recovered source text; upstream
  annotations are reserved for optional offline evaluation.
- Added decomposition diagnostics aligned with recent literature and kept their
  proxy status explicit.
- Replaced model-centric interface labels with task-centric language.
- Added a paper draft, timed video script, and live/backup runbook under
  `submission/`.

## Evidence still required

The private bundle retains 32 source-only cases for internal regression checks.
The hosted schema-version-6 walkthrough contains 18 qualitative demonstrations.
Manual auditing of every displayed relation and resolved rule
result remains required. Before submission:

1. complete error attribution across decomposition, retrieval, evidence assessment,
   and aggregation;
2. rerun and inspect all 18 showcase cases after every model or rule change;
3. avoid presenting the curated cases as an accuracy sample; and
4. conduct a small human study of decomposition quality, evidence correction,
   and trace usefulness because the current diagnostics are only deterministic
   proxies.

## Submission requirements and dates

The official call requires a two-page system paper plus one references-only
page in AAAI two-column style and a demonstration video up to five minutes. It
recommends a 30–60 second overview at the beginning. At least one author must
attend in person, and the demo must have a laptop-based backup mode.

- Register on OpenReview before September 18, 2026.
- Final submission: September 18, 2026, 11:59 PM AOE (UTC−12).
- Notification: November 6, 2026.
- Camera-ready: November 20, 2026.
- Demonstration program: February 18–21, 2027 in Montréal.

Source: [AAAI-27 Demonstrations Program call](https://aaai.org/conference/aaai/aaai-27/demonstration-call/).
