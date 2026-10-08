# Project checkpoint — Part 5 complete

Updated: 8 October 2026, Australia/Brisbane.

Repository: [TanmaySomani/Insurance-pricing-calculator](https://github.com/TanmaySomani/Insurance-pricing-calculator), branch `main`. Verify publication using `git status`, `git log -3 --oneline` and the remote before continuing. Parts 1–4 were published as `db0f098`, `ca26bfc`, `05856cd` and `ab39762`. Part 5 is the client-handover commit following Part 4; verify its exact hash in Git rather than embedding a self-referential hash in this file.

## Objective and delivery boundaries

Build a client-ready motor pricing case study in resumable parts: public data; exposure-aware Poisson frequency and Gamma severity GLMs; boosting comparison; validation and diagnostics; commercial simulation and a live dashboard with editable/addable assumptions and segment rows; final two-page manager summary and GitHub handover. Optional Australian context comes after the core work. Complete one bounded part per handover.

Parts 1–5 are complete as a locally verified portfolio case study. Do not repeat tuning or change targets using published test results. The two-page manager brief, client handover, model cards, clean README and aggregate packaging are delivered. Public hosting, operational repricing and optional Australian context are separate future work, not missing core-case-study deliverables.

## Completed implementation

- Pinned OpenML freMTPL2 version-1 frequency/severity sources, verified SHA-256 downloads, policy/claim preparation, quality audit, deterministic features and splits.
- Source-count versus recorded-count reconciliation, orphan exclusion, coverage flags and full provenance manifest.
- Six converged GLM fits, intercept benchmarks, train/validation residual, dispersion, coefficient, influence and sensitivity evidence; four PNG/PDF figure pairs.
- Poisson/Gamma histogram boosting with a small predeclared validation-only search, uncapped main targets and two separately fitted sensitivities.
- Validation decision frozen before test access, with bundle/config/code/data/version checksums verified before evaluation.
- Identical final-test comparison, tie-aware exposure Gini, lift, deciles, segment A/E, paired policy-bootstrap intervals and tail/missing-cost sensitivities.
- Validation permutation/age-response diagnostics, fixed hypothetical profile examples, timings, five comparison PNG/PDF figure pairs and a business interpretation.
- Version 0.3.0 installed and its CLI evaluated successfully; **45 local tests pass**. Repeated frozen evaluation reproduced 13 evidence/model/selection files byte-for-byte. GitHub CI is defined but remote success has not been verified.

- Part 4: independently checked annual renewal engine, exact segment totals, six-page Streamlit/Plotly dashboard, live controls, addable/editable segment and stress rows, model switch with a fixed price anchor, risk calculator/support screens, saved JSON/CSV scenarios, comparison/restore/import and verified browser previews.
- Version 0.4.0; **72 local tests pass**. Full 135,246-policy scenario calculations reconcile independently at tolerance 1e-12. Warm Python rerun p95 about 0.14s; warm browser KPI update 0.36s. JSON upload/reload verified. Public hosting remains unconfigured.

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

14. Commercial horizon is one assumed annual renewal per policy, default cohort final test; historical exposure is never a forecast weight. Default assumptions: retention 85%, elasticity 1.2, claims inflation 0%, variable expense 25%, fixed expense EUR 30 per retained annual policy, synthetic-price margin 10%, rate corridor −20% to +20%.
15. Baseline price anchor defaults to GLM and remains fixed when switching the claims model. Price is (anchor model loss + fixed expense) / (1 − variable expense − margin). Scenario LR uses synthetic premiums and contribution excludes capital/reinsurance/tax/investment income. Fixed expense is per retained policy, not book-level overhead.
16. Global/segment changes multiply; corridor breaches are rejected, not clipped. The default baseline shares claims inflation/stress with the changed-price case. Optional unstressed baseline is explicitly labelled. Named frequency/severity/loss stress rows are assumptions, not learned features.
17. Exact aggregates use annual loss sums and policy weights for one field at a time. Shared segment response/stress plus affine premiums preserve policy-level arithmetic. No cross-field overlapping rules. Empty/invalid inputs do not silently save or replace valid results.
18. Scenario JSON binds checked inputs to the source/model/engine fingerprint. Outputs are recomputed, unknown schema/version rejected, no uploaded model deserialisation. Saved comparison entries are session-local; download JSON for persistence. The committed aggregates run the scenario/diagnostic pages without local bundles; the risk calculator additionally needs verified local models.

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

## Part 4 commercial findings and recommendation

On the 135,246-policy illustrative annual renewal cohort, baseline expected retention is 114,959 policies, synthetic premium EUR 37.19m and expected contribution EUR 5.27m. Claims model is frozen boosting; baseline price anchor GLM.

A +5% move at assumed elasticity 1.2 gives contribution EUR 6.28m (+EUR 1.02m) and 108,422 retained policies (−6,537). At elasticity 3 the gain falls to EUR 0.49m and retained volume falls by 15,653. At elasticity 6 the contribution change is −EUR 0.30m and volume falls by 29,175. These are conditional simulated outcomes, not achieved profits or calibrated renewal forecasts. The recommendation is to investigate a modest bounded move and obtain actual premium/renewal evidence before rollout, rather than approve a blanket increase from a curve maximum.

`reports/dashboard/COMMERCIAL_REPORT.md` leads with the bounded business conclusion and explains claims inflation, synthetic LR, segment investigations and the expense basis. `example_scenarios.csv` and five versioned JSON examples support reproducible walkthroughs. Browser screenshots are under `reports/dashboard/screenshots/`; final preview is locally served on port 8502 (8501 was already occupied; no unrelated process was stopped).

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
insurance-pricing prepare-dashboard
python -m pytest -q
python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8502
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
- `reports/dashboard/cohort.csv`: 198 exact aggregate rows across three partitions and eight segmentation fields, with annual model loss sums and historical evidence, no source IDs.
- `reports/dashboard/manifest.json`, `risk_spec.json`, `risk_support.csv`: identity, supported ranges/categories and coarse training support.
- `reports/dashboard/verification.json` and `browser_verification.json`: independent full-policy arithmetic, preserved model hashes and separately recorded timing/browser evidence.
- `scripts/verify_dashboard.py`: regenerate numerical examples and warm Python benchmarks without model fitting.
- `app.py`: Streamlit entry point; `docs/DASHBOARD_USAGE.md`: launch and interaction guide. Restart the server after source-module edits; reinstall regular package code when using its CLI.
- Regenerate aggregate comparison figures: `PYTHONPATH=src .venv/bin/python figures/gen_fig_comparison.py`; GLM figures: `figures/gen_fig_glm.py`.

## Remaining boundaries

Public hosting and optional Australian analysis remain unconfigured. No actual renewal elasticity, achieved savings, current Australian pricing analysis, coefficient/parameter confidence bounds, monotonic constraints, fairness/regulatory approval or temporal/customer validation are established. Source data lacks current premiums, renewals, dates and customer IDs. The five-part case study is ready for review and demonstration within those limits.

## Part 5 delivery and verification

- `output/pdf/pricing_manager_brief.pdf`: exactly two A4 pages, leading with the commercial question and conditional recommendation. Evidence values are read from frozen CSVs; input/script/PDF hashes are in `reports/handover/brief_manifest.json`. Both rendered pages were visually checked for layout/readability. Embedded sans fonts make the content portable.
- `scripts/build_manager_brief.py`: deterministic PDF regeneration; optional `requirements-report.txt` pins ReportLab 4.4.9 and pypdf 6.10.0 without changing the modelling/application lock.
- `docs/CLIENT_HANDOVER.md`: acceptance boundaries, clean install, five-minute live walkthrough, reconstruction, responsibility and proposed operational decision.
- `docs/MODEL_CARDS.md`: targets/populations/features, fit/search, exposure, uncertainty, intended uses, unsupported uses, artefact identities and governance limitations.
- `docs/DEPLOYMENT.md`: reviewed aggregate versus full-scoring setup, health/readiness, versioned release/rollback and host limitations.
- Important deployment finding: `verify_selection` requires **both matching prepared policy/claim Parquet tables as well as both bundles**, configs, source and exact package versions. Shipping two joblibs alone cannot enable the current calculator. Prefer the aggregate demo for a public showcase until a controlled full-artefact or separately validated serving-manifest plan is chosen.
- `scripts/verify_handover.py`: verifies exactly two pages, PDF sources and visible numeric values/link, recomputes five scenario JSONs against their CSV evidence, exercises a fresh aggregate-only app tree across six page states and a +5% edit, and checks optional trusted local models without mutation. `reports/handover/verification.json` records executed evidence; `review.json` records the separate visual/test review.
- `scripts/package_client.py`: deterministic allowlisted client ZIP in local `dist/`, with per-file SHA-256 manifest and verification. No raw/prepared data, row-level exports, fitted model binaries, Git state, virtual environment or secrets are packaged. The source is committed; regenerated ZIP is local/Git-ignored.
- CI now defines PDF regeneration/integrity, aggregate-only handover verification and packaging after application tests. Consult commit-specific remote results separately; do not infer CI success from the workflow definition.
- Model/data/scenario source, frozen selection, comparison tables and application version 0.4.0 were preserved. No training, recalibration or new test-driven selection occurred in Part 5.

Rebuild this handover:

```bash
source .venv/bin/activate
python -m pip install -r requirements-report.txt
python scripts/build_manager_brief.py
PYTHONPATH=src python scripts/verify_handover.py
PYTHONPATH=src python scripts/package_client.py
python -m pytest -q
```

PDF previews are `output/pdf/pricing_manager_brief-page-1.png` and `-page-2.png`; re-render and inspect after content/layout edits. Main deployment uses the repository tree, not only an installed wheel.

## Possible next work — choose a separate scope

The five bounded parts are finished. A future task can add separately sourced Australian APRA/ICA/BOM context, arrange a deliberate public aggregate-demo deployment, or plan a new genuine insurer-data pricing study. Real operational repricing needs developed claims, current premiums, renewal/competitor evidence, expense economics, untouched time/customer validation and applicable governance review.

Paste into a fresh chat:

> Continue Insurance-pricing-calculator from CHECKPOINT.md. Parts 1–5 are complete: public-data audit, frozen GLM/boost comparison, tested live scenario dashboard, two-page manager PDF and client handover/model cards/aggregate packaging. Preserve the frozen estimand, models, test results and scenario identity. Do not retune or claim a hosted service, calibrated elasticity or production approval. Read docs/CLIENT_HANDOVER.md and docs/DEPLOYMENT.md, then carry out the newly requested scope. Optional Australian context must be separately sourced and evidenced; any full hosted risk calculator must account for both verified bundles and matching prepared data under the current verifier.
