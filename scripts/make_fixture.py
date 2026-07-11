"""Deterministic FIXTURE generator (no model). Produces a realistic-shaped
demo/data/report.json so the UI can be built and tested offline. Clearly labelled
model='fixture'; the real Ollama run overwrites these files. Exercises the real
pipeline code path via StubBackend.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clauseledger.abstain import apply_abstention, calibrate_threshold  # noqa: E402
from clauseledger.backends import StubBackend  # noqa: E402
from clauseledger.cuad import load_subset  # noqa: E402
from clauseledger.metrics import compute_metrics  # noqa: E402
from clauseledger.pipeline import process_contract  # noqa: E402
from clauseledger.schema import CLAUSE_TYPES, RunConfig, RunReport  # noqa: E402


def _tamper(text: str) -> str:
    words = text.split()
    if len(words) > 6:
        words[2] = "hereinafter"  # small edit -> lower grounding score -> some abstain
    return " ".join(words)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    sub = load_subset()
    demo = sub.contracts[:n]
    by_id = {c.id: c for c in demo}

    initial, recovery = {}, {}
    for ci, c in enumerate(demo):
        for ti, ct in enumerate(CLAUSE_TYPES):
            gs = c.gold.get(ct, [])
            if not gs:
                # occasionally emit a fabrication on a genuinely-absent clause type
                if ct in c.absent and (ci + ti) % 4 == 0:
                    initial[(c.id, ct)] = [{"claim": f"[invented] {ct} obligation",
                                            "quote": f"The parties shall settle {ct} disputes on planet Zog."}]
                continue
            rows = []
            for k, sp in enumerate(gs[:2]):
                q = sp.text
                if (ci + k) % 3 == 0 and len(q.split()) > 6:
                    q = _tamper(q)  # near-miss -> lower confidence
                rows.append({"claim": f"{ct} obligation", "quote": q})
            # split: put ~40% into recovery to demonstrate recall lift
            if ti % 2 == 0 and len(rows) > 0:
                recovery[(c.id, ct)] = [rows[-1]]
                initial[(c.id, ct)] = rows[:-1]
            else:
                initial[(c.id, ct)] = rows

    be = StubBackend(initial=initial, recovery=recovery)
    cfg = RunConfig(backend="fixture", model="fixture", abstain_threshold=0.9)

    results = []
    for c in demo:
        res = process_contract(be, c, cfg, gold=c.gold)
        res.split = c.split
        results.append(res)

    dev = [r for r in results if r.split == "dev"]
    dev_rows = [row for r in dev for row in r.rows]
    thr = calibrate_threshold(dev_rows, 0.9) if dev_rows else 0.9
    for r in results:
        apply_abstention(r.rows, thr)
    test = [r for r in results if r.split == "test"] or results
    test_contracts = [by_id[r.contract_id] for r in test]
    metrics = compute_metrics(test, test_contracts, cfg.gold_overlap_threshold)
    from clauseledger.faults import run_faults  # noqa: E402
    metrics.faults = run_faults(be, test_contracts, cfg.model_copy(update={"abstain_threshold": thr}),
                                metrics.recall_post_recovery)
    cfg = cfg.model_copy(update={"abstain_threshold": thr, "n_contracts": len(test),
                                 "notes": "FIXTURE (deterministic, no model) - replaced by the real run"})
    report = RunReport(generated_utc=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                       config=cfg, metrics=metrics, contracts=results)

    (ROOT / "demo/data").mkdir(parents=True, exist_ok=True)
    (ROOT / "demo/data/report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    (ROOT / "demo/data/contracts.json").write_text(
        json.dumps({c.id: c.text for c in demo}, ensure_ascii=False), encoding="utf-8")
    print(f"fixture: {len(demo)} contracts, thr={thr}, recall_lift={metrics.recall_lift}, "
          f"fabrication={metrics.fabrication_rate}, abstention={metrics.abstention_rate}")


if __name__ == "__main__":
    main()
