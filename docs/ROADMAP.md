# Delivery roadmap

The project is delivered in five bounded parts, each ending with a tested, documented checkpoint. A new chat can resume from `CHECKPOINT.md` without reconstructing decisions from the conversation.

## Part 1 — Data and foundations (complete)

Public-source research, OpenML snapshots and checksums, policy/claim join audit, exposure rules, target reconciliation, fixed feature engineering, deterministic splits, regression checks, reproducible commands, CI definition and GitHub-ready documentation.

Exit evidence: a full local preparation run on the pinned data; policy count and costs reconcile to linked claim records; tests pass. Part 1 established the foundation; fitted GLMs were added in Part 2.

## Part 2 — Interpretable pricing baseline (complete)

Implement Poisson frequency and Gamma severity GLMs, annual pure-premium multiplication and intercept-only benchmarks. Fit preprocessing only on train. Make source-count frequency a separately labelled sensitivity. Export model artefacts, coefficient relativities, validation predictions, calibration, dispersion and residual diagnostics. Keep uncapped recorded costs as the main target; quantify tail sensitivity without tuning on test.

Exit evidence: frozen feature/target definitions, converged fits, positive finite predictions, exposure-aware comparisons, aggregate and segment A/E, source-count versus recorded-count explanation, independently checked predictions and repeatable training commands.

Delivered: six converged fits, train/validation artefacts and metadata, intercept comparison, reference-factor tables, deciles/segment diagnostics, portfolio policy-bootstrap calibration intervals, source-count/complete-count/p99-cap sensitivities, residuals/Fisher influence checks, four figure pairs and 32 passing tests. The final test has not been scored. See `reports/glm/GLM_REPORT.md`.

## Part 3 — Boosting and model selection (next)

Train a frequency/severity boosting challenger on identical populations and splits; document a small validation-only tuning search. Compare deviance, exposure-weighted lift, raw/normalised Gini, decile A/E and relevant segment calibration. Include policy bootstrap uncertainty and large-loss sensitivity. Freeze both candidates before final test reporting. Summarise interpretability, governance effort, stability, computational cost and measured lift.

Exit evidence: reproducible comparison tables/charts, correctly handled exposure/ties, model/version metadata, test results and a supported model-use recommendation. No promise that boosting must win.

## Part 4 — Commercial engine and dashboard

Implement and verify the numerical contract in `DASHBOARD_SPEC.md`. Build Streamlit pages with pre-trained artefacts, live controls, editable segment rows, saved scenarios and exports. Validate assumptions, arithmetic, zero-change identities and interaction paths. Show which segment rate investigations remain reasonable under conservative elasticity/claims assumptions.

Exit evidence: running local dashboard, measured interaction performance, scenario reconciliation and useful manager-facing recommendations with visible limitations. Hosting can be arranged once tested.

## Part 5 — Client handover

Create a clean final README, verified two-page PDF written for a nontechnical pricing manager, an example scenario walkthrough and screenshots. Lead with the business question, bounded recommendation, evidence and risks. Include model cards, data provenance, reproducible setup, dashboard instructions and a complete handover checkpoint. Validate document page count/readability and dashboard deployment configuration. Publish verified deliverables to the specified GitHub repository.

Optional Australian context follows the core work. Verify APRA/ICA/BOM data and licensing, analyse aggregate changes and explain implications for uncertainty, inflation or catastrophe risk without transferring French rating factors to Australia.

## Checkpoint discipline

At the end of each part update implementation status, execution commands, test evidence, outputs, known limitations and an exact next prompt. Record package/config/source changes. Keep raw data and model binaries out of Git unless a deliberate small distribution plan is added. Never claim client readiness before the final quality review.
