import math
import subprocess
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFont

from config import FFMPEG_PATH, FONTS_DIR, STYLE_PRESETS, TEMP_DIR

import math

ANIMATION_SPEEDS = {
    "Quick":  0.5,
    "Medium": 1.0,
    "Slow":   2.0,
}

def ease_out_cubic(t: float) -> float:
    """Decelerates fast — snappy but smooth."""
    return 1 - (1 - t) ** 3

def ease_out_elastic(t: float) -> float:
    """Slight overshoot then settles — bouncy feel."""
    if t == 0 or t == 1:
        return t
    return pow(2, -10 * t) * math.sin((t * 10 - 0.75) * (2 * math.pi) / 3) + 1

def ease_out_back(t: float) -> float:
    """Overshoots slightly then pulls back — satisfying pop."""
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * pow(t - 1, 3) + c1 * pow(t - 1, 2)

def ease_in_out_sine(t: float) -> float:
    """Smooth fade — no harsh start or end."""
    return -(math.cos(math.pi * t) - 1) / 2

def get_word_progress(word, timestamp):
    """Normalized 0.0 → 1.0 progress through this word's duration."""
    duration = max(word["end"] - word["start"], 0.01)
    return min(max((timestamp - word["start"]) / duration, 0.0), 1.0)


def get_adjusted_progress(word, timestamp, speed):
    duration = max(word["end"] - word["start"], 0.01)
    raw_t = (timestamp - word["start"]) / duration
    adjusted_t = raw_t * speed
    return min(max(adjusted_t, 0.0), 1.0)

MAX_CHARS_PER_LINE = 18
PREVIEW_SAMPLE_TEXT = "This Build is Absolutely Insane!"
def _split_lines(words, words_per_line, max_chars_per_line=None):
    CHAR_SPLIT_THRESHOLD = 20

    if max_chars_per_line is None:
        # Scale the character limit dynamically so it doesn't aggressively override the user's word count choice
        max_chars_per_line = max(MAX_CHARS_PER_LINE, words_per_line * 8)

    # Step 1: original split by words_per_line + max_chars_per_line
    lines = []
    current_line = []
    current_chars = 0
    for word in words:
        word_text = word["word"]
        word_chars = len(word_text)
        next_chars = current_chars + word_chars + (1 if current_line else 0)
        if current_line and (len(current_line) >= max(words_per_line, 1) or next_chars > max_chars_per_line):
            lines.append(current_line)
            current_line = [word]
            current_chars = word_chars
        else:
            current_line.append(word)
            current_chars = next_chars
    if current_line:
        lines.append(current_line)

    # Step 2: re-split any line whose total character count exceeds threshold
    final_lines = []
    for line in lines:
        char_count = sum(len(w["word"]) for w in line)
        if char_count > CHAR_SPLIT_THRESHOLD and len(line) > 1:
            mid = len(line) // 2
            final_lines.append(line[:mid])
            final_lines.append(line[mid:])
        else:
            final_lines.append(line)
    return final_lines


def group_words(words, words_per_line, lines_per_subtitle):
    chunks = []
    current_chunk = []
    for word in words:
        candidate_chunk = current_chunk + [word]
        candidate_lines = _split_lines(candidate_chunk, words_per_line)
        if current_chunk and len(candidate_lines) > max(lines_per_subtitle, 1):
            chunks.append(
                {
                    "words": current_chunk,
                    "chunk_start": current_chunk[0]["start"],
                    "chunk_end": current_chunk[-1]["end"],
                }
            )
            current_chunk = [word]
        else:
            current_chunk = candidate_chunk
    if current_chunk:
        chunks.append(
            {
                "words": current_chunk,
                "chunk_start": current_chunk[0]["start"],
                "chunk_end": current_chunk[-1]["end"],
            }
        )
    return chunks


def resolve_font(font_name: str | None, style_name: str, font_size: int):
    preset = STYLE_PRESETS[style_name]
    candidates = [font_name] if font_name else []
    candidates.extend(preset["font_candidates"])
    for candidate in candidates:
        if not candidate:
            continue
        path = FONTS_DIR / candidate
        if path.exists():
            return ImageFont.truetype(str(path), font_size), str(path)
    return ImageFont.load_default(), None


def _hex_to_rgba(color: str | None, alpha: int = 255):
    if not color:
        return None
    rgb = ImageColor.getrgb(color)
    return (*rgb, alpha)


def _measure(draw, text, font, stroke_width=0):
    if not text:
        return (0, 0, 0, 0)
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    # Return (visual_width, visual_height, x_bearing, y_bearing)
    # x_bearing / y_bearing are the bbox offsets that must be subtracted when drawing
    # so that the visual glyph lands exactly where expected.
    return bbox[2] - bbox[0], bbox[3] - bbox[1], bbox[0], bbox[1]


def _split_text_lines(text: str, max_lines: int, max_chars_per_line: int):
    words = text.split()
    if not words:
        return []
    lines = []
    current = []
    current_chars = 0
    for word in words:
        word_chars = len(word)
        next_chars = current_chars + word_chars + (1 if current else 0)
        if current and next_chars > max_chars_per_line and len(lines) < max_lines - 1:
            lines.append(" ".join(current))
            current = [word]
            current_chars = word_chars
        else:
            current.append(word)
            current_chars = next_chars
    if current:
        lines.append(" ".join(current))
    if len(lines) > max_lines:
        merged = lines[: max_lines - 1]
        merged.append(" ".join(lines[max_lines - 1 :]))
        lines = merged
    return lines[:max_lines]


def _find_active(chunks, timestamp):
    for chunk in chunks:
        if chunk["chunk_start"] <= timestamp <= chunk["chunk_end"]:
            active_index = None
            for idx, word in enumerate(chunk["words"]):
                if word["start"] <= timestamp <= word["end"]:
                    active_index = idx
                    break
            return chunk, active_index
    return None, None



def _draw_caption_chunk(
    draw,
    dummy_draw,
    chunk_words,
    active_index,
    style_name,
    base_font,
    resolved_path,
    scaled_font_size,
    active_color,
    inactive_color,
    background_color,
    background_opacity,
    position,
    words_per_line,
    video_info,
    effect,
    timestamp,
    outline_enabled: bool = True,
    outline_color: str = "#000000",
    outline_width: int = 2,
    drop_shadow_enabled: bool = False,
    shadow_color: str = "#000000",
    shadow_offset: int = 4,
    caption_position_pct: float | None = None,
    animation_speed: float = 1.0,
):
    preset = STYLE_PRESETS[style_name]
    stroke_width = outline_width if outline_enabled else 0
    background_rgba = _hex_to_rgba(background_color, int(background_opacity * 255 / 100)) if background_color else None
    line_words = _split_lines(chunk_words, words_per_line)
    line_gap = max(int(scaled_font_size * 0.25), 8)
    padding_x = max(int(scaled_font_size * 0.5), 24)   # FIX: more padding so text never clips edge
    padding_y = max(int(scaled_font_size * 0.25), 14)

    # ── FIX: measure pass now accounts for the active word's boosted font size ──
    absolute_word_idx_measure = 0
    line_metrics = []
    total_height = 0

    for line in line_words:
        widths = []
        heights = []
        for word in line:
            display_word = word["word"].upper() if preset["uppercase"] else word["word"]
            is_active = absolute_word_idx_measure == active_index

            # FIX: compute the actual font that will be used during render
            # so measurement matches what gets drawn
            measure_font = base_font
            if is_active and resolved_path:
                t = get_adjusted_progress(word, timestamp, animation_speed)
                if effect == "Pop":
                    if t < 0.25:
                        scale = ease_out_elastic(t / 0.25)
                    elif t < 0.85:
                        scale = 1.0
                    else:
                        scale = 1.0 - 0.08 * ease_in_out_sine((t - 0.85) / 0.15)
                    size_boost = int(scaled_font_size * 0.18 * scale)
                    measure_font = ImageFont.truetype(resolved_path, scaled_font_size + size_boost)
                elif effect == "Scale Pulse":
                    pulse = 0.5 + 0.5 * math.sin(math.pi * t)
                    size_boost = int(scaled_font_size * 0.12 * pulse)
                    measure_font = ImageFont.truetype(resolved_path, scaled_font_size + size_boost)

            # FIX: for Typewriter, measure the partial word not the full word
            measure_word = display_word
            if is_active and effect == "Typewriter":
                t = get_adjusted_progress(word, timestamp, animation_speed)
                eased = ease_out_cubic(t)
                chars = max(int(len(display_word) * eased), 1)
                measure_word = display_word[:chars]

            width, _, x_bearing, _ = _measure(dummy_draw, measure_word, measure_font, stroke_width=stroke_width)
            _, height, _, y_bearing = _measure(dummy_draw, "Agpqyj|", measure_font, stroke_width=stroke_width)
            widths.append(width)
            heights.append(height)
            absolute_word_idx_measure += 1

        line_width = sum(widths) + max(len(line) - 1, 0) * int(scaled_font_size * 0.35)
        line_height = max(heights or [scaled_font_size])
        line_metrics.append((line, line_width, line_height))
        total_height += line_height
    total_height += max(len(line_metrics) - 1, 0) * line_gap

    # ── position ──────────────────────────────────────────────────────────────
    if caption_position_pct is not None:
        start_y = int(video_info["height"] * (caption_position_pct / 100.0)) - total_height // 2
        start_y = max(0, start_y)
    elif position == "Top":
        start_y = int(video_info["height"] * 0.08)
    elif position == "Center":
        start_y = (video_info["height"] - total_height) // 2
    else:
        start_y = int(video_info["height"] * 0.78) - total_height

    # ── FIX: compute per-line rects centered on frame width ──────────────────
    center_x = video_info["width"] // 2
    rects = []
    cursor_y = start_y
    for _, line_width, line_height in line_metrics:
        x0 = center_x - line_width // 2
        x1 = center_x + line_width // 2
        rects.append((x0, cursor_y, x1, cursor_y + line_height))
        cursor_y += line_height + line_gap

    # ── FIX: draw one background pill per LINE not one giant rect ─────────────
    if background_rgba:
        for (x0, y0, x1, y1) in rects:
            _, _, _, y_bearing = _measure(dummy_draw, "Agpqyj|", base_font, stroke_width=stroke_width)
            draw.rounded_rectangle(
                (x0 - padding_x, y0 - padding_y - y_bearing, x1 + padding_x, y1 + padding_y),
                radius=16,
                fill=background_rgba,
        )

    # ── render words ──────────────────────────────────────────────────────────
    cursor_y = start_y
    absolute_word_idx = 0

    for line_idx, (line, line_width, line_height) in enumerate(line_metrics):
        # FIX: start cursor_x from true center minus half the line width
        cursor_x = center_x - line_width // 2

        for word in line:
            display_word = word["word"].upper() if preset["uppercase"] else word["word"]
            is_active = absolute_word_idx == active_index
            word_font = base_font
            alpha = 255
            y_offset = 0
            draw_word = display_word
            word_color = active_color if is_active else inactive_color  # FIX: default here

            if is_active:
                t = get_adjusted_progress(word, timestamp, animation_speed)

                if effect == "Pop":
                    if t < 0.25:
                        scale = ease_out_elastic(t / 0.25)
                    elif t < 0.85:
                        scale = 1.0
                    else:
                        scale = 1.0 - 0.08 * ease_in_out_sine((t - 0.85) / 0.15)
                    size_boost = int(scaled_font_size * 0.18 * scale)
                    if resolved_path:
                        word_font = ImageFont.truetype(resolved_path, scaled_font_size + size_boost)

                elif effect == "Typewriter":
                    eased = ease_out_cubic(t)
                    chars = max(int(len(display_word) * eased), 1)
                    draw_word = display_word[:chars]

                elif effect == "Bounce":
                    arc = math.sin(math.pi * t)
                    y_offset = int(-10 * arc)

                elif effect == "Fade In":
                    alpha = int(255 * ease_in_out_sine(t))

                elif effect == "Scale Pulse":
                    pulse = 0.5 + 0.5 * math.sin(math.pi * t)
                    size_boost = int(scaled_font_size * 0.12 * pulse)
                    if resolved_path:
                        word_font = ImageFont.truetype(resolved_path, scaled_font_size + size_boost)

                elif effect == "Slide Up":
                    if t < 0.4:
                        eased = ease_out_cubic(t / 0.4)
                        y_offset = int(8 * (1 - eased))

                elif effect == "Karaoke":
                    if t < 0.15:
                        blend = ease_out_cubic(t / 0.15)
                        def blend_hex(c1, c2, f):
                            r1,g1,b1 = int(c1[1:3],16), int(c1[3:5],16), int(c1[5:7],16)
                            r2,g2,b2 = int(c2[1:3],16), int(c2[3:5],16), int(c2[5:7],16)
                            r = int(r1+(r2-r1)*f)
                            g = int(g1+(g2-g1)*f)
                            b = int(b1+(b2-b1)*f)
                            return f"#{r:02x}{g:02x}{b:02x}"  # hex string, not tuple
                        word_color = blend_hex(inactive_color, active_color, blend)

            fill = _hex_to_rgba(word_color, alpha)  # FIX: use word_color instead of recomputing
            text_width, _, _, _ = _measure(draw, draw_word, word_font, stroke_width=stroke_width)
            stroke_fill = outline_color if outline_enabled and outline_color else None

            ascent, descent = word_font.getmetrics()
            bbox = dummy_draw.textbbox((0, 0), draw_word, font=word_font, stroke_width=stroke_width)
            glyph_h = bbox[3] - bbox[1]
            vertical_offset = (line_height - glyph_h) // 2

            _, _, _, y_bearing = _measure(dummy_draw, "Agpqyj|", word_font, stroke_width=stroke_width)

            if drop_shadow_enabled:
                shadow_fill = _hex_to_rgba(shadow_color, int(255 * 0.8)) if shadow_color else (0, 0, 0, int(255 * 0.8))
                draw.text(
                    (cursor_x + shadow_offset, cursor_y + y_offset + shadow_offset - y_bearing),
                    draw_word,
                    font=word_font,
                    fill=shadow_fill,
                )

            draw.text(
                (cursor_x, cursor_y + y_offset - y_bearing),
                draw_word,
                font=word_font,
                fill=fill,
                stroke_width=stroke_width if stroke_fill else 0,
                stroke_fill=stroke_fill,
            )

            cursor_x += text_width + int(scaled_font_size * 0.35)
            absolute_word_idx += 1

        cursor_y += line_height + line_gap


def render_caption_preview(
    image: Image.Image,
    style_name: str,
    font_name: str | None,
    font_size: int,
    active_color: str,
    inactive_color: str,
    background_color: str | None,
    background_opacity: int,
    position: str,
    words_per_line: int,
    lines_per_subtitle: int,
    effect: str,
    outline_enabled: bool = True,
    outline_color: str = "#000000",
    outline_width: int = 2,
    drop_shadow_enabled: bool = False,
    shadow_color: str = "#000000",
    shadow_offset: int = 4,
    caption_position_pct: float | None = None,
    animation_speed: float = 1.0,
):
    preview = image.convert("RGBA")
    video_info = {"width": preview.width, "height": preview.height}
    scaled_font_size = max(int(font_size * (preview.height / 1080)), 18)
    base_font, resolved_path = resolve_font(font_name, style_name, scaled_font_size)
    draw = ImageDraw.Draw(preview)
    dummy = Image.new("RGBA", (preview.width, preview.height))
    dummy_draw = ImageDraw.Draw(dummy)

    sample_words = []
    cursor = 0.0
    for token in PREVIEW_SAMPLE_TEXT.split():
        duration = 0.35 + min(len(token) * 0.04, 0.35)
        sample_words.append({"word": token, "start": cursor, "end": cursor + duration})
        cursor += duration
    chunks = group_words(sample_words, words_per_line, lines_per_subtitle)
    chunk = chunks[0] if chunks else sample_words
    active_index = min(1, max(len(chunk) - 1, 0))
    _draw_caption_chunk(
        draw=draw,
        dummy_draw=dummy_draw,
        chunk_words=chunk if isinstance(chunk, list) else chunk["words"],
        active_index=active_index,
        style_name=style_name,
        base_font=base_font,
        resolved_path=resolved_path,
        scaled_font_size=scaled_font_size,
        active_color=active_color,
        inactive_color=inactive_color,
        background_color=background_color,
        background_opacity=background_opacity,
        position=position,
        words_per_line=words_per_line,
        video_info=video_info,
        effect=effect,
        timestamp=sample_words[active_index]["start"] + 0.15 if sample_words else 0.0,
        outline_enabled=outline_enabled,
        outline_color=outline_color,
        outline_width=outline_width,
        drop_shadow_enabled=drop_shadow_enabled,
        shadow_color=shadow_color,
        shadow_offset=shadow_offset,
        caption_position_pct=caption_position_pct,
        animation_speed=animation_speed,
    )
    return preview.convert("RGB")


def render_caption_frames(
    clip_path: Path,
    words: list,
    style_name: str,
    font_name: str | None,
    font_size: int,
    active_color: str,
    inactive_color: str,
    background_color: str | None,
    background_opacity: int,
    position: str,
    words_per_line: int,
    lines_per_subtitle: int,
    effect: str,
    video_info: dict,
    outline_enabled: bool = True,
    outline_color: str = "#000000",
    outline_width: int = 2,
    drop_shadow_enabled: bool = False,
    shadow_color: str = "#000000",
    shadow_offset: int = 4,
    temp_root: Path | None = None,
    caption_position_pct: float | None = None,
    animation_speed: float = 1.0,
):
    preset = STYLE_PRESETS[style_name]
    frames_dir = (temp_root or TEMP_DIR) / f"caption_frames_{clip_path.stem}"
    frames_dir.mkdir(parents=True, exist_ok=True)
    scaled_font_size = max(int(font_size * (video_info["height"] / 1080)), 18)
    base_font, resolved_path = resolve_font(font_name, style_name, scaled_font_size)
    stroke_width = outline_width if outline_enabled else 0
    background_rgba = _hex_to_rgba(background_color, int(background_opacity * 255 / 100)) if background_color else None
    chunks = group_words(words, words_per_line, lines_per_subtitle)
    frame_count = max(int(math.ceil(video_info["duration"] * video_info["fps"])), 1)

    dummy = Image.new("RGBA", (video_info["width"], video_info["height"]))
    dummy_draw = ImageDraw.Draw(dummy)
    line_gap = max(int(scaled_font_size * 0.25), 8)
    padding_x = max(int(scaled_font_size * 0.4), 18)
    padding_y = max(int(scaled_font_size * 0.2), 12)

    for frame_index in range(frame_count):
        timestamp = frame_index / video_info["fps"]
        image = Image.new("RGBA", (video_info["width"], video_info["height"]), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        chunk, active_index = _find_active(chunks, timestamp)
        if chunk:
            _draw_caption_chunk(
                draw=draw,
                dummy_draw=dummy_draw,
                chunk_words=chunk["words"],
                active_index=active_index,
                style_name=style_name,
                base_font=base_font,
                resolved_path=resolved_path,
                scaled_font_size=scaled_font_size,
                active_color=active_color,
                inactive_color=inactive_color,
                background_color=background_color,
                background_opacity=background_opacity,
                position=position,
                words_per_line=words_per_line,
                video_info=video_info,
                effect=effect,
                timestamp=timestamp,
                outline_enabled=outline_enabled,
                outline_color=outline_color,
                outline_width=outline_width,
                drop_shadow_enabled=drop_shadow_enabled,
                shadow_color=shadow_color,
                shadow_offset=shadow_offset,
                caption_position_pct=caption_position_pct,
                animation_speed=animation_speed,
            )

        image.save(frames_dir / f"{frame_index:06d}.png")

    overlay_path = frames_dir.parent / f"{clip_path.stem}_captions.mov"
    command = [
        FFMPEG_PATH,
        "-y",
        "-framerate",
        f"{video_info['fps']}",
        "-i",
        str(frames_dir / "%06d.png"),
        "-c:v",
        "qtrle",
        "-pix_fmt",
        "argb",
        str(overlay_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or "Caption overlay render failed")
    return overlay_path, frames_dir
