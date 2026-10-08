"""Reproducible numerical figures from aggregate CSVs; vector PDF and PNG."""

import os
from pathlib import Path

# Keep matplotlib's writable cache within the project rather than the user's home.
def plot_glm(root: Path):
    os.environ.setdefault("MPLCONFIGDIR", str(root / "artifacts/matplotlib-cache"))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd

    plt.rcParams.update({
        "font.family": "serif", "font.serif": ["DejaVu Serif"], "font.size": 11,
        "axes.titlesize": 12, "axes.titleweight": "bold", "axes.spines.top": False,
        "axes.spines.right": False, "axes.grid": True, "grid.alpha": .15,
        "legend.frameon": False, "pdf.fonttype": 42, "ps.fonttype": 42,
        "savefig.dpi": 300,
    })
    reports = root / "reports/glm"
    figures = reports / "figures"
    figures.mkdir(exist_ok=True)
    actual, predicted, stress = "#0072B2", "#D55E00", "#009E73"

    def save(fig, name):
        fig.savefig(figures / f"{name}.pdf", bbox_inches="tight")
        fig.savefig(figures / f"{name}.png", bbox_inches="tight", dpi=300)
        plt.close(fig)

    deciles = pd.read_csv(reports / "validation_deciles.csv")
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), layout="constrained")
    ax = axes[0]
    ax.plot(deciles.segment, deciles.actual_cost_per_year_eur, "o-", color=actual, label="Recorded actual")
    ax.plot(deciles.segment, deciles.predicted_cost_per_year_eur, "s--", color=predicted, label="GLM expected")
    ax.set(xlabel="Predicted risk decile (approximately equal exposure)", ylabel="Recorded cost / policy-year (EUR)", title="Validation pure-premium calibration")
    ax.legend()
    axes[1].plot(deciles.segment, deciles.cost_AE, "o-", color=actual, label="Claim-cost A/E")
    axes[1].plot(deciles.segment, deciles.frequency_AE, "s--", color=stress, label="Claim-count A/E")
    axes[1].axhline(1, color=".5", ls=":")
    axes[1].set(xlabel="Predicted risk decile", ylabel="Actual / expected", title="Where predictions differ")
    axes[1].legend()
    save(fig, "validation_deciles")

    segments = pd.read_csv(reports / "validation_segments.csv")
    age = segments[segments.feature.eq("driver_age_band")].copy()
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), layout="constrained")
    x = np.arange(len(age))
    axes[0].bar(x - .18, age.actual_cost_per_year_eur, .36, color=actual, label="Recorded actual")
    axes[0].bar(x + .18, age.predicted_cost_per_year_eur, .36, color=predicted, label="GLM expected")
    axes[0].set_xticks(x, age.segment)
    axes[0].set(ylabel="Recorded cost / policy-year (EUR)", title="Validation: driver age")
    axes[0].legend()
    axes[1].bar(x, age.recorded_to_source_claim_count_ratio, color=stress, width=.65)
    axes[1].set_xticks(x, age.segment)
    axes[1].set(ylim=(0, 1.05), ylabel="Recorded / original claim count", title="Cost-table coverage differs by age")
    save(fig, "validation_age_and_coverage")

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), layout="constrained")
    for ax, family, label in zip(axes, ["frequency", "severity"], ["Expected count over source exposure", "Expected claim severity (EUR)"]):
        bins = pd.read_csv(reports / f"{family}_residual_bins.csv")
        ax.plot(bins.mean_fitted, bins.mean_pearson, "o-", color=actual)
        ax.axhline(0, color=".5", ls=":")
        ax.set(xlabel=label, ylabel="Mean Pearson residual", title=f"Training {family}: fitted-value bins")
        if family == "frequency":
            ax.set_xscale("log")
    save(fig, "training_residuals")

    coefficients = pd.read_csv(reports / "coefficients.csv")
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), layout="constrained")
    for ax, name in zip(axes, ["frequency", "severity"]):
        rows = coefficients[coefficients.model.eq(name) & coefficients.feature.eq("driver_age_band")]
        ax.plot(rows.level_or_increment, rows.relativity, "o-", color=predicted)
        ax.axhline(1, color=".5", ls=":")
        ax.set(ylabel=f"Conditional factor vs age {rows.reference.iloc[0]}", title=f"GLM {name}: age factors")
    save(fig, "driver_age_relativities")
