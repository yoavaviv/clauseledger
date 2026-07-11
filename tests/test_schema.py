"""Tests for clauseledger.schema.

Covers Span geometry (overlaps/iou), pydantic bound validation, enum values,
serialization roundtrips for the frozen artifact models, model defaults, and the
CLAUSE_TYPES registry.
"""
import pytest
from pydantic import ValidationError

from clauseledger.schema import (
    CLAUSE_TYPES,
    Source,
    Span,
    Candidate,
    Grounding,
    Verdict,
    Severity,
    RegisterRow,
    ContractResult,
    ClauseMetric,
    ParetoPoint,
    FaultResult,
    Metrics,
    RunConfig,
    RunReport,
)


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def make_grounding(span=None, score=0.9, grounded=True):
    return Grounding(span=span, score=score, grounded=grounded)


def make_verdict(supported=True, reason="ok", match_score=0.8):
    return Verdict(supported=supported, reason=reason, match_score=match_score)


def make_register_row(**kw):
    base = dict(
        row_id="r1",
        clause_type="Governing Law",
        claim="a claim",
        quote="some quote",
        grounding=make_grounding(span=Span(start=0, end=4, text="some")),
        verdict=make_verdict(),
        source=Source.INITIAL,
        confidence=0.7,
    )
    base.update(kw)
    return RegisterRow(**base)


# ----------------------------------------------------------------------------
# Span.overlaps geometry
# ----------------------------------------------------------------------------

@pytest.mark.parametrize("a,b,expected", [
    ((0, 5), (3, 8), True),      # partial overlap
    ((0, 5), (5, 10), False),    # touching at boundary -> no overlap (half-open)
    ((0, 10), (2, 5), True),     # one contains the other
    ((2, 5), (0, 10), True),     # contained (symmetric)
    ((0, 5), (6, 10), False),    # disjoint with gap
    ((5, 10), (0, 5), False),    # touching from the other side
    ((0, 5), (0, 5), True),      # identical
    ((0, 1), (0, 1), True),      # identical length-1
])
def test_overlaps_geometry(a, b, expected):
    s1 = Span(start=a[0], end=a[1], text="x")
    s2 = Span(start=b[0], end=b[1], text="y")
    assert s1.overlaps(s2) is expected


def test_overlaps_is_symmetric():
    s1 = Span(start=0, end=6, text="x")
    s2 = Span(start=4, end=10, text="y")
    assert s1.overlaps(s2) == s2.overlaps(s1)


def test_overlaps_zero_width_point_inside_range():
    # Documented behavior: a zero-width [3,3) span strictly inside [0,10) is
    # reported as overlapping, because overlaps() is `start < other.end and
    # other.start < end` (3<10 and 0<3). See summary note on this edge case.
    empty = Span(start=3, end=3, text="")
    covering = Span(start=0, end=10, text="x")
    assert empty.overlaps(covering) is True
    assert covering.overlaps(empty) is True


def test_overlaps_zero_width_at_boundary_is_false():
    # A zero-width span sitting exactly on a boundary does not overlap.
    empty = Span(start=0, end=0, text="")
    other = Span(start=0, end=10, text="x")
    assert empty.overlaps(other) is False
    assert other.overlaps(empty) is False


# ----------------------------------------------------------------------------
# Span.iou geometry
# ----------------------------------------------------------------------------

def test_iou_identical_is_one():
    s = Span(start=0, end=10, text="x")
    assert s.iou(Span(start=0, end=10, text="y")) == 1.0


def test_iou_disjoint_is_zero():
    s1 = Span(start=0, end=5, text="x")
    s2 = Span(start=6, end=10, text="y")
    assert s1.iou(s2) == 0.0


def test_iou_touching_boundary_is_zero():
    s1 = Span(start=0, end=5, text="x")
    s2 = Span(start=5, end=10, text="y")
    assert s1.iou(s2) == 0.0


def test_iou_half_overlap_value():
    # [0,10) vs [5,15): inter=5, union=15 -> 1/3
    s1 = Span(start=0, end=10, text="x")
    s2 = Span(start=5, end=15, text="y")
    assert s1.iou(s2) == pytest.approx(5 / 15)


def test_iou_contained_value():
    # [0,10) contains [2,4): inter=2, union=10 -> 0.2
    outer = Span(start=0, end=10, text="x")
    inner = Span(start=2, end=4, text="y")
    assert outer.iou(inner) == pytest.approx(0.2)


def test_iou_is_symmetric():
    s1 = Span(start=0, end=8, text="x")
    s2 = Span(start=3, end=12, text="y")
    assert s1.iou(s2) == pytest.approx(s2.iou(s1))


def test_iou_in_unit_interval():
    s1 = Span(start=1, end=9, text="x")
    s2 = Span(start=4, end=20, text="y")
    v = s1.iou(s2)
    assert 0.0 <= v <= 1.0


def test_iou_both_empty_is_zero():
    # union == 0 -> guarded to 0.0, no ZeroDivisionError
    a = Span(start=3, end=3, text="")
    b = Span(start=3, end=3, text="")
    assert a.iou(b) == 0.0


def test_iou_no_overlap_still_zero_when_far():
    s1 = Span(start=0, end=2, text="x")
    s2 = Span(start=100, end=110, text="y")
    assert s1.iou(s2) == 0.0


# ----------------------------------------------------------------------------
# Span validation (bounds)
# ----------------------------------------------------------------------------

def test_span_negative_start_rejected():
    with pytest.raises(ValidationError):
        Span(start=-1, end=5, text="x")


def test_span_negative_end_rejected():
    with pytest.raises(ValidationError):
        Span(start=0, end=-3, text="x")


def test_span_zero_bounds_allowed():
    s = Span(start=0, end=0, text="")
    assert s.start == 0 and s.end == 0


def test_span_unicode_text_preserved():
    s = Span(start=0, end=3, text="cafe - check ok")
    assert s.text == "cafe - check ok"


# ----------------------------------------------------------------------------
# 0..1 bound validation on scores
# ----------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [-0.01, 1.01, -1.0, 2.0])
def test_grounding_score_out_of_range_rejected(bad):
    with pytest.raises(ValidationError):
        Grounding(score=bad)


@pytest.mark.parametrize("good", [0.0, 0.5, 1.0])
def test_grounding_score_in_range_accepted(good):
    g = Grounding(score=good)
    assert g.score == good


@pytest.mark.parametrize("bad", [-0.5, 1.5])
def test_verdict_match_score_out_of_range_rejected(bad):
    with pytest.raises(ValidationError):
        Verdict(supported=True, reason="r", match_score=bad)


@pytest.mark.parametrize("bad", [-0.1, 1.2])
def test_register_row_confidence_out_of_range_rejected(bad):
    with pytest.raises(ValidationError):
        make_register_row(confidence=bad)


@pytest.mark.parametrize("bad", [-0.1, 1.1])
def test_severity_score_out_of_range_rejected(bad):
    with pytest.raises(ValidationError):
        Severity(tier="high", score=bad, rationale="r")


# ----------------------------------------------------------------------------
# Source enum
# ----------------------------------------------------------------------------

def test_source_enum_values():
    assert Source.INITIAL.value == "initial"
    assert Source.RECOVERY.value == "recovery"


def test_source_enum_membership():
    assert set(s.value for s in Source) == {"initial", "recovery"}


def test_source_is_str_enum():
    assert Source.INITIAL == "initial"


def test_candidate_default_source_is_initial():
    c = Candidate(clause_type="Governing Law", claim="c", quote="q")
    assert c.source == Source.INITIAL


def test_candidate_source_coerced_from_string():
    c = Candidate(clause_type="Governing Law", claim="c", quote="q", source="recovery")
    assert c.source is Source.RECOVERY


def test_candidate_invalid_source_rejected():
    with pytest.raises(ValidationError):
        Candidate(clause_type="X", claim="c", quote="q", source="bogus")


# ----------------------------------------------------------------------------
# Defaults
# ----------------------------------------------------------------------------

def test_register_row_defaults():
    row = make_register_row()
    assert row.abstained is False
    assert row.matches_gold is None
    assert row.severity is None


def test_grounding_defaults():
    g = Grounding(score=0.5)
    assert g.span is None
    assert g.grounded is False


def test_contract_result_defaults():
    cr = ContractResult(contract_id="c1", text_len=100)
    assert cr.split == ""
    assert cr.rows == []
    assert cr.recovered_row_ids == []


def test_metrics_defaults_zeroed():
    m = Metrics(n_contracts=0)
    assert m.recall_single_shot == 0.0
    assert m.recall_post_recovery == 0.0
    assert m.recall_lift == 0.0
    assert m.precision == 0.0
    assert m.fabrication_rate == 0.0
    assert m.per_clause == []
    assert m.pareto == []
    assert m.faults == []


def test_run_config_defaults():
    c = RunConfig(backend="stub", model="m", abstain_threshold=0.5)
    assert c.ground_threshold == 0.85
    assert c.fabrication_floor == 0.6
    assert c.gold_overlap_threshold == 0.5
    assert c.n_contracts == 0
    assert c.notes == ""


# ----------------------------------------------------------------------------
# Serialization roundtrips
# ----------------------------------------------------------------------------

def test_register_row_json_roundtrip():
    row = make_register_row(
        abstained=True,
        matches_gold=True,
        severity=Severity(tier="critical", score=0.9, rationale="big"),
    )
    js = row.model_dump_json()
    back = RegisterRow.model_validate_json(js)
    assert back == row
    assert back.severity.tier == "critical"
    assert back.source is Source.INITIAL


def test_metrics_json_roundtrip():
    m = Metrics(
        n_contracts=3,
        per_clause=[ClauseMetric(
            clause_type="Governing Law", gold_total=2,
            recall_single_shot=0.5, recall_post_recovery=0.75, precision=1.0,
        )],
        recall_single_shot=0.5,
        recall_post_recovery=0.75,
        recall_lift=0.25,
        pareto=[ParetoPoint(threshold=0.5, precision=0.9, recall=0.8, abstention=0.1)],
        faults=[FaultResult(
            name="dropout", description="d", baseline_recall=0.8,
            faulted_recall=0.6, fabrication_rate=0.05, completion=1.0,
        )],
    )
    js = m.model_dump_json()
    back = Metrics.model_validate_json(js)
    assert back == m
    assert back.per_clause[0].clause_type == "Governing Law"
    assert back.faults[0].completion == 1.0


def test_run_report_full_json_roundtrip():
    report = RunReport(
        generated_utc="2026-07-11T00:00:00Z",
        config=RunConfig(backend="stub", model="m", abstain_threshold=0.4),
        metrics=Metrics(n_contracts=1),
        contracts=[ContractResult(
            contract_id="c1", text_len=42, split="test",
            rows=[make_register_row()],
            recovered_row_ids=["r9"],
        )],
    )
    js = report.model_dump_json()
    back = RunReport.model_validate_json(js)
    assert back == report
    assert back.contracts[0].rows[0].row_id == "r1"
    assert back.contracts[0].recovered_row_ids == ["r9"]


def test_span_json_roundtrip():
    s = Span(start=5, end=12, text="hello")
    back = Span.model_validate_json(s.model_dump_json())
    assert back == s


def test_model_dump_roundtrip_via_dict():
    row = make_register_row(matches_gold=False)
    d = row.model_dump()
    back = RegisterRow.model_validate(d)
    assert back == row


# ----------------------------------------------------------------------------
# CLAUSE_TYPES registry
# ----------------------------------------------------------------------------

def test_clause_types_length():
    assert len(CLAUSE_TYPES) == 6


def test_clause_types_unique():
    assert len(set(CLAUSE_TYPES)) == len(CLAUSE_TYPES)


def test_clause_types_expected_contents():
    assert set(CLAUSE_TYPES) == {
        "Renewal Term",
        "Notice Period To Terminate Renewal",
        "Cap On Liability",
        "Liquidated Damages",
        "Post-Termination Services",
        "Governing Law",
    }


def test_clause_types_all_strings():
    assert all(isinstance(c, str) and c for c in CLAUSE_TYPES)
