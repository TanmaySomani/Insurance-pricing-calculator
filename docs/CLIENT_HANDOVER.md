# Client handover

**Business decision:** Investigate a modest +5% option using actual premium and renewal evidence before rollout. The default scenario adds EUR 1.02m contribution with 6,537 fewer retained policies; at elasticity 6 it loses EUR 0.30m. Keep boosting and GLM available at a common price anchor. All commercial results are conditional simulations.

The five core parts are delivered as a reproducible portfolio case study. Public hosting and real tariff approval are separate decisions. Optional Australian public-data context has not been added.

## Start here

| Reader / task | Deliverable |
|---|---|
| Pricing manager: decision and uncertainty | [Two-page manager brief](../output/pdf/pricing_manager_brief.pdf) |
| Reviewer: data, fit, governance and usage limits | [Model cards](MODEL_CARDS.md), [methodology](METHODOLOGY.md) |
| Presenter: live demonstration | [Dashboard guide](DASHBOARD_USAGE.md), walkthrough below |
| Analyst: measured comparison | [Model evidence](../reports/comparison/MODEL_COMPARISON.md), [commercial evidence](../reports/dashboard/COMMERCIAL_REPORT.md) |
| Engineer: deployment and verification | [Deployment review](DEPLOYMENT.md), [checkpoint](../CHECKPOINT.md) |

## Install and demonstrate

Verified locally: CPython 3.14.7, macOS arm64. Create a fresh environment in the repository root:

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt
python -m pip install --no-deps .
python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8502
```

After running the commands above on your own computer, enter `http://127.0.0.1:8502` in a browser on that same computer. This accesses your own running dashboard; there is no public dashboard URL. For review without installation, use the [pricing-manager brief](../output/pdf/pricing_manager_brief.pdf) and [screenshots](../reports/dashboard/screenshots/).

The committed aggregates run scenario, portfolio, comparison, segment and saved-scenario pages without downloads or fitted binaries. Individual risk scoring additionally needs the verified full local pipeline. Do not train on a dashboard rerun.

## Five-minute manager demonstration

1. Open Rate scenarios with test cohort, boosting claims model and GLM price anchor. Explain that these are 135,246 assumed annual renewals, not an exposure-weighted future forecast. Show baseline contribution EUR 5.27m and expected retained volume 114,959.
2. Set global change to +5%. With elasticity 1.2, contribution becomes EUR 6.28m and retained volume 108,422. Premium falls from EUR 37.19m to EUR 36.83m because volume falls. Save as "Five percent review" and download JSON.
3. Change elasticity to 3, then 6. Contribution becomes EUR 5.76m, then EUR 4.97m. The final case is below baseline: response uncertainty determines the decision. Do not label a curve maximum a proven tariff optimum.
4. Restore elasticity 1.2. Switch claims model to GLM, keeping GLM price anchor fixed. Premium and retention stay unchanged; expected claims and contribution change. Changing the anchor separately changes prices and answers a different question.
5. Add age 55-64 through Segment adjustments; enter -3% and optional elasticity 2. This compounds with +5% to a +1.85% net segment move. Display segment volume and cost coverage. Explain why a historical low A/E does not prove a profitable discount.
6. Add a named severity stress with multiplier 1.1. Baseline and scenario claims both increase. Save a separate case, compare it with the unstressed case and explain the baseline basis. Avoid double-counting the same inflation in two controls.
7. Open Saved scenarios, restore a saved case and reload the downloaded JSON. Example files [1-5](../reports/dashboard/) reproduce the committed scenario table. Stored outputs are recomputed; mismatched versions are rejected. Downloads persist; the in-memory list is session-local.
8. Show Model comparison and Segment diagnostics. Note missing claim costs, uncertain top-decile improvement and age-75+ calibration reversal. With verified bundles, show Risk calculator as a hypothetical model response, not a quote.

The two saved browser previews are in [screenshots](../reports/dashboard/screenshots/). The rate screenshot shows the +5%, elasticity-1.2 case. The comparison screenshot shows the frozen model evidence. They are local verified previews, not evidence of a hosted service.

## Reproduce the analysis

```bash
insurance-pricing prepare
insurance-pricing train-glm
insurance-pricing train-boost
insurance-pricing evaluate
insurance-pricing prepare-dashboard
python -m pytest -q
```

These stages reproduce the predeclared pipeline. The now-published final test must not guide further tuning. Source snapshots/config/code/runtime identities are checked. Rebuilding across runtimes needs a new consistent set of earlier-stage artefacts. Raw, prepared and row-level outputs and fitted bundles remain Git-ignored. A deployment with bundles also needs both matching prepared Parquet tables under the current verifier.

## Rebuild and verify the handover

```bash
python -m pip install -r requirements-report.txt
python scripts/build_manager_brief.py
PYTHONPATH=src python scripts/verify_handover.py
PYTHONPATH=src python scripts/package_client.py
```

The PDF uses frozen CSV evidence, embedded sans fonts and deterministic metadata; its manifest records source/script/PDF hashes. Verify exactly two pages and inspect both rendered pages after content edits. Preview rendering uses Poppler, independent of the dashboard. The package script creates an allowlisted aggregate-demo ZIP under local `dist/`; it excludes raw/prepared data, model binaries, virtual environments and Git state, and verifies every packaged file hash. It is for local handover, not a public deployment.

## Acceptance and limits

Completed: source provenance and target audit; exposure-aware GLMs; frozen boosting comparison; lift/Gini/decile/segment diagnostics; uncertainty and tail sensitivity; independently reconciled renewal engine; live editable/addable assumptions and segment rows; risk support warnings; scenario persistence; PDF and model documentation; deployment review and portable aggregate package.

The latest execution evidence is [handover verification](../reports/handover/verification.json). Earlier-stage checks remain in their original reports. Local checks and remote CI are different evidence: consult the GitHub Actions run for a particular commit rather than inferring success from a workflow definition.

Not delivered or established: public URL/host operations; real premiums/renewals/elasticity; ultimate loss development; current Australian rates; production approval; temporal/customer validation; fairness or regulatory acceptance; parameter confidence bounds; monotonic constraints. The delivered case study is suitable for review and demonstration, with these boundaries visible.

## Proposed operational decision, owner and monitoring

Tanmay Somani owns this case-study repository. An insurer must assign its own pricing decision owner and actuarial/model reviewers before operational use. Request complete claims, current premiums, renewal outcomes, competitor context and expense economics. Agree a bounded pilot, retention/contribution tolerances and rollback authority using that evidence. Monitor actual/expected claims and premium, renewal retention and segment mix; reassess drift, coverage, tails and model disagreements. Numerical pilot thresholds are intentionally left for the insurer's data and risk appetite.

Documentation/assumption edits can be reviewed without retraining. Learned-feature, target, calibration or selection changes need controlled refitting and a new untouched evaluation cohort. Optional Australian market context should be a separate, cited analysis of APRA/ICA/BOM data.
