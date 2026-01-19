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

# Setup cookies at module load time
youtube_cookies_path, facebook_cookies_path = setup_cookies()


def cleanup_message_cache() -> None:
    """Clean old entries from message cache."""
    global message_cache
    current_time = time.time()
    message_cache = {k: v for k, v in message_cache.items() if current_time - v < MESSAGE_CACHE_TTL}


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

        # Skip if no text body
        if not message_text or not from_number:
            logger.info("Skipping message - no body or from")
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

        # Try sending via WhatsApp directly first, fall back to Cloudinary if it fails
        logger.info("Attempting to send video via WhatsApp")
        success = await waha_service.send_video_message(from_number, download_result.local_path)

        if success:
            await waha_service.send_text_message(
                from_number, f"✅ {download_result.title}\n\nVideo sent successfully!"
            )
        else:
            # Fallback to Cloudinary if direct sending fails
            logger.info("Direct sending failed, falling back to Cloudinary upload")
            await waha_service.send_text_message(from_number, "📤 Uploading to cloud...")

            upload_url, public_id = await cloud_service.async_upload_to_cloudinary(
                download_result.local_path
            )

            if upload_url:
                await waha_service.send_text_message(
                    from_number,
                    f"✅ {download_result.title}\n\n🎬 Watch here: {upload_url}\n\nLink expires in {settings.cloudinary_retention_hours} hours.",
                )
                db_service.update_download_url(from_number, url, upload_url)
            else:
                await waha_service.send_text_message(
                    from_number, "❌ Failed to upload video. Please try again."
                )

    except Exception as e:
        logger.error("Error handling WAHA message", error=str(e))
        try:
            await waha_service.send_text_message(
                payload.get("from", ""), f"❌ An error occurred: {str(e)}"
            )
        except Exception:  # noqa: E722
            pass


async def handle_message_update(
    value: dict,
    waha_service: WAHAService,
    db_service: DatabaseService,
    cloud_service: CloudinaryService,
    settings: Settings,
) -> None:
    """Handle incoming message from WAHA webhook."""
    try:
        messages = value.get("messages", [])
        for message in messages:
            if message.get("type") == "text":
                from_number = message["from"]
                message_text = message["text"]["body"]

                logger.info("Received text message", from_number=from_number, text=message_text)

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

                # Send downloading message
                await waha_service.send_text_message(from_number, "📥 Downloading video...")

                # Download video
                download_result = await download_video(
                    url, youtube_cookies_path, facebook_cookies_path
                )

                if not download_result.local_path or download_result.error:
                    logger.error("Download failed", url=url, error=download_result.error)
                    error_msg = download_result.error or "Unknown error"
                    if "checkpoint" in error_msg.lower():
                        msg = "❌ Facebook security checkpoint detected. This video requires authentication.\n\nPlease try:\n• Making sure the video is public\n• Using a direct video link\n• Checking if the video is still available"
                    else:
                        msg = f"❌ Could not download video: {error_msg}"
                    await waha_service.send_text_message(from_number, msg)
                    return

                file_size = download_result.file_size_mb or 0
                logger.info("Video downloaded", file_size_mb=file_size)

                # Record in database
                try:
                    user_id = db_service.get_or_create_user(from_number)
                    db_service.record_download(
                        user_id, url, download_result.title or "Unknown", file_size
                    )
                except Exception as e:
                    logger.error("Error recording download", error=str(e))

                # Attempt to send video directly if small enough
                cloudinary_url = None
                video_sent_to_chat = False

                if file_size < settings.max_file_size_mb:
                    logger.info("Video is small, attempting direct send", size_mb=file_size)
                    await waha_service.send_text_message(
                        from_number,
                        "🎥 Here's your video! Uploading to Cloudinary for a shareable link...",
                    )

                    # Try to send video
                    try:
                        success = await waha_service.send_video_message(
                            from_number, download_result.local_path
                        )
                        if success:
                            video_sent_to_chat = True
                            logger.info("Video sent successfully to chat")
                            await waha_service.send_text_message(
                                from_number, "✅ Video sent successfully to chat!"
                            )
                    except Exception as e:
                        logger.error("Error sending video", error=str(e))
                        await waha_service.send_text_message(
                            from_number,
                            f"⚠️ Could not send video directly ({file_size:.2f} MB). Uploading to Cloudinary...",
                        )

                    # Upload to Cloudinary
                    try:
                        cloudinary_url, _ = await cloud_service.async_upload_to_cloudinary(
                            download_result.local_path
                        )
                        logger.info("Cloudinary upload complete", url=cloudinary_url)
                    except Exception as e:
                        logger.error("Cloudinary upload failed", error=str(e))
                else:
                    logger.info(
                        "Video is too large, uploading to Cloudinary only", size_mb=file_size
                    )
                    await waha_service.send_text_message(
                        from_number,
                        f"📤 Video is {file_size:.2f} MB - uploading to Cloudinary for a shareable link...",
                    )

                    try:
                        cloudinary_url, _ = await cloud_service.async_upload_to_cloudinary(
                            download_result.local_path
                        )
                        logger.info("Cloudinary upload complete", url=cloudinary_url)
                        # Delete local file after upload
                        os.remove(download_result.local_path)
                    except Exception as e:
                        logger.error("Cloudinary upload failed", error=str(e))
                        cloudinary_url = None

                # Send Cloudinary link if available
                if cloudinary_url:
                    if video_sent_to_chat:
                        message = f"☁️ Cloudinary Link ({file_size:.2f} MB):\n{cloudinary_url}"
                    else:
                        message = f"☁️ Cloudinary Link ({file_size:.2f} MB):\n{cloudinary_url}\n\nNote: Video was too large to send directly in chat."
                    await waha_service.send_text_message(from_number, message)
                else:
                    if video_sent_to_chat:
                        await waha_service.send_text_message(
                            from_number, "✅ Video sent to chat! (Cloudinary upload failed)"
                        )
                    else:
                        await waha_service.send_text_message(
                            from_number, "❌ Error: Could not upload to Cloudinary."
                        )

                # Clean up local file
                try:
                    if not video_sent_to_chat and os.path.exists(download_result.local_path):
                        os.remove(download_result.local_path)
                except Exception as e:
                    logger.error("Error deleting local file", error=str(e))

    except Exception as e:
        logger.error("Error in message update handler", error=str(e))


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
    """Get detailed health status."""
    waha_service = WAHAService(settings)
    try:
        waha_healthy = await waha_service.health_check()
    finally:
        await waha_service.close()

    return HealthResponse(
        status="healthy" if waha_healthy else "degraded", version="0.1.0", waha_healthy=waha_healthy
    )


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
        # Read raw body for debugging, then parse JSON
        raw_body = await request.body()
        try:
            body = await request.json()
        except Exception:
            body = None

        # Print raw payload to stdout so it appears directly in container logs
        try:
            print("RAW_WEBHOOK_BODY:", raw_body.decode(errors="replace"))
        except Exception:
            print("RAW_WEBHOOK_BODY: <binary>")

        logger.info("Received webhook payload", payload=body)

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

            # Also keep support for old format if needed
            elif "data" in body:
                value = body["data"]

                # Check if this is a message
                if "messages" in value:
                    logger.info("Received new message (old format)")

                    # Check for duplicate messages
                    message = value.get("messages", [{}])[0]
                    message_id = message.get("id")

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

                        # Clean old cache entries
                        cleanup_message_cache()

                    # Handle the message
                    await handle_message_update(
                        value, waha_service, db_service, cloud_service, settings
                    )

                elif "statuses" in value:
                    logger.info("Received status update")

            else:
                logger.warning("Unrecognized webhook format", keys=list(body.keys()))

            return WebhookResponse(status="ok")
        finally:
            await waha_service.close()

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
