"use client";

import { useState } from "react";
import type {
  AtomLinguisticAnalysis,
  DecomposedAtom,
  LinguisticArgument,
  LinguisticModifier,
  LinguisticSpan,
  ObligationLinguisticSummary,
  StageState,
} from "@/lib/types";

const warningLabels: Record<string, string> = {
  ROLE_CUE_MISMATCH: "The atomic-claim type does not match the language cues found.",
  MULTIPLE_PROPOSITION_FRAMES: "This atomic claim may still contain more than one proposition.",
  UNRESOLVED_SUBJECT: "The parser did not identify a subject.",
  UNRESOLVED_PREDICATE: "The parser did not identify a predicate.",
  PARTIAL_LINGUISTIC_ANALYSIS: "The parser resolved only part of this atomic claim.",
  NEGATION_SCOPE_UNCLEAR: "The scope of negation is unclear.",
  ATTRIBUTION_SCOPE_UNCLEAR: "The attribution scope is unclear.",
  QUALIFIER_ATTACHMENT_UNCLEAR: "A qualifier may attach to the wrong predicate.",
};

function plainLabel(value: string): string {
  const text = value.replaceAll("_", " ");
  return `${text.charAt(0).toUpperCase()}${text.slice(1)}`;
}

function Preview({ text, feature }: { text: string; feature: LinguisticSpan | null }) {
  if (!feature || feature.start < 0 || feature.end <= feature.start || feature.end > text.length) return <>{text}</>;
  return <>{text.slice(0, feature.start)}<mark>{text.slice(feature.start, feature.end)}</mark>{text.slice(feature.end)}</>;
}

function FeatureButton({ feature, label, selected, onSelect }: {
  feature: LinguisticSpan; label: string; selected: boolean; onSelect: (feature: LinguisticSpan) => void;
}) {
  return (
    <button type="button" className="linguistic-feature" aria-pressed={selected}
      aria-label={`${label}: ${feature.text}`} onClick={() => onSelect(feature)}>
      <span>{feature.text}</span><small>{label}</small>
    </button>
  );
}

function SpanList({ items, label, activeId, onSelect }: {
  items: LinguisticSpan[]; label: string; activeId: string | null; onSelect: (feature: LinguisticSpan) => void;
}) {
  if (!items.length) return <span className="linguistic-missing">Not explicitly identified</span>;
  return <span className="linguistic-feature-list">{items.map((item) => (
    <FeatureButton key={item.id} feature={item} label={label} selected={item.id === activeId} onSelect={onSelect} />
  ))}</span>;
}

function statusLabel(state: StageState, partial: boolean): string {
  if (state === "running") return "Parsing";
  if (state === "error") return "Unavailable";
  if (state === "complete") return partial ? "Review needed" : "Parsed";
  return "Waiting";
}

export function LinguisticPanel({ atom, analysis, summary, state, error, onRetry, open = false, onToggle }: {
  atom: DecomposedAtom;
  analysis: AtomLinguisticAnalysis | null;
  summary: ObligationLinguisticSummary | null;
  state: StageState;
  error: string | null;
  onRetry: () => void;
  open?: boolean;
  onToggle?: () => void;
}) {
  const [activeFeature, setActiveFeature] = useState<LinguisticSpan | null>(null);
  const warningCount = summary?.warnings.length ?? 0;
  const robustCues = analysis?.cues.filter((cue) => cue.kind !== "quantifier") ?? [];
  const cueCount = robustCues.length;
  const bodyId = `claim-structure-body-${atom.id}`;
  const activeId = activeFeature?.id ?? null;
  const featureButtons = (items: Array<{ feature: LinguisticSpan; label: string }>) => (
    items.length ? <span className="linguistic-feature-list">{items.map(({ feature, label }) => (
      <FeatureButton key={feature.id} feature={feature} label={label} selected={feature.id === activeId} onSelect={setActiveFeature} />
    ))}</span> : <span className="linguistic-missing">Not explicitly identified</span>
  );
  const argumentsView = (items: LinguisticArgument[]) => featureButtons(items.map((feature) => ({ feature, label: plainLabel(feature.role) })));
  const modifiersView = (adjuncts: LinguisticModifier[], others: LinguisticSpan[]) => featureButtons([
    ...adjuncts.map((feature) => ({ feature, label: plainLabel(feature.kind) })),
    ...others.map((feature) => ({ feature, label: "Other modifier" })),
  ]);

  return (
    <aside className="linguistic-panel" aria-labelledby={`claim-structure-heading-${atom.id}`}>
      <div className="linguistic-heading">
        <h3 id={`claim-structure-heading-${atom.id}`}>Claim Structure</h3>
        <span className="linguistic-heading-spacer" />
        <span className="claim-structure-summary" aria-live="polite">
          {statusLabel(state, analysis?.status === "partial")} · {warningCount} warning{warningCount === 1 ? "" : "s"} · {cueCount} cue{cueCount === 1 ? "" : "s"}
        </span>
        {onToggle ? <button type="button" className="linguistic-toggle" aria-expanded={open} aria-controls={bodyId} onClick={onToggle}>
          {open ? "Close" : "Open"}<span className="sr-only"> claim structure</span>
        </button> : null}
      </div>
      {!open ? null : <div className="linguistic-body" id={bodyId}>
        <p className="linguistic-note">Parser cues only; not verdict evidence.</p>
        {state === "running" ? <p className="linguistic-state" aria-live="polite">Parsing the atomic claim…</p>
          : state === "error" ? <div className="linguistic-error" role="status"><p>{error ?? "Claim-structure analysis is unavailable."}</p><button type="button" onClick={onRetry}>Retry Claim Structure</button></div>
          : analysis ? <>
            {warningCount ? <section className="linguistic-group linguistic-inspect" aria-label="Decomposition warnings"><h4>Decomposition warnings</h4><ul className="linguistic-warnings">{summary!.warnings.map((item) => <li key={item}>{warningLabels[item] ?? plainLabel(item)}</li>)}</ul></section> : null}
            <section className="linguistic-group" aria-labelledby={`cues-heading-${atom.id}`}>
              <h4 id={`cues-heading-${atom.id}`}>Language cues</h4>
              {robustCues.length ? <div className="linguistic-feature-list">{robustCues.map((cue) => <FeatureButton key={cue.id} feature={cue} label={plainLabel(cue.kind)} selected={cue.id === activeId} onSelect={setActiveFeature} />)}</div> : <p className="linguistic-missing">No explicit negation, modality, attribution, temporal, or numeric cues identified.</p>}
            </section>
            <details className="syntax-details">
              <summary>Technical parse{analysis.status === "partial" ? " · partial" : ""}</summary>
              {analysis.status === "partial" ? <p className="syntax-caption">This parser output is incomplete; extracted roles should not be treated as settled structure.</p> : null}
              <p className="linguistic-preview" aria-label="Atomic claim preview"><Preview text={atom.text} feature={activeFeature} /></p>
              <div className="linguistic-frames">
                {analysis.frames.length ? analysis.frames.map((frame, index) => <section key={frame.id} aria-label={`Parser frame ${index + 1}`}>
                  <h4>Parser frame {analysis.frames.length > 1 ? index + 1 : ""}</h4>
                  <dl>
                    <div><dt>Subject</dt><dd><SpanList items={frame.subjects} label="Subject" activeId={activeId} onSelect={setActiveFeature} /></dd></div>
                    <div><dt>Predicate</dt><dd><SpanList items={frame.predicate ? [frame.predicate] : []} label="Predicate" activeId={activeId} onSelect={setActiveFeature} /></dd></div>
                    <div><dt>Objects and complements</dt><dd>{argumentsView(frame.coreArguments)}</dd></div>
                    <div><dt>Modifiers</dt><dd>{modifiersView(frame.adjuncts, frame.otherModifiers)}</dd></div>
                  </dl>
                </section>) : <p className="linguistic-missing">No parser frame was resolved.</p>}
              </div>
              <section className="linguistic-group"><h4>Named entities</h4>{featureButtons(analysis.entities.map((feature) => ({ feature, label: feature.label })))}</section>
              <div className="syntax-table-wrap" tabIndex={0}><table><thead><tr><th>Token</th><th>Lemma</th><th>POS</th><th>Dependency</th><th>Head</th></tr></thead><tbody>{analysis.tokens.map((token) => <tr key={token.id}><td><button type="button" className="syntax-token-button" aria-pressed={token.id === activeId} onClick={() => setActiveFeature(token)}>{token.text}</button></td><td>{token.lemma}</td><td>{token.pos}{token.tag ? ` · ${token.tag}` : ""}</td><td>{token.dependency}</td><td>{token.head || "—"}</td></tr>)}</tbody></table></div>
            </details>
          </> : <p className="linguistic-state">Claim structure appears after decomposition.</p>}
      </div>}
    </aside>
  );
}
