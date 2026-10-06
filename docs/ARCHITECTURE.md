# Architecture Overview

> **Status**: planned design from `docs/PRD.md`. Nothing below is implemented yet; update each section to the current state as it is built.

## System Design
PMO Intelligence has 3 inputs, 1 queue, 2 pipelines and 1 health model. Every input becomes a signal, and every placement gets one health reading.

![PMO Intelligence architecture · 3 inputs, 1 queue, 2 pipelines, 1 health model](assets/architecture.png)

- **Session recordings** (S3 folder, upload, URL) and **Teams group chat** (Graph poll every 2 to 5 min) → **Processing queue** (one owning task, N workers, chat jobs first)
- Processing queue → **Session pipeline** (transcribe, roles, signals, actions) and **Chat pipeline** (classify, signals, cadence)
- Both pipelines → **Signal store** (signals with quotes) → recompute → **Health model** (6 scores, trend, RAG, risk flags)
- **Placement register** (admin pages, CSV import) → Health model (context: dates, extension, owners)
- Health model → polls 30 s → **Dashboard and alerts** (live board, email)

Recordings and chat both pass through the one processing queue into their pipelines. Everything they extract lands in the signal store. The health model recomputes the placement after every job and reads the register for context. The dashboard and alerts read the latest snapshot.

It uses the same stack as Interview Intelligence in a new repository, with three new pieces: a Microsoft Graph connector for Teams, the signal store with the health model, and a dashboard built around people rather than recordings.

**What is deliberately not shared**: no shared database, no shared service code at runtime, no monorepo. Files worth copying (the processing queue, the ownership lock, the LLM factory, the entitlement helper shape, the test conftests) are copied in and allowed to diverge.

## Component Architecture
| Component | Technology | Responsibility | Reuse or new |
|-----------|-----------|----------------|--------------|
| Backend | FastAPI, Python 3.12, SQLAlchemy 2.0 async, Alembic, Pydantic | Routes → services → repositories → models; scope check on every by-id route | Reuse the layering and the repo skeleton |
| Database | PostgreSQL 16 + pgvector | Register, sessions, messages, signals (with embeddings), snapshots, flags, access log | Reuse; embeddings let a reviewer search "who else had this blocker" |
| Transcription | AssemblyAI with speaker diarization; Teams' own transcript when a recording comes through Graph | Diarized utterances for the session pipeline | Reuse the shared AssemblyAI client |
| LLM | Azure OpenAI gpt-5.4-mini through the LLM factory, LangGraph graphs, structured output | Session and chat pipelines; every node non-fatal, timed, costed, with a timeout | Reuse the factory, the cost tracker, the timeout setting, the non-fatal node pattern |
| Processing | One process-wide priority queue with N workers, a Postgres advisory lock so one task owns processing during a deploy, startup sweeps, a per-job session | Runs pipeline jobs; chat jobs ahead of session jobs | Reuse as is; it cost three hotfixes to get right |
| Teams connector | Microsoft Graph: channel or chat messages, later meeting recordings and transcripts | Polls watched groups every 2–5 min with delta tokens (channels) or a last-modified watermark (chats) | New |
| Signals and health | signals, health_snapshots, risk_flags, actions tables; a pure scoring module with weights and thresholds in configuration | Six dimension scores, overall, trend, RAG, triggers → snapshot | New |
| Alerts | Amazon SES email now; a Teams message to a PMO channel once the connector can write | Immediate, daily digest, weekly summary | Reuse the SES sender from the daily report |
| Frontend | Next.js 16 App Router, TypeScript strict, shadcn/ui, SWR, TanStack Table, Recharts, dark mode | Risk board, consultant page, session page, actions, admin | Reuse the component library, the auth client, the admin page patterns |
| Auth | Microsoft Entra ID SSO only, roles on the user row, bootstrap admin list from configuration | Role plus placement scope; 404 outside scope; access log | Reuse; replace the UK/US entitlement with role plus consultant scope |
| Infra | AWS eu-west-2: ECS Fargate, RDS, S3, ALB, Secrets Manager, CloudWatch, Terraform | Staging and production environments | Reuse the modules; a separate RDS database on the existing instance, its own bucket, its own ALB rules or hostname |
| CI | GitHub Actions: unit, integration (testcontainers), Playwright; build-and-push with path filters | Gate every merge | Reuse |

## Teams Connector
- **Permission routes, in order of preference**: (1) resource-specific consent (RSC) per group with `ChannelMessage.Read.Group` / `ChatMessage.Read.Chat`; (2) application permissions `ChannelMessage.Read.All` / `Chat.Read.All`, which are Microsoft protected APIs that need approval; (3) delegated permissions through a service account, which is fragile. The full comparison is in the PRD.
- **Sync**: poll every 2–5 min; store the delta token or watermark on `teams_groups`. Change notifications are a later optimisation, because chat subscriptions expire within the hour.
- **Meeting recordings (later)**: `OnlineMeetingRecording.Read.All`, `OnlineMeetingTranscript.Read.All` plus an application access policy assigned to the organisers.
- **Risks**: protected-API lead time; tenant admin consent; Graph throttling on the first history pull; edited or deleted messages (store lastModified, honour deletion); partner tenants needing separate consent.

## Data Model
The placement is the unit of health; the consultant, the client and the project are its context. Every table carries `id`, `created_at`, `updated_at`.

| Table | Key Fields | Notes |
|-------|-----------|-------|
| consultants | full_name, email, entra_oid (nullable), phone, skills, status (bench / placed / left) | One row per person; entra_oid links the Teams author to the consultant |
| clients | name, normalized_name, industry | Dedup on normalized_name |
| projects | client_id, name, client_manager_name, tech_lead_user_id, start_date | One client can run several projects |
| placements | consultant_id, project_id, start_date, expected_end_date, extension_status (not_due / due / requested / confirmed / declined), rate_band, ps_user_id, sme_user_id, status (active / ended / terminated), ended_reason | The unit everything else hangs off; ended_reason is what a forecast model would later learn from |
| teams_groups | placement_id (nullable), project_id (nullable), graph_team_id, graph_channel_id or graph_chat_id, kind (channel / group_chat), is_active, last_synced_at, delta_token | One Teams conversation watched for one placement or project |
| sessions | placement_id, kind (onboarding / technical / check_in / escalation / other), held_at, duration_seconds, source (s3 / upload / url / graph), recording_key, graph_meeting_id, status (uploaded → transcribing → transcribed → analyzing → completed / failed), error_message | One recorded PMO call |
| session_transcripts | session_id (unique), full_text, utterances (JSONB), speaker_roles (JSONB), summary, session_class | Diarized transcript and the attributed roles |
| messages | teams_group_id, graph_message_id (unique with group), author_entra_oid, author_role (consultant / pmo_manager / sme / tech_lead / ps / other), posted_at, body_text, reply_to_message_id, message_class, is_noise | The raw chat, kept so a flag can quote it |
| signals | placement_id, source_kind (session / message), source_id, dimension, polarity, severity (1–3), confidence (0–1), quote, note, occurred_at, embedding (1536D) | The one table the health model reads; indexed on (placement_id, occurred_at) |
| issues | placement_id, topic, first_seen_at, last_seen_at, occurrence_count, status (open / resolved), resolved_at | A blocker followed across sessions; the repeated-blocker trigger reads it |
| actions | placement_id, source_kind, source_id, owner_role, owner_user_id (nullable), description, due_text, due_date (nullable), status (open / done / overdue), closed_at | What was agreed on a call or in the group |
| health_snapshots | placement_id, computed_at, delivery, technical, relationship, engagement, onboarding, communication, overall, trend, risk_level, signal_count, weights_version | One row per recompute; the dashboard reads the latest, the chart reads the history |
| risk_flags | placement_id, trigger, severity, opened_at, evidence_signal_ids, closed_at, closed_by_user_id, closing_note | Open until a person closes it |
| users | email, full_name, entra_oid, role (pmo_manager / sme / tech_lead / ps / admin), is_active | Role is the entitlement; scope is derived from the placements naming the user |
| processing_jobs, processing_costs, refresh_tokens | as in Interview Intelligence | Costs keyed by session_id or message_id, nullable, so chat runs are costed too |
| access_log | user_id, placement_id, route, at | Who looked at whom |

**Open before the first migration**: does a Teams group map to a placement or a project (a project group with two consultants needs the author's identity to attribute a message), and is the register owned here or imported from the PS team's system of record? These are BACKLOG questions 1 and 3.
