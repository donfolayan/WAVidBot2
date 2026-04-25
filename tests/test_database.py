"""Tests for database service."""

import os
import sqlite3
import tempfile

from src.wabotii.config.settings import Settings
from src.wabotii.services.database import DatabaseService


def test_database_initialization():
    """Test database initialization."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        settings = Settings(database_url=f"sqlite:///{db_path}")

        DatabaseService(settings)
        assert os.path.exists(db_path)


def test_get_or_create_user():
    """Test user creation and retrieval."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        settings = Settings(database_url=f"sqlite:///{db_path}")
        service = DatabaseService(settings)

        # Create user
        user_id_1 = service.get_or_create_user("1234567890")
        assert user_id_1 > 0

        # Get same user
        user_id_2 = service.get_or_create_user("1234567890")
        assert user_id_1 == user_id_2

        # Create different user
        user_id_3 = service.get_or_create_user("9876543210")
        assert user_id_3 != user_id_1


def test_record_download():
    """Test recording downloads."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        settings = Settings(database_url=f"sqlite:///{db_path}")
        service = DatabaseService(settings)

        user_id = service.get_or_create_user("1234567890")
        download_id = service.record_download(
            user_id=user_id,
            url="https://youtube.com/watch?v=test",
            video_title="Test Video",
            file_size_mb=15.5,
        )

        assert download_id > 0


def test_get_download_stats():
    """Test retrieving download statistics."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        settings = Settings(database_url=f"sqlite:///{db_path}")
        service = DatabaseService(settings)

        # Should start with no data
        stats = service.get_download_stats()
        assert stats["total_downloads"] == 0
        assert stats["total_users"] == 0

        # Add user and download
        user_id = service.get_or_create_user("1234567890")
        service.record_download(
            user_id=user_id,
            url="https://youtube.com/watch?v=test",
            video_title="Test Video",
            file_size_mb=10.0,
        )

        # Check stats updated
        stats = service.get_download_stats()
        assert stats["total_downloads"] == 1
        assert stats["total_users"] == 1
        assert stats["total_size_mb"] == 10.0


def test_cloudinary_public_id_cleanup_tracking():
    """Test Cloudinary public IDs can be tracked and marked deleted."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        settings = Settings(database_url=f"sqlite:///{db_path}")
        service = DatabaseService(settings)

        user_id = service.get_or_create_user("1234567890@c.us")
        service.record_download(
            user_id=user_id,
            url="https://youtube.com/watch?v=test",
            video_title="Test Video",
            file_size_mb=10.0,
        )
        service.update_download_url(
            "1234567890@c.us",
            "https://youtube.com/watch?v=test",
            "https://res.cloudinary.com/demo/video/upload/test.mp4",
            "wa-downloads/test",
        )
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE downloads SET created_at = datetime('now', '-2 hours')")
        conn.commit()
        conn.close()

        public_ids = service.get_expired_cloudinary_public_ids(retention_hours=1)
        assert public_ids == ["wa-downloads/test"]

        service.mark_cloudinary_deleted("wa-downloads/test")
        assert service.get_expired_cloudinary_public_ids(retention_hours=1) == []
