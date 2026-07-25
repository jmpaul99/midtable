from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_CRON = "dev-cron-secret"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://postgres:postgres@127.0.0.1:54322/postgres"
    supabase_url: str = "http://127.0.0.1:54321"
    supabase_jwt_audience: str = "authenticated"
    # New Supabase API key name; falls back to legacy service_role via alias below
    supabase_secret_key: str = ""
    supabase_service_role_key: str = ""
    football_data_api_token: str = ""
    football_data_base_url: str = "https://api.football-data.org/v4"
    cron_secret: str = _DEV_CRON
    cors_origins: str = "http://localhost:3000"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    auth_bypass_email: str = ""
    public_app_url: str = "http://localhost:3000"
    mailjet_api_key_public: str = ""
    mailjet_api_key_private: str = ""
    mailjet_from_email: str = ""
    mailjet_from_name: str = "Midtable"

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() in {"production", "prod"}

    @property
    def is_development(self) -> bool:
        return self.app_env.strip().lower() == "development"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def jwt_issuer(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1"

    @property
    def resolved_supabase_secret_key(self) -> str:
        """Prefer SUPABASE_SECRET_KEY; accept legacy SUPABASE_SERVICE_ROLE_KEY."""
        return self.supabase_secret_key or self.supabase_service_role_key

    @property
    def mailjet_configured(self) -> bool:
        return bool(
            self.mailjet_api_key_public.strip()
            and self.mailjet_api_key_private.strip()
            and self.mailjet_from_email.strip()
        )

    def validate_runtime(self) -> None:
        if not self.is_production:
            return
        if not self.cron_secret or self.cron_secret == _DEV_CRON:
            raise RuntimeError("CRON_SECRET must be set to a non-default value in production")
        if not self.supabase_url.strip():
            raise RuntimeError("SUPABASE_URL must be set in production (JWKS issuer)")
        if self.auth_bypass_email:
            raise RuntimeError("AUTH_BYPASS_EMAIL must not be set in production")
        if "*" in self.cors_origin_list:
            raise RuntimeError("CORS_ORIGINS must not include '*' when credentials are enabled")
        if not self.public_app_url.strip():
            raise RuntimeError("PUBLIC_APP_URL must be set in production")
        if not self.mailjet_configured:
            raise RuntimeError(
                "Mailjet must be configured in production "
                "(MAILJET_API_KEY_PUBLIC, MAILJET_API_KEY_PRIVATE, MAILJET_FROM_EMAIL)"
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
