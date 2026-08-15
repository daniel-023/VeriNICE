import { Braces } from "lucide-react";
import type { ReactNode } from "react";
import type { DecomposedAtom, StageState } from "@/lib/types";

export function AtomRail({
  atoms,
  state,
  selectedAtomId,
  onSelect,
  selectedDetail,
}: {
  atoms: DecomposedAtom[];
  state: StageState;
  selectedAtomId: string | null;
  onSelect: (atom: DecomposedAtom) => void;
  selectedDetail?: ReactNode;
}) {
  return (
    <section className="atom-rail" aria-labelledby="atoms-heading">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Claim Decomposition</p>
          <h2 id="atoms-heading">Atomic Claims</h2>
        </div>
        <span className="count-pill" aria-label={`${atoms.length} atomic claims`}>
          {atoms.length}
        </span>
      </div>

      {atoms.length ? (
        <ol className="atom-list">
          {atoms.map((atom, index) => (
            <li key={atom.id} className="atom-list-item">
              <button
                type="button"
                className="atom-card"
                aria-current={selectedAtomId === atom.id ? "true" : undefined}
                onClick={() => onSelect(atom)}
              >
                <span className="atom-index" aria-hidden="true">
                  A{index + 1}
                </span>
                <span className="atom-copy">
                  <span className="atom-text">{atom.text}</span>
                  <span className="atom-source">
                    Select to inspect language, candidate evidence, and sentence relations.
                  </span>
                </span>
              </button>
              {selectedAtomId === atom.id ? selectedDetail : null}
            </li>
          ))}
        </ol>
      ) : (
        <div className="panel-empty">
          <Braces size={22} aria-hidden="true" />
          <strong>
            {state === "running" ? "Decomposing claim…" : "No atoms yet"}
          </strong>
          <p>Choose a sample or enter your own text, then decompose the claim.</p>
        </div>
      )}
    </section>
  );
}
