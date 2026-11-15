"""App settings, read from environment variables / .env."""

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    database_url: str = "postgresql+asyncpg://varsis:varsis@localhost:5432/varsis"
    secret_key: str = ""  # signs session cookies and email links; required
    app_url: str = "http://localhost:8080"
    # Comma-separated. These accounts are made admins (and approved) at startup and on sign-up.
    admin_emails: str = ""
    default_quota_gb: float = 10  # upload space of a new user; admins can change it per user

    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_from: str = "varsis@localhost"
    smtp_tls: bool = False

    prowlarr_url: str = "http://localhost:9696"
    prowlarr_api_key: str = ""
    qbit_url: str = "http://localhost:8081"
    qbit_user: str = "admin"
    qbit_pass: str = ""

    music_dir: str = "/music"
    downloads_dir: str = "/downloads"
    covers_dir: str = "/covers"

    @field_validator("secret_key")
    @classmethod
    def strong_secret(cls, v: str) -> str:
        # Anyone who knows the key can forge a login cookie for any account.
        if len(v) < 32 or v.startswith("change-me"):
            raise ValueError("SECRET_KEY must be a random string of at least 32 characters (openssl rand -hex 32)")
        return v

    @field_validator("app_url")
    @classmethod
    def no_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")  # links are built as f"{app_url}/verify?..."

    @model_validator(mode="after")
    def smtp_login_needs_tls(self):
        # Without TLS the SMTP username and password would cross the network as plain text.
        if self.smtp_user and not self.smtp_tls and self.smtp_port != 465:
            raise ValueError("SMTP_USER is set but SMTP_TLS is false: set SMTP_TLS=true (or use port 465)")
        return self

    @property
    def admins(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}


settings = Settings()
