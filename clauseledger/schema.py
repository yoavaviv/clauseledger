"""Core data model for ClauseLedger.

Every object here is part of the frozen contract shared by the pipeline, the tests,
and the static demo UI. Char offsets (`start`, `end`) index into the contract's raw
text, so a span is always independently checkable against the source.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# The 6 genuinely-expensive clause types we scope to (each has CUAD gold).
CLAUSE_TYPES: list[str] = [
    "Renewal Term",
    "Notice Period To Terminate Renewal",
    "Cap On Liability",
    "Liquidated Damages",
    "Post-Termination Services",
    "Governing Law",
]


class Source(str, Enum):
    """Which pass produced a row: the first single-shot pass, or the adversarial
    recovery pass that hunts for what the first pass missed."""
    INITIAL = "initial"
    RECOVERY = "recovery"


class Span(BaseModel):
    """A character range in the contract text, with the exact substring it covers."""
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    text: str

    def overlaps(self, other: "Span") -> bool:
        return self.start < other.end and other.start < self.end

    def iou(self, other: "Span") -> float:
        """Intersection-over-union of the two character ranges (0..1)."""
        inter = max(0, min(self.end, other.end) - max(self.start, other.start))
        union = (self.end - self.start) + (other.end - other.start) - inter
        return inter / union if union > 0 else 0.0


class Candidate(BaseModel):
    """A raw obligation a backend claims to have found, before grounding/verification.

    `quote` is the verbatim contract text the model says supports the claim; we later
    ground it to a real Span and reject it if it is not actually in the document.
    """
    clause_type: str
    claim: str
    quote: str
    source: Source = Source.INITIAL


class StitchEvidence(BaseModel):
    """Proof that a quote was assembled from disjoint verbatim fragments of the source.

    A stitched quote's pieces are all real, but they never appear contiguously - so the
    quote as a whole is a fabrication that plain fuzzy matching admits. `fragments` are the
    real source spans the quote was reconstructed from; `coverage` is the fraction of the
    quote's words those fragments account for.
    """
    fragments: list[Span] = Field(default_factory=list)
    coverage: float = Field(ge=0.0, le=1.0)


class Grounding(BaseModel):
    """Result of locating a candidate's quote in the contract text."""
    span: Optional[Span] = None
    score: float = Field(ge=0.0, le=1.0, description="fuzzy match quality 0..1")
    grounded: bool = False
    # True when the quote is real fragments stitched from non-contiguous source spans
    # (a fabrication fuzzy scoring would otherwise pass). Never grounded when True.
    stitched: bool = False
    stitch_fragments: list[Span] = Field(default_factory=list)


class Verdict(BaseModel):
    """The independent verifier's ruling on whether the cited span supports the claim."""
    supported: bool
    reason: str
    match_score: float = Field(ge=0.0, le=1.0)


class Severity(BaseModel):
    """Yoav's commercial-severity view: how much a missed obligation of this kind hurts.

    PROVISIONAL rubric (money-at-risk x time-to-trigger). Marked to be replaced by
    Yoav's own hand-annotated rubric; never presented as a measured result.
    """
    tier: str = Field(description="one of: critical, high, medium, low")
    score: float = Field(ge=0.0, le=1.0)
    rationale: str


class RegisterRow(BaseModel):
    """One obligation in the final register, with its full provenance trace."""
    row_id: str
    clause_type: str
    claim: str
    quote: str
    grounding: Grounding
    verdict: Verdict
    source: Source
    confidence: float = Field(ge=0.0, le=1.0)
    abstained: bool = False
    abstain_reason: str = ""  # "low confidence" or "legal-mechanics: <signal>"
    severity: Optional[Severity] = None
    # True once matched against a CUAD gold span (only known in eval mode).
    matches_gold: Optional[bool] = None


class ContractResult(BaseModel):
    contract_id: str
    text_len: int
    split: str = ""
    rows: list[RegisterRow] = Field(default_factory=list)
    # Row ids found only after the recovery pass (the measurable recall lift).
    recovered_row_ids: list[str] = Field(default_factory=list)


class CI(BaseModel):
    """A percentile confidence interval for a metric, from bootstrap resampling over
    contracts. On a small test set a point estimate is not enough - the interval says how
    much the number could move if the sample of contracts were different."""
    lo: float
    hi: float
    n_boot: int = 0
    level: float = 0.95


class ClauseMetric(BaseModel):
    clause_type: str
    gold_total: int
    recall_single_shot: float
    recall_post_recovery: float
    precision: float


class ParetoPoint(BaseModel):
    threshold: float
    precision: float
    recall: float
    abstention: float


class StitchDefenseMetric(BaseModel):
    """Adversarial measurement of the stitch guard on real contracts.

    Stitched fabrications (real head + real far-apart tail) are injected and scored; the
    guard should reject all of them AND attribute them as fabrication even when their best
    fuzzy window scores above the floor. The safety number is `false_positive_rate`: how
    often a GENUINE gold quote is wrongly flagged as stitched (must stay ~0, or the guard
    would be corroding the tool's trust instead of protecting it).
    """
    injected: int = 0
    caught: int = 0                      # injected stitches correctly NOT grounded (guard on)
    catch_rate: float = 0.0
    # THE headline: stitches fuzzy grounding would have ASSERTED (score >= threshold) as
    # real obligations - silent false accepts the guard prevents. 0 without the guard's help.
    would_assert_without_guard: int = 0
    attributed_fabrication: int = 0      # injected stitches counted as fabrication WITH the guard
    attributed_baseline: int = 0         # ... counted as fabrication WITHOUT it (raw score < floor)
    genuine_checked: int = 0             # real gold quotes tested for false positives
    false_positives: int = 0             # genuine quotes wrongly flagged as stitched
    false_positive_rate: float = 0.0


class FaultResult(BaseModel):
    name: str
    description: str
    baseline_recall: float
    faulted_recall: float
    fabrication_rate: float
    completion: float = Field(description="fraction of contracts the pipeline finished under this fault")


class Metrics(BaseModel):
    n_contracts: int
    per_clause: list[ClauseMetric] = Field(default_factory=list)
    # Detection recall: obligations LOCATED (before the abstention gate). Drives recall-lift.
    recall_single_shot: float = 0.0
    recall_post_recovery: float = 0.0
    recall_lift: float = 0.0
    # Asserted recall: covered only by asserted (supported, non-abstained) rows - the honest
    # number a user can act on directly. Always <= recall_post_recovery.
    recall_asserted: float = 0.0
    precision: float = 0.0
    # Gold-independent: fraction of emitted rows whose quote is NOT in the document.
    fabrication_rate: float = 0.0
    # On genuinely-absent clause types: confident emissions that should not exist.
    false_alarm_rate: float = 0.0
    abstention_rate: float = 0.0
    pareto: list[ParetoPoint] = Field(default_factory=list)
    faults: list[FaultResult] = Field(default_factory=list)
    # Adversarial stitch-defense measurement (None when not run).
    stitch_defense: Optional["StitchDefenseMetric"] = None
    # 95% bootstrap confidence intervals for headline metrics, keyed by metric name.
    ci: dict[str, CI] = Field(default_factory=dict)


class RunConfig(BaseModel):
    backend: str
    model: str
    abstain_threshold: float
    ground_threshold: float = 0.85
    # A quote scoring below this is treated as genuinely NOT in the document -> fabrication.
    # Fixed and independent of the verification threshold, so fabrication_rate cannot be
    # gamed by moving ground_threshold.
    fabrication_floor: float = 0.6
    # overlap / smaller-span-length threshold for counting a row as matching CUAD gold
    gold_overlap_threshold: float = 0.5
    n_contracts: int = 0
    notes: str = ""


class RunReport(BaseModel):
    """The full frozen artifact the static demo renders."""
    generated_utc: str
    config: RunConfig
    metrics: Metrics
    contracts: list[ContractResult] = Field(default_factory=list)
