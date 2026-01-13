"""Database service for tracking downloads and users."""

import sqlite3
from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass

from ..config.settings import Settings
from ..utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class User:
    """User record."""

    id: int
    phone_number: str
    created_at: datetime


@dataclass
class Download:
    """Download record."""

    id: int
    user_id: int
    url: str
    video_title: str
    file_size_mb: float
    status: str
    created_at: datetime
    deleted_at: Optional[datetime] = None


class DatabaseService:
    """Service for database operations."""

    def __init__(self, settings: Settings):
        """Initialize database service."""
        # Extract database URL (handle SQLite format)
        db_url = settings.database_url
        if db_url.startswith("sqlite://"):
            self.db_path = db_url.replace("sqlite:///", "")
        else:
            self.db_path = db_url

        logger.info("Database service initialized", db_path=self.db_path)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database tables."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Create users table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone_number TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create downloads table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS downloads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    url TEXT NOT NULL,
                    video_title TEXT,
                    file_size_mb REAL,
                    status TEXT DEFAULT 'completed',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    deleted_at TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)

            conn.commit()
            conn.close()
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error("Error initializing database", error=str(e))
            raise

    def get_or_create_user(self, phone_number: str) -> int:
        """Get or create a user by phone number."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Try to get existing user
            cursor.execute("SELECT id FROM users WHERE phone_number = ?", (phone_number,))
            result = cursor.fetchone()

            if result:
                user_id = result[0]
                logger.debug("User found", phone_number=phone_number, user_id=user_id)
            else:
                # Create new user
                cursor.execute(
                    "INSERT INTO users (phone_number) VALUES (?)",
                    (phone_number,)
                )
                conn.commit()
                user_id = cursor.lastrowid
                logger.info("User created", phone_number=phone_number, user_id=user_id)

            conn.close()
            return user_id
        except Exception as e:
            logger.error("Error getting or creating user", phone_number=phone_number, error=str(e))
            raise

    def record_download(
        self,
        user_id: int,
        url: str,
        video_title: str,
        file_size_mb: float,
        status: str = "completed"
    ) -> int:
        """Record a download in the database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO downloads (user_id, url, video_title, file_size_mb, status)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, url, video_title, file_size_mb, status))

            conn.commit()
            download_id = cursor.lastrowid
            conn.close()

            logger.info(
                "Download recorded",
                download_id=download_id,
                user_id=user_id,
                title=video_title,
                size_mb=file_size_mb
            )
            return download_id
        except Exception as e:
            logger.error(
                "Error recording download",
                user_id=user_id,
                url=url,
                error=str(e)
            )
            raise

    def get_user_downloads(self, user_id: int, limit: int = 10) -> List[Download]:
        """Get recent downloads for a user."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, user_id, url, video_title, file_size_mb, status, created_at, deleted_at
                FROM downloads
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (user_id, limit))

            rows = cursor.fetchall()
            conn.close()

            downloads = [
                Download(
                    id=row[0],
                    user_id=row[1],
                    url=row[2],
                    video_title=row[3],
                    file_size_mb=row[4],
                    status=row[5],
                    created_at=datetime.fromisoformat(row[6]) if row[6] else datetime.now(),
                    deleted_at=datetime.fromisoformat(row[7]) if row[7] else None
                )
                for row in rows
            ]

            logger.debug("Retrieved user downloads", user_id=user_id, count=len(downloads))
            return downloads
        except Exception as e:
            logger.error("Error getting user downloads", user_id=user_id, error=str(e))
            return []

    def save_download(self, phone_number: str, url: str, file_path: str) -> None:
        """Save a download record for a phone number."""
        import os
        
        try:
            # Get or create user
            user_id = self.get_or_create_user(phone_number)
            
            # Extract video title from file path
            video_title = os.path.basename(file_path)
            
            # Get file size
            file_size_mb = 0.0
            if os.path.exists(file_path):
                file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            
            # Record the download
            self.record_download(
                user_id=user_id,
                url=url,
                video_title=video_title,
                file_size_mb=file_size_mb,
                status="completed"
            )
            
            logger.info(
                "Download saved",
                phone_number=phone_number,
                url=url,
                file_size_mb=round(file_size_mb, 2)
            )
        except Exception as e:
            logger.error(
                "Error saving download",
                phone_number=phone_number,
                url=url,
                error=str(e)
            )

    def update_download_url(self, phone_number: str, original_url: str, cloudinary_url: str) -> None:
        """Update a download record with the Cloudinary URL (stored as notes)."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Find the download by user phone and original URL
            cursor.execute("""
                SELECT d.id FROM downloads d
                JOIN users u ON d.user_id = u.id
                WHERE u.phone_number = ? AND d.url = ?
                ORDER BY d.created_at DESC
                LIMIT 1
            """, (phone_number, original_url))

            result = cursor.fetchone()
            if result:
                download_id = result[0]
                logger.debug(
                    "Download URL updated",
                    download_id=download_id,
                    cloudinary_url=cloudinary_url
                )
            
            conn.close()
        except Exception as e:
            logger.error(
                "Error updating download URL",
                phone_number=phone_number,
                original_url=original_url,
                error=str(e)
            )

    def get_download_stats(self) -> dict:
        """Get overall download statistics."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Total downloads
            cursor.execute("SELECT COUNT(*) FROM downloads")
            total_downloads = cursor.fetchone()[0]

            # Total users
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]

            # Total size downloaded
            cursor.execute("SELECT COALESCE(SUM(file_size_mb), 0) FROM downloads")
            total_size_mb = cursor.fetchone()[0]

            conn.close()

            stats = {
                "total_downloads": total_downloads,
                "total_users": total_users,
                "total_size_mb": round(total_size_mb, 2)
            }

            logger.debug("Retrieved download stats", stats=stats)
            return stats
        except Exception as e:
            logger.error("Error getting download stats", error=str(e))
            return {"total_downloads": 0, "total_users": 0, "total_size_mb": 0}
