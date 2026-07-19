"""Adversarial stitch-defense measurement.

Closes the loop on README honest-limitation #1: we do not just *claim* the stitch guard
helps, we MEASURE it on real contracts. For each contract we synthesise stitched
fabrications (a verbatim head from one clause + a verbatim tail from a far-apart clause,
concatenated so the pieces are real but never appear together), then report:

  - catch_rate            : stitches the grounder correctly refuses to ground
  - attributed_fabrication: stitches counted as fabrication WITH the guard
  - attributed_baseline   : ... WITHOUT it (fuzzy score < floor only) - the delta is the lift
  - false_positive_rate   : GENUINE gold quotes wrongly flagged as stitched (must stay ~0)

Generation is deterministic (no RNG), so the frozen demo number reproduces exactly.
"""
from __future__ import annotations

import re

from .cuad import Contract
from .ground import detect_stitch, ground_quote
from .schema import StitchDefenseMetric

_SENT = re.compile(r"(?<=[.;])\s+")
# A stitched quote = a DOMINANT verbatim head from one clause + a SHORT verbatim tail
# lifted from a different location. The asymmetry is deliberate: a long dominant head makes
# a fuzzy window score the whole quote high (the tail is a small mismatch), so the quote
# lands in the [floor, assert] band that fuzzy grounding silently admits - exactly the hole
# the guard closes. Symmetric halves instead score ~0.5 and fuzzy already rejects them.
_HEAD_WORD_SPLITS = (18, 15, 12)   # vary the head length to spread across fuzzy-score bands
_TAIL_WORDS = 3                     # short displaced tail
_MIN_DONOR_SEP = 120               # tail donor must start this many chars from the head


def _sentences(text: str, min_len: int = 80) -> list[tuple[int, str]]:
    """(source_offset, sentence) for sentences long enough to donate a fragment."""
    out: list[tuple[int, str]] = []
    pos = 0
    for s in _SENT.split(text):
        idx = text.find(s, pos)
        if idx == -1:
            idx = pos
        pos = idx + len(s)
        if len(s.strip()) >= min_len and len(s.split()) >= (max(_HEAD_WORD_SPLITS) + _TAIL_WORDS):
            out.append((idx, s.strip()))
    return out


def make_stitches(text: str, max_n: int = 6) -> list[str]:
    """Deterministically build asymmetric stitched quotes: a dominant verbatim head from
    one sentence + a short verbatim tail lifted from a different, displaced location.

    Head length is varied across `_HEAD_WORD_SPLITS` to spread the resulting fuzzy scores
    across bands (including the [floor, assert] band fuzzy grounding silently admits). Every
    returned quote is real fragments that never appear verbatim together in the source.
    """
    sents = _sentences(text, min_len=100)
    if len(sents) < 2:
        return []
    out: list[str] = []
    seen: set[str] = set()

    for k, (off_i, si) in enumerate(sents):
        words = si.split()
        if len(words) < max(_HEAD_WORD_SPLITS):
            continue
        # a short tail donor that starts well away from this sentence
        donor = next((sj for off_j, sj in sents
                      if abs(off_j - off_i) >= _MIN_DONOR_SEP and len(sj.split()) >= _TAIL_WORDS),
                     None)
        if donor is None:
            continue
        tail = " ".join(donor.split()[-_TAIL_WORDS:])
        head_n = _HEAD_WORD_SPLITS[k % len(_HEAD_WORD_SPLITS)]
        stitch = " ".join(words[:head_n]) + " " + tail
        if stitch.lower() not in text.lower() and stitch.lower() not in seen:
            seen.add(stitch.lower())
            out.append(stitch)
        if len(out) >= max_n:
            break
    return out


def evaluate_stitch_defense(contracts: list[Contract], fabrication_floor: float = 0.6,
                            threshold: float = 0.85, max_per_contract: int = 6
                            ) -> StitchDefenseMetric:
    injected = caught = would_assert = attributed = attributed_base = 0
    genuine_checked = false_pos = 0

    for c in contracts:
        for q in make_stitches(c.text, max_per_contract):
            injected += 1
            g = ground_quote(q, c.text, threshold, use_stitch_guard=True)
            raw = ground_quote(q, c.text, threshold, use_stitch_guard=False)  # pre-guard
            if not g.grounded:
                caught += 1
            if raw.grounded:                 # fuzzy alone would have ASSERTED this stitch
                would_assert += 1
            if g.stitched or g.score < fabrication_floor:
                attributed += 1
            if raw.score < fabrication_floor:  # fabrication accounting WITHOUT the guard
                attributed_base += 1

        # false-positive safety check: real gold quotes must NOT be flagged as stitched
        for spans in c.gold.values():
            for sp in spans:
                if len(sp.text.split()) < 12:
                    continue
                genuine_checked += 1
                if detect_stitch(sp.text, c.text) is not None:
                    false_pos += 1

    return StitchDefenseMetric(
        injected=injected, caught=caught,
        catch_rate=round(caught / injected, 4) if injected else 0.0,
        would_assert_without_guard=would_assert,
        attributed_fabrication=attributed, attributed_baseline=attributed_base,
        genuine_checked=genuine_checked, false_positives=false_pos,
        false_positive_rate=round(false_pos / genuine_checked, 4) if genuine_checked else 0.0,
    )
