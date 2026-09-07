#!/usr/bin/env python3
"""Render the VeriTrace AAAI-27 content draft as a three-page review PDF."""

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
OUTPUT = ROOT / "output" / "pdf" / "veritrace-aaai27-demo-draft.pdf"


def footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#CBD5E1"))
    canvas.line(0.7 * inch, 0.55 * inch, 7.8 * inch, 0.55 * inch)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor("#475569"))
    canvas.drawString(0.7 * inch, 0.35 * inch, "VeriTrace · AAAI-27 demonstration content draft")
    canvas.drawRightString(7.8 * inch, 0.35 * inch, f"{doc.page}")
    canvas.restoreState()


def paragraph(text: str, style) -> Paragraph:
    return Paragraph(text.replace("VeriTrace", "<b>VeriTrace</b>"), style)


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
        title="VeriTrace: From Evidence to Logic",
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
        Paragraph("From Evidence to Logic:<br/>An Interactive Neuro-Symbolic System for Fact Verification", title),
        Paragraph("Anonymous demonstration submission · content/layout draft", anonymous),
        Paragraph("Abstract", heading),
        paragraph(
            "Fact-verification systems often return a verdict without exposing the decisions behind it. VeriTrace decomposes a complex claim into atomic claims, retrieves source sentences, assesses evidence bundles, and applies supported symbolic rules. Qwen maps eligible source-linked inputs to typed rules; Python checks the cited premises and executes them. An evidence-inference graph links evidence, context, and rule results to a deterministic four-way verdict.",
            abstract,
        ),
        Paragraph("1. Motivation and significance", heading),
        paragraph(
            "A single fact-checking label compresses several different questions: Was the claim decomposed faithfully? Did retrieval miss a decisive passage? Did the evidence auditor over-read contradiction? Did the final rule respect conjunction, alternatives, and mixed evidence? These questions matter even when the final label is correct, yet they are difficult to ask when intermediate results are discarded or shown as unconnected tables.",
            body,
        ),
        paragraph(
            "VeriTrace makes the chain itself the interface. Every atomic claim retains exact offsets in the original claim, and every candidate sentence retains document offsets. Qwen can select only retrieved sentence IDs. The verdict is computed from assessed evidence relations, resolved rule results, and claim composition. Dataset reference labels never enter inference.",
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
            "A schema-constrained Qwen2.5 assessment reads the claim, atomic claims, and retrieved candidates. It must cite retrieved sentence IDs for support, refutation, or context. It also records sufficiency, missing information, and material omission; unknown IDs and unsupported decisive positions are rejected.",
            body,
        ),
        paragraph(
            "For eligible set-membership, numeric, and temporal checks, Qwen maps locally extracted operands to typed rules but cannot return a calculated result. Python validates the cited premises and executes the rule. The frontend presents assessed evidence and resolved rule results in a reasoning graph. Visitors can revise an evidence relation; the graph and verdict then recompute from the displayed relations and composition rule. A spaCy sidecar describes entities, qualifiers, negation, modality, and roles without changing the verdict.",
            body,
        ),
        Paragraph("3. Interaction design", heading),
        paragraph(
            "Human-titled cases can be searched and filtered by topic, verification challenge, and reference verdict. A visitor can open an atomic claim, follow its candidate evidence into the full source, inspect any applicable rule result, and trace the displayed relations through the reasoning graph to the verdict. Revising a support, refutation, or unselected relation recomputes the graph and verdict deterministically.",
            body,
        ),
        PageBreak(),
        Paragraph("4. Demonstration experience", heading),
        paragraph(
            "The first minute shows the whole chain on one curated case. The presenter then asks the visitor to select a category or case. Each of the five plain-language stages exposes its output and independent failure state. A three-minute path reaches the exact source and verdict trace; a five-minute research path adds decomposition auditing and a comparison between semantic retrieval and exact lexical anchors.",
            body,
        ),
        paragraph(
            "Live inference runs locally to avoid conference connectivity. The backup is a static interactive walkthrough containing the same typed intermediates from six recorded feature demonstrations. The cases are selected for distinct, inspectable behaviours rather than benchmark coverage.",
            body,
        ),
        Paragraph("5. Demonstration cases and limitations", heading),
        paragraph(
            "The walkthrough covers six complementary paths: multi-atom support, jurisdiction filtering, conservative treatment of insufficient evidence, conjunctive aggregation with one unresolved atom, a numeric-operator boundary, and an explicit failure case. These examples are qualitative demonstrations, not an accuracy sample. The symbolic layer is presented as an inspectable reasoning mechanism rather than an established accuracy improvement.",
            body,
        ),
        paragraph(
            "VeriTrace verifies claims against supplied documents; it does not establish source authority or perform open-web fact checking. Retrieval rank is not truth, an evidence assessment is not a professional fact-check, and a rule result is valid only for its displayed premises and supported operator.",
            body,
        ),
        FrameBreak(),
        Paragraph("6. Related work and contribution", heading),
        paragraph(
            "WiCE introduced real-world entailment with subclaim-oriented verification in Wikipedia contexts [1]. Wanner et al. showed that factuality evaluation is sensitive to decomposition and studied coverage, coherence, and atomicity [2]. FactLens provides a newer benchmark and evaluators for fine-grained verification, emphasizing context preservation and semantic equivalence [3]. Hu et al. demonstrated that decomposition can add downstream noise as well as benefit [4].",
            body,
        ),
        paragraph(
            "ProgramFC motivates reasoning-program generation followed by execution with specialized functions. CHECKWHY motivates explicit structures connecting evidence to intermediate inferences. VeriTrace adopts these principles through a small typed program IR, a conservative Python operator registry, and an inspectable evidence-inference graph; it does not implement either system wholesale or claim formal argumentation semantics.",
            body,
        ),
        Paragraph("7. Audience relevance", heading),
        paragraph(
            "The demonstration connects natural-language processing, information retrieval, explainable AI, argumentation, and human-AI interaction. Researchers can inspect failure propagation; practitioners can distinguish a missing passage from an unsupported contradiction; educators can use the graph to show why a fact-checking label is not a primitive fact. The system is most informative when it is imperfect because disagreement has a precise location.",
            body,
        ),
        Paragraph("8. Readiness", heading),
        paragraph(
            "The repository includes typed API contracts, deterministic fallbacks, automated backend and frontend tests, a preflight command, recorded walkthrough assets, and an offline runbook. The final submission gate requires three consecutive cold starts, three offline walkthrough rehearsals, and a manual audit of every relation and symbolic premise shown in the 18-case showcase.",
            body,
        ),
        PageBreak(),
        Paragraph("References", title),
        Spacer(1, 6),
        paragraph("[1] R. Kamoi et al. 2023. <i>WiCE: Real-World Entailment for Claims in Wikipedia.</i> EMNLP 2023. doi:10.18653/v1/2023.emnlp-main.470.", small),
        paragraph("[2] M. Wanner, S. Ebner, Z. Jiang, M. Dredze, and B. Van Durme. 2024. <i>A Closer Look at Claim Decomposition.</i> *SEM 2024, 153–175. doi:10.18653/v1/2024.starsem-1.13.", small),
        paragraph("[3] K. Mitra, D. Zhang, S. Rahman, and E. Hruschka. 2025. <i>FactLens: Benchmarking Fine-Grained Fact Verification.</i> Findings of ACL 2025, 18085–18096. doi:10.18653/v1/2025.findings-acl.929.", small),
        paragraph("[4] Q. Hu, Q. Long, and W. Wang. 2025. <i>Decomposition Dilemmas: Does Claim Decomposition Boost or Burden Fact-Checking Performance?</i> NAACL 2025, 6313–6336. doi:10.18653/v1/2025.naacl-long.320.", small),
        paragraph("[5] L. Pan et al. 2023. <i>Fact-Checking Complex Claims with Program-Guided Reasoning.</i> ACL 2023. doi:10.18653/v1/2023.acl-long.386.", small),
        paragraph("[6] J. Si et al. 2024. <i>CHECKWHY: Causal Fact Verification via Argument Structure.</i> ACL 2024. doi:10.18653/v1/2024.acl-long.835.", small),
        Spacer(1, 8),
        paragraph("This third page contains references only. The final manuscript must be transferred into the official AAAI-27 author kit and rechecked against the current call before submission.", small),
    ]
    doc.build(story)
    print(OUTPUT)


if __name__ == "__main__":
    main()
