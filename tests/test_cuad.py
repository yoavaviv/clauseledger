"""Tests for clauseledger.cuad.load_subset against the REAL CUAD subset.

These lean on the `real_subset` session fixture. The central guarantee we assert is
grounding: every gold span must be independently checkable, i.e. text[start:end] must
equal span.text exactly. We also pin the structural invariants the rest of the harness
relies on (categories == CLAUSE_TYPES, split partitioning, absent/gold disjointness).
"""
import dataclasses
from pathlib import Path

import pytest

from clauseledger.cuad import Contract, CuadSubset, load_subset, _DEFAULT
from clauseledger.schema import CLAUSE_TYPES, Span


# Load once at module import purely to drive parametrization ids. Tests that touch the
# data use the `real_subset` fixture; this is only so pytest can name one case per contract.
_SUBSET = load_subset()
_CONTRACT_IDS = [c.id for c in _SUBSET.contracts]
_SPLITS = ["dev", "test"]


# --- top-level shape ---------------------------------------------------------------

def test_load_subset_returns_cuadsubset(real_subset):
    assert isinstance(real_subset, CuadSubset)


def test_categories_equals_clause_types(real_subset):
    # Exact list equality, order included: the categories ARE the 6 clause types.
    assert real_subset.categories == CLAUSE_TYPES


def test_source_is_nonempty_str(real_subset):
    assert isinstance(real_subset.source, str) and real_subset.source.strip()


def test_contracts_nonempty(real_subset):
    assert len(real_subset.contracts) > 0


def test_every_contract_is_contract_instance(real_subset):
    assert all(isinstance(c, Contract) for c in real_subset.contracts)


def test_contract_dataclass_fields(real_subset):
    names = {f.name for f in dataclasses.fields(Contract)}
    assert names == {"id", "text", "gold", "absent", "split"}
    c = real_subset.contracts[0]
    assert isinstance(c.id, str)
    assert isinstance(c.text, str)
    assert isinstance(c.gold, dict)
    assert isinstance(c.absent, list)
    assert isinstance(c.split, str)


def test_contract_split_default_is_test():
    c = Contract(id="X", text="hello", gold={}, absent=[])
    assert c.split == "test"


# --- per-contract invariants (parametrized: one case per real contract) ------------

@pytest.mark.parametrize("cid", _CONTRACT_IDS)
def test_contract_has_text(real_subset, cid):
    c = next(c for c in real_subset.contracts if c.id == cid)
    assert isinstance(c.text, str) and len(c.text) > 0


@pytest.mark.parametrize("cid", _CONTRACT_IDS)
def test_contract_split_in_dev_or_test(real_subset, cid):
    c = next(c for c in real_subset.contracts if c.id == cid)
    assert c.split in {"dev", "test"}


@pytest.mark.parametrize("cid", _CONTRACT_IDS)
def test_contract_gold_keys_are_clause_types(real_subset, cid):
    c = next(c for c in real_subset.contracts if c.id == cid)
    assert set(c.gold.keys()) == set(CLAUSE_TYPES)


@pytest.mark.parametrize("cid", _CONTRACT_IDS)
def test_every_gold_span_self_grounds(real_subset, cid):
    """The core reliability claim: each gold span's char offsets slice out exactly
    its recorded text, and lie within the document."""
    c = next(c for c in real_subset.contracts if c.id == cid)
    for ct, spans in c.gold.items():
        for sp in spans:
            assert isinstance(sp, Span)
            assert 0 <= sp.start <= sp.end <= len(c.text)
            assert c.text[sp.start:sp.end] == sp.text


@pytest.mark.parametrize("cid", _CONTRACT_IDS)
def test_gold_spans_nonempty_text(real_subset, cid):
    c = next(c for c in real_subset.contracts if c.id == cid)
    for spans in c.gold.values():
        for sp in spans:
            assert sp.text != ""
            assert sp.end > sp.start


@pytest.mark.parametrize("cid", _CONTRACT_IDS)
def test_gold_count_positive(real_subset, cid):
    c = next(c for c in real_subset.contracts if c.id == cid)
    assert c.gold_count() > 0


@pytest.mark.parametrize("cid", _CONTRACT_IDS)
def test_gold_count_matches_sum(real_subset, cid):
    c = next(c for c in real_subset.contracts if c.id == cid)
    assert c.gold_count() == sum(len(v) for v in c.gold.values())


@pytest.mark.parametrize("cid", _CONTRACT_IDS)
def test_absent_and_present_gold_disjoint(real_subset, cid):
    c = next(c for c in real_subset.contracts if c.id == cid)
    present = {ct for ct, spans in c.gold.items() if spans}
    assert set(c.absent) & present == set()


@pytest.mark.parametrize("cid", _CONTRACT_IDS)
def test_absent_subset_of_clause_types(real_subset, cid):
    c = next(c for c in real_subset.contracts if c.id == cid)
    assert set(c.absent) <= set(CLAUSE_TYPES)


@pytest.mark.parametrize("cid", _CONTRACT_IDS)
def test_absent_clause_types_have_empty_gold(real_subset, cid):
    c = next(c for c in real_subset.contracts if c.id == cid)
    for a in c.absent:
        assert c.gold.get(a) == []


@pytest.mark.parametrize("cid", _CONTRACT_IDS)
def test_present_and_absent_partition_all_clause_types(real_subset, cid):
    """A clause type is either present (has gold) or declared absent, never both,
    never neither: the two sets partition all 6."""
    c = next(c for c in real_subset.contracts if c.id == cid)
    present = {ct for ct, spans in c.gold.items() if spans}
    assert present | set(c.absent) == set(CLAUSE_TYPES)
    assert present.isdisjoint(set(c.absent))


# --- collection-wide invariants ----------------------------------------------------

def test_contract_ids_unique(real_subset):
    ids = [c.id for c in real_subset.contracts]
    assert len(ids) == len(set(ids))


def test_all_contracts_have_gold(real_subset):
    assert all(c.gold_count() > 0 for c in real_subset.contracts)


def test_total_gold_spans_positive(real_subset):
    total = sum(c.gold_count() for c in real_subset.contracts)
    assert total > 0


# --- split() helper ----------------------------------------------------------------

@pytest.mark.parametrize("name", _SPLITS)
def test_split_returns_only_that_split(real_subset, name):
    got = real_subset.split(name)
    assert len(got) > 0
    assert all(c.split == name for c in got)


def test_split_partitions_contracts(real_subset):
    dev = real_subset.split("dev")
    test = real_subset.split("test")
    assert len(dev) + len(test) == len(real_subset.contracts)
    dev_ids = {c.id for c in dev}
    test_ids = {c.id for c in test}
    assert dev_ids.isdisjoint(test_ids)


def test_split_unknown_name_returns_empty(real_subset):
    assert real_subset.split("nonexistent-split") == []


def test_split_returns_actual_contract_objects(real_subset):
    dev = real_subset.split("dev")
    assert all(isinstance(c, Contract) for c in dev)


# --- loading semantics -------------------------------------------------------------

def test_default_path_points_to_subset_json():
    assert _DEFAULT.name == "subset.json"
    assert _DEFAULT.exists()


def test_load_with_explicit_str_path_matches_default(real_subset):
    reloaded = load_subset(str(_DEFAULT))
    assert reloaded.categories == real_subset.categories
    assert len(reloaded.contracts) == len(real_subset.contracts)
    assert {c.id for c in reloaded.contracts} == {c.id for c in real_subset.contracts}


def test_load_with_explicit_pathlib_path_matches_default(real_subset):
    reloaded = load_subset(Path(_DEFAULT))
    assert len(reloaded.contracts) == len(real_subset.contracts)


def test_reload_reproduces_grounding(real_subset):
    # Loading fresh yields the same grounded spans (loader is deterministic).
    reloaded = load_subset()
    by_id = {c.id: c for c in reloaded.contracts}
    for c in real_subset.contracts:
        r = by_id[c.id]
        assert r.gold_count() == c.gold_count()
        assert r.text == c.text
