"""Tests for clauseledger.verify.verify_candidate.

The verifier is the trust primitive's ruling layer: given a Candidate's cited
quote and the raw contract text it grounds the quote and returns
(Grounding, Verdict, confidence). These tests pin the invariants the rest of the
pipeline (and the abstention gate) rely on:

  * a real gold quote -> supported, confidence ~ 1.0
  * an invented quote -> not supported, low confidence, "fabrication" in reason
  * confidence always in [0, 1] and equal to round(grounding.score, 4)
  * verdict.match_score == confidence, verdict.supported == grounding.grounded
  * the ground_threshold parameter only gates the fuzzy path
"""
import pytest

from clauseledger.verify import verify_candidate
from clauseledger.schema import Candidate, Grounding, Verdict, Source


# Clause types in syn_gold that carry at least one real span.
GOLD_TYPES = [
    "Governing Law",
    "Renewal Term",
    "Notice Period To Terminate Renewal",
    "Cap On Liability",
    "Post-Termination Services",
]

# Alien quotes with no long verbatim run shared with SYN_TEXT -> should be rejected.
INVENTED = [
    "Employee shall receive stock options vesting over a four year schedule.",
    "The pizza delivery must arrive within thirty minutes or the meal is free.",
    "Refunds are processed via carrier pigeon on alternate Tuesdays only.",
    "Quarterly bonuses accrue to shareholders of the holding subsidiary.",
]


def _cand(clause_type, quote, claim=None, source=Source.INITIAL):
    return Candidate(
        clause_type=clause_type,
        claim=claim or f"{clause_type} obligation",
        quote=quote,
        source=source,
    )


def _gold_quote(syn_gold, clause_type):
    return syn_gold[clause_type][0].text


# --------------------------------------------------------------------------
# Supported path: a real gold quote must be verified as supported.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("clause_type", GOLD_TYPES)
def test_gold_quote_is_supported(syn_text, syn_gold, clause_type):
    quote = _gold_quote(syn_gold, clause_type)
    g, verdict, confidence = verify_candidate(_cand(clause_type, quote), syn_text)
    assert verdict.supported is True
    assert g.grounded is True


@pytest.mark.parametrize("clause_type", GOLD_TYPES)
def test_gold_quote_confidence_is_one(syn_text, syn_gold, clause_type):
    # Every gold span is a verbatim substring, so the exact-substring path fires
    # and score is exactly 1.0.
    quote = _gold_quote(syn_gold, clause_type)
    _, _, confidence = verify_candidate(_cand(clause_type, quote), syn_text)
    assert confidence == pytest.approx(1.0)


@pytest.mark.parametrize("clause_type", GOLD_TYPES)
def test_gold_quote_span_matches_text(syn_text, syn_gold, clause_type):
    quote = _gold_quote(syn_gold, clause_type)
    g, _, _ = verify_candidate(_cand(clause_type, quote), syn_text)
    assert g.span is not None
    assert syn_text[g.span.start:g.span.end] == quote


@pytest.mark.parametrize("clause_type", GOLD_TYPES)
def test_supported_reason_mentions_located(syn_text, syn_gold, clause_type):
    quote = _gold_quote(syn_gold, clause_type)
    _, verdict, _ = verify_candidate(_cand(clause_type, quote), syn_text)
    assert "located" in verdict.reason.lower()
    assert "fabrication" not in verdict.reason.lower()


# --------------------------------------------------------------------------
# Fabrication path: an invented quote must be rejected as unsupported.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("quote", INVENTED)
def test_invented_quote_not_supported(syn_text, quote):
    g, verdict, confidence = verify_candidate(_cand("Governing Law", quote), syn_text)
    assert verdict.supported is False
    assert g.grounded is False


@pytest.mark.parametrize("quote", INVENTED)
def test_invented_quote_low_confidence(syn_text, quote):
    # Unsupported means score fell below the default ground threshold (0.85).
    _, _, confidence = verify_candidate(_cand("Governing Law", quote), syn_text)
    assert confidence < 0.85


@pytest.mark.parametrize("quote", INVENTED)
def test_invented_quote_reason_says_fabrication(syn_text, quote):
    _, verdict, _ = verify_candidate(_cand("Governing Law", quote), syn_text)
    assert "fabrication" in verdict.reason.lower()
    assert "not found" in verdict.reason.lower()


# --------------------------------------------------------------------------
# Return shape and type contract.
# --------------------------------------------------------------------------

def test_return_is_three_tuple(syn_text, syn_gold):
    result = verify_candidate(_cand("Governing Law", _gold_quote(syn_gold, "Governing Law")), syn_text)
    assert isinstance(result, tuple)
    assert len(result) == 3


def test_return_types(syn_text, syn_gold):
    g, verdict, confidence = verify_candidate(
        _cand("Governing Law", _gold_quote(syn_gold, "Governing Law")), syn_text)
    assert isinstance(g, Grounding)
    assert isinstance(verdict, Verdict)
    assert isinstance(confidence, float)


@pytest.mark.parametrize("quote", [
    "governed by the laws of the State of Delaware",  # gold
    "totally invented obligation about spaceships",   # fabrication
    "",                                               # empty
])
def test_confidence_in_unit_interval(syn_text, quote):
    _, _, confidence = verify_candidate(_cand("Governing Law", quote), syn_text)
    assert 0.0 <= confidence <= 1.0


# --------------------------------------------------------------------------
# Cross-field consistency invariants.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("quote", [
    "governed by the laws of the State of Delaware",
    "continue to provide transition services",
    "invented clause not present anywhere at all",
    "",
])
def test_match_score_equals_confidence(syn_text, quote):
    g, verdict, confidence = verify_candidate(_cand("Governing Law", quote), syn_text)
    assert verdict.match_score == confidence


@pytest.mark.parametrize("quote", [
    "governed by the laws of the State of Delaware",
    "ninety (90) days written notice",
    "invented clause not present anywhere at all",
])
def test_match_score_is_rounded_score(syn_text, quote):
    g, verdict, _ = verify_candidate(_cand("Governing Law", quote), syn_text)
    assert verdict.match_score == round(g.score, 4)


@pytest.mark.parametrize("quote", [
    "governed by the laws of the State of Delaware",
    "invented clause not present anywhere at all",
    "",
])
def test_supported_tracks_grounded(syn_text, quote):
    g, verdict, _ = verify_candidate(_cand("Governing Law", quote), syn_text)
    assert verdict.supported == g.grounded


@pytest.mark.parametrize("quote", INVENTED + [_ for _ in ["governed by the laws of the State of Delaware"]])
def test_confidence_at_most_four_decimals(syn_text, quote):
    _, _, confidence = verify_candidate(_cand("Governing Law", quote), syn_text)
    assert confidence == round(confidence, 4)


# --------------------------------------------------------------------------
# Normalization: case / whitespace variants of a real quote still ground.
# --------------------------------------------------------------------------

def test_uppercase_gold_quote_still_supported(syn_text, syn_gold):
    quote = _gold_quote(syn_gold, "Governing Law").upper()
    g, verdict, confidence = verify_candidate(_cand("Governing Law", quote), syn_text)
    assert verdict.supported is True
    # normalized (case-insensitive) match path yields 0.99, not an exact 1.0.
    assert confidence == pytest.approx(0.99)


def test_whitespace_collapsed_gold_quote_supported(syn_text, syn_gold):
    base = _gold_quote(syn_gold, "Renewal Term")
    quote = base.replace(" ", "   ")  # extra internal whitespace
    g, verdict, _ = verify_candidate(_cand("Renewal Term", quote), syn_text)
    assert verdict.supported is True


def test_surrounding_whitespace_is_stripped(syn_text, syn_gold):
    base = _gold_quote(syn_gold, "Governing Law")
    quote = "   \n\t" + base + "  \n"
    g, verdict, confidence = verify_candidate(_cand("Governing Law", quote), syn_text)
    # After stripping it is an exact substring -> score 1.0.
    assert verdict.supported is True
    assert confidence == pytest.approx(1.0)


# --------------------------------------------------------------------------
# Empty / degenerate quotes.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("quote", ["", "   ", "\n\t  \n"])
def test_empty_or_blank_quote_unsupported(syn_text, quote):
    g, verdict, confidence = verify_candidate(_cand("Governing Law", quote), syn_text)
    assert verdict.supported is False
    assert confidence == 0.0
    assert g.span is None
    assert "fabrication" in verdict.reason.lower()


# --------------------------------------------------------------------------
# Unicode: a quote of non-ASCII text absent from the contract is a fabrication.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("quote", [
    "obligación de indemnización perpetua 你好世界",
    "résiliation immédiate sans préavis ni indemnité",
    "契約は日本の法律に準拠するものとする",
])
def test_unicode_absent_quote_is_fabrication(syn_text, quote):
    _, verdict, confidence = verify_candidate(_cand("Governing Law", quote), syn_text)
    assert verdict.supported is False
    assert confidence < 0.85


# --------------------------------------------------------------------------
# ground_threshold parameter: only gates the fuzzy path, and does so monotonically.
# --------------------------------------------------------------------------

def test_exact_substring_ignores_high_threshold(syn_text, syn_gold):
    # Exact-substring hits score 1.0 and are grounded regardless of threshold,
    # even a threshold above 1.0.
    quote = _gold_quote(syn_gold, "Governing Law")
    _, verdict, _ = verify_candidate(_cand("Governing Law", quote), syn_text, ground_threshold=1.5)
    assert verdict.supported is True


def test_threshold_monotonic_on_fuzzy_quote(syn_text):
    # A quote with internal typos avoids both exact and normalized paths and lands
    # in the fuzzy path, where the threshold actually bites.
    quote = "governed by the laws of teh Stat of Delawaer"
    # measure the fuzzy score with a permissive threshold
    _, _, score = verify_candidate(_cand("Governing Law", quote), syn_text, ground_threshold=0.0)
    assert 0.0 < score < 1.0, f"expected a strictly-fuzzy score, got {score}"

    lo = max(0.0, score - 0.02)
    hi = score + 0.02

    _, v_lo, _ = verify_candidate(_cand("Governing Law", quote), syn_text, ground_threshold=lo)
    _, v_hi, _ = verify_candidate(_cand("Governing Law", quote), syn_text, ground_threshold=hi)
    assert v_lo.supported is True, "threshold below the score should ground it"
    assert v_hi.supported is False, "threshold above the score should reject it"


def test_threshold_does_not_change_score(syn_text):
    quote = "governed by the laws of teh Stat of Delawaer"
    _, _, c_lo = verify_candidate(_cand("Governing Law", quote), syn_text, ground_threshold=0.1)
    _, _, c_hi = verify_candidate(_cand("Governing Law", quote), syn_text, ground_threshold=0.99)
    # The threshold flips grounded/supported but never the underlying match score.
    assert c_lo == c_hi


def test_default_threshold_is_085(syn_text, syn_gold):
    # Calling with no threshold behaves identically to passing 0.85 explicitly.
    quote = _gold_quote(syn_gold, "Cap On Liability")
    a = verify_candidate(_cand("Cap On Liability", quote), syn_text)
    b = verify_candidate(_cand("Cap On Liability", quote), syn_text, ground_threshold=0.85)
    assert (a[1].supported, a[2]) == (b[1].supported, b[2])


# --------------------------------------------------------------------------
# Source does not influence the ruling (verifier is source-agnostic).
# --------------------------------------------------------------------------

@pytest.mark.parametrize("source", [Source.INITIAL, Source.RECOVERY])
def test_source_does_not_affect_verdict(syn_text, syn_gold, source):
    quote = _gold_quote(syn_gold, "Governing Law")
    _, verdict, confidence = verify_candidate(
        _cand("Governing Law", quote, source=source), syn_text)
    assert verdict.supported is True
    assert confidence == pytest.approx(1.0)


# --------------------------------------------------------------------------
# Integration: a real CUAD contract quote grounds against its own text.
# --------------------------------------------------------------------------

def test_real_subset_self_quote_supported(real_subset):
    # Take a real gold span from the loaded subset and verify it against its
    # own contract text: it must be supported with high confidence.
    picked = None
    for contract in real_subset.contracts:
        for ct, spans in contract.gold.items():
            for sp in spans:
                if sp.text.strip():
                    picked = (contract, ct, sp)
                    break
            if picked:
                break
        if picked:
            break
    if picked is None:
        pytest.skip("no non-empty gold span available in the real subset")
    contract, ct, sp = picked
    _, verdict, confidence = verify_candidate(_cand(ct, sp.text), contract.text)
    assert verdict.supported is True
    assert confidence >= 0.85
