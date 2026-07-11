"""Grounding: locate a model's verbatim quote inside the contract text.

This is the trust primitive. A backend claims an obligation and cites a quote;
grounding decides whether that quote is *actually in the document* and where.
A quote that cannot be grounded is a fabrication (gold-independent), and this is
what lets the verifier reject invented obligations without needing an answer key.
"""
from __future__ import annotations

import re

from rapidfuzz import fuzz

from .schema import Grounding, Span

_WS = re.compile(r"\s+")


def _norm(s: str) -> str:
    return _WS.sub(" ", s).strip().lower()


def ground_quote(quote: str, text: str, threshold: float = 0.85) -> Grounding:
    """Find `quote` in `text`. Returns a Grounding with a Span and a 0..1 score.

    Strategy, cheapest-first: exact substring -> whitespace/case-insensitive exact
    -> fuzzy partial alignment (rapidfuzz). `grounded` is True iff score >= threshold.
    """
    quote = (quote or "").strip()
    if not quote:
        return Grounding(span=None, score=0.0, grounded=False)

    # 1) exact substring
    idx = text.find(quote)
    if idx != -1:
        span = Span(start=idx, end=idx + len(quote), text=quote)
        return Grounding(span=span, score=1.0, grounded=True)

    # 2) whitespace/case-insensitive exact: search normalized text, map back
    nq = _norm(quote)
    if nq:
        # Build a normalized view of text with an index map back to original offsets.
        norm_chars: list[str] = []
        idx_map: list[int] = []
        prev_space = False
        for i, ch in enumerate(text):
            if ch.isspace():
                if not prev_space:
                    norm_chars.append(" ")
                    idx_map.append(i)
                prev_space = True
            else:
                norm_chars.append(ch.lower())
                idx_map.append(i)
                prev_space = False
        # Do NOT strip: idx_map is aligned to norm_chars char-for-char, and stripping
        # ntext would shift every position relative to idx_map (off-by-one span bug).
        ntext = "".join(norm_chars)
        pos = ntext.find(nq)
        if pos != -1:
            # map normalized positions back to original text offsets
            start_orig = idx_map[pos]
            end_norm = pos + len(nq) - 1
            end_orig = idx_map[min(end_norm, len(idx_map) - 1)] + 1
            span_text = text[start_orig:end_orig]
            return Grounding(span=Span(start=start_orig, end=end_orig, text=span_text),
                             score=0.99, grounded=True)

    # 3) fuzzy partial alignment
    al = fuzz.partial_ratio_alignment(quote, text, score_cutoff=50.0)
    if al is not None:
        score = al.score / 100.0
        start, end = al.dest_start, al.dest_end
        span_text = text[start:end]
        return Grounding(span=Span(start=start, end=end, text=span_text),
                         score=score, grounded=score >= threshold)

    return Grounding(span=None, score=0.0, grounded=False)
