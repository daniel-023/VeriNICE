# VeriNICE Einstein composite figure

`verinice-composite-einstein.png` is a 2480 × 1600 px, publication-ready composite assembled exclusively from the four supplied VeriNICE screenshots. No interface elements were redrawn or generated.

`verinice-composite-einstein-pipeline.png` is an alternate 2480 × 1600 px composition. It retains the banner-free overview across the top, places the complete five-stage recorded pipeline at lower left, and keeps the complete reasoning graph at lower right. This version emphasizes the end-to-end workflow; the primary composite emphasizes claim decomposition and source evidence.

`verinice-composite-einstein-all-panels.png` is a 3200 × 1800 px all-in-one composition. The banner-free interface spans the upper region. The lower row combines the atomic-claim and evidence details, the complete recorded pipeline, and the full reasoning graph. This is the broadest demo-storyline version and is intended for full two-column width.

`verinice-composite-einstein-components.png` is the AgentGraph-style 3200 × 1800 px alternate. Stronger gutters, individual borders, and circular A–E markers present each screenshot as a separate demo component: (A) interface overview, (B) claim decomposition, (C) evidence inspection, (D) recorded pipeline, and (E) reasoning graph.

`verinice-composite-einstein-components-wide.png` is the recommended landscape variant at 3520 × 1600 px (2.20:1). Panel A spans the upper strip, while panels B–E form one horizontal component row below it. Panels B and C use the complete-height recaptures without internal cropping, so their native lower boundaries remain visible. This reduces overall figure height while retaining the same A–E mapping and unaltered interface content.

## Source captures

- `einstein-overview.png` — 3024 × 742 px panoramic main-interface capture.
- `einstein-overview-no-banner.png` — 3024 × 681 px derived overview used in the composite; the original 61 px illustrative-run banner was removed by joining the untouched areas immediately above and below it.
- `einstein-pipeline.png` — 1308 × 1464 px complete recorded-pipeline capture, retained as a supplementary image and not placed in the composite.
- `einstein-decomposition.png` — 752 × 504 px atomic-claim capture.
- `einstein-evidence.png` — 968 × 978 px evidence capture.
- `einstein-decomposition-complete.png` — 756 × 1192 px complete-height atomic-claim capture used by the wide component figure.
- `einstein-evidence-complete.png` — 968 × 1384 px complete-height evidence capture used by the wide component figure.
- `einstein-reasoning-graph.png` — 2938 × 1534 px full reasoning-graph capture.

These files are byte-identical copies of the supplied screenshots.

## Composite provenance

- Canvas: 2480 × 1600 px, white background, 24 px outer margin, 16 px gutters.
- Overview region: the 3024 × 681 px banner-free overview is proportionally reduced and centred in a 2432 × 601 px framed region.
- Detail region: the complete decomposition capture is proportionally reduced; the evidence capture uses source crop `968×630+0+0` so the native heading, source controls, and decisive photoelectric-effect passage remain visible. Both are centred without added labels in a 626 × 935 px framed region.
- Graph region: the complete graph capture is proportionally reduced and centred in a 1790 × 935 px framed region. Its supported and refuted branches, AND composition, and final REFUTED verdict remain intact.
- Region borders are 2 px neutral grey (`#D6D9DE`). No panel letters, arrows, explanatory overlays, browser chrome, Next.js development badge, or illustrative-run banner remain in the composite.

## Caption

**Figure 1: VeriNICE's inspectable verification workflow.** The overview shows the recorded Einstein example progressing from claim decomposition through evidence assessment. Focused views expose the two atomic claims and the decisive source passage: Albert Einstein received the 1921 Nobel Prize in Physics, but the award cited the photoelectric effect rather than relativity. The reasoning graph traces the resulting supported and refuted branches and their deterministic `AND` composition into the final **Refuted** verdict.

### All-panels alternate

**Figure 1: VeriNICE's inspectable verification workflow.** The interface shows the recorded Einstein claim and its reference verdict. Detailed views expose the two atomic claims and the decisive source passage identifying the photoelectric effect as the basis of the 1921 Nobel Prize in Physics. The recorded pipeline presents decomposition, retrieval, evidence assessment, symbolic rule application, and deterministic verdict generation, while the reasoning graph traces the supported recipient branch and refuted motivation branch through their `AND` composition to the final **Refuted** verdict.

### AgentGraph-style component alternate

**Figure 1: VeriNICE's inspectable verification workflow.** (A) The recorded-example interface shows the compound Einstein claim and its reference verdict. (B) Claim decomposition produces two independently inspectable atomic claims. (C) Evidence inspection exposes the decisive source passage, which identifies the photoelectric effect rather than relativity as the basis of the award. (D) The recorded pipeline shows decomposition, retrieval, evidence assessment, symbolic rule application, and deterministic verdict generation. (E) The reasoning graph traces the supported recipient branch and refuted motivation branch through their `AND` composition to the final **Refuted** verdict.
