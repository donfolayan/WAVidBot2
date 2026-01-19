"""Cloudinary service for cloud storage and file management."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Optional

import cloudinary
import cloudinary.api
import cloudinary.uploader

from ..config.settings import Settings
from ..utils.logging import get_logger

logger = get_logger(__name__)

executor = ThreadPoolExecutor(max_workers=2)


class CloudinaryService:
    """Service for Cloudinary cloud storage operations."""

    def __init__(self, settings: Settings):
        """Initialize Cloudinary service."""
        self.settings = settings
        cloudinary_url = settings.get_cloudinary_url()

        if cloudinary_url:
            cloudinary.config(
                cloud_name=settings.cloudinary_cloud_name,
                api_key=settings.cloudinary_api_key,
                api_secret=settings.cloudinary_api_secret,
                secure=True,
            )
            logger.info("Cloudinary service initialized", cloud_name=settings.cloudinary_cloud_name)
        else:
            logger.warning("Cloudinary not configured - uploads will be skipped")

    def upload_to_cloudinary(
        self, file_path: str, folder: str = "wa-downloads"
    ) -> tuple[Optional[str], Optional[str]]:
        """Upload a file to Cloudinary synchronously."""
        try:
            if not self.settings.get_cloudinary_url():
                logger.warning("Cloudinary not configured, skipping upload", file=file_path)
                return None, None

            logger.info("Uploading file to Cloudinary", file=file_path, folder=folder)

            result = cloudinary.uploader.upload(
                file_path,
                folder=folder,
                resource_type="video",
                timeout=300,
                overwrite=False,
                invalidate=False,
            )

            secure_url = result.get("secure_url")
            public_id = result.get("public_id")

            if secure_url:
                logger.info("File uploaded to Cloudinary", public_id=public_id, url=secure_url)
                return secure_url, public_id

            logger.error("Cloudinary upload failed - no URL in response", result=result)
            return None, None
        except Exception as e:
            logger.error("Error uploading to Cloudinary", file=file_path, error=str(e))
            return None, None

    async def async_upload_to_cloudinary(
        self, file_path: str, folder: str = "wa-downloads"
    ) -> tuple[Optional[str], Optional[str]]:
        """Upload a file to Cloudinary asynchronously."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(executor, self.upload_to_cloudinary, file_path, folder)

    def cleanup_cloudinary_files(
        self, folder: str = "wa-downloads", retention_hours: Optional[int] = None
    ) -> None:
        """Delete Cloudinary files older than retention_hours."""
        if retention_hours is None:
            retention_hours = self.settings.cloudinary_retention_hours

        if not self.settings.get_cloudinary_url():
            logger.warning("Cloudinary not configured, skipping cleanup")
            return

        try:
            cutoff = datetime.utcnow() - timedelta(hours=retention_hours)
            logger.info("Running Cloudinary cleanup", folder=folder, cutoff_time=cutoff)

            resources = cloudinary.api.resources(
                type="upload", prefix=folder, resource_type="video", max_results=500
            )

            deleted_count = 0
            for res in resources.get("resources", []):
                created_at_str = res.get("created_at")
                if not created_at_str:
                    continue

                created_at = datetime.strptime(created_at_str, "%Y-%m-%dT%H:%M:%SZ")

                if created_at < cutoff:
                    try:
                        public_id = res.get("public_id")
                        cloudinary.uploader.destroy(public_id, resource_type="video")
                        deleted_count += 1
                        logger.info(
                            "Deleted old Cloudinary file",
                            public_id=public_id,
                            created_at=created_at,
                        )
                    except Exception as e:
                        logger.error(
                            "Error deleting Cloudinary file", public_id=public_id, error=str(e)
                        )

            logger.info("Cloudinary cleanup complete", deleted_count=deleted_count)
        except Exception as e:
            logger.error("Error during Cloudinary cleanup", error=str(e))
