"""A live pricing workspace; no fitting, downloads or policy disclosures in UI."""

from dataclasses import asdict
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from insurance_pricing.dashboard_data import SEGMENT_FIELDS, load_dashboard, load_risk_models, risk_frame, run_inputs
from insurance_pricing.scenarios import default_inputs, load_snapshot, sensitivity, simulate, snapshot

GREEN, BLUE, ORANGE = "#346538", "#1F6C9F", "#A56B43"


@st.cache_data(show_spinner="Loading verified portfolio evidence…")
def cached_data(root, token):
    return load_dashboard(Path(root))


@st.cache_resource(show_spinner="Loading frozen risk models…")
def cached_models(root, token):
    return load_risk_models(Path(root))


def money(value):
    return f"EUR {value / 1e6:,.2f}m" if abs(value) >= 1e6 else f"EUR {value:,.0f}"


def percent(value):
    return "—" if value is None or pd.isna(value) else f"{value:.1%}"


def chart(fig):
    fig.update_layout(template="plotly_white", paper_bgcolor="#FBFBFA", plot_bgcolor="#FBFBFA",
                      font={"family": "Helvetica Neue, Arial, sans-serif", "color": "#2F3437", "size": 13},
                      margin={"l": 15, "r": 15, "t": 30, "b": 15}, height=370,
                      legend={"orientation": "h", "y": 1.14, "x": 0})
    fig.update_xaxes(gridcolor="#EAEAEA")
    fig.update_yaxes(gridcolor="#EAEAEA")
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False})


def table(frame):
    st.dataframe(frame, hide_index=True, width="stretch")


def style():
    st.markdown("""<style>
    html, body, [data-testid="stApp"] {font-family:'Helvetica Neue',Arial,sans-serif;}
    .block-container {max-width:1400px;padding-top:4rem;padding-bottom:3rem;}
    h1 {font-family:Georgia,serif!important;font-size:2.8rem!important;font-weight:400!important;letter-spacing:-.035em;}
    h2 {font-size:1.35rem!important;letter-spacing:-.015em;}
    [data-testid="stSidebar"] {border-right:1px solid #EAEAEA;}
    [data-testid="stMetric"] {background:#fff;border:1px solid #EAEAEA;border-radius:8px;padding:18px;}
    [data-testid="stMetricValue"] {font-size:1.7rem;}
    [data-testid="stMetricDelta"] {font-size:.85rem;}
    .eyebrow {font-size:.72rem;letter-spacing:.16em;color:#787774;margin-bottom:.4rem;}
    .note {background:#EDF3EC;border:1px solid #EAEAEA;border-radius:8px;padding:18px 22px;line-height:1.6;}
    .stButton button[kind="primary"] {background:#2F3437;border-color:#2F3437;color:white;box-shadow:none;border-radius:5px;}
    [data-testid="stExpander"] {border:1px solid #EAEAEA;border-radius:8px;}
    </style>""", unsafe_allow_html=True)


def initialise_controls(inputs):
    for key in ["model", "premium_basis", "scope", "segment_field", "baseline_mode"]:
        st.session_state[key] = inputs[key]
    for key, value in inputs["assumptions"].items():
        st.session_state[f"a_{key}"] = float(value) * (100 if key in {"global_change", "retention", "claims_inflation", "variable_expense", "margin", "minimum_change", "maximum_change"} else 1)
    st.session_state["scenario_name"] = inputs["name"]
    st.session_state["included_segments"] = inputs["included_segments"]
    st.session_state["rule_field"] = inputs["segment_field"]
    st.session_state["rule_seed"] = rule_table(inputs["rules"])
    st.session_state["last_rules"] = inputs["rules"]
    st.session_state["stress_seed"] = stress_table(inputs["stresses"])
    st.session_state["editor_revision"] = st.session_state.get("editor_revision", 0) + 1


def rule_table(rules):
    return pd.DataFrame([{ "segment": r["segment"], "rate_percent": r["rate_change"] * 100,
                         "elasticity": r.get("elasticity"), "retention_percent": None if r.get("retention") is None else r["retention"] * 100} for r in rules],
                        columns=["segment", "rate_percent", "elasticity", "retention_percent"]).astype({"segment": "str", "rate_percent": "float64", "elasticity": "float64", "retention_percent": "float64"})


def stress_table(stresses):
    return pd.DataFrame(stresses, columns=["name", "component", "multiplier"]).astype({"name": "str", "component": "str", "multiplier": "float64"})


def rules_from_table(frame):
    rules = []
    for r in frame.to_dict("records"):
        if pd.isna(r["segment"]) or pd.isna(r["rate_percent"]):
            raise ValueError("Complete the segment and rate change in each row, or delete the unfinished row")
        rules.append({"segment": str(r["segment"]), "rate_change": float(r["rate_percent"]) / 100,
                      "elasticity": None if pd.isna(r["elasticity"]) else float(r["elasticity"]),
                      "retention": None if pd.isna(r["retention_percent"]) else float(r["retention_percent"]) / 100})
    return rules


def controls(inputs, manifest):
    current = json.loads(json.dumps(inputs))
    c = st.columns([1, 1, 1, 1.2])
    current["model"] = c[0].selectbox("Claims model", ["boost", "glm"], format_func=lambda v: "Boosting" if v == "boost" else "GLM", key="model")
    current["premium_basis"] = c[1].selectbox("Baseline price anchor", ["glm", "boost"], format_func=lambda v: v.upper(), key="premium_basis", help="Keep this fixed to compare models at identical assumed premiums.")
    current["scope"] = c[2].selectbox("Annual renewal cohort", ["test", "validation", "all", "train"], format_func=lambda v: {"test": "Final test", "validation": "Validation", "all": "Full snapshot", "train": "Training"}[v], key="scope")
    current["segment_field"] = c[3].selectbox("Segment by", list(SEGMENT_FIELDS), format_func=SEGMENT_FIELDS.get, key="segment_field")
    field = current["segment_field"]
    if st.session_state["rule_field"] != field:
        st.session_state["rule_field"] = field
        st.session_state["rule_seed"] = rule_table([])
        st.session_state["last_rules"] = []
        st.session_state["included_segments"] = None
        st.session_state["editor_revision"] += 1
        st.info("Segmentation changed. Segment rules and the cohort filter were reset.")
    levels = manifest["catalog"][field]
    if st.session_state["included_segments"] is None:
        st.session_state["included_segments"] = levels.copy()
    a = current["assumptions"]
    st.subheader("Price and customer response")
    c = st.columns([2, 1, 1])
    rate_now = st.session_state["a_global_change"]
    a["global_change"] = c[0].slider("Global rate change (%)", min_value=float(min(-20, rate_now)), max_value=float(max(20, rate_now)), step=1.0, key="a_global_change") / 100
    a["retention"] = c[1].number_input("Baseline retention (%) · assumed", min_value=0.0, max_value=100.0, step=1.0, key="a_retention") / 100
    a["elasticity"] = c[2].number_input("Price elasticity · assumed", min_value=0.0, step=0.1, key="a_elasticity", help="Retention = baseline retention × price multiplier to the power −elasticity, bounded at 100%.")
    with st.expander("Claims, expenses and the rate corridor", expanded=False):
        c = st.columns(4)
        a["claims_inflation"] = c[0].number_input("Claims inflation (%)", min_value=-99.0, step=1.0, key="a_claims_inflation") / 100
        a["variable_expense"] = c[1].number_input("Variable expense (%)", min_value=0.0, max_value=99.0, step=1.0, key="a_variable_expense") / 100
        a["fixed_expense"] = c[2].number_input("Fixed expense / retained policy (EUR)", min_value=0.0, step=5.0, key="a_fixed_expense")
        a["margin"] = c[3].number_input("Baseline price margin (%)", min_value=0.0, max_value=99.0, step=1.0, key="a_margin") / 100
        c = st.columns(3)
        a["minimum_change"] = c[0].number_input("Minimum combined rate change (%)", min_value=-99.0, step=1.0, key="a_minimum_change") / 100
        a["maximum_change"] = c[1].number_input("Maximum combined rate change (%)", min_value=-99.0, step=1.0, key="a_maximum_change") / 100
        current["baseline_mode"] = c[2].selectbox("Compare with", ["same_stress", "unstressed"], format_func=lambda x: "Baseline with same claims stress" if x == "same_stress" else "Unstressed baseline (includes stress effect)", key="baseline_mode")
        st.caption("All values above are assumptions. Baseline price = (anchor model loss + fixed expense) / (1 − variable expense − margin).")
    revision = st.session_state["editor_revision"]
    with st.expander("Segment adjustments · add or edit rows", expanded=False):
        st.caption("Global and segment changes multiply. Blank elasticity/retention cells inherit global assumptions. One rule per level; the combined change must stay inside the corridor.")
        c = st.columns([3, 1])
        new_level = c[0].selectbox("Segment to add", levels, key=f"new_level_{field}")
        if c[1].button("Add segment", width="stretch"):
            existing = st.session_state.get("last_rules", current["rules"])
            if any(r["segment"] == new_level for r in existing):
                st.warning("This segment already has a rule. Edit its row below.")
            else:
                st.session_state["rule_seed"] = rule_table(existing + [{"segment": new_level, "rate_change": 0, "elasticity": None, "retention": None}])
                st.session_state["stress_seed"] = stress_table(st.session_state["inputs"]["stresses"])
                st.session_state["editor_revision"] += 1
                st.rerun()
        edited = st.data_editor(st.session_state["rule_seed"], num_rows="dynamic", hide_index=True, width="stretch", key=f"rules_editor_{revision}",
                               column_config={"segment": st.column_config.SelectboxColumn("Segment", options=levels, required=True),
                                              "rate_percent": st.column_config.NumberColumn("Extra rate change (%)", default=0.0, required=True, min_value=-99.0, step=1.0),
                                              "elasticity": st.column_config.NumberColumn("Elasticity override", min_value=0.0, step=0.1),
                                              "retention_percent": st.column_config.NumberColumn("Retention override (%)", min_value=0.0, max_value=100.0, step=1.0)})
        current["rules"] = rules_from_table(edited)
        st.session_state["last_rules"] = current["rules"]
    with st.expander("Custom stress assumptions · add parameters", expanded=False):
        st.caption("Add a named frequency, severity or total-loss multiplier. All rows multiply the selected claims estimate, in both baseline and scenario. These are scenario assumptions, not learned rating effects.")
        edited = st.data_editor(st.session_state["stress_seed"], num_rows="dynamic", hide_index=True, width="stretch", key=f"stresses_editor_{revision}",
                               column_config={"name": st.column_config.TextColumn("Assumption name", required=True, max_chars=80),
                                              "component": st.column_config.SelectboxColumn("Affects", options=["frequency", "severity", "loss"], default="loss", required=True),
                                              "multiplier": st.column_config.NumberColumn("Multiplier", min_value=0.01, step=0.05, default=1.0, required=True)})
        current["stresses"] = edited.to_dict("records")
    with st.expander("Cohort filter", expanded=False):
        current["included_segments"] = st.multiselect("Included segments", levels, key="included_segments")
        st.caption("An empty selection shows a usable empty state. Saved rules for excluded levels remain inactive.")
    return current


def kpis(result, baseline_mode):
    b = result.baseline if baseline_mode == "same_stress" else result.unstressed_baseline
    s = result.scenario
    c = st.columns(4)
    def compact(value):
        return f"{value / 1e6:,.2f}m" if abs(value) >= 1e6 else (f"{value / 1e3:,.1f}k" if abs(value) >= 1e3 else f"{value:,.0f}")
    c[0].metric("Contribution · EUR", compact(s["contribution"]), f"{compact(s['contribution'] - b['contribution'])} vs baseline", help="Expected underwriting contribution after the specified expenses.")
    c[1].metric("Retained policies", f"{s['retained']:,.0f}", f"{s['retained'] - b['retained']:+,.0f} policies")
    c[2].metric("Annual premium · EUR", compact(s["premium"]), f"{compact(s['premium'] - b['premium'])} vs baseline")
    c[3].metric("Scenario loss ratio", percent(s["loss_ratio"]), None if s["loss_ratio"] is None or b["loss_ratio"] is None else f"{(s['loss_ratio'] - b['loss_ratio']) * 100:+.1f} pp", delta_color="inverse")
    st.caption(f"Retention {percent(s['retention'])} · Expected claims {money(s['claims'])} · Expenses {money(s['expenses'])} · Combined ratio {percent(s['combined_ratio'])}. Expected underwriting contribution excludes capital, reinsurance, tax and investment income.")


def recommendation(result, curve, inputs):
    b = result.baseline if inputs["baseline_mode"] == "same_stress" else result.unstressed_baseline
    delta, volume = result.scenario["contribution"] - b["contribution"], result.scenario["retained"] - b["retained"]
    if np.isclose(delta, 0) and np.isclose(volume, 0):
        text = "Start from this baseline, then compare a modest rate move with a higher-elasticity case. No rate effect has been introduced yet."
    elif delta > 0:
        text = f"This assumption set increases expected contribution by {money(delta)} while changing retained volume by {volume:+,.0f} policies. Treat it as a candidate for investigation; test stronger price response and claims stress before proposing a change."
    else:
        text = f"This assumption set reduces expected contribution by {money(-delta)} while changing retained volume by {volume:+,.0f} policies. Reconsider the move or identify a credible volume objective before proceeding."
    st.info(text + " These are simulated outcomes, not achieved savings or a proven optimal rate.")


def scenario_page(inputs, data, manifest):
    st.title("What does a rate change really earn?")
    st.caption("A one-year renewal experiment in historical EUR. Prices and customer response are assumed; claims are modelled from linked recorded costs.")
    try:
        current = controls(inputs, manifest)
        if current["included_segments"] == []:
            st.info("Select at least one segment to calculate a scenario.")
            return
        start = time.perf_counter()
        cohort, result, assumptions, rules, stresses = run_inputs(data, current, manifest["catalog"])
        curve = sensitivity(cohort, assumptions, rules, stresses, current["model"], current["premium_basis"])
        elapsed = time.perf_counter() - start
    except (ValueError, TypeError) as exc:
        st.error(str(exc))
        st.caption("Correct the inputs above. Invalid assumptions do not update or save results.")
        return
    st.session_state["inputs"] = current
    st.divider()
    st.subheader("Scenario outcome")
    kpis(result, current["baseline_mode"])
    recommendation(result, curve, current)
    c = st.columns([1.5, 1])
    with c[0]:
        st.subheader("Contribution and retention sensitivity")
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Scatter(x=curve.global_change * 100, y=curve.contribution, name="Contribution (EUR)", line={"color": GREEN}), secondary_y=False)
        fig.add_trace(go.Scatter(x=curve.global_change * 100, y=curve.retention * 100, name="Retention (%)", line={"color": ORANGE, "dash": "dot"}), secondary_y=True)
        fig.add_vline(x=assumptions.global_change * 100, line_color="#787774", line_dash="dash")
        fig.update_xaxes(title="Global rate change (%) · segment rules held fixed")
        fig.update_yaxes(title="Expected contribution (EUR)", secondary_y=False)
        fig.update_yaxes(title="Retention (%)", secondary_y=True)
        chart(fig)
        st.caption("Curve respects the combined rate corridor. Its maximum is conditional on assumed elasticity and costs.")
    with c[1]:
        st.subheader("Baseline vs scenario")
        b = result.baseline if current["baseline_mode"] == "same_stress" else result.unstressed_baseline
        table(pd.DataFrame([{"Measure": key.replace("_", " ").title(), "Baseline": percent(b[key]) if key in {"retention", "loss_ratio", "combined_ratio"} else (f"{b[key]:,.0f}" if key == "retained" else money(b[key])),
                             "Scenario": percent(result.scenario[key]) if key in {"retention", "loss_ratio", "combined_ratio"} else (f"{result.scenario[key]:,.0f}" if key == "retained" else money(result.scenario[key]))} for key in b]))
        st.caption("Baseline uses the same claims stress." if current["baseline_mode"] == "same_stress" else "Unstressed baseline: differences include both rates and claims stress.")
    st.subheader("Segment effects and evidence")
    output = result.segments.copy()
    display = pd.DataFrame({"Segment": output.segment, "Renewal policies": output.policies.round().astype(int), "Combined rate": output.combined_change.map(percent),
                            "Retention": output.scenario_retention.map(percent), "Contribution EUR": output.scenario_contribution.round(),
                            "Scenario loss ratio": output.scenario_loss_ratio.map(percent), "Recorded claims": output.recorded_claims.astype(int),
                            "Cost-table coverage": (output.recorded_claims / output.source_claims.replace(0, np.nan)).map(percent),
                            "Volume screen": np.where(output.recorded_claims < 100, "<100 claims: review", "100+ claims")})
    table(display)
    st.caption(f"{cohort.policies.sum():,.0f} annual renewal opportunities. Historical exposure is used only on diagnostic pages. Scenario and 21-point curve arithmetic: {elapsed * 1000:.0f} ms; browser update timing is measured separately.")
    st.subheader("Keep this scenario")
    c = st.columns([2, 1, 1])
    current["name"] = c[0].text_input("Scenario name", key="scenario_name", max_chars=80)
    st.session_state["inputs"] = current
    if not current["name"].strip():
        st.error("Give the scenario a name before saving.")
        return
    saved = snapshot(current, result, manifest["fingerprint"], manifest["catalog"])
    if c[1].button("Save to comparison", type="primary", width="stretch"):
        st.session_state["saved"][current["name"]] = saved
        st.success("Saved for comparison in this session. Download JSON to keep it after closing the app.")
    c[2].download_button("Download JSON", saved, "pricing-scenario.json", "application/json", width="stretch")
    st.download_button("Export segment results CSV", output.to_csv(index=False), "scenario-segments.csv", "text/csv")


def portfolio_page(data, manifest):
    st.title("The book behind the prices")
    p = data[data.field.eq("driver_age_band")]
    c = st.columns(4)
    c[0].metric("Policies", f"{p.policies.sum():,.0f}")
    c[1].metric("Historical exposure", f"{p.exposure.sum():,.0f} years")
    c[2].metric("Linked recorded claims", f"{p.recorded_claims.sum():,.0f}")
    c[3].metric("Recorded cost / year", money(p.recorded_cost.sum() / p.exposure.sum()))
    st.warning(f"{p.missing_cost_policies.sum():,.0f} policies report original claims without a linked cost row. The fitted target covers recorded costs; missing rows do not establish zero ultimate losses.")
    c = st.columns([1.5, 1])
    with c[0]:
        st.subheader("Historical claim cost by driver age")
        age = p.groupby("segment")[ ["recorded_cost", "exposure"] ].sum().reset_index()
        chart(go.Figure(go.Bar(x=age.segment, y=age.recorded_cost / age.exposure, marker_color=GREEN)).update_layout(yaxis_title="Recorded cost / policy-year (EUR)"))
    with c[1]:
        st.subheader("How to read this workspace")
        st.write("Observed: exposure, counts and linked historical claim costs. Modelled: annual recorded loss costs. Assumed: prices, renewal response, inflation, expenses and stress multipliers.")
        st.write("French third-party liability data, circa 2011–2013. The largest 1% of linked claims represents about 38% of cost. It does not establish current Australian motor or home rates.")
        st.write("No current premiums, dates, customer IDs or renewal outcomes are available. Scenario loss ratios use synthetic premiums; they are not historical observed loss ratios.")
    st.subheader("Frozen partitions")
    table(p.groupby("split").agg(policies=("policies", "sum"), exposure=("exposure", "sum"), linked_claims=("recorded_claims", "sum"), recorded_cost_eur=("recorded_cost", "sum")).reset_index())


def comparison_page(tables):
    st.title("A measured model decision")
    st.write("Boosting is the frozen illustrative default; GLM remains the explainable benchmark. Selection used validation before the final test was read.")
    split = st.selectbox("Evaluation population", ["test", "validation"], format_func=lambda x: "Final test" if x == "test" else "Validation", key="comparison_split")
    m = tables["metrics"]; m = m[m.split.eq(split)].set_index("model")
    c = st.columns(3)
    c[0].metric("Pure-deviance reduction vs GLM", percent(1 - m.loc["boost", "pure_deviance"] / m.loc["glm", "pure_deviance"]))
    c[1].metric("Boosting raw Gini", f"{m.loc['boost', 'raw_gini']:.3f}", f"{m.loc['boost', 'raw_gini'] - m.loc['glm', 'raw_gini']:+.3f} vs GLM")
    c[2].metric("Boosting recorded cost A/E", f"{m.loc['boost', 'pure_premium_AE']:.3f}")
    c = st.columns(2)
    with c[0]:
        st.subheader("Exposure concentration")
        fig = go.Figure()
        curves = tables["concentration_curves"]
        for model, color in [("glm", BLUE), ("boost", GREEN)]:
            r = curves[curves.model.eq(model) & curves.split.eq(split)]
            fig.add_trace(go.Scatter(x=r.exposure_share, y=r.cost_share, name=model.upper(), line={"color": color}))
        fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], name="Equal cost rate", line={"color": "#999999", "dash": "dot"}))
        fig.update_layout(xaxis_title="Cumulative exposure · ascending predicted risk", yaxis_title="Cumulative recorded cost")
        chart(fig)
    with c[1]:
        st.subheader("Decile actual vs expected")
        model = st.selectbox("Decile model", ["boost", "glm"], key="decile_model")
        r = tables["deciles"]; r = r[r.model.eq(model) & r.split.eq(split)]
        fig = go.Figure()
        for col, label, color in [("actual_per_year_eur", "Recorded actual", GREEN), ("expected_per_year_eur", "Expected", ORANGE)]:
            fig.add_trace(go.Scatter(x=r.decile, y=r[col], name=label, mode="lines+markers", line={"color": color}))
        fig.update_layout(xaxis_title="Model-specific risk decile", yaxis_title="Historical cost / policy-year (EUR)")
        chart(fig)
    st.subheader("Paired differences with 95% sampling intervals")
    intervals = tables["paired_intervals"]
    table(intervals[intervals.split.eq(split) & intervals.model.eq("boost_minus_glm")][["metric", "point", "lower_95", "upper_95", "valid_replicates"]])
    st.caption("250 paired policy samples; predictions and bins fixed. Intervals exclude refitting, tuning, missing costs and future drift. Final-test top-decile lift and severity-deviance differences include zero.")
    table(m.reset_index()[["model", "frequency_deviance", "severity_deviance", "pure_deviance", "raw_gini", "normalised_gini", "top_decile_lift", "pure_premium_AE"]])
    with st.expander("Interpretability, governance and large losses"):
        st.write("GLM exposes multiplicative factors and reference groups. Boosting captures nonlinear effects and interactions, but requires explanation, stability and fairness review. Neither has automatic regulatory acceptance. Monotonicity is not imposed.")
        tails = tables["tail_sensitivities"]
        table(tails[tails.split.eq(split)][["model", "scenario", "cost_AE", "pure_deviance", "raw_gini", "top_decile_lift"]])
        st.caption("Capped evaluated outcomes and capped fitted severity answer different questions. Main results retain raw costs. Original-count products are illustrative missing-cost sensitivities.")


def diagnostics_page(tables):
    st.title("Where prices warrant investigation")
    c = st.columns(3)
    field = c[0].selectbox("Diagnostic segment", list(SEGMENT_FIELDS), format_func=SEGMENT_FIELDS.get, key="diagnostic_field")
    model = c[1].selectbox("Diagnostic model", ["boost", "glm"], key="diagnostic_model")
    split = c[2].selectbox("Diagnostic holdout", ["test", "validation"], key="diagnostic_split")
    r = tables["segments"]; r = r[r.feature.eq(field) & r.model.eq(model) & r.split.eq(split)]
    # Draw absolute bounds, preserving even percentile intervals that exclude
    # the point estimate; centred error-bar APIs cannot represent that case.
    x, y = [], []
    for row in r.itertuples():
        x.extend([row.segment, row.segment, None])
        y.extend([row.cost_AE_lower_95, row.cost_AE_upper_95, None])
    fig = go.Figure(go.Scatter(x=x, y=y, mode="lines", line={"color": GREEN}, name="95% sampling interval"))
    fig.add_trace(go.Scatter(x=r.segment, y=r.cost_AE, mode="markers", marker={"color": GREEN, "size": 9}, name="Recorded cost A/E"))
    fig.add_hline(y=1, line_dash="dot", line_color="#787774")
    fig.update_layout(xaxis_title=SEGMENT_FIELDS[field], yaxis_title="Recorded cost actual / expected · 95% sampling interval")
    chart(fig)
    table(r[["segment", "policies", "exposure", "recorded_claims", "cost_AE", "cost_AE_lower_95", "cost_AE_upper_95", "recorded_to_source_claim_count_ratio", "low_claim_volume"]])
    st.info("Investigate persistent differences across holdouts and tail sensitivities. The GLM's 75+ age A/E reverses from about 1.67 on validation to 0.70 on test; a single ratio is a poor rate multiplier. <100 linked claims is a screening flag, not formal credibility.")


def calculator_page(root, inputs, manifest):
    st.title("Explore an individual risk")
    st.caption("Frozen rating models, historical EUR and the current scenario assumptions. This is an illustrative calculation, not a current insurance quote.")
    if not all((root / f"artifacts/{model}/bundle.joblib").exists() for model in ["glm", "boost"]):
        st.info("The risk calculator needs the local fitted bundles. Rebuild them using the setup commands in README.md; the other pages run from verified aggregate evidence.")
        return
    try:
        models = cached_models(str(root), manifest["fingerprint"])
    except (ValueError, OSError) as exc:
        st.error("The frozen risk models could not be verified. Rebuild the pipeline using README.md before using the calculator.")
        st.caption(str(exc))
        return
    spec = json.loads((root / "reports/dashboard/risk_spec.json").read_text())
    values = {}
    defaults = {"DrivAge": 40, "VehAge": 5, "VehPower": 6, "BonusMalus": 50, "Density": 1000}
    labels = {"DrivAge": "Driver age", "VehAge": "Vehicle age", "VehPower": "Vehicle power", "BonusMalus": "Bonus / malus", "Density": "Density"}
    c = st.columns(5)
    for col, key in zip(c, defaults):
        bounds = spec["numeric"][key]
        values[key] = col.number_input(labels[key], min_value=int(bounds["min"]), max_value=int(bounds["max"]), value=int(defaults[key]), step=1, key=f"risk_{key}")
    c = st.columns(4)
    for col, key, default in zip(c, ["Area", "Region", "VehBrand", "VehGas"], ["C", "R24", "B1", "Diesel"]):
        options = spec["categories"][key]
        values[key] = col.selectbox({"Area": "Area", "Region": "Region code", "VehBrand": "Brand code", "VehGas": "Fuel"}[key], options, index=options.index(default), key=f"risk_{key}")
    try:
        frame = risk_frame(values, spec)
        predictions = {name: bundle.predict(frame).iloc[0] for name, bundle in models.items()}
        rows = [{"Model": name.upper(), "Annual frequency": p.frequency, "Mean severity EUR": p.severity, "Annual recorded loss EUR": p.pure_premium} for name, p in predictions.items()]
        table(pd.DataFrame(rows))
        segment = str(frame[inputs["segment_field"]].iloc[0])
        one = pd.DataFrame({"segment": [segment], "policies": [1], "glm_loss": [predictions["glm"].pure_premium], "boost_loss": [predictions["boost"].pure_premium]})
        from insurance_pricing.scenarios import parse_inputs
        a, rules, stresses = parse_inputs(inputs, manifest["catalog"])
        result = simulate(one, a, [r for r in rules if r.segment == segment], stresses, inputs["model"], inputs["premium_basis"])
        c = st.columns(3)
        c[0].metric("Illustrative annual price", money(result.segments.scenario_premium.iloc[0] / result.segments.scenario_retention.iloc[0]) if result.segments.scenario_retention.iloc[0] > 0 else money((one[f"{inputs['premium_basis']}_loss"].iloc[0] + a.fixed_expense) / (1 - a.variable_expense - a.margin) * (1 + result.segments.combined_change.iloc[0])))
        c[1].metric("Expected renewal retention", percent(result.scenario["retention"]))
        c[2].metric("Expected contribution / opportunity", money(result.scenario["contribution"]))
        st.caption(f"Price anchor: {inputs['premium_basis'].upper()}; claims model: {inputs['model'].upper()}. Segment {segment}. Uses the current saved working scenario's rate, expense, retention and stress inputs; the cohort filter does not restrict this hypothetical risk.")
    except ValueError as exc:
        st.error(str(exc)); return
    extremes = [labels[key] for key in defaults if not spec["numeric"][key]["p01"] <= values[key] <= spec["numeric"][key]["p99"]]
    if extremes:
        st.warning("Near the edge of training support: " + ", ".join(extremes) + ". Predictions may be unstable; combinations are not guaranteed representative.")
    support = pd.read_csv(root / "reports/dashboard/risk_support.csv")
    mask = np.ones(len(support), dtype=bool)
    for key in ["driver_age_band", "Region", "VehBrand", "VehGas"]:
        mask &= support[key].astype(str).eq(str(frame[key].iloc[0])).to_numpy()
    count, claims = support.loc[mask, ["policies", "recorded_claims"]].sum()
    st.caption(f"Coarse training cell (age band, region, brand, fuel): {count:,.0f} policies, {claims:,.0f} linked claims. This is a support screen, not formal credibility or joint support for all features.")
    if count < 100 or claims < 20:
        st.warning("Limited training support in this coarse cell. Treat the model response cautiously.")
    effects = pd.read_csv(root / "reports/comparison/driver_age_partial_dependence.csv")
    fig = go.Figure()
    for model, color in [("glm", BLUE), ("boost", GREEN)]:
        r = effects[effects.model.eq(model)]
        fig.add_trace(go.Scatter(x=r.driver_age, y=r.mean_pure_premium_eur, name=model.upper(), line={"color": color}))
    fig.update_layout(xaxis_title="Hypothetical driver age", yaxis_title="Mean model cost (EUR) · fixed validation risk sample")
    chart(fig)
    st.caption("Age response uses a separate fixed risk sample. Correlated features and implausible combinations prevent causal interpretation; boosting can change sharply at nearby ages.")


def saved_page(data, manifest):
    st.title("Compare the decisions you are considering")
    st.caption("Saved scenarios live in this browser session. Download JSON for durable storage; imports are checked and results are recomputed.")
    upload = st.file_uploader("Reload a scenario JSON", type="json", key="scenario_upload")
    if upload is not None and st.button("Load uploaded scenario", type="primary"):
        try:
            inputs = load_snapshot(upload.getvalue(), manifest["fingerprint"], manifest["catalog"])
            run_inputs(data, inputs, manifest["catalog"])
            st.session_state["pending_inputs"] = inputs
            st.session_state["navigate_scenarios"] = True
            st.rerun()
        except (ValueError, TypeError) as exc:
            st.error(str(exc))
    rows = []
    for name, value in st.session_state["saved"].items():
        inputs = load_snapshot(value, manifest["fingerprint"], manifest["catalog"])
        _, result, *_ = run_inputs(data, inputs, manifest["catalog"])
        s = result.scenario
        rows.append({"Scenario": name, "Claims model": inputs["model"], "Price anchor": inputs["premium_basis"], "Cohort": inputs["scope"], "Segmentation": inputs["segment_field"],
                     "Contribution EUR": round(s["contribution"], 2), "Retained policies": round(s["retained"], 2), "Premium EUR": round(s["premium"], 2), "Loss ratio": percent(s["loss_ratio"])})
    if not rows:
        st.info("Save a scenario on the rate page to start a comparison.")
        return
    table(pd.DataFrame(rows))
    st.caption("Compare scenarios on identical cohorts, baseline anchors and expense/claims assumptions when isolating rate or model effects.")
    name = st.selectbox("Saved scenario", list(st.session_state["saved"]), key="saved_choice")
    c = st.columns(3)
    if c[0].button("Restore to rate page"):
        st.session_state["pending_inputs"] = load_snapshot(st.session_state["saved"][name], manifest["fingerprint"], manifest["catalog"])
        st.session_state["navigate_scenarios"] = True
        st.rerun()
    c[1].download_button("Download saved JSON", st.session_state["saved"][name], "saved-scenario.json", "application/json")
    if c[2].button("Remove saved scenario"):
        del st.session_state["saved"][name]; st.rerun()


def main(root: Path):
    st.set_page_config(page_title="Motor pricing studio", layout="wide", initial_sidebar_state="expanded")
    style()
    st.sidebar.markdown('<div class="eyebrow">INSURANCE / PRICING STUDIO</div>', unsafe_allow_html=True)
    st.sidebar.title("Motor pricing")
    st.sidebar.caption("French liability case study\n\nHistorical EUR · Recorded costs")
    if st.session_state.pop("navigate_scenarios", False):
        st.session_state["page"] = "Rate scenarios"
    page = st.sidebar.radio("Workspace", ["Rate scenarios", "Portfolio", "Model comparison", "Segment diagnostics", "Risk calculator", "Saved scenarios"], key="page", label_visibility="collapsed")
    try:
        token = (root / "reports/dashboard/manifest.json").read_text()
        manifest, data, tables = cached_data(str(root), token)
    except (FileNotFoundError, ValueError) as exc:
        st.title("Prepare the pricing workspace")
        st.info("Run the model pipeline and `insurance-pricing prepare-dashboard` using the README setup instructions. The dashboard never fits models or downloads data during an interaction.")
        st.caption(str(exc)); return
    st.session_state.setdefault("inputs", default_inputs())
    st.session_state.setdefault("saved", {})
    if "pending_inputs" in st.session_state:
        st.session_state["inputs"] = st.session_state.pop("pending_inputs")
        initialise_controls(st.session_state["inputs"])
    elif page == "Rate scenarios" and (st.session_state.get("previous_page") != page or "editor_revision" not in st.session_state):
        initialise_controls(st.session_state["inputs"])
    st.session_state["previous_page"] = page
    st.markdown('<div class="eyebrow">OBSERVED DATA · FROZEN MODELS · EXPLICIT ASSUMPTIONS</div>', unsafe_allow_html=True)
    st.sidebar.divider()
    st.sidebar.caption("Boosting default · GLM benchmark\n\nNo live tariff recommendation. Missing costs and large losses remain material.")
    st.sidebar.caption("Project stages 1–5 complete · Historical public-data demo")
    if page == "Rate scenarios": scenario_page(st.session_state["inputs"], data, manifest)
    elif page == "Portfolio": portfolio_page(data, manifest)
    elif page == "Model comparison": comparison_page(tables)
    elif page == "Segment diagnostics": diagnostics_page(tables)
    elif page == "Risk calculator": calculator_page(root, st.session_state["inputs"], manifest)
    else: saved_page(data, manifest)
