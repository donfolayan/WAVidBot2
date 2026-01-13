"""Application configuration using Pydantic Settings."""

import os

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


# Skip loading .env during pytest runs to keep tests independent of local secrets.
ENV_FILE = None if "PYTEST_CURRENT_TEST" in os.environ else ".env"


class Settings(BaseSettings):
    """Application configuration from environment variables."""

    # Application
    app_name: str = Field(default="WABotII", alias="APP_NAME")
    app_version: str = Field(default="0.1.0", alias="APP_VERSION")
    dev_mode: bool = Field(default=False, alias="DEV_MODE")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    port: int = Field(default=8000, alias="PORT")
    base_url: str = Field(default="http://localhost:8000", alias="BASE_URL")

    # WAHA Configuration
    waha_base_url: str = Field(default="http://localhost:3000", alias="WAHA_BASE_URL")
    waha_session_name: str = Field(default="default", alias="WAHA_SESSION_NAME")
    waha_api_key: str = Field(default="", alias="WAHA_API_KEY")
    waha_dashboard_username: str = Field(default="", alias="WAHA_DASHBOARD_USERNAME")
    waha_dashboard_password: str = Field(default="", alias="WAHA_DASHBOARD_PASSWORD")
    whatsapp_swagger_username: str = Field(default="", alias="WHATSAPP_SWAGGER_USERNAME")
    whatsapp_swagger_password: str = Field(default="", alias="WHATSAPP_SWAGGER_PASSWORD")

    # WhatsApp Webhook Verification
    verify_token: str = Field(default="wa_downloader_test_token", alias="VERIFY_TOKEN")

    # Database Configuration
    database_url: str = Field(
        default="sqlite:///./wabotii.db",
        alias="DATABASE_URL"
    )

    # Cloudinary Configuration
    cloudinary_url: str = Field(default="", alias="CLOUDINARY_URL")
    cloudinary_cloud_name: str = Field(default="", alias="CLOUDINARY_CLOUD_NAME")
    cloudinary_api_key: str = Field(default="", alias="CLOUDINARY_API_KEY")
    cloudinary_api_secret: str = Field(default="", alias="CLOUDINARY_API_SECRET")

    # Video Processing
    file_retention_hours: int = Field(default=24, alias="FILE_RETENTION_HOURS")
    cloudinary_retention_hours: int = Field(default=24, alias="CLOUDINARY_RETENTION_HOURS")
    max_file_size_mb: int = Field(default=16, alias="MAX_FILE_SIZE_MB")
    download_timeout_seconds: int = Field(default=300, alias="DOWNLOAD_TIMEOUT_SECONDS")

    # Optional Cookie Files (base64 encoded)
    youtube_cookies_content: str = Field(default="", alias="YOUTUBE_COOKIES_CONTENT")
    facebook_cookies_content: str = Field(default="", alias="FACEBOOK_COOKIES_CONTENT")

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        populate_by_name=True,
        extra="ignore",
    )

    def get_cloudinary_url(self) -> str | None:
        """Get the Cloudinary URL or construct from individual vars."""
        if self.cloudinary_url:
            return self.cloudinary_url
        if self.cloudinary_api_key and self.cloudinary_api_secret and self.cloudinary_cloud_name:
            return (
                f"cloudinary://{self.cloudinary_api_key}:"
                f"{self.cloudinary_api_secret}@{self.cloudinary_cloud_name}"
            )
        return None

    def is_production(self) -> bool:
        """Check if running in production mode."""
        return not self.dev_mode

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings):
        """Use only init and defaults during tests; otherwise include env and dotenv."""
        if "PYTEST_CURRENT_TEST" in os.environ:
            return (init_settings,)
        return (init_settings, env_settings, dotenv_settings, file_secret_settings)


def get_settings() -> Settings:
    """Get application settings."""
    return Settings()  # type: ignore
