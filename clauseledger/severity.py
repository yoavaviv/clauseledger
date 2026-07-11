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

# base tier + score per clause type (money-at-risk x time-to-trigger)
_BASE: dict[str, tuple[str, float, str]] = {
    "Cap On Liability": ("critical", 0.95,
        "caps total financial exposure; missing it can leave liability uncapped"),
    "Notice Period To Terminate Renewal": ("high", 0.85,
        "time-triggered: miss the notice window and you are locked into another paid term"),
    "Liquidated Damages": ("high", 0.80,
        "pre-agreed money payable on breach; direct cash exposure"),
    "Renewal Term": ("medium", 0.55,
        "evergreen/auto-renew lock-in; sets the clock the notice period runs against"),
    "Post-Termination Services": ("medium", 0.50,
        "continuing obligations and cost after the contract ends"),
    "Governing Law": ("low", 0.25,
        "controls interpretation and venue; rarely direct money-at-risk"),
}

_MONEY = re.compile(r"(\$|usd|eur|\bpounds?\b|%|percent|per cent|million|thousand)", re.I)
_TIME = re.compile(r"\b(\d+)\s*(day|business day|month|week)s?\b", re.I)

PROVISIONAL = True  # flag surfaced in the report so the UI can label it


def score_severity(clause_type: str, claim: str) -> Severity:
    tier, score, rationale = _BASE.get(clause_type, ("medium", 0.5, "unclassified obligation"))
    text = claim or ""
    # small, transparent bumps: explicit money or a tight deadline raise urgency
    if _MONEY.search(text):
        score = min(1.0, score + 0.05)
    m = _TIME.search(text)
    if m and int(m.group(1)) <= 30:
        score = min(1.0, score + 0.05)
    return Severity(tier=tier, score=round(score, 3),
                    rationale=f"[provisional] {rationale}")
