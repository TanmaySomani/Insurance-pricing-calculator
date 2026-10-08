# Project checkpoint — Part 3 complete

Updated: 8 October 2026, Australia/Brisbane.

Repository: [TanmaySomani/Insurance-pricing-calculator](https://github.com/TanmaySomani/Insurance-pricing-calculator), branch `main`. Verify publication using `git status`, `git log -3 --oneline` and the remote before continuing. Parts 1–2 were published as `db0f098` and `ca26bfc`; Part 3 publication is recorded in its handover.

## Objective and delivery boundaries

Build a client-ready motor pricing case study in resumable parts: public data; exposure-aware Poisson frequency and Gamma severity GLMs; boosting comparison; validation and diagnostics; commercial simulation and a live dashboard with editable/addable assumptions and segment rows; final two-page manager summary and GitHub handover. Optional Australian context comes after the core work. Complete one bounded part per handover.

Parts 1–3 are complete. **Next is Part 4: commercial engine and Streamlit dashboard.** Do not repeat model tuning or change targets using the now-published test results. The whole client delivery is not yet complete.

## Completed implementation

- Pinned OpenML freMTPL2 version-1 frequency/severity sources, verified SHA-256 downloads, policy/claim preparation, quality audit, deterministic features and splits.
- Source-count versus recorded-count reconciliation, orphan exclusion, coverage flags and full provenance manifest.
- Six converged GLM fits, intercept benchmarks, train/validation residual, dispersion, coefficient, influence and sensitivity evidence; four PNG/PDF figure pairs.
- Poisson/Gamma histogram boosting with a small predeclared validation-only search, uncapped main targets and two separately fitted sensitivities.
- Validation decision frozen before test access, with bundle/config/code/data/version checksums verified before evaluation.
- Identical final-test comparison, tie-aware exposure Gini, lift, deciles, segment A/E, paired policy-bootstrap intervals and tail/missing-cost sensitivities.
- Validation permutation/age-response diagnostics, fixed hypothetical profile examples, timings, five comparison PNG/PDF figure pairs and a business interpretation.
- Version 0.3.0 installed and its CLI evaluated successfully; **45 local tests pass**. Repeated frozen evaluation reproduced 13 evidence/model/selection files byte-for-byte. GitHub CI is defined but remote success has not been verified.

## Critical decisions — preserve

1. Use the pinned OpenML frequency/severity versions together. Raw-source hashes are in `configs/source_lock.json`; do not silently replace snapshots.
2. Main estimand: annual costs represented in the linked severity table. Frequency uses `recorded_claim_count`; severity uses individual positive recorded costs. This is not ultimate loss cost or a commercial premium.
3. Original claim counts remain a separately labelled missing-cost sensitivity. Their product with recorded severity assumes unverified representativeness, not recovered ultimate cost.
4. Keep all positive source exposures, including >1-year values. Fit frequency annual rates with exposure weights (equivalent to the documented count/log-exposure-offset likelihood); severity uses individual-claim unit weights. Annual predictions are multiplied by exposure only for historical evaluation.
5. Preserve mismatch flags. Missing cost rows do not establish zero ultimate losses; never delete all positive-count/no-cost policies or fabricate costs.
6. Seed 20261008 and SHA-256 of seed/policy ID assign approximately 60/20/20. Claims inherit policy splits. The final test is now scored; use it only to report this frozen comparison, not future tuning.
7. Source currency is historical EUR/French motor liability. No current Australian rates, observed historical loss ratios or measured renewal elasticity exist here.
8. GLM: unpenalised log links, 58 parameters per main model, train-only explicit-reference encoding, unknown-category rejection, Newton–Cholesky, tolerance 1e-8 and max 1,000 iterations, two threads. All six fits converged.
9. Boosting: four native categorical inputs plus five continuous inputs; no ID, exposure, outcome or mismatch predictors. Three candidates per component selected independently on validation loss. Selected frequency is 150 iterations/15 leaves/minimum leaf 200; severity is 75 iterations/3 leaves/minimum leaf 100. Learning rate 0.05, L2 10, bins 128, two threads, no automatic early stopping.
10. Keep both main targets uncapped and apply no calibration multiplier. Original-count and capped-severity boosting fits reuse selected hyperparameters without retuning; GLM complete-count fits remain selection-biased sensitivities.
11. Frozen **boosting dashboard default** passed validation screening: ≥1% pure-deviance gain, A/E within 0.80–1.25, paired validation deviance upper 95% bound below zero. This selects an illustrative dashboard default, not production or regulatory approval. GLM remains available as the explainable benchmark.
12. Bootstrap samples policies 250 times with identical samples for both models; repeated claims stay with policy. Predictions/orders/bins stay fixed. Intervals omit fitting/tuning, missing costs, drift and unidentified shared customers. `<100 claims` is a volume screen, not formal credibility.
13. Dashboard stack remains Python + Streamlit + Plotly. Commercial parameter edits recompute arithmetic without fitting models. Addable segment rows use one selected field and reject duplicates/unknown levels. New learned risk variables need data/refit/validation.

## Data findings

678,013 policies; 26,639 raw severity rows; 26,444 linked severity rows; 358,499.45 policy-years; 36,102 original claims. There are 9,117 mismatched policies, including 9,116 with positive source counts but no costs; 195 orphan severity records representing EUR 788,714.18 are excluded. Linked mean severity is EUR 2,265.51 and recorded cost per policy-year EUR 167.11. Largest 1% of linked claims represents about 38% of cost.

Policy counts: train 407,081; validation 135,686; test 135,246. Main training claims 15,945; validation claims 5,229; test claims 5,270. See `reports/DATA_AUDIT.md` and `reports/data_audit.json`.

## Part 2 benchmark and Part 3 results

Part 2 validation GLM pure-deviance was 81.203 versus intercept 87.047 (6.7% gain); GLM annual expected cost EUR 166.56 versus recorded EUR 165.91, A/E 0.996. Main train Pearson dispersion: Poisson 1.77, Gamma 23.38. Original-count sensitivity expected EUR 229.66/year, capped severity EUR 117.65/year, complete-count fit EUR 168.56/year. Cap EUR 16,792.95 removes 32.8% of training cost. Preserve `reports/glm/` as the historical Part 2 evidence.

Part 3 validation boosting pure-deviance 78.897 (2.84% gain vs GLM), A/E 1.081 and expected annual cost EUR 153.53. The decision was frozen at this point; test was then read with no refit or recalibration.

| Final-test measure | GLM | Boosting |
|---|---:|---:|
| Poisson deviance / exposure | 0.46107 | 0.44841 |
| Gamma deviance / claim | 1.56171 | 1.49984 |
| Tweedie p=1.5 deviance / exposure | 76.35327 | 73.87711 |
| Recorded pure-premium A/E | 0.88627 | 0.96098 |
| Expected recorded cost / year (EUR) | 165.98 | 153.08 |
| Raw exposure Gini | 0.358995 | 0.422504 |
| Normalised Gini | 0.364698 | 0.429215 |
| Top-decile cost-rate / portfolio-rate lift | 2.68138 | 3.45330 |

Test actual annual recorded cost is EUR 147.10. Pure-deviance improvement is 3.24%. Paired boosting-minus-GLM 95% sampling intervals: pure deviance −2.476 [−5.743, −0.391]; raw Gini +0.064 [0.019, 0.104]; top-decile lift +0.772 [−0.376, 2.396]. Severity-deviance difference also includes zero. Aggregate boosting A/E interval is 0.820–1.188. Do not claim all ranking/component gains are established.

Main boosting still beats GLM on pure deviance after capping evaluated outcomes or excluding the largest-cost policy, but those diagnostics change outcomes/population and are not refits or production promotion tests. The GLM 75+ cost A/E reverses from about 1.67 on validation to 0.70 on test. The 55–64 group remains below one in both. These support investigation and sensitivity testing, not direct age-rate multipliers. Fixed illustrative profile predictions can vary sharply across nearby ages, underscoring non-monotonic model behaviour.

Full evidence and trade-offs: `reports/comparison/MODEL_COMPARISON.md`. Recommendation: use boosting as the illustrative dashboard default and keep GLM available; compare both under identical commercial assumptions. Complete developed claims/current premiums/renewals/expenses and stability/governance review are needed for real repricing.

## Reproduction and artefacts

Local verified runtime: CPython 3.14.7, macOS arm64; dependencies pinned in `requirements.lock.txt`. From a fresh checkout:

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt
python -m pip install --no-deps .
insurance-pricing prepare
insurance-pricing train-glm
insurance-pricing train-boost
insurance-pricing evaluate
python -m pytest -q
```

Existing local bundles allow `insurance-pricing evaluate` without refitting. Do not repeat tuning based on published test evidence. Other runtime versions require rebuilding previous stages rather than loading unchecked binaries. The integrity lock rejects stale data/configs/code/bundles before scoring.

After source edits, reinstall with `python -m pip install --no-deps .`, or use `PYTHONPATH=src .venv/bin/python -m insurance_pricing.cli <command>`. Regular installation avoids a macOS hidden `.pth` editable-install issue encountered earlier.

- Raw and processed Parquet under `data/` are local and Git-ignored; source download needs network, cached work runs offline.
- `artifacts/glm/bundle.joblib` and `artifacts/boost/bundle.joblib`: reusable fitted bundles, Git-ignored.
- `artifacts/comparison/{validation,test}_{glm,boost}_predictions.parquet`: policy holdout exports with observed targets preserved and `pred_` prediction prefixes.
- `reports/glm/training_metadata.json`: Part 2 provenance, hashes, iterations and versions.
- `reports/comparison/selection.json`: validation-only choice, hyperparameters, category levels, hashes and versions.
- `evaluation_metadata.json`: frozen-selection digest and evaluation code hashes; `verification.json`: local execution/reproducibility evidence.
- Comparison CSVs: tuning, metrics, paired intervals, deciles, segments, concentration curves, tails, permutation/age response, hypothetical profiles and timings.
- Regenerate aggregate comparison figures: `PYTHONPATH=src .venv/bin/python figures/gen_fig_comparison.py`; GLM figures: `figures/gen_fig_glm.py`.

## Not yet implemented

Commercial engine, Streamlit dashboard, hosting and final two-page manager PDF. No simulated profit result, actual renewal elasticity, Australian market analysis, coefficient/parameter confidence intervals, monotonic constraints or temporal/customer validation. The source lacks dates/customer IDs/current premiums/renewals; do not imply those checks have occurred.

## Next action: Part 4

Read `docs/DASHBOARD_SPEC.md`, methodology and model comparison first. Implement the commercial numerical engine separately from UI, verify zero-change/zero-elasticity and weighted portfolio identities, then build the dashboard with pre-trained artefacts and live controls. Use annual renewal cohort weights (default one per policy), not historical exposure as forecast horizon. Preserve the same claims stress in baseline/scenario comparisons and label synthetic premium, scenario loss ratio and expected underwriting contribution as assumptions/model estimates.

Add a model switch, risk calculator, diagnostic pages and editable/addable one-field segment rules. Validate invalid inputs, unknown/duplicate levels, unsupported risk categories/ranges, empty filters and zero denominators. Provide saved/reloaded JSON scenarios, CSV exports and a sensitivity curve. Measure edit-to-result performance before claiming ~1 second. Keep missing-cost coverage/volume beside repricing signals. New custom parameters can be labelled stress assumptions; new learned features require data and refitting. The final two-page PDF belongs to Part 5.

Paste into a fresh chat:

> Continue Part 4 of Insurance-pricing-calculator. Read CHECKPOINT.md, docs/DASHBOARD_SPEC.md, docs/METHODOLOGY.md and reports/comparison/MODEL_COMPARISON.md. Parts 1–3 are complete; boosting is the frozen illustrative dashboard default and GLM the benchmark. Do not retune on the published test. Implement and independently verify the commercial scenario engine, then build a polished Streamlit/Plotly dashboard with live assumptions, editable/addable segment rows, model switch, risk calculator, diagnostics, saved scenarios and exports. Preserve recorded-cost/EUR limitations and distinguish observed/modelled/assumed values. Measure responsiveness, update the checkpoint and publish to the agreed GitHub repository. Keep the two-page manager PDF for Part 5.
