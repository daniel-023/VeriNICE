# AAAI-27 live demonstration runbook

## Station layout

- Conference monitor: VeriGraph at 125–150% browser zoom.
- Presenter laptop: power connected, sleep disabled, notifications and automatic
  updates disabled.
- Poster board: one pipeline diagram, one QR code to recorded walkthrough, and
  one sentence explaining that linguistic analysis is verdict-neutral.
- Keep the laptop's local recording available even if conference Wi-Fi works.

## Before the session

1. Run `./run-verigraph --check`.
2. Start Ollama and run `./run-verigraph --start`.
3. Complete one featured live case; confirm all five stages and exact-source
   links.
4. Open `/walkthrough` in a second tab and disconnect Wi-Fi to confirm backup.
5. Keep the video file and paper PDF locally, not only in cloud storage.

## Three-minute audience path

1. Ask the visitor to choose a topic or challenge.
2. Run or load the case and open one obligation.
3. Follow its best evidence span into the full source.
4. Follow the same obligation into the argument graph.
5. Open the deterministic rule trace and ask whether the visitor agrees.

The audience question is the point: “Which step would you challenge?”

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
- The 32-case claim appears only after the manifest and evaluation report both
  contain 32 complete runs.
