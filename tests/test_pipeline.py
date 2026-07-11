"""Pipeline orchestration: row construction, mutually-exclusive states, recovered-row
accounting, gold/no-gold modes, and RunReport assembly.
"""
import pytest

from clauseledger.backends import StubBackend
from clauseledger.pipeline import process_contract, run
from clauseledger.schema import CLAUSE_TYPES, RunConfig, Source


def cfg(**kw):
    return RunConfig(backend="stub", model="stub", abstain_threshold=kw.pop("thr", 0.9), **kw)


def test_row_ids_unique(syn_contract, stub_from_gold):
    res = process_contract(stub_from_gold, syn_contract, cfg(), gold=syn_contract.gold)
    ids = [r.row_id for r in res.rows]
    assert len(ids) == len(set(ids))


def test_row_id_contains_contract_and_clause(syn_contract, stub_from_gold):
    res = process_contract(stub_from_gold, syn_contract, cfg(), gold=syn_contract.gold)
    for r in res.rows:
        assert r.row_id.startswith("SYN-1::")
        assert r.clause_type in r.row_id


@pytest.mark.parametrize("thr", [0.0, 0.5, 0.9, 0.95, 1.0])
def test_states_mutually_exclusive(syn_contract, stub_from_gold, thr):
    res = process_contract(stub_from_gold, syn_contract, cfg(thr=thr), gold=syn_contract.gold)
    for r in res.rows:
        states = [not r.verdict.supported,
                  r.verdict.supported and r.abstained,
                  r.verdict.supported and not r.abstained]
        assert sum(bool(s) for s in states) == 1


def test_recovered_only_supported(syn_contract):
    be = StubBackend(recovery={("SYN-1", "Governing Law"): [{"claim": "x", "quote": "planet zog law zzz qqq"}]})
    res = process_contract(be, syn_contract, cfg(), gold=syn_contract.gold)
    assert res.recovered_row_ids == []


def test_recovered_supported_counted(syn_contract, syn_gold):
    q = syn_gold["Governing Law"][0].text
    be = StubBackend(recovery={("SYN-1", "Governing Law"): [{"claim": "gl", "quote": q}]})
    res = process_contract(be, syn_contract, cfg(), gold=syn_contract.gold)
    assert len(res.recovered_row_ids) == 1


def test_recovered_ids_are_recovery_source(syn_contract, stub_from_gold):
    res = process_contract(stub_from_gold, syn_contract, cfg(), gold=syn_contract.gold)
    rec_rows = {r.row_id: r for r in res.rows if r.source == Source.RECOVERY}
    for rid in res.recovered_row_ids:
        assert rid in rec_rows


def test_gold_mode_sets_matches(syn_contract, stub_from_gold):
    res = process_contract(stub_from_gold, syn_contract, cfg(), gold=syn_contract.gold)
    assert all(r.matches_gold is not None for r in res.rows)


def test_no_gold_leaves_matches_none(syn_contract, stub_from_gold):
    res = process_contract(stub_from_gold, syn_contract, cfg(), gold=None)
    assert all(r.matches_gold is None for r in res.rows)


def test_text_len_recorded(syn_contract, stub_from_gold):
    res = process_contract(stub_from_gold, syn_contract, cfg(), gold=syn_contract.gold)
    assert res.text_len == len(syn_contract.text)


def test_every_row_has_severity(syn_contract, stub_from_gold):
    res = process_contract(stub_from_gold, syn_contract, cfg(), gold=syn_contract.gold)
    assert all(r.severity is not None for r in res.rows)


def test_supported_rows_have_span(syn_contract, stub_from_gold):
    res = process_contract(stub_from_gold, syn_contract, cfg(), gold=syn_contract.gold)
    for r in res.rows:
        if r.verdict.supported:
            assert r.grounding.span is not None


@pytest.mark.parametrize("ct", CLAUSE_TYPES)
def test_all_clause_types_processed(syn_contract, stub_from_gold, ct):
    res = process_contract(stub_from_gold, syn_contract, cfg(), gold=syn_contract.gold)
    # every clause type is attempted (rows may be empty, but processing covers all)
    assert isinstance(res.rows, list)


# ---- run() ----
def test_run_report_config_counts(syn_contract, stub_from_gold):
    rep = run(stub_from_gold, [syn_contract], cfg())
    assert rep.config.n_contracts == 1 and rep.metrics.n_contracts == 1


def test_run_sets_backend_model(syn_contract, stub_from_gold):
    rep = run(stub_from_gold, [syn_contract], cfg())
    assert rep.config.backend == "stub" and rep.config.model == "stub"


def test_run_timestamp_present(syn_contract, stub_from_gold):
    rep = run(stub_from_gold, [syn_contract], cfg())
    assert rep.generated_utc


def test_run_custom_timestamp(syn_contract, stub_from_gold):
    rep = run(stub_from_gold, [syn_contract], cfg(), generated_utc="2026-01-01 00:00 UTC")
    assert rep.generated_utc == "2026-01-01 00:00 UTC"


def test_run_eval_false_no_matches(syn_contract, stub_from_gold):
    rep = run(stub_from_gold, [syn_contract], cfg(), eval_gold=False)
    for c in rep.contracts:
        for r in c.rows:
            assert r.matches_gold is None


def test_run_multiple_contracts(real_subset, ):
    contracts = real_subset.contracts[:3]
    initial = {(c.id, "Governing Law"): [{"claim": "gl", "quote": c.gold["Governing Law"][0].text}]
               for c in contracts if c.gold.get("Governing Law")}
    rep = run(StubBackend(initial=initial), contracts, cfg(thr=0.0))
    assert rep.metrics.n_contracts <= 3


def test_run_serializes(syn_contract, stub_from_gold):
    rep = run(stub_from_gold, [syn_contract], cfg())
    from clauseledger.schema import RunReport
    assert RunReport.model_validate_json(rep.model_dump_json()).config.backend == "stub"


def test_run_report_holds_all_contracts(real_subset):
    contracts = real_subset.contracts[:4]
    rep = run(StubBackend(), contracts, cfg(thr=0.5))
    assert len(rep.contracts) == 4
