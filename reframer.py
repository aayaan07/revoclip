import functools
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from config import DEFAULT_BACKGROUND_COLOR, FFMPEG_PATH, TEMP_DIR

ASPECT_MAP = {
    "9:16": (9, 16),
    "1:1": (1, 1),
    "16:9": (16, 9),
}

INSET_FRAME_ASPECTS = {
    "Inset 16:9": (16, 9),
    "Inset Tall": (27, 20),
    "Inset 1:1": (1, 1),
}

INSET_MAX_HEIGHT_RATIOS = {
    "Inset 16:9": 0.78,
    "Inset Tall": 0.46,
    "Inset 1:1": 0.78,
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
    stderr = result.stderr

    res_match = re.search(r"(\d{2,5})x(\d{2,5})", stderr)
    if not res_match:
        raise RuntimeError("Could not read video metadata. File may be corrupt or unsupported.")
    width = int(res_match.group(1))
    height = int(res_match.group(2))

    fps_match = re.search(r"(\d+(?:\.\d+)?) fps", stderr)
    fps = float(fps_match.group(1)) if fps_match else 30.0

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
    mode = (mode or "").strip().lower()
    if mode.startswith("cover"):
        return "Cover"
    if mode.startswith("inset 16:9"):
        return "Inset 16:9"
    if mode.startswith("inset tall"):
        return "Inset Tall"
    if mode.startswith("inset 1:1"):
        return "Inset 1:1"
    return "Contain/Fit"


def is_inset_mode(mode: str) -> bool:
    return normalize_reframe_mode(mode) in INSET_FRAME_ASPECTS


def _even(value: int) -> int:
    return max(value - (value % 2), 2)


def _sanitize_hex_color(color: str) -> str:
    raw = (color or DEFAULT_BACKGROUND_COLOR).strip().lstrip("#")
    if re.fullmatch(r"[0-9a-fA-F]{6}", raw):
        return raw.upper()
    return DEFAULT_BACKGROUND_COLOR.lstrip("#")


def _background_is_solid(background_type: str) -> bool:
    return (background_type or "").strip().lower().startswith("solid")


def compute_target_dimensions(width: int, height: int, aspect_ratio: str, reframe_mode: str) -> tuple[int, int]:
    aspect_ratio = normalize_aspect_ratio(aspect_ratio)
    reframe_mode = normalize_reframe_mode(reframe_mode)
    if is_inset_mode(reframe_mode):
        aspect_ratio = "9:16"
    if aspect_ratio == "16:9":
        target_width = width
        target_height = height
    else:
        rw, rh = ASPECT_MAP[aspect_ratio]
        target_height = height
        target_width = int(target_height * (rw / rh))
    return _even(target_width), _even(target_height)


def _crop_center(image: Image.Image, width: int, height: int) -> Image.Image:
    left = max((image.width - width) // 2, 0)
    top = max((image.height - height) // 2, 0)
    return image.crop((left, top, left + width, top + height))


def apply_rounded_corners(image: Image.Image, radius: int) -> Image.Image:
    rounded = image.convert("RGBA")
    mask = Image.new("L", rounded.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, rounded.width, rounded.height), radius=radius, fill=255)
    rounded.putalpha(mask)
    return rounded


def _build_blurred_background(source: Image.Image, target_width: int, target_height: int) -> Image.Image:
    scale = max(target_width / source.width, target_height / source.height)
    bg_width = _even(int(source.width * scale))
    bg_height = _even(int(source.height * scale))
    blurred = source.resize((bg_width, bg_height), Image.Resampling.BILINEAR)
    blurred = _crop_center(blurred, target_width, target_height)
    return blurred.filter(ImageFilter.GaussianBlur(radius=20))


def _build_background(
    source: Image.Image,
    target_width: int,
    target_height: int,
    background_type: str,
    background_color: str,
) -> Image.Image:
    if _background_is_solid(background_type):
        return Image.new("RGB", (target_width, target_height), f"#{_sanitize_hex_color(background_color)}")
    return _build_blurred_background(source, target_width, target_height)


def composite_inset_frame(
    source_frame: Image.Image,
    reframe_mode: str,
    zoom: float = 1.0,
    background_type: str = "Blur",
    background_color: str = DEFAULT_BACKGROUND_COLOR,
    target_size: tuple[int, int] | None = None,
) -> Image.Image:
    reframe_mode = normalize_reframe_mode(reframe_mode)
    if not is_inset_mode(reframe_mode):
        raise ValueError(f"{reframe_mode} is not an inset mode")

    source = source_frame.convert("RGB")
    if target_size is None:
        target_width, target_height = compute_target_dimensions(
            source.width, source.height, "9:16", reframe_mode
        )
    else:
        target_width, target_height = target_size

    canvas = _build_background(
        source,
        target_width,
        target_height,
        background_type,
        background_color,
    ).convert("RGBA")

    frame_w_ratio, frame_h_ratio = INSET_FRAME_ASPECTS[reframe_mode]
    frame_ratio = frame_w_ratio / frame_h_ratio
    max_frame_width = int(target_width * 0.88)
    max_frame_height = int(target_height * INSET_MAX_HEIGHT_RATIOS[reframe_mode])

    frame_width = max_frame_width
    frame_height = int(frame_width / frame_ratio)
    if frame_height > max_frame_height:
        frame_height = max_frame_height
        frame_width = int(frame_height * frame_ratio)

    frame_width = _even(frame_width)
    frame_height = _even(frame_height)
    fg_scale = max(frame_width / source.width, frame_height / source.height) * max(zoom, 1.0)
    fg_width = _even(int(source.width * fg_scale))
    fg_height = _even(int(source.height * fg_scale))

    foreground = source.resize((fg_width, fg_height), Image.Resampling.LANCZOS)
    foreground = _crop_center(foreground, frame_width, frame_height)
    foreground = apply_rounded_corners(
        foreground,
        radius=max(24, int(min(frame_width, frame_height) * 0.06)),
    )

    paste_x = (target_width - frame_width) // 2
    paste_y = (target_height - frame_height) // 2
    canvas.alpha_composite(foreground, (paste_x, paste_y))
    return canvas.convert("RGB")


def build_reframe_filter(
    width: int,
    height: int,
    aspect_ratio: str,
    zoom: float,
    reframe_mode: str,
    background_type: str = "Blur",
    background_color: str = DEFAULT_BACKGROUND_COLOR,
) -> tuple[str, tuple[int, int]]:
    aspect_ratio = normalize_aspect_ratio(aspect_ratio)
    reframe_mode = normalize_reframe_mode(reframe_mode)
    target_width, target_height = compute_target_dimensions(width, height, aspect_ratio, reframe_mode)

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

    scaled_width = _even(scaled_width)
    scaled_height = _even(scaled_height)
    max_width_expr = f"max(iw\\,{target_width})"
    max_height_expr = f"max(ih\\,{target_height})"
    crop_x = f"max((iw-{target_width})/2\\,0)"
    crop_y = f"max((ih-{target_height})/2\\,0)"

    if aspect_ratio != "16:9" and reframe_mode == "Contain/Fit" and not _background_is_solid(background_type):
        bg_scale = max(target_width / width, target_height / height)
        bg_width = _even(int(width * bg_scale))
        bg_height = _even(int(height * bg_scale))
        vf = (
            f"split=2[fgsrc][bgsrc];"
            f"[fgsrc]scale={scaled_width}:{scaled_height}:flags=lanczos[fg];"
            f"[bgsrc]scale={bg_width}:{bg_height}:flags=bilinear,"
            f"boxblur=20:1,crop={target_width}:{target_height}[bg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2"
        )
    else:
        ffmpeg_color = f"0x{_sanitize_hex_color(background_color)}"
        vf = (
            f"scale={scaled_width}:{scaled_height}:flags=lanczos,"
            f"pad={max_width_expr}:{max_height_expr}:(ow-iw)/2:(oh-ih)/2:color={ffmpeg_color},"
            f"crop={target_width}:{target_height}:{crop_x}:{crop_y}"
        )

    return vf, (target_width, target_height)


def reframe_image(
    image: Image.Image,
    aspect_ratio: str,
    zoom: float,
    reframe_mode: str,
    background_type: str = "Blur",
    background_color: str = DEFAULT_BACKGROUND_COLOR,
) -> Image.Image:
    width, height = image.size
    aspect_ratio = normalize_aspect_ratio(aspect_ratio)
    reframe_mode = normalize_reframe_mode(reframe_mode)
    if is_inset_mode(reframe_mode):
        return composite_inset_frame(image, reframe_mode, zoom, background_type, background_color)

    target_width, target_height = compute_target_dimensions(width, height, aspect_ratio, reframe_mode)

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

    scaled_width = _even(scaled_width)
    scaled_height = _even(scaled_height)
    resized = image.convert("RGB").resize((scaled_width, scaled_height), Image.Resampling.LANCZOS)

    canvas_width = max(scaled_width, target_width)
    canvas_height = max(scaled_height, target_height)
    if aspect_ratio != "16:9" and reframe_mode == "Contain/Fit":
        canvas = _build_background(
            image.convert("RGB"),
            canvas_width,
            canvas_height,
            background_type,
            background_color,
        )
    else:
        canvas = Image.new(
            "RGB",
            (canvas_width, canvas_height),
            f"#{_sanitize_hex_color(background_color)}",
        )

    paste_x = (canvas.width - resized.width) // 2
    paste_y = (canvas.height - resized.height) // 2
    canvas.paste(resized, (paste_x, paste_y))
    return _crop_center(canvas, target_width, target_height)


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


def extract_preview(
    video_path: Path,
    aspect_ratio: str,
    zoom: float,
    reframe_mode: str,
    background_type: str = "Blur",
    background_color: str = DEFAULT_BACKGROUND_COLOR,
) -> Image.Image:
    frame = extract_preview_frame(video_path)
    if is_inset_mode(reframe_mode):
        return composite_inset_frame(frame, reframe_mode, zoom, background_type, background_color)
    return reframe_image(frame, aspect_ratio, zoom, reframe_mode, background_type, background_color)
