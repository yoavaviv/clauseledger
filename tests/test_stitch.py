"""Stitch-fabrication defense (closes README honest-limitation #1).

A stitched quote is assembled from real fragments that never appear contiguously in
the source. Plain fuzzy grounding can score such a quote above the fabrication floor;
the stitch guard reconstructs the quote from verbatim fragments and rejects it when the
pieces come from non-contiguous locations. These tests pin both the catch (stitches are
flagged and never grounded) and the safety property (genuine quotes are never flagged).
"""
from __future__ import annotations

import pytest

from clauseledger.ground import detect_stitch, ground_quote
from clauseledger.schema import Candidate
from clauseledger.verify import verify_candidate

# A contract with two clauses far apart in the text, so a stitch across them is
# genuinely non-contiguous in the source.
FILLER = "The parties shall cooperate in good faith to give effect to this Agreement. "
CONTRACT = (
    "Section 8. INDEMNIFICATION. The Vendor shall indemnify and hold harmless the Customer "
    "from any and all claims arising out of the Vendor's gross negligence or willful "
    "misconduct in the performance of the Services under this Agreement. "
    + FILLER * 6 +
    "Section 14. GOVERNING LAW. This Agreement shall be governed by and construed in "
    "accordance with the laws of the State of Delaware, without regard to its conflict of "
    "laws principles or any other choice of law rule."
)

GENUINE = ("The Vendor shall indemnify and hold harmless the Customer from any and all "
           "claims arising out of the Vendor's gross negligence")
# real head from the indemnity clause + real tail from the governing-law clause
STITCH = ("The Vendor shall indemnify and hold harmless the Customer laws of the State of "
          "Delaware, without regard to its conflict of laws principles")


def test_genuine_contiguous_quote_grounds_and_is_not_stitched():
    g = ground_quote(GENUINE, CONTRACT)
    assert g.grounded is True
    assert g.stitched is False
    assert g.stitch_fragments == []
    assert detect_stitch(GENUINE, CONTRACT) is None


def test_stitched_quote_is_detected():
    ev = detect_stitch(STITCH, CONTRACT)
    assert ev is not None
    assert len(ev.fragments) >= 2
    assert ev.coverage >= 0.8


def test_stitched_quote_is_never_grounded():
    g = ground_quote(STITCH, CONTRACT)
    assert g.grounded is False
    assert g.stitched is True
    assert len(g.stitch_fragments) >= 2


def test_verifier_rejects_stitch_with_stitch_reason():
    _g, verdict, _conf = verify_candidate(
        Candidate(clause_type="Governing Law", claim="x", quote=STITCH), CONTRACT)
    assert verdict.supported is False
    assert "stitched" in verdict.reason.lower()


def test_short_quote_is_never_flagged_as_stitch():
    # too short to be a plausible stitch, even if it is not a substring
    assert detect_stitch("laws of Delaware", CONTRACT) is None


def test_benign_fuzzy_noise_is_not_a_stitch():
    # contiguous quote with case/whitespace changes: normalized-exact, not a stitch
    noisy = ("this   agreement shall be GOVERNED by and construed in accordance with the "
             "laws of the state of delaware")
    g = ground_quote(noisy, CONTRACT)
    assert g.stitched is False
    assert g.grounded is True


def test_contiguous_quote_with_small_omission_is_not_flagged():
    # dropping a short middle phrase keeps the fragments adjacent (< gap slack): benign
    src = "the Vendor shall pay a fee of one thousand dollars within thirty days of invoice"
    text = "Article 2. FEES. " + src + ". " + FILLER * 3
    quote = "the Vendor shall pay a fee of one thousand dollars of invoice"  # dropped 'within thirty days'
    assert detect_stitch(quote, text) is None


def test_fully_fabricated_quote_is_not_a_stitch():
    # invented text with no real fragments is caught by ordinary grounding, not the stitch path
    fake = ("The Supplier hereby waives all statutory warranties and assigns its intellectual "
            "property to the Buyer in perpetuity across every jurisdiction on Earth")
    g = ground_quote(fake, CONTRACT)
    assert g.grounded is False
    assert g.stitched is False


def test_detect_stitch_empty_and_degenerate_inputs():
    assert detect_stitch("", CONTRACT) is None
    assert detect_stitch(STITCH, "") is None
    assert detect_stitch("   ", CONTRACT) is None


@pytest.mark.parametrize("gap_words", [0, 2])
def test_adjacent_fragments_in_order_are_contiguous(gap_words):
    # two long real fragments that ARE adjacent must not be misread as a stitch
    text = ("The Licensee shall maintain insurance of not less than five million dollars "
            "throughout the term and for two years thereafter as required by this Agreement. "
            + FILLER * 2)
    quote = "The Licensee shall maintain insurance of not less than five million dollars"
    assert detect_stitch(quote, text) is None


# --- adversarial measurement harness (on the real CUAD subset) --------------- #

def _defense():
    from clauseledger.adversarial import evaluate_stitch_defense
    from clauseledger.cuad import load_subset
    return evaluate_stitch_defense(load_subset().contracts)


def test_stitch_defense_injects_and_catches_all():
    m = _defense()
    assert m.injected >= 50
    assert m.caught == m.injected            # every stitch is refused grounding
    assert m.catch_rate == 1.0


def test_stitch_defense_closes_a_real_hole():
    # the whole point: without the guard, fuzzy grounding would ASSERT many stitches as
    # real obligations, and would count NONE of them as fabrication.
    m = _defense()
    assert m.would_assert_without_guard > 0
    assert m.attributed_fabrication == m.injected
    assert m.attributed_baseline < m.attributed_fabrication


def test_stitch_defense_has_zero_false_positives_on_real_gold():
    # the safety property: genuine gold quotes are never flagged as stitched
    m = _defense()
    assert m.genuine_checked >= 50
    assert m.false_positives == 0
    assert m.false_positive_rate == 0.0


def test_stitch_defense_is_deterministic():
    a, b = _defense(), _defense()
    assert a.model_dump() == b.model_dump()
