"""Pluggable extraction backends.

The pipeline never calls a model directly; it calls a Backend. This keeps the
reliability machinery model-agnostic and, crucially, lets the tests and the static
demo run with zero live inference (StubBackend / ReplayBackend) while a real run
uses OllamaBackend (local, billing-clean).

Every backend answers two questions for a (contract, clause_type):
  extract(...) -> the first single-shot pass
  recover(...) -> the adversarial pass: "what obligation of this type is present
                  but NOT already among these?"  This is what recovers the ~30%
                  a single-shot extractor silently drops.
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import requests

from .schema import CLAUSE_TYPES, Candidate, Source


class Backend(ABC):
    name: str = "base"
    model: str = "none"

    @abstractmethod
    def extract(self, contract_id: str, text: str, clause_type: str) -> list[Candidate]:
        ...

    @abstractmethod
    def recover(self, contract_id: str, text: str, clause_type: str,
                found_quotes: list[str]) -> list[Candidate]:
        ...


# --------------------------------------------------------------------------- #
# StubBackend: fully deterministic, configured in-memory. For unit tests.
# --------------------------------------------------------------------------- #
class StubBackend(Backend):
    name = "stub"
    model = "stub"

    def __init__(self, initial: dict | None = None, recovery: dict | None = None):
        # keyed by (contract_id, clause_type) -> list[dict(claim, quote)]
        self._initial = initial or {}
        self._recovery = recovery or {}

    def extract(self, contract_id, text, clause_type):
        items = self._initial.get((contract_id, clause_type), [])
        return [Candidate(clause_type=clause_type, claim=i["claim"], quote=i["quote"],
                          source=Source.INITIAL) for i in items]

    def recover(self, contract_id, text, clause_type, found_quotes):
        items = self._recovery.get((contract_id, clause_type), [])
        return [Candidate(clause_type=clause_type, claim=i["claim"], quote=i["quote"],
                          source=Source.RECOVERY) for i in items]


# --------------------------------------------------------------------------- #
# ReplayBackend: reads a cached raw-candidate file produced by a real run.
# Makes the demo reproducible and lets integration tests run offline.
# --------------------------------------------------------------------------- #
class ReplayBackend(Backend):
    name = "replay"

    def __init__(self, cache_path: str | Path):
        data = json.loads(Path(cache_path).read_text(encoding="utf-8"))
        self.model = data.get("model", "replay")
        # cache[contract_id][clause_type][source] -> [ {claim, quote}, ... ]
        self._cache: dict = data["cache"]

    def _get(self, contract_id, clause_type, source):
        node = self._cache.get(contract_id, {}).get(clause_type, {})
        return node.get(source, [])

    def extract(self, contract_id, text, clause_type):
        return [Candidate(clause_type=clause_type, claim=i["claim"], quote=i["quote"],
                          source=Source.INITIAL)
                for i in self._get(contract_id, clause_type, "initial")]

    def recover(self, contract_id, text, clause_type, found_quotes):
        return [Candidate(clause_type=clause_type, claim=i["claim"], quote=i["quote"],
                          source=Source.RECOVERY)
                for i in self._get(contract_id, clause_type, "recovery")]


# --------------------------------------------------------------------------- #
# OllamaBackend: real local inference (billing-clean, no API keys).
# Handles long contracts by exhaustive sequential windows (NOT retrieval-RAG).
# --------------------------------------------------------------------------- #
_DESCRIPTIONS = {
    "Renewal Term": "the duration of each renewal period and the renewal mechanism (auto/evergreen vs option-to-renew)",
    "Notice Period To Terminate Renewal": "the notice a party must give to stop a renewal (e.g. 90 days before the term ends)",
    "Cap On Liability": "the monetary ceiling on recoverable liability (note any carve-outs that sit outside the cap)",
    "Liquidated Damages": "a pre-agreed sum payable on breach as a genuine pre-estimate of loss (not a penalty)",
    "Post-Termination Services": "duties to keep providing services after termination",
    "Governing Law": "the substantive law governing interpretation (distinct from forum/jurisdiction and dispute-resolution)",
}


class OllamaBackend(Backend):
    """Local inference. Extracts ALL clause types in one call per pass per window
    (how a real extractor behaves, and far fewer calls), memoized per contract."""
    name = "ollama"

    def __init__(self, model: str = "mistral:7b", host: str = "http://localhost:11434",
                 window_chars: int = 9000, overlap: int = 800, timeout: int = 240,
                 temperature: float = 0.0):
        self.model = model
        self.host = host.rstrip("/")
        self.window_chars = window_chars
        self.overlap = overlap
        self.timeout = timeout
        self.temperature = temperature
        self._memo: dict[str, dict] = {}  # contract_id -> {"initial":{ct:[cand]}, "recovery":{ct:[cand]}}

    def _windows(self, text: str):
        step = self.window_chars - self.overlap
        for start in range(0, max(1, len(text)), step):
            chunk = text[start:start + self.window_chars]
            if chunk.strip():
                yield start, chunk
            if start + self.window_chars >= len(text):
                break

    def _call(self, prompt: str) -> str:
        r = requests.post(f"{self.host}/api/generate", timeout=self.timeout, json={
            "model": self.model, "prompt": prompt, "stream": False,
            "format": "json", "options": {"temperature": self.temperature},
        })
        r.raise_for_status()
        return r.json().get("response", "")

    @staticmethod
    def _parse_multi(resp: str) -> dict[str, list[dict]]:
        """Parse {"<ClauseType>":[{claim,quote}], ...} defensively."""
        out: dict[str, list[dict]] = {ct: [] for ct in CLAUSE_TYPES}
        resp = (resp or "").strip()
        if not resp:
            return out
        obj = None
        try:
            obj = json.loads(resp)
        except Exception:
            m = re.search(r"\{.*\}", resp, re.S)
            if m:
                try:
                    obj = json.loads(m.group(0))
                except Exception:
                    obj = None
        if not isinstance(obj, dict):
            return out
        for ct in CLAUSE_TYPES:
            items = obj.get(ct) or []
            if isinstance(items, dict):
                items = [items]
            for it in items if isinstance(items, list) else []:
                if isinstance(it, dict) and it.get("quote"):
                    out[ct].append({"claim": str(it.get("claim", "")).strip(),
                                    "quote": str(it["quote"]).strip()})
        return out

    def _prompt(self, chunk: str, exclude: Optional[dict[str, list[str]]] = None) -> str:
        lines = "\n".join(f'  - "{ct}": {_DESCRIPTIONS[ct]}' for ct in CLAUSE_TYPES)
        base = (
            "You are a contracts analyst. From the CONTRACT TEXT, extract the commercially "
            "material provisions (obligations, limitations, and mechanics) for EACH of these "
            "clause types:\n" + lines + "\n\n"
            'Return STRICT JSON mapping each clause type to a list of {"claim","quote"}, where '
            "quote is EXACT verbatim text copied character-for-character from the contract. "
            "Use [] for a type with none. Example: "
            '{"Governing Law":[{"claim":"...","quote":"..."}], "Cap On Liability":[], ...}\n'
        )
        if exclude:
            ex = "; ".join(f'{ct}: {" | ".join(q[:80] for q in qs[:6])}'
                           for ct, qs in exclude.items() if qs)
            if ex:
                base += ("\nAlready found (do NOT repeat; find only OTHER provisions still "
                         f"present): {ex}\n")
        return base + f'\nCONTRACT TEXT:\n"""{chunk}"""\n'

    def _pass(self, text: str, exclude: Optional[dict[str, list[str]]], source: Source) -> dict[str, list[Candidate]]:
        result: dict[str, list[Candidate]] = {ct: [] for ct in CLAUSE_TYPES}
        seen: dict[str, set] = {ct: set(q.strip().lower() for q in (exclude or {}).get(ct, []))
                                for ct in CLAUSE_TYPES}
        for _start, chunk in self._windows(text):
            try:
                parsed = self._parse_multi(self._call(self._prompt(chunk, exclude)))
            except Exception:
                parsed = {ct: [] for ct in CLAUSE_TYPES}
            for ct, items in parsed.items():
                for it in items:
                    key = it["quote"].strip().lower()
                    if key and key not in seen[ct]:
                        seen[ct].add(key)
                        result[ct].append(Candidate(clause_type=ct, claim=it["claim"],
                                                     quote=it["quote"], source=source))
        return result

    def _ensure(self, contract_id: str, text: str) -> dict:
        memo = self._memo.get(contract_id)
        if memo is None:
            initial = self._pass(text, None, Source.INITIAL)
            found = {ct: [c.quote for c in initial[ct]] for ct in CLAUSE_TYPES}
            recovery = self._pass(text, found, Source.RECOVERY)
            memo = {"initial": initial, "recovery": recovery}
            self._memo[contract_id] = memo
        return memo

    def extract(self, contract_id, text, clause_type):
        return self._ensure(contract_id, text)["initial"][clause_type]

    def recover(self, contract_id, text, clause_type, found_quotes):
        return self._ensure(contract_id, text)["recovery"][clause_type]


class RecordingBackend(Backend):
    """Wraps a backend and records every candidate into a replay cache, so a real run
    can be frozen and later replayed deterministically (for the demo + tests)."""

    def __init__(self, inner: Backend):
        self.inner = inner
        self.name = f"recording:{inner.name}"
        self.model = inner.model
        self.cache: dict = {}

    def _record(self, contract_id, clause_type, source, cands):
        node = self.cache.setdefault(contract_id, {}).setdefault(clause_type, {})
        node[source] = [{"claim": c.claim, "quote": c.quote} for c in cands]

    def extract(self, contract_id, text, clause_type):
        cands = self.inner.extract(contract_id, text, clause_type)
        self._record(contract_id, clause_type, "initial", cands)
        return cands

    def recover(self, contract_id, text, clause_type, found_quotes):
        cands = self.inner.recover(contract_id, text, clause_type, found_quotes)
        self._record(contract_id, clause_type, "recovery", cands)
        return cands

    def dump(self) -> dict:
        return {"model": self.model, "cache": self.cache}


def get_backend(name: str, **kw) -> Backend:
    name = name.lower()
    if name == "ollama":
        return OllamaBackend(**kw)
    if name == "replay":
        return ReplayBackend(kw["cache_path"])
    if name == "stub":
        return StubBackend(**kw)
    raise ValueError(f"unknown backend: {name}")
