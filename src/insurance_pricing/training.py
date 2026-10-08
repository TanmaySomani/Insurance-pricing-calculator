"""Part 2 orchestration. Train and validation only; the final test stays sealed."""

from importlib.metadata import version
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from insurance_pricing.data import CATEGORICAL_FEATURES, MODEL_FEATURES, NUMERIC_FEATURES
from insurance_pricing.diagnostics import influence_summary, residual_bins
from insurance_pricing.download import sha256
from insurance_pricing.metrics import aggregate_segments, bootstrap_calibration, exposure_deciles, score_models
from insurance_pricing.models import coefficient_table, fit_bundle
from insurance_pricing.plotting import plot_glm


def load_partitions(root):
    audit = json.loads((root / "reports/data_audit.json").read_text())
    if audit["config_sha256"] != sha256(root / "configs/data.json"):
        raise ValueError("Data configuration changed: rerun prepare")
    lock = json.loads((root / "configs/source_lock.json").read_text())
    for kind, name in [("frequency", "freMTPL2freq"), ("severity", "freMTPL2sev")]:
        if sha256(root / f"data/raw/{name}.parquet") != lock[kind]["sha256"]:
            raise ValueError("Source checksum mismatch: rerun prepare with the verified sources")
    output = {}
    # Filter at the Parquet read; no test outcomes/predictions are evaluated here.
    for split in ["train", "validation"]:
        p = pd.read_parquet(root / "data/processed/policies.parquet", filters=[("split", "==", split)])
        c = pd.read_parquet(root / "data/processed/claims.parquet", filters=[("split", "==", split)])
        aggregated = c.groupby("IDpol").agg(n=("ClaimAmount", "size"), cost=("ClaimAmount", "sum")).reindex(p.IDpol, fill_value=0)
        if not p.IDpol.is_unique or not c.IDpol.isin(p.IDpol).all() or not np.array_equal(aggregated.n, p.recorded_claim_count) or not np.allclose(aggregated.cost, p.recorded_claim_cost):
            raise ValueError(f"{split} prepared tables no longer reconcile")
        output[split] = (p.reset_index(drop=True), c.reset_index(drop=True))
    if set(output["train"][0].IDpol) & set(output["validation"][0].IDpol):
        raise ValueError("Training and validation policy populations overlap")
    return output


def sensitivity_table(p, predictions, cap):
    rows = []
    full = np.ones(len(p), dtype=bool)
    for population, mask in [("all_validation", full), ("count_matched_validation", p.claim_count_matches.to_numpy())]:
        for model, column in [("intercept", "benchmark_premium"), ("glm_main", "pure_premium"), ("source_count_illustrative", "source_count_premium"), ("complete_subset_selected", "complete_subset_premium"), ("train_p99_capped_severity", "capped_severity_premium")]:
            expected = float(np.sum(p.Exposure.to_numpy()[mask] * predictions[column].to_numpy()[mask]))
            actual = float(p.recorded_claim_cost.to_numpy()[mask].sum())
            rows.append({"population": population, "model": model, "policies": int(mask.sum()), "exposure": float(p.Exposure.to_numpy()[mask].sum()), "actual_raw_cost_eur": actual, "expected_cost_eur": expected, "actual_expected": actual / expected, "predicted_cost_per_year_eur": expected / p.Exposure.to_numpy()[mask].sum(), "training_severity_cap_eur": cap if model == "train_p99_capped_severity" else None})
    return pd.DataFrame(rows)


def combine_predictions(frame, predictions):
    if not frame.index.equals(predictions.index):
        raise ValueError("Predictions do not align with source rows")
    # All fitted values have an explicit prefix, preserving original source targets.
    output = pd.concat([frame, predictions.add_prefix("pred_")], axis=1)
    if not output.columns.is_unique:
        raise ValueError("Prediction export would overwrite a source column")
    return output


def report_markdown(metrics, sensitivities, diagnostics, metadata, intervals):
    valid = metrics[metrics.split.eq("validation")].set_index("model")
    baseline, glm = valid.loc["intercept"], valid.loc["glm"]
    lines = [
        "# GLM baseline — Part 2", "",
        "**Recommendation:** retain this GLM as the interpretable recorded-cost benchmark and proceed to the boosting comparison. Do not use these estimates for live repricing: missing costs, tail volatility and commercial assumptions remain unresolved.", "",
        "All figures below are on the frozen validation population, not the final test. No validation calibration multiplier has been applied. Actual/expected (A/E) below 1 indicates predicted cost/count above observed; above 1 indicates the reverse.", "",
        "## Validation against an intercept-only benchmark", "",
        "| Measure | Intercept benchmark | GLM |", "|---|---:|---:|",
    ]
    for key, label in [
        ("frequency_poisson_deviance_per_exposure", "Poisson deviance / exposure (lower better)"),
        ("severity_gamma_deviance_per_claim", "Gamma deviance / claim (lower better)"),
        ("pure_premium_tweedie_deviance_per_exposure", f"Tweedie p={metadata['config']['tweedie_power']} deviance / exposure (lower better)"),
        ("frequency_AE", "Frequency A/E"), ("severity_AE", "Severity A/E"),
        ("pure_premium_AE", "Pure-premium A/E"), ("predicted_cost_per_year_eur", "Predicted recorded cost / policy-year (EUR)"),
    ]:
        lines.append(f"| {label} | {baseline[key]:.4f} | {glm[key]:.4f} |")
    improvement = 1 - glm['pure_premium_tweedie_deviance_per_exposure'] / baseline['pure_premium_tweedie_deviance_per_exposure']
    lines += ["", f"Recorded actual cost / policy-year is EUR {glm['actual_cost_per_year_eur']:.2f}. The benchmark frequency and severity are estimated on train, not validation. GLM pure-premium deviance is {improvement:.1%} lower than the intercept benchmark; this is a validation fit improvement, not a profit or retention estimate.", "",
              "![Validation deciles](figures/validation_deciles.png)", "",
              "## Calibration uncertainty", "", f"Fixed-prediction policy bootstrap, {metadata['config']['bootstrap_replicates']} replicates, percentile 95% intervals. This measures validation sampling variability only; it does not cover parameter uncertainty, unrecorded claims or future drift.", "",
              "| GLM metric | A/E | Lower 95% | Upper 95% |", "|---|---:|---:|---:|"]
    for row in intervals.itertuples():
        lines.append(f"| {row.metric} | {row.point:.3f} | {row.lower_95:.3f} | {row.upper_95:.3f} |")
    lines += ["", "## Sensitivity to claim definition and large losses", "",
              "| Scenario on all validation policies | Predicted EUR / year | Raw recorded-cost A/E |", "|---|---:|---:|"]
    for row in sensitivities[sensitivities.population.eq("all_validation")].itertuples():
        lines.append(f"| {row.model} | {row.predicted_cost_per_year_eur:.2f} | {row.actual_expected:.3f} |")
    uplift = sensitivities.loc[sensitivities.population.eq('all_validation') & sensitivities.model.eq('source_count_illustrative'), 'predicted_cost_per_year_eur'].iloc[0] / glm['predicted_cost_per_year_eur'] - 1
    lines += ["", f"The original-count sensitivity increases expected annual recorded-cost premium by {uplift:.1%} versus the main fit. This illustrates the importance of the unresolved claim-definition gap rather than establishing a required rate increase.", "",
              f"The capped sensitivity uses the training {100 * metadata['config']['severity_cap_quantile']:g}th percentile, EUR {metadata['severity_tail']['training_cap_eur']:.2f}. Winsorisation reduces training claim cost by {metadata['severity_tail']['training_cost_reduction_share']:.1%}; it is an alternative capped estimand, not a corrected full-cost premium. Every validation comparison above still uses uncapped actual costs.", "",
              "The source-count product assumes missing-cost claims have the modelled recorded-claim severity. That assumption is unverified; it is not an estimate of recovered ultimate loss. The complete-count subset conditions on outcomes and may select a different risk population. See the separate matched-population rows in `validation_sensitivities.csv`.", "",
              "![Age and coverage](figures/validation_age_and_coverage.png)", "",
              "Aggregate calibration hides segment differences: the 75+ age group has a notably higher recorded-cost A/E, while 55–74 is lower. These are investigation flags, not instructions to change rates by those percentages. Claim-count coverage differs by age and large losses can dominate segment results. The `<100 claims` flag in the segment CSV is a simple volume screen, not a formal credibility test; Part 3 must add uncertainty to the comparison.", "",
              "## Fit and diagnostics", "",
              f"All six fits converged with an unpenalised log link. The design contains {metadata['parameters_including_intercept']} parameters including intercept. Main training Pearson dispersion is {diagnostics['frequency']['pearson_dispersion']:.2f} for Poisson counts and {diagnostics['severity']['pearson_dispersion']:.2f} for Gamma severity.", "",
              "Poisson dispersion is an overdispersion diagnostic, not proof of invalid mean predictions. Gamma dispersion is particularly influenced by extreme claims. Standard Poisson variance assumptions should not be used uncritically for uncertainty. Leverage and a dispersion-scaled Cook-like proxy identify observations worth review; they are approximate one-step diagnostics, not exact leave-one-out effects.", "",
              "![Residual checks](figures/training_residuals.png)", "",
              "Frequency residuals vary across fitted observed-period count bins, including short exposures. This warrants investigation of exposure-related source effects and mean-model adequacy; it does not justify adding realised retrospective exposure as a rating predictor. Severity residual variation also warrants the large-loss sensitivity and a more flexible challenger.", "",
              "![Age factors](figures/driver_age_relativities.png)", "",
              "Category reference levels and conditional factor estimates are in `coefficients.csv`. No coefficient confidence bounds or causal interpretation are asserted. Continuous effects use +10 bonus/malus points and +1 log(1+density) as their reported increments. Rare severity segments may have unstable estimates even when convergence succeeds.", "",
              "## Implementation and reproducibility", "",
              "Run `insurance-pricing train-glm` after preparation. Category encoding learns from training policies only, uses named reference levels and rejects unknown categories. Frequency fits annual rate with exposure weights, equivalent to the unpenalised count likelihood with a log-exposure offset; severity fits individual positive claims without exposure weights. No rating outcomes, IDs or exposure enter the feature design.", "",
              "Models and row-level predictions/residuals are local under `artifacts/glm/`; aggregate reports and vector/raster figures are committed. Metadata records source/config/processed-data/code hashes, package versions, iterations and model checksum.", "",
              "The final test partition has not been scored in Part 2. Part 3 must freeze the comparison before test evaluation, and report Gini/lift with policy-level uncertainty and model trade-offs. No dashboard, true historical loss ratio, elasticity estimate or commercial profit result exists yet.", ""]
    return "\n".join(lines)


def train_glm(root: Path):
    config = json.loads((root / "configs/glm.json").read_text())
    partitions = load_partitions(root)
    train_p, train_c = partitions["train"]
    bundle = fit_bundle(train_p, train_c, config)
    reports, artifacts = root / "reports/glm", root / "artifacts/glm"
    reports.mkdir(parents=True, exist_ok=True)
    artifacts.mkdir(parents=True, exist_ok=True)
    all_metrics, predictions = [], {}
    for split, (p, c) in partitions.items():
        pp, cp = bundle.predict(p), bundle.predict(c)
        predictions[split] = (pp, cp)
        all_metrics.append(score_models(p, c, pp, cp, config["tweedie_power"]))
        combine_predictions(p, pp).to_parquet(artifacts / f"{split}_policy_predictions.parquet", index=False)
        combine_predictions(c, cp).to_parquet(artifacts / f"{split}_claim_predictions.parquet", index=False)
    metrics = pd.concat(all_metrics, ignore_index=True)
    metrics.to_csv(reports / "metrics.csv", index=False)
    coefficient_table(bundle).to_csv(reports / "coefficients.csv", index=False)
    valid_p, valid_c = partitions["validation"]
    valid_pp, _ = predictions["validation"]
    segments = []
    segment_p = valid_p.copy()
    segment_p["bonus_malus_band"] = pd.cut(segment_p.BonusMalus, [0, 50, 75, 100, np.inf], labels=["50", "51–75", "76–100", "101+"])
    segment_p["count_match_status"] = np.where(segment_p.claim_count_matches, "count matched", "count mismatch")
    segment_p["exposure_band"] = pd.cut(segment_p.Exposure, [0, .05, .25, .5, 1, np.inf], labels=["0–0.05", "0.05–0.25", "0.25–0.50", "0.50–1.00", ">1.00"])
    segment_p["density_band"] = pd.cut(segment_p.Density, [-1, 100, 1000, 5000, np.inf], labels=["0–100", "101–1000", "1001–5000", "5001+"])
    for field in CATEGORICAL_FEATURES + ["bonus_malus_band", "count_match_status", "exposure_band", "density_band"]:
        segments.append(aggregate_segments(segment_p, valid_pp, field, config["minimum_segment_claims"]))
    pd.concat(segments, ignore_index=True).to_csv(reports / "validation_segments.csv", index=False)
    exposure_deciles(valid_p, valid_pp).to_csv(reports / "validation_deciles.csv", index=False)
    intervals = bootstrap_calibration(valid_p, valid_pp, config["bootstrap_replicates"], config["bootstrap_seed"])
    intervals.to_csv(reports / "validation_calibration_intervals.csv", index=False)
    sensitivities = sensitivity_table(valid_p, valid_pp, bundle.severity_cap)
    sensitivities.to_csv(reports / "validation_sensitivities.csv", index=False)
    diagnostics = {}
    with threadpool_limits(limits=config["threads"]):
        for family, frame, fitted, actual, likelihood in [
            ("frequency", train_p, train_p.Exposure * predictions["train"][0].frequency, train_p.recorded_claim_count, "poisson"),
            ("severity", train_c, predictions["train"][1].severity, train_c.ClaimAmount, "gamma"),
        ]:
            rows, summary = influence_summary(bundle.transform(frame), fitted.to_numpy(), actual.to_numpy(), likelihood)
            diagnostics[family] = summary
            local_rows = pd.concat([frame[["IDpol"]].reset_index(drop=True), rows], axis=1)
            local_rows.to_parquet(artifacts / f"{family}_residuals.parquet", index=False)
            rows.quantile([.5, .9, .95, .99, .999, 1.]).rename_axis("quantile").to_csv(reports / f"{family}_influence_summary.csv")
            residual_bins(rows).to_csv(reports / f"{family}_residual_bins.csv", index=False)
    (reports / "diagnostics.json").write_text(json.dumps(diagnostics, indent=2, allow_nan=False) + "\n")
    model_path = artifacts / "bundle.joblib"
    joblib.dump(bundle, model_path, compress=3)
    packages = ["numpy", "pandas", "pyarrow", "scikit-learn", "scipy", "joblib", "threadpoolctl", "matplotlib"]
    metadata = {
        "target": "linked_recorded_costs", "evaluated_partitions": ["train", "validation"],
        "test_evaluated": False, "config": config, "features": MODEL_FEATURES,
        "encoded_features": bundle.feature_names(), "numeric_features": NUMERIC_FEATURES,
        "parameters_including_intercept": len(bundle.feature_names()) + 1,
        "iterations": {name: model.n_iter_ for name, model in bundle.models.items()},
        "intercepts": {name: float(model.intercept_) for name, model in bundle.models.items()},
        "versions": {name: version(name) for name in packages},
        "source_manifest": json.loads((root / "reports/data_manifest.json").read_text()),
        "data_config_sha256": sha256(root / "configs/data.json"), "model_config_sha256": sha256(root / "configs/glm.json"),
        "processed_hashes": {name: sha256(root / f"data/processed/{name}.parquet") for name in ["policies", "claims"]},
        "model_sha256": sha256(model_path),
        "code_sha256": {name: sha256(root / f"src/insurance_pricing/{name}.py") for name in ["data", "models", "metrics", "diagnostics", "plotting", "training"]},
        "training_policies": len(train_p), "training_claims": len(train_c),
        "validation_policies": len(valid_p), "validation_claims": len(valid_c),
        "benchmark_frequency": bundle.benchmark_frequency, "benchmark_severity": bundle.benchmark_severity,
        "severity_tail": {
            "training_cap_eur": bundle.severity_cap,
            "training_claims_above_cap": int((train_c.ClaimAmount > bundle.severity_cap).sum()),
            "training_cost_reduction_share": float(1 - np.minimum(train_c.ClaimAmount, bundle.severity_cap).sum() / train_c.ClaimAmount.sum()),
        },
    }
    (reports / "training_metadata.json").write_text(json.dumps(metadata, indent=2, allow_nan=False) + "\n")
    plot_glm(root)
    (reports / "GLM_REPORT.md").write_text(report_markdown(metrics, sensitivities, diagnostics, metadata, intervals))
    print(metrics[metrics.split.eq("validation")].to_string(index=False), flush=True)
    print("Part 2 saved: reports/glm/GLM_REPORT.md. Final test not evaluated.", flush=True)
    return bundle
