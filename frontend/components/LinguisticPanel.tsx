"use client";

import { useState } from "react";
import type {
  AtomLinguisticAnalysis,
  DecomposedAtom,
  LinguisticArgument,
  LinguisticModifier,
  LinguisticSpan,
  StageState,
} from "@/lib/types";

function plainLabel(value: string): string {
  const text = value.replaceAll("_", " ");
  return `${text.charAt(0).toUpperCase()}${text.slice(1)}`;
}

function Preview({ text, feature }: { text: string; feature: LinguisticSpan | null }) {
  if (!feature || feature.start < 0 || feature.end <= feature.start || feature.end > text.length) {
    return <>{text}</>;
  }
  return (
    <>
      {text.slice(0, feature.start)}
      <mark>{text.slice(feature.start, feature.end)}</mark>
      {text.slice(feature.end)}
    </>
  );
}

function FeatureButton({
  feature,
  activeId,
  label,
  onSelect,
}: {
  feature: LinguisticSpan;
  activeId: string | null;
  label: string;
  onSelect: (feature: LinguisticSpan) => void;
}) {
  return (
    <button
      type="button"
      className="linguistic-feature"
      aria-pressed={activeId === feature.id}
      aria-label={`${label}: ${feature.text}`}
      onClick={() => onSelect(feature)}
    >
      <span>{feature.text}</span>
      <small>{label}</small>
    </button>
  );
}

function SpanList({
  items,
  activeId,
  label,
  onSelect,
}: {
  items: LinguisticSpan[];
  activeId: string | null;
  label: string;
  onSelect: (feature: LinguisticSpan) => void;
}) {
  if (!items.length) return <span className="linguistic-missing">Not explicitly identified</span>;
  return (
    <span className="linguistic-feature-list">
      {items.map((item) => (
        <FeatureButton
          key={item.id}
          feature={item}
          activeId={activeId}
          label={label}
          onSelect={onSelect}
        />
      ))}
    </span>
  );
}

function stateLabel(state: StageState, partial: boolean): string {
  if (state === "running") return "Analyzing";
  if (state === "error") return "Unavailable";
  if (state === "complete") return partial ? "Partial" : "Ready";
  return "Waiting";
}

export function LinguisticPanel({
  atom,
  analysis,
  state,
  error,
  onRetry,
}: {
  atom: DecomposedAtom;
  analysis: AtomLinguisticAnalysis | null;
  state: StageState;
  error: string | null;
  onRetry: () => void;
}) {
  const [activeFeature, setActiveFeature] = useState<LinguisticSpan | null>(null);

  const featureButtons = (
    items: Array<{ feature: LinguisticSpan; label: string }>,
  ) => {
    if (!items.length) {
      return <span className="linguistic-missing">Not explicitly identified</span>;
    }
    return (
      <span className="linguistic-feature-list">
        {items.map(({ feature, label }) => (
          <FeatureButton
            key={feature.id}
            feature={feature}
            activeId={activeFeature?.id ?? null}
            label={label}
            onSelect={setActiveFeature}
          />
        ))}
      </span>
    );
  };

  const argumentButtons = (items: LinguisticArgument[]) =>
    featureButtons(items.map((feature) => ({ feature, label: plainLabel(feature.role) })));
  const modifierButtons = (
    adjuncts: LinguisticModifier[],
    otherModifiers: LinguisticSpan[],
  ) =>
    featureButtons([
      ...adjuncts.map((feature) => ({ feature, label: plainLabel(feature.kind) })),
      ...otherModifiers.map((feature) => ({ feature, label: "Other modifier" })),
    ]);

  return (
    <aside className="linguistic-panel" aria-labelledby={`linguistic-heading-${atom.id}`}>
      <div className="linguistic-heading">
        <h3 id={`linguistic-heading-${atom.id}`}>Linguistic Structure</h3>
        <span aria-live="polite">{stateLabel(state, analysis?.status === "partial")}</span>
      </div>
      <p className="linguistic-note">
        Language cues describe the atom; they do not determine whether it is true or supported.
      </p>
      <p className="linguistic-preview" aria-label="Atomic claim preview">
        <Preview text={atom.text} feature={activeFeature} />
      </p>

      {state === "running" ? (
        <p className="linguistic-state" aria-live="polite">Analyzing language…</p>
      ) : state === "error" ? (
        <div className="linguistic-error" role="status">
          <p>{error ?? "Linguistic analysis is unavailable."}</p>
          <button type="button" onClick={onRetry}>Retry Linguistics</button>
        </div>
      ) : analysis ? (
        <>
          <div className="linguistic-frames">
            {analysis.frames.length ? analysis.frames.map((frame, index) => (
              <section key={frame.id} aria-label={`Proposition ${index + 1}`}>
                <h4>Proposition {analysis.frames.length > 1 ? index + 1 : "frame"}</h4>
                <dl>
                  <div>
                    <dt>Subject</dt>
                    <dd><SpanList items={frame.subjects} activeId={activeFeature?.id ?? null} label="Subject" onSelect={setActiveFeature} /></dd>
                  </div>
                  <div>
                    <dt>Predicate</dt>
                    <dd><SpanList items={frame.predicate ? [frame.predicate] : []} activeId={activeFeature?.id ?? null} label="Predicate" onSelect={setActiveFeature} /></dd>
                  </div>
                  <div>
                    <dt>Core arguments</dt>
                    <dd>{argumentButtons(frame.coreArguments)}</dd>
                  </div>
                  <div>
                    <dt>Modifiers</dt>
                    <dd>{modifierButtons(frame.adjuncts, frame.otherModifiers)}</dd>
                  </div>
                </dl>
              </section>
            )) : (
              <section aria-label="Partial proposition">
                <h4>Proposition frame</h4>
                <dl>
                  <div><dt>Subject</dt><dd className="linguistic-missing">Not explicitly identified</dd></div>
                  <div><dt>Predicate</dt><dd className="linguistic-missing">Not explicitly identified</dd></div>
                  <div><dt>Core arguments</dt><dd className="linguistic-missing">Not explicitly identified</dd></div>
                  <div><dt>Modifiers</dt><dd className="linguistic-missing">Not explicitly identified</dd></div>
                </dl>
              </section>
            )}
          </div>

          <section className="linguistic-group" aria-labelledby={`cues-heading-${atom.id}`}>
            <h4 id={`cues-heading-${atom.id}`}>Verification-relevant cues</h4>
            {analysis.cues.length ? (
              <div className="linguistic-feature-list">
                {analysis.cues.map((cue) => (
                  <FeatureButton key={cue.id} feature={cue} activeId={activeFeature?.id ?? null} label={cue.kind} onSelect={setActiveFeature} />
                ))}
              </div>
            ) : <p className="linguistic-missing">No explicit cues identified</p>}
          </section>

          <section className="linguistic-group" aria-labelledby={`entities-heading-${atom.id}`}>
            <h4 id={`entities-heading-${atom.id}`}>Named entities</h4>
            {analysis.entities.length ? (
              <div className="linguistic-feature-list">
                {analysis.entities.map((entity) => (
                  <FeatureButton key={entity.id} feature={entity} activeId={activeFeature?.id ?? null} label={entity.label} onSelect={setActiveFeature} />
                ))}
              </div>
            ) : <p className="linguistic-missing">No named entities identified</p>}
          </section>

          <details className="syntax-details">
            <summary>Syntax Details</summary>
            <div className="syntax-table-wrap">
              <table>
                <thead><tr><th>Token</th><th>Lemma</th><th>POS</th><th>Dependency</th><th>Head</th></tr></thead>
                <tbody>
                  {analysis.tokens.map((token) => (
                    <tr key={token.id}>
                      <td>{token.text}</td><td>{token.lemma}</td><td>{token.pos}{token.tag ? ` · ${token.tag}` : ""}</td><td>{token.dependency}</td><td>{token.head || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      ) : (
        <p className="linguistic-state">Analysis will appear when decomposition completes.</p>
      )}
    </aside>
  );
}
