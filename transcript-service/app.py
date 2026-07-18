"""
Transcript Service — sidecar for the n8n "Discord AI Agent" workflow.

GET /transcript?url=<video_url>
    Downloads the video's audio with yt-dlp (YouTube, Facebook, and ~1800
    other sites), transcribes it, and returns JSON:
    { "title", "uploader", "duration_seconds", "language", "transcript" }

Transcription backends (chosen automatically):
  - If OPENAI_API_KEY is set  -> OpenAI transcription API (fast, ~$0.006/min)
  - Otherwise                 -> local faster-whisper (free, CPU, slower)

Environment variables:
  WHISPER_MODEL         local model size: tiny|base|small|medium (default: base)
  OPENAI_API_KEY        set to use OpenAI's API instead of local whisper
  OPENAI_TRANSCRIBE_MODEL  default: whisper-1
  COOKIES_FILE          path to a Netscape cookies.txt (needed for private/
                        login-gated Facebook videos)
  MAX_DURATION_SECONDS  reject videos longer than this (default: 5400 = 90 min)
  AUTH_TOKEN            optional shared secret; if set, requests must send
                        header  X-Auth-Token: <value>
"""

import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query
import yt_dlp

app = FastAPI(title="Transcript Service", version="1.0.0")

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_TRANSCRIBE_MODEL = os.getenv("OPENAI_TRANSCRIBE_MODEL", "whisper-1")
COOKIES_FILE = os.getenv("COOKIES_FILE", "").strip()
MAX_DURATION = int(os.getenv("MAX_DURATION_SECONDS", "5400"))
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "").strip()

_local_model = None  # lazy-loaded so the container starts instantly


def get_local_model():
    global _local_model
    if _local_model is None:
        from faster_whisper import WhisperModel  # heavy import, do it lazily
        _local_model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    return _local_model


def ydl_opts(tmpdir: str | None = None, download: bool = False) -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    if COOKIES_FILE and Path(COOKIES_FILE).exists():
        opts["cookiefile"] = COOKIES_FILE
    if download:
        opts.update(
            {
                "format": "bestaudio/best",
                "outtmpl": f"{tmpdir}/audio.%(ext)s",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "64",  # small file, plenty for speech
                    }
                ],
            }
        )
    return opts


def probe(url: str) -> dict:
    """Fetch metadata without downloading, so we can enforce MAX_DURATION."""
    try:
        with yt_dlp.YoutubeDL(ydl_opts()) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Could not access video: {e}. "
            "Private/login-gated videos need a cookies file (see README).",
        )
    if info.get("_type") == "playlist":
        entries = info.get("entries") or []
        if not entries:
            raise HTTPException(422, "URL resolved to an empty playlist.")
        info = entries[0]
    return info


def download_audio(url: str, tmpdir: str) -> Path:
    with yt_dlp.YoutubeDL(ydl_opts(tmpdir, download=True)) as ydl:
        ydl.extract_info(url, download=True)
    files = list(Path(tmpdir).glob("audio.*"))
    if not files:
        raise HTTPException(500, "Download succeeded but no audio file was produced.")
    return files[0]


def transcribe_openai(audio_path: Path) -> tuple[str, str | None]:
    from openai import OpenAI

    client = OpenAI(api_key=OPENAI_API_KEY)
    with open(audio_path, "rb") as f:
        result = client.audio.transcriptions.create(
            model=OPENAI_TRANSCRIBE_MODEL, file=f
        )
    return result.text, getattr(result, "language", None)


def transcribe_local(audio_path: Path) -> tuple[str, str | None]:
    model = get_local_model()
    segments, info = model.transcribe(str(audio_path), vad_filter=True)
    text = " ".join(seg.text.strip() for seg in segments)
    return text, getattr(info, "language", None)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "backend": "openai-api" if OPENAI_API_KEY else f"faster-whisper/{WHISPER_MODEL}",
        "cookies_configured": bool(COOKIES_FILE and Path(COOKIES_FILE).exists()),
    }


@app.get("/transcript")
def transcript(
    url: str = Query(..., description="Full YouTube/Facebook video URL"),
    x_auth_token: str | None = Header(default=None),
):
    if AUTH_TOKEN and x_auth_token != AUTH_TOKEN:
        raise HTTPException(401, "Missing or invalid X-Auth-Token header.")

    info = probe(url)
    duration = info.get("duration") or 0
    if duration and duration > MAX_DURATION:
        raise HTTPException(
            413,
            f"Video is {duration}s long; limit is {MAX_DURATION}s. "
            "Raise MAX_DURATION_SECONDS if you really want this.",
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        audio = download_audio(url, tmpdir)
        try:
            if OPENAI_API_KEY:
                text, language = transcribe_openai(audio)
            else:
                text, language = transcribe_local(audio)
        except HTTPException:
            raise
        except Exception as e:  # surface transcription errors cleanly to n8n
            raise HTTPException(500, f"Transcription failed: {e}")

    if not text.strip():
        raise HTTPException(422, "No speech detected in this video.")

    return {
        "title": info.get("title"),
        "uploader": info.get("uploader") or info.get("channel"),
        "duration_seconds": duration,
        "language": language,
        "transcript": text.strip(),
    }
