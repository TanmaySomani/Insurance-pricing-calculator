# Project checkpoint — Part 2 complete

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
- Part 1 was published on `main` as `db0f098`.
- Part 2: six converged Poisson/Gamma fits, annual pure premium and intercept benchmarks, train/validation diagnostics and sensitivities, fixed-prediction policy-bootstrap calibration intervals, four verified PNG/PDF chart pairs and reusable model artefacts.
- Part 2 numerical implementation checks: independent count/offset likelihood comparison, score equations, model serialization, prediction export, exposure metrics and holdout guards. All 32 tests pass locally.

## Critical decisions — preserve when continuing

1. Use the pinned OpenML versions together, not a mix of CASdatasets/Kaggle/OpenML snapshots.
2. Main estimand: expected annual costs represented in the linked severity table. Frequency uses `recorded_claim_count`, not original `ClaimNb`; individual positive recorded costs form severity targets. Original counts remain for a separately labelled missing-cost sensitivity. This is not an ultimate technical premium.
3. Retain positive source exposure, including >1-year values. Use log-exposure offset or the documented equivalent frequency-rate/exposure-weighted likelihood. Severity is claim-level and not weighted by exposure.
4. Preserve discrepancy flags. No blanket deletion of positive-count policies without costs, and no claim that missing costs establish zero ultimate losses.
5. Seed 20261008 and SHA-256 of seed/policy ID assign approximately 60/20/20. Claims inherit the policy partition. Learned transforms use train; tuning/calibration use validation; final evaluation uses frozen test.
6. Source currency is EUR, historical French liability cover. No inferred Australian rates, current price levels, genuine historical loss ratio or estimated retention elasticity.
7. Dashboard stack: Python + Streamlit + Plotly. Editable commercial controls and segment rows recalculate scenarios; new learned risk variables require training data and validation.
8. Part 2 uses `PoissonRegressor(alpha=0)` with annual rate/exposure weights and `GammaRegressor(alpha=0)` with individual-claim unit weights. Train-only category encoding uses explicit bases and rejects unknown categories. Solver Newton–Cholesky, tolerance 1e-8, 1,000 maximum iterations, two threads; convergence warnings halt fitting. Six fits converged in 4–6 iterations.
9. Retain the uncapped main GLM. Original-count, complete-count-subset and train-p99-capped severity fits are sensitivities with different assumptions/selection/targets. No validation calibration multiplier is applied. Gamma log-link fits do not force aggregate cost totals to balance.
10. Final test remains unscored. Part 2 artefacts contain train/validation predictions only. Keep Part 3 tuning, calibration decisions and model choices on validation before one frozen final test comparison.

## Verified data findings

678,013 policies; 26,639 raw severity rows; 26,444 linked severity rows; 358,499.45 policy-years; 36,102 original claims. There are 9,117 count-mismatch policies, including 9,116 with positive original counts but no costs; 195 orphan severity rows representing EUR 788,714.18. Linked mean severity is EUR 2,265.51; recorded cost / policy-year EUR 167.11. Largest 1% of linked claims represents approximately 38% of cost.

Split policy counts: train 407,081; validation 135,686; test 135,246. Full generated details are in `reports/data_audit.json` and `reports/DATA_AUDIT.md`. Do not treat descriptive audit findings as model metrics or choose model parameters using the test aggregates.

## Part 2 results and recommendation

Main models: 58 parameters including intercept, 407,081 training policies and 15,945 training claims. Validation: 135,686 policies and 5,229 claims. Full results: `reports/glm/GLM_REPORT.md`.

| Validation measure | Intercept | GLM |
|---|---:|---:|
| Poisson deviance / exposure | 0.47426 | 0.45480 |
| Gamma deviance / claim | 1.77558 | 1.74455 |
| Tweedie p=1.5 deviance / exposure | 87.04714 | 81.20329 |
| Pure-premium A/E | 0.95267 | 0.99608 |
| Expected recorded cost / policy-year (EUR) | 174.15 | 166.56 |

Actual validation recorded cost is EUR 165.91/year. GLM pure-premium deviance improves 6.7% versus intercept. Portfolio A/E's fixed-prediction policy-bootstrap 95% interval is 0.806–1.233 (250 replicates); it reflects sampling variability only. Original-count sensitivity: EUR 229.66/year (+37.9% vs main), not recovered ultimate cost. Capped severity sensitivity: EUR 117.65/year; training cap EUR 16,792.95 removes 32.8% of training cost. Complete-count fit: EUR 168.56/year on all validation policies; conditioning on count match can select the population.

Main training Pearson dispersion: Poisson 1.77, Gamma 23.38. Age/region differences, particularly 75+ recorded-cost A/E about 1.67, require investigation rather than direct repricing. Count-table coverage varies by segment. `<100 claims` is a volume screen, not formal credibility. Frequency residuals vary across fitted intensity; exposure bands are diagnostic only. The recommendation is to retain the GLM benchmark and proceed to Part 3, without live rate deployment.

## Commands and execution evidence

Local verified runtime: CPython 3.14.7 on macOS arm64; versions are pinned in `requirements.lock.txt`.

```bash
source .venv/bin/activate
insurance-pricing prepare
insurance-pricing train-glm
python -m pytest -q
```

For development directly from source:

```bash
PYTHONPATH=src .venv/bin/python -m insurance_pricing.cli prepare
PYTHONPATH=src .venv/bin/python -m insurance_pricing.cli train-glm
.venv/bin/python -m pytest -q
```

Full preparation and GLM training have run against the real, checksum-verified snapshot. The current suite contains 32 data/model integrity cases. CI is defined but its remote execution must be checked after publication; do not represent it as passed without evidence.

An editable install failed to import because macOS marked its `.pth` file hidden. The documented setup therefore uses a regular package install and a `PYTHONPATH=src` alternative for development. Reinstall after package-code edits when using the installed CLI. This environment issue does not change target definitions or data preparation.

Local caches/processed tables under `data/` and model/prediction binaries under `artifacts/` are ignored by Git and can be rebuilt. Initial downloading needs network access; cached preparation, training and unit tests run offline. GitHub publication/authentication status is reported in the handover response; verify `git status`/`git log` and remote before continuing.

`artifacts/glm/bundle.joblib` stores the reusable model bundle. Predictions use `pred_` column prefixes and retain original outcomes. Row-level predictions/residuals stay local; summary reports and figures are committed. `reports/glm/training_metadata.json` records package versions, config/source/code/processed-data hashes, iterations and model checksum. Figure regeneration: `PYTHONPATH=src .venv/bin/python figures/gen_fig_glm.py`. Reinstall the package after code edits or use the direct-source CLI. This package is version 0.2.0.

## Not yet implemented

No boosting model, Gini/lift model-comparison uncertainty, final test evaluation, commercial simulation, Streamlit dashboard, hosting or final two-page manager PDF. Coefficient/parameter uncertainty is not estimated; current bootstrap intervals hold predictions fixed. This remains a portfolio case study under development, not the completed client delivery.

## Next action: Part 3

Read methodology, Part 2 report, model config and training metadata. Fit an exposure-aware frequency/severity boosting challenger on identical target definitions and splits. Plan a small validation-only tuning search. Add raw/normalised exposure-weighted concentration Gini, lift and decile/segment uncertainty, paired policy-bootstrap deviance differences, and large-loss sensitivity. Freeze model/calibration choices before final test scoring. Compare interpretability, calibration, stability, governance effort and measured lift; do not assume boosting wins. Update this checkpoint at the Part 3 handover.

Paste into a fresh chat:

> Continue Part 3 of Insurance-pricing-calculator. Read CHECKPOINT.md, docs/METHODOLOGY.md and reports/glm/GLM_REPORT.md first. Parts 1–2 are complete. Preserve the uncapped recorded-cost target, correct exposure/claim weights, original-count sensitivity and frozen policy splits. Build the gradient boosting challenger, validation-only tuning, exposure-weighted Gini/lift/decile comparison and paired policy-bootstrap uncertainty. Freeze choices before final test evaluation; explain model trade-offs and update the checkpoint. Keep the commercial dashboard and final two-page summary for Parts 4–5. Check GitHub publication and existing artefacts before making changes.
