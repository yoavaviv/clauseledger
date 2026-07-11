# ADR 0002: Report detection recall AND asserted recall

**Date:** 2026-07-11 · **Status:** accepted

## Context
Headline recall counts gold spans located by supported rows - including rows the system then
abstains on ("human-SME needed"). That is *detection* recall, and it is higher than what a user
can act on directly. Reporting only detection recall would overstate trustworthiness.

## Decision
Report both. **Detection recall** (obligations located, before the abstention gate) drives the
recovery-lift story. **Asserted recall** (covered only by asserted, non-abstained rows) is the
honest number a user acts on, and is always <= detection recall. The Pareto curve shows the full
precision/recall/abstention tradeoff across thresholds.

## Consequences
No number reads higher than it should. The recovery pass is credited for detection; the
abstention gate is credited for trustworthiness; the gap between them is visible.
