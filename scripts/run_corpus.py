"""Extract-only corpus run with per-contract checkpointing (billing-clean, local Ollama).

Separates the SLOW extraction from the cheap deterministic eval (scripts/finalize.py).
Writes the replay cache after EVERY contract, so a long local run is resumable and never
all-or-nothing: re-running skips contracts already in the cache. Freeze the demo afterwards
with `python scripts/finalize.py <cache>`.

Usage:
  python scripts/run_corpus.py [--n N] [--model mistral:7b] [--cache PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clauseledger.backends import OllamaBackend, RecordingBackend  # noqa: E402
from clauseledger.cuad import load_subset  # noqa: E402
from clauseledger.pipeline import process_contract  # noqa: E402
from clauseledger.schema import RunConfig  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=0, help="number of contracts (0 = all)")
    ap.add_argument("--model", default="mistral:7b")
    ap.add_argument("--cache", default=str(ROOT / "data/cuad/replay_cache.json"))
    a = ap.parse_args()

    cache_path = Path(a.cache)
    sub = load_subset()
    contracts = sub.contracts if a.n <= 0 else sub.contracts[: a.n]

    # resume: keep any contracts already cached, only extract the missing ones
    existing: dict = {}
    if cache_path.exists():
        try:
            existing = json.loads(cache_path.read_text(encoding="utf-8")).get("cache", {})
        except Exception:
            existing = {}

    backend = RecordingBackend(OllamaBackend(model=a.model))
    backend.cache = dict(existing)  # seed so a checkpoint dump keeps prior work
    cfg = RunConfig(backend="ollama", model=a.model, abstain_threshold=0.9)

    todo = [c for c in contracts if c.id not in existing]
    print(f"[corpus] {len(contracts)} contracts, {len(existing)} cached, "
          f"{len(todo)} to extract, model={a.model}", flush=True)

    t0 = time.time()
    for i, c in enumerate(todo, 1):
        ts = time.time()
        try:
            res = process_contract(backend, c, cfg, gold=c.gold)
            nrows = len(res.rows)
        except Exception as e:  # never lose the whole run to one bad contract
            print(f"[corpus] {i}/{len(todo)} {c.id[:38]:38s} FAILED: {e}", flush=True)
            continue
        # checkpoint after every contract
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(backend.dump(), ensure_ascii=False), encoding="utf-8")
        print(f"[corpus] {i}/{len(todo)} {c.id[:38]:38s} rows={nrows:3d} "
              f"({time.time()-ts:.0f}s, total {time.time()-t0:.0f}s) [checkpointed]", flush=True)

    total = len(json.loads(cache_path.read_text(encoding='utf-8'))['cache'])
    print(f"[corpus] DONE in {time.time()-t0:.0f}s; cache now holds {total} contracts", flush=True)


if __name__ == "__main__":
    main()
