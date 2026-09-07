# AAAI-27 submission workspace

- `VIDEO_SCRIPT.md`: 4:35 narration and screen sequence.
- `LIVE_RUNBOOK.md`: station setup, visitor paths, failures, and rehearsal gates.
- `draft_paper.tex`: compilable LaTeX paper draft with equations, tables, and
  screenshot placeholders. Replace its standard article class with the official
  AAAI author-kit configuration before submission.
- `references.bib`: references cited by the draft.
- `../output/pdf/veritrace-aaai27-demo-draft.pdf`: rendered review draft generated
  from the paper content. Transfer the final text into the official AAAI-27
  author kit before submission.

Compile the working LaTeX draft from this directory with:

```bash
latexmk -pdf draft_paper.tex
```

The repository does not bundle a TeX distribution or the official AAAI style
files.

The private 32-case AVeriTeC bundle remains available for internal auditing.
The checked-in walkthrough publishes a separate 18-case qualitative showcase:
15 constructed claims grounded in authentic source excerpts and three curated
AVeriTeC cases. Walkthrough schema v6 includes the presentation audit metadata;
graph schema v4 exposes resolved programs as inspectable inference nodes while
keeping unresolved attempts in the Symbolic Checks panel.
