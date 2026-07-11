# ADR 0006: No retrieval-RAG; exhaustive long-context windows

**Date:** 2026-07-11 · **Status:** accepted

## Context
Doing retrieval/chunking over a SINGLE contract that fits in a modern context window is the wrong
frame - a staff engineer's first question would be "why are you retrieving over one document?".

## Decision
Extract over the full contract in long context. For models with limited context, use exhaustive
sequential windows (every part of the document is seen), which is NOT selective retrieval. The
adversarial coverage pass re-reads each section for obligations the first pass missed.

## Consequences
The "omission" the harness measures is a genuine model failure, not an artifact of a retriever
dropping context. The recovery pass is a real second look, not a re-retrieval.
