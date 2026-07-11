# ADR 0003: The demo is a static, precomputed explorer

**Date:** 2026-07-11 · **Status:** accepted

## Context
A live demo that calls an LLM per visitor is a billing and uptime liability, and a perpetual
babysit commitment - the wrong shape for a solo operator (a frozen, dead demo reads worse than
none).

## Decision
Run the full pipeline ONCE offline; freeze every register row, per-row trace, metric, and
fault-injection result to static JSON. The web page renders it with **zero live inference**.
An optional "verify it yourself" path lives off the critical demo path (BYO-key or a no-card
free tier that cannot overspend).

## Consequences
Billing-clean by construction, always-up, zero-babysit. Reproducibility (a one-command offline
eval harness), not a live button, is the trust signal. Extraction is cached (`replay_cache.json`)
so metrics recompute without re-running any model.
