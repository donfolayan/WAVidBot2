"""FastAPI routes for the application."""

import os
import time
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse

from ..config.settings import Settings, get_settings
from ..services.cloud import CloudinaryService
from ..services.database import DatabaseService
from ..services.video import download_video
from ..services.waha import WAHAService
from ..utils.helpers import setup_cookies
from ..utils.logging import get_logger
from .schemas import (
    HealthResponse,
    StatsResponse,
    TestDownloadRequest,
    TestDownloadResponse,
    WebhookResponse,
)

logger = get_logger(__name__)

router = APIRouter()

# Message cache to prevent duplicate processing
message_cache: Dict[str, float] = {}
MESSAGE_CACHE_TTL = 60
DEFAULT_VERIFY_TOKEN = "wa_downloader_test_token"

# Setup cookies at module load time
youtube_cookies_path, facebook_cookies_path = setup_cookies()


def _cleanup_local_file(file_path: str | None) -> None:
    """Remove a local file if it exists."""
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
            logger.info("Cleaned up local file", path=file_path)
        except Exception as e:
            logger.error("Error cleaning up local file", path=file_path, error=str(e))


def cleanup_message_cache() -> None:
    """Clean old entries from message cache."""
    global message_cache
    current_time = time.time()
    message_cache = {k: v for k, v in message_cache.items() if current_time - v < MESSAGE_CACHE_TTL}


def _request_token(request: Request) -> str:
    """Read a webhook token from a header, bearer token, or query string."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return (
        request.headers.get("x-wabotii-token")
        or request.headers.get("x-webhook-secret")
        or request.headers.get("x-api-key")
        or request.query_params.get("token")
        or ""
    ).strip()


def _webhook_is_authorized(request: Request, settings: Settings) -> bool:
    """Require a shared secret for production webhooks."""
    accepted_tokens = {settings.webhook_secret.strip()}
    if settings.verify_token != DEFAULT_VERIFY_TOKEN:
        accepted_tokens.add(settings.verify_token.strip())
    accepted_tokens = {token for token in accepted_tokens if token}

    if not accepted_tokens:
        return settings.dev_mode
    return _request_token(request) in accepted_tokens


def _sender_is_allowed(from_number: str, settings: Settings) -> bool:
    """Restrict downloads to configured WhatsApp senders when present."""
    allowed_numbers = settings.allowed_phone_number_set()
    if not allowed_numbers:
        return True
    return from_number in allowed_numbers or from_number.split("@", 1)[0] in allowed_numbers


async def handle_waha_message(
    payload: dict,
    waha_service: WAHAService,
    db_service: DatabaseService,
    cloud_service: CloudinaryService,
    settings: Settings,
) -> None:
    """Handle incoming message from WAHA webhook (WAHA format)."""
    try:
        from_number = payload.get("from")
        message_text = payload.get("body", "")

        if payload.get("fromMe") or payload.get("isStatus"):
            return

        # Skip if no text body
        if not message_text or not from_number:
            logger.info("Skipping message - no body or from")
            return

        if not _sender_is_allowed(from_number, settings):
            logger.warning("Ignoring message from unauthorized sender", from_number=from_number)
            return

        logger.info("Processing WAHA message", from_number=from_number, text=message_text)

        # Check if message contains a URL
        if "http" not in message_text.lower():
            help_message = """👋 Welcome to WABotII - WhatsApp Video Downloader!

Just send me a YouTube or Facebook video URL, and I'll download it for you.

Supported platforms:
• 📺 YouTube
• 📘 Facebook

Examples:
• https://www.youtube.com/watch?v=...
• https://www.facebook.com/...
• https://youtu.be/..."""
            await waha_service.send_text_message(from_number, help_message)
            return

        url = message_text.strip()
        logger.info("Processing URL", url=url)

        # Validate URL
        is_valid = any(
            [
                url.startswith("https://www.youtube.com"),
                url.startswith("https://youtube.com"),
                url.startswith("https://youtu.be"),
                url.startswith("https://www.facebook.com"),
                url.startswith("https://facebook.com"),
                url.startswith("https://fb.watch"),
                "facebook.com/share" in url,
            ]
        )

        if not is_valid:
            logger.warning("Invalid URL format", url=url)
            await waha_service.send_text_message(
                from_number, "❌ Please send a valid YouTube or Facebook video URL"
            )
            return

        if db_service.count_user_downloads_since(from_number, 24) >= settings.max_daily_downloads:
            logger.warning("Daily download limit reached", from_number=from_number)
            await waha_service.send_text_message(
                from_number, "Daily download limit reached. Please try again tomorrow."
            )
            return

        # Send downloading message
        await waha_service.send_text_message(from_number, "📥 Downloading video...")

        # Download video
        download_result = await download_video(url, youtube_cookies_path, facebook_cookies_path)

        if not download_result.local_path or download_result.error:
            logger.error("Download failed", url=url, error=download_result.error)
            error_msg = download_result.error or "Unknown error"
            if "checkpoint" in error_msg.lower():
                msg = "❌ Facebook security checkpoint detected. This video requires authentication.\n\nPlease try:\n• Making sure the video is public\n• Using a direct video link\n• Checking if the video is still available"
            else:
                msg = f"❌ Could not download video: {error_msg}"

            await waha_service.send_text_message(from_number, msg)
            return

        # Check file size
        file_size_mb = os.path.getsize(download_result.local_path) / (1024 * 1024)
        logger.info("Downloaded video", size_mb=f"{file_size_mb:.2f}")

        # Save to database
        db_service.save_download(from_number, url, download_result.local_path)

        # Try sending via WhatsApp directly for small files; upload larger files only.
        logger.info("Processing downloaded video delivery")
        try:
            success = False
            if file_size_mb <= settings.max_file_size_mb:
                success = await waha_service.send_video_message(
                    from_number, download_result.local_path
                )

            if success:
                await waha_service.send_text_message(
                    from_number, f"✅ {download_result.title}\n\nVideo sent successfully!"
                )
            else:
                logger.info("Uploading video to Cloudinary")
                await waha_service.send_text_message(from_number, "📤 Uploading to cloud...")

                upload_url, public_id = await cloud_service.async_upload_to_cloudinary(
                    download_result.local_path
                )

                if upload_url:
                    await waha_service.send_text_message(
                        from_number,
                        f"✅ {download_result.title}\n\n🎬 Watch here: {upload_url}\n\nLink expires in {settings.cloudinary_retention_hours} hours.",
                    )
                    db_service.update_download_url(from_number, url, upload_url, public_id)
                else:
                    await waha_service.send_text_message(
                        from_number, "❌ Failed to upload video. Please try again."
                    )
        finally:
            # Always clean up local file after processing
            _cleanup_local_file(download_result.local_path)

    except Exception as e:
        logger.error("Error handling WAHA message", error=str(e))
        try:
            await waha_service.send_text_message(
                payload.get("from", ""), f"❌ An error occurred: {str(e)}"
            )
        except Exception:  # noqa: E722
            pass


@router.get(
    "/",
    response_model=Dict[str, str],
    summary="Health Check",
    description="Simple health check endpoint to verify the API is running.",
    tags=["Health"],
)
async def root() -> Dict[str, str]:
    """Health check endpoint."""
    return {"message": "WABotII is running!"}


@router.get(
    "/health", response_model=HealthResponse, summary="Detailed Health Status", tags=["Health"]
)
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """Cheap health status for container/runtime checks."""
    return HealthResponse(status="healthy", version="0.1.0", waha_healthy=None)


@router.get(
    "/health/waha",
    response_model=HealthResponse,
    summary="WAHA Health Status",
    tags=["Health"],
)
async def waha_health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """Get detailed WAHA health status on demand."""
    waha_service = WAHAService(settings)
    try:
        waha_healthy = await waha_service.health_check()
    finally:
        await waha_service.close()

    return HealthResponse(
        status="healthy" if waha_healthy else "degraded", version="0.1.0", waha_healthy=waha_healthy
    )


@router.get("/live", response_model=Dict[str, str], summary="Liveness Check", tags=["Health"])
async def live() -> Dict[str, str]:
    """Cheap liveness check."""
    return {"status": "ok"}


@router.get(
    "/stats", response_model=StatsResponse, summary="Download Statistics", tags=["Statistics"]
)
async def stats(settings: Settings = Depends(get_settings)) -> StatsResponse:
    """Get download statistics."""
    db_service = DatabaseService(settings)
    stats_dict = db_service.get_download_stats()
    return StatsResponse(**stats_dict)


@router.get(
    "/webhook",
    summary="WhatsApp Webhook Verification",
    description="Handles webhook verification from WAHA.",
    tags=["WhatsApp Webhook"],
)
async def verify_webhook(request: Request, settings: Settings = Depends(get_settings)) -> Response:
    """Handle webhook verification from WAHA."""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    logger.info("Webhook verification attempt", mode=mode, has_token=bool(token))

    if mode and token:
        if mode == "subscribe" and token == settings.verify_token:
            logger.info("Webhook verified successfully")
            return Response(content=challenge, media_type="text/plain")
        else:
            logger.warning("Invalid verification token")
            return Response(status_code=403)

    return Response(status_code=400)


@router.post(
    "/webhook",
    response_model=WebhookResponse,
    summary="Receive WhatsApp Messages",
    description="Receives incoming webhooks from WAHA containing messages.",
    tags=["WhatsApp Webhook"],
)
async def receive_webhook(
    request: Request, settings: Settings = Depends(get_settings)
) -> WebhookResponse:
    """Handle incoming webhooks from WAHA."""
    try:
        if not _webhook_is_authorized(request, settings):
            logger.warning("Rejected unauthorized webhook")
            raise HTTPException(status_code=401, detail="Unauthorized webhook")

        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

        logger.info("Received webhook payload")

        waha_service = WAHAService(settings)
        db_service = DatabaseService(settings)
        cloud_service = CloudinaryService(settings)

        try:
            # Check for WAHA format (event + payload)
            if "event" in body and body["event"] == "message" and "payload" in body:
                payload = body["payload"]
                message_id = payload.get("id")

                # Check for duplicate messages
                if message_id:
                    if message_id in message_cache:
                        last_processed = message_cache[message_id]
                        if time.time() - last_processed < MESSAGE_CACHE_TTL:
                            logger.info(
                                "Duplicate message detected, skipping", message_id=message_id
                            )
                            return WebhookResponse(status="ok")

                    # Update cache
                    message_cache[message_id] = time.time()
                    cleanup_message_cache()

                # Handle WAHA message
                logger.info("Received WAHA message")
                await handle_waha_message(
                    payload, waha_service, db_service, cloud_service, settings
                )

            else:
                logger.warning("Unrecognized webhook format", keys=list(body.keys()))

            return WebhookResponse(status="ok")
        finally:
            await waha_service.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in webhook handler", error=str(e))
        return WebhookResponse(status="error", message=str(e))


@router.get("/privacy", summary="Privacy Policy", tags=["Legal"])
async def privacy_policy() -> HTMLResponse:
    """Serve Privacy Policy."""
    try:
        with open("legal/privacy.html", "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content=content)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Privacy Policy not found")


@router.get("/terms", summary="Terms and Conditions", tags=["Legal"])
async def terms_of_service() -> HTMLResponse:
    """Serve Terms and Conditions."""
    try:
        with open("legal/terms.html", "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content=content)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Terms and Conditions not found")


# Development endpoints
@router.post(
    "/test-download",
    response_model=TestDownloadResponse,
    summary="Test Video Download",
    description="Development endpoint for testing video downloads.",
    tags=["Development"],
)
async def test_download(
    request: TestDownloadRequest, settings: Settings = Depends(get_settings)
) -> TestDownloadResponse:
    """Test video download functionality."""
    if not settings.dev_mode:
        raise HTTPException(status_code=403, detail="Test endpoint only available in DEV_MODE")

    if not request.url:
        raise HTTPException(status_code=400, detail="No URL provided")

    try:
        result = await download_video(request.url, youtube_cookies_path, facebook_cookies_path)
        return TestDownloadResponse(
            local_path=result.local_path,
            file_size_mb=result.file_size_mb,
            title=result.title,
            duration=result.duration,
            error=result.error,
        )
    except Exception as e:
        logger.error("Download test failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")
