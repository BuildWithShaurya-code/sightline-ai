# GitHub and deployment

The cloud implementation now uses Vercel for the frontend, API container and independent analysis daemon, with Supabase PostgreSQL and private object storage. See [the authoritative cloud runbook](CLOUD_DEPLOYMENT.md). The local SQLite implementation is retained for rehearsal and development. Historical frontend-only deployment advice has been superseded by this migration.

Live app: https://sightline-ai-eight.vercel.app

Repository: https://github.com/BuildWithShaurya-code/sightline-ai

## Prepare GitHub safely

1. Review the prepared README, setup, model card, security notes and submission record. Add the actual team/contributors, demo link and a consented, redacted walkthrough when available. Do not invent badges, stars, accuracy, customers or a live URL. GitHub recommends explaining what the project does, why it helps and how to use it. [README guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes).
2. Decide repository visibility and application/model licensing with the owner. Confirm dataset/footage rights and the event’s reuse rules. Private checkpoint exclusion is not a substitute for a licensing decision.
3. Create a review package from the project root:

   ```sh
   python3 scripts/export_review_package.py --output /path/to/new/sightline-github-review
   ```

   The output must be a new directory. It is a curated source copy: no real `.env`, weights, uploads, local databases, historical screenshots or private QA data. Review `PACKAGE_MANIFEST.json` before publishing.
4. Create an empty GitHub repository in your chosen account. Initialize Git only in that reviewed copy, make a truthful initial commit, add the actual remote and push. Do not rewrite commit dates or pretend the existing prototype was created during the event. Publish only to the owner-approved repository and retain the real contribution history.
5. Enable repository protections appropriate to the account: review pull requests, require the two prepared CI jobs, protect the main branch from force pushes, enable available secret scanning/push protection and private vulnerability reporting. These settings have not been changed by this task.
6. Add a short repository description and topics such as `computer-vision`, `fastapi`, `react`, `supabase`, `human-in-the-loop` and `hackathon`. Create a `v0.1.0-demo` release only after a fresh-clone test and the event’s rules permit it. Include verified scope and known gaps in its notes.

## CI and verification

`.github/workflows/ci.yml` uses read-only repository permissions, commit-pinned official actions, cancellation of redundant runs and timeouts. It has no deploy or production-secret step. Forked PRs run ordinary checks; they do not get provider credentials or private models. [GitHub workflow security](https://docs.github.com/en/actions/reference/security/secure-use), [Actions secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets).

The frontend job installs the lockfile, checks types/build, runs 8 source/rendering scripts, validates Vercel configuration logic and checks the curated package. The backend job installs declared dependencies and runs the 68 model-free security/contract tests. See the repository Actions tab for current runs. A workflow file alone is not evidence of a passing run. The full private-model pipeline, real accounts, cloud policies and actual delivery remain separate release gates. Do not label a passing public CI job “all integration tests passed.”

Dependabot configuration proposes dependency/action updates weekly. Its server-side operation starts only after an eligible repository is published/configured. Review dependency changes rather than merging blindly during the demo.

