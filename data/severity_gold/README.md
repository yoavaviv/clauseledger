# Commercial-severity gold - annotation protocol

This is the **authored moat**. The reliability harness is hard engineering anyone senior
can respect; the part a weekend clone cannot reproduce is the judgment about *which missed
obligation actually bleeds money*. That judgment is hand-annotated here, on real SaaS master
service agreements - the class of contract (service-credit SLAs, renewal traps, liability
allocation) that CUAD does not cover.

Severity is a **curated prioritisation, never a measured result.** Nothing in this folder is
presented as an accuracy number. The one metric derived from it, `rank_agreement`, only reports
how far the cheap provisional heuristic in `severity.py` already tracks the expert ordering.

## What you produce

Fill in `annotations.json` (schema below). Two layers:

1. **`types`** - your ordering of the 6 clause types by severity-of-a-miss. This *replaces* the
   provisional `_BASE` rubric wholesale (`rubric_from_gold` converts it). This is the headline moat
   artifact: the ranking a bootcamp grad cannot defend in an interview.
2. **`entries`** - one row per real clause you annotate across 10-15 MSAs. This is the held-out
   evidence set: the harness runs over these contracts and reports fabrication + abstention on a
   domain it was never tuned for.

## The two axes (ordinal 1-5 each)

| Axis | 1 | 3 | 5 |
|---|---|---|---|
| **money_at_risk** | trivial / capped small | material but bounded | large or uncapped exposure |
| **time_to_trigger** | no deadline / open-ended | months of runway | days, or already running |

Derived score = `0.6 x money + 0.4 x time`, normalised to 0-1. Money is weighted higher on
purpose: a large exposure noticed late still hurts more than a tight deadline on a trivial sum.
Adjust the weights in `severity_gold.py` if your judgment differs - and write down why.

## Rules that keep this honest and legal

- **Never commit the full MSAs.** They are third-party documents. Put each raw contract text at
  `raw/<msa_id>.txt` (gitignored). The committed annotation carries only a **short fair-use quote**,
  a `source_ref` (where it came from), and - if you want provenance - a local content hash.
- **`quote` is an excerpt, not the clause.** One sentence is plenty; it only has to be locatable in
  the raw text so the held-out pass can attach it as a span.
- **Cede legal mechanics by design.** Where the correct answer is "a lawyer decides"
  (condition-precedent, survival, materiality, liquidated-damages enforceability), set
  `abstain_expected: true`. That is not a gap; it is the designed boundary between commercial
  severity (yours) and legal adjudication (not yours). Defend the seam.
- **Rationale is the moat.** One line per type and per entry, in harm-of-the-miss terms, ideally
  anchored to lived experience ("I have been on the hook for this"). This is what cannot be faked.

## Sourcing 10-15 real MSAs (all public, no client material)

Use publicly-filed or openly-published agreements only - never anything from a Hopp account or an
NDA'd counterparty. Good sources: SEC EDGAR exhibit 10.x filings (search "master services agreement"
/ "master subscription agreement"), vendors that publish their standard MSA/terms, and public
contract-template repositories. Prefer SaaS/subscription agreements with **service-level credits**,
**auto-renewal + notice windows**, and **liability caps with carve-outs** - the expensive triad.

## Schema (annotations.json)

```jsonc
{
  "meta": { "annotator": "Yoav Aviv", "version": "1.0", "dated": "2026-07-DD",
            "axes_note": "money_at_risk x time_to_trigger, ordinal 1-5; prioritisation not measurement" },
  "types": [
    { "clause_type": "Cap On Liability", "money_at_risk": 5, "time_to_trigger": 2,
      "kind": "allocation", "rationale": "..." }
    // ... all 6 clause types
  ],
  "entries": [
    { "msa_id": "vendor-x-saas-msa", "clause_type": "Notice Period To Terminate Renewal",
      "quote": "short verbatim excerpt", "money_at_risk": 4, "time_to_trigger": 5,
      "kind": "obligation", "abstain_expected": false, "rationale": "..." }
    // ... 10-15 MSAs worth of clauses
  ]
}
```

`clause_type` must be one of the six in `clauseledger/schema.py`. `annotations.example.json` is a
**synthetic** worked example (fabricated MSAs, for format + tests only) - do not treat its numbers
as real judgment.

## Run the held-out pass (after annotating, with raw texts present locally)

```bash
# rank agreement only (labels are enough, no raw texts needed):
python scripts/eval_severity_gold.py

# full held-out reliability pass (needs raw/<msa_id>.txt present):
python scripts/eval_severity_gold.py --backend ollama --model mistral:7b
```

Writes `heldout_report.json` (metrics + rank agreement + entry counts, **no contract text**), which
the case study and the README moat section cite.
