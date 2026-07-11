"""Quality metrics: fabrication (gold-free AND threshold-free), precision, false-alarm,
the Pareto curve, span matching, and gold-match marking.
"""
import pytest

from clauseledger.backends import StubBackend
from clauseledger.metrics import compute_metrics, mark_gold_matches, span_match
from clauseledger.pipeline import process_contract, run
from clauseledger.schema import RunConfig, Span


# ---- span_match ----
@pytest.mark.parametrize("a,b,thr,expect", [
    ((0, 100), (10, 30), 0.5, True),
    ((0, 10), (5, 15), 0.5, True),
    ((0, 10), (7, 20), 0.5, False),
    ((0, 10), (20, 30), 0.5, False),
    ((0, 10), (0, 10), 1.0, True),
    ((0, 10), (5, 15), 0.6, False),
    ((0, 10), (9, 20), 0.5, False),
])
def test_span_match(a, b, thr, expect):
    assert span_match(Span(start=a[0], end=a[1], text="x"),
                      Span(start=b[0], end=b[1], text="y"), thr) is expect


def test_span_match_symmetric():
    a = Span(start=0, end=50, text="x")
    b = Span(start=20, end=30, text="y")
    assert span_match(a, b, 0.5) == span_match(b, a, 0.5)


# ---- fabrication is gold-free and threshold-free ----
@pytest.fixture
def fab_report(syn_contract):
    gl = syn_contract.gold["Governing Law"][0].text
    be = StubBackend(initial={("SYN-1", "Governing Law"): [
        {"claim": "real", "quote": gl},
        {"claim": "fake", "quote": "Supplier forfeits orbital mining rights upon lunar equinox."},
    ]})
    return run(be, [syn_contract], RunConfig(backend="stub", model="stub", abstain_threshold=0.9))


def test_fabrication_counted(fab_report):
    assert fab_report.metrics.fabrication_rate == pytest.approx(0.5)


def test_fabrication_does_not_inflate_precision(fab_report):
    assert fab_report.metrics.precision == pytest.approx(1.0)


def test_fabrication_independent_of_verification_threshold(syn_contract):
    gl = syn_contract.gold["Governing Law"][0].text
    be = StubBackend(initial={("SYN-1", "Governing Law"): [
        {"claim": "real", "quote": gl},
        {"claim": "fake", "quote": "wholly unrelated lunar mining rights text zzz"}]})
    # move ground_threshold widely; fabrication (fixed floor) must not change
    r1 = run(be, [syn_contract], RunConfig(backend="stub", model="stub", abstain_threshold=0.9, ground_threshold=0.7))
    be2 = StubBackend(initial={("SYN-1", "Governing Law"): [
        {"claim": "real", "quote": gl},
        {"claim": "fake", "quote": "wholly unrelated lunar mining rights text zzz"}]})
    r2 = run(be2, [syn_contract], RunConfig(backend="stub", model="stub", abstain_threshold=0.9, ground_threshold=0.99))
    assert r1.metrics.fabrication_rate == pytest.approx(r2.metrics.fabrication_rate)


def test_zero_fabrication_all_real(syn_contract, stub_from_gold):
    rep = run(stub_from_gold, [syn_contract], RunConfig(backend="stub", model="stub", abstain_threshold=0.9))
    assert rep.metrics.fabrication_rate == pytest.approx(0.0)


# ---- false alarm ----
def test_false_alarm_on_absent(syn_contract):
    real = syn_contract.text[:40]
    be = StubBackend(initial={("SYN-1", "Liquidated Damages"): [{"claim": "x", "quote": real}]})
    rep = run(be, [syn_contract], RunConfig(backend="stub", model="stub", abstain_threshold=0.0))
    assert rep.metrics.false_alarm_rate > 0


def test_no_false_alarm_when_clean(syn_contract, stub_from_gold):
    rep = run(stub_from_gold, [syn_contract], RunConfig(backend="stub", model="stub", abstain_threshold=0.9))
    assert rep.metrics.false_alarm_rate == pytest.approx(0.0)


def test_fabrication_on_absent_not_false_alarm(syn_contract):
    # unsupported row on absent type -> fabrication, NOT false alarm
    be = StubBackend(initial={("SYN-1", "Liquidated Damages"): [
        {"claim": "x", "quote": "totally invented off-world penalty clause zzz"}]})
    rep = run(be, [syn_contract], RunConfig(backend="stub", model="stub", abstain_threshold=0.0))
    assert rep.metrics.false_alarm_rate == pytest.approx(0.0)
    assert rep.metrics.fabrication_rate > 0


# ---- precision ----
def test_precision_all_correct(syn_contract, stub_from_gold):
    rep = run(stub_from_gold, [syn_contract], RunConfig(backend="stub", model="stub", abstain_threshold=0.9))
    assert rep.metrics.precision == pytest.approx(1.0)


def test_precision_unit_interval(fab_report):
    assert 0.0 <= fab_report.metrics.precision <= 1.0


# ---- Pareto ----
@pytest.fixture
def pareto(syn_contract, stub_from_gold):
    rep = run(stub_from_gold, [syn_contract], RunConfig(backend="stub", model="stub", abstain_threshold=0.9))
    return rep.metrics.pareto


def test_pareto_21_points(pareto):
    assert len(pareto) == 21


def test_pareto_thresholds_ascending(pareto):
    ts = [p.threshold for p in pareto]
    assert ts == sorted(ts)


def test_pareto_recall_nonincreasing(pareto):
    r = [p.recall for p in pareto]
    assert all(r[i] >= r[i + 1] - 1e-9 for i in range(len(r) - 1))


def test_pareto_abstention_nondecreasing(pareto):
    a = [p.abstention for p in pareto]
    assert all(a[i] <= a[i + 1] + 1e-9 for i in range(len(a) - 1))


@pytest.mark.parametrize("field", ["precision", "recall", "abstention"])
def test_pareto_values_bounded(pareto, field):
    assert all(0.0 <= getattr(p, field) <= 1.0 for p in pareto)


def test_pareto_threshold_zero_no_abstention(pareto):
    assert pareto[0].abstention == pytest.approx(0.0)


# ---- mark_gold_matches ----
def test_mark_gold_unsupported_false(syn_contract):
    be = StubBackend(initial={("SYN-1", "Governing Law"): [{"claim": "f", "quote": "not present zzz qqq"}]})
    res = process_contract(be, syn_contract, RunConfig(backend="stub", model="stub", abstain_threshold=0.9),
                           gold=syn_contract.gold)
    assert all(r.matches_gold is False for r in res.rows)


def test_mark_gold_true_on_real(syn_contract, stub_from_gold):
    res = process_contract(stub_from_gold, syn_contract,
                           RunConfig(backend="stub", model="stub", abstain_threshold=0.9), gold=syn_contract.gold)
    supported = [r for r in res.rows if r.verdict.supported]
    assert supported and all(r.matches_gold for r in supported)


def test_mark_gold_no_cross_type_leak(syn_contract):
    # a real GL quote emitted under Cap On Liability must NOT match CoL gold
    gl = syn_contract.gold["Governing Law"][0].text
    be = StubBackend(initial={("SYN-1", "Cap On Liability"): [{"claim": "x", "quote": gl}]})
    res = process_contract(be, syn_contract, RunConfig(backend="stub", model="stub", abstain_threshold=0.0),
                           gold=syn_contract.gold)
    col = [r for r in res.rows if r.clause_type == "Cap On Liability"]
    assert all(r.matches_gold is False for r in col)


def test_compute_metrics_empty():
    m = compute_metrics([], [], 0.5, 0.6)
    assert m.n_contracts == 0 and m.recall_post_recovery == 0.0
