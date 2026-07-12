"""Tests for the commercial-severity gold kit (over the synthetic example fixture)."""
from pathlib import Path

import pytest

from clauseledger.schema import CLAUSE_TYPES
from clauseledger.severity_gold import (SeverityGold, derive_score, kendall_tau,
                                        load_heldout_contracts, load_severity_gold,
                                        provisional_ranking, rank_agreement,
                                        rubric_from_gold)

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "data" / "severity_gold" / "annotations.example.json"
STUB = ROOT / "data" / "severity_gold" / "annotations.json"


@pytest.fixture
def gold() -> SeverityGold:
    return load_severity_gold(EXAMPLE)


# ---- score derivation ----

def test_derive_score_bounds_and_monotonic():
    assert derive_score(1, 1) == pytest.approx(0.2)
    assert derive_score(5, 5) == pytest.approx(1.0)
    assert derive_score(5, 1) > derive_score(1, 5)  # money weighted above time
    assert 0.0 <= derive_score(3, 3) <= 1.0


# ---- loading + validation ----

def test_example_loads_and_covers_all_types(gold):
    assert gold.is_populated
    assert {t.clause_type for t in gold.types} == set(CLAUSE_TYPES)
    assert len(gold.entries) >= 5


def test_axes_out_of_range_rejected():
    import json
    raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    raw["types"][0]["money_at_risk"] = 6
    with pytest.raises(Exception):
        SeverityGold.model_validate(raw)


def test_unknown_clause_type_rejected():
    import json
    raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    raw["types"][0]["clause_type"] = "Made Up Clause"
    with pytest.raises(Exception):
        SeverityGold.model_validate(raw)


def test_stub_is_empty_but_valid():
    stub = load_severity_gold(STUB)
    assert not stub.is_populated
    assert stub.types == [] and stub.entries == []
    assert rank_agreement(stub) is None  # nothing to compare yet


# ---- rankings + agreement ----

def test_ranking_orders_by_score(gold):
    ranking = gold.ranking()
    assert len(ranking) == len(CLAUSE_TYPES)
    scores = {t.clause_type: t.score for t in gold.types}
    assert scores[ranking[0]] >= scores[ranking[-1]]


def test_kendall_tau_identity_and_reverse():
    seq = ["a", "b", "c", "d"]
    assert kendall_tau(seq, seq) == 1.0
    assert kendall_tau(seq, list(reversed(seq))) == -1.0
    assert kendall_tau(["a"], ["a"]) == 0.0  # too few common items


def test_rank_agreement_in_range(gold):
    tau = rank_agreement(gold)
    assert tau is not None
    assert -1.0 <= tau <= 1.0


def test_provisional_ranking_is_all_types():
    assert set(provisional_ranking()) == set(CLAUSE_TYPES)


def test_rubric_from_gold_shape(gold):
    rubric = rubric_from_gold(gold)
    assert set(rubric.keys()) == set(CLAUSE_TYPES)
    for tier, score, rationale, kind in rubric.values():
        assert tier in {"critical", "high", "medium", "low"}
        assert 0.0 <= score <= 1.0
        assert isinstance(rationale, str) and rationale
        assert kind in {"obligation", "allocation", "mechanic"}


# ---- held-out contract assembly (raw texts are gitignored; synthesise them in tmp) ----

def test_load_heldout_contracts_from_local_texts(tmp_path, gold):
    raw = tmp_path / "raw"
    raw.mkdir()
    # write a text containing one of the example quotes so it can be located
    quote = gold.entries[0].quote
    msa_id = gold.entries[0].msa_id
    (raw / f"{msa_id}.txt").write_text(f"PREAMBLE. {quote} And more text.", encoding="utf-8")
    contracts = load_heldout_contracts(gold, raw_dir=raw)
    assert len(contracts) == 1
    c = contracts[0]
    assert c.id == msa_id and c.split == "heldout"
    # the located quote is attached as a gold span for its clause type
    assert any(spans for spans in c.gold.values())


def test_load_heldout_contracts_skips_missing_texts(tmp_path, gold):
    # empty raw dir -> no contracts (committed repo ships labels, not the MSAs)
    contracts = load_heldout_contracts(gold, raw_dir=tmp_path)
    assert contracts == []
