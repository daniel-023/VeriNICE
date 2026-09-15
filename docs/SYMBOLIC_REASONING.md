# Symbolic reasoning

VeriNICE uses a bounded library of symbolic operators executed over validated,
source-linked premises. The library supplements direct evidence assessment; it
is neither a general theorem prover nor a complete taxonomy of fact-verification
reasoning.

This guide covers **Stage 04 · Apply symbolic rules** and the deterministic
composition performed in **Stage 05 · Compose verdict**.

## Execution flow

Each symbolic result follows the same sequence:

1. **Candidate generation.** The backend detects eligible operator profiles
   from the atomic claim and grounded evidence, and issues the permissible
   premise identifiers.
2. **Model mapping.** Qwen2.5 proposes mappings among those server-issued
   candidates and premises; it cannot invent a rule type or refer to an
   unissued premise.
3. **Validation.** Python checks source grounding, the registered profile,
   operand alignment, and operator-specific preconditions. For conservative
   attribute and distinct-count extractors, Python may also recover an omitted
   mapping, but only when the complete server-issued candidate independently
   yields a decisive result.
4. **Deterministic execution.** Python applies the typed comparison.
5. **Verdict composition.** Resolved support or refutation joins sufficient
   direct evidence at the atomic-claim level before the claim verdict is
   composed.

Invalid, missing, or ambiguous operands cause abstention rather than a guessed
comparison.

## Operators and eligibility

The interface groups executions under six rule types:

| Rule type | Interface description | Eligibility and abstention |
| --- | --- | --- |
| **Set membership** | Checks whether an item appears in a source list; absence counts only when the list is complete. | The item and list entries must be grounded in the selected premises. Presence can support membership. Absence can refute it only when the source explicitly licenses the list as complete; otherwise the result is unresolved. |
| **Numeric comparison** | Compares numbers when they refer to the same quantity, unit, entity, and time. | Values must have aligned measures, entities, time scopes, and supported units. Decimal values are compared without implicit unit conversion. Missing alignment or conflicting grounded values produces abstention. |
| **Temporal comparison** | Compares absolute dates or date ranges tied to the same event. | Dates or intervals must be absolute and attached to aligned events. Relative or ambiguous dates are unresolved. Event-order comparisons require a grounded date for each event. |
| **Attribute comparison** | Compares a claimed attribute with an explicitly stated source attribute using a supported pattern. | Both values must be explicit and a registered extraction profile must apply. Free-form semantic attributes outside those profiles are not inferred. |
| **Distinct-value count** | Counts distinct source values; an exact total requires a complete list. | Explicit values are aligned with the claim's subject, predicate, and named category, then deduplicated. A grounded collection can prove a lower bound. Exact-count claims currently remain unresolved; supporting one would additionally require a complete-value-set certificate. |
| **Largest/smallest comparison** | Finds a comparable counterexample that can refute a largest or smallest claim. | A counterexample must use the same measure, unit, entity class, and relevant scope. A valid larger or smaller comparator can refute an extremum claim. The absence of a counterexample does not prove the extremum, so the operator otherwise abstains. |

Small domain-neutral examples illustrate the boundaries:

- A complete roster that lists `North`, `South`, and `West` can refute the
  claim that `East` belongs to that roster. An unlabeled partial list cannot.
- A source value of 12 can refute a claim of “more than 15” only if both values
  refer to the same measure, unit, entity, and time.
- Two grounded dates can establish that event A occurred before event B;
  “recently” cannot be ordered without an absolute reference.
- Two distinct grounded colours prove “at least two colours,” but do not prove
  “exactly two colours” unless the source gives a complete enumeration.
- A 42-metre structure in the same comparison class refutes the claim that a
  40-metre structure is the tallest; it does not identify the true maximum.

## Reusable operators and extraction profiles

An **operator** is reusable calculation code such as membership, comparison,
counting, or extremum refutation. An **extraction profile** is a registered,
bounded way to recognize eligible language and obtain the operands that an
operator requires. Separating them prevents a successful calculation in one
domain from being presented as unrestricted semantic reasoning.

The current profiles are:

| Profile group | Registered profiles | Scope |
| --- | --- | --- |
| General | `GENERIC_SET_MEMBERSHIP`, `GENERIC_NUMERIC_THRESHOLD`, `GENERIC_ABSOLUTE_DATE`, `GENERIC_EVENT_ORDER`, `GENERIC_DISTINCT_VALUES`, `GENERIC_EXTREMUM_COUNTEREXAMPLE` | Recognize explicit lists, aligned numeric thresholds, absolute dates or event order, category-labelled distinct values, and comparable extremum counterexamples. |
| Bounded attribute patterns | `EXPLICIT_NEGATION`, `COUNTRY_LOCATION`, `EXCLUSIVE_PURPOSE` | Handle explicit negation and narrowly registered location or exclusivity wording. |
| Award patterns | `AWARD_RECIPIENT`, `AWARD_MOTIVATION` | Align explicitly named recipients, award years, and stated motivations without assuming a particular award programme. Award categories used in lower-bound counts are handled by `GENERIC_DISTINCT_VALUES`. |

Adding a new profile extends operand extraction and its validation tests; it
does not require changing the underlying typed operator when the calculation
is already supported.

## Result states

Every attempted symbolic execution records one of four states:

- `PROVED`: validated operands and the rule establish the atomic claim.
- `DISPROVED`: validated operands and the rule contradict the atomic claim.
- `UNRESOLVED`: the rule is relevant, but its evidence or preconditions are
  insufficient, ambiguous, or conflicting.
- `NOT_APPLICABLE`: the rule does not apply to the atomic claim and premises.

Only `PROVED` and `DISPROVED` contribute decisive symbolic support or
refutation. The other states remain inspectable but do not determine a verdict.

## Deterministic verdict composition

For each atomic claim `o`, sufficient direct evidence and resolved symbolic
outputs determine a support indicator `S_o` and a refutation indicator `R_o`:

| `S_o` | `R_o` | Atomic state |
| :---: | :---: | --- |
| 1 | 0 | `SUPPORTED` |
| 0 | 1 | `REFUTED` |
| 1 | 1 | `CONFLICTING_EVIDENCE` |
| 0 | 0 | `NOT_ENOUGH_EVIDENCE` |

A `SINGLE` claim inherits its atom's state. For `AND`, one refuted atom refutes
the conjunction; otherwise a conflicting atom makes it conflicting, all atoms
supported makes it supported, and remaining cases lack enough evidence. For
`OR`, one supported atom supports the disjunction; otherwise a conflicting atom
makes it conflicting, all atoms refuted makes it refuted, and remaining cases
lack enough evidence.

Reviewer changes to evidence relations pass through the same composition rules.
Neither the interface nor the recorded reference verdict can override them.

## Boundaries

The symbolic layer guarantees that a registered operation is executed
consistently over validated, source-linked operands. It does not guarantee
source authority, extraction correctness, semantic equivalence, exhaustive
world knowledge, implicit unit conversion, or general logical reasoning.
