"""A small, self-contained mutation tester for the trust core (billing-clean, no deps).

Green tests prove code passes; they do NOT prove the tests would CATCH a bug. Mutation
testing measures that directly: inject a small fault (a mutant), run the targeted tests, and
see whether they FAIL (the mutant is "killed") or still pass (the mutant "survives" - a hole
in the suite). The mutation score = killed / total. Survivors are the honest weak spots; the
project then writes tests to kill them. This is the WEAK-SUITE guard from the Testing House:
a low failure rate can mean weak tests, not a strong system.

Usage:
  python scripts/mutation_test.py                       # default: the trust core
  python scripts/mutation_test.py clauseledger/ground.py --tests tests/test_ground.py ...
  python scripts/mutation_test.py --json out.json       # machine-readable summary
"""
from __future__ import annotations

import argparse
import ast
import copy
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# module -> the fast, targeted tests that exercise it (kept small so each mutant runs quickly).
# The trust-DECISION core: grounding, verification, abstention - the three modules that
# actually decide whether an obligation is trusted, abstained, or rejected.
TRUST_CORE: dict[str, list[str]] = {
    "clauseledger/ground.py": ["tests/test_ground.py", "tests/test_stitch.py"],
    "clauseledger/verify.py": ["tests/test_verify.py", "tests/test_stitch.py"],
    "clauseledger/abstain.py": ["tests/test_abstain.py"],
}
# The measurement layer: heavier and dominated by equivalent numeric mutants; run with --extended.
EXTENDED: dict[str, list[str]] = {
    "clauseledger/metrics.py": ["tests/test_recall.py", "tests/test_ci.py"],
    "clauseledger/adversarial.py": ["tests/test_stitch.py"],
}

_CMP_SWAP = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt,
             ast.Eq: ast.NotEq, ast.NotEq: ast.Eq}
_BIN_SWAP = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Div, ast.Div: ast.Mult}
_BOOL_SWAP = {ast.And: ast.Or, ast.Or: ast.And}


class _Mutator(ast.NodeTransformer):
    """Applies exactly ONE mutation, at the target (node index, kind), leaving the rest."""

    def __init__(self, target: int, kind: str):
        self.i = -1
        self.target = target
        self.kind = kind
        self.applied = False

    def _hit(self, kind: str) -> bool:
        if kind != self.kind:
            return False
        self.i += 1
        if self.i == self.target:
            self.applied = True
            return True
        return False

    def visit_Compare(self, node):
        self.generic_visit(node)
        if len(node.ops) == 1 and type(node.ops[0]) in _CMP_SWAP and self._hit("cmp"):
            node.ops = [_CMP_SWAP[type(node.ops[0])]()]
        return node

    def visit_BinOp(self, node):
        self.generic_visit(node)
        if type(node.op) in _BIN_SWAP and self._hit("bin"):
            node.op = _BIN_SWAP[type(node.op)]()
        return node

    def visit_BoolOp(self, node):
        self.generic_visit(node)
        if type(node.op) in _BOOL_SWAP and self._hit("bool"):
            node.op = _BOOL_SWAP[type(node.op)]()
        return node

    def visit_Constant(self, node):
        self.generic_visit(node)
        if isinstance(node.value, bool) and self._hit("boolconst"):
            return ast.copy_location(ast.Constant(value=not node.value), node)
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool) \
                and self._hit("num"):
            return ast.copy_location(ast.Constant(value=node.value + 1), node)
        return node


def _count(tree: ast.AST) -> dict[str, int]:
    counts = {"cmp": 0, "bin": 0, "bool": 0, "boolconst": 0, "num": 0}
    for n in ast.walk(tree):
        if isinstance(n, ast.Compare) and len(n.ops) == 1 and type(n.ops[0]) in _CMP_SWAP:
            counts["cmp"] += 1
        elif isinstance(n, ast.BinOp) and type(n.op) in _BIN_SWAP:
            counts["bin"] += 1
        elif isinstance(n, ast.BoolOp) and type(n.op) in _BOOL_SWAP:
            counts["bool"] += 1
        elif isinstance(n, ast.Constant):
            if isinstance(n.value, bool):
                counts["boolconst"] += 1
            elif isinstance(n.value, (int, float)):
                counts["num"] += 1
    return counts


def _run_tests(tests: list[str]) -> bool:
    """Return True if the tests PASS (mutant survived), False if they FAIL (killed)."""
    r = subprocess.run([sys.executable, "-m", "pytest", "-x", "-q", "--no-header",
                        "-p", "no:cacheprovider", *tests],
                       cwd=ROOT, capture_output=True, text=True)
    return r.returncode == 0


def mutate_module(module: str, tests: list[str]) -> dict:
    path = ROOT / module
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    counts = _count(tree)
    total = sum(counts.values())
    killed = survived = 0
    survivors: list[str] = []
    t0 = time.time()
    print(f"[mut] {module}: {total} mutants ({counts})", flush=True)
    try:
        for kind, n in counts.items():
            for idx in range(n):
                m = _Mutator(idx, kind)
                mutated = ast.fix_missing_locations(m.visit(copy.deepcopy(tree)))
                path.write_text(ast.unparse(mutated), encoding="utf-8")
                passed = _run_tests(tests)
                if passed:
                    survived += 1
                    survivors.append(f"{kind}#{idx}")
                else:
                    killed += 1
    finally:
        path.write_text(src, encoding="utf-8")  # ALWAYS restore the original
    score = killed / total if total else 1.0
    print(f"[mut] {module}: killed {killed}/{total} = {score:.1%} "
          f"({time.time()-t0:.0f}s){'  SURVIVORS: ' + ', '.join(survivors) if survivors else ''}",
          flush=True)
    return {"module": module, "total": total, "killed": killed, "survived": survived,
            "score": round(score, 4), "survivors": survivors}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("module", nargs="?", help="single module to mutate (default: trust core)")
    ap.add_argument("--tests", nargs="*", help="tests for the single module")
    ap.add_argument("--json", help="write the summary to this path")
    ap.add_argument("--extended", action="store_true", help="also mutate the measurement layer")
    a = ap.parse_args()

    if a.module:
        plan = {a.module: a.tests or []}
    else:
        plan = {**TRUST_CORE, **(EXTENDED if a.extended else {})}
    results = [mutate_module(m, t) for m, t in plan.items()]
    tot = sum(r["total"] for r in results)
    kil = sum(r["killed"] for r in results)
    overall = kil / tot if tot else 1.0
    summary = {"overall_score": round(overall, 4), "killed": kil, "total": tot,
               "modules": results}
    print(f"\n[mut] TRUST CORE mutation score: {kil}/{tot} = {overall:.1%}")
    if a.json:
        Path(a.json).write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"[mut] wrote {a.json}")


if __name__ == "__main__":
    main()
