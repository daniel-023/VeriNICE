# VeriNICE demonstration video — 4:35 target

Keep the cursor movements slow and the narration conversational. Record at
1080p with interface zoomed so evidence spans are readable.

## 0:00–0:45 — the whole idea

“A fact-checking label tells us almost nothing about how the system reached its
answer. VeriNICE lets us inspect that path. It breaks a claim into atomic claims,
finds the passages most relevant to each one, distinguishes support from
refutation, and then shows the exact rule behind the verdict. The
language model proposes structure; it never gets the last word.”

Show one curated case, the five-stage rail, and the completed graph. Do not
explain model names yet.

## 0:45–1:25 — choose a useful sample

Choose a category, then select either a source-grounded example or an AVeriTeC
case. Point out the origin badge and that the reference label is metadata, not
an input to the pipeline.

## 1:25–2:15 — structure and retrieval

Run the selected case. Show the typed obligations and exact source grounding.
Open one obligation and trace its candidate evidence back into the full source.
Explain hybrid retrieval in one sentence: semantic similarity finds paraphrases;
lexical anchors protect exact numbers and names.

## 2:15–3:05 — support, conflict, and abstention

Show one supporting or refuting relation. Explain that Qwen can select only
retrieved sentence IDs, that insufficient selections remain provisional, and
that every decisive relation has a visible source anchor. Open the graph and
follow one atomic claim to its evidence.

## 3:05–4:05 — review a relation and inspect the rule

Open a symbolic result and point to its two steps: “The model selects from
server-issued rule/profile candidates and grounded inputs. Python validates the
profile preconditions and executes the rule.” Select a
premise to jump to the exact source span. Then change one evidence relation and
show the graph and verdict recompute from the visible atomic-claim states. The
verdict is not another model response.

## 4:05–4:35 — close

“VeriNICE is useful precisely when the pipeline is imperfect: it gives a
researcher or practitioner somewhere concrete to look, disagree, and improve.
At the live demonstration, visitors can choose a topic, inspect a recorded case,
or supply a claim and documents to run locally.”

End on the reasoning graph and project URL/QR code. Do not show an accuracy
number unless the final, expanded evaluation has been completed.
