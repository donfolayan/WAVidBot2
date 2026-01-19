"""Tests for utilities."""

import os

from src.wabotii.utils.helpers import sanitize_filename, setup_cookies


def test_sanitize_filename():
    """Test filename sanitization."""
    # Test with special characters
    filename = sanitize_filename("Test Video!@#$%^&*().mp4")
    assert "Test Video" in filename
    assert "!" not in filename
    assert "@" not in filename

    # Test with emoji (should be removed)
    filename = sanitize_filename("🎬 Video 📹")
    assert "🎬" not in filename
    assert "Video" in filename


def test_sanitize_filename_truncation():
    """Test filename truncation."""
    long_name = "A" * 60
    filename = sanitize_filename(long_name)
    # Should have timestamp added, so will be longer than 50
    assert len(filename.split("_")[0]) <= 50


def test_setup_cookies_no_env():
    """Test setup cookies with no environment variables."""
    # Clear env vars if they exist
    os.environ.pop("YOUTUBE_COOKIES_CONTENT", None)
    os.environ.pop("FACEBOOK_COOKIES_CONTENT", None)

    youtube_path, facebook_path = setup_cookies()
    assert youtube_path is None
    assert facebook_path is None
