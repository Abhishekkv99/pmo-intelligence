# Product Roadmap

Six phases, each one or two sprints, each ending with a staging sign-off by the PMO manager before the next starts.

## Milestone 0: Bootstrap (Sprint 0)
- [x] Project skeleton and tooling (stack copied from Interview Intelligence: queue, ownership lock, LLM factory, auth, CI, Docker, Terraform)
- [x] SSO sign-in with roles (single tenant, members of the tenant with a role only; roles granted with `make user-role`)
- [x] Empty dashboard deployed to staging (`https://pmo-intelligence-staging.itcapp.ai`)
- [x] Graph app registration created and the Teams permission request submitted (the Teams app was approved and published, 1.0.0)
- **Exit gate**: staging URL signs in; CI green; the permission request has a ticket number. **Met 2026-10-08**: SSO sign-in on staging, CI green on `develop`, and the Teams app approved without a ticket number (see the Sprint 0 handover)

## Milestone 1: Register and Sessions
- [x] Placement register (admin pages, CSV import) (Sprint 1 Phase 2, 2026-10-08)
- [x] Session ingestion: upload, URL and S3 folder; transcription (Sprint 1 Phase 3, 2026-10-09)
- [ ] Session pipeline and session page
- **Exit gate**: three real recorded PMO calls processed end to end; the PMO manager agrees the signals and summary are right

## Milestone 2: Health v1
- [ ] Signal store, scoring module, snapshots, triggers, flags
- [ ] Risk board and consultant page
- [ ] Daily recompute
- **Exit gate**: ten placements scored from their sessions; the PMO manager agrees with the ranking, or the weights are tuned until they do

## Milestone 3: Teams Chat
- [ ] Graph connector (RSC or application permission), poller, message store
- [ ] Chat pipeline and cadence tracking; messages on the timeline
- [ ] Gone-quiet and missed-commitment triggers
- **Exit gate**: one real group watched for a week; new posts appear within 5 minutes; no message read outside the watched groups

## Milestone 4: Alerts and Actions
- [ ] SES alerts (immediate, daily digest, weekly summary)
- [ ] Actions page; flag closing with notes
- [ ] Access log view
- **Exit gate**: alerts received for a staged red placement; a PS closes a flag and it shows on the board

## Milestone 5: Production and Tuning
- [ ] Production deploy; consultant notice issued
- [ ] Retention job
- [ ] Monthly review of flags against outcomes
- [ ] Teams meeting recordings and transcripts through Graph (if calls are held in Teams)
- **Exit gate**: live for every active placement; first monthly review done

## Later (not version 1)
- [ ] Forecast of early-termination probability, learned from closed placements with recorded outcomes
