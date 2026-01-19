"""Tests for configuration."""

from src.wabotii.config.settings import Settings


def test_settings_default_values():
    """Test default settings values."""
    settings = Settings()
    assert settings.app_name == "WABotII"
    assert settings.port == 8000
    assert settings.dev_mode is False


def test_settings_dev_mode():
    """Test dev mode settings."""
    settings = Settings(dev_mode=True)
    assert settings.dev_mode is True


def test_cloudinary_url_construction():
    """Test Cloudinary URL construction."""
    settings = Settings(
        cloudinary_api_key="key123",
        cloudinary_api_secret="secret456",
        cloudinary_cloud_name="mycloud",
    )
    url = settings.get_cloudinary_url()
    assert "cloudinary://" in url
    assert "key123" in url
    assert "mycloud" in url
