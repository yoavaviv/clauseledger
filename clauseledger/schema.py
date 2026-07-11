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


class Grounding(BaseModel):
    """Result of locating a candidate's quote in the contract text."""
    span: Optional[Span] = None
    score: float = Field(ge=0.0, le=1.0, description="fuzzy match quality 0..1")
    grounded: bool = False


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
