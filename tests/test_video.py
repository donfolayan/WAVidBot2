from pathlib import Path
from types import SimpleNamespace

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
async def test_youtube_tries_player_clients_before_authenticated_clients(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    cookie_path = tmp_path / "cookies.txt"
    cookie_path.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    attempts = []

    def fake_download(url, platform, cookie, *args):
        attempts.append((cookie, args[-2]))
        raise RuntimeError("Sign in to confirm you're not a bot")

    monkeypatch.setattr(video, "_download_sync", fake_download)

    result = await download_video(
        "https://youtube.com/watch?v=example",
        youtube_cookies_path=str(cookie_path),
        youtube_pot_provider_script_dir="/opt/bgutil-pot-provider",
    )

    assert result.error_code is DownloadErrorCode.AUTH_REQUIRED
    assert attempts == [
        (None, "mweb"),
        (None, "web_embedded"),
        (str(cookie_path), "mweb"),
        (str(cookie_path), "web_creator"),
    ]


@pytest.mark.asyncio
async def test_download_sanitizes_extractor_errors(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    def fake_download(*args):
        raise RuntimeError("ERROR: Cannot parse data; please report this issue on GitHub")

    monkeypatch.setattr(video, "_download_sync", fake_download)
    monkeypatch.setattr(
        video,
        "_download_facebook_with_gallery_sync",
        lambda *args: (_ for _ in ()).throw(RuntimeError("No results")),
    )

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


@pytest.mark.asyncio
async def test_facebook_uses_gallery_fallback(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    def fake_download(*args):
        raise RuntimeError("No video formats found")

    monkeypatch.setattr(video, "_download_sync", fake_download)
    monkeypatch.setattr(
        video,
        "_download_facebook_with_gallery_sync",
        lambda *args: {
            "local_path": "downloads/facebook.mp4",
            "file_size_mb": 2.0,
            "title": "Facebook video",
            "duration": None,
        },
    )

    result = await download_video("https://facebook.com/watch/?v=example")

    assert result.error is None
    assert result.local_path == "downloads/facebook.mp4"


def test_find_downloaded_file_ignores_partial_files(tmp_path):
    (tmp_path / "video.mp4.part").write_bytes(b"partial")
    expected = tmp_path / "video.mp4"
    expected.write_bytes(b"complete")

    assert video._find_downloaded_file(str(tmp_path)) == Path(expected)


def test_facebook_he_aac_audio_is_normalized_for_whatsapp(monkeypatch, tmp_path):
    source = tmp_path / "facebook.mp4"
    source.write_bytes(b"facebook-video")
    captured_command = []

    def fake_run(command, **kwargs):
        captured_command.extend(command)
        Path(command[-1]).write_bytes(b"whatsapp-video-with-aac-lc")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(video.subprocess, "run", fake_run)

    result = video._normalize_facebook_audio(source, video.time.monotonic() + 30)

    assert result.name == "facebook.whatsapp.mp4"
    assert result.read_bytes() == b"whatsapp-video-with-aac-lc"
    assert not source.exists()
    assert captured_command[captured_command.index("-c:v") + 1] == "copy"
    assert captured_command[captured_command.index("-profile:a") + 1] == "aac_low"
    assert captured_command[captured_command.index("-b:a") + 1] == "64k"


def test_facebook_aac_lc_audio_is_still_normalized(monkeypatch, tmp_path):
    source = tmp_path / "facebook.mp4"
    source.write_bytes(b"compatible-video")

    def fake_run(command, **kwargs):
        Path(command[-1]).write_bytes(b"normalized-video")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(video.subprocess, "run", fake_run)

    result = video._normalize_facebook_audio(source, video.time.monotonic() + 30)

    assert result != source
    assert result.read_bytes() == b"normalized-video"


def test_proxy_credentials_are_redacted():
    proxy = "http://user:secret@proxy.example:8080"

    assert video._redact_proxy(f"Could not connect to {proxy}", proxy) == (
        "Could not connect to <redacted YouTube proxy>"
    )


def test_download_configures_mweb_pot_provider(monkeypatch, tmp_path):
    captured_options = {}

    class FakeYoutubeDL:
        def __init__(self, options):
            captured_options.update(options)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def extract_info(self, url, download):
            output = next(tmp_path.glob("wabotii_youtube_*")) / "example.mp4"
            output.write_bytes(b"video")
            return {
                "title": "Example",
                "duration": 1,
                "requested_downloads": [{"filepath": str(output)}],
            }

    monkeypatch.setattr(video.yt_dlp, "YoutubeDL", FakeYoutubeDL)

    result = video._download_sync(
        "https://youtube.com/watch?v=example",
        VideoPlatform.YOUTUBE,
        None,
        str(tmp_path),
        30,
        720,
        64,
        "/opt/bgutil-pot-provider",
        "mweb",
        "socks5://proxy.example:1080",
    )

    assert result["local_path"]
    assert captured_options["extractor_args"] == {
        "youtube": {"player_client": ["mweb"], "fetch_pot": ["always"]},
        "youtubepot-bgutilscript": {"server_home": ["/opt/bgutil-pot-provider"]},
    }
    assert captured_options["proxy"] == "socks5://proxy.example:1080"
