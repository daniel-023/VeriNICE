# AAAI-27 live demonstration runbook

## Station layout

- Conference monitor: VeriTrace at 125–150% browser zoom.
- Presenter laptop: power connected, sleep disabled, notifications and automatic
  updates disabled.
- Poster board: one pipeline diagram, one QR code to recorded walkthrough, and
  one sentence explaining that linguistic analysis is verdict-neutral.
- Keep the laptop's local recording available even if conference Wi-Fi works.

## Before the session

1. Run `./run-verigraph --check`.
2. Start Ollama and run `./run-verigraph --start`.
3. Complete one curated live case; confirm all five stages and exact-source
   links.
4. Open `/walkthrough` in a second tab and disconnect Wi-Fi to confirm backup.
5. Keep the video file and paper PDF locally, not only in cloud storage.

## Three-minute audience path

1. Ask the visitor to choose Science, History, Geography, Technology, or Current Affairs.
2. Run or load the case and open one obligation.
3. Follow its best evidence span into the full source.
4. Follow the same atomic claim into the reasoning graph.
5. Open the deterministic rule trace and ask whether the visitor agrees.

The audience question is the point: “Which step would you challenge?”

## Suggested showcase paths

| Case | Primary demonstration | Presenter note |
| --- | --- | --- |
| `showcase-history-einstein` | Attribute comparison | Contrast the awarded prize with its grounded citation. |
| `showcase-history-curie` | Distinct-value counting | Combine two sources and inspect the counted scientific fields. |
| `showcase-geography-canberra` | Extremum counterexample | Show why one larger aligned value can refute a superlative. |
| `showcase-geography-everest` | Conservative abstention | Compare incompatible definitions without forcing a result. |
| `showcase-current-nato` | Temporal ordering | Execute a before/after comparison over two accession dates. |
| `showcase-current-unsc` | Exhaustive-list membership | Use absence only when the source explicitly supplies the complete list. |
| `averitec-dev-0392` | Jurisdiction filtering | Show that explicit mismatches stay visible but cannot affect the verdict. |

The NDF case is retained in the local 32-case bundle but excluded from the
hosted showcase. Its transformed UK financial-sanctions list does not cleanly
match the claim's terrorist-group designation measure, so its current symbolic
result is not strong enough for a flagship demonstration.

## Five-minute research path

Add the decomposition audit and compare a misleading dense match against an
exact lexical anchor. Explain the conservative neutral fallback. Keep model
architecture details for questions.

## Failure branches

| Failure | Immediate move | What to say |
| --- | --- | --- |
| Wi-Fi unavailable | Stay on local live mode | “The demonstration is fully local.” |
| Ollama/model failure | Switch to `/walkthrough` | “This is a recorded run of the same typed pipeline.” |
| Backend failure | Use static walkthrough, then restart after visitor leaves | “The fallback preserves every inspectable intermediate.” |
| One stage times out | Show its independent retry, or switch cases | “Stages fail independently so completed evidence is not hidden.” |
| Projector unreadable | Increase browser zoom; use source/graph tabs only | “We can follow one obligation without viewing the whole dashboard.” |

Never debug in front of a visitor for more than 15 seconds. Switch to the
walkthrough and preserve the conversation.

## Submission rehearsal gates

- Three consecutive cold-start demos without a manual fix.
- Three consecutive offline walkthrough demos.
- A new participant can correct one relation and explain the status trace after one viewing.
- Every factual claim in the paper appears in a test, recorded artifact, or
  cited source.
- Describe the 18 hosted runs as a qualitative showcase, not an accuracy
  sample. Keep full-set audit results separate from the demo narrative.
