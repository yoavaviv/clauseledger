"""Loader for the CUAD subset (TheAtticusProject, CC BY 4.0).

Exposes contracts with gold obligation spans for our 6 clause types, plus the
genuinely-absent clause types per contract (used as fabrication/false-alarm negatives).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .schema import Span

_DEFAULT = Path(__file__).resolve().parent.parent / "data" / "cuad" / "subset.json"


@dataclass
class Contract:
    id: str
    text: str
    gold: dict[str, list[Span]]
    absent: list[str]
    split: str = "test"

    def gold_count(self) -> int:
        return sum(len(v) for v in self.gold.values())


@dataclass
class CuadSubset:
    categories: list[str]
    source: str
    contracts: list[Contract] = field(default_factory=list)

    def split(self, name: str) -> list[Contract]:
        return [c for c in self.contracts if c.split == name]


def load_subset(path: str | Path = _DEFAULT) -> CuadSubset:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    contracts: list[Contract] = []
    for c in raw["contracts"]:
        gold = {
            cat: [Span(start=s["start"], end=s["end"], text=s["text"]) for s in spans]
            for cat, spans in c["gold"].items()
        }
        contracts.append(
            Contract(id=c["id"], text=c["text"], gold=gold,
                     absent=c.get("absent", []), split=c.get("split", "test"))
        )
    return CuadSubset(categories=raw["categories"], source=raw["source"], contracts=contracts)
