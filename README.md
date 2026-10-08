# Motor Insurance Pricing Calculator

**Business question:** How should a motor insurer differentiate prices by risk while balancing expected claims, retention, and underwriting contribution?

**Current conclusion:** Build an interpretable pricing baseline and test a boosting challenger, but treat commercial rate recommendations as scenarios. The selected public data has no premiums or renewal outcomes, and claim counts do not fully reconcile with recorded costs. Part 1 quantifies those gaps before modelling.

This is a staged portfolio case study using French motor third-party liability data. It is being developed toward a manager-facing pricing dashboard and a two-page decision brief. **The models and dashboard are not implemented yet.**

## Delivery checkpoints

| Part | Deliverable | Status |
|---|---|---|
| 1 | Public data, provenance, quality audit, engineered features, frozen splits | Complete |
| 2 | Poisson frequency + Gamma severity GLMs, pure premium, diagnostics | Next |
| 3 | Gradient boosting, lift/Gini/decile validation, model recommendation | Planned |
| 4 | Commercial simulation and live dashboard with editable assumptions | Planned |
| 5 | Client presentation, two-page summary, deployment and final review | Planned |
| Optional | Australian market risk context with separately sourced public data | After core delivery |

Resume instructions are in [CHECKPOINT.md](CHECKPOINT.md). Each part will finish with updated commands, tests, findings, and the next task. A checkpoint is a deliberate handover point, not a claim that the whole project is finished.

## Why this dataset

The primary source is **freMTPL2, OpenML version 1**:

- [41214 — frequency](https://www.openml.org/d/41214): policy risk characteristics, exposure and original claim counts.
- [41215 — severity](https://www.openml.org/d/41215): claim amounts linked through `IDpol`.
- [CASdatasets documentation](https://dutangc.github.io/CASdatasets/reference/freMTPL.html): provenance and field definitions.

OpenML reports CC0 for both dataset snapshots. Attribution and download checksums are recorded in [data_manifest.json](reports/data_manifest.json). The OpenML snapshot contains **678,013 policies**, whereas the CASdatasets description refers to 677,991; this project pins the downloaded OpenML bytes rather than treating different versions as interchangeable.

The [Allstate Kaggle competition](https://www.kaggle.com/competitions/allstate-claims-severity/data) is a useful severity alternative. We choose freMTPL2 because its linked policy exposure, counts, and costs support the full requested pricing workflow. See [DATA_SOURCES.md](docs/DATA_SOURCES.md).

## What Part 1 found

| Measure | Value |
|---|---:|
| Raw policy rows | 678,013 |
| Raw claim-cost records | 26,639 |
| Matched claim-cost records | 26,444 |
| Exposure | 358,499.45 policy-years |
| Original claim count | 36,102 |
| Policies reporting claims without any cost record | 9,116 |
| Orphan claim records excluded from modelling | 195 |
| Recorded cost per policy-year | EUR 167.11 |

These describe the snapshot; EUR 167.11 is **not a fitted premium or a recommended rate**. No currency conversion, inflation, loss development, expenses, or profit allowance is included. The largest 1% of matched claims account for approximately 38% of recorded cost, so tail uncertainty will matter in model comparison.

The main estimand is **expected cost represented in the linked claim-cost table**. Frequency uses its count of recorded claims; severity uses positive individual claim costs. Original `ClaimNb` remains available for a separately labelled sensitivity. Missing costs are flagged, never presented as evidence of zero ultimate loss. Full detail: [data audit](reports/DATA_AUDIT.md) and [methodology](docs/METHODOLOGY.md).

## Reproduce Part 1

Use Python 3.14 for the verified environment. The package allows Python 3.12–3.14; other environments still need validation. Run from the repository root:

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt
python -m pip install --no-deps .
insurance-pricing prepare
python -m pytest -q
```

The first prepare downloads about 7.75 MB from OpenML using HTTPS, with no Kaggle credentials. Later runs verify the cached bytes against the committed SHA-256 source lock. Structural data defects halt preparation. If a cache is corrupted, remove the affected local raw file and rerun; do not casually update the source lock.

`insurance-pricing download` downloads and verifies sources without preparation. To run elsewhere, pass `--root /absolute/path/to/repository`. After editing package code, reinstall with `python -m pip install --no-deps .`, or run directly from source with `PYTHONPATH=src .venv/bin/python -m insurance_pricing.cli prepare`.

The setup uses a regular package install. Editable installs can fail in macOS environments that mark `.pth` files hidden, because Python skips those files; this [CPython issue](https://github.com/python/cpython/issues/148121) occurred locally. A regular install or the direct-source command above avoids relying on an editable `.pth` file.

Outputs:

- `data/processed/policies.parquet`: one row per policy, raw risk factors, features, both target definitions, flags, partition.
- `data/processed/claims.parquet`: one row per matched claim, risk factors, features, inherited partition.
- [reports/](reports/): provenance, audit, reconciliation and descriptive segment summary. Raw/processed records are excluded from Git; reproducible code and aggregate reports are committed.

## Planned interactive dashboard

Python + Streamlit will provide portfolio/model results, segment diagnostics, an individual risk calculator, and commercial scenarios. Changing assumptions will recalculate expected retention, retained policies, premium, claims, loss ratio and underwriting contribution. An editable segment table will support adding rate adjustments and elasticity overrides; scenarios can be saved and compared.

Inputs include rate change, baseline retention, elasticity, claims inflation, expense ratio, fixed expense and margin. Model choice will switch between GLM and boosting. New rating variables will require available training data and a validated model refit; adding a dashboard control alone cannot create a learned risk effect. See [DASHBOARD_SPEC.md](docs/DASHBOARD_SPEC.md).

## Judgement and limitations

- Historical French liability costs are not current Australian motor or home prices.
- Random policy holdouts cannot measure future performance; dates and customer identifiers are absent.
- Recorded-cost incompleteness may vary by segment. This uncertainty is central to interpretation.
- Baseline premiums and elasticity will be explicit assumptions because historical premiums and renewal outcomes are unavailable.
- An interpretable GLM helps explain rating factors; neither GLMs nor boosting have automatic regulatory approval. Governance, permitted variables, fairness, stability, and documentation must be assessed for the deployment jurisdiction.
- Final business recommendations will follow model evidence and commercial sensitivity, not just ranking metrics.

## Project structure

```text
configs/                 Source checksum lock and data/split decisions
src/insurance_pricing/   Reusable download, preparation and feature code
tests/                   Financial integrity and leakage safeguards
data/raw/                Local verified source cache (not committed)
data/processed/          Reproducible policy and claim tables (not committed)
reports/                 Committed aggregate audit evidence
docs/                    Sources, methodology, dashboard and roadmap
artifacts/               Future local model artifacts (not committed)
```

Code is MIT licensed; source-data licensing is separately reported by OpenML. No fitted results, simulated profits, or Australian conclusions have been claimed at this checkpoint.
