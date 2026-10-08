"""Interpretable, unpenalised log-link frequency–severity GLMs.

Rate-target Poisson with exposure weights has the same score equations as
count-target Poisson with log-exposure offset. Gamma uses individual claims
and unit weights. A shared encoder learns categories from training policies
only; unknown categories are rejected rather than assigned a silent base rate.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import warnings

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import GammaRegressor, PoissonRegressor
from sklearn.preprocessing import OneHotEncoder
from threadpoolctl import threadpool_limits

from insurance_pricing.data import CATEGORICAL_FEATURES, MODEL_FEATURES, NUMERIC_FEATURES


@dataclass
class GLMBundle:
    encoder: OneHotEncoder
    models: dict
    benchmark_frequency: float
    benchmark_severity: float
    severity_cap: float
    config: dict

    @staticmethod
    def categories(frame: pd.DataFrame) -> pd.DataFrame:
        return frame[CATEGORICAL_FEATURES].astype(str)

    def transform(self, frame: pd.DataFrame) -> sparse.csr_matrix:
        if frame[MODEL_FEATURES].isna().any().any():
            raise ValueError("Missing rating features")
        numeric = frame[NUMERIC_FEATURES].to_numpy(dtype=float)
        if not np.isfinite(numeric).all():
            raise ValueError("Non-finite rating features")
        categorical = self.encoder.transform(self.categories(frame))
        return sparse.hstack([categorical, sparse.csr_matrix(numeric)], format="csr")

    def feature_names(self) -> list[str]:
        return list(self.encoder.get_feature_names_out(CATEGORICAL_FEATURES)) + NUMERIC_FEATURES

    def predict(self, policies: pd.DataFrame) -> pd.DataFrame:
        x = self.transform(policies)
        output = pd.DataFrame(index=policies.index)
        with threadpool_limits(limits=self.config["threads"]):
            for name, model in self.models.items():
                output[name] = model.predict(x)
        output["pure_premium"] = output["frequency"] * output["severity"]
        output["source_count_premium"] = output["source_frequency"] * output["severity"]
        output["complete_subset_premium"] = output["complete_frequency"] * output["complete_severity"]
        output["capped_severity_premium"] = output["frequency"] * output["capped_severity"]
        output["benchmark_frequency"] = self.benchmark_frequency
        output["benchmark_severity"] = self.benchmark_severity
        output["benchmark_premium"] = self.benchmark_frequency * self.benchmark_severity
        if not np.isfinite(output.to_numpy()).all() or (output <= 0).any().any():
            raise ValueError("Predictions must be strictly positive and finite")
        return output


def fit_bundle(policies: pd.DataFrame, claims: pd.DataFrame, config: dict) -> GLMBundle:
    """Reject mixed partitions; never accept holdout rows in training."""
    if policies.empty or claims.empty or not policies["split"].eq("train").all() or not claims["split"].eq("train").all():
        raise ValueError("Fit requires nonempty training-only policy and claim tables")
    os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(config["threads"]))
    if config["alpha"] != 0:
        raise ValueError("Part 2 is an unpenalised GLM baseline: alpha must be zero")
    if not 0 < config["severity_cap_quantile"] < 1:
        raise ValueError("Invalid sensitivity quantile")
    if not policies["IDpol"].is_unique or not claims["IDpol"].isin(policies["IDpol"]).all():
        raise ValueError("Claim-policy training population does not reconcile")
    exposure = policies["Exposure"].to_numpy(dtype=float)
    counts = policies["recorded_claim_count"].to_numpy(dtype=float)
    amounts = claims["ClaimAmount"].to_numpy(dtype=float)
    if not np.isfinite(exposure).all() or (exposure <= 0).any() or not np.isfinite(amounts).all() or (amounts <= 0).any():
        raise ValueError("Exposure and Gamma outcomes must be positive finite values")
    if not np.isfinite(counts).all() or (counts < 0).any() or (counts != np.floor(counts)).any() or counts.sum() != len(claims):
        raise ValueError("Recorded counts must reconcile to training claims")
    actual_counts = claims.groupby("IDpol").size().reindex(policies["IDpol"], fill_value=0).to_numpy()
    if not np.array_equal(counts, actual_counts):
        raise ValueError("Recorded counts do not reconcile at policy level")
    encoder = OneHotEncoder(
        drop=[config["categorical_references"][col] for col in CATEGORICAL_FEATURES],
        handle_unknown="error", sparse_output=True, dtype=np.float64,
    )
    encoder.fit(GLMBundle.categories(policies))
    bundle = GLMBundle(encoder, {}, float(counts.sum() / exposure.sum()), float(amounts.mean()), float(np.quantile(amounts, config["severity_cap_quantile"])), config.copy())
    xp, xc = bundle.transform(policies), bundle.transform(claims)
    matched_p = policies["claim_count_matches"].to_numpy(dtype=bool)
    matched_c = claims["claim_count_matches"].to_numpy(dtype=bool)
    specs = [
        ("frequency", PoissonRegressor, xp, counts / exposure, exposure),
        ("severity", GammaRegressor, xc, amounts, None),
        ("source_frequency", PoissonRegressor, xp, policies["source_claim_count"].to_numpy(dtype=float) / exposure, exposure),
        ("complete_frequency", PoissonRegressor, xp[matched_p], counts[matched_p] / exposure[matched_p], exposure[matched_p]),
        ("complete_severity", GammaRegressor, xc[matched_c], amounts[matched_c], None),
        ("capped_severity", GammaRegressor, xc, np.minimum(amounts, bundle.severity_cap), None),
    ]
    with threadpool_limits(limits=config["threads"]), warnings.catch_warnings():
        warnings.simplefilter("error", ConvergenceWarning)
        for name, cls, x, target, weights in specs:
            model = cls(alpha=0, solver=config["solver"], max_iter=config["max_iter"], tol=config["tol"])
            model.fit(x, target, sample_weight=weights)
            if model.n_iter_ >= config["max_iter"]:
                raise RuntimeError(f"{name} exhausted its iteration budget")
            bundle.models[name] = model
            print(f"Fitted {name}: {model.n_iter_} iterations, {x.shape[0]:,} observations", flush=True)
    return bundle


def coefficient_table(bundle: GLMBundle) -> pd.DataFrame:
    """Relativities relative to explicit bases, and meaningful numeric increments.

    These are conditional fitted factors, not causal effects or confidence bounds.
    """
    rows = []
    for name in ["frequency", "severity"]:
        model = bundle.models[name]
        offset = 0
        for col, categories, drop_index in zip(CATEGORICAL_FEATURES, bundle.encoder.categories_, bundle.encoder.drop_idx_):
            reference = categories[drop_index]
            for level in categories:
                beta = 0.0 if level == reference else float(model.coef_[offset])
                if level != reference:
                    offset += 1
                rows.append({"model": name, "feature": col, "level_or_increment": level, "reference": reference, "coefficient": beta, "increment": 1., "relativity": float(np.exp(beta))})
        for col, step, label in zip(NUMERIC_FEATURES, [.1, 1.], ["+10 bonus/malus points", "+1 log(1+density)"]):
            beta = float(model.coef_[offset])
            offset += 1
            rows.append({"model": name, "feature": col, "level_or_increment": label, "reference": "continuous", "coefficient": beta, "increment": step, "relativity": float(np.exp(beta * step))})
    return pd.DataFrame(rows)
