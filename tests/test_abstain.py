"""Tests for clauseledger.abstain: apply_abstention and calibrate_threshold.

The abstention gate turns a supported-but-low-confidence row into a "human-SME needed"
row instead of an asserted fact. Unsupported rows are a separate (rejected) state and are
never marked abstained. calibrate_threshold picks the lowest dev-split threshold whose
asserted rows reach a target precision.
"""
import pytest

from clauseledger.abstain import apply_abstention, calibrate_threshold
from clauseledger.schema import Grounding, RegisterRow, Source, Span, Verdict


DEFAULT_GRID = [i / 20 for i in range(0, 21)]


def make_row(row_id="r", *, supported=True, confidence=0.5, matches_gold=None,
             clause_type="Governing Law", quote="q", source=Source.INITIAL):
    span = Span(start=0, end=len(quote), text=quote)
    grounding = Grounding(span=span, score=1.0, grounded=True)
    verdict = Verdict(supported=supported, reason="because",
                      match_score=1.0 if supported else 0.0)
    return RegisterRow(
        row_id=row_id, clause_type=clause_type, claim="a claim",
        quote=quote, grounding=grounding, verdict=verdict,
        source=source, confidence=confidence, matches_gold=matches_gold,
    )


# --------------------------------------------------------------------------
# apply_abstention
# --------------------------------------------------------------------------

def test_supported_low_confidence_is_abstained():
    row = make_row(supported=True, confidence=0.2)
    apply_abstention([row], threshold=0.5)
    assert row.abstained is True


def test_supported_high_confidence_not_abstained():
    row = make_row(supported=True, confidence=0.9)
    apply_abstention([row], threshold=0.5)
    assert row.abstained is False


def test_supported_confidence_equal_threshold_not_abstained():
    # confidence >= threshold means asserted; boundary uses strict `<`.
    row = make_row(supported=True, confidence=0.5)
    apply_abstention([row], threshold=0.5)
    assert row.abstained is False


@pytest.mark.parametrize("confidence", [0.0, 0.1, 0.5, 0.9, 1.0])
def test_unsupported_never_abstained(confidence):
    # Unsupported rows are rejected, a distinct state: abstained must stay False
    # regardless of confidence or threshold.
    row = make_row(supported=False, confidence=confidence)
    apply_abstention([row], threshold=0.99)
    assert row.abstained is False


@pytest.mark.parametrize("threshold", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_unsupported_false_across_all_thresholds(threshold):
    row = make_row(supported=False, confidence=0.0)
    apply_abstention([row], threshold=threshold)
    assert row.abstained is False


@pytest.mark.parametrize("threshold", [0.0, 0.2, 0.4, 0.6, 0.8, 1.0])
def test_supported_matches_strict_less_than_rule(threshold):
    conf = 0.5
    row = make_row(supported=True, confidence=conf)
    apply_abstention([row], threshold=threshold)
    assert row.abstained == (conf < threshold)


def test_threshold_zero_never_abstains_supported():
    # No confidence can be < 0.0, so nothing abstains at threshold 0.0.
    rows = [make_row(row_id=f"r{i}", supported=True, confidence=c)
            for i, c in enumerate([0.0, 0.3, 1.0])]
    apply_abstention(rows, threshold=0.0)
    assert all(r.abstained is False for r in rows)


def test_threshold_one_abstains_all_below_one():
    below = make_row(row_id="a", supported=True, confidence=0.99)
    at_one = make_row(row_id="b", supported=True, confidence=1.0)
    apply_abstention([below, at_one], threshold=1.0)
    assert below.abstained is True
    assert at_one.abstained is False


def test_monotonic_abstained_count_non_decreasing():
    confidences = [0.05, 0.2, 0.4, 0.55, 0.7, 0.85, 0.95]
    rows = [make_row(row_id=f"r{i}", supported=True, confidence=c)
            for i, c in enumerate(confidences)]
    prev = -1
    for t in DEFAULT_GRID:
        apply_abstention(rows, threshold=t)
        count = sum(1 for r in rows if r.abstained)
        assert count >= prev, f"abstention count dropped at threshold {t}"
        prev = count
    # At threshold 1.0 every supported row with confidence < 1 is abstained.
    assert prev == len(rows)


def test_returns_none_and_mutates_in_place():
    row = make_row(supported=True, confidence=0.1)
    result = apply_abstention([row], threshold=0.5)
    assert result is None
    assert row.abstained is True


def test_mutates_same_object_identity():
    row = make_row(supported=True, confidence=0.1)
    rows = [row]
    apply_abstention(rows, threshold=0.5)
    assert rows[0] is row
    assert rows[0].abstained is True


def test_empty_list_is_noop():
    # Must not raise on an empty register.
    assert apply_abstention([], threshold=0.5) is None


def test_mixed_rows_updated_independently():
    low = make_row(row_id="low", supported=True, confidence=0.1)
    high = make_row(row_id="high", supported=True, confidence=0.9)
    rejected = make_row(row_id="rej", supported=False, confidence=0.1)
    apply_abstention([low, high, rejected], threshold=0.5)
    assert low.abstained is True
    assert high.abstained is False
    assert rejected.abstained is False


def test_reapplying_overwrites_previous_abstained():
    row = make_row(supported=True, confidence=0.4)
    apply_abstention([row], threshold=0.9)
    assert row.abstained is True
    # Re-run with a lower threshold: the flag must be recomputed, not sticky.
    apply_abstention([row], threshold=0.1)
    assert row.abstained is False


def test_unicode_quote_does_not_break_abstention():
    row = make_row(supported=True, confidence=0.2, quote="clause §1.2 – café \U0001f4c4")
    apply_abstention([row], threshold=0.6)
    assert row.abstained is True


# --------------------------------------------------------------------------
# calibrate_threshold
# --------------------------------------------------------------------------

def test_all_correct_returns_lowest_threshold():
    rows = [make_row(row_id=f"r{i}", supported=True, confidence=c, matches_gold=True)
            for i, c in enumerate([0.1, 0.5, 0.9])]
    assert calibrate_threshold(rows, target_precision=0.9) == 0.0


def test_empty_dev_returns_highest_grid_value():
    # No asserted rows at any threshold -> falls through to grid[-1].
    assert calibrate_threshold([], target_precision=0.9) == DEFAULT_GRID[-1]
    assert calibrate_threshold([]) == 1.0


def test_return_value_in_unit_interval():
    rows = [make_row(supported=True, confidence=0.7, matches_gold=True)]
    t = calibrate_threshold(rows)
    assert 0.0 <= t <= 1.0


def test_return_value_is_a_grid_member():
    rows = [
        make_row(row_id="a", supported=True, confidence=0.3, matches_gold=False),
        make_row(row_id="b", supported=True, confidence=0.9, matches_gold=True),
    ]
    t = calibrate_threshold(rows, target_precision=0.9)
    assert t in DEFAULT_GRID


def test_respects_target_precision_pushes_threshold_up():
    # A wrong low-confidence asserted row drags precision below target at t=0,
    # so the calibrator must climb past it.
    rows = [
        make_row(row_id="wrong", supported=True, confidence=0.3, matches_gold=False),
        make_row(row_id="right", supported=True, confidence=0.9, matches_gold=True),
    ]
    t = calibrate_threshold(rows, target_precision=0.9)
    # Smallest grid value that excludes the 0.3 row is 0.35.
    assert t == 0.35
    # And that threshold indeed yields precision >= target.
    asserted = [r for r in rows if r.verdict.supported and r.confidence >= t]
    prec = sum(1 for r in asserted if r.matches_gold) / len(asserted)
    assert prec >= 0.9


def test_lower_target_precision_accepts_lower_threshold():
    rows = [
        make_row(row_id="wrong", supported=True, confidence=0.3, matches_gold=False),
        make_row(row_id="right", supported=True, confidence=0.9, matches_gold=True),
    ]
    high = calibrate_threshold(rows, target_precision=0.9)
    low = calibrate_threshold(rows, target_precision=0.5)
    assert low <= high
    assert low == 0.0  # 50% precision already met by both rows at t=0


@pytest.mark.parametrize("target,expected", [
    (0.5, 0.0),
    (0.9, 0.35),
    (1.0, 0.35),
])
def test_target_precision_grid_mapping(target, expected):
    rows = [
        make_row(row_id="wrong", supported=True, confidence=0.3, matches_gold=False),
        make_row(row_id="right", supported=True, confidence=0.9, matches_gold=True),
    ]
    assert calibrate_threshold(rows, target_precision=target) == expected


def test_no_threshold_reaches_target_returns_last_grid_value():
    # Every asserted row is wrong -> target never met -> grid[-1].
    rows = [
        make_row(row_id="a", supported=True, confidence=0.3, matches_gold=False),
        make_row(row_id="b", supported=True, confidence=0.9, matches_gold=False),
    ]
    assert calibrate_threshold(rows, target_precision=0.9) == DEFAULT_GRID[-1]


def test_all_unsupported_returns_last_grid_value():
    # No supported rows means no asserted rows at any threshold.
    rows = [make_row(row_id=f"r{i}", supported=False, confidence=0.9, matches_gold=True)
            for i in range(3)]
    assert calibrate_threshold(rows, target_precision=0.9) == DEFAULT_GRID[-1]


def test_custom_grid_returns_value_from_that_grid():
    rows = [
        make_row(row_id="wrong", supported=True, confidence=0.3, matches_gold=False),
        make_row(row_id="right", supported=True, confidence=0.9, matches_gold=True),
    ]
    grid = [0.0, 0.5, 1.0]
    t = calibrate_threshold(rows, target_precision=0.9, grid=grid)
    assert t in grid
    # 0.0 fails (prec .5), 0.5 excludes the wrong row (prec 1.0) -> 0.5.
    assert t == 0.5


def test_single_value_grid_returns_that_value():
    rows = [make_row(supported=True, confidence=0.9, matches_gold=False)]
    # Only threshold 0.7; asserted row is wrong so target unmet -> grid[-1] == 0.7.
    assert calibrate_threshold(rows, target_precision=0.9, grid=[0.7]) == 0.7


def test_matches_gold_none_counts_as_not_matching():
    # Unset matches_gold is falsy: precision reads 0, target unmet.
    rows = [make_row(supported=True, confidence=0.9, matches_gold=None)]
    assert calibrate_threshold(rows, target_precision=0.9) == DEFAULT_GRID[-1]


def test_default_target_precision_is_ninety_percent():
    # One correct + one wrong at conf 0.5 -> precision 0.5 < 0.9 default at t<=0.5.
    rows = [
        make_row(row_id="wrong", supported=True, confidence=0.4, matches_gold=False),
        make_row(row_id="right", supported=True, confidence=0.8, matches_gold=True),
    ]
    # Default (0.9) must climb above 0.4; explicit 0.5 should stay at 0.0.
    assert calibrate_threshold(rows) > 0.0
    assert calibrate_threshold(rows, target_precision=0.5) == 0.0


def test_calibrated_threshold_gates_downstream_abstention():
    # End-to-end: calibrate on dev, then apply on a fresh row and check the gate.
    dev = [
        make_row(row_id="wrong", supported=True, confidence=0.3, matches_gold=False),
        make_row(row_id="right", supported=True, confidence=0.9, matches_gold=True),
    ]
    t = calibrate_threshold(dev, target_precision=0.9)  # 0.35
    low = make_row(row_id="new_low", supported=True, confidence=0.3)
    high = make_row(row_id="new_high", supported=True, confidence=0.6)
    apply_abstention([low, high], threshold=t)
    assert low.abstained is True
    assert high.abstained is False
