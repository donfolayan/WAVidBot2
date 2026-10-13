import base64
import json

import httpx
import pytest

from src.wabotii.config.settings import Settings
from src.wabotii.services.waha import WAHAService


@pytest.mark.asyncio
async def test_send_video_uses_video_endpoint_and_preserves_file(tmp_path):
    video_bytes = b"mp4-with-video-and-audio"
    video_path = tmp_path / "facebook-reel.mp4"
    video_path.write_bytes(video_bytes)
    captured_request = None

    def handle_request(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(201, json={"id": "message-id"})

    settings = Settings(
        WAHA_BASE_URL="https://waha.example",
        WAHA_SESSION_NAME="WhatsApp-bot",
        WAHA_API_KEY="test-key",
    )
    service = WAHAService(settings)
    await service.client.aclose()
    service.client = httpx.AsyncClient(
        base_url=settings.waha_base_url,
        headers={"X-Api-Key": settings.waha_api_key},
        transport=httpx.MockTransport(handle_request),
    )

    try:
        assert await service.send_video_message("2348000000000@c.us", str(video_path))
    finally:
        await service.close()

    assert captured_request is not None
    assert captured_request.url.path == "/api/sendVideo"
    payload = json.loads(captured_request.content)
    assert payload["session"] == "WhatsApp-bot"
    assert payload["chatId"] == "2348000000000@c.us"
    assert payload["asNote"] is False
    assert payload["convert"] is False
    assert payload["file"]["mimetype"] == "video/mp4"
    assert base64.b64decode(payload["file"]["data"]) == video_bytes
