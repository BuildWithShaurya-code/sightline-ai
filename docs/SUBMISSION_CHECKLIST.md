# Repository and submission release checklist

The production release is live and verified. Owner-supplied team/demo material and unmeasured evaluation remain open; see VERIFICATION.md for the release evidence.

## Prepared

- [x] README describing the actual local implementation and limitations.
- [x] Setup, architecture in README, model card, verification, operations and demo guidance.
- [x] HYPNEXIS-specific PPT outline and honest contribution record.
- [x] Commit-pinned GitHub CI configuration without production secrets; local equivalent checks verified.
- [x] Guarded Vercel frontend configuration and a private-source export allowlist.
- [x] Local worker recovery/admission, cancellation protections and offline backup/restore.

## Required before public publication / submission

- [ ] Confirm event reuse/AI/pretrained-model rules and final problem fit.
- [ ] Confirm application license, model/data/footage rights and required third-party notices.
- [ ] Add actual team/contributor details, demo recording and verified links.
- [x] Review the export manifest and scan the final tracked Git files/history; do not push the entire Downloads folder.
- [x] Publish the intended public GitHub repository and verify its clean Linux CI run: both jobs passed for `eaf3afa` ([run](https://github.com/BuildWithShaurya-code/sightline-ai/actions/runs/39281684819)).
- [ ] Supply private authorized model/fixtures for full-suite reproduction through an agreed channel.
- [ ] Submit the actual PPT/project through the organizer portal. Nothing has been submitted by this task.

## Required before claiming hosted readiness

- [x] All-Vercel frontend/identity/inference services and analysis daemon with private Supabase database/storage.
- [ ] Verify a Linux clean image, cold start, HTTPS/CORS, upload limits, memory and queue/load behavior.
- [x] Verify two disposable real accounts and cloud table/private-storage ownership on the deployed configuration.
- [ ] Test real notification acceptance/delivery only with an authorized test recipient.
- [ ] Test durable database/media recovery and rollback on the final host.
- [x] Publish a new evidence record and distinguish remaining gaps from successful tests.
