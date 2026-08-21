# Downloader architecture

## Decision

Keep yt-dlp as the in-process extraction engine and isolate its volatile behavior inside
`services/video.py`. Do not add a second always-on downloader service yet.

The request flow is:

1. Strictly validate the host as YouTube or Facebook.
2. Attempt public access without account cookies.
3. Retry once with the platform cookie file when one is configured.
4. Prefer a progressive H.264 MP4 up to 720p; merge video/audio only when needed.
5. Stop at the configured time and byte limits and allow only one concurrent download by default.
6. Return stable error categories while keeping extractor details in server logs.
7. Send the local file directly; use Cloudinary only as the existing fallback.

## Why not replace yt-dlp?

Cobalt is the most credible open-source alternative for both target platforms. It uses a different
YouTube implementation, but its self-hosted form adds Node, another API process, more monitoring,
and separate YouTube session/PO-token machinery. Its Facebook support is limited to publicly
accessible videos. That is useful as a future optional provider, but not a cheaper or universal
replacement.

Other projects commonly suggested as alternatives are desktop applications, yt-dlp wrappers, or
media-gallery tools. They do not provide a more reliable server-side path for both YouTube and
Facebook.

## Authentication

Cookies are a fallback, not the default. YouTube may rotate an exported browser session, and using
an account for automated downloads carries throttling or account-risk. Refresh cookie secrets only
when restricted media truly needs them. YouTube PO tokens are short-lived and should eventually be
supplied by a maintained provider plugin if anonymous downloads begin requiring them consistently;
they should not be pasted into static deployment configuration.

## Cost controls

The important controls are `VIDEO_MAX_HEIGHT`, `VIDEO_MAX_DOWNLOAD_SIZE_MB`,
`MAX_CONCURRENT_DOWNLOADS`, and `DOWNLOAD_TIMEOUT_SECONDS`. Raising them increases bandwidth,
temporary disk, peak memory, ffmpeg CPU time, and Cloudinary use.

For a small family bot, run the FastAPI app and WAHA on one small persistent host with a local
volume. Two separately billed always-on services generally cost more and make WAHA session
persistence harder. Scale the downloader out only after queue time, CPU, or memory measurements
show that the single-worker setup is insufficient.

## Future provider boundary

If real production logs show that one platform remains unreliable, turn the current service into a
provider interface and add Cobalt only for that platform. Keep delivery, limits, cookie selection,
and error categories outside the provider so the WhatsApp flow does not change.
