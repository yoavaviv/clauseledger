"""Fault injection: honest failure numbers under stress.

We degrade the inputs/verifier and re-measure. The point a hiring manager respects is
NOT a flattering headline; it is showing recall degrade gracefully and fabrication stay
controlled when the world gets messy. `completion` is the fraction of contracts the
pipeline finished without crashing.
"""
from __future__ import annotations

from dataclasses import replace

from .backends import Backend
from .cuad import Contract
from .metrics import compute_metrics
from .pipeline import run
from .schema import FaultResult, RunConfig


def _truncate(contracts: list[Contract], frac: float) -> list[Contract]:
    out = []
    for c in contracts:
        out.append(replace(c, text=c.text[: max(1, int(len(c.text) * frac))]))
    return out


def _reformat(contracts: list[Contract]) -> list[Contract]:
    """Collapse/duplicate whitespace and change case: tests grounding under formatting noise."""
    out = []
    for c in contracts:
        t = c.text.replace("\n", "  \n ").replace("  ", " \t")
        out.append(replace(c, text=t))
    return out


def _safe_run(backend, contracts, config):
    """Run, returning (metrics, completion_fraction). Never raises."""
    ok = 0
    results = []
    from .pipeline import process_contract
    for c in contracts:
        try:
            results.append(process_contract(backend, c, config, gold=c.gold))
            ok += 1
        except Exception:
            continue
    metrics = compute_metrics(results, contracts, config.gold_overlap_threshold,
                              config.fabrication_floor)
    completion = ok / len(contracts) if contracts else 1.0
    return metrics, completion


def run_faults(backend: Backend, contracts: list[Contract], config: RunConfig,
               baseline_recall: float) -> list[FaultResult]:
    out: list[FaultResult] = []

    # 1) truncate contracts to 60%: tail obligations become unfindable
    m, comp = _safe_run(backend, _truncate(contracts, 0.6), config)
    out.append(FaultResult(name="truncation_60",
        description="Each contract truncated to 60% of its length. Recall should drop for "
                    "tail obligations; fabrication should NOT rise to compensate.",
        baseline_recall=round(baseline_recall, 4), faulted_recall=m.recall_post_recovery,
        fabrication_rate=m.fabrication_rate, completion=round(comp, 4)))

    # 2) formatting noise: grounding must tolerate whitespace/case changes
    m, comp = _safe_run(backend, _reformat(contracts), config)
    out.append(FaultResult(name="formatting_noise",
        description="Whitespace duplicated/altered and tabs injected. Grounding should still "
                    "locate quotes via normalization; recall roughly holds.",
        baseline_recall=round(baseline_recall, 4), faulted_recall=m.recall_post_recovery,
        fabrication_rate=m.fabrication_rate, completion=round(comp, 4)))

    # 3) stricter verifier: raise the grounding bar; assertions fall, fabrication should drop
    strict = config.model_copy(update={"ground_threshold": 0.98})
    m, comp = _safe_run(backend, contracts, strict)
    out.append(FaultResult(name="strict_verifier",
        description="Verification bar raised to 0.98: borderline citations (score 0.85-0.98) are "
                    "rejected, so detection recall falls. Fabrication is measured at a FIXED floor, "
                    "so it does not move - the assertion bar and the fabrication measure are "
                    "independent dials, by design.",
        baseline_recall=round(baseline_recall, 4), faulted_recall=m.recall_post_recovery,
        fabrication_rate=m.fabrication_rate, completion=round(comp, 4)))

    return out
