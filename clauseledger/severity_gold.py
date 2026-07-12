"""Yoav's hand-annotated commercial-severity gold - the authored moat.

The provisional rubric in `severity.py` ranks clause types by a generic
money-at-risk x time-to-trigger heuristic. THIS module consumes the real thing:
a human annotation set on genuine SaaS master service agreements (a class CUAD does
not cover), where the severity ordering is Yoav's expert judgment from 20 years of
enterprise bid/contract work, not a formula.

Two layers live in the annotation file:

  * `rubric.types`  - a type-level ordering of the 6 clause types by how much a MISS
    of that type bleeds money. This can REPLACE the provisional `_BASE` tiers.
  * `entries`       - instance-level annotations on real MSA clauses (the held-out
    evidence). Each carries the two ordinal axes, the clause kind, whether the tool is
    EXPECTED to abstain, and a lived-experience rationale.

Severity is a curated PRIORITISATION, never a measured result. Nothing here is
presented as an accuracy number; the agreement metric below only reports how far the
cheap provisional heuristic already tracks the expensive expert ordering.

Full MSA texts are third-party documents and are NOT redistributed: annotations carry
only short fair-use quotes plus a source reference and a local content hash. The raw
texts (for running the held-out reliability pass) live in a gitignored `raw/` folder.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from .cuad import Contract
from .schema import CLAUSE_TYPES, Span

_DEFAULT = Path(__file__).resolve().parent.parent / "data" / "severity_gold" / "annotations.json"
_RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "severity_gold" / "raw"

# money is weighted above urgency: a large exposure you notice late still hurts more
# than a tight deadline on a trivial sum. Transparent and adjustable.
_MONEY_WEIGHT = 0.6
_TIME_WEIGHT = 0.4


def derive_score(money_at_risk: int, time_to_trigger: int) -> float:
    """Collapse the two ordinal axes (1..5 each) into a 0..1 severity score."""
    return round((_MONEY_WEIGHT * money_at_risk + _TIME_WEIGHT * time_to_trigger) / 5.0, 3)


class _Axes(BaseModel):
    money_at_risk: int = Field(ge=1, le=5, description="ordinal 1..5; higher = more money exposed by a miss")
    time_to_trigger: int = Field(ge=1, le=5, description="ordinal 1..5; higher = tighter/sooner window to act")

    @property
    def score(self) -> float:
        return derive_score(self.money_at_risk, self.time_to_trigger)


class RubricType(_Axes):
    """Type-level severity judgment for one clause type (replaces a provisional `_BASE` row)."""
    clause_type: str
    kind: str = Field(description="obligation | allocation | mechanic")
    rationale: str

    @field_validator("clause_type")
    @classmethod
    def _known_type(cls, v: str) -> str:
        if v not in CLAUSE_TYPES:
            raise ValueError(f"unknown clause_type {v!r}; expected one of {CLAUSE_TYPES}")
        return v


class GoldEntry(_Axes):
    """Instance-level annotation of one clause found in one real MSA (held-out evidence)."""
    msa_id: str
    clause_type: str
    quote: str = Field(description="short verbatim excerpt, fair-use only - never the full clause")
    kind: str = Field(description="obligation | allocation | mechanic")
    abstain_expected: bool = Field(
        default=False,
        description="True where the correct behaviour is to route to a human (legal-mechanics seam)")
    rationale: str

    @field_validator("clause_type")
    @classmethod
    def _known_type(cls, v: str) -> str:
        if v not in CLAUSE_TYPES:
            raise ValueError(f"unknown clause_type {v!r}; expected one of {CLAUSE_TYPES}")
        return v


class RubricMeta(BaseModel):
    annotator: str
    version: str
    dated: str
    axes_note: str = ""


class SeverityGold(BaseModel):
    """The full annotation set: type-level rubric + instance-level entries."""
    meta: RubricMeta
    types: list[RubricType] = Field(default_factory=list)
    entries: list[GoldEntry] = Field(default_factory=list)

    @property
    def is_populated(self) -> bool:
        """True once real annotations exist (not just the empty stub)."""
        return bool(self.types) and bool(self.entries)

    def ranking(self) -> list[str]:
        """Clause types ordered most- to least-severe by the annotator's derived score."""
        return [t.clause_type for t in sorted(self.types, key=lambda t: t.score, reverse=True)]

    def msa_ids(self) -> list[str]:
        seen: list[str] = []
        for e in self.entries:
            if e.msa_id not in seen:
                seen.append(e.msa_id)
        return seen


def load_severity_gold(path: str | Path = _DEFAULT) -> SeverityGold:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return SeverityGold.model_validate(raw)


def provisional_ranking() -> list[str]:
    """The current provisional rubric's ordering, for comparison against the gold."""
    from .severity import _BASE
    return [ct for ct, _ in sorted(_BASE.items(), key=lambda kv: kv[1][1], reverse=True)]


def kendall_tau(rank_a: list[str], rank_b: list[str]) -> float:
    """Rank correlation over the items common to both orderings (-1..1).

    +1 = identical ordering, -1 = exactly reversed, 0 = no association. No scipy dependency.
    """
    common = [x for x in rank_a if x in rank_b]
    pos_b = {x: i for i, x in enumerate(rank_b)}
    order_a = [x for x in rank_a if x in common]
    n = len(order_a)
    if n < 2:
        return 0.0
    concordant = discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            # order_a already ascending in a; compare b's positions
            b_i, b_j = pos_b[order_a[i]], pos_b[order_a[j]]
            if b_i < b_j:
                concordant += 1
            else:
                discordant += 1
    total = n * (n - 1) / 2
    return round((concordant - discordant) / total, 4) if total else 0.0


def rank_agreement(gold: SeverityGold) -> Optional[float]:
    """Kendall tau between the provisional heuristic ordering and the gold ordering.

    None until the gold rubric is populated. This is the ONLY number the gold produces
    about the rubric itself: how far the cheap default already tracks expert judgment.
    """
    if not gold.types:
        return None
    return kendall_tau(provisional_ranking(), gold.ranking())


def rubric_from_gold(gold: SeverityGold) -> dict[str, tuple[str, float, str, str]]:
    """Turn the gold rubric into a `severity._BASE`-shaped dict so it can replace the
    provisional tiers wholesale. Tier is bucketed from the derived score.
    """
    def tier_for(score: float) -> str:
        if score >= 0.85:
            return "critical"
        if score >= 0.65:
            return "high"
        if score >= 0.4:
            return "medium"
        return "low"

    return {
        t.clause_type: (tier_for(t.score), t.score, t.rationale, t.kind)
        for t in gold.types
    }


def load_heldout_contracts(gold: SeverityGold, raw_dir: str | Path = _RAW_DIR) -> list[Contract]:
    """Build pipeline `Contract`s from locally-present raw MSA texts (gitignored).

    Each MSA text is read from `raw/<msa_id>.txt`. MSAs with no local text are skipped
    (the committed repo ships labels, not the copyrighted contracts), so this returns
    only the subset a given machine can actually run. The annotator's short quotes are
    attached as gold spans for their clause type where the quote is locatable, so the
    held-out pass can also report recall against the hand labels.
    """
    raw_dir = Path(raw_dir)
    by_msa: dict[str, list[GoldEntry]] = {}
    for e in gold.entries:
        by_msa.setdefault(e.msa_id, []).append(e)

    contracts: list[Contract] = []
    for msa_id, entries in by_msa.items():
        text_path = raw_dir / f"{msa_id}.txt"
        if not text_path.exists():
            continue
        text = text_path.read_text(encoding="utf-8")
        gold_spans: dict[str, list[Span]] = {}
        for e in entries:
            idx = text.find(e.quote)
            if idx >= 0:
                gold_spans.setdefault(e.clause_type, []).append(
                    Span(start=idx, end=idx + len(e.quote), text=e.quote))
        contracts.append(Contract(id=msa_id, text=text, gold=gold_spans, absent=[], split="heldout"))
    return contracts
