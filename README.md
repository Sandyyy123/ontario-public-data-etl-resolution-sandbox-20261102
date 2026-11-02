# Ontario Public-Dataset ETL, Address/Entity Resolution & Lead-Cohort Scoring Sandbox (Synthetic Demo)

> **Important Disclosure:** This repository is a **synthetic Python demonstration** created specifically to illustrate deterministic address/entity resolution and multi-signal lead scoring for an Upwork proposal (`2117353817236374460`). It uses synthetic in-memory fixtures only and is **not** a prior commercial client project.

## What This Synthetic Sandbox Demonstrates

1. **Ontario Civic Address & FSA+LDU Normalization (`normalize_ontario_address`)**: Unifies suite/unit prefixes (`Suite 400, 120 Adelaide St. W.` vs. `400-120 Adelaide Street W`), street suffixes, municipality codes, and Canadian postal codes into a deterministic `address_resolution_key`.
2. **Corporate Entity Key Resolution (`normalize_corporate_entity`)**: Normalizes Canadian corporate legal names (`Inc.`, `Ltd.`, `(Ontario)`, punctuation) to link Corporations Canada records against municipal building permits and court dockets.
3. **Multi-Signal Mortgage Lead Cohort Scoring (`stitch_and_score_property_signals`)**: Joins municipal permit capex, Corporations Canada active/amendment signals, Ontario court docket filings, and CMHC zone velocity into `HIGH_INTENT_COMMERCIAL`, `HIGH_INTENT_RESIDENTIAL`, and `WATCHLIST` cohorts with full `source_record_ids` lineage.

## Run Contract Tests

```bash
pytest -v
```
