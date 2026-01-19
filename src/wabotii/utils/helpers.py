"""Helper utilities."""

import base64
import os
import re
import tempfile
from datetime import datetime
from typing import Optional

from .logging import get_logger

logger = get_logger(__name__)


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
