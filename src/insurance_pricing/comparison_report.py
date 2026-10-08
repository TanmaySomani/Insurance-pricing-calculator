"""Manager-facing comparison and reproducible figures from aggregate evidence."""

import os
from pathlib import Path

import numpy as np
import pandas as pd


def render_comparison(root, selection, metrics, intervals):
    test = metrics[metrics.split.eq("test")].set_index("model")
    validation = metrics[metrics.split.eq("validation")].set_index("model")
    paired = intervals[intervals.model.eq("boost_minus_glm") & intervals.split.eq("test")].set_index("metric")
    reports = root / "reports/comparison"
    tails = pd.read_csv(reports / "tail_sensitivities.csv")
    segments = pd.read_csv(reports / "segments.csv")
    gain = 1 - test.loc["boost", "pure_deviance"] / test.loc["glm", "pure_deviance"]
    default = selection["decision"]["default_model"]
    clear = paired.loc["pure_deviance", "upper_95"] < 0

    def ci(model, metric, split="test"):
        r = intervals[intervals.model.eq(model) & intervals.metric.eq(metric) & intervals.split.eq(split)].iloc[0]
        return f"{r.point:.3f} [{r.lower_95:.3f}, {r.upper_95:.3f}]"

    lines = [
        "# Model comparison — Part 3", "",
        "**Business question:** Does a more flexible pricing model improve risk differentiation enough to justify its additional explanation and monitoring effort?", "",
        f"**Decision:** Use **{default.upper()} as the default for the illustrative commercial dashboard**, with GLM available for comparison. This decision was frozen on validation before test access. "
        f"On the final test, boosting reduces recorded pure-premium deviance by **{gain:.1%}** versus GLM. "
        + ("The paired sampling interval supports a reduction." if clear else "The paired sampling interval does not establish a clear reduction.")
        + " Keep GLM as the explainable benchmark. Investigate segment and large-loss behaviour before considering real repricing; these data do not support a live tariff recommendation.", "",
        "The output predicts costs represented in the linked claim table, in historical EUR per policy-year. Missing claim costs, future loss development, inflation, expenses, renewal behaviour and current premiums are outside the fitted target. Neither model predicts an ultimate technical premium.", "",
        "## Evidence on identical holdouts", "",
        "| Population / metric | Intercept | GLM | Boosting |", "|---|---:|---:|---:|",
    ]
    fields = [("frequency_deviance", "Poisson deviance / exposure"), ("severity_deviance", "Gamma deviance / claim"), ("pure_deviance", "Tweedie p=1.5 deviance / exposure"), ("pure_premium_AE", "Recorded cost actual / expected"), ("expected_per_year_eur", "Expected recorded cost / year, EUR"), ("raw_gini", "Raw exposure concentration Gini"), ("normalised_gini", "Normalised Gini"), ("top_decile_lift", "Highest-decile observed cost / portfolio cost rate")]
    for split, frame in [("Validation", validation), ("Final test", test)]:
        for field, label in fields:
            values = ["—" if pd.isna(frame.loc[model, field]) else f"{frame.loc[model, field]:.4f}" for model in ["intercept", "glm", "boost"]]
            lines.append(f"| {split}: {label} | " + " | ".join(values) + " |")
    lines.extend(["", f"Validation recorded cost is EUR {validation.loc['glm', 'actual_per_year_eur']:.2f}/year; final test recorded cost is EUR {test.loc['glm', 'actual_per_year_eur']:.2f}/year. Test contains {int(test.loc['glm', 'policies']):,} policies and {int(test.loc['glm', 'claims']):,} linked claims. Lower deviance is better; higher Gini/lift is better. An intercept has tied scores and no highest-decile lift.", "",
        "| Final-test metric: point [95% sampling interval] | GLM | Boosting | Boosting minus GLM |", "|---|---:|---:|---:|"])
    for field in ["pure_deviance", "raw_gini", "normalised_gini", "top_decile_lift", "pure_premium_AE"]:
        lines.append(f"| {field} | {ci('glm', field)} | {ci('boost', field)} | {ci('boost_minus_glm', field)} |")
    lines.extend(["", "Intervals use 250 paired, fixed-size policy bootstrap samples. Both models receive the same sampled policies; repeated claims remain with their policy. Predictions, sort orders and decile membership stay fixed. These are conditional sampling intervals, not refitting/tuning intervals, and do not cover missing costs, future drift or unidentified repeated customers. Validation intervals follow a tuning search and do not remove selection optimism. Percentile intervals are approximate for this heavy-tailed portfolio; Gini and lift gains need not have the same evidential strength as deviance gains.", "",
        "The final-test pure-deviance and raw-Gini differences have intervals on the favourable side of zero. The top-decile lift difference and severity-deviance difference include zero, so their point improvements are not established by these intervals. Higher A/E is not intrinsically better: calibration depends on distance from one.", "",
        "![Paired final-test uncertainty](figures/paired_uncertainty.png)", "",
        "![Concentration curves](figures/concentration.png)", "",
        "## Calibration and segment judgement", "",
        f"Final-test aggregate A/E is {test.loc['glm', 'pure_premium_AE']:.3f} for GLM and {test.loc['boost', 'pure_premium_AE']:.3f} for boosting. A/E above one means recorded costs exceed expected costs. No calibration multiplier was applied to either model; aggregate balance must not be inferred from the separate component fits.", "",
        "![Final-test decile calibration and intervals](figures/test_deciles.png)", "",
        "Deciles rank annual pure premium and allocate approximately equal exposure using tied-score group midpoints. Equal scores are never split, so exposure shares can differ and bins can be absent. Each model has its own deciles: same-numbered deciles are not the same policies. Actual/expected uses exposure times annual prediction in the denominator. CSVs retain policy counts, claim counts and exposure; sparse-segment flags use <100 recorded claims as a screen, not formal credibility.", "",
        "| Final-test driver age | Claims | GLM cost A/E [95%] | Boost cost A/E [95%] |", "|---|---:|---:|---:|"])
    age = segments[segments.split.eq("test") & segments.feature.eq("driver_age_band")]
    for label in sorted(age.segment.unique()):
        g = age[age.segment.eq(label) & age.model.eq("glm")].iloc[0]
        b = age[age.segment.eq(label) & age.model.eq("boost")].iloc[0]
        lines.append(f"| {label} | {int(g.recorded_claims):,} | {g.cost_AE:.3f} [{g.cost_AE_lower_95:.3f}, {g.cost_AE_upper_95:.3f}] | {b.cost_AE:.3f} [{b.cost_AE_lower_95:.3f}, {b.cost_AE_upper_95:.3f}] |")
    lines.extend(["", "Review age, region, bonus/malus and cost-table coverage together. A ratio above one is an investigation signal, not an automatic rate increase: large claims, incomplete cost reporting, selection and low volume can explain it. Lower-risk segments may warrant competitive pricing only after actual premium adequacy and retention economics are established. The GLM's 75+ A/E reverses from about 1.67 on validation to 0.70 on test; this argues against applying a simple age-group increase from one holdout. The 55–64 group has A/E below one in both holdouts, but an actual rate decrease still requires premium and commercial evidence.", "",
        "![Segment calibration](figures/test_age.png)", "",
        "## Large-loss and missing-cost sensitivities", "",
        "| Final-test scenario | Model | Cost A/E | Pure deviance | Raw Gini | Top-decile lift |", "|---|---|---:|---:|---:|---:|"])
    for r in tails[tails.split.eq("test")].itertuples():
        lines.append(f"| {r.scenario} | {r.model} | {r.cost_AE:.3f} | {r.pure_deviance:.3f} | {r.raw_gini:.3f} | {r.top_decile_lift:.3f} |")
    lines.extend(["", f"The cap is the training-only claim p99, EUR {selection['training_severity_cap_eur']:,.2f}. `outcomes_capped_at_train_p99` changes evaluated claim outcomes with fixed main-model predictions; `capped_severity_fit` changes the fitted severity target while retaining raw evaluated outcomes. These answer different questions and their deviance levels are not interchangeable. `largest_cost_policy_excluded` removes that entire policy from the fixed-model evaluation and is a post-freeze diagnostic, not a selection criterion. Main comparisons retain uncapped costs.", "",
        "`source_count_illustrative` multiplies original-count frequency by linked-record severity under an unverified representativeness assumption. It is not recovered ultimate cost. Boosting sensitivities use the selected main-model hyperparameters without retuning. The source audit records 9,116 policies with positive original counts but no cost rows, plus 195 orphan cost rows. This is material structural uncertainty even when sampling intervals are narrow.", "",
        "## Method and selection controls", "",
        "Both candidates use the same train/validation/test policies and recorded-cost target. Frequency uses annual rates and exposure weights; severity uses individual positive claims with unit weights. The baseline has 58 parameters per main GLM. Boosting uses histogram Poisson/Gamma losses with log links, four native categorical features (area, brand, fuel, region) and five continuous features (power, vehicle age, driver age, bonus/malus, log density). Preprocessing is fitted only on training policies and rejects unknown categories. ID, exposure, outcome fields and discrepancy flags never enter the rating design.", "",
        "A predeclared search tests three frequency and three severity candidates, choosing each component by its own validation deviance. Learning rate is 0.05, L2 regularisation 10, histogram bins 128 and threads two; automatic early stopping is disabled. Selected frequency parameters: " + str(selection["selected_parameters"]["frequency"]) + ". Selected severity parameters: " + str(selection["selected_parameters"]["severity"]) + ". The shallow severity model reflects the observed validation search, not a decision based on test tails.", "",
        f"The illustrative-default gate required at least 1% validation pure-deviance improvement, boosting A/E between 0.80 and 1.25, and a paired validation deviance-difference upper 95% limit below zero. Validation gain was {selection['decision']['relative_validation_deviance_gain']:.2%}; gate results: {selection['decision']['checks']}. This permissive calibration corridor is a project screening rule, not a regulatory or production standard. Model/config/code/data hashes and package versions were frozen in [selection.json](selection.json) before the final test was read; evaluation verifies the lock. Neither model was refitted on train+validation or changed after test scoring.", "",
        "Raw concentration Gini sorts ascending predicted annual risk, groups ties, and computes one minus twice the area under cumulative recorded cost versus cumulative exposure. Normalisation divides by the Gini from ordering on observed annual cost. The latter is an in-sample oracle denominator, not achievable predictive performance. Zero-cost or zero-oracle cases are undefined and exported as missing, not invented zeros. Top-decile lift compares the highest predicted-risk bin's observed annual cost with the entire portfolio's observed annual cost; it differs from the separately exported top/bottom ratio.", "",
        "Implementation reference: [scikit-learn HistGradientBoostingRegressor](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html). [tuning.csv](tuning.csv) records every candidate and local fit time; [prediction_timings.csv](prediction_timings.csv) records inference time for policy and claim rows, including encoding. Timings are environment-specific, not a production latency guarantee.", "",
        "## Explanation and business trade-offs", "",
        "![Validation explanation diagnostics](figures/explanations.png)", "",
        "Permutation importance is the increase in pure-premium deviance when one input is shuffled on a seeded 20,000-policy validation sample, with three repeats. Standard deviation measures shuffle variation, not confidence in the causal effect. The age response changes driver age for every risk in a seeded 2,000-policy validation sample, regenerates GLM bands, and averages predictions. Correlated features, implausible age/bonus combinations, sparse extremes and interactions limit both diagnostics. These plots are model explanations, not causal pricing effects or calibrated portfolio quotes.", "",
    ])
    profiles = pd.read_csv(reports / "profile_examples.csv")
    lines.extend(["Six fixed hypothetical profiles illustrate disagreements without using test outcomes or exposing source policy rows. All use area C, brand B1, Diesel, region R24, vehicle age 5, power 6 and density 1,000. EUR figures are annual recorded-cost predictions, not current quotes; combinations may be sparse or implausible. BM means bonus/malus.", "",
                  "| Profile | GLM annual EUR | Boost annual EUR | Boost / GLM |", "|---|---:|---:|---:|"])
    for r in profiles.itertuples():
        lines.append(f"| {r.profile} | {r.glm_pure_premium_eur:.2f} | {r.boost_pure_premium_eur:.2f} | {r.boost_to_glm_ratio:.2f} |")
    lines.extend(["", "These are model response illustrations rather than evidence of causal age or claim-history effects. Material disagreements are a reason to compare scenario results and monitor stability.", "",
        "| Pricing consideration | GLM | Boosting |", "|---|---|---|",
        "| Interpretation | Explicit multiplicative factors and references; fixed age bands | Nonlinear interactions; permutation/response diagnostics add explanation effort |",
        "| Measured fit | Transparent benchmark; final-test evidence above | Better fit only to the extent supported by the measured holdout evidence |",
        "| Stability | Coefficients and residuals can be monitored; misspecified bands can hide patterns | Predictions can be uneven across sparse inputs; monotonicity is not imposed |",
        "| Governance / acceptance | Familiar documentation aids review; no automatic acceptance | Requires additional stability, permitted-variable, fairness and explanation review; no automatic acceptance |",
        "| Operations | Fast, compact scoring; refit and calibration still need control | More trees and preprocessing; versioned artefacts, prediction monitoring and fallback needed |", "",
        "**Business recommendation:** In Part 4, compare both models under identical assumed baseline premiums, rate changes, inflation and retention elasticity. Prioritise investigation of persistent segment inadequacy that survives tail sensitivity and has sufficient volume. Use scenario contribution and retained volume to bound proposed changes; do not report simulated profit as achieved savings. Before live use, obtain complete developed claims, current premiums, renewal outcomes, expense economics, time/customer validation and jurisdiction-specific governance review. Historical French liability factors cannot establish current Australian motor or home rates.", "",
        "Reproduce with `insurance-pricing train-boost` followed by `insurance-pricing evaluate` after Part 2 training. Repeat evaluation with the frozen bundles to regenerate metrics; do not retune on the reported test. Local row-level predictions and bundles are ignored by Git. Aggregate evidence and five PNG/vector PDF figure pairs are committed; regenerate plots with `PYTHONPATH=src .venv/bin/python figures/gen_fig_comparison.py`.", "",
    ])
    return "\n".join(lines)


def plot_comparison(root: Path):
    os.environ.setdefault("MPLCONFIGDIR", str(root / "artifacts/matplotlib-cache"))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.family": "serif", "font.serif": ["DejaVu Serif"], "font.size": 10,
                         "axes.titlesize": 12, "axes.titleweight": "bold", "axes.spines.top": False,
                         "axes.spines.right": False, "axes.grid": True, "grid.alpha": .15,
                         "legend.frameon": False, "pdf.fonttype": 42, "savefig.dpi": 300})
    reports = root / "reports/comparison"
    figures = reports / "figures"
    figures.mkdir(exist_ok=True)
    colors = {"glm": "#0072B2", "boost": "#D55E00"}

    def save(fig, name):
        fig.savefig(figures / f"{name}.pdf", bbox_inches="tight")
        fig.savefig(figures / f"{name}.png", bbox_inches="tight", dpi=300)
        plt.close(fig)

    curves = pd.read_csv(reports / "concentration_curves.csv")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), layout="constrained")
    for ax, split in zip(axes, ["validation", "test"]):
        for model in colors:
            r = curves[curves.split.eq(split) & curves.model.eq(model)]
            ax.plot(r.exposure_share, r.cost_share, color=colors[model], label=model.upper())
        ax.plot([0, 1], [0, 1], color=".5", ls=":", label="Equal cost rate")
        ax.set(xlim=(0, 1), ylim=(0, 1), xlabel="Cumulative exposure (ascending predicted risk)", ylabel="Cumulative recorded cost", title=split.title())
        ax.legend()
    save(fig, "concentration")

    deciles = pd.read_csv(reports / "deciles.csv")
    fig, axes = plt.subplots(2, 2, figsize=(10, 7), sharey="row", layout="constrained")
    for j, model in enumerate(colors):
        r = deciles[deciles.split.eq("test") & deciles.model.eq(model)]
        axes[0, j].plot(r.decile, r.actual_per_year_eur, "o-", color="#009E73", label="Recorded actual")
        axes[0, j].plot(r.decile, r.expected_per_year_eur, "s--", color=colors[model], label="Expected")
        axes[0, j].set(title=f"Final test: {model.upper()}", ylabel="Cost / policy-year (EUR)")
        axes[0, j].legend()
        axes[1, j].vlines(r.decile, r.cost_AE_lower_95, r.cost_AE_upper_95, color=colors[model], lw=1.5)
        axes[1, j].plot(r.decile, r.cost_AE, "o", color=colors[model], label="Cost A/E; 95% sampling interval")
        axes[1, j].axhline(1, color=".5", ls=":")
        axes[1, j].set(xlabel="Model-specific risk decile (equal exposure approx.)", ylabel="Recorded actual / expected")
        axes[1, j].legend(fontsize=8)
        for ax in axes[:, j]:
            ax.set_xticks(np.arange(1, 11))
    save(fig, "test_deciles")

    intervals = pd.read_csv(reports / "paired_intervals.csv")
    paired = intervals[intervals.split.eq("test") & intervals.model.eq("boost_minus_glm")].set_index("metric")
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.6), layout="constrained")
    for ax, metric, title in zip(axes, ["pure_deviance", "raw_gini", "top_decile_lift"], ["Pure deviance (lower is better)", "Raw Gini (higher is better)", "Top-decile lift (higher is better)"]):
        r = paired.loc[metric]
        ax.hlines(0, r.lower_95, r.upper_95, color=colors["boost"], lw=3)
        ax.plot(r.point, 0, "o", color=colors["boost"])
        ax.axvline(0, color=".4", ls=":")
        ax.set(yticks=[], ylim=(-.5, .5), xlabel="Boosting minus GLM", title=title)
    save(fig, "paired_uncertainty")

    segments = pd.read_csv(reports / "segments.csv")
    age = segments[segments.split.eq("test") & segments.feature.eq("driver_age_band")]
    levels = sorted(age.segment.unique())
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), layout="constrained")
    for model, shift in [("glm", -.12), ("boost", .12)]:
        r = age[age.model.eq(model)].set_index("segment").loc[levels]
        x = np.arange(len(r)) + shift
        axes[0].vlines(x, r.cost_AE_lower_95, r.cost_AE_upper_95, color=colors[model], lw=1.5)
        axes[0].plot(x, r.cost_AE, "o", color=colors[model], label=model.upper())
    axes[0].axhline(1, color=".5", ls=":")
    axes[0].set_xticks(np.arange(len(levels)), levels, rotation=30)
    axes[0].set(title="Final test: age calibration with 95% intervals", ylabel="Recorded cost actual / expected")
    axes[0].legend()
    g = age[age.model.eq("glm")].set_index("segment").loc[levels]
    axes[1].bar(np.arange(len(g)), g.recorded_claims, color="#009E73", width=.65)
    axes[1].set_xticks(np.arange(len(levels)), levels, rotation=30)
    axes[1].set(title="Linked claim volume by driver age", ylabel="Recorded claims")
    save(fig, "test_age")

    importance = pd.read_csv(reports / "permutation_importance.csv").sort_values("mean_deviance_increase")
    effects = pd.read_csv(reports / "driver_age_partial_dependence.csv")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.3), layout="constrained")
    axes[0].barh(importance.feature, importance.mean_deviance_increase, xerr=importance.repeat_std, color=colors["boost"])
    axes[0].axvline(0, color=".5", ls=":")
    axes[0].set(title="Boosting: validation permutation importance", xlabel="Pure-deviance increase (± shuffle SD)")
    for model in colors:
        r = effects[effects.model.eq(model)]
        axes[1].plot(r.driver_age, r.mean_pure_premium_eur, "o-", color=colors[model], label=model.upper())
    axes[1].set(title="Age response: fixed validation risk sample", xlabel="Hypothetical driver age", ylabel="Mean annual pure premium (EUR)")
    axes[1].legend()
    save(fig, "explanations")
