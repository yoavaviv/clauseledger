# ADR 0007: The legal-concept boundary (what the tool claims, and does not)

**Date:** 2026-07-11 · **Status:** accepted (after a contracts-lawyer concept review)

## Context
The author is a 20-year systems/integration expert, not a lawyer. A legal-concept review
found four issues that an interviewer could expose: (1) Governing Law was conflated with
jurisdiction/venue; (2) three of the six clause types (Governing Law, Cap On Liability,
Renewal Term) are not "obligations" but allocations/mechanics; (3) severity rationales
described harm-of-the-clause instead of harm-of-the-miss; (4) abstention keyed on model
confidence, so the tool did not actually cede the legal-mechanics questions it claimed to.

## Decision
- **Terminology.** The extracted unit is a "commercially material provision", tagged by kind
  (obligation / allocation / mechanic). Only Notice Period, Liquidated Damages, and
  Post-Termination Services are genuine obligations; the tool no longer calls all six that.
- **Governing Law** is defined as the substantive law governing interpretation, explicitly
  distinct from forum/jurisdiction and dispute-resolution (which are out of scope).
- **Severity** rationales are stated in harm-of-the-MISS terms (a miss changes what the
  reviewer knows, never the contract). "Uncapped liability" is a separate finding from
  "a cap exists and was missed".
- **Abstention** gains a second, orthogonal trigger: text signals of legal complexity
  (condition-precedent "provided that / subject to", survival, materiality, penalty/LD
  language) force "human-SME needed" regardless of confidence. Now the claimed boundary
  ("we cede legal mechanics") is the implemented one.

## Scope honesty (stated, not hidden)
The six are a CUAD-derived demo subset. In a real MSA the top money-risks are
indemnification, uncapped liability / consequential-damages exclusion, and IP - none in
scope here. Liquidated-damages enforceability (genuine pre-estimate vs penalty; UK
Cavendish/Makdessi, US penalty rule) and SLA service-credit-vs-LD distinctions are routed
to a human. Grounding confirms a quote EXISTS, not that it is operative language (a recital
or definition can ground) - see README limitations.

## Consequences
Every genuine legal error is removed; the remaining scope limits are named up front rather
than discovered in an interview. Commercial-severity judgment (which miss bleeds money)
remains the author's defensible edge; legal-mechanics adjudication is deferred to counsel.
