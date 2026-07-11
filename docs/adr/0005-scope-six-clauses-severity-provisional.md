# ADR 0005: Scope to 6 expensive clause types; severity is provisional

**Date:** 2026-07-11 · **Status:** accepted

## Context
Trying to cover all 41 CUAD categories dilutes the demo and buries the reliability story. The
commercial-severity judgment (which missed obligation actually bleeds money) is the defensible
moat, and it must be visibly the author's, not borrowed from CUAD's annotators.

## Decision
Scope to 6 genuinely-expensive clause types with CUAD gold: Renewal Term, Notice Period To
Terminate Renewal, Cap On Liability, Liquidated Damages, Post-Termination Services, and Governing
Law (as a control). Ship a **provisional** severity rubric (money-at-risk x time-to-trigger),
clearly labelled, as a placeholder for Yoav Aviv's hand-annotated commercial-severity gold. The
UI and docs never present severity as a measured result.

## Consequences
The reliability numbers stay legible; the severity layer is honest about being a curated
prioritisation, and is the part a weekend clone cannot reproduce.
