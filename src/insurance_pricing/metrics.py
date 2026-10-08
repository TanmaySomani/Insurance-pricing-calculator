"""Exposure-aware validation with actual/expected ratios and explicit units."""

import numpy as np
import pandas as pd
from scipy.special import xlogy
from sklearn.metrics import mean_gamma_deviance, mean_poisson_deviance, mean_tweedie_deviance


def safe_ratio(numerator: float, denominator: float) -> float | None:
    return float(numerator / denominator) if denominator > 0 else None


def poisson_residuals(counts, expected):
    counts, expected = np.asarray(counts, dtype=float), np.asarray(expected, dtype=float)
    if not np.isfinite(counts).all() or not np.isfinite(expected).all() or (counts < 0).any() or (expected <= 0).any():
        raise ValueError("Invalid Poisson residual inputs")
    deviance = 2 * (xlogy(counts, counts / expected) - counts + expected)
    return (counts - expected) / np.sqrt(expected), np.sign(counts - expected) * np.sqrt(np.maximum(deviance, 0))


def gamma_residuals(amounts, expected):
    ratio = np.asarray(amounts, dtype=float) / np.asarray(expected, dtype=float)
    if not np.isfinite(ratio).all() or (ratio <= 0).any():
        raise ValueError("Gamma residual inputs must be positive")
    return ratio - 1, np.sign(ratio - 1) * np.sqrt(np.maximum(2 * (ratio - 1 - np.log(ratio)), 0))


def score_models(policies, claims, pp, cp, power=1.5):
    rows = []
    e = policies["Exposure"].to_numpy()
    n = policies["recorded_claim_count"].to_numpy()
    cost = policies["recorded_claim_cost"].to_numpy()
    for label, f, s, pure in [("intercept", "benchmark_frequency", "benchmark_severity", "benchmark_premium"), ("glm", "frequency", "severity", "pure_premium")]:
        rows.append({
            "model": label, "split": str(policies["split"].iloc[0]),
            "frequency_poisson_deviance_per_exposure": float(mean_poisson_deviance(n / e, pp[f], sample_weight=e)),
            "frequency_AE": safe_ratio(n.sum(), np.sum(e * pp[f])),
            "severity_gamma_deviance_per_claim": float(mean_gamma_deviance(claims["ClaimAmount"], cp[s])),
            "severity_AE": safe_ratio(claims["ClaimAmount"].sum(), cp[s].sum()),
            "pure_premium_tweedie_deviance_per_exposure": float(mean_tweedie_deviance(cost / e, pp[pure], sample_weight=e, power=power)),
            "pure_premium_AE": safe_ratio(cost.sum(), np.sum(e * pp[pure])),
            "actual_cost_per_year_eur": float(cost.sum() / e.sum()),
            "predicted_cost_per_year_eur": float(np.average(pp[pure], weights=e)),
        })
    return pd.DataFrame(rows)


def aggregate_segments(policies, predictions, field, minimum_claims=100):
    frame = policies[[field, "IDpol", "Exposure", "source_claim_count", "recorded_claim_count", "recorded_claim_cost", "claim_count_matches"]].copy()
    frame["expected_count"] = predictions["frequency"].to_numpy() * frame["Exposure"]
    frame["expected_cost"] = predictions["pure_premium"].to_numpy() * frame["Exposure"]
    frame["source_count_expected_cost"] = predictions["source_count_premium"].to_numpy() * frame["Exposure"]
    out = frame.groupby(field, observed=True, dropna=False).agg(
        policies=("IDpol", "size"), exposure=("Exposure", "sum"),
        source_claims=("source_claim_count", "sum"), recorded_claims=("recorded_claim_count", "sum"),
        recorded_cost=("recorded_claim_cost", "sum"), expected_claims=("expected_count", "sum"),
        expected_cost=("expected_cost", "sum"), source_count_expected_cost=("source_count_expected_cost", "sum"),
        count_match_policies=("claim_count_matches", "sum"),
    ).reset_index().rename(columns={field: "segment"})
    out.insert(0, "feature", field)
    out["frequency_AE"] = out["recorded_claims"] / out["expected_claims"]
    out["cost_AE"] = out["recorded_cost"] / out["expected_cost"]
    out["actual_cost_per_year_eur"] = out["recorded_cost"] / out["exposure"]
    out["predicted_cost_per_year_eur"] = out["expected_cost"] / out["exposure"]
    out["policy_count_match_share"] = out["count_match_policies"] / out["policies"]
    out["recorded_to_source_claim_count_ratio"] = np.where(out["source_claims"] > 0, out["recorded_claims"] / out["source_claims"], np.nan)
    out["source_count_premium_uplift"] = out["source_count_expected_cost"] / out["expected_cost"] - 1
    out["low_claim_volume"] = out["recorded_claims"] < minimum_claims
    return out


def exposure_deciles(policies, predictions):
    """Assign tied predicted scores as a group using its exposure midpoint.

    Large tied-score groups can make uneven or missing bins; don't split ties
    by outcomes or arbitrary policy order to create apparent differentiation.
    """
    frame = policies.copy()
    frame["risk_score"] = predictions["pure_premium"].to_numpy()
    groups = frame.groupby("risk_score", sort=True)["Exposure"].sum()
    midpoint = (groups.cumsum() - .5 * groups) / groups.sum()
    bins = np.minimum((midpoint * 10).astype(int) + 1, 10)
    frame["risk_decile"] = frame["risk_score"].map(bins)
    return aggregate_segments(frame, predictions, "risk_decile", minimum_claims=100)


def bootstrap_calibration(policies, predictions, replicates, seed):
    """Fixed-size policy bootstrap: repeated claims are already grouped by policy.

    Predictions are held fixed. This measures validation sampling variability,
    not parameter uncertainty, future drift or unrecorded claims.
    """
    if replicates < 2:
        raise ValueError("At least two bootstrap replicates required")
    values = np.column_stack([
        policies["recorded_claim_count"], policies["recorded_claim_cost"],
        policies["Exposure"] * predictions["frequency"],
        policies["Exposure"] * predictions["pure_premium"],
        policies["recorded_claim_count"] * predictions["severity"],
    ])
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(replicates):
        totals = values[rng.integers(0, len(values), size=len(values))].sum(axis=0)
        draws.append([totals[0] / totals[2], totals[1] / totals[3], totals[1] / totals[4]])
    draws = np.array(draws)
    rows = []
    sums = values.sum(axis=0)
    points = [sums[0] / sums[2], sums[1] / sums[3], sums[1] / sums[4]]
    for k, label in enumerate(["frequency_AE", "pure_premium_AE", "severity_AE"]):
        rows.append({"metric": label, "point": float(points[k]), "lower_95": float(np.quantile(draws[:, k], .025)), "upper_95": float(np.quantile(draws[:, k], .975)), "replicates": replicates})
    return pd.DataFrame(rows)
