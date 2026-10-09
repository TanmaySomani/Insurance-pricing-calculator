# Deployment review and packaging

**Delivery status:** Verified local dashboard and aggregate-demo package. Public hosting is not configured or claimed. No host account, authentication, domain, uploaded model binaries or hosting costs were provisioned in Part 5.

## Free-hosting preparation (9 October 2026)

Streamlit Community Cloud deployment files and a step-by-step [hosting guide](HOSTING.md) are prepared. The root `requirements.txt` includes the pinned application lock, and CI installs through that same entry point. Use `main`, `app.py`, Python 3.14 and no secrets. Account sign-in/terms and GitHub connection remain with the account owner; actual hosting and a public URL are not claimed. A hosted aggregate demo is the recommended initial showcase. The full-scoring requirements below remain unchanged.

## Supported delivery modes

| Mode | What is available | What the recipient needs |
|---|---|---|
| Repository / aggregate ZIP | Scenario, portfolio, comparison, segment and saved-scenario pages; risk page explains missing artefacts | Python 3.14 verified environment and locked dependencies; no raw data or models |
| Full local reconstruction | Above plus hypothetical individual risk scoring | Run the fixed data/training/evaluation/aggregate stages in order |
| Future hosted aggregate demo | Same aggregate behaviour as a clean checkout | Deliberate host/runtime selection, install/start/health checks and access policy; not deployed |
| Future hosted full calculator | Hypothetical frozen individual predictions | Trusted compatible bundles **and** matching prepared policy/claim tables/config/code/runtime; separate data/artefact distribution decision |

No standalone wheel-only deployment is claimed: the app expects the repository tree, source files, configs and checked reports. `scripts/package_client.py` packages that tree using an explicit allowlist and per-file SHA-256 manifest. `dist/` stays Git-ignored. The ZIP never contains source policy records, pickle/joblib files or secrets.

## Startup contract

Use [the handover install commands](CLIENT_HANDOVER.md). Default demonstration binds `127.0.0.1:8502`. For a selected host, pass its approved address/port to Streamlit at launch; use its reverse proxy/TLS/access controls. Do not expose the local app by merely changing the bind address. Leave CORS/XSRF protections at their defaults. The app is a research demo, with no built-in user authentication or production quote API.

Health probe: `GET /_stcore/health` should return `ok`. Then exercise a +5% change, model switch with fixed anchor, saved JSON reload and all six pages. A green health response alone does not validate the evidence or calculations. Run `scripts/verify_handover.py` in the selected environment before release.

The local evidence uses CPython 3.14.7 and `requirements.lock.txt`; optional PDF generation uses `requirements-report.txt`. Other operating systems/interpreters need their own clean installation and checks. No Docker image, Linux host smoke test or cloud capacity benchmark is claimed. A selected hosting platform must support all pinned dependency versions; do not silently loosen them to get a deployment through. [Streamlit deployment guidance](https://docs.streamlit.io/deploy) describes the hosting options; no particular plan or availability is assumed here.

## Artefact integrity and portability

Scenario aggregate identity checks engine version/hash, frozen model-selection digest and table hashes. Code/data changes require deliberate versioning and rebuilding. Uploaded files are size-limited JSON assumptions; duplicate keys, unsupported schemas/fields, non-finite values and foreign fingerprints are rejected. Outputs are always recomputed. Browser-session saves are not durable storage; users must download files. Local warm timing (about 0.36s for one observed browser KPI update) is not a hosted service target.

The individual calculator's current `verify_selection` additionally checks `data/processed/policies.parquet` and `claims.parquet`, both model binaries, model/data configs, modelling source and exact package versions before loading joblib. Uploading only two bundles will fail. A full service must either provision that entire trusted verified set through a controlled channel, or implement and validate a separately versioned serving-only manifest. The latter is not implemented. Prepared tables contain source policy-level records, so prefer aggregate hosting until the distribution/access decision is made.

Joblib uses pickle-based persistence and requires a trusted source. Do not accept user-uploaded models or relax version guards. See [scikit-learn's model persistence documentation](https://scikit-learn.org/stable/model_persistence.html). SHA-256 comparison protects against unintended changes relative to the trusted checkout; it is not a signature or source authentication.

## Release and rollback

Release the Git commit, application lock, source lock, selection record, aggregate manifest, PDF manifest and verification together. The package manifest covers packaged file contents. Re-run tests and no-model checkout verification after changes; inspect the two PDF pages after prose/layout edits. Review the CI run for the published commit separately. Back up downloaded scenario JSON before replacing evidence: foreign fingerprints are rejected rather than silently migrated.

Rollback means restore the previous complete release tree and matching dependencies/artefacts, then verify it. Preserve the five example scenarios and manifest for comparison. No training, downloads or model selection may occur in the user interaction path. Real customer pricing requires the data and review steps in the model cards and manager brief, beyond this deployment review.
