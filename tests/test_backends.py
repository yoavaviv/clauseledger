"""Tests for clauseledger.backends: StubBackend, RecordingBackend, ReplayBackend,
and the get_backend factory. OllamaBackend is deliberately out of scope here.

These exercise the model-agnostic contract every backend obeys:
  extract(...) -> Candidates tagged Source.INITIAL
  recover(...) -> Candidates tagged Source.RECOVERY
keyed by (contract_id, clause_type), empty for unset keys, and the record ->
dump -> replay roundtrip that lets a real run be frozen and replayed offline.
"""
import json

import pytest

from clauseledger.backends import (
    RecordingBackend,
    ReplayBackend,
    StubBackend,
    get_backend,
)
from clauseledger.pipeline import process_contract
from clauseledger.schema import Candidate, RunConfig, Source


def _cfg():
    return RunConfig(backend="stub", model="stub", abstain_threshold=0.5)


# --------------------------------------------------------------------------- #
# StubBackend
# --------------------------------------------------------------------------- #
def test_stub_extract_returns_configured_initial():
    stub = StubBackend(
        initial={("C1", "Governing Law"): [{"claim": "gl", "quote": "Delaware law governs"}]}
    )
    out = stub.extract("C1", "any text", "Governing Law")
    assert len(out) == 1
    assert out[0].quote == "Delaware law governs"
    assert out[0].claim == "gl"


def test_stub_extract_returns_candidate_objects():
    stub = StubBackend(initial={("C1", "Cap On Liability"): [{"claim": "c", "quote": "q"}]})
    out = stub.extract("C1", "text", "Cap On Liability")
    assert all(isinstance(c, Candidate) for c in out)


def test_stub_extract_source_is_initial():
    stub = StubBackend(initial={("C1", "Renewal Term"): [{"claim": "r", "quote": "renews"}]})
    out = stub.extract("C1", "text", "Renewal Term")
    assert out[0].source == Source.INITIAL


def test_stub_recover_source_is_recovery():
    stub = StubBackend(recovery={("C1", "Renewal Term"): [{"claim": "r", "quote": "renews"}]})
    out = stub.recover("C1", "text", "Renewal Term", found_quotes=[])
    assert out[0].source == Source.RECOVERY


def test_stub_extract_carries_clause_type_through():
    stub = StubBackend(initial={("C1", "Post-Termination Services"): [{"claim": "p", "quote": "q"}]})
    out = stub.extract("C1", "text", "Post-Termination Services")
    assert out[0].clause_type == "Post-Termination Services"


def test_stub_unset_key_returns_empty_extract():
    stub = StubBackend(initial={("C1", "Governing Law"): [{"claim": "g", "quote": "q"}]})
    assert stub.extract("C1", "text", "Cap On Liability") == []


def test_stub_unset_contract_returns_empty():
    stub = StubBackend(initial={("C1", "Governing Law"): [{"claim": "g", "quote": "q"}]})
    assert stub.extract("OTHER", "text", "Governing Law") == []


def test_stub_recover_unset_key_returns_empty():
    stub = StubBackend(recovery={("C1", "Renewal Term"): [{"claim": "r", "quote": "q"}]})
    assert stub.recover("C1", "text", "Governing Law", found_quotes=[]) == []


def test_stub_defaults_are_empty():
    stub = StubBackend()
    assert stub.extract("X", "t", "Governing Law") == []
    assert stub.recover("X", "t", "Governing Law", []) == []


def test_stub_initial_and_recovery_are_independent():
    stub = StubBackend(
        initial={("C1", "Renewal Term"): [{"claim": "i", "quote": "iq"}]},
        recovery={("C1", "Renewal Term"): [{"claim": "r", "quote": "rq"}]},
    )
    assert stub.extract("C1", "t", "Renewal Term")[0].quote == "iq"
    assert stub.recover("C1", "t", "Renewal Term", [])[0].quote == "rq"


def test_stub_recover_ignores_found_quotes_argument():
    stub = StubBackend(recovery={("C1", "Renewal Term"): [{"claim": "r", "quote": "rq"}]})
    a = stub.recover("C1", "t", "Renewal Term", found_quotes=[])
    b = stub.recover("C1", "t", "Renewal Term", found_quotes=["anything", "here"])
    assert [c.quote for c in a] == [c.quote for c in b] == ["rq"]


def test_stub_extract_ignores_text_argument():
    stub = StubBackend(initial={("C1", "Governing Law"): [{"claim": "g", "quote": "q"}]})
    assert stub.extract("C1", "text A", "Governing Law")[0].quote == "q"
    assert stub.extract("C1", "totally different", "Governing Law")[0].quote == "q"


def test_stub_multiple_rows_preserved_in_order():
    rows = [{"claim": f"c{i}", "quote": f"q{i}"} for i in range(3)]
    stub = StubBackend(initial={("C1", "Governing Law"): rows})
    out = stub.extract("C1", "t", "Governing Law")
    assert [c.quote for c in out] == ["q0", "q1", "q2"]


@pytest.mark.parametrize("quote", ["", "  ", "clause 42 — governs", "règle générale ünïcode", "🚀 emoji clause"])
def test_stub_handles_edge_case_quotes(quote):
    stub = StubBackend(initial={("C1", "Governing Law"): [{"claim": "c", "quote": quote}]})
    out = stub.extract("C1", "t", "Governing Law")
    assert out[0].quote == quote


def test_stub_name_and_model():
    stub = StubBackend()
    assert stub.name == "stub"
    assert stub.model == "stub"


# --------------------------------------------------------------------------- #
# RecordingBackend
# --------------------------------------------------------------------------- #
def test_recording_passes_through_extract():
    inner = StubBackend(initial={("C1", "Governing Law"): [{"claim": "g", "quote": "q"}]})
    rec = RecordingBackend(inner)
    out = rec.extract("C1", "t", "Governing Law")
    assert [c.quote for c in out] == ["q"]


def test_recording_captures_initial_into_cache():
    inner = StubBackend(initial={("C1", "Governing Law"): [{"claim": "g", "quote": "q"}]})
    rec = RecordingBackend(inner)
    rec.extract("C1", "t", "Governing Law")
    assert rec.cache["C1"]["Governing Law"]["initial"] == [{"claim": "g", "quote": "q"}]


def test_recording_captures_recovery_into_cache():
    inner = StubBackend(recovery={("C1", "Renewal Term"): [{"claim": "r", "quote": "rq"}]})
    rec = RecordingBackend(inner)
    rec.recover("C1", "t", "Renewal Term", found_quotes=[])
    assert rec.cache["C1"]["Renewal Term"]["recovery"] == [{"claim": "r", "quote": "rq"}]


def test_recording_name_prefixes_inner():
    rec = RecordingBackend(StubBackend())
    assert rec.name == "recording:stub"


def test_recording_model_mirrors_inner():
    rec = RecordingBackend(StubBackend())
    assert rec.model == "stub"


def test_recording_dump_shape():
    rec = RecordingBackend(StubBackend(initial={("C1", "Governing Law"): [{"claim": "g", "quote": "q"}]}))
    rec.extract("C1", "t", "Governing Law")
    dumped = rec.dump()
    assert set(dumped.keys()) == {"model", "cache"}
    assert dumped["model"] == "stub"
    assert dumped["cache"]["C1"]["Governing Law"]["initial"][0]["quote"] == "q"


def test_recording_empty_result_records_empty_list():
    rec = RecordingBackend(StubBackend())
    rec.extract("C1", "t", "Governing Law")
    assert rec.cache["C1"]["Governing Law"]["initial"] == []


def test_recording_via_process_contract_records_all_clause_types(syn_contract, stub_from_gold):
    rec = RecordingBackend(stub_from_gold)
    process_contract(rec, syn_contract, _cfg(), gold=syn_contract.gold)
    dumped = rec.dump()
    # process_contract iterates every clause type, both passes -> all recorded
    from clauseledger.schema import CLAUSE_TYPES
    node = dumped["cache"][syn_contract.id]
    assert set(node.keys()) == set(CLAUSE_TYPES)
    for ct in CLAUSE_TYPES:
        assert set(node[ct].keys()) == {"initial", "recovery"}


def test_recording_captures_gold_quotes_through_pipeline(syn_contract, stub_from_gold):
    rec = RecordingBackend(stub_from_gold)
    process_contract(rec, syn_contract, _cfg(), gold=syn_contract.gold)
    node = rec.cache[syn_contract.id]
    # Governing Law lives in the initial pass per the fixture
    gl_quotes = [r["quote"] for r in node["Governing Law"]["initial"]]
    assert "governed by the laws of the State of Delaware" in gl_quotes
    # Notice Period was placed in the recovery pass by the fixture
    np_quotes = [r["quote"] for r in node["Notice Period To Terminate Renewal"]["recovery"]]
    assert "ninety (90) days written notice" in np_quotes


# --------------------------------------------------------------------------- #
# ReplayBackend (roundtrip through a RecordingBackend.dump() cache file)
# --------------------------------------------------------------------------- #
def _record_syn(syn_contract, stub_from_gold, tmp_path):
    rec = RecordingBackend(stub_from_gold)
    process_contract(rec, syn_contract, _cfg(), gold=syn_contract.gold)
    p = tmp_path / "cache.json"
    p.write_text(json.dumps(rec.dump()), encoding="utf-8")
    return p


def test_replay_roundtrip_extract(syn_contract, stub_from_gold, tmp_path):
    path = _record_syn(syn_contract, stub_from_gold, tmp_path)
    replay = ReplayBackend(path)
    out = replay.extract(syn_contract.id, syn_contract.text, "Governing Law")
    assert "governed by the laws of the State of Delaware" in [c.quote for c in out]


def test_replay_roundtrip_recovery(syn_contract, stub_from_gold, tmp_path):
    path = _record_syn(syn_contract, stub_from_gold, tmp_path)
    replay = ReplayBackend(path)
    out = replay.recover(syn_contract.id, syn_contract.text, "Notice Period To Terminate Renewal", [])
    assert "ninety (90) days written notice" in [c.quote for c in out]


def test_replay_extract_source_is_initial(syn_contract, stub_from_gold, tmp_path):
    path = _record_syn(syn_contract, stub_from_gold, tmp_path)
    replay = ReplayBackend(path)
    out = replay.extract(syn_contract.id, syn_contract.text, "Governing Law")
    assert all(c.source == Source.INITIAL for c in out)


def test_replay_recover_source_is_recovery(syn_contract, stub_from_gold, tmp_path):
    path = _record_syn(syn_contract, stub_from_gold, tmp_path)
    replay = ReplayBackend(path)
    out = replay.recover(syn_contract.id, syn_contract.text, "Notice Period To Terminate Renewal", [])
    assert all(c.source == Source.RECOVERY for c in out)


def test_replay_model_read_from_cache(syn_contract, stub_from_gold, tmp_path):
    path = _record_syn(syn_contract, stub_from_gold, tmp_path)
    replay = ReplayBackend(path)
    assert replay.model == "stub"


def test_replay_unknown_contract_returns_empty(syn_contract, stub_from_gold, tmp_path):
    path = _record_syn(syn_contract, stub_from_gold, tmp_path)
    replay = ReplayBackend(path)
    assert replay.extract("NOPE", "t", "Governing Law") == []
    assert replay.recover("NOPE", "t", "Governing Law", []) == []


def test_replay_unknown_clause_returns_empty(syn_contract, stub_from_gold, tmp_path):
    path = _record_syn(syn_contract, stub_from_gold, tmp_path)
    replay = ReplayBackend(path)
    assert replay.extract(syn_contract.id, "t", "Made Up Clause") == []


def test_replay_default_model_when_absent(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"cache": {}}), encoding="utf-8")
    replay = ReplayBackend(p)
    assert replay.model == "replay"


def test_replay_accepts_str_path(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"model": "m", "cache": {"C1": {"Governing Law": {"initial": [{"claim": "c", "quote": "q"}]}}}}), encoding="utf-8")
    replay = ReplayBackend(str(p))
    out = replay.extract("C1", "t", "Governing Law")
    assert out[0].quote == "q"


def test_replay_missing_cache_key_raises(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"model": "m"}), encoding="utf-8")
    with pytest.raises(KeyError):
        ReplayBackend(p)


def test_replay_name():
    # name is a class attribute, available without instantiation
    assert ReplayBackend.name == "replay"


def test_replay_equivalent_to_stub_through_pipeline(syn_contract, stub_from_gold, tmp_path):
    # A full pipeline run on the replayed cache should reproduce the recorded rows.
    path = _record_syn(syn_contract, stub_from_gold, tmp_path)
    replay = ReplayBackend(path)
    stub_result = process_contract(stub_from_gold, syn_contract, _cfg(), gold=syn_contract.gold)
    replay_result = process_contract(replay, syn_contract, _cfg(), gold=syn_contract.gold)
    stub_quotes = sorted(r.quote for r in stub_result.rows)
    replay_quotes = sorted(r.quote for r in replay_result.rows)
    assert stub_quotes == replay_quotes


# --------------------------------------------------------------------------- #
# get_backend factory
# --------------------------------------------------------------------------- #
def test_get_backend_stub():
    b = get_backend("stub")
    assert isinstance(b, StubBackend)


def test_get_backend_stub_passes_kwargs():
    b = get_backend("stub", initial={("C1", "Governing Law"): [{"claim": "g", "quote": "q"}]})
    assert b.extract("C1", "t", "Governing Law")[0].quote == "q"


def test_get_backend_case_insensitive():
    assert isinstance(get_backend("STUB"), StubBackend)
    assert isinstance(get_backend("Stub"), StubBackend)


def test_get_backend_replay(syn_contract, stub_from_gold, tmp_path):
    path = _record_syn(syn_contract, stub_from_gold, tmp_path)
    b = get_backend("replay", cache_path=str(path))
    assert isinstance(b, ReplayBackend)


@pytest.mark.parametrize("name", ["unknown", "gpt", "", "stubb", "ollamaa"])
def test_get_backend_unknown_raises_valueerror(name):
    with pytest.raises(ValueError):
        get_backend(name)
