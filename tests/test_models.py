"""Independent likelihood checks, leakage guards and scenario-target safeguards."""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from scipy.optimize import minimize
from threadpoolctl import threadpool_limits

from insurance_pricing.data import CATEGORICAL_FEATURES
from insurance_pricing.diagnostics import influence_summary
from insurance_pricing.metrics import bootstrap_calibration, exposure_deciles, gamma_residuals, poisson_residuals, score_models
from insurance_pricing.models import coefficient_table, fit_bundle
from insurance_pricing.training import combine_predictions


@pytest.fixture(scope="module")
def fitted():
    config = json.loads((Path(__file__).resolve().parents[1] / "configs/glm.json").read_text())
    rng = np.random.default_rng(810)
    p = pd.DataFrame({"IDpol": np.arange(1, 1501), "split": "train", "Exposure": rng.uniform(.1, 2, 1500)})
    alternates = ["A", "B2", "Regular", "R11", "18–24", "New", "4"]
    for col, alternate in zip(CATEGORICAL_FEATURES, alternates):
        p[col] = rng.choice([config["categorical_references"][col], alternate], len(p))
    p["bonus_malus_scaled"] = rng.uniform(.5, 2, len(p))
    p["log_density"] = rng.uniform(1, 10, len(p))
    true_frequency = np.exp(-1.6 + .3 * p.bonus_malus_scaled + .04 * p.log_density + .5 * p.driver_age_band.eq("18–24"))
    p["recorded_claim_count"] = rng.poisson(p.Exposure * true_frequency)
    p["source_claim_count"] = p.recorded_claim_count + rng.binomial(1, .1, len(p))
    p["source_frequency"] = p.source_claim_count / p.Exposure
    p["claim_count_matches"] = p.source_claim_count.eq(p.recorded_claim_count)
    c = p.loc[p.index.repeat(p.recorded_claim_count)].reset_index(drop=True).copy()
    mean_severity = np.exp(6.8 + .1 * c.log_density + .4 * c.driver_age_band.eq("18–24"))
    c["ClaimAmount"] = rng.gamma(shape=2, scale=mean_severity / 2)
    p["recorded_claim_cost"] = p.IDpol.map(c.groupby("IDpol").ClaimAmount.sum()).fillna(0)
    bundle = fit_bundle(p, c, config)
    return p, c, bundle


def test_rate_weighted_fit_matches_independent_count_offset_likelihood(fitted):
    p, _, bundle = fitted
    x = bundle.transform(p).toarray()
    z = np.column_stack([np.ones(len(x)), x])
    e, n = p.Exposure.to_numpy(), p.recorded_claim_count.to_numpy()

    def objective(beta):
        eta = z @ beta
        mu = e * np.exp(eta)
        return float(np.mean(mu - n * eta)), z.T @ (mu - n) / len(n)

    with threadpool_limits(limits=2):
        result = minimize(objective, np.zeros(z.shape[1]), jac=True, method="BFGS", options={"gtol": 1e-8})
    independent = np.exp(z @ result.x)
    np.testing.assert_allclose(bundle.predict(p).frequency, independent, rtol=2e-5)
    assert np.linalg.norm(objective(result.x)[1], ord=np.inf) < 1e-7


def test_intercept_balances_count_and_gamma_score_equations(fitted):
    p, c, bundle = fitted
    pp, cp = bundle.predict(p), bundle.predict(c)
    assert np.sum(p.Exposure * pp.frequency) == pytest.approx(p.recorded_claim_count.sum(), rel=1e-7)
    assert np.sum(p.Exposure * pp.source_frequency) == pytest.approx(p.source_claim_count.sum(), rel=1e-7)
    assert np.mean(c.ClaimAmount / cp.severity - 1) == pytest.approx(0, abs=1e-7)
    assert bundle.benchmark_frequency * bundle.benchmark_severity == pytest.approx(p.recorded_claim_cost.sum() / p.Exposure.sum())
    np.testing.assert_allclose(pp.pure_premium, pp.frequency * pp.severity)


def test_artifact_preserves_original_target_and_prefixes_predictions(fitted, tmp_path):
    p, _, bundle = fitted
    exported = combine_predictions(p, bundle.predict(p))
    assert exported.columns.is_unique
    pd.testing.assert_series_equal(exported.source_frequency, p.source_frequency)
    assert "pred_source_frequency" in exported
    exported.to_parquet(tmp_path / "predictions.parquet", index=False)
    assert pd.read_parquet(tmp_path / "predictions.parquet").columns.is_unique
    with pytest.raises(ValueError, match="align"):
        combine_predictions(p, bundle.predict(p).iloc[::-1])


def test_holdout_training_and_inconsistent_claim_population_fail(fitted):
    p, c, bundle = fitted
    bad = p.copy()
    bad.loc[0, "split"] = "validation"
    with pytest.raises(ValueError, match="training-only"):
        fit_bundle(bad, c, bundle.config)
    with pytest.raises(ValueError, match="reconcile"):
        fit_bundle(p, c.iloc[:-1], bundle.config)


def test_unknown_categories_and_outcome_changes_cannot_silently_change_risk(fitted):
    p, _, bundle = fitted
    changed = p.copy()
    changed["recorded_claim_cost"] = 1e12
    changed["source_claim_count"] = 999
    changed["Exposure"] = 100
    np.testing.assert_allclose(bundle.predict(p).pure_premium, bundle.predict(changed).pure_premium)
    changed.loc[0, "Region"] = "unseen_region"
    with pytest.raises(ValueError, match="unknown categories"):
        bundle.predict(changed)


def test_bundle_roundtrip_and_reference_relativities(fitted, tmp_path):
    p, _, bundle = fitted
    joblib.dump(bundle, tmp_path / "trusted.joblib")
    restored = joblib.load(tmp_path / "trusted.joblib")
    np.testing.assert_array_equal(bundle.predict(p).pure_premium, restored.predict(p).pure_premium)
    coefficients = coefficient_table(bundle)
    refs = coefficients[coefficients.level_or_increment.eq(coefficients.reference)]
    assert len(refs) == 2 * len(CATEGORICAL_FEATURES)
    assert refs.relativity.eq(1).all()
    assert bundle.severity_cap == pytest.approx(np.quantile(fitted[1].ClaimAmount, .99))


def test_residuals_use_count_exposure_and_positive_gamma_likelihood():
    pearson, deviance = poisson_residuals([0, 4], [2, 4])
    np.testing.assert_allclose(pearson, [-np.sqrt(2), 0])
    np.testing.assert_allclose(deviance, [-2, 0])
    pearson, deviance = gamma_residuals([100, 200], [100, 100])
    np.testing.assert_allclose(pearson, [0, 1])
    assert deviance[1] ** 2 == pytest.approx(2 * (1 - np.log(2)))
    with pytest.raises(ValueError):
        gamma_residuals([0], [1])


def test_fisher_leverage_and_diagnostics_are_consistent(fitted):
    p, _, bundle = fitted
    expected = (p.Exposure * bundle.predict(p).frequency).to_numpy()
    _, summary = influence_summary(bundle.transform(p), expected, p.recorded_claim_count.to_numpy(), "poisson")
    assert summary["leverage_sum"] == pytest.approx(summary["parameters_including_intercept"], rel=1e-6)
    assert summary["pearson_dispersion"] > 0


def test_deciles_keep_ties_and_reconcile_exposure(fitted):
    p, _, bundle = fitted
    predictions = bundle.predict(p)
    predictions["pure_premium"] = 100.
    deciles = exposure_deciles(p, predictions)
    assert len(deciles) == 1
    assert deciles.exposure.sum() == pytest.approx(p.Exposure.sum())
    assert deciles.expected_cost.sum() == pytest.approx(100 * p.Exposure.sum())


def test_metrics_and_bootstrap_reproducible_with_policy_clusters(fitted):
    p, c, bundle = fitted
    pp, cp = bundle.predict(p), bundle.predict(c)
    metrics = score_models(p, c, pp, cp)
    glm = metrics.set_index("model").loc["glm"]
    assert glm.pure_premium_AE == pytest.approx(p.recorded_claim_cost.sum() / np.sum(p.Exposure * pp.pure_premium))
    a = bootstrap_calibration(p, pp, 20, 55)
    b = bootstrap_calibration(p, pp, 20, 55)
    pd.testing.assert_frame_equal(a, b)
    assert (a.lower_95 < a.upper_95).all()
