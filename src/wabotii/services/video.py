"""Video download service using yt-dlp."""

import os
import asyncio
import yt_dlp
import requests
import http.cookiejar
import random
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

from ..utils.logging import get_logger
from ..utils.helpers import sanitize_filename
import tempfile
import shutil

logger = get_logger(__name__)


@dataclass
class VideoDownloadResult:
    """Result of video download operation."""

    local_path: Optional[str]
    file_size_mb: Optional[float]
    title: Optional[str] = None
    duration: Optional[int] = None
    error: Optional[str] = None


def resolve_facebook_share(url: str, cookies_path: Optional[str] = None) -> str:
    """Resolve Facebook share URL to actual video URL."""
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ]

    user_agent = random.choice(user_agents)
    headers = {
        "User-Agent": user_agent,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Cache-Control": "max-age=0"
    }

    cookies = None
    if cookies_path and os.path.exists(cookies_path):
        cj = http.cookiejar.MozillaCookieJar()
        try:
            cj.load(cookies_path, ignore_discard=True, ignore_expires=True)
            cookies = {c.name: c.value for c in cj}
            logger.info("Loaded Facebook cookies", count=len(cookies))
        except Exception as e:
            logger.warning("Could not load cookies", cookies_path=cookies_path, error=str(e))

    try:
        # Add delay to appear human-like
        await_time = random.uniform(1, 3)
        logger.debug("Waiting before Facebook request", seconds=await_time)
        # Can't use await here, so just use time.sleep
        import time
        time.sleep(await_time)

        response = requests.get(
            url,
            headers=headers,
            cookies=cookies,
            allow_redirects=True,
            timeout=15
        )
        final_url = response.url

        # Check for security checkpoints
        if any(keyword in str(final_url).lower() for keyword in ["checkpoint", "login", "security"]):
            error_msg = f"Facebook security checkpoint detected: {final_url}"
            logger.error("Facebook checkpoint detected", url=final_url)
            raise Exception(error_msg)

        if any(keyword in response.text.lower() for keyword in ["robot", "bot", "security check", "checkpoint"]):
            logger.error("Facebook security challenge detected")
            raise Exception("Facebook security challenge detected")

        return str(final_url)
    except Exception as e:
        logger.error("Error resolving Facebook share URL", error=str(e))
        raise


def _download_sync(url: str, ydl_opts: dict) -> dict:
    """Synchronous helper to run yt-dlp and return basic metadata."""
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

            if info:
                downloaded_path = ydl.prepare_filename(info)
                title = info.get("title", "video")
                sanitized_title = sanitize_filename(title)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                new_filename = f"original_{sanitized_title}_{timestamp}.mp4"
                new_path = os.path.join("downloads", new_filename)

                if downloaded_path != new_path:
                    try:
                        os.rename(downloaded_path, new_path)
                        logger.info("Renamed downloaded file", old=downloaded_path, new=new_path)
                    except Exception:
                        try:
                            shutil.copy2(downloaded_path, new_path)
                            os.remove(downloaded_path)
                            logger.info("Copied and removed file", from_path=downloaded_path, to_path=new_path)
                        except Exception:
                            new_path = downloaded_path

                if os.path.exists(new_path):
                    file_size_mb = os.path.getsize(new_path) / (1024 * 1024)

                    if file_size_mb == 0:
                        try:
                            os.remove(new_path)
                        except:
                            pass
                        raise Exception("The downloaded file is empty")

                    duration = info.get("duration")
                    logger.info(
                        "Video downloaded successfully",
                        path=new_path,
                        size_mb=file_size_mb,
                        duration=duration
                    )
                    return {
                        "local_path": new_path,
                        "file_size_mb": file_size_mb,
                        "title": title,
                        "duration": duration,
                    }
    except Exception as e:
        # Propagate exception to caller where it will be handled
        raise


async def download_video(
    url: str,
    youtube_cookies_path: Optional[str] = None,
    facebook_cookies_path: Optional[str] = None
) -> VideoDownloadResult:
    """Download video from YouTube or Facebook using yt-dlp."""
    logger.info("Starting video download", url=url)

    # Add delay to appear more human-like
    await asyncio.sleep(2)

    cookies_path = None
    if "youtube.com" in url or "youtu.be" in url:
        cookies_path = youtube_cookies_path
        if cookies_path:
            logger.info("Using YouTube cookies", path=cookies_path)
    elif "facebook.com" in url:
        cookies_path = facebook_cookies_path
        if cookies_path:
            logger.info("Using Facebook cookies", path=cookies_path)

    # Handle Facebook share URLs (run resolution in a thread to avoid blocking)
    if "facebook.com/share" in url:
        logger.info("Detected Facebook share URL - resolving...")
        try:
            url = await asyncio.to_thread(resolve_facebook_share, url, cookies_path)
            logger.info("Resolved share URL", resolved_url=url)
        except Exception as e:
            logger.error("Failed to resolve Facebook share URL", error=str(e))
            return VideoDownloadResult(
                local_path=None,
                file_size_mb=None,
                error=str(e)
            )

    # Configure yt-dlp options
    ydl_opts = {
        "format": "best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best",
        "outtmpl": "downloads/original_%(id)s.%(ext)s",
        "quiet": False,
        "no_warnings": False,
        "merge_output_format": "mp4",
        "verbose": False,
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.70 Safari/537.36",
    }

    if cookies_path:
        ydl_opts["cookiefile"] = cookies_path

    try:
        # Run the blocking yt-dlp download in a thread to avoid blocking the event loop
        result = await asyncio.to_thread(_download_sync, url, ydl_opts)
        return VideoDownloadResult(
            local_path=result.get("local_path"),
            file_size_mb=result.get("file_size_mb"),
            title=result.get("title"),
            duration=result.get("duration"),
        )
    except Exception as e:
        error_str = str(e).lower()
        if "requested format not available" in error_str:
            error_msg = "Video format not available - might be private or deleted"
        elif "video is private" in error_str:
            error_msg = "Video is private"
        elif "sign in to view" in error_str:
            error_msg = "Video requires authentication"
        else:
            error_msg = str(e)
        logger.error("yt-dlp download error", error=error_msg)
        return VideoDownloadResult(
            local_path=None,
            file_size_mb=None,
            error=error_msg
        )
