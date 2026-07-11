"""Calibrated abstention.

A supported row is only ASSERTED if its confidence clears the threshold; otherwise
it is emitted as "human-SME needed" rather than stated as fact. Unsupported rows are
rejected by the verifier and are a separate state (not abstention). The threshold is
calibrated on the dev split; the precision/recall/abstention tradeoff is published as
a Pareto curve, never a single flattering number.
"""
from __future__ import annotations

from .schema import RegisterRow


def apply_abstention(rows: list[RegisterRow], threshold: float) -> None:
    """Mark supported-but-low-confidence rows as abstained (in place)."""
    for r in rows:
        r.abstained = bool(r.verdict.supported and r.confidence < threshold)


def calibrate_threshold(dev_rows: list[RegisterRow], target_precision: float = 0.9,
                        grid: list[float] | None = None) -> float:
    """Pick the lowest threshold on the dev split that reaches target asserted-precision.

    Returns the smallest threshold whose asserted rows hit target precision; if none do,
    returns the highest grid value. Requires rows with matches_gold set (eval mode).
    """
    grid = grid or [i / 20 for i in range(0, 21)]
    best = grid[-1]
    for t in grid:
        asserted = [r for r in dev_rows if r.verdict.supported and r.confidence >= t]
        if not asserted:
            continue
        prec = sum(1 for r in asserted if r.matches_gold) / len(asserted)
        if prec >= target_precision:
            best = t
            break
    return best
