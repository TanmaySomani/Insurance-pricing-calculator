"""Financial integrity, target separation, and policy holdout regression checks."""

import json

import numpy as np
import pandas as pd
import pytest

from insurance_pricing.data import MODEL_FEATURES, assign_split, audit_sources, build_tables, engineer_features
from insurance_pricing.download import SOURCES, download, sha256

CONFIG = {"split_seed": 20261008, "train_bucket_end": 6000, "validation_bucket_end": 8000, "split_bucket_count": 10000}


@pytest.fixture
def sources():
    frequency = pd.DataFrame({
        "IDpol": [1., 2., 3., 4.], "ClaimNb": [2, 1, 0, 1], "Exposure": [.5, 1., 2.01, .1],
        "Area": ["'A'", "B", "C", "D"], "VehPower": [4, 5, 12, 15], "VehAge": [0, 5, 21, 100],
        "DrivAge": [18, 24, 25, 100], "BonusMalus": [50, 60, 100, 230],
        "VehBrand": ["B1"] * 4, "VehGas": ["Diesel"] * 4,
        "Density": [1., 20., 100., 27000.], "Region": ["R11"] * 4,
    })
    # Policy 2 has a positive original count without costs. Policy 999 is orphaned.
    severity = pd.DataFrame({"IDpol": [1., 1., 4., 999.], "ClaimAmount": [100., 300., 200., 500.]})
    return frequency, severity


def test_costs_and_counts_reconcile_without_multiplying_policies(sources):
    policies, claims = build_tables(*sources, CONFIG)
    assert len(policies) == 4 and len(claims) == 3
    assert policies.recorded_claim_cost.sum() == claims.ClaimAmount.sum() == 600
    assert policies.recorded_claim_count.sum() == len(claims)
    first = policies.set_index("IDpol").loc[1]
    assert first.recorded_claim_count == 2 and first.recorded_claim_cost == 400
    assert first.recorded_frequency == 4 and first.recorded_loss_cost == 800


def test_missing_cost_remains_flagged_and_original_count_is_preserved(sources):
    policies, claims = build_tables(*sources, CONFIG)
    row = policies.set_index("IDpol").loc[2]
    assert row.source_claim_count == row.ClaimNb == 1
    assert row.recorded_claim_count == row.recorded_claim_cost == 0
    assert row.positive_source_count_no_cost and not row.claim_count_matches
    audit = audit_sources(*sources, policies, claims)
    assert audit["unmatched_severity_records"] == 1
    assert audit["unmatched_severity_cost_eur"] == 500


def test_partial_cost_count_is_flagged(sources):
    frequency, severity = sources
    frequency.loc[3, "ClaimNb"] = 2
    policies, _ = build_tables(frequency, severity, CONFIG)
    row = policies.set_index("IDpol").loc[4]
    assert not row.claim_count_matches and not row.positive_source_count_no_cost
    assert row.source_claim_count == 2 and row.recorded_claim_count == 1


def test_exposure_is_not_capped(sources):
    policies, _ = build_tables(*sources, CONFIG)
    assert policies.set_index("IDpol").loc[3, "Exposure"] == 2.01


def test_claims_inherit_policy_split(sources):
    policies, claims = build_tables(*sources, CONFIG)
    expected = claims.IDpol.map(policies.set_index("IDpol").split)
    assert (claims.split == expected).all()


def test_split_is_stable_under_row_order_and_new_rows():
    ids = pd.Series(range(1, 10001))
    initial = pd.Series(assign_split(ids, CONFIG), index=ids)
    reordered = pd.Series(assign_split(ids.iloc[::-1], CONFIG), index=ids.iloc[::-1])
    pd.testing.assert_series_equal(initial, reordered.sort_index())
    assert initial.value_counts(normalize=True)["train"] == pytest.approx(.6, abs=.02)
    assert assign_split(pd.Series([1, 2]), CONFIG).tolist() == initial.loc[[1, 2]].tolist()
    assert initial.loc[[1, 2, 3, 4]].tolist() == ["train", "train", "validation", "train"]


def test_feature_boundaries_and_no_target_columns(sources):
    output = engineer_features(sources[0])
    assert output.driver_age_band.astype(str).tolist() == ["18–24", "18–24", "25–34", "75+"]
    assert output.vehicle_power_band.tolist() == ["4", "5", "12", "12"]
    assert output.vehicle_age_band.astype(str).tolist() == ["New", "1–5", "21+", "21+"]
    assert output.log_density.iloc[0] == pytest.approx(np.log(2))
    assert not set(MODEL_FEATURES) & {"IDpol", "Exposure", "ClaimNb", "ClaimAmount", "source_claim_count", "recorded_claim_cost", "split"}


@pytest.mark.parametrize("column,value", [("Exposure", 0), ("Exposure", -1), ("ClaimNb", -1), ("ClaimNb", 1.5), ("Density", np.inf), ("DrivAge", 17), ("IDpol", 1.5), ("VehGas", ""), ("VehAge", np.nan)])
def test_invalid_inputs_fail_instead_of_silently_changing_risk(sources, column, value):
    frequency, severity = sources
    # Explicit float conversion avoids pandas integer-assignment errors in this fixture.
    if pd.api.types.is_numeric_dtype(frequency[column]):
        frequency[column] = frequency[column].astype(float)
    frequency.loc[0, column] = value
    with pytest.raises(ValueError):
        build_tables(frequency, severity, CONFIG)


def test_duplicate_policy_id_fails(sources):
    frequency, severity = sources
    frequency.loc[1, "IDpol"] = 1
    with pytest.raises(ValueError, match="duplicate"):
        build_tables(frequency, severity, CONFIG)


@pytest.mark.parametrize("amount", [0, -1, np.inf, np.nan])
def test_nonpositive_or_invalid_gamma_target_fails(sources, amount):
    frequency, severity = sources
    severity.loc[0, "ClaimAmount"] = amount
    with pytest.raises(ValueError):
        build_tables(frequency, severity, CONFIG)


def test_cached_source_checksum_mismatch_fails_before_reading_data(tmp_path):
    raw = tmp_path / "data/raw"
    raw.mkdir(parents=True)
    configs = tmp_path / "configs"
    configs.mkdir()
    dataset_id, name = SOURCES["frequency"]
    path = raw / f"{name}.parquet"
    path.write_bytes(b"original snapshot")
    digest = sha256(path)
    path.write_bytes(b"corrupted snapshot")
    (raw / f"{name}.metadata.json").write_text(json.dumps({"name": name, "version": "1"}))
    (configs / "source_lock.json").write_text(json.dumps({"frequency": {"sha256": digest}}))
    with pytest.raises(ValueError, match="checksum mismatch"):
        download(tmp_path)
