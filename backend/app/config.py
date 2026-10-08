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

    # AssemblyAI (session transcription)
    assemblyai_api_key: str = ""

    # Azure OpenAI (signal extraction, summaries, embeddings)
    azure_openai_api_key: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_deployment: str = ""
    azure_openai_api_version: str = "2025-04-01-preview"
    azure_embedding_deployment: str = ""
    # Per-request timeout for every chat and embedding call. The client's own
    # default is no timeout, so a dead connection would wait forever
    azure_openai_timeout_seconds: int = 300

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
