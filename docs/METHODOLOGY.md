# Pricing methodology and decision rules

At Part 2, data preparation and the unpenalised Poisson/Gamma baseline are implemented, with train/validation diagnostics and sensitivity checks. Boosting, Gini/model comparison, final test evaluation and commercial simulation remain planned.

## Business objective and target

We want risk-differentiated annual expected claim costs and a transparent view of commercial trade-offs. The supplied data can only establish costs present in its claim table, not ultimate loss costs, real historical loss ratios, or observed renewal response.

Let `e_i` be source exposure in years, `n_i` the count of matched positive claim-cost records, and `c_i` their sum. The primary targets are `n_i/e_i` for annual recorded frequency and each positive `ClaimAmount` for claim severity. Policy loss cost is `c_i/e_i`.

Some policies have original `ClaimNb > 0` but no cost row. Their recorded-cost count and sum are zero **by definition of the observed table**, not because the true claim cost is known to be zero. `source_claim_count`, `claim_count_matches`, and `positive_source_count_no_cost` retain the discrepancy. Policies with a partial count match are also flagged. All eligible policies stay in the primary frequency population; we do not condition training on having a claim.

The main frequency and severity targets must refer to the same claim definition. Mixing original counts with mean severity from the smaller cost table would need an unverified representativeness assumption. It is therefore a sensitivity, not the primary estimate.

Part 2 fits a separate original-count Poisson frequency model and quantifies the difference, including by segment. Its product with recorded severity is an **illustrative missing-cost sensitivity**, not a recovered ground-truth ultimate premium. Additional checks show count-match coverage by segment and a complete-count subset result, with selection bias explicitly noted. No missing costs are imputed as known values.

Orphan claim-cost records cannot be modelled without risk factors or exposure. They are excluded from the joined target and quantified in the audit. Multiple severity rows for the same policy remain individual claims. Frequency policy IDs must be unique, and joins enforce one-to-one or many-to-one cardinality.

## Exposure and scale

All positive finite source exposures are retained, including values above one year. No count, exposure, or severity cap is silently applied. Frequency predictions are annual rates; multiply by exposure to obtain expected observed-period counts. Multiply annual pure premium by exposure to compare predicted and recorded observed-period costs.

Portfolio actual frequency is `sum(n_i)/sum(e_i)`. Portfolio actual loss cost is `sum(c_i)/sum(e_i)`. Never use the unweighted mean of policy annualised rates for these summaries.

## Features implemented in Part 1

| Feature | Transformation | Reason |
|---|---|---|
| Driver age | Fixed bands 18–24, 25–34, 35–44, 45–54, 55–64, 65–74, 75+ | Explainable nonlinear baseline |
| Vehicle age | New, 1–5, 6–10, 11–20, 21+ | Stable categories; unusual old vehicles retained |
| Vehicle power | Categories 4–11, 12+ for this source | Pool upper power levels; source value retained |
| Bonus/malus | Original value / 100 | Readable continuous coefficient scale |
| Density | `log1p(Density)` | Reduce skew without clipping source data |
| Area, brand, fuel, region | Strip export quotes, retain categories | Categorical risk factors with opaque brand labels |

Only `MODEL_FEATURES` enter the GLM. IDs, exposure, counts, costs, flags, and partition labels are excluded as predictors. Exposure belongs in the frequency likelihood, not the rating-factor design. Original numeric risk factors are retained so a boosting challenger can use appropriate continuous effects. Bonus/malus may capture historical claims information and underwriting practices; its timing and meaning cannot be fully audited from this snapshot.

These fixed transformations use no fitted full-sample quantiles. Encoders, splines, imputation if needed later, and any learned clipping thresholds must be fitted using training data only. Unseen categories must be handled explicitly and reported. No target encoding across splits.

## Frozen validation design

Seed 20261008 plus `IDpol` is hashed using SHA-256. The first 64 bits modulo 10,000 select train buckets [0,6000), validation [6000,8000), or test [8000,10000). Every severity row inherits the policy split. Assignment is deterministic across row order and processes, approximately 60/20/20.

Training fits parameters; validation selects preprocessing and hyperparameters, tail treatment, and any calibration. Test is for the final frozen comparison. Part 1 contains descriptive test audit aggregates for integrity; they must not guide model choices. The same test policies evaluate GLM and challenger. Record all model/feature/config versions and seeds.

No customer ID or time fields are available. A policy holdout can still share an unidentified customer or repeated risk across splits, and cannot prove future robustness. Do not call it out-of-time validation.

## Models implemented in Part 2 and planned for Part 3

Frequency baseline: Poisson GLM with log link, `E[n_i|x_i,e_i] = e_i * exp(x_i beta)`. The implementation uses scikit-learn's `PoissonRegressor(alpha=0)` on annual rate with exposure weights, equivalent to unpenalised count-target likelihood with a log-exposure offset. Tests compare it independently against a count/offset objective optimised using SciPy. Adding a penalty would change comparisons if weights are rescaled.

Severity baseline: scikit-learn `GammaRegressor(alpha=0)` with log link on individual positive claim costs. Each observed claim has weight one. A policy-average severity implementation would instead use recorded claim count weights. Frequency's training intercept score balances counts; Gamma's log-link intercept score balances the mean relative residual `actual/predicted - 1`, so aggregate severity/pure-premium totals need not balance exactly. No calibration multiplier is applied in Part 2.

The shared one-hot encoder learns categories from training policies only, drops the explicit reference levels in `configs/glm.json`, and rejects unseen categories. All six models use Newton–Cholesky, tolerance 1e-8, maximum 1,000 iterations and two compute threads. Convergence warnings halt training. Main fits have 58 parameters including intercept and full-rank Fisher information. The sensitivity models are original-count frequency, count-matched subset frequency/severity, and claim severity winsorised at the training-only 99th percentile. Main outcomes remain uncapped.

Implementation references: [PoissonRegressor](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.PoissonRegressor.html) and [GammaRegressor](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.GammaRegressor.html). Current verified package versions are pinned in `requirements.lock.txt` and saved with the training metadata.

Annual pure premium: `lambda_hat_i * severity_hat_i`. This is a frequency–severity approximation to recorded loss cost. Dependence through policy characteristics and unobserved factors must be discussed. It excludes loss development, inflation and commercial loadings.

Challenger: gradient boosting with Poisson frequency loss and positive Gamma severity loss, or a documented appropriate alternative. Use identical target definitions and splits. Frequency retains exposure weights. Hyperparameters are selected on validation data. Training artefacts must record the package versions and selected features. Tune a limited, documented search rather than repeatedly consulting test results.

Compare interpretability, fit, calibration, stability, computation, monitoring effort, and governance. Greater ranking lift alone is insufficient for promotion. GLM coefficients can explain multiplicative factors; boosting can capture interactions but requires more explanation and stability assessment. Do not claim automatic regulatory acceptance for either model.

## Validation and diagnostics required before a recommendation

- Exposure-weighted Poisson deviance and count actual/expected for frequency; Gamma deviance and claim-cost actual/expected for severity.
- Recorded pure-premium calibration and exposure-weighted Tweedie deviance with a predeclared power, e.g. 1.5.
- Lift and actual/expected charts by predicted-risk decile. Rank on annual pure premium; form approximately equal-exposure bins, aggregate observed costs and predicted cost `premium * exposure`, and show policy/claim counts. Document tied scores and deterministic boundaries.
- Exposure-weighted concentration Gini: sort by ascending predicted annual premium, plot cumulative exposure against cumulative recorded cost, and compute `1 - 2 * area`. Group equal scores to avoid artificial ordering lift. Normalised Gini divides by the corresponding ideal ordering on observed annual loss cost; label both and handle zero-cost portfolios.
- Policy-level bootstrap intervals for Gini, deviance differences, calibration and lift; repeated claims from one policy must stay together. Heavy tails may make rankings unstable.
- Actual/expected by age, region, vehicle, fuel, area, bonus/malus and missing-cost coverage; show segment credibility rather than reacting to isolated low-volume ratios.
- Poisson dispersion, deviance/Pearson residuals, influential observations, calibration slopes where meaningful, and GLM coefficient relativity plots.
- Severity tail concentration, residuals, largest-loss sensitivity, and uncapped main results. If a capped sensitivity is used, learn its threshold on train, report the retained/excluded cost and keep raw holdout costs visible.
- Permutation importance/partial dependence for boosting, with correlated-feature limitations. Explain policy examples and where models materially disagree.

## Decision gates

Part 2 evaluates train/validation only. It publishes decile/segment A/E, volume/coverage screens, training Pearson dispersion, residual bins, Fisher leverage and a dispersion-scaled Cook-like proxy. The proxy is approximate, not an exact leave-one-out refit. Fixed-prediction 250-replicate policy bootstrap intervals cover portfolio validation calibration, with repeat claims kept together through policy totals. They do not cover fitted-parameter uncertainty or missing claims. The `<100 recorded claims` segment flag is a simple screening rule, not formal credibility. Gini, lift uncertainty, paired model comparisons and final test results remain Part 3 requirements.

Residual checks include fitted observed-period intensity and validation exposure bands. Exposure is used in likelihood/evaluation, never as a rating predictor. Aggregate validation pure-premium A/E is approximately 0.996, but age/region discrepancies and the wide bootstrap interval remain material. Part 2's business recommendation is to retain the GLM benchmark for challenger evaluation rather than deploy rates.

Proceed to Part 2 when source hashes, cardinality, targets and splits reconcile. Proceed to commercial recommendations only after the model comparison, missing-cost sensitivity and tail uncertainty are documented. Promote a challenger only if its validation/test benefit is credible, calibration and material segment behaviour are acceptable, and explainability/monitoring costs are justified.

The manager-facing summary must lead with a bounded decision supported by findings, not a claim of achieved savings. Recommended real repricing requires actual current premiums, renewal outcomes, expense economics, claims development and applicable governance review.
