"""Independent verifier: does the cited quote actually support the claim?

Deterministic and gold-free. It grounds the quote in the document; a claim whose
quote cannot be located is rejected as unsupported (a fabrication). Confidence
tracks how firmly the citation was located, which is what abstention keys on.
"""
from __future__ import annotations

from .ground import ground_quote
from .schema import Candidate, Grounding, Verdict


def verify_candidate(cand: Candidate, text: str, ground_threshold: float = 0.85
                     ) -> tuple[Grounding, Verdict, float]:
    g = ground_quote(cand.quote, text, ground_threshold)
    supported = g.grounded
    if supported:
        reason = "cited text located in the contract"
    elif g.stitched:
        reason = ("cited text is stitched from non-contiguous fragments of the contract "
                  "(fabrication: the pieces are real but never appear together)")
    else:
        reason = "cited text not found in the contract (unsupported / possible fabrication)"
    verdict = Verdict(supported=supported, reason=reason, match_score=round(g.score, 4))
    confidence = round(g.score, 4)
    return g, verdict, confidence
