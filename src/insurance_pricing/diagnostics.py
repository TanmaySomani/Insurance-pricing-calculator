"""Residual and approximate GLM influence diagnostics (not causal attribution)."""

import numpy as np
import pandas as pd
from scipy import sparse

from insurance_pricing.metrics import gamma_residuals, poisson_residuals


def influence_summary(x, expected, observed, family):
    """Fisher leverage and dispersion-scaled, Cook-like one-step proxy.

    Poisson information weights are expected observed-period counts. Gamma
    log-link information weights are constant before dispersion scaling.
    Calculate in chunks to avoid a full dense policy design matrix.
    """
    z = sparse.hstack([np.ones((x.shape[0], 1)), x], format="csr")
    weights = np.asarray(expected) if family == "poisson" else np.ones(len(expected))
    gram = (z.T @ z.multiply(weights[:, None])).toarray()
    rank = int(np.linalg.matrix_rank(gram))
    if rank != z.shape[1]:
        raise ValueError(f"{family} design is rank deficient: {rank}/{z.shape[1]}")
    inverse = np.linalg.inv(gram)
    leverage = np.empty(x.shape[0])
    for start in range(0, len(leverage), 10000):
        chunk = z[start:start + 10000].toarray()
        leverage[start:start + len(chunk)] = np.einsum("ij,jk,ik->i", chunk, inverse, chunk, optimize=True) * weights[start:start + len(chunk)]
    if (leverage < -1e-8).any() or (leverage >= 1).any():
        raise ValueError("Invalid Fisher leverage")
    leverage = np.maximum(leverage, 0)
    pearson, deviance = (poisson_residuals if family == "poisson" else gamma_residuals)(observed, expected)
    dispersion = float(np.square(pearson).sum() / (len(pearson) - rank))
    proxy = np.square(pearson) * leverage / (rank * dispersion * np.square(1 - leverage))
    rows = pd.DataFrame({"actual": observed, "expected": expected, "pearson_residual": pearson, "deviance_residual": deviance, "fisher_leverage": leverage, "cook_like_proxy": proxy})
    # Keep row-level diagnostics locally; publish only distribution summaries.
    summary = {
        "family": family, "observations": len(expected), "parameters_including_intercept": rank,
        "pearson_dispersion": dispersion, "sum_deviance": float(np.square(deviance).sum()),
        "maximum_leverage": float(leverage.max()), "leverage_sum": float(leverage.sum()),
        "maximum_cook_like_proxy": float(proxy.max()),
        "absolute_deviance_residual_p99": float(np.quantile(np.abs(deviance), .99)),
        "note": "Approximate one-step influence; not an exact leave-one-out change. Gamma dispersion is especially tail-sensitive.",
    }
    return rows, summary


def residual_bins(rows):
    output = rows.copy()
    output["fitted_bin"] = pd.qcut(output["expected"], q=20, duplicates="drop")
    output["pearson_squared"] = output["pearson_residual"] ** 2
    output["deviance_squared"] = output["deviance_residual"] ** 2
    return output.groupby("fitted_bin", observed=True).agg(
        observations=("actual", "size"), mean_fitted=("expected", "mean"),
        mean_actual=("actual", "mean"), mean_pearson=("pearson_residual", "mean"),
        mean_deviance=("deviance_residual", "mean"), mean_squared_pearson=("pearson_squared", "mean"),
        mean_squared_deviance=("deviance_squared", "mean"),
    ).reset_index().drop(columns="fitted_bin")
