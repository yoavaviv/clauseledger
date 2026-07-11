"""Tests for OllamaBackend WITHOUT a live model.

Everything here exercises the pure/parse/window logic and the extract/recover
control flow with a monkeypatched `_call`, so no network is ever touched.
"""
import pytest

from clauseledger.backends import OllamaBackend
from clauseledger.schema import CLAUSE_TYPES, Source


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def make_backend(**kw):
    return OllamaBackend(**kw)


def all_types_present(parsed):
    return set(parsed.keys()) == set(CLAUSE_TYPES)


# --------------------------------------------------------------------------- #
# _parse_multi
# --------------------------------------------------------------------------- #
def test_parse_multi_valid_multi_type():
    resp = ('{"Governing Law":[{"claim":"gov","quote":"laws of Delaware"}],'
            '"Cap On Liability":[{"claim":"cap","quote":"liability shall not exceed"}]}')
    out = OllamaBackend._parse_multi(resp)
    assert all_types_present(out)
    assert out["Governing Law"] == [{"claim": "gov", "quote": "laws of Delaware"}]
    assert out["Cap On Liability"] == [{"claim": "cap", "quote": "liability shall not exceed"}]
    # untouched types stay empty
    assert out["Liquidated Damages"] == []


def test_parse_multi_returns_all_clause_types_keys():
    out = OllamaBackend._parse_multi('{"Governing Law":[{"quote":"x"}]}')
    assert all_types_present(out)
    for ct in CLAUSE_TYPES:
        assert isinstance(out[ct], list)


def test_parse_multi_multiple_items_one_type():
    resp = ('{"Renewal Term":['
            '{"claim":"a","quote":"renews annually"},'
            '{"claim":"b","quote":"successive one-year periods"}]}')
    out = OllamaBackend._parse_multi(resp)
    assert len(out["Renewal Term"]) == 2
    assert out["Renewal Term"][0]["quote"] == "renews annually"
    assert out["Renewal Term"][1]["quote"] == "successive one-year periods"


def test_parse_multi_json_embedded_in_prose():
    resp = ('Sure, here is the analysis you asked for:\n'
            '{"Governing Law":[{"claim":"c","quote":"State of Delaware"}]}\n'
            'Let me know if you need more.')
    out = OllamaBackend._parse_multi(resp)
    assert out["Governing Law"] == [{"claim": "c", "quote": "State of Delaware"}]


def test_parse_multi_json_in_code_fence():
    resp = '```json\n{"Cap On Liability":[{"claim":"c","quote":"capped at fees paid"}]}\n```'
    out = OllamaBackend._parse_multi(resp)
    assert out["Cap On Liability"] == [{"claim": "c", "quote": "capped at fees paid"}]


@pytest.mark.parametrize("resp", [
    "this is not json at all",
    "no braces here, just words",
    "{ this is broken and unbalanced",
    "{'python': 'dict style not valid json and no close",
])
def test_parse_multi_malformed_returns_empty(resp):
    out = OllamaBackend._parse_multi(resp)
    assert all_types_present(out)
    assert all(out[ct] == [] for ct in CLAUSE_TYPES)


@pytest.mark.parametrize("resp", ["", "   ", "\n\t  \n", None])
def test_parse_multi_empty_string_returns_empty(resp):
    out = OllamaBackend._parse_multi(resp)
    assert all_types_present(out)
    assert all(out[ct] == [] for ct in CLAUSE_TYPES)


def test_parse_multi_non_dict_json_returns_empty():
    # valid JSON but a list, not a mapping
    out = OllamaBackend._parse_multi('[1, 2, 3]')
    assert all(out[ct] == [] for ct in CLAUSE_TYPES)


def test_parse_multi_item_missing_quote_skipped():
    resp = ('{"Governing Law":[{"claim":"has no quote"},'
            '{"claim":"good","quote":"kept"}]}')
    out = OllamaBackend._parse_multi(resp)
    assert out["Governing Law"] == [{"claim": "good", "quote": "kept"}]


def test_parse_multi_empty_quote_skipped():
    resp = '{"Governing Law":[{"claim":"c","quote":""}]}'
    out = OllamaBackend._parse_multi(resp)
    assert out["Governing Law"] == []


def test_parse_multi_dict_instead_of_list_coerced():
    resp = '{"Cap On Liability":{"claim":"single","quote":"one obligation"}}'
    out = OllamaBackend._parse_multi(resp)
    assert out["Cap On Liability"] == [{"claim": "single", "quote": "one obligation"}]


def test_parse_multi_unknown_keys_ignored():
    resp = ('{"TotallyMadeUpType":[{"claim":"c","quote":"q"}],'
            '"Another Fake":[{"claim":"c","quote":"q"}],'
            '"Governing Law":[{"claim":"real","quote":"kept"}]}')
    out = OllamaBackend._parse_multi(resp)
    assert all_types_present(out)
    assert "TotallyMadeUpType" not in out
    assert out["Governing Law"] == [{"claim": "real", "quote": "kept"}]


def test_parse_multi_claim_defaults_to_empty_string():
    out = OllamaBackend._parse_multi('{"Governing Law":[{"quote":"only a quote"}]}')
    assert out["Governing Law"] == [{"claim": "", "quote": "only a quote"}]


def test_parse_multi_strips_whitespace():
    resp = '{"Governing Law":[{"claim":"  spaced claim  ","quote":"\\n padded quote \\t"}]}'
    out = OllamaBackend._parse_multi(resp)
    assert out["Governing Law"] == [{"claim": "spaced claim", "quote": "padded quote"}]


def test_parse_multi_null_list_value_handled():
    # a clause type mapped to null should not blow up
    out = OllamaBackend._parse_multi('{"Governing Law":null,"Cap On Liability":[{"quote":"q"}]}')
    assert out["Governing Law"] == []
    assert out["Cap On Liability"] == [{"claim": "", "quote": "q"}]


def test_parse_multi_unicode_quote_preserved():
    resp = '{"Governing Law":[{"claim":"c","quote":"gövérned — naïve €50 中文"}]}'
    out = OllamaBackend._parse_multi(resp)
    assert out["Governing Law"][0]["quote"] == "gövérned — naïve €50 中文"


def test_parse_multi_non_string_quote_coerced_to_str():
    # quote given as a number: truthy, coerced with str()
    out = OllamaBackend._parse_multi('{"Governing Law":[{"claim":"c","quote":42}]}')
    assert out["Governing Law"] == [{"claim": "c", "quote": "42"}]


def test_parse_multi_non_dict_items_in_list_skipped():
    resp = '{"Governing Law":["a bare string", 123, {"claim":"c","quote":"kept"}]}'
    out = OllamaBackend._parse_multi(resp)
    assert out["Governing Law"] == [{"claim": "c", "quote": "kept"}]


# --------------------------------------------------------------------------- #
# _windows
# --------------------------------------------------------------------------- #
def test_windows_short_text_single_window():
    b = make_backend(window_chars=9000, overlap=800)
    text = "short contract text"
    wins = list(b._windows(text))
    assert len(wins) == 1
    start, chunk = wins[0]
    assert start == 0
    assert chunk == text


def test_windows_cover_whole_text():
    b = make_backend(window_chars=10, overlap=3)
    text = "".join(chr(ord("a") + (i % 26)) for i in range(53))
    covered = [False] * len(text)
    for start, chunk in b._windows(text):
        assert text[start:start + len(chunk)] == chunk
        for i in range(start, start + len(chunk)):
            covered[i] = True
    assert all(covered), "every character must be covered by some window"


def test_windows_overlap_present():
    b = make_backend(window_chars=10, overlap=3)
    text = "x" * 40
    starts = [s for s, _ in b._windows(text)]
    step = b.window_chars - b.overlap
    assert step == 7
    # consecutive windows advance by exactly `step`, so they overlap by `overlap`
    for a, c in zip(starts, starts[1:]):
        assert c - a == step
        overlap = (a + b.window_chars) - c
        assert overlap == b.overlap


def test_windows_length_never_exceeds_window_chars():
    b = make_backend(window_chars=10, overlap=3)
    text = "y" * 100
    for _start, chunk in b._windows(text):
        assert len(chunk) <= b.window_chars


def test_windows_empty_text_yields_nothing():
    b = make_backend(window_chars=10, overlap=3)
    assert list(b._windows("")) == []


def test_windows_whitespace_only_window_skipped():
    b = make_backend(window_chars=10, overlap=3)
    # A block of spaces should not yield a window (chunk.strip() is falsy)
    wins = list(b._windows("     "))
    assert wins == []


def test_windows_multiple_windows_for_long_text():
    b = make_backend(window_chars=10, overlap=3)
    text = "z" * 100
    wins = list(b._windows(text))
    assert len(wins) > 1
    # last window must reach the end of the text
    last_start, last_chunk = wins[-1]
    assert last_start + len(last_chunk) == len(text)


# --------------------------------------------------------------------------- #
# extract / recover with monkeypatched _call
# --------------------------------------------------------------------------- #
def _resp(mapping):
    """Build a JSON response string from {clause_type: [(claim, quote), ...]}."""
    import json
    obj = {ct: [{"claim": c, "quote": q} for c, q in rows] for ct, rows in mapping.items()}
    return json.dumps(obj)


def test_extract_source_label_initial(monkeypatch):
    b = make_backend()
    monkeypatch.setattr(b, "_call",
                        lambda prompt: _resp({"Governing Law": [("gov", "laws of Delaware")]}))
    cands = b.extract("C1", "The contract is governed by the laws of Delaware.", "Governing Law")
    assert len(cands) == 1
    assert cands[0].source == Source.INITIAL
    assert cands[0].quote == "laws of Delaware"
    assert cands[0].clause_type == "Governing Law"


def test_recover_source_label_recovery(monkeypatch):
    b = make_backend()

    def call(prompt):
        if "Already found" in prompt:
            # recovery pass turns up a Cap obligation the initial pass missed
            return _resp({"Cap On Liability": [("cap", "liability shall not exceed fees")]})
        # initial pass finds a Governing Law item, which populates the exclude set
        # so the recovery prompt carries the "Already found" marker
        return _resp({"Governing Law": [("g", "laws of Delaware")]})

    monkeypatch.setattr(b, "_call", call)
    initial = b.extract("C1", "some text about liability and Delaware", "Governing Law")
    cands = b.recover("C1", "some text about liability and Delaware", "Cap On Liability",
                      [c.quote for c in initial])
    assert len(cands) == 1
    assert cands[0].source == Source.RECOVERY
    assert cands[0].quote == "liability shall not exceed fees"


def test_recover_returns_only_new_quotes(monkeypatch):
    b = make_backend()

    def call(prompt):
        if "Already found" in prompt:
            # recovery pass returns the old one AND a genuinely new one
            return _resp({"Governing Law": [
                ("old", "laws of Delaware"),
                ("new", "subject to New York jurisdiction"),
            ]})
        # initial pass finds the Delaware quote
        return _resp({"Governing Law": [("old", "laws of Delaware")]})

    monkeypatch.setattr(b, "_call", call)
    text = "governed by the laws of Delaware and subject to New York jurisdiction"
    initial = b.extract("C1", text, "Governing Law")
    recovery = b.recover("C1", text, "Governing Law", [c.quote for c in initial])
    init_quotes = {c.quote for c in initial}
    rec_quotes = {c.quote for c in recovery}
    assert "laws of Delaware" in init_quotes
    # recovery excludes what initial already found, returns only the new one
    assert rec_quotes == {"subject to New York jurisdiction"}
    assert all(c.source == Source.RECOVERY for c in recovery)


def test_dedup_across_windows(monkeypatch):
    # window small enough that the same text produces several windows, all returning
    # the same quote; the pass must dedup to a single candidate.
    b = make_backend(window_chars=10, overlap=3)
    monkeypatch.setattr(b, "_call",
                        lambda prompt: _resp({"Governing Law": [("g", "Delaware law")]}))
    text = "d" * 100  # forces many windows
    cands = b.extract("C1", text, "Governing Law")
    assert len(cands) == 1
    assert cands[0].quote == "Delaware law"


def test_dedup_case_insensitive(monkeypatch):
    b = make_backend(window_chars=10, overlap=3)
    responses = [
        _resp({"Governing Law": [("g", "Delaware Law")]}),
        _resp({"Governing Law": [("g", "delaware law")]}),  # same key, different case
    ]
    calls = {"n": 0}

    def call(prompt):
        r = responses[min(calls["n"], len(responses) - 1)]
        calls["n"] += 1
        return r

    monkeypatch.setattr(b, "_call", call)
    cands = b.extract("C1", "d" * 100, "Governing Law")
    assert len(cands) == 1


def test_call_raising_returns_empty_not_crash(monkeypatch):
    b = make_backend()

    def boom(prompt):
        raise RuntimeError("network down / model missing")

    monkeypatch.setattr(b, "_call", boom)
    # neither pass should propagate the exception
    initial = b.extract("C1", "any contract text here", "Governing Law")
    recovery = b.recover("C1", "any contract text here", "Governing Law", [])
    assert initial == []
    assert recovery == []


def test_memoization_single_pass_per_contract(monkeypatch):
    b = make_backend()
    calls = {"n": 0}

    def call(prompt):
        calls["n"] += 1
        return _resp({"Governing Law": [("g", "Delaware")]})

    monkeypatch.setattr(b, "_call", call)
    b.extract("C1", "short text", "Governing Law")
    after_first = calls["n"]
    # second extract for the same contract must not re-call the model
    b.extract("C1", "short text", "Cap On Liability")
    b.recover("C1", "short text", "Governing Law", [])
    assert calls["n"] == after_first


def test_extract_multiple_clause_types_routed(monkeypatch):
    b = make_backend()
    monkeypatch.setattr(b, "_call", lambda prompt: _resp({
        "Governing Law": [("g", "Delaware law")],
        "Renewal Term": [("r", "automatically renews")],
    }))
    text = "governed by Delaware law; the term automatically renews"
    gov = b.extract("C1", text, "Governing Law")
    ren = b.extract("C1", text, "Renewal Term")
    cap = b.extract("C1", text, "Cap On Liability")
    assert [c.quote for c in gov] == ["Delaware law"]
    assert [c.quote for c in ren] == ["automatically renews"]
    assert cap == []


def test_extract_empty_model_output(monkeypatch):
    b = make_backend()
    monkeypatch.setattr(b, "_call", lambda prompt: "")
    assert b.extract("C1", "text", "Governing Law") == []


def test_candidate_claim_carried_through(monkeypatch):
    b = make_backend()
    monkeypatch.setattr(b, "_call",
                        lambda prompt: _resp({"Governing Law": [("the claim text", "the quote")]}))
    cands = b.extract("C1", "governed by the quote clause", "Governing Law")
    assert cands[0].claim == "the claim text"


def test_backend_name_and_default_model():
    b = make_backend()
    assert b.name == "ollama"
    assert b.model == "mistral:7b"
    assert b.host == "http://localhost:11434"


def test_host_trailing_slash_stripped():
    b = make_backend(host="http://localhost:11434/")
    assert b.host == "http://localhost:11434"
