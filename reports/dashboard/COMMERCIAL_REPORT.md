# Commercial scenario evidence — Part 4

**Business question:** How does a rate move trade expected underwriting contribution against retained renewal volume?

**Recommendation:** Investigate a modest +5% option, conditional on actual premium adequacy and measured renewal response. Do not roll it out from this case study. Under assumed elasticity 1.2 it adds approximately EUR 1.02m contribution but loses 6,537 expected retained policies; under elasticity 6 it loses approximately EUR 0.30m contribution and 29,175 policies. This sensitivity makes renewal evidence essential.

All figures below are simulated, in historical EUR. They use the 135,246 final-test policies as one assumed annual renewal opportunity each, the frozen boosting recorded-cost model, and the same GLM synthetic price anchor. They are not forecasts validated against observed renewals or achieved savings.

## Declared assumptions

Baseline retention 85%; elasticity 1.2 unless shown; no claims inflation unless shown; variable expense 25% of premium; EUR 30 annual fixed expense per retained policy; baseline price margin 10%; combined rate corridor −20% to +20%. Synthetic annual price is (GLM model loss + EUR 30) / 0.65. Baseline and changed-price cases use identical claims stress; changing elasticity does not change baseline retention or premiums.

## Rate and response comparisons

| Case | Elasticity | Claims inflation | Retained policies | Premium EUR m | Contribution EUR m | Contribution delta vs same-stress baseline EUR m | Retained delta | Scenario LR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 1.2 | 0% | 114,959 | 37.19 | 5.27 | +0.00 | +0 | 51.6% |
| Plus 5 percent | 1.2 | 0% | 108,422 | 36.83 | 6.28 | +1.02 | -6,537 | 49.1% |
| Plus 5, elasticity 3 | 3.0 | 0% | 99,306 | 33.74 | 5.76 | +0.49 | -15,653 | 49.1% |
| Plus 5, elasticity 6 | 6.0 | 0% | 85,784 | 29.14 | 4.97 | -0.30 | -29,175 | 49.1% |
| Plus 5, inflation 10 percent | 1.2 | 10% | 108,422 | 36.83 | 4.48 | +1.12 | -6,537 | 54.0% |

For the homogeneous +5% rate experiment, contribution breaks even with its baseline around elasticity **4.81**, holding all other assumptions fixed. This is a property of the entered economics, not an estimated market elasticity or a recommended price optimum.

Revenue can fall despite a higher rate because retention falls. Claims and per-policy fixed expenses also fall with retained volume. With 10% claims inflation, contribution is lower in absolute terms even though the rate-only delta improves relative to a baseline under the same inflation. Comparing it with an unstressed baseline answers a different question and is explicitly labelled in the UI.

## Segment judgement

Use historical held-out A/E and coverage to choose investigations, then compare commercial scenarios. The 55–64 age group has recorded-cost A/E below one in both holdouts, so premium competitiveness may merit investigation. It is not proof that a discount is profitable: baseline premiums and renewal outcomes are unavailable, and a discount may reduce contribution.

Do not apply a broad age-75+ increase from the validation A/E. GLM calibration reverses between validation and test, and cost coverage is incomplete. Review developed claims, large losses, premium adequacy and stability before action. The dashboard keeps claim volume/coverage beside scenario segment effects and retains GLM as a benchmark.

## Verification and live controls

The independent policy-level reconciliation applies +5% globally and −3% to age 55–64, with that segment's elasticity set to 2. Direct calculations over all 135,246 policy predictions agree with exact aggregate engine totals to relative tolerance 1e-12. Historical exposure is not used as a renewal weight. Both model bundles and the Part 3 selection record stayed unchanged.

Local checks: 72 tests pass. Six warm Python-side reruns measured p95 0.143s; the scenario plus 21-point curve measured p95 0.119s. A warm browser slider edit reached a visible KPI in 0.364s, including automation overhead. JSON upload/reload reproduced the +5% scenario in the live browser. These are local warm measurements, not cold-start or hosting guarantees.

Editable segment rows support extra rate changes and optional response overrides. Named stress rows add assumed frequency/severity/loss multipliers; they do not add learned rating coefficients. Saved scenarios carry checked source/model/engine identity. Uploaded outputs are ignored and recomputed. Invalid assumptions, empty filters, duplicates, unsupported categories and stale versions have usable states.

[Dashboard walkthrough](../../docs/DASHBOARD_USAGE.md) · [Example scenarios CSV](example_scenarios.csv) · [Verification](verification.json) · [Version manifest](manifest.json)

## Limitations and next decision

Missing claim costs remain structural uncertainty, and the source is historical French liability. Claims development, current price levels, customer/time validation, actual renewal response, taxes, capital, reinsurance and unmodelled anti-selection are absent. Scenario LR uses synthetic premiums; no historical observed LR is fabricated. The expense basis assumes fixed costs are per retained policy, not book-level overhead. Portfolio filtering supports one selected segmentation dimension, without overlapping cross-field rules.

Before real repricing, obtain complete developed claims, actual current premiums, renewal and competitor evidence, credible expense economics and applicable governance review. Part 5 will turn this into the final two-page manager brief and handover, with deployment packaging reviewed separately.

![Live rate scenario](screenshots/rate-scenario.jpg)
