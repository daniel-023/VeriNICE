# VeriGraph at the AAAI-27 Demonstrations Program

This is the working submission brief for the September 18, 2026 deadline. It
separates what is implemented from what still needs evidence, so paper and
video claims stay defensible.

## The one-sentence pitch

VeriGraph turns an opaque fact-checking prediction into an inspectable,
editable chain of verification obligations, source-grounded evidence links,
and deterministic status rules that an audience can challenge in real time.

## What is novel

The strongest contribution is not linguistic analysis by itself. It is the
connection between several AI methods in one audience-facing system:

1. schema-constrained, contextualized claim decomposition;
2. hybrid dense and lexical evidence retrieval;
3. a provenance-constrained overall evidence-position audit;
4. a typed argument graph with deterministic four-way draft-status mapping;
5. reviewer-editable support, attack, and neither relations; and
6. exact source spans and an audit trail for every displayed result.

The linguistic view is supporting instrumentation. It helps a user notice
lost entities, qualifiers, negation, modality, and role drift. It never counts
as evidence and cannot alter the verdict. That boundary is important: it makes
the system easier to inspect without overstating what a parser can prove.

## Research positioning

- WiCE (Kamoi et al., 2023) remains related work for real-world entailment and
  subclaim verification. VeriGraph no longer describes its decomposition as
  “WiCE-style.”
- Wanner et al. (2024) show that downstream factuality results are sensitive
  to the decomposition method and frame decomposition quality through coverage,
  coherence, and atomicity.
- FactLens (Mitra et al., 2025) is the primary contemporary reference for
  fine-grained verification and subclaim quality. VeriGraph's diagnostic report
  follows its concerns—atomicity, coverage, sufficiency, non-fabrication,
  non-redundancy, and readability—but clearly labels the implemented checks as
  deterministic proxies rather than the FactLens evaluator.
- Hu et al. (2025) show that decomposition can introduce noise as well as
  improve verification. VeriGraph responds by exposing decomposition warnings,
  retaining exact source grounding, and measuring downstream verdict behavior.

References:

- Kamoi et al. [WiCE](https://aclanthology.org/2023.emnlp-main.470/)
- Wanner et al. [A Closer Look at Claim Decomposition](https://aclanthology.org/2024.starsem-1.13/)
- Mitra et al. [FactLens](https://aclanthology.org/2025.findings-acl.929/)
- Hu et al. [Decomposition Dilemmas](https://aclanthology.org/2025.naacl-long.320/)

## Acceptance criteria translated into work

The AAAI call emphasizes clarity, significance, relevance, audience engagement,
new ideas, and a convincing live demonstration. VeriGraph addresses those
criteria as follows:

| Criterion | Evidence in the demo | Remaining proof before submission |
| --- | --- | --- |
| Clarity | Five plain-language stages, exact spans, visible rule trace | Five-user dry run; remove any explanation that needs prompting |
| Significance | Shows where a verdict came from and where the pipeline abstained | Short comparison against an opaque label-only baseline |
| AI relevance | NLP, retrieval, grounded evidence auditing, argumentation, and human-AI inspection | State the bridge across methods in abstract and first video minute |
| Engagement | Searchable cases, topic/challenge/verdict filters, live custom claim | Rehearse three audience-selected branches under five minutes |
| New ideas | Typed obligations connected to deterministic, inspectable aggregation | Avoid claiming novelty for standard models or linguistic parsing |
| Reliability | Local models, preflight command, recorded walkthrough fallback | Full offline rehearsal on the actual conference laptop |

## Implemented in this revision

- Added human titles plus topic, challenge, verdict, and free-text sample filters.
- Added metadata for every one of the 32 checked-in cases and featured cases for
  a quick opening path.
- Built and validated a balanced 32-case private bundle: eight cases per
  reference verdict, preserving all 22 cases from the earlier release.
- Added hybrid retrieval so exact numbers and other lexical anchors can recover
  passages that dense similarity alone can miss.
- Replaced the failing sentence-only prediction path with a claim-level audit
  that can select only supplied evidence IDs and cannot see reference labels.
- Added reviewer controls that relabel cited spans and recompute the graph and
  status through deterministic relation rules.
- Preserved human-written AVeriTeC evidence cards next to recovered source text
  so archived-page drift does not silently remove benchmark evidence; cards
  exclude gold labels and justifications.
- Added decomposition diagnostics aligned with recent literature and kept their
  proxy status explicit.
- Replaced model-centric interface labels with task-centric language.
- Added a paper draft, timed video script, and live/backup runbook under
  `submission/`.

## Evidence still required

The private bundle and checked-in static walkthrough contain 32
source-complete cases and 32 freshly recorded runs. Automatic draft status
agrees with the AVeriTeC reference label on 14/32 cases (43.8%): 5/8 supported,
1/8 refuted, 4/8 not-enough-evidence, and 4/8 conflicting-evidence cases. The
median recorded end-to-end latency is 39.36 seconds. This is not an
acceptance-ready verification result, and accuracy is not a claimed
contribution. The defensible demonstration contribution is the inspectable,
provenance-constrained workflow and the review interaction. Before submission:

1. complete error attribution across decomposition, retrieval, grounded audit,
   and aggregation;
2. improve refutation detection and rerun the complete fixed set after every
   model or rule change;
3. report per-label results and decomposition diagnostics, not one headline
   number; and
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
