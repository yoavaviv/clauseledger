"""Grounding: locate a model's verbatim quote inside the contract text.

This is the trust primitive. A backend claims an obligation and cites a quote;
grounding decides whether that quote is *actually in the document* and where.
A quote that cannot be grounded is a fabrication (gold-independent), and this is
what lets the verifier reject invented obligations without needing an answer key.

Fuzzy alignment alone has a known hole (README, honest limitation #1): a fake quote
STITCHED from real fragments scattered across the contract can score above the
fabrication floor, because a good local window still aligns well. `detect_stitch`
closes that hole - it reconstructs the quote from verbatim fragments and flags any
quote whose pieces are real but do not appear contiguously in the source.
"""
from __future__ import annotations

import re

from rapidfuzz import fuzz

from .schema import Grounding, Span, StitchEvidence

_WS = re.compile(r"\s+")


def _norm(s: str) -> str:
    return _WS.sub(" ", s).strip().lower()


def _normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Whitespace/case-normalized view of `text` plus a char-for-char index map back
    to original offsets. Shared by the normalized-exact match and the stitch detector.

    Do NOT strip the result: idx_map is aligned to the normalized chars one-for-one, and
    stripping would shift every position relative to idx_map (an off-by-one span bug).
    """
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
    return "".join(norm_chars), idx_map


# --- stitch detection tunables ----------------------------------------------- #
# A quote must be long enough to plausibly be stitched from parts.
_STITCH_MIN_QUOTE_WORDS = 12
# A verbatim fragment must be at least this many words to count as a "piece".
_STITCH_MIN_FRAG_WORDS = 3
# The reconstructed fragments must cover at least this fraction of the quote's words.
_STITCH_MIN_COVERAGE = 0.8
# Adjacent fragments up to this many source chars apart still count as contiguous
# (tolerates a small omitted word/punctuation); a wider gap means the pieces come
# from different regions = a stitch. Generous on purpose: false-flagging a real quote
# as a fabrication is worse for a trust tool than missing one exotic stitch.
_STITCH_MAX_GAP = 60


def detect_stitch(quote: str, text: str) -> StitchEvidence | None:
    """Detect a quote assembled from >=2 disjoint verbatim fragments of `text`.

    Returns StitchEvidence when the quote is NOT a contiguous substring yet can be
    reconstructed from real fragments taken from non-contiguous source locations, i.e.
    a fabrication that fuzzy grounding would otherwise admit. Returns None otherwise
    (contiguous quotes, short quotes, and genuine fuzzy noise are all left alone).
    """
    nq = _norm(quote)
    words = nq.split()
    if len(words) < _STITCH_MIN_QUOTE_WORDS:
        return None

    ntext, idx_map = _normalize_with_map(text)
    if not ntext or nq in ntext:
        # a contiguous (normalized) substring is handled by the normal path - not a stitch
        return None

    # Greedy longest-verbatim-fragment cover of the quote against the source.
    fragments: list[tuple[int, int]] = []  # (src_start_norm, src_end_norm)
    covered_words = 0
    i = 0
    n = len(words)
    while i < n:
        best_j = i
        best_pos = -1
        j = i + 1
        while j <= n:
            frag = " ".join(words[i:j])
            pos = ntext.find(frag)
            if pos == -1:
                break
            best_j, best_pos = j, pos
            j += 1
        if best_j - i >= _STITCH_MIN_FRAG_WORDS:
            frag = " ".join(words[i:best_j])
            fragments.append((best_pos, best_pos + len(frag)))
            covered_words += best_j - i
            i = best_j
        else:
            i += 1  # a word we cannot place verbatim: an unmatched gap

    if len(fragments) < 2 or covered_words / n < _STITCH_MIN_COVERAGE:
        return None

    # Contiguity: consecutive fragments must sit adjacent and in order in the source.
    # Any out-of-order or far-apart pair means the pieces were stitched from elsewhere.
    disjoint = any((b[0] - a[1]) < 0 or (b[0] - a[1]) > _STITCH_MAX_GAP
                   for a, b in zip(fragments, fragments[1:]))
    if not disjoint:
        return None

    spans = [Span(start=idx_map[s], end=idx_map[min(e - 1, len(idx_map) - 1)] + 1,
                  text=text[idx_map[s]:idx_map[min(e - 1, len(idx_map) - 1)] + 1])
             for s, e in fragments]
    return StitchEvidence(fragments=spans, coverage=round(covered_words / n, 4))


def ground_quote(quote: str, text: str, threshold: float = 0.85,
                 use_stitch_guard: bool = True) -> Grounding:
    """Find `quote` in `text`. Returns a Grounding with a Span and a 0..1 score.

    Strategy, cheapest-first: exact substring -> whitespace/case-insensitive exact
    -> fuzzy partial alignment (rapidfuzz). `grounded` is True iff score >= threshold.
    A quote flagged as STITCHED (real fragments, non-contiguous) is never grounded,
    regardless of its fuzzy score - that is the fabrication fuzzy matching would miss.

    `use_stitch_guard=False` disables that guard and returns the raw fuzzy behaviour -
    used only to MEASURE what the guard prevents (the pre-guard baseline), never in the
    live pipeline.
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
        ntext, idx_map = _normalize_with_map(text)
        pos = ntext.find(nq)
        if pos != -1:
            start_orig = idx_map[pos]
            end_norm = pos + len(nq) - 1
            end_orig = idx_map[min(end_norm, len(idx_map) - 1)] + 1
            span_text = text[start_orig:end_orig]
            return Grounding(span=Span(start=start_orig, end=end_orig, text=span_text),
                             score=0.99, grounded=True)

    # 2b) stitch guard: real fragments from non-contiguous locations = fabrication.
    # Run BEFORE fuzzy alignment so a good local window can never launder a stitch.
    if use_stitch_guard:
        stitch = detect_stitch(quote, text)
        if stitch is not None:
            # Keep the first fragment's span as display evidence, but never ground it.
            return Grounding(span=stitch.fragments[0], score=0.0, grounded=False,
                             stitched=True, stitch_fragments=stitch.fragments)

    # 3) fuzzy partial alignment
    al = fuzz.partial_ratio_alignment(quote, text, score_cutoff=50.0)
    if al is not None:
        score = al.score / 100.0
        start, end = al.dest_start, al.dest_end
        span_text = text[start:end]
        return Grounding(span=Span(start=start, end=end, text=span_text),
                         score=score, grounded=score >= threshold)

    return Grounding(span=None, score=0.0, grounded=False)
