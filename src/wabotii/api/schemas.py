"""Pydantic schemas for API requests and responses."""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class TestDownloadRequest(BaseModel):
    """Request for testing video download."""

    url: str = Field(..., description="Video URL to download")

    model_config = {
        "json_schema_extra": {
            "example": {
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
            }
        }
    }


class TestDownloadResponse(BaseModel):
    """Response for video download."""

    local_path: Optional[str] = Field(None, description="Local path of downloaded video")
    file_size_mb: Optional[float] = Field(None, description="File size in MB")
    title: Optional[str] = Field(None, description="Video title")
    duration: Optional[int] = Field(None, description="Video duration in seconds")
    error: Optional[str] = Field(None, description="Error message if download failed")

    model_config = {
        "json_schema_extra": {
            "example": {
                "local_path": "downloads/video_title_20240112_123456.mp4",
                "file_size_mb": 15.5,
                "title": "Video Title",
                "duration": 300,
                "error": None
            }
        }
    }


class WebhookResponse(BaseModel):
    """Response for webhook processing."""

    status: str = Field(..., description="Processing status")
    message: Optional[str] = Field(None, description="Optional status message")

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "ok",
                "message": "Message processed successfully"
            }
        }
    }


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Error details")
    request_id: Optional[str] = Field(None, description="Request tracking ID")

    model_config = {
        "json_schema_extra": {
            "example": {
                "error": "Invalid URL",
                "detail": "URL must be from YouTube or Facebook",
                "request_id": "req_12345"
            }
        }
    }


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(..., description="Service status")
    version: str = Field(..., description="API version")
    waha_healthy: bool = Field(..., description="WAHA service health status")

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "healthy",
                "version": "0.1.0",
                "waha_healthy": True
            }
        }
    }


class StatsResponse(BaseModel):
    """Statistics response."""

    total_downloads: int = Field(..., description="Total number of downloads")
    total_users: int = Field(..., description="Total number of users")
    total_size_mb: float = Field(..., description="Total size downloaded in MB")

    model_config = {
        "json_schema_extra": {
            "example": {
                "total_downloads": 150,
                "total_users": 25,
                "total_size_mb": 2450.5
            }
        }
    }
