"""Build checked aggregate renewal inputs; never refit or select a model."""

from importlib.metadata import version
import hashlib
import json
import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from insurance_pricing.comparison import load_glm, verify_selection, write_json
from insurance_pricing.data import engineer_features
from insurance_pricing.download import sha256
from insurance_pricing.scenarios import ENGINE_VERSION, parse_inputs, simulate

SEGMENT_FIELDS = {"driver_age_band": "Driver age", "Region": "Region", "VehGas": "Fuel",
                  "VehBrand": "Vehicle brand", "Area": "Area", "vehicle_age_band": "Vehicle age",
                  "vehicle_power_band": "Vehicle power", "bonus_malus_band": "Bonus / malus"}
RAW_NUMERIC = ["DrivAge", "VehAge", "VehPower", "BonusMalus", "Density"]
RAW_CATEGORICAL = ["Area", "Region", "VehBrand", "VehGas"]


def add_segments(frame):
    out = frame.copy()
    out["bonus_malus_band"] = pd.cut(out.BonusMalus, [0, 50, 75, 100, np.inf], labels=["50", "51–75", "76–100", "101+"])
    return out


def prepare_dashboard(root: Path):
    selection = json.loads((root / "reports/comparison/selection.json").read_text())
    verify_selection(root, selection)
    os.environ.setdefault("LOKY_MAX_CPU_COUNT", "2")
    glm, _ = load_glm(root)
    boost = joblib.load(root / "artifacts/boost/bundle.joblib")
    p = pd.read_parquet(root / "data/processed/policies.parquet")
    frame = add_segments(p)
    frame["policies"] = 1.0
    frame["exposure"] = p.Exposure
    frame["source_claims"] = p.source_claim_count
    frame["recorded_claims"] = p.recorded_claim_count
    frame["recorded_cost"] = p.recorded_claim_cost
    frame["count_match_policies"] = p.claim_count_matches.astype(int)
    frame["missing_cost_policies"] = p.positive_source_count_no_cost.astype(int)
    for name, bundle in [("glm", glm), ("boost", boost)]:
        pred = bundle.predict(p)
        frame[f"{name}_loss"] = pred.pure_premium
        frame[f"{name}_historical_expected"] = p.Exposure * pred.pure_premium
    sum_fields = ["policies", "exposure", "source_claims", "recorded_claims", "recorded_cost", "count_match_policies", "missing_cost_policies", "glm_loss", "boost_loss", "glm_historical_expected", "boost_historical_expected"]
    rows = []
    for field in SEGMENT_FIELDS:
        groups = frame.groupby(["split", field], observed=True)[sum_fields].sum().reset_index().rename(columns={field: "segment"})
        groups["segment"] = groups.segment.astype(str)
        groups["field"] = field
        rows.append(groups)
    cohort = pd.concat(rows, ignore_index=True)
    destination = root / "reports/dashboard"
    destination.mkdir(parents=True, exist_ok=True)
    cohort.to_csv(destination / "cohort.csv", index=False)
    train = p[p.split.eq("train")]
    risk_spec = {
        "categories": {name: sorted(train[name].astype(str).unique()) for name in RAW_CATEGORICAL},
        "numeric": {name: {"min": float(train[name].min()), "max": float(train[name].max()), "p01": float(train[name].quantile(.01)), "p99": float(train[name].quantile(.99))} for name in RAW_NUMERIC},
        "power_levels": sorted(int(v) for v in train.VehPower.unique()),
    }
    write_json(destination / "risk_spec.json", risk_spec)
    support = train.groupby(["driver_age_band", "Region", "VehBrand", "VehGas"], observed=True).agg(policies=("IDpol", "size"), recorded_claims=("recorded_claim_count", "sum")).reset_index()
    support.to_csv(destination / "risk_support.csv", index=False)
    paths = [destination / name for name in ["cohort.csv", "risk_spec.json", "risk_support.csv"]]
    paths += sorted((root / "reports/comparison").glob("*.csv"))
    hashes = {str(path.relative_to(root)): sha256(path) for path in paths}
    identity = {"selection_sha256": sha256(root / "reports/comparison/selection.json"), "engine_sha256": sha256(root / "src/insurance_pricing/scenarios.py"), "engine_version": ENGINE_VERSION, "tables_sha256": hashes}
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    manifest = {**identity, "fingerprint": fingerprint, "catalog": {field: sorted(cohort[cohort.field.eq(field)].segment.unique()) for field in SEGMENT_FIELDS},
                "models": {name: selection[f"{name}_sha256"] for name in ["glm", "boost"]},
                "default_model": selection["decision"]["default_model"], "processed_hashes": selection["processed_hashes"],
                "renewal_weights": "One annual opportunity per policy; historical exposure does not weight the renewal forecast",
                "aggregation": "Exact for shared segment retention/rate/stress and affine baseline premium; no rounding or sampling",
                "versions": {name: version(name) for name in ["numpy", "pandas", "streamlit", "plotly"]}}
    write_json(destination / "manifest.json", manifest)
    print(f"Dashboard inputs: {len(p):,} policies, {len(cohort):,} aggregate rows; no model fitting", flush=True)


def load_dashboard(root: Path):
    manifest = json.loads((root / "reports/dashboard/manifest.json").read_text())
    if manifest["engine_version"] != ENGINE_VERSION or sha256(root / "src/insurance_pricing/scenarios.py") != manifest["engine_sha256"]:
        raise ValueError("Scenario engine changed; rerun prepare-dashboard to version the inputs")
    if sha256(root / "reports/comparison/selection.json") != manifest["selection_sha256"]:
        raise ValueError("Frozen model selection differs from the dashboard")
    identity = {key: manifest[key] for key in ["selection_sha256", "engine_sha256", "engine_version", "tables_sha256"]}
    if hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest() != manifest["fingerprint"]:
        raise ValueError("Dashboard identity does not reconcile")
    for name, digest in manifest["tables_sha256"].items():
        if sha256(root / name) != digest:
            raise ValueError(f"Dashboard evidence checksum changed: {name}")
    cohort = pd.read_csv(root / "reports/dashboard/cohort.csv", dtype={"segment": str})
    tables = {p.stem: pd.read_csv(p, dtype={"segment": str}) for p in (root / "reports/comparison").glob("*.csv")}
    return manifest, cohort, tables


def select_cohort(data, inputs):
    subset = data[data.field.eq(inputs["segment_field"])]
    if inputs["scope"] != "all":
        subset = subset[subset.split.eq(inputs["scope"])]
    numbers = subset.select_dtypes(include="number").columns
    result = subset.groupby("segment", sort=True)[numbers].sum().reset_index()
    if inputs["included_segments"] is not None:
        result = result[result.segment.isin(inputs["included_segments"])]
    return result.reset_index(drop=True)


def run_inputs(data, inputs, catalog):
    assumptions, rules, stresses = parse_inputs(inputs, catalog)
    cohort = select_cohort(data, inputs)
    # Rules for excluded levels remain saved but have no effect on the filter.
    active = [rule for rule in rules if rule.segment in set(cohort.segment)]
    result = simulate(cohort, assumptions, active, stresses, inputs["model"], inputs["premium_basis"])
    return cohort, result, assumptions, active, stresses


def load_risk_models(root: Path):
    selection = json.loads((root / "reports/comparison/selection.json").read_text())
    # Verify trusted local artefacts before joblib deserialisation. Uploaded files
    # are JSON assumptions only; they can never supply a model path or object.
    verify_selection(root, selection)
    os.environ.setdefault("LOKY_MAX_CPU_COUNT", "2")
    return {name: joblib.load(root / f"artifacts/{name}/bundle.joblib") for name in ["glm", "boost"]}


def risk_frame(values, spec):
    if set(values) != set(RAW_NUMERIC + RAW_CATEGORICAL):
        raise ValueError("Risk inputs must match the supported rating schema")
    for key in RAW_CATEGORICAL:
        if values[key] not in spec["categories"][key]:
            raise ValueError(f"Unsupported category for {key}")
    for key in RAW_NUMERIC:
        value = values[key]
        if isinstance(value, (str, bool)) or not np.isfinite(value) or not spec["numeric"][key]["min"] <= value <= spec["numeric"][key]["max"]:
            raise ValueError(f"{key} must be within the training range")
        if key != "Density" and int(value) != value:
            raise ValueError(f"{key} must be an integer")
    if values["VehPower"] not in spec["power_levels"]:
        raise ValueError("Unsupported vehicle power")
    return add_segments(engineer_features(pd.DataFrame([values])))
