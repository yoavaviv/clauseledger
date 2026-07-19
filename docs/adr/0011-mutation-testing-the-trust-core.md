# ADR 0011: Mutation-test the trust core (green tests are not enough)

**Date:** 2026-07-19 · **Status:** accepted (harness shipped; full scored run runs offline)

## Context
The suite is large (1000+ cases, 90%+ coverage) and green. But coverage and a green bar only
prove the tests EXECUTE the code, not that they would CATCH a bug in it. The Testing House
WEAK-SUITE result (SWE-ABS 2026) is blunt about this: a low failure rate can mean the tests
are weak, not the system strong. For a project whose whole thesis is "measured, not asserted,"
asserting test quality from coverage alone would be the exact hypocrisy it calls out.

## Decision
Ship a small, dependency-free **mutation tester** (`scripts/mutation_test.py`) and point it at
the **trust-decision core** (grounding, verification, abstention - the modules that decide
whether an obligation is trusted, abstained, or rejected). It parses each module's AST, injects
one fault at a time (comparison/arithmetic/boolean-operator swaps, boolean and numeric constant
tweaks), runs the module's targeted tests, and records whether the fault is **killed** (a test
fails) or **survives** (a hole in the suite). Mutation score = killed / total; survivors are the
honest weak spots to write tests against. The harness always restores the original source in a
`finally` block, and is billing-clean (stdlib only, local pytest, no model, no keys).

## Consequences
The tool is the deliverable and the discipline: it converts "we have tests" into "our tests
kill N% of injected faults, and here are the survivors." A trial run on `verify.py` killed 2 of
3 mutants (the survivor was an equivalent mutant: a rounding-precision change with no observable
effect), confirming the harness discriminates real gaps from equivalent mutants.

## Honest status (stated, not hidden)
The **full scored run over the trust core is deferred to an offline pass**: each mutant spawns a
pytest subprocess, and the adversarial stitch tests it runs load the CUAD subset, so a full
sweep is minutes of local compute better spent offline than inline. The number is not published
yet; when it is, it goes on the scoreboard with its survivor list. Publishing the harness plus a
validated trial, and being explicit that the full score is pending, is more honest than quoting
a rushed or partial figure. Run it with `python scripts/mutation_test.py --json out.json`.
