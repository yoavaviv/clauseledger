"""Commercial-severity view: how much a MISSED obligation of each type hurts.

PROVISIONAL rubric on two axes - money-at-risk x time-to-trigger - as a placeholder
for Yoav's own hand-annotated commercial-severity gold (his 20y SI bid/contract
judgment is the real moat). This is a curated PRIORITIZATION, never a measured result,
and the UI must label it as such.

Replace `_BASE` and `_bump` with Yoav's annotated rubric when ready. See
docs/adr and the project brief.
"""
from __future__ import annotations

import re

from .schema import Severity

# Rationale is stated in HARM-OF-THE-MISS terms (what goes wrong if the extractor
# MISSES a clause that is present), not harm-of-the-clause. A miss never changes the
# contract; it changes what the reviewer knows.
# `kind` marks whether the term is a genuine obligation (a duty) vs an allocation
# (a shield/limitation) vs a mechanic (duration/framework) - only some are "obligations".
# base tier + score + rationale + kind
_BASE: dict[str, tuple[str, float, str, str]] = {
    "Cap On Liability": ("critical", 0.95,
        "if a cap exists and is missed, you misprice exposure and may fail to invoke it; "
        "a genuinely absent cap is a separate uncapped-liability finding", "allocation"),
    "Notice Period To Terminate Renewal": ("high", 0.85,
        "time-triggered: miss this and you can blow the non-renewal window and get locked "
        "into another paid term", "obligation"),
    "Liquidated Damages": ("high", 0.80,
        "missing it misjudges cash exposure on breach; enforceability (genuine pre-estimate "
        "vs penalty) is a legal question routed to a human", "obligation"),
    "Renewal Term": ("medium", 0.55,
        "missing the renewal duration/mechanism mis-sets the clock the notice period runs "
        "against", "mechanic"),
    "Post-Termination Services": ("medium", 0.50,
        "missing it under-scopes continuing duties and cost after the contract ends", "obligation"),
    "Governing Law": ("low", 0.25,
        "the substantive law governing interpretation (distinct from forum/jurisdiction and "
        "dispute-resolution, which are not captured here); rarely direct money-at-risk", "mechanic"),
}


def clause_kind(clause_type: str) -> str:
    """obligation (a duty) | allocation (a shield/limitation) | mechanic (duration/framework)."""
    return _BASE.get(clause_type, (None, None, None, "mechanic"))[3]

_MONEY = re.compile(r"(\$|usd|eur|\bpounds?\b|%|percent|per cent|million|thousand)", re.I)
_TIME = re.compile(r"\b(\d+)\s*(day|business day|month|week)s?\b", re.I)

PROVISIONAL = True  # flag surfaced in the report so the UI can label it


def score_severity(clause_type: str, claim: str) -> Severity:
    tier, score, rationale, _kind = _BASE.get(clause_type, ("medium", 0.5, "unclassified term", "mechanic"))
    text = claim or ""
    # small, transparent bumps: explicit money or a tight deadline raise urgency
    if _MONEY.search(text):
        score = min(1.0, score + 0.05)
    m = _TIME.search(text)
    if m and int(m.group(1)) <= 30:
        score = min(1.0, score + 0.05)
    return Severity(tier=tier, score=round(score, 3),
                    rationale=f"[provisional] {rationale}")
