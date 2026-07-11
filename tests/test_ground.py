"""Tests for clauseledger.ground.ground_quote.

Grounding is the trust primitive: given a model-cited `quote` and the contract
`text`, decide whether the quote is actually in the document and where. We assert
the four documented strategies (exact substring -> case/whitespace-insensitive
exact -> fuzzy alignment -> reject), the score/grounded contract, span-offset
correctness, and the fabrication-rejection behaviour that the verifier relies on.
"""
import re

import pytest

from clauseledger.ground import ground_quote
from clauseledger.schema import Grounding


# ---------------------------------------------------------------------------
# Local texts (independent of fixtures, so bounds/unicode cases are explicit)
# ---------------------------------------------------------------------------

GOLD_QUOTES = [
    "governed by the laws of the State of Delaware",
    "automatically renew for successive one-year periods",
    "ninety (90) days written notice",
    "total liability of either party exceed the fees paid",
    "continue to provide transition services",
]

ABSENT_QUOTES = [
    "Neptune frozen methane oceans swallowed the derelict cargo hauler",
    "photosynthesis converts sunlight into chemical energy within chloroplasts",
    "the quick brown fox jumps over the lazy sleeping dog by the river",
    "quantum chromodynamics predicts the confinement of colored quarks",
    "a recipe for sourdough bread requires flour water salt and patience",
    "migratory albatrosses circumnavigate the southern ocean each winter",
]


# ---------------------------------------------------------------------------
# 1) Exact substring -> score 1.0, correct offsets, grounded True
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("quote", GOLD_QUOTES)
def test_exact_substring_score_one_and_grounded(syn_text, quote):
    g = ground_quote(quote, syn_text)
    assert isinstance(g, Grounding)
    assert g.score == 1.0
    assert g.grounded is True
    assert g.span is not None


@pytest.mark.parametrize("quote", GOLD_QUOTES)
def test_exact_substring_offsets_correct(syn_text, quote):
    g = ground_quote(quote, syn_text)
    expected = syn_text.find(quote)
    assert g.span.start == expected
    assert g.span.end == expected + len(quote)
    assert syn_text[g.span.start:g.span.end] == quote
    assert g.span.text == quote


def test_exact_first_occurrence_is_chosen():
    text = "alpha beta gamma alpha beta gamma"
    g = ground_quote("alpha beta", text)
    assert g.span.start == 0
    assert g.span.end == len("alpha beta")
    assert g.score == 1.0


# ---------------------------------------------------------------------------
# 2) Case-insensitive path -> score 0.99, span recovers original-case text
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("transform", [str.upper, str.lower, str.title])
def test_case_insensitive_path_grounds(syn_text, transform):
    quote = transform("governed by the laws of the State of Delaware")
    # ensure the transformed quote is NOT a verbatim substring (forces path 2)
    if syn_text.find(quote) != -1:
        pytest.skip("transform happened to be exact substring")
    g = ground_quote(quote, syn_text)
    assert g.grounded is True
    assert g.score == pytest.approx(0.99)
    # span points at the ORIGINAL-case text, not the quote's case
    assert g.span.text == syn_text[g.span.start:g.span.end]
    assert g.span.text.lower() == quote.lower()


def test_case_insensitive_span_offsets_land_on_original(syn_text):
    original = "total liability of either party exceed the fees paid"
    g = ground_quote(original.upper(), syn_text)
    assert syn_text[g.span.start:g.span.end] == original
    assert g.span.text == original


# ---------------------------------------------------------------------------
# 3) Whitespace-insensitive path -> offsets correct, span recovers original ws
# ---------------------------------------------------------------------------

def test_whitespace_insensitive_path_grounds(syn_text):
    base = "ninety (90) days written notice"
    # expand each single space into a run; also inject a tab
    noisy = re.sub(r" ", "   ", base).replace("(90)", "(90)\t")
    assert syn_text.find(noisy) == -1
    g = ground_quote(noisy, syn_text)
    assert g.grounded is True
    assert g.score == pytest.approx(0.99)
    # the recovered span text, once whitespace-normalized, equals the base quote
    assert re.sub(r"\s+", " ", g.span.text).strip() == base
    assert syn_text[g.span.start:g.span.end] == g.span.text


def test_leading_whitespace_text_offsets_correct():
    # Text with heavy leading + interior whitespace; the index map must not drift.
    text = "   \n\t  The  Provider   shall   indemnify   the  Client   fully.  "
    quote = "Provider shall indemnify the Client"
    assert text.find(quote) == -1  # not verbatim (extra spaces)
    g = ground_quote(quote, text)
    assert g.grounded is True
    assert g.span is not None
    # offsets index the ORIGINAL text and recover the covered slice exactly
    assert text[g.span.start:g.span.end] == g.span.text
    assert re.sub(r"\s+", " ", g.span.text).strip() == quote
    # start must land on the 'P' of Provider, not at position 0 (the leading ws)
    assert text[g.span.start] == "P"


def test_whitespace_path_end_offset_within_bounds_at_text_end():
    text = "Clause tail:   transition   services"
    quote = "transition services"
    g = ground_quote(quote, text)
    assert g.grounded is True
    assert g.span.end <= len(text)
    assert text[g.span.start:g.span.end] == g.span.text


# ---------------------------------------------------------------------------
# 4) Fuzzy near-miss -> a span is returned; grounded depends on threshold
# ---------------------------------------------------------------------------

def test_fuzzy_near_miss_returns_span_with_partial_score(syn_text):
    # typo ("Delware") defeats exact + normalized-exact, leaving fuzzy alignment
    quote = "governed by the laws of the State of Delware"
    assert syn_text.find(quote) == -1
    g = ground_quote(quote, syn_text)
    assert g.span is not None
    assert 0.0 < g.score < 1.0
    assert syn_text[g.span.start:g.span.end] == g.span.text


def test_threshold_controls_grounded_flag_not_span(syn_text):
    quote = "governed by the laws of the State of Delware"  # fuzzy-only match
    lax = ground_quote(quote, syn_text, threshold=0.0)
    strict = ground_quote(quote, syn_text, threshold=2.0)  # unreachable score
    # same located span regardless of threshold
    assert lax.span == strict.span
    assert lax.score == strict.score
    # only the grounded verdict moves
    assert lax.grounded is True
    assert strict.grounded is False


def test_grounded_flag_is_score_ge_threshold(syn_text):
    quote = "governed by the laws of the State of Delware"
    g0 = ground_quote(quote, syn_text)  # natural fuzzy score
    s = g0.score
    assert 0.0 < s < 1.0
    at = ground_quote(quote, syn_text, threshold=s)
    above = ground_quote(quote, syn_text, threshold=min(s + 0.01, 1.0))
    assert at.grounded is True   # grounded iff score >= threshold
    assert above.grounded is False


# ---------------------------------------------------------------------------
# 5) Fabrication rejection -> genuinely-absent quotes are not grounded
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("quote", ABSENT_QUOTES)
def test_absent_quote_not_grounded(syn_text, quote):
    g = ground_quote(quote, syn_text)
    assert g.grounded is False
    assert g.score < 0.85  # below the default threshold


@pytest.mark.parametrize("quote", ABSENT_QUOTES)
def test_absent_quote_score_in_unit_interval(syn_text, quote):
    g = ground_quote(quote, syn_text)
    assert 0.0 <= g.score <= 1.0


def test_fabrication_against_empty_text_never_grounds():
    g = ground_quote("any obligation whatsoever appears here", "")
    assert g.grounded is False
    assert g.span is None or g.span.text == ""


# ---------------------------------------------------------------------------
# 6) Empty / whitespace-only / None quote -> hard reject
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("quote", ["", "   ", "\t\n ", None])
def test_empty_or_blank_quote_rejected(syn_text, quote):
    g = ground_quote(quote, syn_text)
    assert g.span is None
    assert g.score == 0.0
    assert g.grounded is False


# ---------------------------------------------------------------------------
# 7) Unicode -> exact match, correct code-point offsets
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,quote", [
    ("Contrat: la responsabilite totale ne depasse pas les frais.", "responsabilite totale"),
    ("La responsabilité totale ne dépasse pas les frais payés.", "responsabilité totale"),
    ("Payment 💰 due within thirty (30) days of the invoice.", "thirty (30) days"),
    ("Zahlung 💰 innerhalb von dreißig Tagen fällig.", "dreißig Tagen"),
    ("契約は Delaware 州の法律に準拠します。", "Delaware"),
])
def test_unicode_exact_offsets(text, quote):
    g = ground_quote(quote, text)
    assert g.score == 1.0
    assert g.grounded is True
    assert text[g.span.start:g.span.end] == quote
    assert g.span.text == quote


def test_unicode_offsets_after_emoji_are_codepoint_indexed():
    text = "Cap 💰💰 total liability of either party exceeds nothing."
    quote = "total liability of either party"
    g = ground_quote(quote, text)
    # find() and slicing both operate on code points, so offsets must agree
    assert g.span.start == text.find(quote)
    assert text[g.span.start:g.span.end] == quote


# ---------------------------------------------------------------------------
# 8) Invariants: span within bounds; span text recovers the stripped quote
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("quote", GOLD_QUOTES + ABSENT_QUOTES + [
    "governed by the laws of the State of Delware",  # fuzzy
    "NINETY (90) DAYS WRITTEN NOTICE",               # case
])
def test_span_always_within_bounds(syn_text, quote):
    g = ground_quote(quote, syn_text)
    if g.span is not None:
        assert 0 <= g.span.start <= g.span.end <= len(syn_text)
        # the span text is always exactly the slice it claims to cover
        assert syn_text[g.span.start:g.span.end] == g.span.text


@pytest.mark.parametrize("pad", ["  {}  ", "\n{}\t", "   {}", "{}\n\n"])
def test_padded_quote_stripped_before_exact_match(syn_text, pad):
    core = "continue to provide transition services"
    quote = pad.format(core)
    g = ground_quote(quote, syn_text)
    assert g.score == 1.0
    assert g.grounded is True
    # span recovers the STRIPPED quote, not the padding
    assert g.span.text == core
    assert syn_text[g.span.start:g.span.end] == core


def test_score_never_exceeds_unit_interval_for_varied_inputs(syn_text):
    for quote in GOLD_QUOTES + ABSENT_QUOTES + ["", "  ", "Delware typo notice"]:
        g = ground_quote(quote, syn_text)
        assert 0.0 <= g.score <= 1.0
        # grounded implies a located span
        if g.grounded:
            assert g.span is not None


def test_default_threshold_matches_explicit_085(syn_text):
    quote = "governed by the laws of the State of Delware"
    g_default = ground_quote(quote, syn_text)
    g_explicit = ground_quote(quote, syn_text, threshold=0.85)
    assert g_default.grounded == g_explicit.grounded
    assert g_default.score == g_explicit.score


def test_returns_grounding_type_for_all_paths(syn_text):
    for quote in ["governed by the laws of the State of Delaware",  # exact
                  "GOVERNED BY THE LAWS OF THE STATE OF DELAWARE",  # case
                  "governed by the laws of the State of Delware",   # fuzzy
                  ""]:                                              # reject
        assert isinstance(ground_quote(quote, syn_text), Grounding)
