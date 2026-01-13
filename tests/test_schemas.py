"""Tests for API schemas."""

from src.wabotii.api.schemas import (
    TestDownloadRequest,
    TestDownloadResponse,
    WebhookResponse,
    HealthResponse
)


def test_test_download_request():
    """Test download request schema."""
    req = TestDownloadRequest(url="https://youtube.com/watch?v=test")
    assert req.url == "https://youtube.com/watch?v=test"


def test_test_download_response():
    """Test download response schema."""
    resp = TestDownloadResponse(
        local_path="downloads/test.mp4",
        file_size_mb=15.5,
        title="Test Video",
        duration=300
    )
    assert resp.local_path == "downloads/test.mp4"
    assert resp.file_size_mb == 15.5
    assert resp.duration == 300


def test_webhook_response():
    """Test webhook response schema."""
    resp = WebhookResponse(status="ok")
    assert resp.status == "ok"

    resp_with_msg = WebhookResponse(status="error", message="Test error")
    assert resp_with_msg.status == "error"
    assert resp_with_msg.message == "Test error"


def test_health_response():
    """Test health response schema."""
    resp = HealthResponse(
        status="healthy",
        version="0.1.0",
        waha_healthy=True
    )
    assert resp.status == "healthy"
    assert resp.version == "0.1.0"
    assert resp.waha_healthy is True
