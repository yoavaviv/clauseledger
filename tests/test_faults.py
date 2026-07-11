"""Fault injection and end-to-end integration invariants on real CUAD.
Faults must degrade gracefully and never crash (completion == 1.0).
"""
import pytest

from clauseledger.backends import StubBackend
from clauseledger.faults import run_faults
from clauseledger.pipeline import run
from clauseledger.schema import CLAUSE_TYPES, RunConfig


def cfg(thr=0.9):
    return RunConfig(backend="stub", model="stub", abstain_threshold=thr)


@pytest.fixture
def faults(syn_contract, stub_from_gold):
    return run_faults(stub_from_gold, [syn_contract], cfg(), baseline_recall=1.0)


def test_three_faults_present(faults):
    assert {f.name for f in faults} == {"truncation_60", "formatting_noise", "strict_verifier"}


@pytest.mark.parametrize("name", ["truncation_60", "formatting_noise", "strict_verifier"])
def test_fault_completion_full(faults, name):
    f = next(x for x in faults if x.name == name)
    assert f.completion == pytest.approx(1.0)  # never crashes


@pytest.mark.parametrize("name", ["truncation_60", "formatting_noise", "strict_verifier"])
def test_fault_recall_bounded(faults, name):
    f = next(x for x in faults if x.name == name)
    assert 0.0 <= f.faulted_recall <= 1.0


@pytest.mark.parametrize("name", ["truncation_60", "formatting_noise", "strict_verifier"])
def test_fault_fabrication_bounded(faults, name):
    f = next(x for x in faults if x.name == name)
    assert 0.0 <= f.fabrication_rate <= 1.0


def test_truncation_drops_recall(faults):
    f = next(x for x in faults if x.name == "truncation_60")
    assert f.faulted_recall < 1.0  # tail obligations cut


def test_strict_verifier_recall_le_baseline(faults):
    f = next(x for x in faults if x.name == "strict_verifier")
    assert f.faulted_recall <= f.baseline_recall + 1e-9


def test_formatting_noise_preserves_completion(faults):
    f = next(x for x in faults if x.name == "formatting_noise")
    assert f.completion == 1.0


def test_faults_carry_baseline(faults):
    assert all(f.baseline_recall == pytest.approx(1.0) for f in faults)


def test_faults_have_descriptions(faults):
    assert all(len(f.description) > 20 for f in faults)


def test_faults_never_raise_on_empty():
    out = run_faults(StubBackend(), [], cfg(), baseline_recall=0.0)
    assert len(out) == 3


# ---- end-to-end integration on real CUAD ----
@pytest.fixture
def real_report(real_subset):
    contracts = real_subset.contracts[:12]
    initial, recovery = {}, {}
    for ci, c in enumerate(contracts):
        for ti, ct in enumerate(CLAUSE_TYPES):
            spans = c.gold.get(ct, [])
            if not spans:
                continue
            rows = [{"claim": ct, "quote": s.text} for s in spans]
            (recovery if (ci + ti) % 2 == 0 else initial)[(c.id, ct)] = rows
    return run(StubBackend(initial=initial, recovery=recovery), contracts,
               RunConfig(backend="stub", model="stub", abstain_threshold=0.0)), contracts


def test_real_zero_fabrication(real_report):
    rep, _ = real_report
    assert rep.metrics.fabrication_rate == pytest.approx(0.0)


def test_real_precision_perfect(real_report):
    rep, _ = real_report
    assert rep.metrics.precision == pytest.approx(1.0)


def test_real_no_false_alarm(real_report):
    rep, _ = real_report
    assert rep.metrics.false_alarm_rate == pytest.approx(0.0)


def test_real_every_supported_has_span(real_report):
    rep, _ = real_report
    for c in rep.contracts:
        for r in c.rows:
            if r.verdict.supported:
                assert r.grounding.span is not None


def test_real_absent_types_not_matched(real_report):
    rep, contracts = real_report
    by_id = {c.id: c for c in contracts}
    for cres in rep.contracts:
        contract = by_id[cres.contract_id]
        for r in cres.rows:
            if r.clause_type in contract.absent:
                assert not r.verdict.supported or r.matches_gold is False


def test_real_report_serializes(real_report):
    rep, _ = real_report
    assert len(rep.model_dump_json()) > 500


def test_real_states_exclusive(real_report):
    rep, _ = real_report
    for c in rep.contracts:
        for r in c.rows:
            s = [not r.verdict.supported, r.verdict.supported and r.abstained,
                 r.verdict.supported and not r.abstained]
            assert sum(bool(x) for x in s) == 1


def test_real_faults_run(real_subset):
    contracts = real_subset.contracts[:6]
    initial = {(c.id, "Governing Law"): [{"claim": "gl", "quote": c.gold["Governing Law"][0].text}]
               for c in contracts if c.gold.get("Governing Law")}
    be = StubBackend(initial=initial)
    faults = run_faults(be, contracts, cfg(thr=0.0), baseline_recall=1.0)
    assert all(f.completion == 1.0 for f in faults)


def test_real_contract_count(real_report):
    rep, contracts = real_report
    assert len(rep.contracts) == len(contracts)
