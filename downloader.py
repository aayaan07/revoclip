import shutil
import subprocess
from pathlib import Path

from config import SUPPORTED_UPLOADS, TEMP_DIR


def prepare_input_video(
    url: str | None = None,
    upload_path: str | None = None,
    download_quality: str = "1080p",
) -> Path:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    if url and url.strip():
        return download_video(url.strip(), download_quality)
    if upload_path:
        return copy_local_video(Path(upload_path))
    raise ValueError("Provide either a YouTube URL or a local video file.")


def copy_local_video(source: Path) -> Path:
    if source.suffix.lower() not in SUPPORTED_UPLOADS:
        raise ValueError(f"Unsupported upload type: {source.suffix}")
    destination = TEMP_DIR / f"source{source.suffix.lower()}"
    shutil.copy2(source, destination)
    return destination


def build_format_selector(download_quality: str) -> str:
    if download_quality == "Best available":
        return "bv*+ba/b"
    max_height = "".join(ch for ch in download_quality if ch.isdigit()) or "1080"
    return (
        f"bestvideo[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]/"
        f"bestvideo[height<={max_height}]+bestaudio/"
        f"best[height<={max_height}][ext=mp4]/best[height<={max_height}]"
    )


def download_video(url: str, download_quality: str = "1080p") -> Path:
    output_template = TEMP_DIR / "downloaded.%(ext)s"
    for existing_file in TEMP_DIR.glob("downloaded.*"):
        existing_file.unlink(missing_ok=True)
    command = [
        "yt-dlp",
        "-f",
        build_format_selector(download_quality),
        "--merge-output-format",
        "mp4",
        "-o",
        str(output_template),
        url,
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout or "yt-dlp download failed")
    matches = sorted(TEMP_DIR.glob("downloaded.*"))
    if not matches:
        raise FileNotFoundError("Downloaded file not found")
    return matches[0]
