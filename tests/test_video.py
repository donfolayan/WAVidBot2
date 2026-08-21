from pathlib import Path

import pytest

from src.wabotii.services import video
from src.wabotii.services.video import (
    DownloadErrorCode,
    VideoPlatform,
    detect_platform,
    download_video,
)


@pytest.mark.parametrize(
    ("url", "platform"),
    [
        ("https://youtu.be/example", VideoPlatform.YOUTUBE),
        ("https://m.youtube.com/shorts/example", VideoPlatform.YOUTUBE),
        ("https://www.facebook.com/share/v/example", VideoPlatform.FACEBOOK),
        ("https://fb.watch/example", VideoPlatform.FACEBOOK),
    ],
)
def test_detect_platform(url, platform):
    assert detect_platform(url) is platform


@pytest.mark.parametrize(
    "url",
    [
        "not-a-url",
        "ftp://youtube.com/video",
        "https://facebook.com.example.org/video",
        "https://example.org/?next=https://youtube.com/video",
    ],
)
def test_detect_platform_rejects_unsupported_urls(url):
    with pytest.raises(ValueError):
        detect_platform(url)


@pytest.mark.asyncio
async def test_download_tries_anonymous_before_cookie(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    cookie_path = tmp_path / "cookies.txt"
    cookie_path.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    attempts = []

    def fake_download(url, platform, cookie, *args):
        attempts.append(cookie)
        if cookie is None:
            raise RuntimeError("Sign in to view this video")
        return {
            "local_path": "downloads/video.mp4",
            "file_size_mb": 1.0,
            "title": "Video",
            "duration": 10,
        }

    monkeypatch.setattr(video, "_download_sync", fake_download)

    result = await download_video(
        "https://youtube.com/watch?v=example",
        youtube_cookies_path=str(cookie_path),
    )

    assert result.error is None
    assert attempts == [None, str(cookie_path)]


@pytest.mark.asyncio
async def test_download_sanitizes_extractor_errors(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    def fake_download(*args):
        raise RuntimeError("ERROR: Cannot parse data; please report this issue on GitHub")

    monkeypatch.setattr(video, "_download_sync", fake_download)

    result = await download_video("https://facebook.com/watch/?v=example")

    assert result.error_code is DownloadErrorCode.EXTRACTOR_CHANGED
    assert "Facebook changed" in result.error
    assert "GitHub" not in result.error


@pytest.mark.asyncio
async def test_download_does_not_retry_non_auth_failure_with_cookie(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    cookie_path = tmp_path / "cookies.txt"
    cookie_path.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    attempts = []

    def fake_download(url, platform, cookie, *args):
        attempts.append(cookie)
        raise RuntimeError("Maximum file size exceeded")

    monkeypatch.setattr(video, "_download_sync", fake_download)

    result = await download_video(
        "https://facebook.com/watch/?v=example",
        facebook_cookies_path=str(cookie_path),
    )

    assert result.error_code is DownloadErrorCode.TOO_LARGE
    assert attempts == [None]


def test_find_downloaded_file_ignores_partial_files(tmp_path):
    (tmp_path / "video.mp4.part").write_bytes(b"partial")
    expected = tmp_path / "video.mp4"
    expected.write_bytes(b"complete")

    assert video._find_downloaded_file(str(tmp_path)) == Path(expected)
