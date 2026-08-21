"""Cost-conscious video downloads with resilient yt-dlp defaults."""

import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import yt_dlp
from yt_dlp.networking.impersonate import ImpersonateTarget
from yt_dlp.utils import DownloadError

from ..utils.helpers import sanitize_filename
from ..utils.logging import get_logger

logger = get_logger(__name__)


class VideoPlatform(StrEnum):
    """Platforms intentionally supported by the bot."""

    YOUTUBE = "youtube"
    FACEBOOK = "facebook"


class DownloadErrorCode(StrEnum):
    """Stable failure categories that do not expose extractor internals to users."""

    AUTH_REQUIRED = "auth_required"
    FORBIDDEN = "forbidden"
    TOO_LARGE = "too_large"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED_URL = "unsupported_url"
    EXTRACTOR_CHANGED = "extractor_changed"
    DOWNLOAD_FAILED = "download_failed"


@dataclass
class VideoDownloadResult:
    """Result of a video download operation."""

    local_path: Optional[str]
    file_size_mb: Optional[float]
    title: Optional[str] = None
    duration: Optional[int] = None
    error: Optional[str] = None
    error_code: Optional[DownloadErrorCode] = None


def detect_platform(url: str) -> VideoPlatform:
    """Validate a URL and return its supported platform."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Please send a complete http or https URL.")

    hostname = parsed.hostname.lower().removeprefix("www.")
    if hostname == "youtu.be" or hostname.endswith(".youtube.com") or hostname == "youtube.com":
        return VideoPlatform.YOUTUBE
    if hostname == "fb.watch" or hostname.endswith(".facebook.com") or hostname == "facebook.com":
        return VideoPlatform.FACEBOOK
    raise ValueError("Only YouTube and Facebook links are supported.")


def _format_selector(max_height: int, max_download_size_mb: int) -> str:
    """Prefer a ready-to-send MP4 before formats that require an ffmpeg merge."""
    single_file_filter = (
        f"[filesize<?{max_download_size_mb}M][filesize_approx<?{max_download_size_mb}M]"
    )
    # A 50/50 split rejects normal low-bitrate audio/video pairs because sizes
    # are reported in MiB while yt-dlp's M suffix is decimal. The final hard
    # byte check still enforces the combined limit after merging.
    component_limit_mb = max(1, (max_download_size_mb * 3) // 4)
    component_filter = (
        f"[filesize<?{component_limit_mb}M][filesize_approx<?{component_limit_mb}M]"
    )
    return (
        f"best[ext=mp4][vcodec^=avc1][height<={max_height}]{single_file_filter}"
        f"/bestvideo[ext=mp4][vcodec^=avc1][height<={max_height}]{component_filter}"
        f"+bestaudio[ext=m4a]{component_filter}"
        f"/best[height<={max_height}]{single_file_filter}/best{single_file_filter}"
    )


def _friendly_error(platform: VideoPlatform, raw_error: str) -> tuple[DownloadErrorCode, str]:
    """Turn volatile extractor output into useful, stable WhatsApp messages."""
    error = raw_error.lower()
    platform_name = platform.value.title()

    if "file is larger than max-filesize" in error or "maximum file size" in error:
        return DownloadErrorCode.TOO_LARGE, "This video is too large for the bot's download limit."
    if "timed out" in error or "download deadline exceeded" in error:
        return DownloadErrorCode.TIMEOUT, "The download took too long. Please try again later."
    if any(text in error for text in ("sign in", "login required", "cookies are needed", "confirm your age")):
        return DownloadErrorCode.AUTH_REQUIRED, (
            f"{platform_name} requires a logged-in session for this video. The configured session may have expired."
        )
    if any(text in error for text in ("private video", "video is private", "friends only")):
        return DownloadErrorCode.AUTH_REQUIRED, "This video is private or restricted to its audience."
    if any(text in error for text in ("403", "forbidden", "captcha", "not a bot")):
        return DownloadErrorCode.FORBIDDEN, (
            f"{platform_name} blocked this request. Please try again later or refresh the configured session."
        )
    if any(text in error for text in ("cannot parse data", "unable to extract", "no video formats found")):
        return DownloadErrorCode.EXTRACTOR_CHANGED, (
            f"{platform_name} changed how this video is delivered. Please try again after the bot is updated."
        )
    if any(text in error for text in ("unavailable", "removed", "deleted", "not found")):
        return DownloadErrorCode.UNAVAILABLE, "This video is unavailable, deleted, or restricted."
    if "unsupported url" in error:
        return DownloadErrorCode.UNSUPPORTED_URL, "This type of link is not supported."
    return DownloadErrorCode.DOWNLOAD_FAILED, "The video could not be downloaded. Please try again later."


def _could_benefit_from_cookies(raw_error: str) -> bool:
    """Avoid an authenticated retry for failures that cookies cannot repair."""
    error = raw_error.lower()
    return any(
        text in error
        for text in (
            "sign in",
            "login",
            "private",
            "cookies",
            "403",
            "forbidden",
            "captcha",
            "cannot parse data",
            "unable to extract",
            "no video formats found",
        )
    )


def _find_downloaded_file(work_dir: str) -> Path:
    """Find yt-dlp's final output without relying on a pre-merge filename."""
    candidates = [
        path
        for path in Path(work_dir).rglob("*")
        if path.is_file() and path.suffix not in {".part", ".ytdl"}
    ]
    if not candidates:
        raise DownloadError("Download completed without an output file")
    return max(candidates, key=lambda path: path.stat().st_size)


def _download_sync(
    url: str,
    platform: VideoPlatform,
    cookie_path: Optional[str],
    destination_dir: str,
    timeout_seconds: int,
    max_height: int,
    max_download_size_mb: int,
    youtube_pot_provider_script_dir: str,
) -> dict[str, Any]:
    """Run one blocking yt-dlp attempt."""
    work_dir = tempfile.mkdtemp(prefix=f"wabotii_{platform.value}_", dir=destination_dir)
    deadline = time.monotonic() + timeout_seconds
    max_bytes = max_download_size_mb * 1024 * 1024

    def enforce_limits(progress: dict[str, Any]) -> None:
        if time.monotonic() > deadline:
            raise DownloadError("Download deadline exceeded")
        downloaded = progress.get("downloaded_bytes") or 0
        if downloaded > max_bytes:
            raise DownloadError("Maximum file size exceeded")

    ydl_opts: dict[str, Any] = {
        "format": _format_selector(max_height, max_download_size_mb),
        "outtmpl": os.path.join(work_dir, "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
        "max_filesize": max_bytes,
        "socket_timeout": min(30, timeout_seconds),
        "retries": 2,
        "fragment_retries": 2,
        "extractor_retries": 2,
        "concurrent_fragment_downloads": 1,
        "progress_hooks": [enforce_limits],
        "postprocessor_hooks": [enforce_limits],
    }

    # Browser TLS impersonation materially helps Facebook, but forcing it for every
    # extractor can make otherwise-good requests less reliable.
    if platform is VideoPlatform.FACEBOOK:
        ydl_opts["impersonate"] = ImpersonateTarget()
    elif youtube_pot_provider_script_dir:
        ydl_opts["extractor_args"] = {
            "youtube": {"player_client": ["mweb"]},
            "youtubepot-bgutilscript": {
                "server_home": [youtube_pot_provider_script_dir]
            },
        }
    if cookie_path and os.path.isfile(cookie_path):
        ydl_opts["cookiefile"] = cookie_path

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:  # type: ignore[arg-type]
            info = ydl.extract_info(url, download=True)
        if not info:
            raise DownloadError("Download returned no video information")

        downloaded_path = _find_downloaded_file(work_dir)
        requested_downloads = info.get("requested_downloads") or []
        remaining_outputs = [
            path
            for path in Path(work_dir).rglob("*")
            if path.is_file() and path.suffix not in {".part", ".ytdl"}
        ]
        if len(requested_downloads) > 1 and len(remaining_outputs) > 1:
            raise DownloadError("ffmpeg could not merge the video and audio streams")
        if downloaded_path.stat().st_size <= 0:
            raise DownloadError("The downloaded file is empty")
        if downloaded_path.stat().st_size > max_bytes:
            raise DownloadError("Maximum file size exceeded")

        title = info.get("title") or f"{platform.value}_video"
        extension = downloaded_path.suffix or ".mp4"
        final_name = f"{sanitize_filename(title)}{extension}"
        final_path = Path(destination_dir, final_name)
        shutil.move(str(downloaded_path), final_path)
        return {
            "local_path": str(final_path),
            "file_size_mb": final_path.stat().st_size / (1024 * 1024),
            "title": title,
            "duration": info.get("duration"),
        }
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _download_facebook_with_gallery_sync(
    url: str,
    cookie_path: Optional[str],
    destination_dir: str,
    timeout_seconds: int,
    max_download_size_mb: int,
) -> dict[str, Any]:
    """Use gallery-dl as an independent Facebook extraction fallback."""
    work_dir = tempfile.mkdtemp(prefix="wabotii_facebook_gallery_", dir=destination_dir)
    max_bytes = max_download_size_mb * 1024 * 1024
    command = [
        sys.executable,
        "-m",
        "gallery_dl",
        "--config-ignore",
        "--destination",
        work_dir,
        "--filename",
        "{id}.{extension}",
        "--filesize-max",
        f"{max_download_size_mb}M",
        "--http-timeout",
        str(min(30, timeout_seconds)),
        "--retries",
        "2",
    ]
    if cookie_path and os.path.isfile(cookie_path):
        command.extend(["--cookies", cookie_path])
    command.append(url)

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=max(10, timeout_seconds),
            check=False,
        )
        try:
            downloaded_path = _find_downloaded_file(work_dir)
        except DownloadError as exc:
            diagnostic = (completed.stderr or completed.stdout or str(exc))[-1000:]
            raise DownloadError(f"gallery-dl did not produce a video: {diagnostic}") from exc

        if downloaded_path.stat().st_size <= 0:
            raise DownloadError("The gallery-dl output file is empty")
        if downloaded_path.stat().st_size > max_bytes:
            raise DownloadError("Maximum file size exceeded")

        final_path = Path(destination_dir, f"{sanitize_filename('Facebook video')}{downloaded_path.suffix}")
        shutil.move(str(downloaded_path), final_path)
        return {
            "local_path": str(final_path),
            "file_size_mb": final_path.stat().st_size / (1024 * 1024),
            "title": "Facebook video",
            "duration": None,
        }
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


_download_semaphore: Optional[asyncio.Semaphore] = None
_download_semaphore_limit: Optional[int] = None


def _limiter(limit: int) -> asyncio.Semaphore:
    """Create the process-local download limiter lazily for the active event loop."""
    global _download_semaphore, _download_semaphore_limit
    limit = max(1, limit)
    if _download_semaphore is None or _download_semaphore_limit != limit:
        _download_semaphore = asyncio.Semaphore(limit)
        _download_semaphore_limit = limit
    return _download_semaphore


async def download_video(
    url: str,
    youtube_cookies_path: Optional[str] = None,
    facebook_cookies_path: Optional[str] = None,
    *,
    timeout_seconds: int = 300,
    max_height: int = 720,
    max_download_size_mb: int = 64,
    max_concurrent_downloads: int = 1,
    youtube_pot_provider_script_dir: str = "",
) -> VideoDownloadResult:
    """Download from YouTube/Facebook anonymously, using cookies only if needed."""
    try:
        platform = detect_platform(url)
    except ValueError as exc:
        return VideoDownloadResult(
            local_path=None,
            file_size_mb=None,
            error=str(exc),
            error_code=DownloadErrorCode.UNSUPPORTED_URL,
        )

    cookie_path = (
        youtube_cookies_path if platform is VideoPlatform.YOUTUBE else facebook_cookies_path
    )
    # Public media should not risk or depend on a personal account. Authentication
    # becomes a fallback only when an anonymous extraction fails.
    attempts: list[Optional[str]] = [None]
    if cookie_path and os.path.isfile(cookie_path):
        attempts.append(cookie_path)

    os.makedirs("downloads", exist_ok=True)
    last_error = "Download failed"
    overall_deadline = time.monotonic() + max(10, timeout_seconds)
    async with _limiter(max_concurrent_downloads):
        for attempt_number, attempt_cookie in enumerate(attempts, start=1):
            remaining_seconds = int(overall_deadline - time.monotonic())
            if remaining_seconds <= 0:
                last_error = "Download deadline exceeded"
                break
            logger.info(
                "Starting video download",
                platform=platform.value,
                attempt=attempt_number,
                authenticated=bool(attempt_cookie),
            )
            try:
                result = await asyncio.to_thread(
                    _download_sync,
                    url,
                    platform,
                    attempt_cookie,
                    "downloads",
                    remaining_seconds,
                    max(144, max_height),
                    max(1, max_download_size_mb),
                    youtube_pot_provider_script_dir,
                )
                return VideoDownloadResult(**result)
            except Exception as exc:
                last_error = str(exc)
                logger.warning(
                    "Video download attempt failed",
                    platform=platform.value,
                    attempt=attempt_number,
                    authenticated=bool(attempt_cookie),
                    error=last_error,
                )
                if attempt_cookie is None and len(attempts) > 1 and not _could_benefit_from_cookies(last_error):
                    break

        fallback_error_code, _ = _friendly_error(platform, last_error)
        if platform is VideoPlatform.FACEBOOK and fallback_error_code not in {
            DownloadErrorCode.TOO_LARGE,
            DownloadErrorCode.TIMEOUT,
            DownloadErrorCode.UNAVAILABLE,
            DownloadErrorCode.UNSUPPORTED_URL,
        }:
            logger.info("Trying gallery-dl Facebook fallback", authenticated=bool(cookie_path))
            try:
                remaining_seconds = int(overall_deadline - time.monotonic())
                if remaining_seconds <= 0:
                    raise DownloadError("Download deadline exceeded")
                result = await asyncio.to_thread(
                    _download_facebook_with_gallery_sync,
                    url,
                    cookie_path,
                    "downloads",
                    remaining_seconds,
                    max(1, max_download_size_mb),
                )
                return VideoDownloadResult(**result)
            except Exception as exc:
                logger.warning("gallery-dl Facebook fallback failed", error=str(exc))
                if "deadline exceeded" in str(exc).lower():
                    last_error = str(exc)

    error_code, message = _friendly_error(platform, last_error)
    logger.error("Video download failed", platform=platform.value, error_code=error_code.value)
    return VideoDownloadResult(
        local_path=None,
        file_size_mb=None,
        error=message,
        error_code=error_code,
    )
