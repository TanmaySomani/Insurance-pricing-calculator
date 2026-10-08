# Dashboard specification — planned for Part 4

Purpose: allow a pricing manager to understand risk segmentation and test how pricing assumptions change expected retention, portfolio mix, and underwriting contribution. Every scenario must identify which values are observed, modelled, or assumed. No commercial outputs are implemented in Part 1.

## Pages and decisions

| Page | Manager's question | Planned content |
|---|---|---|
| Portfolio | What is this book, and how reliable are the data? | Exposure, claims, recorded cost, source completeness, tail concentration, dataset/version labels |
| Model comparison | Which model supports our pricing decision? | GLM/boosting calibration, lift, Gini with uncertainty, deciles, diagnostics and trade-offs |
| Segments | Where do rates warrant investigation? | Credibility-aware A/E, modelled expected costs, claim counts and missing-cost coverage; scenario loss ratios separately labelled |
| Rate scenarios | What happens if we change rates or assumptions? | Editable controls/table, baseline comparison, retention, volume, premium, claims, expense and contribution |
| Risk calculator | How do risk factors affect an example quote? | Rating inputs, annual frequency/severity/pure premium, commercial loading, model explanation |

Use Python + Streamlit + Plotly, with reusable numerical functions outside the UI. Load pre-trained model artefacts; changing a commercial slider must not refit the models or query OpenML. Cache immutable data/model inputs while recomputing scenario arithmetic on each edit. Performance acceptance: common assumption edits should update in approximately one second on a documented reference machine after initial loading; measure this before claiming it.

## Editable inputs

- Selected fitted model: GLM or boosting.
- Global rate change and one-dimensional segment adjustments.
- Assumed baseline retention, price elasticity and segment-specific overrides.
- Claim-cost inflation, variable expense ratio, fixed annual expense, and target contribution margin.
- Optional expense/frequency/severity stress multipliers, explicitly scenario overrides rather than new fitted coefficients.
- A capped change corridor to constrain suggested rate moves.

An editable table lets the user add/remove rows containing segment field, segment value, rate adjustment and optional elasticity. MVP adjustments use **one selected segmentation field**, with at most one row per level, avoiding ambiguous overlapping rules. Unknown levels and duplicate rules should be rejected. Global and segment changes combine multiplicatively. Changing the segmentation field resets its table after a clear UI notice. Scenario names, all inputs, model/source version and outputs can be exported as JSON/CSV and reloaded for comparison.

New assumptions can be represented as configured stress multipliers with clear labels. A genuinely new rating feature needs observed training data, a transformation, refitting and validation; it cannot acquire a learned effect merely by adding a text field. The quote calculator must constrain rating inputs to supported ranges and show warnings for extrapolation or unseen categories.

## Commercial simulation contract

All commercial values below are assumptions or model estimates. This dataset contains no historical premium or renewal observation. The future simulation assumes one annual renewal opportunity per policy; original exposure is for historical model evaluation, not the forecast horizon. Default assumption values must be reviewed in Part 4 and never described as estimated from freMTPL2.

For policy `i`, let `L_i` be selected annual modelled recorded loss cost, `v` variable expense share, `f` fixed annual policy expense, and `m` desired contribution margin. Construct an **illustrative** annual baseline premium:

```text
P0_i = (L_i + f) / (1 - v - m)
P1_i = P0_i * (1 + global_change) * (1 + segment_change_i)
relative_change_i = P1_i / P0_i - 1
q1_i = clip(q0_i * (P1_i / P0_i) ** (-elasticity_i), 0, 1)
L1_i = L_i * (1 + claims_inflation) * loss_stress_multiplier_i
```

Require `L_i > 0`, `f >= 0`, `v >= 0`, `m >= 0`, `v + m < 1`, `q0` in [0,1], nonnegative elasticity, price multipliers strictly positive and finite, inflation above -100%, and positive finite stress multipliers. Rate corridors apply to the combined relative change. Zero elasticity means no price response; zero change leaves retention at baseline; discounts may raise retention but never above 100%.

For an annual renewal cohort, with optional nonnegative representative policy weights `w_i` defaulting to one:

```text
Expected retained policies = sum(w_i * q1_i)
Expected annual premium     = sum(w_i * q1_i * P1_i)
Expected annual claims      = sum(w_i * q1_i * L1_i)
Expected annual expenses    = sum(w_i * q1_i * (v * P1_i + f))
Underwriting contribution   = premium - claims - expenses
Scenario loss ratio         = claims / premium
Scenario combined ratio     = (claims + expenses) / premium
```

Apply the same claims inflation/stress to baseline and changed-price comparisons to isolate the effect of rates. Separately allow comparison against an unstressed baseline, with labels explaining the difference. The simulation assumes retained risks have their modelled loss costs; risk-dependent retention is captured only through entered segment assumptions. It does not estimate unobserved anti-selection, competition, new business, price optimisation causality, taxes, investment income, reinsurance, capital costs or ultimate development.

“Volume” means expected retained annual renewal policies in this cohort; it does not mean new sales. “Profit” in the UI should be labelled **expected underwriting contribution**, with its expense basis visible. A historical observed loss ratio must not be fabricated. Where a synthetic premium is used, display **scenario loss ratio**. Historical actual/expected claim calibration uses actual recorded costs and model predictions and belongs on the diagnostics page.

## Outputs and guardrails

Show side-by-side baseline/scenario KPIs and absolute/percentage changes, a rate-versus-retention/contribution sensitivity curve, segment impacts, and a downloadable scenario snapshot. No denominator-zero ratios, NaNs, negative premiums, silent caps, or invalid economic assumptions may reach the display. Thin segments and missing-cost coverage must remain visible beside apparent repricing opportunities.

Recommendation text should identify a bounded option and its sensitivity to elasticity and claims assumptions. It must not imply that an assumed elasticity was empirically estimated or that the maximum of a scenario curve is a proven optimal rate.

## Part 4 acceptance checks

- Baseline zero-change identities and zero-elasticity behaviour reconcile independently.
- Weighted sums reconcile to segment/portfolio KPIs; discounts and retention bounds behave correctly.
- Invalid rate/expense combinations and duplicate segment rules are rejected.
- Adding a supported segment row updates the relevant risks and aggregate impact live.
- Saved/reloaded scenarios reproduce all inputs and outputs for the same model/source versions.
- Model/risk calculators cannot use ID, outcome or exposure as a learned rating feature.
- Empty filters, unseen levels, small claim counts and extrapolated risks show usable states.
- Commercial outputs clearly distinguish assumptions from observed and modelled values.
