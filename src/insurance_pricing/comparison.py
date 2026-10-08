"""Separate validation-only selection from checksum-locked final evaluation."""

from importlib.metadata import version
import json
from pathlib import Path
import time

import joblib
import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.metrics import mean_gamma_deviance, mean_poisson_deviance, mean_tweedie_deviance

from insurance_pricing.boosting import BOOST_FEATURES, tune_boost
from insurance_pricing.data import CATEGORICAL_FEATURES, assign_split, engineer_features
from insurance_pricing.download import sha256
from insurance_pricing.metrics import aggregate_segments
from insurance_pricing.ranking import RankPlan, decile_labels, decile_report, model_contributions, paired_bootstrap, ranking_metrics
from insurance_pricing.training import combine_predictions, load_partitions


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def load_glm(root):
    meta = json.loads((root / "reports/glm/training_metadata.json").read_text())
    if sha256(root / "artifacts/glm/bundle.joblib") != meta["model_sha256"]:
        raise ValueError("GLM artifact checksum mismatch; rebuild Part 2")
    for name, digest in meta["processed_hashes"].items():
        if sha256(root / f"data/processed/{name}.parquet") != digest:
            raise ValueError("Prepared data differs from the GLM training snapshot")
    if sha256(root / "configs/glm.json") != meta["model_config_sha256"]:
        raise ValueError("GLM config changed since training")
    for name in ["models", "data"]:
        if sha256(root / f"src/insurance_pricing/{name}.py") != meta["code_sha256"][name]:
            raise ValueError("GLM model or feature code changed since training")
    for name, expected in meta["versions"].items():
        if version(name) != expected:
            raise ValueError(f"Runtime version differs for {name}; rebuild before comparison")
    return joblib.load(root / "artifacts/glm/bundle.joblib"), meta


def score_one(label, p, c, pp, cp):
    e = p.Exposure.to_numpy()
    row = {
        "model": label, "split": str(p.split.iloc[0]), "policies": len(p), "claims": len(c),
        "frequency_deviance": float(mean_poisson_deviance(p.recorded_claim_count / e, pp.frequency, sample_weight=e)),
        "severity_deviance": float(mean_gamma_deviance(c.ClaimAmount, cp.severity)),
        "pure_deviance": float(mean_tweedie_deviance(p.recorded_claim_cost / e, pp.pure_premium, sample_weight=e, power=1.5)),
        "frequency_AE": float(p.recorded_claim_count.sum() / np.sum(e * pp.frequency)),
        "severity_AE": float(c.ClaimAmount.sum() / cp.severity.sum()),
        "pure_premium_AE": float(p.recorded_claim_cost.sum() / np.sum(e * pp.pure_premium)),
        "actual_per_year_eur": float(p.recorded_claim_cost.sum() / e.sum()),
        "expected_per_year_eur": float(np.average(pp.pure_premium, weights=e)),
        **ranking_metrics(e, p.recorded_claim_cost, pp.pure_premium),
    }
    return row


def choose_default(metrics, intervals, gate):
    rows = metrics.set_index("model")
    gain = float(1 - rows.loc["boost", "pure_deviance"] / rows.loc["glm", "pure_deviance"])
    paired = intervals[intervals.model.eq("boost_minus_glm") & intervals.metric.eq("pure_deviance")].iloc[0]
    ae = float(rows.loc["boost", "pure_premium_AE"])
    checks = {
        "minimum_validation_gain": bool(gain >= gate["minimum_relative_pure_deviance_gain"]),
        "validation_calibration_corridor": bool(gate["minimum_AE"] <= ae <= gate["maximum_AE"]),
        "paired_validation_gain_clear": bool(paired.upper_95 < 0) if gate["require_paired_deviance_upper_95_below_zero"] else True,
    }
    return {"default_model": "boost" if all(checks.values()) else "glm", "relative_validation_deviance_gain": gain, "checks": checks, "scope": "Default for the illustrative dashboard only; not live-rate approval"}


def train_boost(root: Path):
    config = json.loads((root / "configs/boost.json").read_text())
    if config["tweedie_power"] != 1.5:
        raise ValueError("Comparison predeclares Tweedie power 1.5")
    glm, glm_meta = load_glm(root)
    partitions = load_partitions(root)
    p, c = partitions["train"]
    vp, vc = partitions["validation"]
    bundle, trials = tune_boost(p, c, vp, vc, config)
    reports, artifacts = root / "reports/comparison", root / "artifacts/boost"
    reports.mkdir(parents=True, exist_ok=True)
    artifacts.mkdir(parents=True, exist_ok=True)
    trials.to_csv(reports / "tuning.csv", index=False)
    predictions = {"glm": glm.predict(vp), "boost": bundle.predict(vp)}
    claim_predictions = {"glm": glm.predict(vc), "boost": bundle.predict(vc)}
    metrics = pd.DataFrame([score_one(name, vp, vc, predictions[name], claim_predictions[name]) for name in predictions])
    contributions = {name: model_contributions(vp, vc, predictions[name], claim_predictions[name]) for name in predictions}
    intervals = paired_bootstrap(vp, predictions, contributions, config["bootstrap_replicates"], config["seed"])
    metrics.to_csv(reports / "selection_validation_metrics.csv", index=False)
    intervals.to_csv(reports / "selection_validation_intervals.csv", index=False)
    joblib.dump(bundle, artifacts / "bundle.joblib", compress=3)
    decision = choose_default(metrics, intervals, config["promotion_gate"])
    selection = {
        "selection_population": "validation", "test_read_during_selection": False,
        "config": config, "config_sha256": sha256(root / "configs/boost.json"),
        "selected_parameters": bundle.selected, "features": BOOST_FEATURES,
        "category_levels": {col: list(levels) for col, levels in zip(BOOST_FEATURES[:4], bundle.encoder.categories_)},
        "calibration": "none", "decision": decision,
        "glm_sha256": glm_meta["model_sha256"], "boost_sha256": sha256(artifacts / "bundle.joblib"),
        "processed_hashes": glm_meta["processed_hashes"], "data_config_sha256": sha256(root / "configs/data.json"),
        "code_sha256": {name: sha256(root / f"src/insurance_pricing/{name}.py") for name in ["data", "models", "boosting", "ranking"]},
        "versions": glm_meta["versions"], "training_severity_cap_eur": bundle.severity_cap,
        "training_policies": len(p), "training_claims": len(c),
    }
    # This record is created without reading the final test population.
    write_json(reports / "selection.json", selection)
    print(metrics.to_string(index=False), flush=True)
    print(f"Frozen validation decision: {decision['default_model']}. Test remains unscored.", flush=True)
    return bundle


def verify_selection(root, selection):
    if selection["selection_population"] != "validation" or selection["test_read_during_selection"]:
        raise ValueError("Selection must have been made without final test access")
    checks = [(root / "configs/boost.json", selection["config_sha256"]), (root / "configs/data.json", selection["data_config_sha256"]), (root / "artifacts/boost/bundle.joblib", selection["boost_sha256"]), (root / "artifacts/glm/bundle.joblib", selection["glm_sha256"])]
    checks += [(root / f"data/processed/{name}.parquet", digest) for name, digest in selection["processed_hashes"].items()]
    checks += [(root / f"src/insurance_pricing/{name}.py", digest) for name, digest in selection["code_sha256"].items()]
    for path, digest in checks:
        if sha256(path) != digest:
            raise ValueError(f"Frozen comparison checksum changed: {path.name}; do not retune on test results")
    for name, expected in selection["versions"].items():
        if version(name) != expected:
            raise ValueError(f"Frozen runtime differs for {name}")


def load_test(root):
    p = pd.read_parquet(root / "data/processed/policies.parquet", filters=[("split", "==", "test")]).reset_index(drop=True)
    c = pd.read_parquet(root / "data/processed/claims.parquet", filters=[("split", "==", "test")]).reset_index(drop=True)
    config = json.loads((root / "configs/data.json").read_text())
    if p.empty or c.empty or not p.IDpol.is_unique or not (assign_split(p.IDpol, config) == "test").all() or not c.IDpol.isin(p.IDpol).all():
        raise ValueError("Final test policy partition is invalid")
    totals = c.groupby("IDpol").agg(n=("ClaimAmount", "size"), cost=("ClaimAmount", "sum")).reindex(p.IDpol, fill_value=0)
    if not np.array_equal(totals.n, p.recorded_claim_count) or not np.allclose(totals.cost, p.recorded_claim_cost):
        raise ValueError("Final test counts and costs do not reconcile")
    return p, c


def segment_frames(p):
    frame = p.copy()
    frame["bonus_malus_band"] = pd.cut(frame.BonusMalus, [0, 50, 75, 100, np.inf], labels=["50", "51–75", "76–100", "101+"])
    frame["exposure_band"] = pd.cut(frame.Exposure, [0, .05, .25, .5, 1, np.inf], labels=["0–0.05", "0.05–0.25", "0.25–0.50", "0.50–1.00", ">1.00"])
    frame["count_match_status"] = np.where(frame.claim_count_matches, "matched", "mismatch")
    return frame, CATEGORICAL_FEATURES + ["bonus_malus_band", "exposure_band", "count_match_status"]


def segment_uncertainty(p, predictions, replicates, seed):
    """Fixed segment/decile policy bootstrap, using shared samples for both models."""
    frame, fields = segment_frames(p)
    groups, labels, offset = [], [], 0
    for field in fields:
        codes, levels = pd.factorize(frame[field].astype(str), sort=True)
        groups.append(codes + offset)
        labels.extend((field, str(level), "both") for level in levels)
        offset += len(levels)
    for model, pp in predictions.items():
        codes, levels = pd.factorize(decile_labels(p.Exposure, pp.pure_premium), sort=True)
        groups.append(codes + offset)
        labels.extend(("risk_decile", str(level), model) for level in levels)
        offset += len(levels)
    column = np.concatenate(groups)
    row = np.tile(np.arange(len(p)), len(groups))
    membership = sparse.csr_matrix((np.ones(len(row)), (row, column)), shape=(len(p), offset)).T
    values = np.column_stack([p.recorded_claim_cost, p.Exposure * predictions["glm"].pure_premium, p.Exposure * predictions["boost"].pure_premium, p.Exposure])
    point = membership @ values
    draws = np.empty((replicates, offset, 4))
    rng = np.random.default_rng(seed)
    for k in range(replicates):
        weights = np.bincount(rng.integers(0, len(p), size=len(p)), minlength=len(p))
        draws[k] = membership @ (values * weights[:, None])
    rows = []
    for j, (field, level, population) in enumerate(labels):
        for model, expected_column in [("glm", 1), ("boost", 2)]:
            if population != "both" and population != model:
                continue
            ratios = np.divide(draws[:, j, 0], draws[:, j, expected_column], out=np.full(replicates, np.nan), where=draws[:, j, expected_column] > 0)
            finite = ratios[np.isfinite(ratios)]
            rows.append({"model": model, "feature": field, "segment": level, "cost_AE": float(point[j, 0] / point[j, expected_column]), "cost_AE_lower_95": float(np.quantile(finite, .025)) if len(finite) else None, "cost_AE_upper_95": float(np.quantile(finite, .975)) if len(finite) else None, "valid_replicates": len(finite)})
    return pd.DataFrame(rows)


def tail_sensitivities(p, c, predictions, cap):
    capped = c.assign(capped_cost=np.minimum(c.ClaimAmount, cap)).groupby("IDpol").capped_cost.sum().reindex(p.IDpol, fill_value=0).to_numpy()
    largest = int(np.argmax(p.recorded_claim_cost.to_numpy()))
    rows = []
    for name, pp in predictions.items():
        for scenario, cost, mask in [
            ("raw_recorded_outcomes", p.recorded_claim_cost.to_numpy(), np.ones(len(p), dtype=bool)),
            ("outcomes_capped_at_train_p99", capped, np.ones(len(p), dtype=bool)),
            ("largest_cost_policy_excluded", p.recorded_claim_cost.to_numpy(), np.arange(len(p)) != largest),
        ]:
            row = {"model": name, "scenario": scenario, "policies": int(mask.sum()), "cost_AE": float(cost[mask].sum() / np.sum(p.Exposure.to_numpy()[mask] * pp.pure_premium.to_numpy()[mask])), "pure_deviance": float(mean_tweedie_deviance(cost[mask] / p.Exposure.to_numpy()[mask], pp.pure_premium.to_numpy()[mask], sample_weight=p.Exposure.to_numpy()[mask], power=1.5)), **ranking_metrics(p.Exposure.to_numpy()[mask], cost[mask], pp.pure_premium.to_numpy()[mask])}
            rows.append(row)
        for scenario, column in [("source_count_illustrative", "source_count_premium"), ("capped_severity_fit", "capped_severity_premium")]:
            rows.append({"model": name, "scenario": scenario, "policies": len(p), "cost_AE": float(p.recorded_claim_cost.sum() / np.sum(p.Exposure * pp[column])), "pure_deviance": float(mean_tweedie_deviance(p.recorded_claim_cost / p.Exposure, pp[column], sample_weight=p.Exposure, power=1.5)), **ranking_metrics(p.Exposure, p.recorded_claim_cost, pp[column])})
    return pd.DataFrame(rows)


def explain_validation(glm, boost, p, config):
    sample = p.sample(n=min(len(p), config["permutation_sample_policies"]), random_state=config["seed"]).reset_index(drop=True)
    baseline = boost.predict(sample).pure_premium
    loss = mean_tweedie_deviance(sample.recorded_claim_cost / sample.Exposure, baseline, sample_weight=sample.Exposure, power=1.5)
    rng = np.random.default_rng(config["seed"])
    rows = []
    for feature in BOOST_FEATURES:
        increases = []
        for _ in range(config["permutation_repeats"]):
            changed = sample.copy()
            changed[feature] = changed[feature].to_numpy()[rng.permutation(len(sample))]
            prediction = boost.predict(changed).pure_premium
            increases.append(float(mean_tweedie_deviance(sample.recorded_claim_cost / sample.Exposure, prediction, sample_weight=sample.Exposure, power=1.5) - loss))
        rows.append({"feature": feature, "mean_deviance_increase": float(np.mean(increases)), "repeat_std": float(np.std(increases)), "sample_policies": len(sample), "repeats": config["permutation_repeats"]})
    sample = p.sample(n=min(len(p), config["partial_dependence_sample_policies"]), random_state=config["seed"]).reset_index(drop=True)
    effects = []
    for age in [18, 22, 25, 35, 45, 55, 65, 75, 85, 100]:
        changed = sample.copy()
        changed["DrivAge"] = age
        changed = engineer_features(changed)
        for name, bundle in [("glm", glm), ("boost", boost)]:
            pred = bundle.predict(changed)
            effects.append({"model": name, "driver_age": age, "mean_annual_frequency": float(pred.frequency.mean()), "mean_severity_eur": float(pred.severity.mean()), "mean_pure_premium_eur": float(pred.pure_premium.mean()), "sample_policies": len(sample)})
    return pd.DataFrame(rows), pd.DataFrame(effects)


def illustrative_profiles(glm, boost):
    """Fixed hypothetical risks: no outcome-based selection or policy disclosure."""
    profiles = engineer_features(pd.DataFrame([
        {"profile": f"Age {age}, BM {bonus}", "DrivAge": age, "BonusMalus": bonus,
         "VehAge": 5, "VehPower": 6, "Area": "C", "VehBrand": "B1",
         "VehGas": "Diesel", "Region": "R24", "Density": 1000}
        for age, bonus in [(20, 100), (22, 100), (25, 100), (40, 50), (40, 100), (80, 50)]
    ]))
    for name, bundle in [("glm", glm), ("boost", boost)]:
        predictions = bundle.predict(profiles)
        profiles[f"{name}_annual_frequency"] = predictions.frequency
        profiles[f"{name}_severity_eur"] = predictions.severity
        profiles[f"{name}_pure_premium_eur"] = predictions.pure_premium
    profiles["boost_to_glm_ratio"] = profiles.boost_pure_premium_eur / profiles.glm_pure_premium_eur
    return profiles


def evaluate_models(root: Path):
    reports = root / "reports/comparison"
    selection_path = reports / "selection.json"
    selection = json.loads(selection_path.read_text())
    verify_selection(root, selection)
    selection_digest = sha256(selection_path)
    config = selection["config"]
    # Avoid joblib's macOS physical-core probe; both bundles already limit threads.
    import os
    os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(config["threads"]))
    glm, _ = load_glm(root)
    boost = joblib.load(root / "artifacts/boost/bundle.joblib")
    partitions = load_partitions(root)
    # No model fitting or tuning occurs after this final-test read.
    partitions["test"] = load_test(root)
    artifacts = root / "artifacts/comparison"
    artifacts.mkdir(parents=True, exist_ok=True)
    metrics, intervals, deciles, segments, segment_ci, tails, curves, timings = [], [], [], [], [], [], [], []
    for split in ["validation", "test"]:
        p, c = partitions[split]
        predictions, claim_predictions = {}, {}
        for name, bundle in [("glm", glm), ("boost", boost)]:
            start = time.perf_counter()
            predictions[name], claim_predictions[name] = bundle.predict(p), bundle.predict(c)
            timings.append({"model": name, "split": split, "policies": len(p), "claims": len(c), "prediction_seconds": time.perf_counter() - start})
            combine_predictions(p, predictions[name]).to_parquet(artifacts / f"{split}_{name}_predictions.parquet", index=False)
            metrics.append(score_one(name, p, c, predictions[name], claim_predictions[name]))
            deciles.append(decile_report(p, predictions[name], name).assign(split=split))
            frame, fields = segment_frames(p)
            segments.extend(aggregate_segments(frame, predictions[name], field).assign(model=name, split=split) for field in fields)
            curve = RankPlan.create(predictions[name].pure_premium).curve(p.Exposure, p.recorded_claim_cost)
            chosen = np.unique(np.searchsorted(curve[0], np.linspace(0, 1, 201)).clip(max=len(curve[0]) - 1))
            curves.append(pd.DataFrame({"model": name, "split": split, "exposure_share": curve[0][chosen], "cost_share": curve[1][chosen]}))
        baseline_pp = pd.DataFrame({"frequency": glm.benchmark_frequency, "severity": glm.benchmark_severity, "pure_premium": glm.benchmark_frequency * glm.benchmark_severity}, index=p.index)
        baseline_cp = pd.DataFrame({"severity": glm.benchmark_severity}, index=c.index)
        metrics.append(score_one("intercept", p, c, baseline_pp, baseline_cp))
        contributions = {name: model_contributions(p, c, predictions[name], claim_predictions[name]) for name in predictions}
        intervals.append(paired_bootstrap(p, predictions, contributions, config["bootstrap_replicates"], config["seed"]).assign(split=split))
        segment_ci.append(segment_uncertainty(p, predictions, config["bootstrap_replicates"], config["seed"] + 1).assign(split=split))
        tails.append(tail_sensitivities(p, c, predictions, selection["training_severity_cap_eur"]).assign(split=split))
        print(f"Evaluated {split}: {len(p):,} policies with paired bootstrap and segment uncertainty", flush=True)
    metrics = pd.DataFrame(metrics)
    intervals = pd.concat(intervals, ignore_index=True)
    segment_ci = pd.concat(segment_ci, ignore_index=True)
    metrics.to_csv(reports / "metrics.csv", index=False)
    intervals.to_csv(reports / "paired_intervals.csv", index=False)
    deciles = pd.concat(deciles, ignore_index=True)
    deciles["segment"] = deciles.decile.astype(str)
    deciles = deciles.merge(segment_ci[segment_ci.feature.eq("risk_decile")].drop(columns=["feature", "cost_AE"]), on=["model", "split", "segment"], validate="one_to_one")
    deciles.to_csv(reports / "deciles.csv", index=False)
    segments = pd.concat(segments, ignore_index=True)
    segments["segment"] = segments.segment.astype(str)
    segments = segments.merge(segment_ci[~segment_ci.feature.eq("risk_decile")].drop(columns="cost_AE"), on=["model", "split", "feature", "segment"], validate="one_to_one")
    segments.to_csv(reports / "segments.csv", index=False)
    pd.concat(tails, ignore_index=True).to_csv(reports / "tail_sensitivities.csv", index=False)
    pd.concat(curves, ignore_index=True).to_csv(reports / "concentration_curves.csv", index=False)
    pd.DataFrame(timings).to_csv(reports / "prediction_timings.csv", index=False)
    importance, effects = explain_validation(glm, boost, partitions["validation"][0], config)
    importance.to_csv(reports / "permutation_importance.csv", index=False)
    effects.to_csv(reports / "driver_age_partial_dependence.csv", index=False)
    illustrative_profiles(glm, boost).to_csv(reports / "profile_examples.csv", index=False)
    if sha256(selection_path) != selection_digest:
        raise ValueError("Selection record changed during final evaluation")
    write_json(reports / "evaluation_metadata.json", {"selection_sha256": selection_digest, "model_selection_changed_after_test": False, "default_model": selection["decision"]["default_model"], "evaluated_partitions": ["validation", "test"], "bootstrap": "Fixed predictions and bins; paired fixed-size policy samples, percentile 95% intervals", "code_sha256": {name: sha256(root / f"src/insurance_pricing/{name}.py") for name in ["comparison", "ranking", "boosting"]}, "versions": selection["versions"]})
    from insurance_pricing.comparison_report import render_comparison, plot_comparison

    plot_comparison(root)
    (reports / "MODEL_COMPARISON.md").write_text(render_comparison(root, selection, metrics, intervals))
    print(metrics[metrics.split.eq("test")].to_string(index=False), flush=True)
    print("Final comparison saved; model selection remained frozen.", flush=True)
