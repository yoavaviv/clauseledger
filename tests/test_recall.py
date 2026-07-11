"""Recall: single-shot vs post-recovery vs asserted, recall-lift, per-clause. Exact
expected values on the synthetic contract, plus invariants on real CUAD.
"""
import pytest

from clauseledger.backends import StubBackend
from clauseledger.pipeline import run
from clauseledger.schema import CLAUSE_TYPES, RunConfig


@pytest.fixture
def report(syn_contract, stub_from_gold):
    cfg = RunConfig(backend="stub", model="stub", abstain_threshold=0.9)
    return run(stub_from_gold, [syn_contract], cfg)


# ---- exact values on the synthetic contract (4/5 single-shot, 5/5 post-recovery) ----
def test_single_shot_recall_exact(report):
    assert report.metrics.recall_single_shot == pytest.approx(0.8)


def test_post_recovery_recall_exact(report):
    assert report.metrics.recall_post_recovery == pytest.approx(1.0)


def test_recall_lift_exact(report):
    assert report.metrics.recall_lift == pytest.approx(0.2)


def test_asserted_recall_exact(report):
    # all quotes exact (confidence 1.0), threshold 0.9 -> nothing abstains -> asserted == post
    assert report.metrics.recall_asserted == pytest.approx(1.0)


def test_recall_lift_is_post_minus_single(report):
    m = report.metrics
    assert m.recall_lift == pytest.approx(m.recall_post_recovery - m.recall_single_shot)


def test_asserted_le_post(report):
    assert report.metrics.recall_asserted <= report.metrics.recall_post_recovery + 1e-9


def test_single_le_post(report):
    assert report.metrics.recall_single_shot <= report.metrics.recall_post_recovery + 1e-9


def test_all_recalls_in_unit_interval(report):
    m = report.metrics
    for v in (m.recall_single_shot, m.recall_post_recovery, m.recall_asserted):
        assert 0.0 <= v <= 1.0


# ---- per-clause recall ----
@pytest.mark.parametrize("ct", CLAUSE_TYPES)
def test_per_clause_present(report, ct):
    cms = {c.clause_type: c for c in report.metrics.per_clause}
    assert ct in cms


@pytest.mark.parametrize("ct,expect_gold", [
    ("Governing Law", 1), ("Renewal Term", 1), ("Notice Period To Terminate Renewal", 1),
    ("Cap On Liability", 1), ("Post-Termination Services", 1), ("Liquidated Damages", 0),
])
def test_per_clause_gold_totals(report, ct, expect_gold):
    cm = next(c for c in report.metrics.per_clause if c.clause_type == ct)
    assert cm.gold_total == expect_gold


def test_notice_period_only_in_recovery(report):
    cm = next(c for c in report.metrics.per_clause if c.clause_type == "Notice Period To Terminate Renewal")
    assert cm.recall_single_shot == pytest.approx(0.0)
    assert cm.recall_post_recovery == pytest.approx(1.0)


@pytest.mark.parametrize("ct", ["Governing Law", "Renewal Term", "Cap On Liability", "Post-Termination Services"])
def test_initial_clauses_found_single_shot(report, ct):
    cm = next(c for c in report.metrics.per_clause if c.clause_type == ct)
    assert cm.recall_single_shot == pytest.approx(1.0)


def test_per_clause_recall_monotonic(report):
    for cm in report.metrics.per_clause:
        assert cm.recall_single_shot <= cm.recall_post_recovery + 1e-9


# ---- abstention lowers asserted recall ----
def test_asserted_below_detection_with_high_threshold(syn_contract, syn_gold):
    initial = {}
    for ct, spans in syn_gold.items():
        if spans:
            w = spans[0].text.split()
            w[1] = "hereinbefore"
            initial[("SYN-1", ct)] = [{"claim": ct, "quote": " ".join(w)}]
    be = StubBackend(initial=initial)
    cfg = RunConfig(backend="stub", model="stub", abstain_threshold=0.999)
    rep = run(be, [syn_contract], cfg)
    assert rep.metrics.recall_asserted <= rep.metrics.recall_post_recovery


# ---- invariants on REAL CUAD ----
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


def test_real_recall_post_is_full(real_report):
    rep, _ = real_report
    assert rep.metrics.recall_post_recovery == pytest.approx(1.0)


def test_real_lift_nonnegative(real_report):
    rep, _ = real_report
    assert rep.metrics.recall_lift >= 0


def test_real_asserted_le_post(real_report):
    rep, _ = real_report
    assert rep.metrics.recall_asserted <= rep.metrics.recall_post_recovery + 1e-9


def test_real_per_clause_gold_matches_data(real_report):
    rep, contracts = real_report
    for cm in rep.metrics.per_clause:
        expected = sum(len(c.gold.get(cm.clause_type, [])) for c in contracts)
        assert cm.gold_total == expected


def test_real_single_le_post(real_report):
    rep, _ = real_report
    assert rep.metrics.recall_single_shot <= rep.metrics.recall_post_recovery + 1e-9


def test_empty_run_zero_recall():
    from clauseledger.cuad import Contract
    c = Contract(id="empty", text="nothing here", gold={ct: [] for ct in CLAUSE_TYPES}, absent=list(CLAUSE_TYPES))
    rep = run(StubBackend(), [c], RunConfig(backend="stub", model="stub", abstain_threshold=0.5))
    assert rep.metrics.recall_post_recovery == 0.0
    assert rep.metrics.recall_lift == 0.0
