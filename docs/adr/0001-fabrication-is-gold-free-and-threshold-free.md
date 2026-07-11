# ADR 0001: Fabrication is measured gold-free AND threshold-free

**Date:** 2026-07-11 · **Status:** accepted

## Context
CUAD is a fixed 41-clause-type SPAN dataset, not an enumeration of every obligation. If
"fabrication" were measured against CUAD gold, a real obligation the annotators never tagged
would count as a fabrication - a disagreement-with-annotators artifact, not real fabrication.
A knowledgeable reviewer punctures that in one question.

## Decision
Fabrication = the cited quote is not actually in the contract, decided by grounding score
below a **fixed floor (0.6)** that is independent of the verification threshold. It needs no
answer key (a quote either is or is not in the document) and cannot be gamed by moving the
verification threshold.

## Consequences
Fabrication leads the scoreboard as the honest, un-gameable number. The verification threshold
(0.85, tunable) governs *assertion*, a separate dial - demonstrated by the `strict_verifier`
fault, which moves recall but not fabrication.

## Limitation (stated, not hidden)
Fuzzy matching (`partial_ratio`) can score a fabrication assembled from real contract phrases
above the floor. This is a known weakness; the floor bounds obvious fabrication, not adversarial
stitching. See README limitations.
