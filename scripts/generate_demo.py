"""Generate the frozen demo artifact by running the REAL pipeline over CUAD contracts.

Uses the local Ollama backend (billing-clean, no keys). Calibrates the abstention
threshold on the dev split, reports metrics on the test split, and freezes:
  - demo/data/report.json      the RunReport the static UI renders
  - demo/data/contracts.json   {id: text} for span highlighting in the UI
  - data/cuad/replay_cache.json raw candidates, so the run replays deterministically

Usage: python scripts/generate_demo.py [n_contracts] [model]
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clauseledger.abstain import apply_abstention, calibrate_threshold  # noqa: E402
from clauseledger.backends import OllamaBackend, RecordingBackend  # noqa: E402
from clauseledger.cuad import load_subset  # noqa: E402
from clauseledger.metrics import compute_metrics  # noqa: E402
from clauseledger.pipeline import process_contract  # noqa: E402
from clauseledger.schema import RunConfig, RunReport  # noqa: E402


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    model = sys.argv[2] if len(sys.argv) > 2 else "mistral:7b"

    sub = load_subset()
    # shortest-first (subset is already sorted) keeps the local run tractable
    demo = sub.contracts[:n]
    by_id = {c.id: c for c in demo}
    print(f"[gen] {len(demo)} contracts, model={model}", flush=True)

    backend = RecordingBackend(OllamaBackend(model=model))
    cfg = RunConfig(backend="ollama", model=model, abstain_threshold=0.9)

    results = []
    t0 = time.time()
    for i, c in enumerate(demo, 1):
        ts = time.time()
        res = process_contract(backend, c, cfg, gold=c.gold)
        res.split = c.split
        results.append(res)
        print(f"[gen] {i}/{len(demo)} {c.id[:38]:38s} rows={len(res.rows):3d} "
              f"({time.time()-ts:.0f}s, total {time.time()-t0:.0f}s)", flush=True)

    dev = [r for r in results if r.split == "dev"]
    test = [r for r in results if r.split == "test"]
    dev_rows = [row for r in dev for row in r.rows]

    thr = calibrate_threshold(dev_rows, target_precision=0.9) if dev_rows else 0.9
    print(f"[gen] calibrated abstain_threshold={thr} on {len(dev)} dev contracts", flush=True)
    for r in results:
        apply_abstention(r.rows, thr)

    report_contracts = test if test else results
    metrics = compute_metrics(report_contracts, [by_id[r.contract_id] for r in report_contracts],
                              cfg.gold_overlap_threshold)
    cfg = cfg.model_copy(update={"abstain_threshold": thr, "n_contracts": len(report_contracts),
                                 "notes": f"calibrated on {len(dev)} dev; reported on {len(report_contracts)} test"})
    report = RunReport(
        generated_utc=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        config=cfg, metrics=metrics, contracts=results)  # ship all for exploration

    (ROOT / "demo/data").mkdir(parents=True, exist_ok=True)
    (ROOT / "demo/data/report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    (ROOT / "demo/data/contracts.json").write_text(
        json.dumps({c.id: c.text for c in demo}, ensure_ascii=False), encoding="utf-8")
    (ROOT / "data/cuad").mkdir(parents=True, exist_ok=True)
    (ROOT / "data/cuad/replay_cache.json").write_text(
        json.dumps(backend.dump(), ensure_ascii=False), encoding="utf-8")

    m = metrics
    print(f"\n[gen] DONE in {time.time()-t0:.0f}s")
    print(f"  recall single-shot {m.recall_single_shot}  post-recovery {m.recall_post_recovery}  "
          f"LIFT {m.recall_lift}")
    print(f"  precision {m.precision}  fabrication {m.fabrication_rate}  "
          f"false-alarm {m.false_alarm_rate}  abstention {m.abstention_rate}")


if __name__ == "__main__":
    main()
