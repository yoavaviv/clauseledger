# ADR 0004: Local Ollama, and a weaker model on purpose

**Date:** 2026-07-11 · **Status:** accepted

## Context
The showcase must be billing-clean (no API keys) and reproducible by anyone. Extraction quality
is not the point - the reliability harness on top is.

## Decision
Default extraction backend is a local Ollama model (`mistral:7b`), billing-clean and
reproducible with no keys. The harness is model-agnostic (pluggable backends); a stronger model
is a one-line swap.

## Consequences
A weaker model MISSES more, which makes the recovery-pass lift and the abstention behaviour more
pronounced - it sharpens exactly what the harness demonstrates. The frozen demo's model is stated
in the scoreboard; the numbers are honest for that model and reproducible.
