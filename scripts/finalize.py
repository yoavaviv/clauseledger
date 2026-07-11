"""Freeze the demo artifact from a replay cache (produced by a real Ollama run).
Separates the expensive extraction (cached) from cheap deterministic evaluation, so
metrics/faults can be recomputed without re-running any model.

Usage: python scripts/finalize.py [cache_path]
"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from clauseledger.backends import ReplayBackend
from clauseledger.cuad import load_subset
from clauseledger.evaluate import evaluate

cache_path = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "data/cuad/replay_cache.json")
cache = json.loads(Path(cache_path).read_text(encoding="utf-8"))
ids = set(cache["cache"].keys())
sub = load_subset()
contracts = [c for c in sub.contracts if c.id in ids]
be = ReplayBackend(cache_path)
be.name, be.model = "ollama (frozen)", cache.get("model", "unknown")

report = evaluate(be, contracts)
(ROOT / "demo/data").mkdir(parents=True, exist_ok=True)
(ROOT / "demo/data/report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
(ROOT / "demo/data/contracts.json").write_text(
    json.dumps({c.id: c.text for c in contracts}, ensure_ascii=False), encoding="utf-8")
m = report.metrics
print(f"finalized {len(contracts)} contracts (model={be.model}), "
      f"test={m.n_contracts}, thr={report.config.abstain_threshold}")
print(f"  detection recall {m.recall_single_shot} -> {m.recall_post_recovery} (lift {m.recall_lift}); "
      f"asserted {m.recall_asserted}")
print(f"  precision {m.precision}  fabrication {m.fabrication_rate}  "
      f"false-alarm {m.false_alarm_rate}  abstention {m.abstention_rate}")
