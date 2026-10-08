"""Check committed handover evidence and a clean no-model dashboard tree.

Run with PYTHONPATH=src and requirements-report.txt. Does not train, download,
change selection, or overwrite earlier-stage reports. Runtime observations are
written only to reports/handover/verification.json.
"""
import argparse
import hashlib
from importlib.metadata import version
import json
import math
from pathlib import Path
import platform
import shutil
import tempfile

import pandas as pd
from pypdf import PdfReader
from streamlit.testing.v1 import AppTest

from insurance_pricing.dashboard_data import load_dashboard, load_risk_models, run_inputs
from insurance_pricing.scenarios import load_snapshot
from package_client import client_files

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(aggregate_only=False):
    manifest, data, _ = load_dashboard(ROOT)
    brief = json.loads((ROOT / "reports/handover/brief_manifest.json").read_text())
    for name, expected in brief["sources_sha256"].items():
        assert digest(ROOT / name) == expected, f"PDF source changed: {name}"
    assert digest(ROOT / "scripts/build_manager_brief.py") == brief["script_sha256"]
    assert digest(ROOT / brief["pdf"]) == brief["pdf_sha256"]
    pdf = PdfReader(ROOT / brief["pdf"])
    assert len(pdf.pages) == 2
    content = [p.extract_text() for p in pdf.pages]
    assert all(float(p.mediabox.width) > 590 and float(p.mediabox.height) > 840 for p in pdf.pages)
    for phrase in ["1.02m", "6,537", "0.30m", "114,959", "108,422", "6.28", "4.97"]:
        assert phrase in content[0], f"Missing manager decision evidence: {phrase}"
    for phrase in ["3.24%", "76.35", "73.88", "0.359", "0.423", "9,116", "regulatory approval"]:
        assert phrase in content[1], f"Missing manager model evidence: {phrase}"
    links = [a.get_object().get("/A", {}).get("/URI") for p in pdf.pages for a in p.get("/Annots", [])]
    assert "https://github.com/TanmaySomani/Insurance-pricing-calculator" in links
    examples = pd.read_csv(ROOT / "reports/dashboard/example_scenarios.csv")
    for i, row in examples.iterrows():
        inputs = load_snapshot((ROOT / f"reports/dashboard/example_{i + 1}.json").read_bytes(), manifest["fingerprint"], manifest["catalog"])
        result = run_inputs(data, inputs, manifest["catalog"])[1]
        assert row["name"] == inputs["name"]
        for name in ["retained", "premium", "claims", "expenses", "contribution", "loss_ratio", "combined_ratio", "retention"]:
            assert math.isclose(result.scenario[name], row[name], rel_tol=1e-10, abs_tol=1e-8), (row["name"], name)
        assert math.isclose(result.scenario["contribution"] - result.baseline["contribution"], row.contribution_change_same_stress, abs_tol=1e-8)
    routes = ["Rate scenarios", "Portfolio", "Model comparison", "Segment diagnostics", "Risk calculator", "Saved scenarios"]
    with tempfile.TemporaryDirectory(prefix="insurance-client-") as temporary:
        clean = Path(temporary)
        for source in client_files(ROOT):
            target = clean / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source, target)
        assert not (clean / "data").exists() and not (clean / "artifacts").exists()
        at = AppTest.from_file(str(clean / "app.py"), default_timeout=30).run()
        assert not at.exception and not at.error
        baseline = at.metric[0].value
        at.slider(key="a_global_change").set_value(5.0).run()
        assert not at.exception and not at.error and at.metric[0].value != baseline
        assert at.metric[0].value == "6.28m" and at.metric[1].value == "108,422"
        for route in routes[1:]:
            at.radio(key="page").set_value(route).run()
            assert not at.exception and not at.error, route
            if route == "Risk calculator":
                assert any("bundles" in info.value.lower() for info in at.info)
    model_record = "Not required for aggregate-only verification"
    needed = [ROOT / f"artifacts/{model}/bundle.joblib" for model in ["glm", "boost"]]
    if not aggregate_only and all(p.exists() for p in needed):
        before = {str(p.relative_to(ROOT)): digest(p) for p in needed}
        load_risk_models(ROOT)  # Exact runtime/data/config/code/bundle identity check.
        assert before == {str(p.relative_to(ROOT)): digest(p) for p in needed}
        model_record = {"trusted_local_models_verified": True, "unchanged_sha256": before}
    record = {"python": platform.python_version(), "platform": platform.platform(),
              "fingerprint": manifest["fingerprint"], "pdf_pages": len(pdf.pages),
              "pdf_sources_and_values_verified": True, "pdf_link_verified": True,
              "example_scenarios_recomputed": len(examples), "aggregate_only_pages_verified": routes,
              "aggregate_only_live_edit_verified": True, "aggregate_only_risk_setup_state_verified": True,
              "models": model_record, "reportlab_version": version("reportlab"), "pypdf_version": version("pypdf"),
              "scope": "Local checks. PDF visual review and remote CI status are recorded separately."}
    (ROOT / "reports/handover/verification.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aggregate-only", action="store_true", help="Skip optional local model loading")
    verify(parser.parse_args().aggregate_only)
