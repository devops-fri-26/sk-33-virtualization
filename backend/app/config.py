"""App settings, read from environment variables / .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    database_url: str = "postgresql+asyncpg://varsis:varsis@localhost:5432/varsis"
    secret_key: str = "change-me"
    app_url: str = "http://localhost:8080"

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


settings = Settings()
