"""Ranking arithmetic, paired uncertainty, selection locks and exposure weights."""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import mean_tweedie_deviance

from insurance_pricing.boosting import BOOST_FEATURES, new_model, tune_boost
from insurance_pricing.comparison import choose_default, segment_uncertainty, verify_selection
from insurance_pricing.download import sha256
from insurance_pricing.ranking import RankPlan, decile_labels, model_contributions, paired_bootstrap, ranking_metrics, tweedie_contributions


def test_exposure_gini_matches_hand_calculation_and_signed_order():
    perfect = ranking_metrics([1, 2], [1, 8], [1, 4])
    assert perfect["raw_gini"] == pytest.approx(2 / 9)
    assert perfect["normalised_gini"] == pytest.approx(1)
    reverse = ranking_metrics([1, 2], [1, 8], [4, 1])
    assert reverse["raw_gini"] == pytest.approx(-2 / 9)
    assert reverse["normalised_gini"] == pytest.approx(-1)


def test_ties_have_no_ordering_lift_and_undefined_denominators_are_explicit():
    tied = ranking_metrics([1, 2], [1, 8], [10, 10])
    assert tied["raw_gini"] == tied["normalised_gini"] == 0
    assert tied["top_decile_lift"] is None
    assert ranking_metrics([1, 2], [0, 0], [1, 2])["raw_gini"] is None
    assert ranking_metrics([1, 2], [2, 4], [1, 2])["normalised_gini"] is None
    before = RankPlan.create([1, 1, 3]).gini([1, 2, 1], [3, 8, 20])
    after = RankPlan.create([1, 3, 1]).gini([2, 1, 1], [8, 20, 3])
    assert before == pytest.approx(after)


def test_deciles_are_exposure_weighted_and_keep_ties():
    labels = decile_labels(np.ones(100), np.arange(100))
    np.testing.assert_array_equal(np.bincount(labels)[1:], np.full(10, 10))
    assert len(set(decile_labels([1, 2, 3], [10, 10, 10]))) == 1
    for exposure in [[0, 1], [-1, 1], [np.nan, 1]]:
        with pytest.raises(ValueError):
            decile_labels(exposure, [1, 2])


def test_unit_tweedie_contributions_match_library_with_exposure():
    cost, e, pred = np.array([0, 100, 2000]), np.array([.1, .5, 2]), np.array([200, 250, 900])
    assert tweedie_contributions(cost, e, pred).sum() / e.sum() == pytest.approx(mean_tweedie_deviance(cost / e, pred, sample_weight=e, power=1.5))


@pytest.fixture(scope="module")
def booster():
    config = json.loads((Path(__file__).resolve().parents[1] / "configs/boost.json").read_text())
    config["frequency_candidates"] = [{"max_iter": 10, "max_leaf_nodes": 3, "min_samples_leaf": 20}]
    config["severity_candidates"] = [{"max_iter": 10, "max_leaf_nodes": 3, "min_samples_leaf": 10}]
    rng = np.random.default_rng(508)

    def make(n, split, offset):
        p = pd.DataFrame({"IDpol": np.arange(offset, offset + n), "split": split, "Exposure": rng.uniform(.1, 1.5, n)})
        for name, values in [("Area", ["A", "C"]), ("VehBrand", ["B1", "B2"]), ("VehGas", ["Diesel", "Regular"]), ("Region", ["R11", "R24"])]:
            p[name] = rng.choice(values, n)
        p["VehPower"] = rng.integers(4, 12, n)
        p["VehAge"] = rng.integers(0, 30, n)
        p["DrivAge"] = rng.integers(18, 90, n)
        p["BonusMalus"] = rng.integers(50, 150, n)
        p["log_density"] = rng.uniform(1, 10, n)
        p["recorded_claim_count"] = rng.poisson(p.Exposure * .7)
        p["source_claim_count"] = p.recorded_claim_count + rng.binomial(1, .2, n)
        p["claim_count_matches"] = p.recorded_claim_count.eq(p.source_claim_count)
        p["driver_age_band"] = np.where(p.DrivAge < 35, "18–34", "35+")
        p["vehicle_age_band"] = np.where(p.VehAge < 10, "0–9", "10+")
        p["vehicle_power_band"] = p.VehPower.astype(str)
        c = p.loc[p.index.repeat(p.recorded_claim_count)].reset_index(drop=True).copy()
        c["ClaimAmount"] = rng.gamma(2, 1000, len(c))
        p["recorded_claim_cost"] = p.IDpol.map(c.groupby("IDpol").ClaimAmount.sum()).fillna(0)
        return p, c

    p, c = make(600, "train", 1)
    vp, vc = make(300, "validation", 1001)
    bundle, trials = tune_boost(p, c, vp, vc, config)
    return p, c, vp, vc, bundle, trials


def test_boosting_positive_predictions_serialization_and_no_outcome_features(booster, tmp_path):
    p, _, _, _, bundle, trials = booster
    before = bundle.predict(p)
    np.testing.assert_allclose(before.pure_premium, before.frequency * before.severity)
    assert trials.selected.all()
    changed = p.copy()
    changed["Exposure"] = 100
    changed["recorded_claim_cost"] = 1e10
    changed["IDpol"] = 1
    np.testing.assert_array_equal(before.pure_premium, bundle.predict(changed).pure_premium)
    joblib.dump(bundle, tmp_path / "bundle.joblib")
    np.testing.assert_array_equal(before.pure_premium, joblib.load(tmp_path / "bundle.joblib").predict(p).pure_premium)
    assert not set(BOOST_FEATURES) & {"Exposure", "IDpol", "ClaimNb", "ClaimAmount", "recorded_claim_count"}


def test_poisson_boosting_constant_fit_uses_exposure_weights(booster):
    p, _, _, _, bundle, _ = booster
    x = bundle.transform(p)
    model = new_model(bundle.config, {"max_iter": 2, "max_leaf_nodes": 3, "min_samples_leaf": 10000}, "poisson")
    from threadpoolctl import threadpool_limits

    with threadpool_limits(limits=2):
        model.fit(x, p.recorded_claim_count / p.Exposure, sample_weight=p.Exposure)
        prediction = model.predict(x)
    np.testing.assert_allclose(prediction, p.recorded_claim_count.sum() / p.Exposure.sum(), rtol=1e-6)


def test_boosting_test_tuning_and_unknown_category_fail(booster):
    p, c, vp, vc, bundle, _ = booster
    bad = vp.copy()
    bad["split"] = "test"
    with pytest.raises(ValueError, match="validation"):
        tune_boost(p, c, bad, vc, bundle.config)
    bad = vp.copy()
    bad.loc[0, "VehBrand"] = "unseen_brand"
    with pytest.raises(ValueError, match="unknown categories"):
        bundle.predict(bad)


def test_paired_bootstrap_identical_models_has_exactly_zero_differences(booster):
    _, _, p, c, bundle, _ = booster
    pp, cp = bundle.predict(p), bundle.predict(c)
    contributions = model_contributions(p, c, pp, cp)
    result = paired_bootstrap(p, {"glm": pp, "boost": pp}, {"glm": contributions, "boost": contributions}, 20, 50)
    differences = result[result.model.eq("boost_minus_glm")]
    assert differences[["point", "lower_95", "upper_95"]].eq(0).all().all()
    repeated = paired_bootstrap(p, {"glm": pp, "boost": pp}, {"glm": contributions, "boost": contributions}, 20, 50)
    pd.testing.assert_frame_equal(result, repeated)
    assert contributions["severity_deviance"].sum() / len(c) == pytest.approx(2 * np.mean(c.ClaimAmount / cp.severity - 1 - np.log(c.ClaimAmount / cp.severity)))


def test_segment_bootstrap_agrees_for_identical_predictions(booster):
    _, _, p, _, bundle, _ = booster
    pp = bundle.predict(p)
    result = segment_uncertainty(p, {"glm": pp, "boost": pp}, 10, 20)
    a = result[result.model.eq("glm")].drop(columns="model").reset_index(drop=True)
    b = result[result.model.eq("boost")].drop(columns="model").reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b)


def test_promotion_needs_gain_calibration_and_paired_evidence():
    metrics = pd.DataFrame({"model": ["glm", "boost"], "pure_deviance": [100, 95], "pure_premium_AE": [1, 1.05]})
    intervals = pd.DataFrame({"model": ["boost_minus_glm"], "metric": ["pure_deviance"], "upper_95": [-1]})
    gate = {"minimum_relative_pure_deviance_gain": .01, "minimum_AE": .8, "maximum_AE": 1.25, "require_paired_deviance_upper_95_below_zero": True}
    assert choose_default(metrics, intervals, gate)["default_model"] == "boost"
    intervals.loc[0, "upper_95"] = 1
    assert choose_default(metrics, intervals, gate)["default_model"] == "glm"
    intervals.loc[0, "upper_95"] = -1
    metrics.loc[1, "pure_premium_AE"] = 1.5
    assert choose_default(metrics, intervals, gate)["default_model"] == "glm"


def test_selection_guard_rejects_any_test_informed_selection(tmp_path):
    with pytest.raises(ValueError, match="without final test"):
        verify_selection(tmp_path, {"selection_population": "test", "test_read_during_selection": True})


def test_selection_guard_detects_config_tampering_before_evaluation(tmp_path):
    files = ["configs/boost.json", "configs/data.json", "artifacts/boost/bundle.joblib", "artifacts/glm/bundle.joblib"]
    for name in files:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"frozen test fixture")
    selection = {"selection_population": "validation", "test_read_during_selection": False,
                 "config_sha256": sha256(tmp_path / files[0]), "data_config_sha256": sha256(tmp_path / files[1]),
                 "boost_sha256": sha256(tmp_path / files[2]), "glm_sha256": sha256(tmp_path / files[3]),
                 "processed_hashes": {}, "code_sha256": {}, "versions": {}}
    verify_selection(tmp_path, selection)
    (tmp_path / files[0]).write_bytes(b"changed after selection")
    with pytest.raises(ValueError, match="checksum changed"):
        verify_selection(tmp_path, selection)


def test_gini_matches_independent_pairwise_definition_with_ties():
    e = np.array([.01, 1, 2, .3])
    cost = np.array([0, 30, 100, 1])
    score = np.array([5, 2, 5, 1])
    pairwise = np.sum(e[:, None] * cost[None, :] * np.sign(score[None, :] - score[:, None])) / (e.sum() * cost.sum())
    assert ranking_metrics(e, cost, score)["raw_gini"] == pytest.approx(pairwise)
