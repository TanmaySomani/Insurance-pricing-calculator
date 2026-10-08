"""Build audited policy and claim tables without disguising source discrepancies.

The main target is cost represented in the linked severity table. A missing
severity row means no *recorded* cost, not proof that no ultimate loss exists.
Original ClaimNb is retained for a separately labelled frequency sensitivity.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from insurance_pricing.download import download, sha256

FREQUENCY_COLUMNS = [
    "IDpol", "ClaimNb", "Exposure", "Area", "VehPower", "VehAge", "DrivAge",
    "BonusMalus", "VehBrand", "VehGas", "Density", "Region",
]
RAW_FEATURES = ["Area", "VehPower", "VehAge", "DrivAge", "BonusMalus", "VehBrand", "VehGas", "Density", "Region"]
CATEGORICAL_FEATURES = ["Area", "VehBrand", "VehGas", "Region", "driver_age_band", "vehicle_age_band", "vehicle_power_band"]
NUMERIC_FEATURES = ["bonus_malus_scaled", "log_density"]
MODEL_FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES


def validate_sources(frequency: pd.DataFrame, severity: pd.DataFrame) -> None:
    """Fail on structural defects; record rather than erase valid unusual values."""
    for label, frame, required in [
        ("frequency", frequency, FREQUENCY_COLUMNS),
        ("severity", severity, ["IDpol", "ClaimAmount"]),
    ]:
        missing = set(required) - set(frame.columns)
        if missing:
            raise ValueError(f"{label}: missing columns {sorted(missing)}")
        if frame.empty or frame[required].isna().any().any():
            raise ValueError(f"{label}: empty data or missing required values")
        ids = frame["IDpol"].to_numpy(dtype=float)
        if not np.isfinite(ids).all() or (ids <= 0).any() or (ids != np.floor(ids)).any():
            raise ValueError(f"{label}: policy IDs must be positive finite integers")
    if frequency["IDpol"].duplicated().any():
        raise ValueError("frequency: duplicate policy IDs would multiply costs during the join")
    numeric = frequency[["ClaimNb", "Exposure", "VehPower", "VehAge", "DrivAge", "BonusMalus", "Density"]].astype(float)
    if not np.isfinite(numeric.to_numpy()).all():
        raise ValueError("frequency: non-finite numeric values")
    if (numeric["Exposure"] <= 0).any():
        raise ValueError("frequency: exposure must be positive")
    if (numeric.drop(columns="Exposure") < 0).any().any():
        raise ValueError("frequency: negative counts or risk factors")
    if (numeric["ClaimNb"] != np.floor(numeric["ClaimNb"])).any():
        raise ValueError("frequency: claim counts must be integers")
    if (numeric["DrivAge"] < 18).any():
        raise ValueError("frequency: driver age below documented driving age")
    amounts = severity["ClaimAmount"].to_numpy(dtype=float)
    if not np.isfinite(amounts).all() or (amounts <= 0).any():
        raise ValueError("severity: Gamma targets require strictly positive finite claim costs")
    for column in ["Area", "VehBrand", "VehGas", "Region"]:
        if frequency[column].astype(str).str.strip("' \"").eq("").any():
            raise ValueError(f"frequency: empty category in {column}")


def assign_split(ids: pd.Series, config: dict) -> np.ndarray:
    """Hash policy ID and seed, so claims and policies never cross partitions.

    Assignment is independent of row order, targets, and runtime hash randomisation.
    This is a policy holdout, not a customer holdout or an out-of-time test.
    """
    train_end = config["train_bucket_end"]
    validation_end = config["validation_bucket_end"]
    buckets = config["split_bucket_count"]
    if not 0 < train_end < validation_end < buckets:
        raise ValueError("Invalid split thresholds")
    seed = config["split_seed"]
    values = np.fromiter(
        (int(hashlib.sha256(f"{seed}:{int(policy_id)}".encode()).hexdigest()[:16], 16) % buckets for policy_id in ids),
        dtype=np.int64, count=len(ids),
    )
    return np.where(values < train_end, "train", np.where(values < validation_end, "validation", "test"))


def engineer_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Fixed business bands; no full-sample quantiles or learned preprocessing."""
    output = frame.copy()
    output["driver_age_band"] = pd.cut(
        output["DrivAge"], [17, 24, 34, 44, 54, 64, 74, np.inf],
        labels=["18–24", "25–34", "35–44", "45–54", "55–64", "65–74", "75+"],
    )
    output["vehicle_age_band"] = pd.cut(
        output["VehAge"], [-1, 0, 5, 10, 20, np.inf],
        labels=["New", "1–5", "6–10", "11–20", "21+"],
    )
    output["vehicle_power_band"] = output["VehPower"].astype(int).clip(upper=12).astype(str)
    output["bonus_malus_scaled"] = output["BonusMalus"].astype(float) / 100
    output["log_density"] = np.log1p(output["Density"].astype(float))
    return output


def build_tables(frequency: pd.DataFrame, severity: pd.DataFrame, config: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    validate_sources(frequency, severity)
    policies = frequency[FREQUENCY_COLUMNS].copy()
    policies["IDpol"] = policies["IDpol"].astype("int64")
    policies["source_claim_count"] = policies["ClaimNb"].astype("int64")
    for column in ["Area", "VehBrand", "VehGas", "Region"]:
        policies[column] = policies[column].astype(str).str.strip("' \"")
    claims = severity[["IDpol", "ClaimAmount"]].copy()
    claims["IDpol"] = claims["IDpol"].astype("int64")
    claims["claim_record_id"] = np.arange(len(claims), dtype=np.int64)
    # Multiple claims per policy are genuine observations, not duplicate policies.
    aggregate = claims.groupby("IDpol", sort=False).agg(
        recorded_claim_count=("ClaimAmount", "size"),
        recorded_claim_cost=("ClaimAmount", "sum"),
    )
    policies = policies.merge(aggregate, on="IDpol", how="left", validate="one_to_one")
    policies["recorded_claim_count"] = policies["recorded_claim_count"].fillna(0).astype("int64")
    policies["recorded_claim_cost"] = policies["recorded_claim_cost"].fillna(0.0)
    policies["claim_count_matches"] = policies["source_claim_count"].eq(policies["recorded_claim_count"])
    policies["positive_source_count_no_cost"] = policies["source_claim_count"].gt(0) & policies["recorded_claim_count"].eq(0)
    policies["recorded_frequency"] = policies["recorded_claim_count"] / policies["Exposure"]
    policies["source_frequency"] = policies["source_claim_count"] / policies["Exposure"]
    policies["recorded_loss_cost"] = policies["recorded_claim_cost"] / policies["Exposure"]
    policies["split"] = assign_split(policies["IDpol"], config)
    policies = engineer_features(policies)
    # Inner join excludes orphan claims; the audit explicitly quantifies their cost.
    claims = claims.merge(
        policies[["IDpol", "split", "claim_count_matches"] + RAW_FEATURES + MODEL_FEATURES[4:]],
        on="IDpol", how="inner", validate="many_to_one",
    )
    if not np.isclose(policies["recorded_claim_cost"].sum(), claims["ClaimAmount"].sum()):
        raise AssertionError("Joined claim costs do not reconcile")
    if policies["recorded_claim_count"].sum() != len(claims):
        raise AssertionError("Joined claim counts do not reconcile")
    return policies, claims


def summarise(policies: pd.DataFrame, claims: pd.DataFrame) -> dict:
    exposure = float(policies["Exposure"].sum())
    return {
        "policies": len(policies), "exposure_years": exposure,
        "source_claim_count": int(policies["source_claim_count"].sum()),
        "recorded_claim_count": int(policies["recorded_claim_count"].sum()),
        "recorded_claim_cost_eur": float(policies["recorded_claim_cost"].sum()),
        "source_frequency_per_year": float(policies["source_claim_count"].sum() / exposure) if exposure else None,
        "recorded_frequency_per_year": float(policies["recorded_claim_count"].sum() / exposure) if exposure else None,
        "recorded_severity_eur": float(claims["ClaimAmount"].mean()) if len(claims) else None,
        "recorded_loss_cost_per_year_eur": float(policies["recorded_claim_cost"].sum() / exposure) if exposure else None,
        "count_mismatch_policies": int((~policies["claim_count_matches"]).sum()),
        "positive_source_count_no_cost_policies": int(policies["positive_source_count_no_cost"].sum()),
        "exposure_over_one_year_policies": int(policies["Exposure"].gt(1).sum()),
    }


def audit_sources(frequency: pd.DataFrame, severity: pd.DataFrame, policies: pd.DataFrame, claims: pd.DataFrame) -> dict:
    unmatched = severity.loc[~severity["IDpol"].isin(policies["IDpol"])]
    amounts = claims["ClaimAmount"]
    top_n = max(1, int(np.ceil(len(amounts) * .01)))
    return {
        "target_basis": "Costs represented by matched, positive severity records; not ultimate claims",
        "raw_frequency_rows": len(frequency), "raw_severity_rows": len(severity),
        "missing_frequency_values": int(frequency.isna().sum().sum()),
        "missing_severity_values": int(severity.isna().sum().sum()),
        "duplicate_frequency_ids": int(frequency["IDpol"].duplicated().sum()),
        "unmatched_severity_records": len(unmatched),
        "unmatched_severity_cost_eur": float(unmatched["ClaimAmount"].sum()),
        "portfolio": summarise(policies, claims),
        "splits": {name: summarise(policies[policies["split"].eq(name)], claims[claims["split"].eq(name)]) for name in ["train", "validation", "test"]},
        "severity_percentiles_eur": {str(q): float(amounts.quantile(q)) for q in [.5, .9, .95, .99, .999, 1]},
        "top_one_percent_claim_cost_share": float(amounts.nlargest(top_n).sum() / amounts.sum()),
        "category_levels": {col: sorted(policies[col].unique().tolist()) for col in ["Area", "VehGas", "VehBrand", "Region"]},
        "warnings": [
            "Positive source counts without costs are not established zero ultimate losses.",
            "Original source counts and recorded-cost counts define different targets.",
            "Source exposure >1 year is retained; capping it would change annualised risk.",
            "No policy dates, customer IDs, historical premiums or renewal outcomes: no temporal validation or estimated elasticity.",
            "No inflation, development, expenses, taxes or reinsurance adjustment has been applied.",
        ],
    }


def render_audit(audit: dict) -> str:
    portfolio = audit["portfolio"]
    lines = [
        "# Data audit — Part 1", "", "Business conclusion: the snapshot supports a recorded-cost pricing case study. It cannot establish an ultimate technical premium or an optimal commercial rate without additional data.", "",
        "Generated by `insurance-pricing prepare`. Monetary observations are EUR at source values.", "",
        "| Measure | Observed value |", "|---|---:|",
        f"| Raw policy rows | {audit['raw_frequency_rows']:,} |",
        f"| Raw claim-cost rows | {audit['raw_severity_rows']:,} |",
        f"| Matched claim-cost rows | {portfolio['recorded_claim_count']:,} |",
        f"| Exposure (policy-years) | {portfolio['exposure_years']:,.2f} |",
        f"| Original claim count | {portfolio['source_claim_count']:,} |",
        f"| Count mismatch policies | {portfolio['count_mismatch_policies']:,} |",
        f"| Policies with positive original count and no cost row | {portfolio['positive_source_count_no_cost_policies']:,} |",
        f"| Orphan claim-cost rows excluded from modelling | {audit['unmatched_severity_records']:,} |",
        f"| Orphan claim cost excluded (EUR) | {audit['unmatched_severity_cost_eur']:,.2f} |",
        f"| Exposure above one year, retained | {portfolio['exposure_over_one_year_policies']:,} |",
        f"| Source claims / policy-year | {portfolio['source_frequency_per_year']:.5f} |",
        f"| Recorded claims / policy-year | {portfolio['recorded_frequency_per_year']:.5f} |",
        f"| Matched mean severity (EUR) | {portfolio['recorded_severity_eur']:,.2f} |",
        f"| Recorded cost / policy-year (EUR) | {portfolio['recorded_loss_cost_per_year_eur']:,.2f} |",
        f"| Share of cost in largest 1% of matched claims | {audit['top_one_percent_claim_cost_share']:.1%} |",
        "", "These are descriptive source statistics, not model performance or proposed prices.", "",
        "Missing required values and duplicate policy IDs were checked. Structural defects halt the pipeline. Repeated policy IDs in the severity table represent separate claim observations; they are aggregated only for policy targets.", "",
        "## Frozen partitions", "", "SHA-256 of seed and policy ID assigns approximately 60% / 20% / 20%. Every claim inherits its policy's split. No targets enter assignment. Descriptive audit statistics for the test partition do not tune preprocessing or model choices.", "",
        "| Split | Policies | Exposure | Recorded claims | Recorded cost / year (EUR) |", "|---|---:|---:|---:|---:|",
    ]
    for name, values in audit["splits"].items():
        lines.append(f"| {name} | {values['policies']:,} | {values['exposure_years']:,.2f} | {values['recorded_claim_count']:,} | {values['recorded_loss_cost_per_year_eur']:,.2f} |")
    lines += ["", "## Decisions and limitations", ""]
    lines += [f"- {warning}" for warning in audit["warnings"]]
    lines += ["", "See [methodology](../docs/METHODOLOGY.md) for target reconciliation, future sensitivity checks, feature definitions, and validation rules.", ""]
    return "\n".join(lines)


def prepare(root: Path) -> dict:
    download(root)
    config = json.loads((root / "configs/data.json").read_text())
    if config["target_basis"] != "linked_recorded_claim_costs" or config["exposure_treatment"] != "retain_positive_source_exposure_without_capping":
        raise ValueError("Unsupported target/exposure policy; update code and methodology together")
    frequency = pd.read_parquet(root / "data/raw/freMTPL2freq.parquet")
    severity = pd.read_parquet(root / "data/raw/freMTPL2sev.parquet")
    policies, claims = build_tables(frequency, severity, config)
    processed = root / "data/processed"
    processed.mkdir(parents=True, exist_ok=True)
    policies.to_parquet(processed / "policies.parquet", index=False)
    claims.to_parquet(processed / "claims.parquet", index=False)
    audit = audit_sources(frequency, severity, policies, claims)
    audit["config"] = config
    audit["feature_columns"] = MODEL_FEATURES
    audit["config_sha256"] = sha256(root / "configs/data.json")
    reports = root / "reports"
    (reports / "data_audit.json").write_text(json.dumps(audit, indent=2, allow_nan=False) + "\n")
    (reports / "DATA_AUDIT.md").write_text(render_audit(audit))
    pd.crosstab(policies["source_claim_count"], policies["recorded_claim_count"]).to_csv(reports / "claim_count_reconciliation.csv")
    summary = policies.groupby("driver_age_band", observed=True).agg(
        policies=("IDpol", "size"), exposure=("Exposure", "sum"),
        source_claims=("source_claim_count", "sum"), recorded_claims=("recorded_claim_count", "sum"),
        recorded_cost=("recorded_claim_cost", "sum"), mismatches=("claim_count_matches", lambda x: int((~x).sum())),
    )
    summary["recorded_frequency"] = summary["recorded_claims"] / summary["exposure"]
    summary["recorded_loss_cost_eur"] = summary["recorded_cost"] / summary["exposure"]
    summary.to_csv(reports / "segment_data_summary.csv")
    print(f"Prepared {len(policies):,} policies and {len(claims):,} matched claims. See reports/DATA_AUDIT.md.")
    return audit
