"""Bootstrap confidence intervals for the headline metrics.

The point of CIs on this project is honesty about a small test set: the interval must be
well-formed, bracket-ordered, in range, and deterministic (so the frozen demo number
reproduces). These tests pin those invariants without depending on the (model-produced,
mutable) replay cache.
"""
from __future__ import annotations

from clauseledger.backends import StubBackend
from clauseledger.cuad import Contract
from clauseledger.metrics import _CI_METRICS, _percentile, bootstrap_metrics
from clauseledger.pipeline import run
from clauseledger.schema import RunConfig


def _multi(syn_text, syn_gold, n=5):
    """n synthetic contracts (distinct ids, same gold) + a stub that returns the gold."""
    contracts, initial, recovery = [], {}, {}
    for k in range(n):
        cid = f"SYN-{k}"
        contracts.append(Contract(id=cid, text=syn_text, gold=syn_gold,
                                   absent=["Liquidated Damages"], split="test"))
        for ct, spans in syn_gold.items():
            if not spans:
                continue
            rows = [{"claim": f"{ct} obligation", "quote": s.text} for s in spans]
            (recovery if ct == "Notice Period To Terminate Renewal" else initial)[(cid, ct)] = rows
    return contracts, StubBackend(initial=initial, recovery=recovery)


def _results(syn_text, syn_gold, n=5):
    contracts, be = _multi(syn_text, syn_gold, n)
    cfg = RunConfig(backend="stub", model="stub", abstain_threshold=0.5)
    rep = run(be, contracts, cfg)
    return rep.contracts, contracts


def test_ci_has_all_headline_metrics(syn_text, syn_gold):
    res, contracts = _results(syn_text, syn_gold)
    ci = bootstrap_metrics(res, contracts, n_boot=200)
    assert set(ci.keys()) == set(_CI_METRICS)


def test_ci_is_bracket_ordered_and_in_range(syn_text, syn_gold):
    res, contracts = _results(syn_text, syn_gold)
    ci = bootstrap_metrics(res, contracts, n_boot=200)
    for k, c in ci.items():
        assert 0.0 <= c.lo <= c.hi <= 1.0, f"{k}: {c.lo}..{c.hi}"
        assert c.n_boot == 200 and c.level == 0.95


def test_ci_is_deterministic(syn_text, syn_gold):
    res, contracts = _results(syn_text, syn_gold)
    a = bootstrap_metrics(res, contracts, n_boot=200, seed=0)
    b = bootstrap_metrics(res, contracts, n_boot=200, seed=0)
    assert {k: (v.lo, v.hi) for k, v in a.items()} == {k: (v.lo, v.hi) for k, v in b.items()}


def test_ci_brackets_point_estimate_when_data_is_homogeneous(syn_text, syn_gold):
    # identical contracts -> every resample is identical -> zero-width CI at the point value
    res, contracts = _results(syn_text, syn_gold, n=5)
    ci = bootstrap_metrics(res, contracts, n_boot=100)
    for c in ci.values():
        assert c.lo == c.hi  # no variation across resamples of identical contracts


def test_bootstrap_returns_empty_for_singleton():
    assert bootstrap_metrics([], []) == {}


def test_percentile_interpolates():
    vals = [0.0, 1.0]
    assert _percentile(vals, 0.0) == 0.0
    assert _percentile(vals, 1.0) == 1.0
    assert _percentile(vals, 0.5) == 0.5
    assert _percentile([0.4], 0.9) == 0.4  # single value
