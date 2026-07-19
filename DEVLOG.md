# DEVLOG

Dated build log. Raw material for the LinkedIn build-log posts and a second timestamp trail
beside the commit history.

## 2026-07-11 - v0.1.0, first build

- **Framed the thing.** Not "another contract AI" - a reliability harness. The hero is not
  extraction, it is measuring how often extraction silently misses or fabricates, recovering the
  misses, abstaining instead of guessing, and publishing honest numbers.
- **Data.** Pulled CUAD v1 (The Atticus Project, CC BY 4.0), derived a 40-contract subset over 6
  expensive clause types with a dev/test split and genuine absences (for fabrication/false-alarm
  negatives). All 134 gold spans self-ground - loader verified on real data.
- **Core.** Grounding primitive (exact -> case/space-insensitive -> fuzzy), pluggable backends
  (stub / replay / ollama / recording), verifier, calibrated abstention, severity (provisional),
  metrics, fault injection, pipeline. Smoke-tested end-to-end: recovery pass lifts recall,
  fabrication caught, Pareto computes.
- **Decision:** no retrieval-RAG over a single contract (ADR 0006); exhaustive long-context
  windows + an adversarial coverage pass instead.
- **Demo.** Static precomputed explorer (ADR 0003) - paper/ink/amber identity, scoreboard,
  recall-lift bars, Pareto SVG, fault table, per-clause table, and a contract explorer that
  highlights each row's cited span in the source text. Screenshot-verified in headless Chrome.
  Caught and fixed a scroll bug (auto-highlight was scrolling the window, hiding the header).
- **Tests + red-team.** 970 pytest cases (12 categories, 20+ each), 93% line coverage, plus property-based (hypothesis)
  tests for grounding offsets and metric invariants. Ran an independent adversarial code review
  in parallel; it found three real issues, all fixed:
  1. off-by-one span when contract text has leading whitespace (index-map desync after a stray
     `.strip()`);
  2. fabrication rate was threshold-dependent -> made it gold-free AND threshold-free at a fixed
     floor (ADR 0001);
  3. headline recall counted abstained rows -> added asserted recall alongside detection recall
     (ADR 0002).
- **Generation.** Ran the real pipeline over 10 contracts with local Ollama `mistral:7b`
  (billing-clean, no keys). A weaker model on purpose (ADR 0004): it misses more, which sharpens
  the recovery and abstention story. Extraction cached to `replay_cache.json` so metrics recompute
  without re-running the model.
- **Owed (Yoav):** replace the provisional severity rubric with hand-annotated commercial-severity
  gold on ~10-15 real SaaS MSAs (money-at-risk x time-to-trigger) - the defensible moat (ADR 0005).

## 2026-07-12 - real run + legal review folded in

- **Real numbers (mistral:7b, 10 contracts, 6 held-out test):** fabrication 0.0, detection
  recall 93.3%, asserted recall 40.0% at a 90%-precision operating point (abstention 75%),
  false-alarm 4.8%. Honest and on-brand: a modest local model, made trustworthy by abstaining
  hard on what it cannot ground firmly. Test-set recovery lift was ~0 (single-shot already
  covered the small gold set; the recovery pass still produced 21 grounded rows across the
  corpus). Reframed the demo to lead with fabrication + the real precision/abstention Pareto,
  with an explicit small-sample banner - NOT a benchmark.
- **Contracts-lawyer concept review (ADR 0007):** fixed Governing-Law/jurisdiction conflation,
  tagged clause kind (3 of 6 are not obligations), rewrote severity in harm-of-the-miss terms,
  and added a text-signal legal-mechanics abstention trigger so the tool actually cedes what it
  claims to. Scope limits (indemnity/uncapped/IP out of scope, LD enforceability, grounding !=
  operative) named in the README.
- Test suite now 987 green.

## 2026-07-12 - public push + severity-gold kit

- **Public.** Repo pushed to GitHub (yoavaviv/clauseledger), CI green. Authorship kept clean (no
  per-commit AI trailer); a "How this was built" note in the README owns the AI-orchestration story
  directly instead - senior direction plus leverage, decisions on the record. Stopped tracking the
  generation run log; fixed a flat-layout packaging bug that broke the first CI run (declare the
  import package explicitly + pin the build backend).
- **Severity-gold kit (ADR 0008).** Built the consumer for the owed moat so annotating is pure data
  entry with instant feedback. `data/severity_gold/` (protocol README + synthetic example + empty
  stub) and `clauseledger/severity_gold.py`: two annotation layers (type-level ranking that
  *replaces* the provisional `_BASE`, and instance-level entries on real MSAs), two ordinal axes
  (money-at-risk x time-to-trigger), one diagnostic (`rank_agreement`, Kendall tau vs the provisional
  ordering - not an accuracy claim), and a held-out reliability pass (`scripts/eval_severity_gold.py`)
  that reports fabrication + abstention on real SaaS MSAs the harness was never tuned for. Raw MSAs
  are never redistributed (gitignored `raw/`); only short fair-use quotes + metrics are committed.
  12 new tests, suite now 999 green, 93% coverage.
- **Still owed (Yoav):** the annotations themselves - source 10-15 public SaaS MSAs and fill
  `data/severity_gold/annotations.json` per the protocol. Cannot be fabricated; that is the point.

## 2026-07-19 - reliability depth: stitch guard + CIs + mutation harness

A per-layer deepening pass, everything measured, nothing asserted. Suite 999 -> 1,020 green.

- **Stitch-fabrication guard (ADR 0009).** Closed the repo's #1 admitted limitation. `detect_stitch`
  reconstructs a quote from its longest verbatim fragments and, if the pieces come from
  non-contiguous source locations, refuses to ground it regardless of fuzzy score; wired through
  the verifier reason and the fabrication metric. Built an adversarial harness
  (`clauseledger/adversarial.py`) that injects stitched fabrications (dominant real head + short
  displaced real tail) into every contract. On the full subset: **240 injected, 100% caught, 150
  (62.5%) would have been ASSERTED as real obligations by fuzzy grounding alone, 0 false positives
  on 132 real gold quotes.** The guard is conservative by design (favor precision - never flag a
  real quote), so the safety number leads.
- **Bootstrap confidence intervals (ADR 0010).** Contract-level 95% percentile bootstrap on every
  headline metric, deterministic (fixed seed). On the small test set the intervals are honestly
  wide (recall 0.79 with a CI spanning ~0.5-1.0); the demo now shows each number as `estimate
  [lo-hi]`. This is the honesty instrument the project preaches, applied to its own scoreboard.
- **Mutation testing (ADR 0011).** Built a dependency-free AST mutation tester
  (`scripts/mutation_test.py`) for the trust-decision core - the WEAK-SUITE guard (green tests
  execute code, they do not prove they would catch a bug). Trial on `verify.py` killed 2/3 (the
  survivor an equivalent rounding mutant). The full scored run is an offline pass (each mutant
  spawns pytest); harness + trial shipped, the number pending rather than rushed.
- **Demo + docs.** Explorer gained a stitch-defense panel and per-metric CI displays; refroze from
  the local cache (11 contracts, mistral:7b). README updated: reliability-engineering section,
  honest-limitation rewrite (the stitch hole is now defended and measured), 1,020-test count.
- **Judgment call.** Started a full-corpus local re-extraction for a bigger denominator; mistral
  was ~14 min/contract on the long tail (7 h for 30) with recall-lift ~0, so stopped it - the CIs
  express the small sample honestly, a better fix than a marginally larger N. Untouched by design:
  the severity-gold MSA annotations (Yoav's moat).
- **Left owed (Yoav):** same as before - the MSA annotations; plus, optionally, run the full
  mutation score offline.
