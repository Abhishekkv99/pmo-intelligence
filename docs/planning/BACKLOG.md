# Backlog

## Open Questions (decide before Sprint 1)
From the PRD, "Decisions needed before Sprint 1". Each one changes the data model, the Teams work or the health model.

| # | Question | Why it matters | Suggested answer |
|---|----------|----------------|------------------|
| 1 | Are the Teams groups team channels or group chats, one per consultant or one per project? | Decides the Graph endpoints, the permission route and whether teams_groups hangs off a placement or a project | One group chat per placement, if that is how they exist today |
| 2 | Where do PMO call recordings live today: a Nextcloud or S3 folder like the interviews, Teams meeting recordings, or nowhere yet? | Decides whether Phase 1 reuses the S3 scanner or starts with upload only, and whether Graph recording access is needed | Reuse the S3 scanner if a folder exists; otherwise upload and URL first |
| 3 | Who is the system of record for placements: this tool, or the PS team's spreadsheet or CRM? | Owning it here means admin pages; importing means a sync and a source of truth elsewhere | Own it here, seed it once from the spreadsheet |
| 4 | Which route for Teams permissions: RSC per group, application permissions through Microsoft's approval, or a service account? | Lead time and tenant-admin involvement | RSC, with application permissions requested in parallel as the fallback |
| 5 | Who may see what: is a PS limited to their own placements, and may an SME see health scores or only their technical sessions? | The role model and the scope check | PS and tech lead scoped to their placements; SME sees sessions and the technical dimension only; PMO manager sees all |
| 6 | Do consultants know their calls and group are analysed, and who issues the notice? | Lawful basis under UK GDPR; the wording is HR's | HR issues a notice at placement start; the tool's first production deploy waits for it |
| 7 | Starting weights and thresholds for the six dimensions and the triggers | They are configuration, but the first values shape whether the PMO trusts the board | The values in the health section, tuned at the Phase 2 gate |
| 8 | One environment or two (staging and production), and does it share the RDS instance with Interview Intelligence? | Cost and blast radius; the shared db.t4g.small is already at two databases | Two environments; a separate database on the existing instance to start, its own instance once production load is known |
| 9 | UK only, or UK and US from the start? | The branch dimension cost Interview Intelligence two sprints to retrofit | Model branch on placements from day one even if only UK is populated |
| 10 | Name and hostname | Repo, Entra app registration, Route 53 record, ECR repositories | pmo-intelligence, pmo.itcapp.ai and pmo-staging.itcapp.ai |

## High Priority
- [ ] Submit the Teams Graph permission request in Sprint 0 (longest external lead time)

## Medium Priority

## Low Priority

## Tech Debt
