"""Annual renewal economics, independent of Streamlit and observed exposure.

Inputs contain sums of annual model loss costs and representative policy weights.
Aggregation is exact when price response and stress are common within a segment:
baseline premium is affine in loss, and all monetary totals are additive.
"""

from dataclasses import asdict, dataclass, replace
import json

import numpy as np
import pandas as pd

ENGINE_VERSION = "1"
MODELS = ("glm", "boost")


def finite_number(value, name):
    if isinstance(value, (bool, str)) or not isinstance(value, (int, float, np.number)) or not np.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


@dataclass(frozen=True)
class Assumptions:
    global_change: float = 0.0
    retention: float = 0.85
    elasticity: float = 1.2
    claims_inflation: float = 0.0
    variable_expense: float = 0.25
    fixed_expense: float = 30.0
    margin: float = 0.10
    minimum_change: float = -0.20
    maximum_change: float = 0.20

    def validate(self):
        for name, value in asdict(self).items():
            finite_number(value, name)
        if not 0 <= self.retention <= 1 or self.elasticity < 0:
            raise ValueError("Retention must be 0–1 and elasticity nonnegative")
        if self.fixed_expense < 0 or min(self.variable_expense, self.margin) < 0 or self.variable_expense + self.margin >= 1:
            raise ValueError("Expenses and margin must be nonnegative; variable expense + margin must be below 100%")
        if self.global_change <= -1 or self.claims_inflation <= -1:
            raise ValueError("Price and claims multipliers must remain positive")
        if self.minimum_change <= -1 or self.minimum_change > self.maximum_change:
            raise ValueError("Rate corridor must be ordered and above −100%")


@dataclass(frozen=True)
class SegmentRule:
    segment: str
    rate_change: float = 0.0
    elasticity: float | None = None
    retention: float | None = None


@dataclass(frozen=True)
class Stress:
    name: str
    component: str = "loss"
    multiplier: float = 1.0


def validate_rules(rules, levels):
    seen = set()
    for rule in rules:
        if not isinstance(rule.segment, str) or rule.segment not in levels:
            raise ValueError(f"Unknown segment: {rule.segment}")
        if rule.segment in seen:
            raise ValueError(f"Duplicate segment rule: {rule.segment}")
        seen.add(rule.segment)
        if finite_number(rule.rate_change, "Segment rate change") <= -1:
            raise ValueError("Segment price multiplier must be positive")
        if rule.elasticity is not None and finite_number(rule.elasticity, "Segment elasticity") < 0:
            raise ValueError("Segment elasticity must be nonnegative")
        if rule.retention is not None and not 0 <= finite_number(rule.retention, "Segment retention") <= 1:
            raise ValueError("Segment retention must be 0–1")


def stress_multiplier(stresses):
    multiplier, names = 1.0, set()
    for stress in stresses:
        if not isinstance(stress.name, str) or not 0 < len(stress.name.strip()) <= 80:
            raise ValueError("Give each stress a name of 1–80 characters")
        name = stress.name.strip().casefold()
        if name in names:
            raise ValueError("Stress names must be unique")
        names.add(name)
        if stress.component not in {"frequency", "severity", "loss"}:
            raise ValueError("Stress component must be frequency, severity or loss")
        factor = finite_number(stress.multiplier, "Stress multiplier")
        if factor <= 0:
            raise ValueError("Stress multipliers must be positive")
        multiplier *= factor
    if not np.isfinite(multiplier) or multiplier <= 0:
        raise ValueError("Combined stress is outside the finite positive range")
    return multiplier


def totals(frame, prefix):
    values = {name: float(frame[f"{prefix}_{name}"].sum()) for name in ["retained", "premium", "claims", "expenses", "contribution"]}
    premium = values["premium"]
    values["loss_ratio"] = values["claims"] / premium if premium > 0 else None
    values["combined_ratio"] = (values["claims"] + values["expenses"]) / premium if premium > 0 else None
    values["retention"] = values["retained"] / float(frame.policies.sum())
    return values


@dataclass
class ScenarioResult:
    segments: pd.DataFrame
    baseline: dict
    scenario: dict
    unstressed_baseline: dict


def simulate(cohort, assumptions=Assumptions(), rules=(), stresses=(), model="boost", premium_basis="glm"):
    assumptions.validate()
    if model not in MODELS or premium_basis not in MODELS:
        raise ValueError("Choose GLM or boosting")
    needed = ["segment", "policies", "glm_loss", "boost_loss"]
    if not set(needed).issubset(cohort.columns) or cohort.empty or not cohort.segment.is_unique:
        raise ValueError("Select a nonempty cohort with one row per segment")
    numeric = cohort[["policies", "glm_loss", "boost_loss"]].to_numpy(dtype=float)
    if not np.isfinite(numeric).all() or (numeric < 0).any():
        raise ValueError("Cohort weights and model loss sums must be finite and nonnegative")
    validate_rules(rules, set(cohort.segment))
    zero = cohort.policies.eq(0)
    if (cohort.loc[zero, ["glm_loss", "boost_loss"]] != 0).any().any():
        raise ValueError("Zero-weight segments cannot have positive weighted loss sums")
    out = cohort.loc[~zero].copy()
    if out.empty or (out[["glm_loss", "boost_loss"]] <= 0).any().any():
        raise ValueError("Select positive-weight risks with positive model losses")
    lookup = {r.segment: r for r in rules}
    out["segment_change"] = [lookup[s].rate_change if s in lookup else 0 for s in out.segment]
    out["elasticity"] = [lookup[s].elasticity if s in lookup and lookup[s].elasticity is not None else assumptions.elasticity for s in out.segment]
    out["baseline_retention"] = [lookup[s].retention if s in lookup and lookup[s].retention is not None else assumptions.retention for s in out.segment]
    multiplier = (1 + assumptions.global_change) * (1 + out.segment_change.to_numpy())
    change = multiplier - 1
    if (change < assumptions.minimum_change - 1e-12).any() or (change > assumptions.maximum_change + 1e-12).any():
        raise ValueError("Combined global and segment change exceeds the rate corridor; adjust inputs")
    out["combined_change"] = change
    q0 = out.baseline_retention.to_numpy()
    # Log-space evaluation handles large elasticities and q0=0 without 0*inf.
    with np.errstate(divide="ignore", under="ignore"):
        q1 = np.exp(np.minimum(np.log(q0) - out.elasticity.to_numpy() * np.log(multiplier), 0))
    out["scenario_retention"] = q1
    p0 = (out[f"{premium_basis}_loss"].to_numpy() + out.policies.to_numpy() * assumptions.fixed_expense) / (1 - assumptions.variable_expense - assumptions.margin)
    loss0 = out[f"{model}_loss"].to_numpy()
    loss1 = loss0 * (1 + assumptions.claims_inflation) * stress_multiplier(stresses)
    for prefix, q, price, loss in [("baseline", q0, p0, loss1), ("scenario", q1, p0 * multiplier, loss1), ("unstressed", q0, p0, loss0)]:
        out[f"{prefix}_retained"] = out.policies * q
        out[f"{prefix}_premium"] = price * q
        out[f"{prefix}_claims"] = loss * q
        out[f"{prefix}_expenses"] = q * (assumptions.variable_expense * price + assumptions.fixed_expense * out.policies)
        out[f"{prefix}_contribution"] = out[f"{prefix}_premium"] - out[f"{prefix}_claims"] - out[f"{prefix}_expenses"]
        out[f"{prefix}_loss_ratio"] = np.divide(out[f"{prefix}_claims"], out[f"{prefix}_premium"], out=np.full(len(out), np.nan), where=out[f"{prefix}_premium"] > 0)
    amounts = out[[c for c in out if c.endswith(("_premium", "_claims", "_expenses", "_contribution", "_retained"))]]
    if not np.isfinite(amounts.to_numpy()).all():
        raise ValueError("Economic assumptions produce non-finite results")
    return ScenarioResult(out, totals(out, "baseline"), totals(out, "scenario"), totals(out, "unstressed"))


def feasible_global_range(assumptions, rules, levels):
    assumptions.validate()
    validate_rules(rules, set(levels))
    multipliers = np.array([1 + next((r.rate_change for r in rules if r.segment == level), 0) for level in levels])
    if len(multipliers) == 0:
        raise ValueError("No segments selected")
    return float(np.max((1 + assumptions.minimum_change) / multipliers - 1)), float(np.min((1 + assumptions.maximum_change) / multipliers - 1))


def sensitivity(cohort, assumptions, rules=(), stresses=(), model="boost", premium_basis="glm", points=21):
    lower, upper = feasible_global_range(assumptions, rules, cohort.segment)
    if lower > upper:
        raise ValueError("No global change satisfies all segment corridors")
    rows = []
    for change in np.linspace(lower, upper, points):
        result = simulate(cohort, replace(assumptions, global_change=float(change)), rules, stresses, model, premium_basis)
        rows.append({"global_change": change, **result.scenario})
    return pd.DataFrame(rows)


def default_inputs():
    return {"name": "Working scenario", "model": "boost", "premium_basis": "glm", "scope": "test",
            "segment_field": "driver_age_band", "included_segments": None, "baseline_mode": "same_stress",
            "assumptions": asdict(Assumptions()), "rules": [], "stresses": []}


def parse_inputs(inputs, catalog):
    if not isinstance(inputs, dict) or set(inputs) != set(default_inputs()):
        raise ValueError("Scenario inputs have missing or unsupported fields")
    if not isinstance(inputs["name"], str) or not 0 < len(inputs["name"].strip()) <= 80:
        raise ValueError("Scenario name must be 1–80 characters")
    if not all(isinstance(inputs[key], str) for key in ["model", "premium_basis", "scope", "segment_field", "baseline_mode"]):
        raise ValueError("Model, cohort and segmentation selections must be strings")
    if inputs["model"] not in MODELS or inputs["premium_basis"] not in MODELS or inputs["scope"] not in {"train", "validation", "test", "all"} or inputs["segment_field"] not in catalog:
        raise ValueError("Unsupported model, cohort or segmentation field")
    if inputs["baseline_mode"] not in {"same_stress", "unstressed"}:
        raise ValueError("Unsupported baseline comparison")
    if not isinstance(inputs["assumptions"], dict) or set(inputs["assumptions"]) != set(asdict(Assumptions())):
        raise ValueError("Assumption fields differ from the supported schema")
    if not isinstance(inputs["rules"], list) or not isinstance(inputs["stresses"], list) or len(inputs["rules"]) > 1000 or len(inputs["stresses"]) > 100:
        raise ValueError("Use lists of up to 1,000 segment rules and 100 stress assumptions")
    try:
        assumptions = Assumptions(**inputs["assumptions"])
        rules = tuple(SegmentRule(**r) for r in inputs["rules"])
        stresses = tuple(Stress(**s) for s in inputs["stresses"])
    except (TypeError, KeyError) as exc:
        raise ValueError("Invalid segment rule or stress schema") from exc
    assumptions.validate()
    levels = catalog[inputs["segment_field"]]
    validate_rules(rules, set(levels))
    stress_multiplier(stresses)
    included = inputs["included_segments"]
    if included is not None and (not isinstance(included, list) or not all(isinstance(s, str) for s in included) or len(included) != len(set(included)) or not set(included).issubset(levels)):
        raise ValueError("Unknown or duplicate included segments")
    return assumptions, rules, stresses


def snapshot(inputs, result, fingerprint, catalog):
    parse_inputs(inputs, catalog)
    return json.dumps({"schema_version": 1, "engine_version": ENGINE_VERSION, "fingerprint": fingerprint,
                       "inputs": inputs, "outputs": {"baseline": result.baseline, "scenario": result.scenario, "unstressed_baseline": result.unstressed_baseline}}, indent=2, allow_nan=False)


def load_snapshot(value, fingerprint, catalog):
    if len(value) > 1_000_000:
        raise ValueError("Scenario file is too large")
    def reject_constant(value):
        raise ValueError(f"Non-finite JSON value: {value}")
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result
    try:
        obj = json.loads(value, parse_constant=reject_constant, object_pairs_hook=unique_keys)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("Invalid scenario JSON") from exc
    if not isinstance(obj, dict) or set(obj) != {"schema_version", "engine_version", "fingerprint", "inputs", "outputs"} or obj["schema_version"] != 1 or obj["engine_version"] != ENGINE_VERSION:
        raise ValueError("Unsupported scenario schema/engine")
    if obj["fingerprint"] != fingerprint:
        raise ValueError("Scenario uses a different source/model/dashboard version")
    parse_inputs(obj["inputs"], catalog)
    # Stored outputs are never trusted; callers recompute from checked inputs.
    return obj["inputs"]
