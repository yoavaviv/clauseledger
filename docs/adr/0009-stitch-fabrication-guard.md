# ADR 0009: A contiguity guard closes the stitched-fabrication hole

**Date:** 2026-07-19 · **Status:** accepted

## Context
ADR 0001 measures fabrication as "the cited quote is not in the document," decided by a fuzzy
grounding score below a fixed floor. Its stated weakness: a quote **stitched** from real
contract phrases taken from different places can score above the floor, because fuzzy
`partial_ratio` aligns the quote to the best local window and a dominant real fragment carries
the score. Such a quote is a fabrication - the pieces are real but never appear together - yet
fuzzy grounding admits it, and worse, a stitch with a long dominant fragment can clear the
0.85 assertion bar and be ASSERTED as a genuine obligation.

## Decision
Add a deterministic **stitch guard** that runs BEFORE fuzzy alignment (`detect_stitch` in
`ground.py`). It reconstructs the quote from the longest verbatim fragments of the source; if
the quote is covered by >=2 fragments whose source spans are **non-contiguous** (out of order,
or separated by more than a small slack), the quote is flagged `stitched` and is **never
grounded**, regardless of its fuzzy score. A stitched quote counts as fabrication in the
scoreboard even when its best fuzzy window scores above the floor.

The guard is conservative by construction: short quotes, contiguous quotes, and genuine fuzzy
noise (a real quote with minor character differences) are all left to the normal path. Favoring
precision here is deliberate - false-flagging a REAL quote as a fabrication would corrode the
tool's trust, which is worse than missing one exotic stitch.

## Consequences
Measured on the CUAD subset with an adversarial harness that injects stitched fabrications
(`clauseledger/adversarial.py`, surfaced as `stitch_defense` in the report):
- **100% of injected stitches are caught** (none grounded).
- **~62% of them would have been ASSERTED as real obligations by fuzzy grounding alone** - the
  silent false accepts the guard prevents.
- **0 false positives on the real CUAD gold quotes** - genuine obligations are never flagged.
- Every injected stitch is now attributed as fabrication; without the guard, none were (their
  raw fuzzy scores sit above the floor).

## Limitation (stated, not hidden)
The guard targets cross-location stitching. A quote that drops only a SHORT middle phrase (its
fragments stay within the contiguity slack) is treated as benign, even though the omission can
change meaning. That narrower "material-omission" class is out of scope; the guard bounds
stitched fabrication, not every misquote. See README limitations.
