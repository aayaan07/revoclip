import functools
import re
import subprocess
from pathlib import Path

from PIL import Image

from config import FFMPEG_PATH, TEMP_DIR

ASPECT_MAP = {
    "9:16": (9, 16),
    "1:1": (1, 1),
    "16:9": (16, 9),
}


def get_video_info(video_path: Path) -> dict:
    """Extract width, height, fps, and duration from a video using ffmpeg stderr output."""
    result = subprocess.run(
        [FFMPEG_PATH, "-i", str(video_path), "-f", "null", "-"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    # ffmpeg writes all metadata to stderr even on non-zero exit (input probe always exits non-zero with -f null)
    stderr = result.stderr

    # --- width x height ---
    res_match = re.search(r"(\d{2,5})x(\d{2,5})", stderr)
    if not res_match:
        raise RuntimeError("Could not read video metadata. File may be corrupt or unsupported.")
    width = int(res_match.group(1))
    height = int(res_match.group(2))

    # --- fps ---
    fps_match = re.search(r"(\d+(?:\.\d+)?) fps", stderr)
    fps = float(fps_match.group(1)) if fps_match else 30.0

    # --- duration ---
    dur_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", stderr)
    if dur_match:
        hours = int(dur_match.group(1))
        minutes = int(dur_match.group(2))
        seconds = float(dur_match.group(3))
        duration = hours * 3600 + minutes * 60 + seconds
    else:
        duration = 0.0

    return {"width": width, "height": height, "duration": duration, "fps": fps}


def normalize_aspect_ratio(label: str) -> str:
    if label.startswith("9:16"):
        return "9:16"
    if label.startswith("1:1"):
        return "1:1"
    return "16:9"


def normalize_reframe_mode(mode: str) -> str:
    if mode.lower().startswith("cover"):
        return "Cover"
    return "Contain/Fit"


def build_reframe_filter(width: int, height: int, aspect_ratio: str, zoom: float, reframe_mode: str) -> tuple[str, tuple[int, int]]:
    aspect_ratio = normalize_aspect_ratio(aspect_ratio)
    reframe_mode = normalize_reframe_mode(reframe_mode)
    if aspect_ratio == "16:9":
        target_width = width
        target_height = height
    else:
        rw, rh = ASPECT_MAP[aspect_ratio]
        target_ratio = rw / rh
        target_height = height
        target_width = int(target_height * target_ratio)

    target_width = max(target_width - (target_width % 2), 2)
    target_height = max(target_height - (target_height % 2), 2)

    if aspect_ratio == "16:9":
        scaled_width = max(int(width * zoom), 2)
        scaled_height = max(int(height * zoom), 2)
    elif reframe_mode == "Cover":
        cover_scale = max(target_width / width, target_height / height)
        scaled_width = max(int(width * cover_scale * zoom), 2)
        scaled_height = max(int(height * cover_scale * zoom), 2)
    else:
        contain_scale = min(target_width / width, target_height / height)
        scaled_width = max(int(width * contain_scale * zoom), 2)
        scaled_height = max(int(height * contain_scale * zoom), 2)

    scaled_width = max(scaled_width - (scaled_width % 2), 2)
    scaled_height = max(scaled_height - (scaled_height % 2), 2)
    max_width_expr = f"max(iw\\,{target_width})"
    max_height_expr = f"max(ih\\,{target_height})"
    crop_x = f"max((iw-{target_width})/2\\,0)"
    crop_y = f"max((ih-{target_height})/2\\,0)"
    vf = (
        f"scale={scaled_width}:{scaled_height},"
        f"pad={max_width_expr}:{max_height_expr}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"crop={target_width}:{target_height}:{crop_x}:{crop_y}"
    )
    return vf, (target_width, target_height)


def reframe_image(image: Image.Image, aspect_ratio: str, zoom: float, reframe_mode: str) -> Image.Image:
    width, height = image.size
    aspect_ratio = normalize_aspect_ratio(aspect_ratio)
    reframe_mode = normalize_reframe_mode(reframe_mode)
    if aspect_ratio == "16:9":
        target_width = width
        target_height = height
    else:
        rw, rh = ASPECT_MAP[aspect_ratio]
        target_height = height
        target_width = int(target_height * (rw / rh))
    target_width = max(target_width - (target_width % 2), 2)
    target_height = max(target_height - (target_height % 2), 2)

    if aspect_ratio == "16:9":
        scaled_width = max(int(width * zoom), 2)
        scaled_height = max(int(height * zoom), 2)
    elif reframe_mode == "Cover":
        cover_scale = max(target_width / width, target_height / height)
        scaled_width = max(int(width * cover_scale * zoom), 2)
        scaled_height = max(int(height * cover_scale * zoom), 2)
    else:
        contain_scale = min(target_width / width, target_height / height)
        scaled_width = max(int(width * contain_scale * zoom), 2)
        scaled_height = max(int(height * contain_scale * zoom), 2)

    scaled_width = max(scaled_width - (scaled_width % 2), 2)
    scaled_height = max(scaled_height - (scaled_height % 2), 2)
    resized = image.convert("RGB").resize((scaled_width, scaled_height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (max(scaled_width, target_width), max(scaled_height, target_height)), "black")
    paste_x = (canvas.width - resized.width) // 2
    paste_y = (canvas.height - resized.height) // 2
    canvas.paste(resized, (paste_x, paste_y))
    left = max((canvas.width - target_width) // 2, 0)
    top = max((canvas.height - target_height) // 2, 0)
    return canvas.crop((left, top, left + target_width, top + target_height))


@functools.lru_cache(maxsize=10)
def extract_preview_frame(video_path: Path) -> Image.Image:
    info = get_video_info(video_path)
    preview_path = TEMP_DIR / "preview.png"
    midpoint = max(info["duration"] / 2, 0)
    command = [
        FFMPEG_PATH,
        "-y",
        "-ss",
        str(midpoint),
        "-i",
        str(video_path),
        "-vframes",
        "1",
        str(preview_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or "Preview generation failed")
    return Image.open(preview_path).copy()


def extract_preview(video_path: Path, aspect_ratio: str, zoom: float, reframe_mode: str) -> Image.Image:
    return reframe_image(extract_preview_frame(video_path), aspect_ratio, zoom, reframe_mode)
