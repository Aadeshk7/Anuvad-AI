import os
os.environ["PYTHONUTF8"] = "1"
import subprocess
import logging
from pathlib import Path
from typing import Optional
from app.core.config import settings

logger = logging.getLogger("audio-utils")


def configure_ffmpeg_path() -> Optional[str]:
    """Configure PATH so ffmpeg binaries are reachable from backend processes."""
    candidates: list[Path] = []

    if settings.ffmpeg_dir:
        candidates.append(Path(settings.ffmpeg_dir).expanduser().resolve())

    workspace_root = Path(__file__).resolve().parents[3]
    candidates.append(workspace_root / "ffmpeg")
    candidates.append(workspace_root / "ffmpeg" / "bin")

    for candidate in candidates:
        ffmpeg_exe = candidate / "ffmpeg.exe"
        ffprobe_exe = candidate / "ffprobe.exe"
        if candidate.exists() and ffmpeg_exe.exists() and ffprobe_exe.exists():
            os.environ["PATH"] = f"{candidate}{os.pathsep}" + os.environ.get("PATH", "")
            return str(candidate)

    return None


def extract_audio(video_path: str, audio_output_path: str, timeout: int = 300) -> bool:
    """
    Extract audio from video using FFmpeg, optimized for Whisper.

    Settings:
    - 16 kHz mono PCM (required by Whisper)
    - -threads 0  → auto-detect optimal thread count
    - -af aresample=resampler=swr → high-quality resampler
    - -compression_level 0 → fastest WAV write (no compression needed)
    - Raises on failure so callers get a proper exception.
    """
    configure_ffmpeg_path()

    audio_output_path = str(audio_output_path)
    video_path = str(video_path)

    command = [
        "ffmpeg",
        "-y",                           # overwrite output
        "-threads", "0",                # auto thread count
        "-i", video_path,
        "-vn",                          # no video
        "-af", "afftdn=nr=12:nf=-35:tn=1,highpass=f=100,aresample=resampler=swr",  # Denoise + highpass + resampling
        "-acodec", "pcm_s16le",         # 16-bit PCM (Whisper requirement)
        "-ar", "16000",                 # 16 kHz sample rate
        "-ac", "1",                     # mono channel
        "-loglevel", "error",           # only show real errors
        audio_output_path,
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,  # handle manually for better error messages
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            logger.error(f"FFmpeg failed (code {result.returncode}): {stderr}")
            raise RuntimeError(f"FFmpeg audio extraction failed: {stderr}")

        # Verify output exists and is non-empty
        if not os.path.exists(audio_output_path) or os.path.getsize(audio_output_path) == 0:
            raise RuntimeError("FFmpeg produced an empty or missing audio file.")

        logger.info(
            f"Audio extracted → {audio_output_path} "
            f"({os.path.getsize(audio_output_path) / 1024:.1f} KB)"
        )
        return True

    except subprocess.TimeoutExpired:
        logger.error(f"FFmpeg timed out after {timeout}s for {video_path}")
        raise RuntimeError(f"Audio extraction timed out after {timeout} seconds.")


def get_video_duration(video_path: str) -> float:
    """Get the duration of a video file using ffprobe."""
    try:
        configure_ffmpeg_path()
        command = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=30)
        return float(result.stdout.strip())
    except Exception as e:
        logger.warning(f"Could not determine video duration: {e}")
        return 0.0
