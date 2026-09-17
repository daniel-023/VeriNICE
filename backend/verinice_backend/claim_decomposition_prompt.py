"""Prompt used by the claim decomposition model.

Keeping this text separate from transport and validation makes prompt changes
reviewable without mixing them with runtime control flow.
"""

DECOMPOSITION_INSTRUCTIONS = """Decompose one claim into standalone verification
obligations. Cover every independently verifiable proposition asserted by the
claim and add nothing. Completeness comes first; among equally complete answers,
prefer fewer obligations.

Each obligation must be one proposition whose truth can vary independently.
Preserve polarity, attribution, modality, quantities, dates, locations,
comparisons, conditions, and causal scope. Do not split a modifier from the
proposition it qualifies. In particular, keep an attributed causal quantity
together: "The inquiry said a wiring fault caused 10 outages" is one obligation,
not a count plus a cause of unspecified deaths. Never include a broad obligation
and a narrower duplicate.

Assertions inside introductory, relative, or subordinate clauses still count.
Split them when they state independently checkable events or values. Do not
split a comparison, range, or one event merely because it contains several
numbers, dates, locations, or adjectives. Comparisons must retain both sides
and their direction in one obligation.

Every obligation's text must be understandable by itself. Replace pronouns and
cross-obligation references such as he, she, his, her, it, its, these, those,
former, or latter with their explicit antecedents when the claim supplies one.
If sourceText begins after the antecedent, leaving its pronoun in text is
invalid. Restore an omitted subject or possessive determiner only when needed
to make reconstructed text grammatical. Do not invent an antecedent that the
claim omits.

sourceText is a locator, not the reconstructed proposition. Copy it exactly
from one contiguous claim span and prefer the shortest span that uniquely
locates the assertion. When propositions share a subject, verb, modal, or
condition, sourceText may quote only the distinguishing fragment while text
reconstructs the complete proposition. Never create obligations for evidence,
entities, isolated dates, numbers, or tokens.

Choose the role for the main verification challenge. ATTRIBUTION means that a
speaker or source said, reported, or alleged something; it does not mean
"awarded to." CAUSAL_RELATION requires claimed causation such as caused, made,
or led to; association or correlation alone is CORE. NUMERIC_CONSTRAINT covers
counts, thresholds, rates, and percentages. TEMPORAL_CONSTRAINT covers dates,
periods, and ordering. Use the other specific roles when applicable and CORE as
the fallback. A role never creates another obligation.

Every sentence asserting a proposition contributes at least one obligation.
Do not collapse a multi-sentence claim into one whole-claim obligation. Use AND
when every obligation must hold, OR when any one is sufficient, and SINGLE only
when exactly one proposition is asserted. Composition is flat.

Examples:
Claim: The curator reported the manuscript was authentic.
JSON: {"composition":"SINGLE","obligations":[{"text":"The curator reported the manuscript was authentic.","sourceText":"The curator reported the manuscript was authentic","role":"ATTRIBUTION"}]}
Claim: An inquiry concluded a faulty valve caused 37 litres of coolant to leak.
JSON: {"composition":"SINGLE","obligations":[{"text":"An inquiry concluded a faulty valve caused 37 litres of coolant to leak.","sourceText":"An inquiry concluded a faulty valve caused 37 litres of coolant to leak","role":"CAUSAL_RELATION"}]}
Claim: After a sensor detected 14 signals, the observatory confirmed 9 candidates.
JSON: {"composition":"AND","obligations":[{"text":"The sensor detected 14 signals.","sourceText":"a sensor detected 14 signals","role":"NUMERIC_CONSTRAINT"},{"text":"The observatory confirmed 9 candidates after the sensor detection.","sourceText":"the observatory confirmed 9 candidates","role":"NUMERIC_CONSTRAINT"}]}
Claim: Mina catalogued the Aurora archive in 2016 and digitized its index in 2018.
JSON: {"composition":"AND","obligations":[{"text":"Mina catalogued the Aurora archive in 2016.","sourceText":"Mina catalogued the Aurora archive in 2016","role":"TEMPORAL_CONSTRAINT"},{"text":"Mina digitized the Aurora archive's index in 2018.","sourceText":"digitized its index in 2018","role":"TEMPORAL_CONSTRAINT"}]}
Claim: The board appointed Leila and praised her fieldwork.
JSON: {"composition":"AND","obligations":[{"text":"The board appointed Leila.","sourceText":"The board appointed Leila","role":"CORE"},{"text":"The board praised Leila's fieldwork.","sourceText":"praised her fieldwork","role":"CORE"}]}
Claim: The reservoir level in June was lower than the level in May.
JSON: {"composition":"SINGLE","obligations":[{"text":"The reservoir level in June was lower than the reservoir level in May.","sourceText":"The reservoir level in June was lower than the level in May","role":"TEMPORAL_CONSTRAINT"}]}
Claim: The indicator shifted from violet through amber to grey.
JSON: {"composition":"SINGLE","obligations":[{"text":"The indicator shifted from violet through amber to grey.","sourceText":"The indicator shifted from violet through amber to grey","role":"CORE"}]}
Claim: If funding passes, the council will repair the pier and reopen the museum.
JSON: {"composition":"AND","obligations":[{"text":"If funding passes, the council will repair the pier.","sourceText":"repair the pier","role":"CONDITIONAL"},{"text":"If funding passes, the council will reopen the museum.","sourceText":"reopen the museum","role":"CONDITIONAL"}]}
Claim: The parcel is stored in Dock 4 or Warehouse 7.
JSON: {"composition":"OR","obligations":[{"text":"The parcel is stored in Dock 4.","sourceText":"Dock 4","role":"LOCATION_CONSTRAINT"},{"text":"The parcel is stored in Warehouse 7.","sourceText":"Warehouse 7","role":"LOCATION_CONSTRAINT"}]}

Return only JSON conforming to the supplied schema."""
