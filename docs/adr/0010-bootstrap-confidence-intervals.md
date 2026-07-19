# ADR 0010: Headline metrics carry bootstrap confidence intervals

**Date:** 2026-07-19 · **Status:** accepted

## Context
The frozen demo reports metrics on a small held-out test set (single-digit contracts). A bare
point estimate ("recall 0.79") reads as more certain than it is: with a handful of contracts,
the number would move a lot if the sample were different. Presenting a point estimate without
its uncertainty is exactly the "good demo, can't trust it" failure this project exists to call
out - applied to our own scoreboard.

## Decision
Attach a **95% percentile bootstrap confidence interval** to each headline metric
(`bootstrap_metrics` in `metrics.py`, surfaced as `metrics.ci`). Resampling is at the
**contract level** with replacement (contracts are the independent observations, and it is the
small NUMBER OF CONTRACTS that drives the uncertainty), recomputing the full metric on each
resample. The bootstrap is deterministic (fixed seed) so the frozen number reproduces exactly.

## Consequences
The demo shows each number as `estimate [lo-hi]`. On the small test set the intervals are wide
(e.g. recall 0.79 with a CI spanning roughly 0.5-1.0), which is the honest message: the harness
and the method generalize, but the ABSOLUTE numbers are demo-scale and are labelled as such. As
the corpus grows, the intervals narrow - the CI is the visible payoff of a bigger run.

## Limitation (stated, not hidden)
The bootstrap quantifies sampling variability over the contracts we HAVE; it does not correct
for the CUAD subset being non-representative of production contracts, nor for the fixed-schema
recall denominator (ADR 0002). It is an honesty instrument for the sample, not a claim about the
population.
