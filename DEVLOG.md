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
