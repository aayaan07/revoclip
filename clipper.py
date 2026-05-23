import shutil
import subprocess
from pathlib import Path

from PIL import Image

from captioner import render_caption_frames, render_hook
from config import FFMPEG_PATH, OUTPUT_DIR, TEMP_DIR
from reframer import (
    build_reframe_filter,
    composite_inset_frame,
    compute_target_dimensions,
    get_video_info,
    is_inset_mode,
)


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


def _render_inset_video(
    source_video: Path,
    destination: Path,
    reframe_mode: str,
    zoom: float,
    background_type: str,
    background_color: str,
):
    info = get_video_info(source_video)
    target_width, target_height = compute_target_dimensions(
        info["width"], info["height"], "9:16", reframe_mode
    )
    frames_dir = TEMP_DIR / f"{destination.stem}_inset_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    try:
        _run(
            [
                FFMPEG_PATH,
                "-y",
                "-i",
                str(source_video),
                str(frames_dir / "%06d.png"),
            ]
        )

        for frame_path in sorted(frames_dir.glob("*.png")):
            with Image.open(frame_path) as frame:
                composited = composite_inset_frame(
                    frame.convert("RGB"),
                    reframe_mode,
                    zoom,
                    background_type,
                    background_color,
                    target_size=(target_width, target_height),
                )
                composited.save(frame_path)

        _run(
            [
                FFMPEG_PATH,
                "-y",
                "-framerate",
                f"{info['fps']}",
                "-i",
                str(frames_dir / "%06d.png"),
                "-i",
                str(source_video),
                "-map",
                "0:v",
                "-map",
                "1:a?",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-shortest",
                "-movflags",
                "+faststart",
                str(destination),
            ]
        )
    finally:
        shutil.rmtree(frames_dir, ignore_errors=True)

    return destination, {
        "width": target_width,
        "height": target_height,
        "duration": info["duration"],
        "fps": info["fps"],
    }


def reframe_video(
    source_video: Path,
    destination: Path,
    aspect_ratio: str,
    zoom: float,
    reframe_mode: str,
    background_type: str,
    background_color: str,
):
    if is_inset_mode(reframe_mode):
        return _render_inset_video(
            source_video,
            destination,
            reframe_mode,
            zoom,
            background_type,
            background_color,
        )

    info = get_video_info(source_video)
    vf, dims = build_reframe_filter(
        info["width"],
        info["height"],
        aspect_ratio,
        zoom,
        reframe_mode,
        background_type,
        background_color,
    )
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


def burn_hook_text(
    video_path: Path, destination: Path, video_info: dict, caption_settings: dict
):
    hook_text = caption_settings.get("hook_text", "")
    if not hook_text or not hook_text.strip():
        shutil.copy2(video_path, destination)
        return destination

    frames_dir = TEMP_DIR / f"{video_path.stem}_hook_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    try:
        extract_result = subprocess.run(
            [
                FFMPEG_PATH,
                "-y",
                "-i",
                str(video_path),
                str(frames_dir / "%06d.png"),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if extract_result.returncode != 0:
            raise RuntimeError(extract_result.stderr or "Hook frame extraction failed")

        for frame_path in sorted(frames_dir.glob("*.png")):
            with Image.open(frame_path) as frame:
                hooked = render_hook(
                    frame=frame.convert("RGB"),
                    hook_text=hook_text,
                    font_name=caption_settings.get("hook_font_name")
                    or caption_settings.get("font_name"),
                    font_size=caption_settings.get("hook_font_size", 52),
                    text_color=caption_settings.get("hook_color", "#FFFFFF"),
                    outline_enabled=caption_settings.get("hook_outline_enabled", True),
                    outline_color=caption_settings.get("hook_outline_color", "#000000"),
                    outline_width=caption_settings.get("hook_outline_width", 4),
                    drop_shadow_enabled=caption_settings.get("hook_shadow_enabled", True),
                    shadow_color=caption_settings.get("hook_shadow_color", "#000000"),
                    shadow_offset=caption_settings.get("hook_shadow_offset", 5),
                    position_pct=caption_settings.get("hook_position_pct", 8.0),
                    case_mode=caption_settings.get("hook_case", "upper"),
                )
                hooked.save(frame_path)

        encode_result = subprocess.run(
            [
                FFMPEG_PATH,
                "-y",
                "-framerate",
                f"{video_info['fps']}",
                "-i",
                str(frames_dir / "%06d.png"),
                "-i",
                str(video_path),
                "-map",
                "0:v",
                "-map",
                "1:a?",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-shortest",
                "-movflags",
                "+faststart",
                str(destination),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if encode_result.returncode != 0:
            raise RuntimeError(encode_result.stderr or "Hook video render failed")
        return destination
    finally:
        shutil.rmtree(frames_dir, ignore_errors=True)


def render_clip(
    source_video: Path,
    clip_index: int,
    segment: dict,
    transcript_words: list,
    aspect_ratio: str,
    zoom: float,
    reframe_mode: str,
    background_type: str,
    background_color: str,
    caption_settings: dict,
    clip_prefix: str = "",
):
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cut_path = TEMP_DIR / f"clip_{clip_index}_cut.mp4"
    reframed_path = TEMP_DIR / f"clip_{clip_index}_reframed.mp4"
    captioned_path = TEMP_DIR / f"clip_{clip_index}_captioned.mp4"
    final_path = OUTPUT_DIR / f"{clip_prefix}clip_{clip_index}.mp4"

    cut_segment(source_video, float(segment["start_time"]), float(segment["end_time"]), cut_path)
    reframed_path, video_info = reframe_video(
        cut_path,
        reframed_path,
        aspect_ratio,
        zoom,
        reframe_mode,
        background_type,
        background_color,
    )
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
        word_by_word=caption_settings.get("word_by_word", False),
        fade_in_words=caption_settings.get("fade_in_words", False),
        caption_case=caption_settings.get("caption_case", "upper"),
    )
    burn_caption_overlay(reframed_path, overlay_path, captioned_path)
    show_hook = caption_settings.get("show_hook", False)
    hook_text = caption_settings.get("hook_text", "")
    if show_hook and hook_text and hook_text.strip():
        burn_hook_text(captioned_path, final_path, video_info, caption_settings)
    else:
        shutil.copy2(captioned_path, final_path)
    shutil.rmtree(frames_dir, ignore_errors=True)
    overlay_path.unlink(missing_ok=True)
    captioned_path.unlink(missing_ok=True)
    return final_path
