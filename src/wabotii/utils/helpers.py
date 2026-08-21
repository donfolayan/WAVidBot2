"""Helper utilities."""

import base64
import os
import re
import tempfile
from datetime import datetime
from typing import Optional

from .logging import get_logger

logger = get_logger(__name__)


def cookie_names(cookie_data: bytes) -> set[str]:
    """Read cookie names from Netscape data without exposing their values."""
    names: set[str] = set()
    text = cookie_data.decode("utf-8", errors="replace")
    for line in text.splitlines():
        if not line or (line.startswith("#") and not line.startswith("#HttpOnly_")):
            continue
        fields = line.split("\t")
        if len(fields) >= 7:
            names.add(fields[5])
    return names


def log_cookie_session_status(platform: str, cookie_data: bytes) -> None:
    """Log whether an exported cookie set contains the platform login session."""
    names = cookie_names(cookie_data)
    required = {
        "youtube": {"SAPISID", "__Secure-3PAPISID", "LOGIN_INFO"},
        "facebook": {"c_user", "xs"},
    }[platform]
    missing = sorted(required - names)
    if missing:
        logger.warning(
            "Cookie file may not contain an authenticated session",
            platform=platform,
            cookie_count=len(names),
            missing_cookie_names=missing,
        )
    else:
        logger.info(
            "Authenticated cookie session detected",
            platform=platform,
            cookie_count=len(names),
        )


def sanitize_filename(filename: str) -> str:
    """Sanitize filename by removing special characters and emojis."""
    # Remove special characters and emojis
    filename = re.sub(r"[^\w\s-]", "", filename)
    # Replace multiple spaces with single space
    filename = re.sub(r"\s+", " ", filename)
    # Truncate if too long
    if len(filename) > 50:
        filename = filename[:47] + "..."
    # Add timestamp for uniqueness
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{filename}_{timestamp}"
    return filename.strip()


def setup_cookies() -> tuple[Optional[str], Optional[str]]:
    """Create cookies files from base64-encoded environment variables at runtime."""
    youtube_cookies_content = os.getenv("YOUTUBE_COOKIES_CONTENT", "").strip()
    facebook_cookies_content = os.getenv("FACEBOOK_COOKIES_CONTENT", "").strip()

    youtube_path: Optional[str] = None
    facebook_path: Optional[str] = None

    if youtube_cookies_content:
        try:
            decoded = base64.b64decode(youtube_cookies_content)
            if not decoded.startswith(b"# Netscape HTTP Cookie File"):
                logger.warning("Decoded YouTube cookies file does not start with Netscape header")
            # Normalize to UTF-8: cookie files from Windows browsers may be latin-1/windows-1252
            try:
                decoded.decode("utf-8")
            except UnicodeDecodeError:
                decoded = decoded.decode("latin-1").encode("utf-8")
                logger.warning("YouTube cookie file re-encoded from latin-1 to UTF-8")
            log_cookie_session_status("youtube", decoded)
            # Create a secure temporary file for cookies to avoid leaking secrets
            tf = tempfile.NamedTemporaryFile(delete=False, prefix="youtube_cookies_", suffix=".txt")
            tf.write(decoded)
            tf.close()
            try:
                os.chmod(tf.name, 0o600)
            except Exception:
                pass
            youtube_path = tf.name
            logger.info(
                "YouTube cookies file created successfully (base64 decoded)", path=youtube_path
            )
        except Exception as e:
            logger.error("Error creating YouTube cookies file", error=str(e))

    if facebook_cookies_content:
        try:
            decoded = base64.b64decode(facebook_cookies_content)
            if not decoded.startswith(b"# Netscape HTTP Cookie File"):
                logger.warning("Decoded Facebook cookies file does not start with Netscape header")
            # Normalize to UTF-8: cookie files from Windows browsers may be latin-1/windows-1252
            try:
                decoded.decode("utf-8")
            except UnicodeDecodeError:
                decoded = decoded.decode("latin-1").encode("utf-8")
                logger.warning("Facebook cookie file re-encoded from latin-1 to UTF-8")
            log_cookie_session_status("facebook", decoded)
            tf = tempfile.NamedTemporaryFile(
                delete=False, prefix="facebook_cookies_", suffix=".txt"
            )
            tf.write(decoded)
            tf.close()
            try:
                os.chmod(tf.name, 0o600)
            except Exception:
                pass
            facebook_path = tf.name
            logger.info(
                "Facebook cookies file created successfully (base64 decoded)", path=facebook_path
            )
        except Exception as e:
            logger.error("Error creating Facebook cookies file", error=str(e))

    return youtube_path, facebook_path
