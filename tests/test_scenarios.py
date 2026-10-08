"""Independent commercial arithmetic, exact aggregation and scenario integrity."""
from dataclasses import asdict, replace
import json

import numpy as np
import pandas as pd
import pytest

from insurance_pricing.dashboard_data import select_cohort
from insurance_pricing.scenarios import Assumptions, SegmentRule, Stress, default_inputs, feasible_global_range, load_snapshot, parse_inputs, sensitivity, simulate, snapshot


@pytest.fixture
def cohort():
    return pd.DataFrame({"segment": ["A", "B"], "policies": [2., 3.], "glm_loss": [200., 900.], "boost_loss": [300., 600.]})


def test_two_segment_example_matches_independent_manual_economics(cohort):
    a = Assumptions(global_change=.10, retention=.8, elasticity=2, claims_inflation=.1, variable_expense=.2, fixed_expense=20, margin=.1)
    rules = [SegmentRule("B", -.1, elasticity=1, retention=.6)]
    result = simulate(cohort, a, rules, [Stress("Severity uncertainty", "severity", 1.2)])
    p0 = [(200 + 2 * 20) / .7, (900 + 3 * 20) / .7]
    prices = [p0[0] * 1.1, p0[1] * .99]
    q0 = [.8, .6]
    q1 = [.8 / 1.1**2, .6 / .99]
    losses = [300 * 1.1 * 1.2, 600 * 1.1 * 1.2]
    premium = sum(q * p for q, p in zip(q1, prices))
    claims = sum(q * loss for q, loss in zip(q1, losses))
    expenses = sum(q * (.2 * p + 20 * n) for q, p, n in zip(q1, prices, [2, 3]))
    assert result.scenario["premium"] == pytest.approx(premium)
    assert result.scenario["claims"] == pytest.approx(claims)
    assert result.scenario["expenses"] == pytest.approx(expenses)
    assert result.scenario["contribution"] == pytest.approx(premium - claims - expenses)
    assert result.scenario["retained"] == pytest.approx(2 * q1[0] + 3 * q1[1])
    assert result.scenario["loss_ratio"] == pytest.approx(claims / premium)
    assert result.baseline["claims"] == pytest.approx(sum(q * loss for q, loss in zip(q0, losses)))
    assert result.unstressed_baseline["claims"] == pytest.approx(.8 * 300 + .6 * 600)


def test_zero_change_and_zero_elasticity_identities(cohort):
    a = Assumptions(claims_inflation=.07)
    result = simulate(cohort, a, stresses=[Stress("Frequency stress", "frequency", 1.1)])
    assert result.baseline == result.scenario
    changed = simulate(cohort, replace(a, global_change=.1, elasticity=0))
    assert changed.scenario["retained"] == pytest.approx(changed.baseline["retained"])
    assert changed.scenario["premium"] == pytest.approx(1.1 * changed.baseline["premium"])
    assert changed.scenario["claims"] == pytest.approx(changed.baseline["claims"])


def test_discount_retention_saturates_and_zero_retention_has_undefined_ratios(cohort):
    result = simulate(cohort, Assumptions(global_change=-.2, retention=.95, elasticity=10))
    assert result.scenario["retained"] == 5
    zero = simulate(cohort, Assumptions(retention=0, elasticity=1e300))
    assert zero.scenario["premium"] == zero.scenario["claims"] == zero.scenario["contribution"] == 0
    assert zero.scenario["loss_ratio"] is None
    assert zero.scenario["combined_ratio"] is None


def test_exact_aggregation_matches_independent_policy_weighted_sums():
    losses, anchor, weights = np.array([100., 250., 80., 600.]), np.array([110., 200., 100., 500.]), np.array([1., 3., .5, 2.])
    labels = np.array(["A", "A", "B", "B"])
    p = pd.DataFrame({"segment": labels, "policies": weights, "glm_loss": anchor * weights, "boost_loss": losses * weights})
    aggregate = p.groupby("segment").sum().reset_index()
    a = Assumptions(global_change=.04, elasticity=1.7, claims_inflation=.06)
    result = simulate(aggregate, a, [SegmentRule("B", -.03, elasticity=.8)])
    rate = 1.04 * np.where(labels == "B", .97, 1.)
    q = .85 * rate ** (-np.where(labels == "B", .8, 1.7))
    price = (anchor + 30) / .65 * rate
    np.testing.assert_allclose(result.scenario["premium"], np.sum(weights * q * price))
    np.testing.assert_allclose(result.scenario["claims"], np.sum(weights * q * losses * 1.06))
    np.testing.assert_allclose(result.scenario["expenses"], np.sum(weights * q * (.25 * price + 30)))
    np.testing.assert_allclose(result.scenario["retained"], np.sum(weights * q))


def test_model_switch_preserves_baseline_price_and_retention(cohort):
    a = Assumptions(global_change=.05)
    glm, boost = [simulate(cohort, a, model=m, premium_basis="glm") for m in ["glm", "boost"]]
    assert glm.scenario["premium"] == boost.scenario["premium"]
    assert glm.scenario["retained"] == boost.scenario["retained"]
    assert glm.scenario["claims"] != boost.scenario["claims"]


@pytest.mark.parametrize("changes", [{"variable_expense": .9, "margin": .1}, {"elasticity": -1}, {"retention": 1.1}, {"claims_inflation": -1}, {"global_change": -1}, {"fixed_expense": -1}, {"margin": float("nan")}, {"maximum_change": -.3}, {"elasticity": True}])
def test_invalid_assumptions_are_rejected(cohort, changes):
    with pytest.raises(ValueError): simulate(cohort, replace(Assumptions(), **changes))


def test_duplicate_unknown_rules_and_nonpositive_stresses_fail(cohort):
    for rules in [[SegmentRule("A"), SegmentRule("A")], [SegmentRule("unknown")], [SegmentRule("A", retention=2)]]:
        with pytest.raises(ValueError): simulate(cohort, rules=rules)
    for stresses in [[Stress("stress", multiplier=0)], [Stress("duplicate"), Stress("DUPLICATE")], [Stress("", multiplier=1)], [Stress("wrong", "temperature")]]:
        with pytest.raises(ValueError): simulate(cohort, stresses=stresses)


def test_combined_corridor_is_enforced_not_silently_clipped(cohort):
    with pytest.raises(ValueError, match="corridor"):
        simulate(cohort, Assumptions(global_change=.1), [SegmentRule("A", .1)])
    low, high = feasible_global_range(Assumptions(), [SegmentRule("A", .1)], cohort.segment)
    assert low == pytest.approx(-.2)
    assert high == pytest.approx(1.2 / 1.1 - 1)
    grid = sensitivity(cohort, Assumptions(), [SegmentRule("A", .1)])
    assert len(grid) == 21
    assert grid.global_change.max() == pytest.approx(high)


def test_source_exposure_is_not_a_forecast_weight(cohort):
    one = cohort.assign(exposure=[.01, 100.])
    two = cohort.assign(exposure=[100., .01])
    assert simulate(one).scenario == simulate(two).scenario


def test_snapshot_roundtrip_recomputes_and_rejects_versions(cohort):
    inputs = default_inputs(); inputs["segment_field"] = "driver_age_band"
    catalog = {"driver_age_band": ["A", "B"]}
    result = simulate(cohort)
    value = snapshot(inputs, result, "test-fingerprint", catalog)
    restored = load_snapshot(value, "test-fingerprint", catalog)
    assert restored == inputs
    a, r, s = parse_inputs(restored, catalog)
    assert simulate(cohort, a, r, s).scenario == result.scenario
    obj = json.loads(value); obj["outputs"]["scenario"]["contribution"] = 1e99
    assert load_snapshot(json.dumps(obj), "test-fingerprint", catalog) == inputs
    with pytest.raises(ValueError, match="different source"):
        load_snapshot(value, "other-version", catalog)
    with pytest.raises(ValueError): load_snapshot('{"schema_version":1,"schema_version":2}', "test-fingerprint", catalog)
    with pytest.raises(ValueError): load_snapshot(value.replace('0.85', 'NaN'), "test-fingerprint", catalog)
    with pytest.raises(ValueError): load_snapshot('a' * 1_000_001, "test-fingerprint", catalog)


def test_empty_cohort_and_invalid_weights_are_explicit(cohort):
    for value in [cohort.iloc[:0], cohort.assign(policies=[-1, 3]), cohort.assign(glm_loss=[0, 100])]:
        with pytest.raises(ValueError): simulate(value)
    added = pd.concat([cohort, pd.DataFrame({"segment": ["excluded"], "policies": [0], "glm_loss": [0], "boost_loss": [0]})], ignore_index=True)
    assert simulate(added).scenario == simulate(cohort).scenario


def test_selection_reconciles_splits_filters_and_representative_weights():
    frame = pd.DataFrame({"field": ["Region"] * 3, "split": ["test", "validation", "test"], "segment": ["A", "A", "B"], "policies": [2., 3., 4.]})
    inputs = default_inputs(); inputs.update(segment_field="Region", scope="all", included_segments=["A"])
    assert select_cohort(frame, inputs).policies.sum() == 5
    inputs["included_segments"] = []
    assert select_cohort(frame, inputs).empty
