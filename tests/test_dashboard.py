"""Real aggregate evidence and manager interactions; no refitting in tests."""
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from insurance_pricing.dashboard_data import load_dashboard, risk_frame, run_inputs
from insurance_pricing.scenarios import default_inputs

ROOT = Path(__file__).resolve().parents[1]


def app():
    result = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
    assert not result.exception
    assert not result.error
    return result


def test_dashboard_aggregates_reconcile_each_dimension_and_test_metrics():
    manifest, data, tables = load_dashboard(ROOT)
    for field in manifest["catalog"]:
        selected = data[data.field.eq(field) & data.split.eq("test")]
        assert selected.policies.sum() == 135246
        assert selected.recorded_claims.sum() == 5270
        metric = tables["metrics"].query("split == 'test' and model == 'boost'").iloc[0]
        assert selected.boost_historical_expected.sum() / selected.exposure.sum() == pytest.approx(metric.expected_per_year_eur)
    a, b = [dict(default_inputs(), segment_field=f) for f in ["driver_age_band", "Region"]]
    first = run_inputs(data, a, manifest["catalog"])[1]
    second = run_inputs(data, b, manifest["catalog"])[1]
    assert first.scenario["contribution"] == pytest.approx(second.scenario["contribution"])


def test_live_rate_change_and_model_switch_preserve_price_anchor():
    at = app()
    baseline = at.metric[0].value
    at.slider(key="a_global_change").set_value(5.0).run()
    assert not at.exception and at.metric[0].value != baseline
    assert at.session_state["inputs"]["assumptions"]["global_change"] == .05
    price, volume = at.metric[2].value, at.metric[1].value
    at.selectbox(key="model").set_value("glm").run()
    assert not at.exception and at.metric[2].value == price and at.metric[1].value == volume


def test_add_edit_segment_and_reset_on_field_change():
    at = app()
    at.button[0].click().run()  # Add segment button, independently of canvas editing.
    revision = at.session_state["editor_revision"]
    at.session_state[f"rules_editor_{revision}"] = {"edited_rows": {0: {"rate_percent": 5.0, "elasticity": 2.0}}, "added_rows": [], "deleted_rows": []}
    at.run()
    assert not at.exception and not at.error
    assert at.session_state["inputs"]["rules"][0]["rate_change"] == .05
    at.selectbox(key="segment_field").set_value("Region").run()
    assert not at.exception and at.session_state["inputs"]["rules"] == []
    at.button[0].click().run()
    assert not at.exception and at.session_state["inputs"]["rules"][0]["segment"].startswith("R")


def test_custom_stress_addition_changes_claims_and_is_saved():
    at = app()
    before = at.metric[0].value
    revision = at.session_state["editor_revision"]
    at.session_state[f"stresses_editor_{revision}"] = {"edited_rows": {}, "added_rows": [{"name": "Claims uncertainty", "component": "severity", "multiplier": 1.1}], "deleted_rows": []}
    at.run()
    assert not at.exception and not at.error
    assert at.metric[0].value != before
    assert at.session_state["inputs"]["stresses"][0]["multiplier"] == 1.1
    at.button[0].click().run()  # Adding a segment must retain stress edits.
    assert at.session_state["inputs"]["stresses"][0]["multiplier"] == 1.1


def test_invalid_economics_and_empty_filter_show_usable_states():
    at = app()
    at.number_input(key="a_variable_expense").set_value(95.0).run()
    assert not at.exception and at.error and len(at.metric) == 0
    at.number_input(key="a_variable_expense").set_value(25.0).run()
    at.multiselect(key="included_segments").set_value([]).run()
    assert not at.exception and len(at.metric) == 0
    assert any("at least one segment" in info.value for info in at.info)


def test_saved_scenario_restore_and_all_pages_render():
    at = app()
    at.slider(key="a_global_change").set_value(5.0).run()
    at.text_input(key="scenario_name").set_value("Five percent review").run()
    save = next(b for b in at.button if b.label == "Save to comparison")
    save.click().run()
    assert "Five percent review" in at.session_state["saved"]
    for route in ["Portfolio", "Model comparison", "Segment diagnostics", "Risk calculator", "Saved scenarios"]:
        at.radio(key="page").set_value(route).run()
        assert not at.exception and not at.error
    next(b for b in at.button if b.label == "Restore to rate page").click().run()
    assert not at.exception and at.slider(key="a_global_change").value == 5


def test_risk_schema_rejects_unknowns_outcomes_and_extrapolation():
    import json
    spec = json.loads((ROOT / "reports/dashboard/risk_spec.json").read_text())
    values = {"DrivAge": 40, "VehAge": 5, "VehPower": 6, "BonusMalus": 50, "Density": 1000, "Area": "C", "Region": "R24", "VehBrand": "B1", "VehGas": "Diesel"}
    assert risk_frame(values, spec).driver_age_band.iloc[0] == "35–44"
    for changed in [dict(values, IDpol=1), dict(values, DrivAge=200), dict(values, VehBrand="unknown")]:
        with pytest.raises(ValueError): risk_frame(changed, spec)
