# Model and commercial-engine cards

Version 0.4.0 application; frozen Part 3 models and Part 4 dashboard identity. Owner: Tanmay Somani. Reviewed for this case-study handover on 8 October 2026. These cards describe delivered behaviour; they do not establish production or regulatory approval.

## Shared data and intended use

Use: explainable pricing research, model comparison and conditional annual-renewal scenarios for historical French motor third-party liability. Do not use as a customer quote, ultimate claims estimate, Australian tariff or calibrated retention forecast.

OpenML freMTPL2 frequency 41214 and severity 41215, version 1; CC0 as reported in the saved source metadata. Source attribution and byte hashes: [source manifest](../reports/data_manifest.json) and [source lock](../configs/source_lock.json). Data has 678,013 policies, 358,499.45 policy-years and 26,444 linked positive claim costs. Exclude 195 orphan costs; retain all positive source exposures, including values above one year.

Main target: annual cost represented in the linked severity table. Recorded claim count divided by exposure is the frequency response, with exposure weights. Individual positive claim amount is the severity response, with unit weights. Frequency times severity is annual recorded loss cost. Missing cost rows are not proof of zero ultimate cost. Original source counts are a separate, explicitly assumptive sensitivity.

SHA-256 policy-ID assignment with seed 20261008 makes approximately 60/20/20 splits: 407,081 training, 135,686 validation and 135,246 test policies. Claims inherit their policy split. There are no customer identifiers or dates for customer/time separation. Fitted transformations and category levels use training data only. The final test is already published and must not guide further tuning.

## Poisson / Gamma GLM benchmark

- Algorithm: unpenalised log-link Poisson and Gamma GLMs; 58 parameters per component including intercept. Newton-Cholesky, tolerance 1e-8, maximum 1,000 iterations, two threads. Six main/benchmark/sensitivity fits converged.
- Features: categorical area, brand, fuel, region and fixed driver-age, vehicle-age and power bands; scaled bonus/malus and log density. Train-only reference coding; reference levels are in [GLM configuration](../configs/glm.json). Unknown categories are rejected.
- Exposure: annual count-rate fitting with exposure weights is equivalent to the documented Poisson count/log-exposure-offset likelihood. Exposure is not a rating predictor. Historical predicted costs use annual predictions times source exposure.
- Explanations: multiplicative coefficients, reference factors, calibration by segment/decile, residuals, dispersion and approximate one-step influence. Influence measures are not exact leave-one-out changes; coefficient confidence bounds were not delivered.
- Diagnostics: training Pearson dispersion 1.77 for frequency and 23.38 for severity. Large claims materially affect severity and calibration.
- Final-test results: pure-premium deviance 76.353; raw exposure Gini 0.359; actual/expected recorded cost 0.886; expected annual recorded cost EUR 165.98. See [GLM evidence](../reports/glm/GLM_REPORT.md).
- Artefact: `artifacts/glm/bundle.joblib`; SHA-256 `d522e47661aa671cd45f21a8a8a012f7918bda39e8eefa2599702cfdb1bbda64`. Local and Git-ignored.

## Histogram gradient-boosting challenger

- Algorithm: separate histogram Poisson/Gamma regressors, with the same targets, exposures and severity weights as GLM. Four native categorical inputs (area, brand, fuel, region); continuous power, vehicle age, driver age, bonus/malus and log density.
- Search: three predeclared candidates per component; choose each on validation deviance. Frequency: 150 iterations, 15 leaves, minimum leaf 200. Severity: 75 iterations, 3 leaves, minimum leaf 100. Shared learning rate 0.05, L2 10, 128 bins, two threads; no automatic early stopping or calibration multiplier. Main claims are uncapped.
- Selection: frozen before test access. Validation gate: at least 1% pure-deviance gain, A/E within 0.80-1.25 and paired deviance upper 95% sampling bound below zero. This selected the dashboard default only. No post-test refit/recalibration.
- Final-test results: pure-premium deviance 73.877 (3.24% lower than GLM); raw exposure Gini 0.423; A/E 0.961; expected annual recorded cost EUR 153.08. Actual recorded cost was EUR 147.10/year.
- Uncertainty: 250 paired policy-bootstrap draws with predictions, bins and order fixed. Boosting-minus-GLM pure deviance -2.476 [-5.743, -0.391]; Gini +0.064 [0.019, 0.104]. Top-decile lift and severity-deviance differences include zero. Intervals omit fitting/search, missing costs, drift and unidentified customer clusters.
- Explanations: validation permutation diagnostics, age response and six fixed hypothetical profiles. These are model response summaries, not causal effects. No monotonic constraints; nearby ages can have sharp differences. Coarse support and training-range warnings do not guarantee plausible joint combinations.
- Artefact: `artifacts/boost/bundle.joblib`; SHA-256 `d1b804e5e783d9ddbdb86f0ed5f0b808674567acc73e3426d4a1ed7076c59aea`. Local and Git-ignored. Details: [comparison report](../reports/comparison/MODEL_COMPARISON.md), [selection record](../reports/comparison/selection.json).

## Commercial engine: an assumption model

This engine does not learn behaviour. Each cohort policy represents one annual renewal opportunity; historical exposure never weights future renewals. Let L be anchor annual model loss, f expense per retained policy, v variable expense ratio and m synthetic-price margin:

`P0 = (L + f) / (1 - v - m)`; `P1 = P0 * (1 + global change) * (1 + segment change)`.

`q1 = min(1, q0 * (P1 / P0)^(-elasticity))`. Expected contribution is retained premium minus retained stressed model claims and specified expenses. Fixed expense scales with retained policies, not book-level overhead. Default baseline shares claims stress with the changed-price case; optional unstressed comparisons are labelled. Changing claims model holds the anchor prices fixed. Exact sums preserve policy-level arithmetic for one segmentation field with shared within-segment assumptions.

Defaults: retention 85%, elasticity 1.2, variable expense 25%, fixed expense EUR 30, margin 10%, inflation 0%, combined rate corridor -20% to +20%. Named frequency/severity/loss multipliers are assumptions, not new fitted rating variables. Unsupported/duplicate rules, non-finite values and corridor breaches are rejected. Empty filters do not produce a valid forecast. JSON inputs are fingerprint-bound and outputs recomputed.

Absent effects: actual premiums, calibrated renewal behaviour, competitor response, new business, unmodelled anti-selection, capital, reinsurance, taxes, investment income and developed ultimate claims. Scenario LR is based on synthetic premiums; it is not historical observed LR.

## Review before operational use

Missing costs affect 9,116 positive-source-count policies. The largest 1% of linked claims represents about 38% of cost. The GLM age-75+ A/E reverses between validation (about 1.67) and test (0.70); do not derive a broad age increase from one holdout. Age 55-64 warrants competitiveness investigation, not an automatic discount. Neither algorithm has demonstrated fairness, permitted-variable compliance or jurisdiction-specific acceptance.

For real pricing, obtain developed claims, current premiums, renewals and expense economics; validate customer/time separation and stability; complete applicable variable/fairness/explanation review. Define monitoring and rollback with a named owner. Replacing risk variables or changing selection needs a new, genuinely untouched evaluation population. Changes to assumptions do not require refitting.

Only load trusted, checksum-verified local bundles in the pinned runtime. The current verifier also requires matching prepared policy and claim Parquet files; bundles alone are insufficient. Model hashes detect changes relative to a trusted checkout; they do not authenticate an arbitrary checkout. Cross-version persisted-model loading is unsupported by [scikit-learn's persistence guidance](https://scikit-learn.org/stable/model_persistence.html).
