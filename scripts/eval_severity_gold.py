"""Held-out evaluation on Yoav's commercial-severity gold. Zero API keys.

Two modes, chosen by what is present:

  # rank agreement only - needs just the labels in annotations.json:
  python scripts/eval_severity_gold.py

  # full held-out reliability pass - also needs raw/<msa_id>.txt locally (gitignored):
  python scripts/eval_severity_gold.py --backend ollama --model mistral:7b

`rank_agreement` reports how far the cheap provisional heuristic already tracks the expert
ordering (a diagnostic, never an accuracy claim). The held-out pass reports fabrication and
abstention on real SaaS MSAs the harness was never tuned for - the honest out-of-distribution
number - plus recall against the annotator's own short quotes.

Writes data/severity_gold/heldout_report.json (metrics + rankings only; NO contract text).
"""
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from clauseledger.abstain import apply_abstention
from clauseledger.metrics import compute_metrics
from clauseledger.pipeline import process_contract
from clauseledger.schema import RunConfig
from clauseledger.severity_gold import (load_heldout_contracts, load_severity_gold,
                                        provisional_ranking, rank_agreement)

ap = argparse.ArgumentParser()
ap.add_argument("--backend", choices=["ollama", "replay"], default=None,
                help="omit for rank-agreement-only mode (no raw texts needed)")
ap.add_argument("--model", default="mistral:7b")
ap.add_argument("--gold", default=str(ROOT / "data/severity_gold/annotations.json"))
ap.add_argument("--out", default=str(ROOT / "data/severity_gold/heldout_report.json"))
ap.add_argument("--abstain-threshold", type=float, default=0.9)
a = ap.parse_args()

gold = load_severity_gold(a.gold)
stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

report = {
    "generated_utc": stamp,
    "annotator": gold.meta.annotator,
    "gold_version": gold.meta.version,
    "populated": gold.is_populated,
    "n_types": len(gold.types),
    "n_msas_annotated": len(gold.msa_ids()),
    "n_entries": len(gold.entries),
    "provisional_ranking": provisional_ranking(),
    "gold_ranking": gold.ranking() if gold.types else None,
    "rank_agreement_kendall_tau": rank_agreement(gold),
    "heldout": None,
}

print(f"gold: {gold.meta.annotator} v{gold.meta.version}  "
      f"types={len(gold.types)} msas={len(gold.msa_ids())} entries={len(gold.entries)}")
if not gold.is_populated:
    print("gold is a STUB - populate data/severity_gold/annotations.json (see README.md).")
print(f"provisional ranking: {provisional_ranking()}")
if gold.types:
    print(f"gold ranking       : {gold.ranking()}")
    print(f"rank agreement (kendall tau vs provisional): {report['rank_agreement_kendall_tau']}")

if a.backend:
    contracts = load_heldout_contracts(gold)
    if not contracts:
        print("no raw MSA texts found under data/severity_gold/raw/ - skipping held-out pass.")
    else:
        if a.backend == "ollama":
            from clauseledger.backends import OllamaBackend
            be = OllamaBackend(model=a.model)
        else:
            from clauseledger.backends import ReplayBackend
            be = ReplayBackend(str(ROOT / "data/cuad/replay_cache.json"))
        cfg = RunConfig(backend=be.name, model=be.model, abstain_threshold=a.abstain_threshold)
        results = [process_contract(be, c, cfg, gold=c.gold) for c in contracts]
        for r in results:
            apply_abstention(r.rows, a.abstain_threshold)
        m = compute_metrics(results, contracts, cfg.gold_overlap_threshold, cfg.fabrication_floor)
        report["heldout"] = {
            "backend": be.name, "model": be.model,
            "n_contracts": len(contracts),
            "fabrication_rate": m.fabrication_rate,
            "abstention_rate": m.abstention_rate,
            "recall_vs_hand_quotes": m.recall_post_recovery,
            "recall_asserted": m.recall_asserted,
        }
        print(f"held-out ({be.name} {be.model}, {len(contracts)} real MSAs): "
              f"fabrication={m.fabrication_rate:.3f} abstention={m.abstention_rate:.3f} "
              f"recall-vs-hand-quotes={m.recall_post_recovery:.3f}")

Path(a.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
print(f"wrote {a.out}")
