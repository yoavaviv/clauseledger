"""Property-based tests (hypothesis) for the grounding primitive and metric invariants.
These assert properties over many generated inputs, not just hand-picked cases.
"""
from hypothesis import given, settings
from hypothesis import strategies as st

from clauseledger.ground import ground_quote
from clauseledger.metrics import span_match
from clauseledger.schema import Span

# realistic contract-ish text
_TEXT = ("This Master Services Agreement is governed by the laws of the State of New York. "
         "The term shall automatically renew for one-year periods unless either party gives "
         "ninety (90) days notice. Total liability shall not exceed the fees paid. "
         "Post-termination the provider shall deliver transition services for sixty days.")


@given(st.integers(min_value=0, max_value=len(_TEXT) - 20),
       st.integers(min_value=8, max_value=60))
@settings(max_examples=200, deadline=None)
def test_any_real_substring_grounds_at_correct_offset(start, length):
    end = min(len(_TEXT), start + length)
    sub = _TEXT[start:end]
    if not sub.strip():
        return
    g = ground_quote(sub, _TEXT)
    assert g.grounded
    assert g.span is not None
    # grounding strips the quote (models add whitespace), so the span recovers sub.strip()
    assert _TEXT[g.span.start:g.span.end] == sub.strip()


@given(st.text(alphabet=st.characters(min_codepoint=32, max_codepoint=126), min_size=0, max_size=80))
@settings(max_examples=200, deadline=None)
def test_grounding_never_out_of_bounds(q):
    g = ground_quote(q, _TEXT)
    assert 0.0 <= g.score <= 1.0
    if g.span is not None:
        assert 0 <= g.span.start <= g.span.end <= len(_TEXT)


@given(st.integers(0, 100), st.integers(0, 100), st.integers(0, 100), st.integers(0, 100))
@settings(max_examples=200, deadline=None)
def test_span_match_symmetric(a0, a1, b0, b1):
    a = Span(start=min(a0, a1), end=max(a0, a1) + 1, text="x")
    b = Span(start=min(b0, b1), end=max(b0, b1) + 1, text="y")
    assert span_match(a, b, 0.5) == span_match(b, a, 0.5)


@given(st.floats(min_value=0.0, max_value=1.0))
@settings(max_examples=50, deadline=None)
def test_grounding_threshold_only_affects_flag_not_span(thr):
    q = "governed by the laws of the State of New York"
    g = ground_quote(q, _TEXT, threshold=thr)
    # exact match -> always grounded regardless of threshold, span stable
    assert g.grounded
    assert _TEXT[g.span.start:g.span.end] == q
