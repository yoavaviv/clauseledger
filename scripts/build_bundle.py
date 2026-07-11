"""Bundle the frozen JSON into demo/data/bundle.js so the static UI works over file://
(browsers block fetch() of local files). Run after generate_demo.py or make_fixture.py.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
d = ROOT / "demo" / "data"
report = json.loads((d / "report.json").read_text(encoding="utf-8"))
contracts = json.loads((d / "contracts.json").read_text(encoding="utf-8"))
js = ("window.REPORT=" + json.dumps(report, ensure_ascii=False) + ";\n"
      "window.CONTRACTS=" + json.dumps(contracts, ensure_ascii=False) + ";\n")
(d / "bundle.js").write_text(js, encoding="utf-8")
print("bundle.js written:", (d / "bundle.js").stat().st_size, "bytes", file=sys.stderr)
