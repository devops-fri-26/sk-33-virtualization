"""App settings, read from environment variables / .env."""

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Everything the backend can be configured with.

    Each field is read from the environment variable of the same name in upper case (`DATABASE_URL`, `SMTP_HOST`…),
    or from a `.env` file in the backend folder or the folder above it. Variables it doesn't know are ignored.
    """

    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    database_url: str  # required; docker compose builds it from POSTGRES_PASSWORD
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
    smtp_tls: bool = False  # encrypt with STARTTLS; required when SMTP_USER is set (unless the port is 465)

    music_dir: str = "/music"
    covers_dir: str = "/covers"

    @field_validator("secret_key")
    @classmethod
    def strong_secret(cls, v: str) -> str:
        """Refuse to start with a missing, short or placeholder SECRET_KEY.

        Args:
            v: The configured value.

        Returns:
            The value, unchanged.

        Raises:
            ValueError: If it is shorter than 32 characters or still starts with "change-me".
        """
        # Anyone who knows the key can forge a login cookie for any account.
        if len(v) < 32 or v.startswith("change-me"):
            raise ValueError("SECRET_KEY must be a random string of at least 32 characters (openssl rand -hex 32)")
        return v

    @field_validator("app_url")
    @classmethod
    def no_trailing_slash(cls, v: str) -> str:
        """Remove slashes from the end of APP_URL.

        Args:
            v: The configured value.

        Returns:
            The address without a trailing slash.
        """
        return v.rstrip("/")  # links are built as f"{app_url}/verify?..."

    @model_validator(mode="after")
    def smtp_login_needs_tls(self):
        """Refuse to start when the SMTP login would be sent unencrypted.

        Returns:
            The settings, unchanged.

        Raises:
            ValueError: If SMTP_USER is set while SMTP_TLS is off and the port isn't 465.
        """
        # Without TLS the SMTP username and password would cross the network as plain text.
        if self.smtp_user and not self.smtp_tls and self.smtp_port != 465:
            raise ValueError("SMTP_USER is set but SMTP_TLS is false: set SMTP_TLS=true (or use port 465)")
        return self

    @property
    def admins(self) -> set[str]:
        """The addresses in ADMIN_EMAILS, in lower case."""
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}


# Read once at import; every other module imports this object.
settings = Settings()
