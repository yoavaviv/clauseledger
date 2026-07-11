"""Reproduce the numbers from any backend. Zero API keys.

  python scripts/run_eval.py --backend replay --cache data/cuad/replay_cache.json
  python scripts/run_eval.py --backend ollama --model mistral:7b --n 10

The replay path recomputes metrics from cached extractions instantly; the ollama path
re-extracts locally (slow, billing-clean). Both print the same metric set.
"""
import argparse, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from clauseledger.backends import OllamaBackend, ReplayBackend
from clauseledger.cuad import load_subset
from clauseledger.evaluate import evaluate

ap = argparse.ArgumentParser()
ap.add_argument("--backend", choices=["replay", "ollama"], default="replay")
ap.add_argument("--cache", default=str(ROOT / "data/cuad/replay_cache.json"))
ap.add_argument("--model", default="mistral:7b")
ap.add_argument("--n", type=int, default=10)
a = ap.parse_args()

sub = load_subset()
if a.backend == "replay":
    import json
    ids = set(json.loads(Path(a.cache).read_text(encoding="utf-8"))["cache"].keys())
    contracts = [c for c in sub.contracts if c.id in ids]
    be = ReplayBackend(a.cache)
else:
    contracts = sub.contracts[:a.n]
    be = OllamaBackend(model=a.model)

rep = evaluate(be, contracts)
m = rep.metrics
print(f"backend={be.name} model={be.model} test_contracts={m.n_contracts} abstain_thr={rep.config.abstain_threshold}")
print(f"detection recall: {m.recall_single_shot:.3f} -> {m.recall_post_recovery:.3f}  (lift +{m.recall_lift:.3f})")
print(f"asserted recall : {m.recall_asserted:.3f}")
print(f"precision       : {m.precision:.3f}")
print(f"fabrication     : {m.fabrication_rate:.3f}   false-alarm: {m.false_alarm_rate:.3f}")
print(f"abstention      : {m.abstention_rate:.3f}")
print("per clause:")
for c in m.per_clause:
    print(f"  {c.clause_type:38s} gold={c.gold_total:2d}  recall {c.recall_single_shot:.2f}->{c.recall_post_recovery:.2f}  prec {c.precision:.2f}")
for f in m.faults:
    print(f"fault {f.name:16s} recall={f.faulted_recall:.3f} fabrication={f.fabrication_rate:.3f} completion={f.completion:.2f}")
