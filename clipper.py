import shutil
import subprocess
from pathlib import Path

from captioner import render_caption_frames
from config import FFMPEG_PATH, OUTPUT_DIR, TEMP_DIR
from reframer import build_reframe_filter, get_video_info


def _run(command):
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout or "FFmpeg command failed")


def clip_words(words: list, start: float, end: float) -> list:
    selected = []
    for word in words:
        if word["end"] < start or word["start"] > end:
            continue
        selected.append(
            {
                "word": word["word"],
                "start": max(word["start"] - start, 0.0),
                "end": max(word["end"] - start, 0.0),
            }
        )
    return selected


def cut_segment(source_video: Path, start: float, end: float, destination: Path):
    duration = max(end - start, 0.1)
    _run(
        [
            FFMPEG_PATH,
            "-y",
            "-ss",
            str(start),
            "-i",
            str(source_video),
            "-t",
            str(duration),
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(destination),
        ]
    )
    return destination


def reframe_video(source_video: Path, destination: Path, aspect_ratio: str, zoom: float, reframe_mode: str):
    info = get_video_info(source_video)
    vf, dims = build_reframe_filter(info["width"], info["height"], aspect_ratio, zoom, reframe_mode)
    _run(
        [
            FFMPEG_PATH,
            "-y",
            "-i",
            str(source_video),
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(destination),
        ]
    )
    return destination, {"width": dims[0], "height": dims[1], "duration": info["duration"], "fps": info["fps"]}


def burn_caption_overlay(video_path: Path, overlay_path: Path, destination: Path):
    _run(
        [
            FFMPEG_PATH,
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(overlay_path),
            "-filter_complex",
            "[0:v][1:v]overlay=0:0:format=auto[v]",
            "-map",
            "[v]",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(destination),
        ]
    )
    return destination


def render_clip(
    source_video: Path,
    clip_index: int,
    segment: dict,
    transcript_words: list,
    aspect_ratio: str,
    zoom: float,
    reframe_mode: str,
    caption_settings: dict,
    clip_prefix: str = "",
):
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cut_path = TEMP_DIR / f"clip_{clip_index}_cut.mp4"
    reframed_path = TEMP_DIR / f"clip_{clip_index}_reframed.mp4"
    final_path = OUTPUT_DIR / f"{clip_prefix}clip_{clip_index}.mp4"

    cut_segment(source_video, float(segment["start_time"]), float(segment["end_time"]), cut_path)
    reframed_path, video_info = reframe_video(cut_path, reframed_path, aspect_ratio, zoom, reframe_mode)
    words = clip_words(transcript_words, float(segment["start_time"]), float(segment["end_time"]))
    overlay_path, frames_dir = render_caption_frames(
        clip_path=reframed_path,
        words=words,
        style_name=caption_settings["style"],
        font_name=caption_settings["font_name"],
        font_size=caption_settings["font_size"],
        active_color=caption_settings["active_color"],
        inactive_color=caption_settings["inactive_color"],
        background_color=caption_settings["background_color"],
        background_opacity=caption_settings["background_opacity"],
        position=caption_settings["position"],
        words_per_line=caption_settings["words_per_line"],
        lines_per_subtitle=caption_settings["lines_per_subtitle"],
        effect=caption_settings["effect"],
        video_info=video_info,
        outline_enabled=caption_settings.get("outline_enabled", True),
        outline_color=caption_settings.get("outline_color", "#000000"),
        outline_width=caption_settings.get("outline_width", 2),
        drop_shadow_enabled=caption_settings.get("drop_shadow_enabled", False),
        shadow_color=caption_settings.get("shadow_color", "#000000"),
        shadow_offset=caption_settings.get("shadow_offset", 4),
        caption_position_pct=caption_settings.get("caption_position_pct"),
        animation_speed=caption_settings.get("animation_speed", 1.0),
    )
    burn_caption_overlay(reframed_path, overlay_path, final_path)
    shutil.rmtree(frames_dir, ignore_errors=True)
    overlay_path.unlink(missing_ok=True)
    return final_path
