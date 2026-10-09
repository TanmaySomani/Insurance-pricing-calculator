# Free public dashboard deployment

Prepared on 9 October 2026. Host: **Streamlit Community Cloud**, a free service for publicly sharing community apps. This is a historical public-data portfolio demonstration. Its resource limits and hibernation make it suitable for visitors testing the case study, without a production availability promise.

**Status: repository prepared; account sign-in and actual deployment still required.** A proposed subdomain is not a live app. Add the verified public URL to README only after the app is deployed and checked.

## Deploy from GitHub

1. Sign in at [share.streamlit.io](https://share.streamlit.io/). The account owner should review and accept any terms and GitHub authorisation prompts. Connect the public repository; this demo does not need private-repository access or application secrets.
2. Select **Create app**, then the existing-app option. Use:

   | Setting | Value |
   |---|---|
   | Repository | `TanmaySomani/Insurance-pricing-calculator` |
   | Branch | `main` |
   | Main file path | `app.py` |
   | Python version (Advanced settings) | `3.14` |
   | Secrets | None required |
   | Visibility | Public |

3. Optional: request subdomain `insurance-pricing-calculator` if the form reports it available. Otherwise choose an available name. Community Cloud supplies an HTTPS `streamlit.app` URL; do not link an unverified guessed address.
4. Deploy, inspect build logs, and wait for the actual dashboard. `requirements.txt` includes the existing pinned `requirements.lock.txt`; do not loosen versions or use the platform's default interpreter to bypass an install failure. `app.py` loads the repository's source directly, so no editable install or CLI training is needed on the host.
5. Verify the checklist below and add the exact working public URL to README. Share that URL with visitors; localhost only works on the computer running the local server.

## What visitors can test

Rate scenarios, portfolio evidence, model comparison, segment diagnostics and saved JSON/CSV scenarios work from the committed aggregate tables. Users can change rates, retention, elasticity, inflation and expenses; add segment rules and named stresses; compare claims models at a fixed price anchor; and download/reload scenarios. Saved entries belong to each browser session; download JSON for durable storage.

The individual Risk calculator page explains the full local setup requirement. Its fitted models and matching prepared policy/claim tables are intentionally absent from GitHub. Do not upload these records or bypass the current verifier simply to make that page score on the host. A full hosted calculator requires a separately reviewed serving-artefact plan. The public aggregate demo does not retrain, download source data or access visitors' insurance records.

## Verify after deployment

- Open the real public URL in a logged-out browser and confirm it is accessible without a viewer invite.
- At final-test cohort, boosting claims model, GLM price anchor and default assumptions: baseline contribution EUR 5.27m and retained volume 114,959. Set +5%: contribution EUR 6.28m and retained volume 108,422.
- Switch the claims model with the anchor fixed: premium and retention must stay unchanged.
- Add/edit a segment rule, add a severity stress, and check that invalid inputs show a usable message. Saved JSON reload must recompute its results; incompatible fingerprints must be rejected.
- Visit all six pages, including the Risk calculator's setup state. Confirm the model evidence renders and the PDF/source links in the repository work.
- Inspect host logs and memory/resource behaviour with a few simultaneous visitors. Local warm timing does not establish cloud response time or load capacity.
- Record the deployed commit, public URL, interpreter and observed checks. Before declaring deployment complete, verify the actual website, not just the platform's build status.

## Free-service behaviour and maintenance

The official documentation states that apps without traffic for 12 hours sleep. A visitor with access can wake the app using the platform's button. Session state may be lost across restarts/hibernation. GitHub updates to the selected branch can update the hosted app, so keep the code and checked aggregate identity together. There are no recurring hosting automations, keep-alive pings or paid services configured here.

For problems, first read the Community Cloud logs. Verify Python 3.14 and the pinned dependency install, then the aggregate checksums. Keep `.streamlit/config.toml` protections at their defaults; no CORS/XSRF bypass or localhost tunnel is required. If current platform support differs from the docs, report the actual limitation and validate a deliberate alternative runtime instead of silently changing model versions.

Sources checked 9 October 2026: [free Community Cloud](https://streamlit.io/cloud), [deployment and interpreter selection](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy), [dependency file discovery](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies), [GitHub connection](https://docs.streamlit.io/deploy/streamlit-community-cloud/get-started/connect-your-github-account), [hibernation and resources](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app). Broader artefact and rollout limits remain in [DEPLOYMENT.md](DEPLOYMENT.md).
