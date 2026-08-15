import { ExternalLink, FileText, Plus, Trash2 } from "lucide-react";
import { Fragment, KeyboardEvent, useEffect, useMemo, useRef } from "react";
import type {
  DemoDocument,
  EvidenceRelation,
  EvidenceSpan,
  NLIRelation,
  StageState,
} from "@/lib/types";

const RELATION_COPY: Record<NLIRelation, string> = {
  ENTAILMENT: "Supports atom",
  CONTRADICTION: "Contradicts atom",
  NEUTRAL: "Neither",
};

function validSpans(value: string, spans: EvidenceSpan[]): EvidenceSpan[] {
  const ordered = [...spans].sort((left, right) => left.start - right.start);
  let previousEnd = 0;
  return ordered.filter((span) => {
    const valid =
      span.start >= previousEnd &&
      span.end > span.start &&
      span.end <= value.length &&
      value.slice(span.start, span.end) === span.text;
    if (valid) previousEnd = span.end;
    return valid;
  });
}

export function DocumentPanel({
  documents,
  activeDocumentId,
  onActivate,
  onTextChange,
  onTitleChange,
  onAdd,
  onRemove,
  spans,
  relations,
  selectedAtomText,
  retrievalState,
  readOnly = false,
}: {
  documents: DemoDocument[];
  activeDocumentId: string;
  onActivate: (documentId: string) => void;
  onTextChange: (documentId: string, value: string) => void;
  onTitleChange: (documentId: string, value: string) => void;
  onAdd: () => void;
  onRemove: (documentId: string) => void;
  spans: EvidenceSpan[];
  relations: EvidenceRelation[];
  selectedAtomText: string | null;
  retrievalState: StageState;
  readOnly?: boolean;
}) {
  const activeDocument =
    documents.find((document) => document.id === activeDocumentId) ?? documents[0];
  const value = activeDocument?.text ?? "";
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const mirrorRef = useRef<HTMLDivElement>(null);
  const highlightRefs = useRef(new Map<string, HTMLElement>());
  const pendingSpanRef = useRef<string | null>(null);
  const tabRefs = useRef(new Map<string, HTMLButtonElement>());
  const activeSpans = useMemo(
    () => spans.filter((span) => span.documentId === activeDocument?.id),
    [activeDocument?.id, spans],
  );
  const highlights = useMemo(() => validSpans(value, activeSpans), [activeSpans, value]);
  const evidenceCountByDocument = useMemo(() => {
    const counts = new Map<string, number>();
    spans.forEach((span) => counts.set(span.documentId, (counts.get(span.documentId) ?? 0) + 1));
    return counts;
  }, [spans]);
  const titlesByDocument = useMemo(
    () => new Map(documents.map((document) => [document.id, document.title])),
    [documents],
  );
  const relationsBySpan = useMemo(
    () =>
      new Map(
        relations.map((item) => [
          `${item.documentId}:${item.spanId}`,
          item.relation,
        ]),
      ),
    [relations],
  );

  const mirrorContent = useMemo(() => {
    const parts = [];
    let cursor = 0;
    highlights.forEach((span) => {
      parts.push(
        <Fragment key={`${span.id}-before`}>{value.slice(cursor, span.start)}</Fragment>,
      );
      parts.push(
        <mark
          className="evidence-highlight"
          data-testid="evidence-highlight"
          key={`${span.id}-mark`}
          ref={(node) => {
            if (node) highlightRefs.current.set(span.id, node);
            else highlightRefs.current.delete(span.id);
          }}
        >
          {value.slice(span.start, span.end)}
        </mark>,
      );
      cursor = span.end;
    });
    parts.push(<Fragment key="document-tail">{value.slice(cursor)}</Fragment>);
    if (value.endsWith("\n")) parts.push(<Fragment key="final-space"> </Fragment>);
    return parts;
  }, [highlights, value]);

  const scrollToSpan = (spanId: string) => {
    pendingSpanRef.current = null;
    const textarea = textareaRef.current;
    const mirror = mirrorRef.current;
    const highlight = highlightRefs.current.get(spanId);
    if (!textarea || !mirror || !highlight) return;
    textarea.scrollTop = Math.max(0, highlight.offsetTop - textarea.clientHeight * 0.25);
    mirror.scrollTop = textarea.scrollTop;
  };

  // A jump into another source lands after that tab renders; within the active
  // source the pending target is consumed on the next frame like any other.
  useEffect(() => {
    if (!selectedAtomText || !highlights.length) return;
    const target = pendingSpanRef.current ?? highlights[0].id;
    const frame = requestAnimationFrame(() => scrollToSpan(target));
    return () => cancelAnimationFrame(frame);
  }, [activeDocument?.id, highlights, selectedAtomText]);

  const jumpToSpan = (span: EvidenceSpan) => {
    pendingSpanRef.current = span.id;
    if (span.documentId !== activeDocument?.id) {
      onActivate(span.documentId);
      return;
    }
    scrollToSpan(span.id);
  };

  const syncScroll = () => {
    const textarea = textareaRef.current;
    const mirror = mirrorRef.current;
    if (!textarea || !mirror) return;
    mirror.scrollTop = textarea.scrollTop;
    mirror.scrollLeft = textarea.scrollLeft;
  };

  const handleTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let nextIndex: number | null = null;
    if (event.key === "ArrowRight") nextIndex = (index + 1) % documents.length;
    if (event.key === "ArrowLeft") nextIndex = (index - 1 + documents.length) % documents.length;
    if (event.key === "Home") nextIndex = 0;
    if (event.key === "End") nextIndex = documents.length - 1;
    if (nextIndex === null) return;
    event.preventDefault();
    const next = documents[nextIndex];
    onActivate(next.id);
    tabRefs.current.get(next.id)?.focus();
  };

  const elsewhere = spans.length - activeSpans.length;
  const highlightCount = `${highlights.length} candidate evidence span${
    highlights.length === 1 ? "" : "s"
  } highlighted in this source`;
  const candidateStatus = !selectedAtomText
    ? "Select an atomic claim to show its candidate evidence."
    : retrievalState === "running"
      ? "Finding candidate evidence across the source documents."
      : retrievalState === "complete" && spans.length
        ? elsewhere
          ? `${highlightCount}, ${elsewhere} in other sources.`
          : `${highlightCount}.`
        : retrievalState === "complete"
          ? "No candidate evidence was selected for this atom."
          : retrievalState === "error"
            ? "Candidate evidence is unavailable until retrieval is retried."
            : "Candidate evidence has not been retrieved yet.";

  return (
    <section className="document-panel" aria-labelledby="document-heading">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Pipeline Input</p>
          <h2 id="document-heading">Evidence Sources</h2>
        </div>
        <FileText size={18} aria-hidden="true" />
      </div>

      <div className="source-tabs-row">
        <div className="source-tabs" role="tablist" aria-label="Evidence sources">
          {documents.map((document, index) => {
            const selected = document.id === activeDocument?.id;
            const evidenceCount = evidenceCountByDocument.get(document.id) ?? 0;
            return (
              <button
                type="button"
                role="tab"
                id={`source-tab-${document.id}`}
                aria-controls={`source-panel-${document.id}`}
                aria-selected={selected}
                tabIndex={selected ? 0 : -1}
                key={document.id}
                ref={(node) => {
                  if (node) tabRefs.current.set(document.id, node);
                  else tabRefs.current.delete(document.id);
                }}
                onClick={() => onActivate(document.id)}
                onKeyDown={(event) => handleTabKeyDown(event, index)}
              >
                <span>{document.title}</span>
                {evidenceCount ? <small aria-label={`${evidenceCount} evidence spans`}>{evidenceCount}</small> : null}
              </button>
            );
          })}
        </div>
        <button
          type="button"
          className="source-icon-button"
          aria-label="Add evidence source"
          onClick={onAdd}
          disabled={readOnly || documents.length >= 8}
        >
          <Plus size={15} aria-hidden="true" />
        </button>
      </div>

      {activeDocument ? (
        <div
          className="source-panel"
          role="tabpanel"
          id={`source-panel-${activeDocument.id}`}
          aria-labelledby={`source-tab-${activeDocument.id}`}
        >
          <div className="source-controls">
            <label>
              <span className="sr-only">Source title</span>
              <input
                name={`source-title-${activeDocument.id}`}
                autoComplete="off"
                value={activeDocument.title}
                maxLength={300}
                readOnly={readOnly}
                onChange={(event) => onTitleChange(activeDocument.id, event.target.value)}
                aria-label="Source title"
              />
            </label>
            {activeDocument.url.startsWith("http") ? (
              <a href={activeDocument.url} target="_blank" rel="noreferrer">
                View source <ExternalLink size={12} aria-hidden="true" />
              </a>
            ) : null}
            <button
              type="button"
              className="source-icon-button source-remove-button"
              aria-label={`Remove ${activeDocument.title}`}
              onClick={() => onRemove(activeDocument.id)}
              disabled={readOnly || documents.length === 1}
            >
              <Trash2 size={14} aria-hidden="true" />
            </button>
          </div>
          <p className="document-match-status" id="document-candidate-status" aria-live="polite">
            {candidateStatus}
          </p>
          {selectedAtomText && spans.length ? (
            <nav className="evidence-list-panel" aria-labelledby="evidence-list-heading">
              <h3 id="evidence-list-heading">Candidate evidence spans</h3>
              <ol className="evidence-list">
                {spans.map((span) => {
                  const relation = relationsBySpan.get(`${span.documentId}:${span.id}`);
                  return (
                    <li key={`${span.documentId}:${span.id}:${span.start}`}>
                      <button
                        type="button"
                        className="evidence-entry"
                        onClick={() => jumpToSpan(span)}
                      >
                        <span className="evidence-entry-source">
                          {titlesByDocument.get(span.documentId) ?? span.documentId}
                        </span>
                        <q className="evidence-entry-quote">{span.text}</q>
                        {relation ? (
                          <span
                            className={`evidence-relation relation-${relation.toLowerCase()}`}
                          >
                            {RELATION_COPY[relation]}
                          </span>
                        ) : null}
                      </button>
                    </li>
                  );
                })}
              </ol>
            </nav>
          ) : null}
          <label className="document-paper document-editor">
            <span className="sr-only">Evidence document: {activeDocument.title}</span>
            <div className="document-mirror" ref={mirrorRef} aria-hidden="true">
              <div className="document-mirror-content">{mirrorContent}</div>
            </div>
            <textarea
              ref={textareaRef}
              name="evidence-document"
              autoComplete="off"
              maxLength={250000}
              value={value}
              readOnly={readOnly}
              aria-describedby="document-candidate-status"
              onChange={(event) => onTextChange(activeDocument.id, event.target.value)}
              onScroll={syncScroll}
              placeholder="Paste the full evidence document…"
            />
          </label>
        </div>
      ) : null}
    </section>
  );
}
