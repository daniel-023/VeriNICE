# AAAI-27 submission workspace

- `VIDEO_SCRIPT.md`: 4:35 narration and screen sequence.
- `LIVE_RUNBOOK.md`: station setup, visitor paths, failures, and rehearsal gates.
- `draft_paper.tex`: canonical, compilable LaTeX paper source with equations,
  tables, and interface figures. Replace its standard article class with the official
  AAAI author-kit configuration before submission.
- `references.bib`: references cited by the draft.

Compile the working LaTeX draft from this directory with:

```bash
latexmk -pdf draft_paper.tex
```

The repository does not bundle a TeX distribution or the official AAAI style
files. Compiled PDFs and upload archives are generated deliverables and remain
outside version control.

The private 32-case AVeriTeC bundle remains available for internal auditing.
The checked-in walkthrough publishes a separate 18-case qualitative showcase:
15 constructed claims grounded in authentic source excerpts and three curated
AVeriTeC cases, with three entries in each displayed category and a 7/7/2/2
supported/refuted/insufficient/conflicting verdict distribution. Source excerpts
are contiguous, sentence-complete, and accompanied by a visible selection
rationale. Walkthrough schema v6 includes the presentation audit metadata;
graph schema v4 exposes resolved programs as inspectable inference nodes while
keeping unresolved attempts in the Symbolic Checks panel.
