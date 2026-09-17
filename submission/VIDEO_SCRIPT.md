# VeriNICE demonstration video script

## Opening

**On screen:** Open VeriNICE and briefly show the five-stage pipeline.

**Narration:**

> This video presents VeriNICE, an inspectable neurosymbolic fact-verification
> system. Fact-checking is rarely as simple as matching one claim to one
> sentence. A claim may contain several facts, draw on multiple passages, or
> require comparisons between dates, quantities, or attributes. VeriNICE shows
> how a claim is decomposed, how source evidence is assessed, when symbolic
> reasoning is applied, and how these results produce a four-way verdict.

## Example walkthrough

**On screen:** In **History**, select **Einstein's Nobel Prize citation** and
show the supplied source documents.

**Narration:**

> Let's review this claim: “The Nobel Prize in Physics for 1921 was awarded to
> Albert Einstein, and the prize was awarded for his theory of relativity.”
> VeriNICE evaluates it only against the supplied source documents, rather than
> searching the open web.

### Claim decomposition

**On screen:** Open **01 Decompose** and select each atomic claim.

**Narration:**

> First, a language model separates the statement into verifiable atomic claims:
> that Einstein received the 1921 Physics prize, and that it was awarded for his
> theory of relativity.
>
> VeriNICE also records whether the atoms form a single statement, an `AND`, or
> an `OR`. Each atom remains linked to the original wording, and the backend
> validates the structure before continuing.

### Retrieval

**On screen:** Open **02 Retrieve**. Switch between the two atomic claims, then
select a retrieved sentence to reveal it in the document panel.

**Narration:**

> VeriNICE retrieves evidence separately for each atomic claim by combining
> semantic and keyword-based matching. Semantic matching finds paraphrases,
> while keyword matching preserves important names, dates, and numbers. Every
> result retains its exact source location and is highlighted in the document
> panel for inspection in context.
>
> In this case, both retrieval paths lead to official Nobel material, including
> the citation stating that Einstein received the 1921 Physics prize especially
> for his discovery of the law of the photoelectric effect.

### Evidence assessment

**On screen:** Open **03 Assess**. Point to the relation labels, sufficiency
state, and highlighted source sentences for each atomic claim.

**Narration:**

> The model can assess only retrieved sentence identifiers. Supporting evidence
> establishes the atom; refuting evidence contradicts it; neutral evidence is
> relevant but neither supports nor refutes it; and other candidates remain unused.
>
> It also judges the selected sentences together. A sufficient bundle resolves
> every relevant entity, relationship, time, quantity, comparison, and scope.
> Partial or insufficient bundles leave gaps. Their relations remain visible,
> but only a sufficient bundle can contribute directly to the verdict.
>
> In this run, the first bundle is marked partial and the second insufficient,
> so their relations remain provisional. But the source explicitly names the
> recipient, award, year, and motivation. These values match registered award
> profiles, making both atoms eligible for symbolic checks.

### Symbolic reasoning

**On screen:** Open **04 Reason**. Briefly show the rule-type list, then expand
the two `ATTRIBUTE_COMPARE` results and their source-linked premises.

**Narration:**

> VeriNICE provides six bounded types of symbolic reasoning: set membership,
> numeric comparison, temporal comparison, attribute comparison, distinct-value
> counting, and largest-or-smallest comparison.
>
> The backend supplies eligible operators and source-linked premises. The model
> maps the premises to a rule, and Python validates and executes it. Missing or
> ambiguous operands produce an unresolved result rather than a guess.
>
> Here, VeriNICE compares attributes for each atom. The source names Albert
> Einstein as the recipient of the 1921 Nobel Prize in Physics. The recipient,
> award, and year align, so the first check returns `PROVED`.
>
> For the second, the claimed motivation is the theory of relativity, but the
> Nobel citation identifies the discovery of the law of the photoelectric
> effect. The motivations do not match, so the check returns `DISPROVED`.

### Verdict composition and reasoning graph

**On screen:** Open **05 Decide**, then show the reasoning graph. Highlight the
claim, atomic-claim, evidence, and inference nodes; follow the green and red
edges; finish on the rule trace and final verdict.

**Narration:**

> VeriNICE combines sufficient direct evidence with resolved symbolic results
> for each atom. Support alone means `SUPPORTED`; refutation alone means
> `REFUTED`; both mean `CONFLICTING_EVIDENCE`; and neither means
> `NOT_ENOUGH_EVIDENCE`.
>
> Atomic outcomes are then composed according to the claim structure. An `AND`
> needs every atom to be supported and is refuted if any is refuted. An `OR` is
> supported if any atom is supported and refuted only if all are refuted.
> Remaining conflicts or gaps produce the corresponding outcome in the rule
> trace.
>
> The graph makes this inspectable. Claim, evidence, and inference nodes show
> where results came from. Green edges show support, red edges show refutation,
> and selecting a node returns to its highlighted source passage.
>
> Here, the first obligation is supported by a proved symbolic result, while the
> second is refuted by a disproved result. Because the original claim joins them
> with `AND`, the refuted obligation refutes the complete claim. VeriNICE
> therefore returns `REFUTED` as the final verdict.

## Conclusion

**On screen:** End on the completed reasoning graph and the VeriNICE title.

**Narration:**

> VeriNICE exposes the complete path from a claim and its supplied sources to
> evidence assessments, validated symbolic reasoning, and a four-way verdict.
> It does not replace human judgment, but makes source use, intermediate
> decisions, and verdict composition easier to inspect and understand.

## Recording notes

- Keep `PROVED` and `DISPROVED` distinct from the claim-level verdicts
  `SUPPORTED`, `REFUTED`, `CONFLICTING_EVIDENCE`, and
  `NOT_ENOUGH_EVIDENCE`.
- When describing the four-way output, keep the graph or rule trace visible so
  the explanation is tied to the interface rather than presented as a detached
  list.
- Do not imply that provisional relations affect the Einstein verdict. Its
  validated symbolic results are decisive.
