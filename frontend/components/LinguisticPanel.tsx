"use client";

import { useState, type KeyboardEvent } from "react";
import type {
  AtomLinguisticAnalysis,
  DecomposedAtom,
  LinguisticArgument,
  LinguisticModifier,
  LinguisticSpan,
  ObligationLinguisticSummary,
  StageState,
} from "@/lib/types";

function plainLabel(value: string): string {
  const text = value.replaceAll("_", " ");
  return `${text.charAt(0).toUpperCase()}${text.slice(1)}`;
}

const warningLabels: Record<string, string> = {
  ROLE_CUE_MISMATCH: "The obligation type does not match the language cues found in the text.",
  MULTIPLE_PROPOSITION_FRAMES: "This obligation still contains more than one proposition.",
  UNRESOLVED_SUBJECT: "No subject could be resolved.",
  UNRESOLVED_PREDICATE: "No predicate could be resolved.",
  PARTIAL_LINGUISTIC_ANALYSIS: "Only part of this obligation could be analysed.",
  NEGATION_SCOPE_UNCLEAR: "The scope of negation is unclear.",
  ATTRIBUTION_SCOPE_UNCLEAR: "The reporting and embedded proposition scopes are unclear.",
  QUALIFIER_ATTACHMENT_UNCLEAR: "A qualifier may attach to the wrong predicate.",
};

const roleLabels: Record<string, string> = {
  CORE: "Core fact",
  NUMERIC_CONSTRAINT: "Numeric constraint",
  TEMPORAL_CONSTRAINT: "Temporal constraint",
  ATTRIBUTION: "Attribution",
  LOCATION_CONSTRAINT: "Location constraint",
  CAUSAL_RELATION: "Causal relation",
  CONDITIONAL: "Conditional",
  MODALITY_CONSTRAINT: "Modality constraint",
};

const dependencyLabels: Record<string, string> = {
  advcl: "Adverbial clause",
  advmod: "Adverbial modifier",
  agent: "Passive agent",
  attr: "Subject complement",
  aux: "Auxiliary",
  ccomp: "Clausal complement",
  conj: "Coordination",
  det: "Determiner",
  dobj: "Direct object",
  iobj: "Indirect object",
  mark: "Clause marker",
  neg: "Negation",
  nsubj: "Subject",
  nsubjpass: "Passive subject",
  obj: "Direct object",
  obl: "Oblique modifier",
  pobj: "Prepositional object",
  prep: "Preposition",
  punct: "Punctuation",
  root: "Root",
  xcomp: "Open clausal complement",
};

const posLabels: Record<string, string> = {
  ADJ: "Adjective",
  ADV: "Adverb",
  AUX: "Auxiliary",
  CCONJ: "Coordinating conjunction",
  DET: "Determiner",
  NOUN: "Noun",
  NUM: "Number",
  PART: "Particle",
  PRON: "Pronoun",
  PROPN: "Proper noun",
  VERB: "Verb",
};

function dependencyLabel(value: string): string {
  return dependencyLabels[value.toLowerCase()] ?? plainLabel(value);
}

function posLabel(value: string): string {
  return posLabels[value] ?? plainLabel(value);
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
  summary,
  state,
  error,
  onRetry,
}: {
  atom: DecomposedAtom;
  analysis: AtomLinguisticAnalysis | null;
  summary: ObligationLinguisticSummary | null;
  state: StageState;
  error: string | null;
  onRetry: () => void;
}) {
  const [activeFeature, setActiveFeature] = useState<LinguisticSpan | null>(null);
  const [syntaxView, setSyntaxView] = useState<"readable" | "raw">("readable");
  const syntaxPanelId = `syntax-panel-${atom.id}`;
  const syntaxTabId = (view: "readable" | "raw") => `syntax-tab-${view}-${atom.id}`;

  const handleSyntaxTabKey = (
    event: KeyboardEvent<HTMLButtonElement>,
    view: "readable" | "raw",
  ) => {
    let next: "readable" | "raw" | null = null;
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      next = view === "readable" ? "raw" : "readable";
    } else if (event.key === "Home") {
      next = "readable";
    } else if (event.key === "End") {
      next = "raw";
    }
    if (!next) return;
    event.preventDefault();
    setSyntaxView(next);
    document.getElementById(syntaxTabId(next))?.focus();
  };

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

      {summary ? (
        <section className="linguistic-group" aria-label="Obligation audit">
          <h4>Obligation audit</h4>
          <dl className="linguistic-audit">
            <div><dt>Proposed role</dt><dd>{plainLabel(atom.role)}</dd></div>
            <div><dt>spaCy audit</dt><dd>{plainLabel(summary.roleAudit)}</dd></div>
          </dl>
          {summary.warnings.length ? (
            <ul className="linguistic-warnings">
              {summary.warnings.map((warning) => (
                <li key={warning}>{warningLabels[warning] ?? plainLabel(warning)}</li>
              ))}
            </ul>
          ) : <p className="linguistic-missing">No audit warnings</p>}
        </section>
      ) : null}

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
            {analysis.frames.length > 1 ? (
              <p className="linguistic-frame-note">
                Related clauses have separate frames; a clausal complement may also appear as a core argument.
              </p>
            ) : null}
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
            <p className="syntax-caption">
              Technical view of how the parser identifies words, roles, and relationships.
            </p>
            <div className="syntax-legend" role="note">
              <strong>Linguistic terms:</strong> lemma = base word · POS/tag = word type · dependency = grammatical relationship · head = related word
            </div>
            <div className="syntax-tabs" role="tablist" aria-label="Syntax table view">
              <button
                type="button"
                role="tab"
                id={syntaxTabId("readable")}
                aria-controls={syntaxPanelId}
                aria-selected={syntaxView === "readable"}
                tabIndex={syntaxView === "readable" ? 0 : -1}
                className={syntaxView === "readable" ? "syntax-tab active" : "syntax-tab"}
                onClick={() => setSyntaxView("readable")}
                onKeyDown={(event) => handleSyntaxTabKey(event, "readable")}
              >
                Readable syntax
              </button>
              <button
                type="button"
                role="tab"
                id={syntaxTabId("raw")}
                aria-controls={syntaxPanelId}
                aria-selected={syntaxView === "raw"}
                tabIndex={syntaxView === "raw" ? 0 : -1}
                className={syntaxView === "raw" ? "syntax-tab active" : "syntax-tab"}
                onClick={() => setSyntaxView("raw")}
                onKeyDown={(event) => handleSyntaxTabKey(event, "raw")}
              >
                Raw details
              </button>
            </div>
            <div
              className="syntax-table-wrap"
              id={syntaxPanelId}
              role="tabpanel"
              aria-labelledby={syntaxTabId(syntaxView)}
              tabIndex={0}
            >
              <table>
                <thead>
                  {syntaxView === "readable" ? (
                    <tr><th>Token</th><th>Role / dependency</th><th>Head</th><th>POS / tag</th><th>Lemma</th></tr>
                  ) : (
                    <tr><th>Token</th><th>Lemma</th><th>POS</th><th>Dependency</th><th>Head</th><th>Offsets</th></tr>
                  )}
                </thead>
                <tbody>
                  {analysis.tokens.map((token) => (
                    <tr key={token.id}>
                      <td>
                        <button
                          type="button"
                          className="syntax-token-button"
                          aria-pressed={activeFeature?.id === token.id}
                          aria-label={`Token: ${token.text}`}
                          onClick={() => setActiveFeature(token)}
                        >
                          {token.text}
                        </button>
                      </td>
                      {syntaxView === "readable" ? (
                        <>
                          <td>{dependencyLabel(token.dependency)} <span className="syntax-raw">· {token.dependency}</span></td>
                          <td>{token.head || "—"}</td>
                          <td>{posLabel(token.pos)} <span className="syntax-raw">· {token.pos}{token.tag ? `/${token.tag}` : ""}</span></td>
                          <td>{token.lemma}</td>
                        </>
                      ) : (
                        <>
                          <td>{token.lemma}</td>
                          <td>{token.pos}{token.tag ? ` · ${token.tag}` : ""}</td>
                          <td>{token.dependency}</td>
                          <td>{token.head || "—"}</td>
                          <td>{token.start}–{token.end}</td>
                        </>
                      )}
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
