# ADR 0008: A commercial-severity gold kit, kept separate from the provisional rubric

**Date:** 2026-07-12 · **Status:** accepted

## Context
ADR 0005 shipped a *provisional* severity rubric as a labelled placeholder and named the authored
moat: a hand-annotated commercial-severity gold on real SaaS MSAs, encoding which missed obligation
actually bleeds money. That gold is a human act (20 years of enterprise bid/contract judgment); it
cannot be generated. What *can* be built ahead of it is the harness that consumes it, so the moment
the annotations exist they produce a legible result and can replace the placeholder.

Three constraints shaped the design:
- **The judgment must stay visibly human.** The kit must not smuggle in an automated severity score
  dressed as expert labelling. It only *consumes* labels and reports one diagnostic.
- **Severity is a prioritisation, never a measured result** (ADR 0005 holds). No accuracy claim may
  attach to it.
- **Real MSAs are third-party documents.** A public repo cannot redistribute them.

## Decision
Add a self-contained kit under `data/severity_gold/` + `clauseledger/severity_gold.py`:

- **Two annotation layers.** `types` = a type-level ordering of the 6 clause types by severity-of-a-
  miss (this *replaces* the provisional `_BASE` via `rubric_from_gold`); `entries` = instance-level
  annotations on real MSA clauses (the held-out evidence set).
- **Two ordinal axes**, money-at-risk x time-to-trigger (1-5 each), collapsed to a 0-1 score with
  money weighted above urgency (0.6/0.4), transparently and adjustably.
- **One derived number, and only one:** `rank_agreement` (Kendall tau) between the provisional
  heuristic ordering and the gold ordering - a diagnostic of how far the cheap default already
  tracks expert judgment, explicitly not an accuracy metric.
- **A held-out reliability pass** that runs the existing pipeline over the annotated MSAs and reports
  **fabrication + abstention** on a domain the harness was never tuned for (the honest out-of-
  distribution number), plus recall against the annotator's own short quotes.
- **No redistribution of MSAs.** Raw texts live in a gitignored `raw/<msa_id>.txt`; committed
  annotations carry only short fair-use quotes + a source reference. The held-out pass runs locally;
  only metrics (no text) are frozen to `heldout_report.json`.
- **The `abstain_expected` flag** lets the annotator mark, by design, the legal-mechanics clauses
  where the correct behaviour is to route to a human - making the commercial/legal seam a labelled
  boundary rather than an unmarked failure.

`annotations.json` ships as an empty, valid stub; `annotations.example.json` is a clearly-synthetic
worked example used for the format and the tests.

## Consequences
The moat artifact has a home, a protocol, and a working consumer before the human work is done, so
annotating is pure data entry with immediate feedback. The provisional rubric can be swapped for the
gold in one call once populated. The repo stays legally clean (no third-party contracts committed),
and severity never acquires a false measured-accuracy claim. Cost: an empty stub in the tree until
the annotation happens - accepted, because it makes the owed work explicit and one-command-runnable.
