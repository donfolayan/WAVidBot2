"""WAHA (WhatsApp HTTP API) service wrapper."""

from dataclasses import dataclass
from typing import Optional

import httpx

from ..config.settings import Settings
from ..utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class WAHAMessage:
    """WAHA message response."""

    phone_number: str
    message_id: str
    body: str | None = None


class WAHAService:
    """Service for interacting with WAHA API."""

    def __init__(self, settings: Settings):
        """Initialize WAHA service."""
        self.base_url = settings.waha_base_url
        self.session_name = settings.waha_session_name
        self.api_key = settings.waha_api_key

        headers = {}
        if self.api_key:
            headers["X-Api-Key"] = self.api_key

        self.client = httpx.AsyncClient(base_url=self.base_url, headers=headers, timeout=30.0)
        logger.info("WAHA service initialized", base_url=self.base_url)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()

    async def health_check(self) -> bool:
        """Check if WAHA is healthy."""
        try:
            response = await self.client.get("/ping")
            is_healthy = response.status_code == 200
            logger.info("WAHA health check", is_healthy=is_healthy)
            return is_healthy
        except Exception as e:
            logger.error("WAHA health check failed", error=str(e))
            return False

    async def init_session(self) -> dict:
        """Initialize a new session in WAHA."""
        try:
            response = await self.client.post("/api/sessions", json={"name": self.session_name})
            result = response.json()
            logger.info("WAHA session initialized", session=self.session_name)
            return result
        except Exception as e:
            logger.error("Failed to initialize WAHA session", error=str(e))
            raise

    async def get_qr_code(self) -> Optional[bytes]:
        """Get QR code for current session."""
        try:
            response = await self.client.get(f"/api/sessions/{self.session_name}/screenshot")
            if response.status_code == 200:
                logger.info("QR code retrieved", session=self.session_name)
                return response.content
            logger.warning("Failed to get QR code", status_code=response.status_code)
            return None
        except Exception as e:
            logger.error("Error getting QR code", error=str(e))
            return None

    async def send_text_message(self, phone_number: str, text: str) -> bool:
        """Send a text message via WAHA."""
        try:
            # Ensure phone number is in correct format (with country code)
            if not phone_number.endswith("@c.us"):
                phone_number = f"{phone_number}@c.us"

            response = await self.client.post(
                "/api/sendText",
                json={"chatId": phone_number, "text": text, "session": self.session_name},
            )

            if response.status_code in (200, 201):
                logger.info("Text message sent", phone_number=phone_number)
                return True

            logger.warning(
                "Failed to send text message",
                status_code=response.status_code,
                response=response.text,
            )
            return False
        except Exception as e:
            logger.error("Error sending text message", phone_number=phone_number, error=str(e))
            return False

    async def send_video_message(self, phone_number: str, video_path: str) -> bool:
        """Send a video message via WAHA using sendFile endpoint."""
        import base64
        import os

        try:
            # Ensure phone number is in correct format
            if not phone_number.endswith("@c.us"):
                phone_number = f"{phone_number}@c.us"

            # Read and encode video file as base64
            with open(video_path, "rb") as f:
                video_data = base64.b64encode(f.read()).decode("utf-8")

            # Get filename from path
            filename = os.path.basename(video_path)

            # Send video using sendFile endpoint (compatible with WEBJS engine)
            response = await self.client.post(
                "/api/sendFile",
                json={
                    "chatId": phone_number,
                    "file": {"mimetype": "video/mp4", "filename": filename, "data": video_data},
                    "session": self.session_name,
                },
            )

            if response.status_code in (200, 201):
                logger.info("Video message sent", phone_number=phone_number, file=video_path)
                return True

            logger.warning(
                "Failed to send video message",
                status_code=response.status_code,
                response=response.text,
            )
            return False
        except Exception as e:
            logger.error(
                "Error sending video message",
                phone_number=phone_number,
                file=video_path,
                error=str(e),
            )
            return False

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
