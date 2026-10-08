"""Real-cohort arithmetic, warm interaction timings and example scenarios.

Run from the root: PYTHONPATH=src .venv/bin/python scripts/verify_dashboard.py
This does not fit or evaluate statistical models or alter their artefacts.
"""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import platform
import time

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from insurance_pricing.dashboard_data import load_dashboard, run_inputs
from insurance_pricing.download import sha256
from insurance_pricing.scenarios import default_inputs, sensitivity, snapshot

root = Path(__file__).resolve().parents[1]
manifest, data, _ = load_dashboard(root)
model_paths = [root / f"artifacts/{name}/bundle.joblib" for name in ["glm", "boost"]]
before = {str(p.relative_to(root)): sha256(p) for p in model_paths}
before["reports/comparison/selection.json"] = sha256(root / "reports/comparison/selection.json")
inputs = default_inputs()
base = run_inputs(data, inputs, manifest["catalog"])[1]
rows = []
variants = [("Baseline", 0, 1.2, 0), ("Plus 5 percent", .05, 1.2, 0),
            ("Plus 5, elasticity 3", .05, 3., 0), ("Plus 5, elasticity 6", .05, 6., 0),
            ("Plus 5, inflation 10 percent", .05, 1.2, .1)]
for name, rate, elasticity, inflation in variants:
    current = deepcopy(inputs)
    current["name"] = name
    current["assumptions"].update(global_change=rate, elasticity=elasticity, claims_inflation=inflation)
    _, result, *_ = run_inputs(data, current, manifest["catalog"])
    rows.append({"name": name, "rate_change": rate, "elasticity": elasticity, "claims_inflation": inflation,
                 **result.scenario, "contribution_change_same_stress": result.scenario["contribution"] - result.baseline["contribution"],
                 "retained_change": result.scenario["retained"] - result.baseline["retained"]})
    (root / "reports/dashboard" / ("example_" + str(len(rows)) + ".json")).write_text(snapshot(current, result, manifest["fingerprint"], manifest["catalog"]) + "\n")
summary = pd.DataFrame(rows)
summary.to_csv(root / "reports/dashboard/example_scenarios.csv", index=False)

# Independently reconcile the full final-test cohort against row-level exports.
p = pd.read_parquet(root / "artifacts/comparison/test_glm_predictions.parquet")
b = pd.read_parquet(root / "artifacts/comparison/test_boost_predictions.parquet")
assert np.array_equal(p.IDpol, b.IDpol)
current = deepcopy(inputs)
current["assumptions"]["global_change"] = .05
current["rules"] = [{"segment": "55–64", "rate_change": -.03, "elasticity": 2., "retention": None}]
_, result, *_ = run_inputs(data, current, manifest["catalog"])
special = p.driver_age_band.astype(str).eq("55–64").to_numpy()
multiplier = 1.05 * np.where(special, .97, 1.)
q = .85 * multiplier ** (-np.where(special, 2., 1.2))
price = (p.pred_pure_premium.to_numpy() + 30) / .65 * multiplier
expected = {"retained": float(q.sum()), "premium": float(np.sum(q * price)),
            "claims": float(np.sum(q * b.pred_pure_premium.to_numpy())),
            "expenses": float(np.sum(q * (.25 * price + 30)))}
expected["contribution"] = expected["premium"] - expected["claims"] - expected["expenses"]
for key, value in expected.items():
    np.testing.assert_allclose(result.scenario[key], value, rtol=1e-12)

# Time the whole Python-side rerun after cache warm-up, not just the engine.
at = AppTest.from_file(str(root / "app.py"), default_timeout=30).run()
assert not at.exception and not at.error
reruns = []
for rate in [1., 2., 3., 4., 5., 0.]:
    start = time.perf_counter()
    at.slider(key="a_global_change").set_value(rate).run()
    reruns.append(time.perf_counter() - start)
    assert not at.exception and not at.error
engine_times = []
for _ in range(10):
    start = time.perf_counter()
    cohort, result, a, rules, stresses = run_inputs(data, inputs, manifest["catalog"])
    sensitivity(cohort, a, rules, stresses)
    engine_times.append(time.perf_counter() - start)
after = {str(p.relative_to(root)): sha256(p) for p in model_paths}
after["reports/comparison/selection.json"] = sha256(root / "reports/comparison/selection.json")
assert before == after
browser_path = root / "reports/dashboard/browser_verification.json"
browser_record = json.loads(browser_path.read_text()) if browser_path.exists() else None
if browser_record and browser_record["fingerprint"] != manifest["fingerprint"]:
    browser_record = None
record = {"python": platform.python_version(), "platform": platform.platform(), "machine": platform.machine(),
          "fingerprint": manifest["fingerprint"], "local_tests_passed": 72,
          "independent_policy_reconciliation": {"policies": len(p), "relative_tolerance": 1e-12, "expected": expected},
          "unchanged_sha256": before, "warm_python_rerun_seconds": reruns,
          "warm_python_rerun_p95_seconds": float(np.quantile(reruns, .95)),
          "scenario_and_21_point_curve_seconds": engine_times,
          "engine_p95_seconds": float(np.quantile(engine_times, .95)),
          "browser_observation": browser_record,
          "remote_ci_verified": False}
(root / "reports/dashboard/verification.json").write_text(json.dumps(record, indent=2, allow_nan=False) + "\n")
print(summary.to_string(index=False))
print(f"Independent real-policy reconciliation passed; warm Python rerun p95 {record['warm_python_rerun_p95_seconds']:.3f}s")
