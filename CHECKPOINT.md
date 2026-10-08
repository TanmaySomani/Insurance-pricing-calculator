# Project checkpoint — Part 1 complete

Updated: 8 October 2026, Australia/Brisbane.

Repository: [TanmaySomani/Insurance-pricing-calculator](https://github.com/TanmaySomani/Insurance-pricing-calculator).

## Objective and agreed scope

Build a client-ready motor pricing case study in resumable parts: public data; Poisson frequency and Gamma severity GLMs; boosting comparison; rigorous exposure-aware validation; live commercial dashboard with editable and addable assumptions/segment rows; final two-page manager summary and clean GitHub handover. Optional Australian market context comes after the core work. Complete one bounded part per handover.

## Completed

- Empty remote cloned into the current workspace; `origin` targets the user-specified repository and branch is `main`.
- freMTPL2 OpenML version-1 frequency/severity data researched, downloaded and pinned by SHA-256.
- Reusable CLI and tested data contract, source validation, join integrity, fixed feature engineering and policy-level train/validation/test partitions.
- Full audit, provenance manifest, claim-count reconciliation and driver-age segment summary.
- README, methodology, dataset decision, dashboard numerical specification and delivery roadmap.
- Python environment and dependency lock; CI definition for the integrity tests.

## Critical decisions — preserve when continuing

1. Use the pinned OpenML versions together, not a mix of CASdatasets/Kaggle/OpenML snapshots.
2. Main estimand: expected annual costs represented in the linked severity table. Frequency uses `recorded_claim_count`, not original `ClaimNb`; individual positive recorded costs form severity targets. Original counts remain for a separately labelled missing-cost sensitivity. This is not an ultimate technical premium.
3. Retain positive source exposure, including >1-year values. Use log-exposure offset or the documented equivalent frequency-rate/exposure-weighted likelihood. Severity is claim-level and not weighted by exposure.
4. Preserve discrepancy flags. No blanket deletion of positive-count policies without costs, and no claim that missing costs establish zero ultimate losses.
5. Seed 20261008 and SHA-256 of seed/policy ID assign approximately 60/20/20. Claims inherit the policy partition. Learned transforms use train; tuning/calibration use validation; final evaluation uses frozen test.
6. Source currency is EUR, historical French liability cover. No inferred Australian rates, current price levels, genuine historical loss ratio or estimated retention elasticity.
7. Dashboard stack: Python + Streamlit + Plotly. Editable commercial controls and segment rows recalculate scenarios; new learned risk variables require training data and validation.

## Verified data findings

678,013 policies; 26,639 raw severity rows; 26,444 linked severity rows; 358,499.45 policy-years; 36,102 original claims. There are 9,117 count-mismatch policies, including 9,116 with positive original counts but no costs; 195 orphan severity rows representing EUR 788,714.18. Linked mean severity is EUR 2,265.51; recorded cost / policy-year EUR 167.11. Largest 1% of linked claims represents approximately 38% of cost.

Split policy counts: train 407,081; validation 135,686; test 135,246. Full generated details are in `reports/data_audit.json` and `reports/DATA_AUDIT.md`. Do not treat descriptive audit findings as model metrics or choose model parameters using the test aggregates.

## Commands and execution evidence

Local verified runtime: CPython 3.14.7 on macOS arm64; versions are pinned in `requirements.lock.txt`.

```bash
source .venv/bin/activate
insurance-pricing prepare
python -m pytest -q
```

For development directly from source:

```bash
PYTHONPATH=src .venv/bin/python -m insurance_pricing.cli prepare
.venv/bin/python -m pytest -q
```

Full preparation has run against the real, checksum-verified snapshot. The current suite contains 22 financial-integrity, target-definition, partition and invalid-input cases. CI is defined but its remote execution must be checked after publication; do not represent it as passed without evidence.

An editable install failed to import because macOS marked its `.pth` file hidden. The documented setup therefore uses a regular package install and a `PYTHONPATH=src` alternative for development. Reinstall after package-code edits when using the installed CLI. This environment issue does not change target definitions or data preparation.

Local caches/processed tables under `data/` and future binaries under `artifacts/` are ignored by Git and can be rebuilt. Initial downloading needs network access; cached preparation and unit tests run offline. GitHub publication/authentication status is reported in the handover response; verify `git status`/`git log` and remote before continuing.

## Not yet implemented

No fitted GLMs, boosting model, model metrics, confidence intervals, commercial simulation, Streamlit dashboard, hosting or final two-page manager PDF. Part 1 is the foundation, not the completed client delivery.

## Next action: Part 2

Read `docs/METHODOLOGY.md`, `configs/data.json`, `src/insurance_pricing/data.py` and audit reports. Implement interpretable Poisson/Gamma baselines and an intercept benchmark with correct exposure/count bases, training-only preprocessing, validation diagnostics and saved artefacts. Add a source-count sensitivity, quantify missing-cost coverage by segment and document severity tail treatment. Keep all model choices away from the final test partition. Update this checkpoint and documentation at the Part 2 handover.

Paste into a fresh chat:

> Continue Part 2 of Insurance-pricing-calculator. Read CHECKPOINT.md and docs/METHODOLOGY.md first. Part 1 is complete; preserve the recorded-cost target, original-count sensitivity, uncapped positive exposure, frozen policy splits and leakage protections. Build reproducible Poisson frequency and Gamma severity GLMs, combine annual pure premium, add intercept benchmarks and validation diagnostics, and update the checkpoint. Save the boosting comparison, commercial dashboard and final two-page summary for their planned parts. Check GitHub publication status before making changes.
