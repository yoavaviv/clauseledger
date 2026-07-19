"""The evaluation protocol, in one place: run the pipeline, calibrate the abstention
threshold on the dev split, report metrics on the test split, and run fault injection.
Shared by the demo-freeze step and the reproducible CLI so the numbers are identical.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .abstain import apply_abstention, calibrate_threshold
from .adversarial import evaluate_stitch_defense
from .backends import Backend
from .cuad import Contract
from .faults import run_faults
from .metrics import bootstrap_metrics, compute_metrics
from .pipeline import process_contract
from .schema import RunConfig, RunReport


def evaluate(backend: Backend, contracts: list[Contract], *, target_precision: float = 0.9,
             run_fault: bool = True, generated_utc: str | None = None) -> RunReport:
    cfg = RunConfig(backend=backend.name, model=backend.model, abstain_threshold=0.9)

    results = []
    for c in contracts:
        res = process_contract(backend, c, cfg, gold=c.gold)
        res.split = c.split
        results.append(res)

    by_id = {c.id: c for c in contracts}
    dev = [r for r in results if r.split == "dev"]
    dev_rows = [row for r in dev for row in r.rows]
    thr = calibrate_threshold(dev_rows, target_precision) if dev_rows else 0.9
    for r in results:
        apply_abstention(r.rows, thr)

    report_results = [r for r in results if r.split == "test"] or results
    report_contracts = [by_id[r.contract_id] for r in report_results]
    metrics = compute_metrics(report_results, report_contracts,
                              cfg.gold_overlap_threshold, cfg.fabrication_floor)
    if run_fault:
        metrics.faults = run_faults(
            backend, report_contracts,
            cfg.model_copy(update={"abstain_threshold": thr}), metrics.recall_post_recovery)
    # adversarial stitch-defense measurement (deterministic; independent of the backend)
    metrics.stitch_defense = evaluate_stitch_defense(
        report_contracts, fabrication_floor=cfg.fabrication_floor, threshold=cfg.ground_threshold)
    # bootstrap 95% CIs for the headline metrics (honest uncertainty on a small test set)
    metrics.ci = bootstrap_metrics(report_results, report_contracts,
                                   cfg.gold_overlap_threshold, cfg.fabrication_floor)

    cfg = cfg.model_copy(update={
        "abstain_threshold": thr, "n_contracts": len(report_results),
        "notes": f"calibrated on {len(dev)} dev contracts; reported on {len(report_results)} test"})
    stamp = generated_utc or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    # ship all contracts (dev+test) for exploration, but metrics are test-only
    return RunReport(generated_utc=stamp, config=cfg, metrics=metrics, contracts=results)
