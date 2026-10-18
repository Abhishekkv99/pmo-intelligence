from datetime import date

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    project_name: str = "pmo-intelligence"
    app_env: str = "development"
    # Echoes every SQL statement when on. Off unless set, so a container that
    # forgets APP_DEBUG (a one-off ECS task, the migration container) stays
    # quiet; compose and .env.example turn it on for development.
    app_debug: bool = False
    app_port: int = 8000
    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"

    # Database
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/pmo_intelligence"
    )

    # AssemblyAI (session transcription). The EU endpoint keeps the audio and
    # transcripts of workers' calls in the EU, at the US price. speech_models is
    # required by the API: the first model that supports the language is used.
    assemblyai_api_key: str = ""
    assemblyai_base_url: str = "https://api.eu.assemblyai.com"
    assemblyai_speech_models: list[str] = ["universal-3-5-pro", "universal-2"]
    # Rate card (2026-10-08): Universal-3.5 Pro $0.21/hr, plus $0.02/hr for
    # speaker diarization. Billed pro-rated to the second.
    assemblyai_cost_per_hour_usd: float = 0.21
    assemblyai_diarization_cost_per_hour_usd: float = 0.02
    # Diarization hint: a PMO call is the consultant and a PMO person,
    # sometimes an SME or the consultant's CDM too.
    assemblyai_min_speakers: int = 2
    assemblyai_max_speakers: int = 4
    # A transcript still unfinished after this long fails the session.
    assemblyai_timeout_seconds: int = 1800
    assemblyai_poll_interval_seconds: float = 5.0

    # Azure OpenAI (signal extraction, summaries, embeddings)
    azure_openai_api_key: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_deployment: str = ""
    azure_openai_api_version: str = "2025-04-01-preview"
    azure_embedding_deployment: str = ""
    # Per-request timeout for every chat and embedding call. The client's own
    # default is no timeout, so a dead connection would wait forever
    azure_openai_timeout_seconds: int = 300

    # Session pipeline. Every LLM node stops after this long and is recorded
    # as a node error; it is under the client timeout so the node's own limit
    # fires first. One reasoning effort for every node.
    session_node_timeout_seconds: int = 240
    session_reasoning_effort: str = "medium"
    # The issues node is offered the placement's open issues and the ones
    # resolved within this many days of the call, so a blocker raised again
    # is linked to (and reopens) the earlier issue.
    session_resolved_issue_lookback_days: int = 30
    # Signal embeddings, made after a session's analysis is stored: at most
    # this many signals per request, and the whole session's embedding stops
    # after this long (a failure leaves them for the backfill command).
    signal_embedding_batch_size: int = 100
    signal_embedding_timeout_seconds: int = 120

    # Health model. The weights, decay and thresholds are in the versioned
    # file app/health/config/<version>.json; every snapshot records the
    # version. The daily recompute (decay and the contract horizon move
    # without new evidence) runs at this hour in this zone, which also gives
    # the dates the scoring reads.
    health_config_version: str = "v1"
    health_daily_enabled: bool = False
    health_daily_hour: int = 6
    health_timezone: str = "Europe/London"

    # AWS / Storage
    aws_region: str = "eu-west-2"
    s3_bucket_name: str = "pmo-intelligence-media"
    s3_endpoint_url: str | None = None
    storage_backend: str = "local"
    local_upload_dir: str = "./uploads"

    # Upload constraints (session recordings)
    max_upload_size_mb: int = 500
    allowed_extensions: list[str] = [
        ".mp4",
        ".mov",
        ".webm",
        ".mp3",
        ".wav",
        ".m4a",
        ".ogg",
    ]
    # The PMO recordings folder (main ITC account, read through a bucket
    # policy). A folder under the prefix is a recurring Talk room; the scan
    # only catalogs it, and a recording is processed when a person asks.
    recordings_source_bucket: str = "nextcloud-talk-recordings-itc"
    recordings_source_prefix: str = "recordings/pmo/"
    # Off unless set: development has no access to the source bucket.
    recordings_scan_enabled: bool = False
    recordings_scan_interval_seconds: int = 900
    # Recording file names carry the local time of the call.
    recordings_timezone: str = "Europe/London"
    # Only calls on or after this UK date are cataloged, and only folders
    # holding one: older calls are out of scope (user decision 2026-10-09,
    # 2.5 months before then). Empty (None) catalogs everything.
    recordings_earliest_date: date | None = date(2026, 7, 24)
    # Typical bytes per second of audio in a PMO recording, for the cost
    # estimate shown before Process (a recording's length is known only once
    # transcribed). Measured 2026-10-09 on the 204 Talk recordings since the
    # earliest date: size over the gap between the file name's time and the
    # S3 time, median 77.4 KiB/s (p10 25, p90 109 over all 2,294). The gap
    # includes the upload, so estimates err high.
    recordings_bytes_per_second: int = 79_000

    # Downloading a recording from a URL; max_upload_size_mb caps it too.
    url_download_timeout_seconds: int = 1800
    url_download_max_redirects: int = 5

    # Teams chat through Microsoft Graph. The Graph app (its own registration,
    # not the SSO one) signs in app-only with a certificate, given as the
    # base64 of its .pfx and the .pfx password (both from the app secret).
    # Watched chats are read with Chat.Read.All, one change-notification
    # subscription per chat; graph_client_state is the secret every
    # notification must carry. Off unless enabled.
    teams_enabled: bool = False
    graph_tenant_id: str = ""
    graph_client_id: str = ""
    graph_certificate_pfx_base64: str = ""
    graph_certificate_password: str = ""
    graph_client_state: str = ""
    # Every Graph request stops after this long; a 429, 503 or 504 is retried
    # this many times (after Retry-After, else an exponential backoff).
    graph_timeout_seconds: float = 30.0
    graph_max_retries: int = 5
    # The PMO accounts whose chat lists discovery reads (user principal
    # names, JSON list): between them they are in every PRJ ITC chat.
    teams_discovery_accounts: list[str] = []
    # The public base URL Graph sends notifications to (the staging site);
    # the notification and lifecycle routes are appended to it.
    teams_notification_base_url: str = ""

    # Processing queue: how many pipeline jobs run at once
    processing_concurrency: int = 1
    # Start tracemalloc and log per-job allocation growth (costly; diagnostics only)
    memory_diagnostics_enabled: bool = False

    # Security
    secret_key: str = "change-me-to-a-random-string"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 1440

    # Token expiration
    access_token_expiration_minutes: int = 15
    refresh_token_expiration_days: int = 7

    # Cookie settings
    cookie_secure: bool = False
    cookie_domain: str = ""

    # Microsoft Entra ID (SSO)
    # Email/password sign-in. Disabled in staging and production so Microsoft
    # Entra ID is the only way in; left on by default for local development and
    # CI, where the E2E suite needs a non-interactive way to authenticate.
    local_auth_enabled: bool = True

    azure_client_id: str = ""
    azure_client_secret: str = ""
    azure_tenant_id: str = ""
    # Other Entra tenants whose accounts may sign in, comma-separated tenant
    # IDs. The home tenant (azure_tenant_id) is always allowed. Empty keeps the
    # app single-tenant: the tenant-specific authority is used and nothing
    # changes. Non-empty switches the authorize, token and JWKS requests to the
    # "organizations" authority (the app registration must be multi-tenant)
    # and every id_token's issuer is checked against the full list, so an
    # account from any other organisation is refused before a row is created.
    azure_allowed_tenant_ids: str = ""
    azure_redirect_uri: str = "http://localhost:3000/auth/callback/microsoft"

    # The first PMO managers. Comma-separated emails, matched
    # case-insensitively at startup and at user-row creation and given the
    # pmo_manager role. Elevate-only: a listed user who already has a role is
    # never changed by this setting and an unlisted user is never touched. It
    # is the only way to grant a role without a database change — the
    # operator has no SQL access to RDS.
    bootstrap_admin_emails: str = ""

    @property
    def cors_origins(self) -> list[str]:
        return [self.frontend_url]


settings = Settings()
