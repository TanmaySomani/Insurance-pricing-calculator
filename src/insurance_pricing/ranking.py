"""Tie-aware exposure concentration, lift and paired policy bootstrap metrics."""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.special import xlogy


def validate_arrays(exposure, cost, score):
    e, c, s = [np.asarray(v, dtype=float) for v in [exposure, cost, score]]
    if e.ndim != 1 or len(e) == 0 or e.shape != c.shape or e.shape != s.shape or not all(np.isfinite(v).all() for v in [e, c, s]) or (e <= 0).any() or (c < 0).any():
        raise ValueError("Ranking needs aligned finite vectors, positive exposure and nonnegative cost")
    return e, c, s


@dataclass
class RankPlan:
    order: np.ndarray
    starts: np.ndarray

    @classmethod
    def create(cls, score):
        score = np.asarray(score)
        order = np.argsort(score, kind="stable")
        starts = np.r_[0, np.flatnonzero(np.diff(score[order]) != 0) + 1]
        return cls(order, starts)

    def curve(self, exposure, cost):
        e = np.add.reduceat(np.asarray(exposure)[self.order], self.starts)
        c = np.add.reduceat(np.asarray(cost)[self.order], self.starts)
        if e.sum() <= 0 or c.sum() <= 0:
            return None
        return np.r_[0., np.cumsum(e) / e.sum()], np.r_[0., np.cumsum(c) / c.sum()]

    def gini(self, exposure, cost):
        curve = self.curve(exposure, cost)
        return float(1 - 2 * np.trapezoid(curve[1], curve[0])) if curve is not None else None


def decile_labels(exposure, score):
    e = np.asarray(exposure, dtype=float)
    score = np.asarray(score, dtype=float)
    if e.ndim != 1 or len(e) == 0 or e.shape != score.shape or not np.isfinite(e).all() or not np.isfinite(score).all() or (e <= 0).any():
        raise ValueError("Deciles require aligned finite scores and positive exposure")
    plan = RankPlan.create(score)
    grouped = np.add.reduceat(e[plan.order], plan.starts)
    midpoint = (np.cumsum(grouped) - .5 * grouped) / grouped.sum()
    labels = np.minimum((midpoint * 10).astype(int) + 1, 10)
    result = np.empty(len(e), dtype=int)
    result[plan.order] = np.repeat(labels, np.diff(np.r_[plan.starts, len(e)]))
    return result


def ranking_metrics(exposure, cost, score):
    e, c, s = validate_arrays(exposure, cost, score)
    raw = RankPlan.create(s).gini(e, c)
    ideal = RankPlan.create(c / e).gini(e, c)
    labels = decile_labels(e, s)
    high, low = labels == 10, labels == 1
    overall = c.sum() / e.sum()
    high_rate = c[high].sum() / e[high].sum() if high.any() else None
    low_rate = c[low].sum() / e[low].sum() if low.any() else None
    return {
        "raw_gini": raw, "ideal_gini": ideal,
        "normalised_gini": raw / ideal if raw is not None and ideal is not None and ideal > 1e-12 else None,
        "top_decile_lift": high_rate / overall if high_rate is not None and overall > 0 else None,
        "top_bottom_lift": high_rate / low_rate if high_rate is not None and low_rate is not None and low_rate > 0 else None,
    }


def tweedie_contributions(cost, exposure, prediction):
    """Exposure times Tweedie p=1.5 unit deviance, in stable square form."""
    y = np.asarray(cost) / np.asarray(exposure)
    mu = np.asarray(prediction)
    if (mu <= 0).any() or (y < 0).any() or not np.isfinite(mu).all():
        raise ValueError("Invalid Tweedie outcomes or predictions")
    return 4 * np.asarray(exposure) * np.square(np.sqrt(y) - np.sqrt(mu)) / np.sqrt(mu)


def model_contributions(policies, claims, pp, cp):
    e = policies.Exposure.to_numpy()
    n = policies.recorded_claim_count.to_numpy(dtype=float)
    c = policies.recorded_claim_cost.to_numpy()
    mu = e * pp.frequency.to_numpy()
    frequency = 2 * (xlogy(n, n / mu) - n + mu)
    ratio = claims.ClaimAmount.to_numpy() / cp.severity.to_numpy()
    gamma = 2 * (ratio - 1 - np.log(ratio))
    gamma_by_policy = pd.Series(gamma, index=claims.IDpol).groupby(level=0).sum().reindex(policies.IDpol, fill_value=0).to_numpy()
    return {"frequency_deviance": frequency, "severity_deviance": gamma_by_policy, "pure_deviance": tweedie_contributions(c, e, pp.pure_premium)}


def paired_bootstrap(policies, predictions, contributions, replicates, seed):
    """Resample policies once per replicate for both candidates and all metrics.

    Predictions, ranking and decile assignment stay fixed. Ordering is cached;
    repeated claim rows are grouped before sampling. Intervals exclude fitting,
    tuning, drift and missing-claim uncertainty.
    """
    if replicates < 2 or set(predictions) != {"glm", "boost"}:
        raise ValueError("Paired comparison needs both models and at least two replicates")
    e = policies.Exposure.to_numpy()
    c = policies.recorded_claim_cost.to_numpy()
    n = policies.recorded_claim_count.to_numpy()
    ideal = RankPlan.create(c / e)
    names = list(predictions)
    plans = {name: RankPlan.create(predictions[name].pure_premium) for name in names}
    tops = {name: decile_labels(e, predictions[name].pure_premium) == 10 for name in names}

    def calculate(weights):
        ew, cw, nw = e * weights, c * weights, n * weights
        total_e, total_c, total_n = ew.sum(), cw.sum(), nw.sum()
        oracle = ideal.gini(ew, cw)
        result = {}
        for name in names:
            pp, comp = predictions[name], contributions[name]
            raw = plans[name].gini(ew, cw)
            top = tops[name]
            top_e = ew[top].sum()
            result[name] = {
                "raw_gini": raw,
                "normalised_gini": raw / oracle if raw is not None and oracle is not None and oracle > 1e-12 else None,
                "top_decile_lift": cw[top].sum() / top_e / (total_c / total_e) if top_e > 0 and total_c > 0 else None,
                "pure_premium_AE": total_c / np.sum(ew * pp.pure_premium),
                "frequency_deviance": float(np.sum(weights * comp["frequency_deviance"]) / total_e),
                "severity_deviance": float(np.sum(weights * comp["severity_deviance"]) / total_n) if total_n > 0 else None,
                "pure_deviance": float(np.sum(weights * comp["pure_deviance"]) / total_e),
            }
        return result

    point = calculate(np.ones(len(e)))
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(replicates):
        weights = np.bincount(rng.integers(0, len(e), size=len(e)), minlength=len(e))
        draws.append(calculate(weights))
    rows = []
    for name in names + ["boost_minus_glm"]:
        for metric in point[names[0]]:
            if name == "boost_minus_glm":
                value = None if point["boost"][metric] is None or point["glm"][metric] is None else point["boost"][metric] - point["glm"][metric]
                samples = [d["boost"][metric] - d["glm"][metric] for d in draws if d["boost"][metric] is not None and d["glm"][metric] is not None]
            else:
                value = point[name][metric]
                samples = [d[name][metric] for d in draws if d[name][metric] is not None]
            rows.append({"model": name, "metric": metric, "point": value, "lower_95": float(np.quantile(samples, .025)) if samples else None, "upper_95": float(np.quantile(samples, .975)) if samples else None, "valid_replicates": len(samples), "requested_replicates": replicates})
    return pd.DataFrame(rows)


def decile_report(policies, pp, model):
    frame = pd.DataFrame({"decile": decile_labels(policies.Exposure, pp.pure_premium), "exposure": policies.Exposure, "cost": policies.recorded_claim_cost, "count": policies.recorded_claim_count, "expected": policies.Exposure * pp.pure_premium, "expected_count": policies.Exposure * pp.frequency})
    out = frame.groupby("decile").agg(policies=("cost", "size"), exposure=("exposure", "sum"), recorded_cost=("cost", "sum"), recorded_claims=("count", "sum"), expected_cost=("expected", "sum"), expected_claims=("expected_count", "sum")).reset_index()
    out["actual_per_year_eur"] = out.recorded_cost / out.exposure
    out["expected_per_year_eur"] = out.expected_cost / out.exposure
    out["cost_AE"] = out.recorded_cost / out.expected_cost
    out["frequency_AE"] = out.recorded_claims / out.expected_claims
    out["actual_lift"] = out.actual_per_year_eur / (frame.cost.sum() / frame.exposure.sum())
    out.insert(0, "model", model)
    return out
