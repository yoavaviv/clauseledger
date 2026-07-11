"""Calibrated abstention.

A supported row is only ASSERTED if its confidence clears the threshold; otherwise
it is emitted as "human-SME needed" rather than stated as fact. Unsupported rows are
rejected by the verifier and are a separate state (not abstention). The threshold is
calibrated on the dev split; the precision/recall/abstention tradeoff is published as
a Pareto curve, never a single flattering number.
"""
from __future__ import annotations

import re

from .schema import RegisterRow

# Text signals that a clause raises a LEGAL-MECHANICS question (condition-precedent,
# survival, materiality, penalty/LD enforceability) that the tool deliberately does NOT
# adjudicate. These fire regardless of model confidence, so the "cede legal mechanics to
# a human" boundary is real and not merely a function of the confidence gate.
_LEGAL_SIGNALS = {
    "condition-precedent": re.compile(
        r"\b(provided\s+that|subject\s+to|as\s+a\s+condition\s+(?:to|of)|conditioned\s+upon)\b", re.I),
    "survival": re.compile(r"\bsurviv(?:e|es|al)\b", re.I),
    "materiality": re.compile(r"\bmaterial(?:ly)?\s+(?:breach|adverse)\b|\bin\s+all\s+material\s+respects\b", re.I),
    "penalty/enforceability": re.compile(r"\b(penalty|liquidated\s+damages)\b", re.I),
}


def legal_complexity(text: str) -> list[str]:
    """Return the legal-mechanics signals present in `text` (empty if none)."""
    return [name for name, pat in _LEGAL_SIGNALS.items() if pat.search(text or "")]


def apply_abstention(rows: list[RegisterRow], threshold: float) -> None:
    """Abstain on supported rows below the confidence threshold, OR that raise a
    legal-mechanics question in the text (regardless of confidence). In place."""
    for r in rows:
        if not r.verdict.supported:
            r.abstained = False
            r.abstain_reason = ""
            continue
        signals = legal_complexity(r.quote)
        if r.confidence < threshold:
            r.abstained = True
            r.abstain_reason = "low confidence"
        elif signals:
            r.abstained = True
            r.abstain_reason = "legal-mechanics: " + ", ".join(signals)
        else:
            r.abstained = False
            r.abstain_reason = ""


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
