# HYPNEXIS’26 submission plan

Prepared 19 October 2026. The organizer’s Unstop listing currently gives the online presentation deadline as **20 October 2026, 11:59 PM IST**, with the offline event on 24–25 October. It lists innovation, problem understanding, feasibility, impact, scalability and presentation quality as PPT evaluation areas. Offline problem statements will be revealed at the event. Confirm updates in your registration portal. [Organizer listing](https://unstop.com/competitions/hypnexis-2026-manipal-university-mu-jaipur-1711890/amp).

The supplied registration website could not be fetched during this research. A published rule explicitly allowing existing applications, pretrained weights or AI-assisted work was not located. These permissions and the final track/problem fit remain unconfirmed. Do not assume eligibility or submit this preparation as work completed entirely during the event.

## Positioning

**One sentence:** SightLine turns surveillance footage into timestamped, reviewable person/mask/knife evidence, with an operator deciding what happens next.

**Target user hypothesis:** a small-property security operator who needs to inspect a short clip quickly. This is a hypothesis, not validated customer research. Replace it with consented interviews or observed workflow evidence when available.

**Defensible contribution:** the complete review workflow—private account setup, real inference, bounded evidence, human confirmation, false-alarm handling, persistent history and honest response status. Do not call object detection itself a novel invention.

## Suggested online deck: eight slides

| Slide | Show | Evidence or task |
| --- | --- | --- |
| 1. Problem | One operator, one clip, one missed review moment | State the user/problem without an invented crime statistic |
| 2. User workflow | Upload → evidence → review → response | Use a redacted real screen recording once recorded |
| 3. Working prototype | A short positive example and an empty-scene control | Show actual confidence/time offsets; disclose model limitations |
| 4. Technical depth | Current architecture and exact three-class model | Explain the private PostgreSQL schema, signed media access and independent worker; distinguish local rehearsal mode |
| 5. Trust and control | Confirmation gate, account ownership, required dismissal reason, no default PIN | Demonstrate behavior; do not claim external dispatch is live |
| 6. Validation | 189 backend tests, 14 frontend checks, connected workflow and restart drill | Separate functional tests, mocks, accuracy and hosted checks |
| 7. Feasibility and scale | Current cloud deployment, durable queue/storage and a measured resource plan | No fictional unit economics, usage or scalability benchmark |
| 8. Team and next work | Actual contributors, existing work and event contribution plan | Add real team details and the event’s approved problem statement |

This is a proposed outline, not an official required template or a submitted presentation. The live app link is in the README. Team names, a demonstration video, representative accuracy, business evidence and organizer approval still need owner-supplied evidence.

## Contribution and originality record

| Period / asset | Current known status | Team must record |
| --- | --- | --- |
| Existing application and trained model | Already present before 24 October | Original author, model/data provenance and any prior submission |
| Repairs and documentation | AI-assisted changes and verification occurred before the event | Review responsibility and tools used |
| Event-time implementation | Not yet performed | Actual commits, authors, timestamps, problem mapping and tests |
| Training data / sample clips | Rights/provenance not verified in this handoff | Source, permissions, consent and redistribution restrictions |
| Third-party components | Listed in requirements, lockfile and notices | Applicable license decisions and required attribution |

Keep truthful Git history and a baseline release before the event if its rules permit. Log what is newly built rather than altering history. Ask the organizers whether this baseline can be reused and what attribution is required; no organizer has been contacted on your behalf.

## Suggested 36-hour work plan, subject to the revealed problem

- Hours 0–3: read rules/problem, confirm reuse and scope, choose one measurable acceptance story.
- Hours 3–14: implement the chosen event-specific contribution; pair feature work with meaningful tests.
- Hours 14–22: evaluate consented positive knife/mask and negative clips; record misses, false alerts, hardware and full latency.
- Hours 22–28: integrate/rehearse on the final device and URL; test a second account and restart recovery.
- Hours 28–33: freeze features, record the demo, prepare evidence and the contribution log.
- Hours 33–36: rehearse live delivery and fallback, verify submission links and submit by the actual deadline.

These are team-planning suggestions, not organizer requirements. Prioritize a small working, explainable result over adding an untested feature to the pitch.

## Before submission

- Confirm registration, portal deadlines, PPT requirements and permitted prior work.
- Add real team/contributor details and a consented, redacted demo video.
- Confirm application/model/data rights before publishing a repository.
- Match the final problem statement and identify the work completed during the event.
- Verify every quantitative claim against a reproducible result; keep unmeasured items explicitly open.
- Check links while signed out. Keep account passwords and private demonstration credentials out of README/slides.
