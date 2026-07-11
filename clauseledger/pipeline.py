"""End-to-end orchestration: extract -> recover -> verify -> abstain -> severity -> metrics.

process_contract runs one contract; run() runs a set and assembles the frozen RunReport
the static demo renders.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .abstain import apply_abstention
from .backends import Backend
from .cuad import Contract
from .metrics import compute_metrics, mark_gold_matches
from .schema import (CLAUSE_TYPES, ContractResult, Grounding, RegisterRow, RunConfig,
                     RunReport, Source, Span, Verdict)
from .severity import score_severity
from .verify import verify_candidate


def process_contract(backend: Backend, contract: Contract, config: RunConfig,
                     gold: dict[str, list[Span]] | None = None) -> ContractResult:
    rows: list[RegisterRow] = []
    recovered: list[str] = []

    for ct in CLAUSE_TYPES:
        initial = backend.extract(contract.id, contract.text, ct)
        found_quotes = [c.quote for c in initial]
        recovery = backend.recover(contract.id, contract.text, ct, found_quotes)

        for j, cand in enumerate(initial + recovery):
            grounding, verdict, confidence = verify_candidate(
                cand, contract.text, config.ground_threshold)
            row = RegisterRow(
                row_id=f"{contract.id}::{ct}::{cand.source.value}::{j}",
                clause_type=ct, claim=cand.claim, quote=cand.quote,
                grounding=grounding, verdict=verdict, source=cand.source,
                confidence=confidence, severity=score_severity(ct, cand.claim),
            )
            rows.append(row)
            if cand.source == Source.RECOVERY and verdict.supported:
                recovered.append(row.row_id)

    apply_abstention(rows, config.abstain_threshold)
    if gold is not None:
        mark_gold_matches(rows, gold, config.gold_overlap_threshold)

    return ContractResult(contract_id=contract.id, text_len=len(contract.text),
                          rows=rows, recovered_row_ids=recovered)


def run(backend: Backend, contracts: list[Contract], config: RunConfig,
        eval_gold: bool = True, generated_utc: str | None = None) -> RunReport:
    results: list[ContractResult] = []
    for c in contracts:
        results.append(process_contract(backend, c, config,
                                        gold=c.gold if eval_gold else None))
    metrics = compute_metrics(results, contracts, config.gold_overlap_threshold,
                              config.fabrication_floor)
    config = config.model_copy(update={"n_contracts": len(contracts),
                                       "backend": backend.name, "model": backend.model})
    stamp = generated_utc or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return RunReport(generated_utc=stamp, config=config, metrics=metrics, contracts=results)
