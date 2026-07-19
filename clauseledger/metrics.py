"""Metrics: recall (single-shot vs post-recovery), precision, gold-free fabrication,
false-alarm on absent clauses, abstention, and the precision/recall/abstention Pareto.

Recall is measured against CUAD gold spans; fabrication is measured WITHOUT gold
(a quote either is or isn't in the document), which is the honest, un-gameable number
that leads the scoreboard.
"""
from __future__ import annotations

import random

from .cuad import Contract
from .schema import (CI, ClauseMetric, ContractResult, Metrics, ParetoPoint, RegisterRow,
                     Source, Span, CLAUSE_TYPES)


def span_match(a: Span, b: Span, threshold: float = 0.5) -> bool:
    """True if spans overlap enough: overlap / smaller-span-length >= threshold.

    Lenient by design: a short correct quote inside a long CUAD gold highlight counts.
    """
    inter = max(0, min(a.end, b.end) - max(a.start, b.start))
    if inter <= 0:
        return False
    smaller = max(1, min(a.end - a.start, b.end - b.start))
    return inter / smaller >= threshold


def _covered(gold_spans: list[Span], rows: list[RegisterRow], overlap_threshold: float) -> int:
    """How many gold spans are covered by at least one supported row."""
    n = 0
    for g in gold_spans:
        if any(r.verdict.supported and r.grounding.span and span_match(r.grounding.span, g, overlap_threshold)
               for r in rows):
            n += 1
    return n


def mark_gold_matches(rows: list[RegisterRow], gold: dict[str, list[Span]],
                      overlap_threshold: float = 0.5) -> None:
    """Set row.matches_gold for eval display/precision (in place)."""
    for r in rows:
        if not r.verdict.supported or not r.grounding.span:
            r.matches_gold = False
            continue
        gspans = gold.get(r.clause_type, [])
        r.matches_gold = any(span_match(r.grounding.span, g, overlap_threshold) for g in gspans)


def compute_metrics(results: list[ContractResult], contracts: list[Contract],
                    overlap_threshold: float = 0.5,
                    fabrication_floor: float = 0.6,
                    pareto_grid: list[float] | None = None) -> Metrics:
    by_id = {c.id: c for c in contracts}
    if pareto_grid is None:  # [] explicitly means "skip the Pareto" (used by the bootstrap)
        pareto_grid = [i / 20 for i in range(0, 21)]

    all_rows: list[RegisterRow] = [r for res in results for r in res.rows]
    supported = [r for r in all_rows if r.verdict.supported]

    # ---- recall single-shot vs post-recovery, per clause + aggregate ----
    per_clause: list[ClauseMetric] = []
    tot_gold = ss_cov = pr_cov = 0
    for ct in CLAUSE_TYPES:
        c_gold = c_ss = c_pr = 0
        prec_hit = prec_tot = 0
        for res in results:
            contract = by_id.get(res.contract_id)
            if not contract:
                continue
            gspans = contract.gold.get(ct, [])
            c_gold += len(gspans)
            rows_ct = [r for r in res.rows if r.clause_type == ct]
            ss_rows = [r for r in rows_ct if r.source == Source.INITIAL]
            c_ss += _covered(gspans, ss_rows, overlap_threshold)
            c_pr += _covered(gspans, rows_ct, overlap_threshold)
            for r in rows_ct:
                if r.verdict.supported and not r.abstained:
                    prec_tot += 1
                    if r.matches_gold:
                        prec_hit += 1
        per_clause.append(ClauseMetric(
            clause_type=ct, gold_total=c_gold,
            recall_single_shot=round(c_ss / c_gold, 4) if c_gold else 0.0,
            recall_post_recovery=round(c_pr / c_gold, 4) if c_gold else 0.0,
            precision=round(prec_hit / prec_tot, 4) if prec_tot else 0.0,
        ))
        tot_gold += c_gold
        ss_cov += c_ss
        pr_cov += c_pr

    recall_ss = ss_cov / tot_gold if tot_gold else 0.0
    recall_pr = pr_cov / tot_gold if tot_gold else 0.0

    # asserted recall: gold covered only by asserted (supported, non-abstained) rows
    as_cov = 0
    for res in results:
        contract = by_id.get(res.contract_id)
        if not contract:
            continue
        for ct in CLAUSE_TYPES:
            arows = [r for r in res.rows if r.clause_type == ct
                     and r.verdict.supported and not r.abstained]
            as_cov += _covered(contract.gold.get(ct, []), arows, overlap_threshold)
    recall_asserted = as_cov / tot_gold if tot_gold else 0.0

    # ---- precision on asserted (non-abstained supported) rows ----
    asserted = [r for r in supported if not r.abstained]
    prec = (sum(1 for r in asserted if r.matches_gold) / len(asserted)) if asserted else 0.0

    # ---- fabrication (gold-free AND threshold-free): quote genuinely not in the document ----
    # Measured against a FIXED floor, not ground_threshold, so it cannot be gamed by moving
    # the verification threshold. A row scoring below the floor cites text that is not there.
    # A STITCHED quote (real fragments, non-contiguous) is a fabrication too, even when its
    # best fuzzy window scores above the floor - the stitch guard is what catches that class.
    fabrication = (sum(1 for r in all_rows
                       if r.grounding.stitched or r.grounding.score < fabrication_floor)
                   / len(all_rows)) if all_rows else 0.0

    # ---- false alarm on genuinely-absent clause types ----
    absent_pairs = 0
    absent_hits = 0
    for res in results:
        contract = by_id.get(res.contract_id)
        if not contract:
            continue
        for ct in contract.absent:
            absent_pairs += 1
            if any(r.clause_type == ct and r.verdict.supported and not r.abstained for r in res.rows):
                absent_hits += 1
    false_alarm = absent_hits / absent_pairs if absent_pairs else 0.0

    abstention = (sum(1 for r in supported if r.abstained) / len(supported)) if supported else 0.0

    # ---- Pareto over abstention thresholds ----
    pareto: list[ParetoPoint] = []
    for t in pareto_grid:
        assert_rows = [r for r in supported if r.confidence >= t]
        p = (sum(1 for r in assert_rows if r.matches_gold) / len(assert_rows)) if assert_rows else 1.0
        # recall at threshold: gold covered by asserted rows only
        cov = 0
        for res in results:
            contract = by_id.get(res.contract_id)
            if not contract:
                continue
            for ct in CLAUSE_TYPES:
                gspans = contract.gold.get(ct, [])
                arows = [r for r in res.rows if r.clause_type == ct and r.confidence >= t]
                cov += _covered(gspans, arows, overlap_threshold)
        rec = cov / tot_gold if tot_gold else 0.0
        ab = (sum(1 for r in supported if r.confidence < t) / len(supported)) if supported else 0.0
        pareto.append(ParetoPoint(threshold=round(t, 3), precision=round(p, 4),
                                  recall=round(rec, 4), abstention=round(ab, 4)))

    return Metrics(
        n_contracts=len(results), per_clause=per_clause,
        recall_single_shot=round(recall_ss, 4), recall_post_recovery=round(recall_pr, 4),
        recall_lift=round(recall_pr - recall_ss, 4), recall_asserted=round(recall_asserted, 4),
        precision=round(prec, 4),
        fabrication_rate=round(fabrication, 4), false_alarm_rate=round(false_alarm, 4),
        abstention_rate=round(abstention, 4), pareto=pareto,
    )


def _percentile(sorted_vals: list[float], q: float) -> float:
    """Linear-interpolated percentile (q in 0..1) of an already-sorted list."""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    frac = pos - lo
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac


# Headline metrics we attach a confidence interval to (name -> attribute on Metrics).
_CI_METRICS = ("recall_post_recovery", "recall_asserted", "precision",
               "fabrication_rate", "false_alarm_rate", "abstention_rate")


def bootstrap_metrics(results: list[ContractResult], contracts: list[Contract],
                      overlap_threshold: float = 0.5, fabrication_floor: float = 0.6,
                      n_boot: int = 500, level: float = 0.95, seed: int = 0
                      ) -> dict[str, CI]:
    """Percentile bootstrap CIs for the headline metrics, resampling CONTRACTS with
    replacement. Deterministic (fixed seed) so the frozen number reproduces exactly.

    Resampling at the contract level (not the row level) is the honest unit: contracts are
    the independent observations, and it is the small NUMBER OF CONTRACTS that drives the
    uncertainty on a demo-scale test set.
    """
    if len(results) < 2:
        return {}
    rng = random.Random(seed)
    by_id = {c.id: c for c in contracts}
    samples: dict[str, list[float]] = {k: [] for k in _CI_METRICS}
    n = len(results)
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        res_s = [results[i] for i in idx]
        con_s = [by_id[results[i].contract_id] for i in idx]
        m = compute_metrics(res_s, con_s, overlap_threshold, fabrication_floor,
                            pareto_grid=[])  # skip the pareto grid: not needed for CIs
        for k in _CI_METRICS:
            samples[k].append(getattr(m, k))
    lo_q, hi_q = (1 - level) / 2, 1 - (1 - level) / 2
    out: dict[str, CI] = {}
    for k, vals in samples.items():
        vals.sort()
        out[k] = CI(lo=round(_percentile(vals, lo_q), 4), hi=round(_percentile(vals, hi_q), 4),
                    n_boot=n_boot, level=level)
    return out
