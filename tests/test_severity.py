"""Tests for clauseledger.severity.score_severity.

The rubric is PROVISIONAL (money-at-risk x time-to-trigger). These tests pin the
public contract: correct tier/score per clause type, [0,1] bounded scores,
the "[provisional]" rationale prefix, the money/time bumps, the unknown-type
default, and the PROVISIONAL flag.
"""
import pytest

from clauseledger.severity import score_severity, PROVISIONAL
from clauseledger.schema import Severity, CLAUSE_TYPES


# (clause_type, expected_tier, expected_base_score) for all 6 scoped types.
BASE_CASES = [
    ("Cap On Liability", "critical", 0.95),
    ("Notice Period To Terminate Renewal", "high", 0.85),
    ("Liquidated Damages", "high", 0.80),
    ("Renewal Term", "medium", 0.55),
    ("Post-Termination Services", "medium", 0.50),
    ("Governing Law", "low", 0.25),
]

NEUTRAL = "some obligation described in plain prose"  # no money token, no digits


# --- tier correctness across all 6 clause types -----------------------------

@pytest.mark.parametrize("ct,tier,_score", BASE_CASES)
def test_tier_per_clause_type(ct, tier, _score):
    assert score_severity(ct, NEUTRAL).tier == tier


@pytest.mark.parametrize("ct,_tier,score", BASE_CASES)
def test_base_score_per_clause_type(ct, _tier, score):
    # neutral claim -> no bump -> exact base score
    assert score_severity(ct, NEUTRAL).score == score


@pytest.mark.parametrize("ct,_tier,_score", BASE_CASES)
def test_returns_severity_instance(ct, _tier, _score):
    assert isinstance(score_severity(ct, NEUTRAL), Severity)


@pytest.mark.parametrize("ct,_tier,_score", BASE_CASES)
def test_score_in_unit_interval(ct, _tier, _score):
    s = score_severity(ct, "payment of $5,000,000 due within 15 days of breach")
    assert 0.0 <= s.score <= 1.0


@pytest.mark.parametrize("ct,_tier,_score", BASE_CASES)
def test_rationale_provisional_prefix(ct, _tier, _score):
    assert score_severity(ct, NEUTRAL).rationale.startswith("[provisional]")


@pytest.mark.parametrize("ct,tier,_score", BASE_CASES)
def test_tier_in_allowed_set(ct, tier, _score):
    assert score_severity(ct, NEUTRAL).tier in {"critical", "high", "medium", "low"}


def test_all_scoped_clause_types_are_known():
    # every clause type in the schema resolves to a non-default rationale
    for ct in CLAUSE_TYPES:
        assert score_severity(ct, NEUTRAL).rationale != "[provisional] unclassified obligation"


# --- unknown clause type default --------------------------------------------

def test_unknown_clause_type_tier_is_medium():
    assert score_severity("Nonexistent Clause", NEUTRAL).tier == "medium"


def test_unknown_clause_type_base_score():
    assert score_severity("Nonexistent Clause", NEUTRAL).score == 0.5


def test_unknown_clause_type_rationale():
    assert score_severity("Nonexistent Clause", NEUTRAL).rationale == "[provisional] unclassified term"


@pytest.mark.parametrize("ct", ["", "governing law", "CAP ON LIABILITY", "Renewal"])
def test_case_sensitive_unknown_defaults_to_medium(ct):
    # lookup is exact/case-sensitive; near-misses fall to the default tier
    assert score_severity(ct, NEUTRAL).tier == "medium"


# --- PROVISIONAL flag -------------------------------------------------------

def test_provisional_flag_true():
    assert PROVISIONAL is True


# --- money bump -------------------------------------------------------------

@pytest.mark.parametrize("money", ["$100,000", "USD 50000", "5 million", "20 percent", "10%", "EUR 900"])
def test_money_token_raises_score(money):
    base = score_severity("Governing Law", NEUTRAL).score
    bumped = score_severity("Governing Law", f"exposure of {money} on default").score
    assert bumped > base


def test_money_bump_is_five_hundredths():
    base = score_severity("Renewal Term", NEUTRAL).score
    bumped = score_severity("Renewal Term", "damages of $1,000 apply").score
    assert bumped == pytest.approx(base + 0.05)


def test_money_bump_caps_at_one():
    # Cap On Liability base is 0.95; +0.05 money bump lands exactly at 1.0, not above.
    s = score_severity("Cap On Liability", "liability capped at $1,000,000")
    assert s.score == 1.0


def test_money_and_time_bumps_cap_at_one():
    # 0.95 + 0.05 + 0.05 would be 1.05; must clamp to 1.0.
    s = score_severity("Cap On Liability", "pay $500,000 within 10 days of the claim")
    assert s.score == 1.0


# --- time bump --------------------------------------------------------------

def test_tight_deadline_raises_score():
    base = score_severity("Renewal Term", NEUTRAL).score
    bumped = score_severity("Renewal Term", "notice must be given within 15 days").score
    assert bumped == pytest.approx(base + 0.05)


def test_deadline_boundary_thirty_days_bumps():
    base = score_severity("Governing Law", NEUTRAL).score
    bumped = score_severity("Governing Law", "cure within 30 days").score
    assert bumped == pytest.approx(base + 0.05)


def test_deadline_thirty_one_days_no_bump():
    base = score_severity("Governing Law", NEUTRAL).score
    same = score_severity("Governing Law", "cure within 31 days").score
    assert same == base


def test_long_deadline_ninety_days_no_bump():
    # mirrors the synthetic contract's "ninety (90) days" notice window
    base = score_severity("Notice Period To Terminate Renewal", NEUTRAL).score
    same = score_severity("Notice Period To Terminate Renewal", "ninety (90) days written notice").score
    assert same == base


def test_word_number_deadline_does_not_bump():
    # spelled-out numbers are not digits; regex needs \d+
    base = score_severity("Renewal Term", NEUTRAL).score
    same = score_severity("Renewal Term", "within thirty days of notice").score
    assert same == base


# --- edge / failure modes ---------------------------------------------------

def test_none_claim_does_not_crash_and_uses_base():
    s = score_severity("Governing Law", None)
    assert s.score == 0.25
    assert s.tier == "low"


def test_empty_claim_uses_base():
    assert score_severity("Cap On Liability", "").score == 0.95


def test_unicode_claim_handled():
    s = score_severity("Liquidated Damages", "penalidade de €50 milhões — sanção imediata")
    assert isinstance(s, Severity)
    assert 0.0 <= s.score <= 1.0


def test_score_is_rounded_to_three_decimals():
    s = score_severity("Renewal Term", NEUTRAL)  # 0.55 stays clean
    assert s.score == round(s.score, 3)


def test_no_money_no_time_leaves_base_untouched():
    for ct, _tier, base in BASE_CASES:
        assert score_severity(ct, "a clause with no figures whatsoever").score == base


def test_critical_is_highest_base_tier():
    scores = {ct: score_severity(ct, NEUTRAL).score for ct, _, _ in BASE_CASES}
    assert scores["Cap On Liability"] == max(scores.values())


def test_governing_law_is_lowest_base():
    scores = {ct: score_severity(ct, NEUTRAL).score for ct, _, _ in BASE_CASES}
    assert scores["Governing Law"] == min(scores.values())


# ---- clause kind (obligation vs allocation vs mechanic) ----
from clauseledger.severity import clause_kind  # noqa: E402


@pytest.mark.parametrize("ct,kind", [
    ("Cap On Liability", "allocation"),
    ("Governing Law", "mechanic"),
    ("Renewal Term", "mechanic"),
    ("Notice Period To Terminate Renewal", "obligation"),
    ("Liquidated Damages", "obligation"),
    ("Post-Termination Services", "obligation"),
])
def test_clause_kind(ct, kind):
    assert clause_kind(ct) == kind


def test_clause_kind_unknown_default():
    assert clause_kind("Whatever") == "mechanic"


def test_not_all_clauses_are_obligations():
    from clauseledger.schema import CLAUSE_TYPES
    kinds = {clause_kind(c) for c in CLAUSE_TYPES}
    assert "allocation" in kinds and "mechanic" in kinds  # the legal-review correction
