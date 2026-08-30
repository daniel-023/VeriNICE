#!/usr/bin/env python3
"""Render the VeriGraph AAAI-27 content draft as a three-page review PDF."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    FrameBreak,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf" / "verigraph-aaai27-demo-draft.pdf"


def footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#CBD5E1"))
    canvas.line(0.7 * inch, 0.55 * inch, 7.8 * inch, 0.55 * inch)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor("#475569"))
    canvas.drawString(0.7 * inch, 0.35 * inch, "VeriGraph · AAAI-27 demonstration content draft")
    canvas.drawRightString(7.8 * inch, 0.35 * inch, f"{doc.page}")
    canvas.restoreState()


def paragraph(text: str, style) -> Paragraph:
    return Paragraph(text.replace("VeriGraph", "<b>VeriGraph</b>"), style)


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    margin = 0.7 * inch
    gutter = 0.22 * inch
    usable = letter[0] - 2 * margin
    column = (usable - gutter) / 2
    frames = [
        Frame(margin, 0.68 * inch, column, 9.52 * inch, id="left", showBoundary=0),
        Frame(margin + column + gutter, 0.68 * inch, column, 9.52 * inch, id="right", showBoundary=0),
    ]
    doc = BaseDocTemplate(
        str(OUTPUT),
        pagesize=letter,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=0.62 * inch,
        bottomMargin=0.68 * inch,
        title="VeriGraph: Interactive Evidence Auditing",
        author="Anonymous AAAI-27 demonstration submission",
    )
    doc.addPageTemplates(PageTemplate(id="two-column", frames=frames, onPage=footer))

    base = getSampleStyleSheet()
    title = ParagraphStyle(
        "Title",
        parent=base["Title"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=18,
        textColor=colors.HexColor("#0F172A"),
        alignment=TA_CENTER,
        spaceAfter=8,
    )
    anonymous = ParagraphStyle(
        "Anonymous",
        parent=base["Normal"],
        alignment=TA_CENTER,
        fontSize=8.5,
        textColor=colors.HexColor("#475569"),
        spaceAfter=9,
    )
    heading = ParagraphStyle(
        "Heading",
        parent=base["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=10.5,
        leading=12,
        textColor=colors.HexColor("#0F4C5C"),
        spaceBefore=7,
        spaceAfter=3,
    )
    body = ParagraphStyle(
        "Body",
        parent=base["BodyText"],
        fontName="Times-Roman",
        fontSize=8.55,
        leading=10.5,
        textColor=colors.HexColor("#111827"),
        alignment=4,
        spaceAfter=5,
    )
    abstract = ParagraphStyle("Abstract", parent=body, leftIndent=8, rightIndent=8)
    small = ParagraphStyle("Small", parent=body, fontSize=8.1, leading=9.8)

    story = [
        Paragraph("VeriGraph: Interactive Evidence Auditing<br/>with Editable Decision Traces", title),
        Paragraph("Anonymous demonstration submission · content/layout draft", anonymous),
        Paragraph("Abstract", heading),
        paragraph(
            "Fact-verification systems often return a label while hiding the intermediate decisions that made it possible. VeriGraph turns a complex claim into typed verification obligations, retrieves source-grounded evidence, assigns a provenance-constrained claim evidence position, and assembles the selected spans into an argument graph with a deterministic four-way draft status. Visitors can move from a status to its rule, an obligation, an audited relation, and the exact source passage. The system combines local language-model decomposition and evidence auditing, hybrid retrieval, linguistic auditing, and symbolic aggregation. Its contribution is an inspectable bridge between statistical components and human review, not another opaque factuality score.",
            abstract,
        ),
        Paragraph("1. Motivation and significance", heading),
        paragraph(
            "A single fact-checking label compresses several different questions: Was the claim decomposed faithfully? Did retrieval miss a decisive passage? Did the evidence auditor over-read contradiction? Did the final rule respect conjunction, alternatives, and mixed evidence? These questions matter even when the final label is correct, yet they are difficult to ask when intermediate results are discarded or shown as unconnected tables.",
            body,
        ),
        paragraph(
            "VeriGraph makes the chain itself the interface. Every obligation retains exact grounding in the original claim. Every evidence candidate retains document and sentence offsets. The local auditor can select only supplied span IDs. Its overall support-only, attack-only, mixed-or-misleading, or insufficient position maps deterministically to a four-way draft status and trace. Dataset reference labels are metadata and never enter inference.",
            body,
        ),
        FrameBreak(),
        Paragraph("2. System", heading),
        paragraph(
            "The user selects a curated AVeriTeC case or enters a claim with source documents. A local Qwen2.5 model proposes a schema-constrained, contextualized decomposition of at most twelve standalone obligations. Each obligation has a verification role and exact UTF-16 source grounding. Invalid output receives one repair attempt; failure preserves the full claim as one obligation so the pipeline remains usable.",
            body,
        ),
        paragraph(
            "Retrieval segments documents and combines BGE dense similarity with lexical anchors using reciprocal-rank fusion. Exact numbers and names can recover passages that dense similarity ranks poorly. Soft source diversity avoids forcing irrelevant passages into multi-document results.",
            body,
        ),
        paragraph(
            "A schema-constrained Qwen2.5 audit reads the claim, obligations, and retrieved candidates. It must cite supplied span IDs for every decisive position. Exact scope, comparison, time, quantity, preliminary-evidence, and omitted-context rules are part of the contract; unknown IDs and ungrounded decisive positions are rejected.",
            body,
        ),
        paragraph(
            "The frontend builds a typed argument graph from decomposition and audited evidence selections. A backend rule engine maps the validated overall position to a draft status. In live mode, visitors can relabel a cited span as support, attack, or neither; the graph and composition-aware status then recompute from the reviewed edges. A spaCy sidecar audits entities, qualifiers, negation, modality, and role preservation without changing the status.",
            body,
        ),
        Paragraph("3. Interaction design", heading),
        paragraph(
            "Human-titled cases can be searched and filtered by topic, verification challenge, and reference verdict. A visitor selects numerical conflict, cross-source disagreement, or insufficient evidence; opens one obligation; follows its highlighted passage into the full source; and traces that same obligation through the graph to the status rule. The visitor can then correct a support, attack, or neither relation and observe the deterministic graph and status update.",
            body,
        ),
        PageBreak(),
        Paragraph("4. Demonstration experience", heading),
        paragraph(
            "The first minute shows the whole chain on one featured case. The presenter then asks the visitor to select a topic or challenge. Each of the five plain-language stages exposes its output and independent failure state. A three-minute path reaches the exact source and verdict trace; a five-minute research path adds decomposition auditing and a comparison between semantic retrieval and exact lexical anchors.",
            body,
        ),
        paragraph(
            "Live inference runs locally to avoid conference connectivity. The backup is a static interactive walkthrough containing the same typed intermediates from recorded local runs. The current snapshot has 32 cases, balanced at eight cases per reference label.",
            body,
        ),
        Paragraph("5. Evaluation and limitations", heading),
        paragraph(
            "Evaluation separates draft-status agreement from decomposition quality and error source. Deterministic diagnostics cover atomicity, coverage, sufficiency, non-fabrication, non-redundancy, readability, and linguistic warnings. They are engineering proxies, not human judgments or the FactLens evaluator. In the current 32-run snapshot, automatic draft status agrees with the reference label on 14/32 cases (43.8%): 5/8 supported, 1/8 refuted, 4/8 not-enough-evidence, and 4/8 conflicting-evidence cases. Median end-to-end latency on the recording laptop is 39.36 seconds. These results do not support an autonomous-verification claim, and accuracy is not presented as a contribution. Before final submission we will complete error attribution and conduct a small human study of decomposition quality, evidence correction, and trace usefulness.",
            body,
        ),
        paragraph(
            "VeriGraph audits supplied documents; it does not establish source authority or perform open-web fact checking. Retrieval rank is not truth, an automatic evidence position is not a human verdict, and the graph does not infer new relations. These boundaries are stated in the interface and narration.",
            body,
        ),
        FrameBreak(),
        Paragraph("6. Related work and contribution", heading),
        paragraph(
            "WiCE introduced real-world entailment with subclaim-oriented verification in Wikipedia contexts [1]. Wanner et al. showed that factuality evaluation is sensitive to decomposition and studied coverage, coherence, and atomicity [2]. FactLens provides a newer benchmark and evaluators for fine-grained verification, emphasizing context preservation and semantic equivalence [3]. Hu et al. demonstrated that decomposition can add downstream noise as well as benefit [4].",
            body,
        ),
        paragraph(
            "VeriGraph operationalizes these concerns in an interactive audit surface. Its novelty is the inspectable, editable connection from schema-grounded obligations through cited evidence positions to a deterministic argument and status trace. It does not claim novelty for the component models or linguistic parser.",
            body,
        ),
        Paragraph("7. Audience relevance", heading),
        paragraph(
            "The demonstration connects natural-language processing, information retrieval, explainable AI, argumentation, and human-AI interaction. Researchers can inspect failure propagation; practitioners can distinguish a missing passage from an unsupported contradiction; educators can use the graph to show why a fact-checking label is not a primitive fact. The system is most informative when it is imperfect because disagreement has a precise location.",
            body,
        ),
        Paragraph("8. Readiness", heading),
        paragraph(
            "The repository includes typed API contracts, deterministic fallbacks, automated backend and frontend tests, a preflight command, recorded walkthrough assets, and an offline runbook. The final submission gate requires three consecutive cold starts, three offline walkthrough rehearsals, and a manifest/evaluation audit before any 32-case claim is used.",
            body,
        ),
        PageBreak(),
        Paragraph("References", title),
        Spacer(1, 6),
        paragraph("[1] R. Kamoi et al. 2023. <i>WiCE: Real-World Entailment for Claims in Wikipedia.</i> EMNLP 2023. doi:10.18653/v1/2023.emnlp-main.470.", small),
        paragraph("[2] M. Wanner, S. Ebner, Z. Jiang, M. Dredze, and B. Van Durme. 2024. <i>A Closer Look at Claim Decomposition.</i> *SEM 2024, 153–175. doi:10.18653/v1/2024.starsem-1.13.", small),
        paragraph("[3] K. Mitra, D. Zhang, S. Rahman, and E. Hruschka. 2025. <i>FactLens: Benchmarking Fine-Grained Fact Verification.</i> Findings of ACL 2025, 18085–18096. doi:10.18653/v1/2025.findings-acl.929.", small),
        paragraph("[4] Q. Hu, Q. Long, and W. Wang. 2025. <i>Decomposition Dilemmas: Does Claim Decomposition Boost or Burden Fact-Checking Performance?</i> NAACL 2025, 6313–6336. doi:10.18653/v1/2025.naacl-long.320.", small),
        Spacer(1, 8),
        paragraph("This third page contains references only. The final manuscript must be transferred into the official AAAI-27 author kit and rechecked against the current call before submission.", small),
    ]
    doc.build(story)
    print(OUTPUT)


if __name__ == "__main__":
    main()
