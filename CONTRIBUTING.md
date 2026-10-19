# Contributing

Read `AGENTS.md` and the current setup and verification documents first. Use a feature branch and a pull request with a concrete before/after description and actual test results. Keep changes focused on the existing operator workflow.

Use Node 24 and Python 3.12. Run the frontend and model-free checks in the README. Changes to inference or video processing also need the full private-model suite and a real positive/negative video check. Do not generate successful detections or provider-delivery statuses to make a demo pass.

Preserve the original checkpoint and exact class map. Use disposable fixtures and separate accounts for integration tests. Never commit real environment files, account sessions, databases, PIN hashes, private media or checkpoints. Keep provider and production credentials out of public/forked CI.

For HYPNEXIS, record existing work, AI-assisted work and new event contributions honestly in `docs/HYPNEXIS_SUBMISSION.md`. Do not alter commit dates or describe this existing prototype as entirely built during the event. Confirm event-specific reuse rules with the organizer.

The project’s own source/model license has not yet been selected by its owner. Do not change licensing or publish private assets on someone else’s behalf.
