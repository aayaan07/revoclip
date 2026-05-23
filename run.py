"""
Revoclip — FastAPI backend
Run with:  python run.py
Then open:  http://localhost:7860
"""

import asyncio
import base64
import io
import json
import os
import shutil
import sys
import traceback
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, UploadFile, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

from captioner import ANIMATION_SPEEDS, render_caption_preview, resolve_font
from clipper import render_clip
from config import (
    ANIMATION_SPEED_OPTIONS, DEFAULT_ANIMATION_SPEED, DEFAULT_CAPTION_EFFECT,
    BACKGROUND_TYPE_OPTIONS, DEFAULT_BACKGROUND_COLOR, DEFAULT_BACKGROUND_TYPE,
    DEFAULT_CAPTION_CASE, DEFAULT_CAPTION_STYLE, DEFAULT_DOWNLOAD_QUALITY, DEFAULT_FONT_SIZE,
    DEFAULT_FADE_IN_WORDS,
    DEFAULT_GEMINI_MODEL, DEFAULT_GROQ_MODEL, DEFAULT_LINES_PER_SUBTITLE,
    DEFAULT_HOOK_CASE, DEFAULT_HOOK_COLOR, DEFAULT_HOOK_FONT_SIZE, DEFAULT_HOOK_OUTLINE,
    DEFAULT_HOOK_OUTLINE_COLOR, DEFAULT_HOOK_OUTLINE_WIDTH,
    DEFAULT_HOOK_POSITION_PCT, DEFAULT_HOOK_SHADOW, DEFAULT_HOOK_SHADOW_COLOR,
    DEFAULT_HOOK_SHADOW_OFFSET, DEFAULT_SHOW_HOOK,
    DEFAULT_MAX_DURATION, DEFAULT_MIN_DURATION, DEFAULT_NUM_CLIPS,
    DEFAULT_OLLAMA_MODEL, DEFAULT_OPENROUTER_MODEL, DEFAULT_POSITION, DEFAULT_PROVIDER,
    DEFAULT_REFRAME_MODE, DEFAULT_WORD_BY_WORD, DEFAULT_WORDS_PER_LINE, DEFAULT_ZOOM,
    DOWNLOAD_QUALITY_OPTIONS, FONTS_DIR, OUTPUT_DIR, STYLE_PRESETS,
    REFRAME_MODE_OPTIONS,
    TEMP_DIR, WHISPER_MODEL, WHISPER_MODEL_OPTIONS,
)
from downloader import prepare_input_video
from errors import friendly_error
from highlight import HighlightDetector, ERROR_MESSAGES
from reframer import (
    extract_preview,
    is_inset_mode,
    normalize_aspect_ratio,
    normalize_reframe_mode,
    reframe_image,
)
from transcriber import transcribe_video
from PIL import Image

for _s in ("stdout", "stderr"):
    _stream = getattr(sys, _s, None)
    if _stream and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)
FONTS_DIR.mkdir(parents=True, exist_ok=True)
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

PREVIEW_FALLBACK_PATH = ASSETS_DIR / "preview-img.png"

app = FastAPI(title="Revoclip")
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")
app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")


def list_fonts() -> list[str]:
    return sorted({p.name for p in [*FONTS_DIR.glob("*.ttf"), *FONTS_DIR.glob("*.otf")]})


def clean_temp_dir():
    for path in TEMP_DIR.iterdir():
        if path.name.startswith("transcript_") and path.suffix == ".json":
            continue
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)


def build_zip_from_files(files: list[Path]) -> Path | None:
    if not files:
        return None
    zip_path = OUTPUT_DIR / f"revoclip_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as arc:
        for f in files:
            arc.write(f, arcname=f.name)
    return zip_path


def pil_to_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def log(msg: str):
    print(f"[Revoclip] {msg}", flush=True)


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.get("/", response_class=HTMLResponse)
async def index():
    html = (Path(__file__).resolve().parent / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    favicon_path = ASSETS_DIR / "favicon.ico"
    return FileResponse(str(favicon_path), media_type="image/x-icon")


@app.get("/api/config")
async def get_config():
    presets_out = {}
    for name, p in STYLE_PRESETS.items():
        presets_out[name] = {
            "active_color":        p["active_color"],
            "inactive_color":      p["inactive_color"],
            "background_color":    p.get("background_color") or "#000000",
            "background_opacity":  p.get("background_opacity", 0),
            "outline_enabled":     p.get("outline_enabled", True),
            "outline_color":       p.get("outline_color", "#000000"),
            "outline_width":       p.get("outline_width", 3),
            "drop_shadow_enabled": p.get("drop_shadow_enabled", False),
            "shadow_color":        p.get("shadow_color", "#000000"),
            "shadow_offset":       p.get("shadow_offset", 4),
            "position":            p.get("position", "Bottom"),
            "font_size":           p.get("font_size", DEFAULT_FONT_SIZE),
        }
    return {
        "style_presets": presets_out,
        "whisper_models": WHISPER_MODEL_OPTIONS,
        "default_whisper": WHISPER_MODEL,
        "download_qualities": DOWNLOAD_QUALITY_OPTIONS,
        "default_quality": DEFAULT_DOWNLOAD_QUALITY,
        "default_style": DEFAULT_CAPTION_STYLE,
        "default_position": DEFAULT_POSITION,
        "default_zoom": DEFAULT_ZOOM,
        "default_words": DEFAULT_WORDS_PER_LINE,
        "default_lines": DEFAULT_LINES_PER_SUBTITLE,
        "default_font_size": DEFAULT_FONT_SIZE,
        "default_caption_case": DEFAULT_CAPTION_CASE,
        "default_show_hook": DEFAULT_SHOW_HOOK,
        "default_hook_case": DEFAULT_HOOK_CASE,
        "default_hook_font_size": DEFAULT_HOOK_FONT_SIZE,
        "default_hook_color": DEFAULT_HOOK_COLOR,
        "default_hook_outline": DEFAULT_HOOK_OUTLINE,
        "default_hook_outline_color": DEFAULT_HOOK_OUTLINE_COLOR,
        "default_hook_outline_width": DEFAULT_HOOK_OUTLINE_WIDTH,
        "default_hook_shadow": DEFAULT_HOOK_SHADOW,
        "default_hook_shadow_color": DEFAULT_HOOK_SHADOW_COLOR,
        "default_hook_shadow_offset": DEFAULT_HOOK_SHADOW_OFFSET,
        "default_hook_position_pct": DEFAULT_HOOK_POSITION_PCT,
        "default_effect": DEFAULT_CAPTION_EFFECT,
        "default_animation_speed": DEFAULT_ANIMATION_SPEED,
        "default_word_by_word": DEFAULT_WORD_BY_WORD,
        "default_fade_in_words": DEFAULT_FADE_IN_WORDS,
        "animation_speed_options": ANIMATION_SPEED_OPTIONS,
        "default_reframe": DEFAULT_REFRAME_MODE,
        "reframe_modes": REFRAME_MODE_OPTIONS,
        "background_type_options": BACKGROUND_TYPE_OPTIONS,
        "default_background_type": DEFAULT_BACKGROUND_TYPE,
        "default_background_color": DEFAULT_BACKGROUND_COLOR,
        "default_provider": DEFAULT_PROVIDER,
        "default_groq_model": DEFAULT_GROQ_MODEL,
        "default_gemini_model": DEFAULT_GEMINI_MODEL,
        "default_openrouter_model": DEFAULT_OPENROUTER_MODEL,
        "default_ollama_model": DEFAULT_OLLAMA_MODEL,
        "default_num_clips": DEFAULT_NUM_CLIPS,
        "default_min_duration": DEFAULT_MIN_DURATION,
        "default_max_duration": DEFAULT_MAX_DURATION,
        "fonts": list_fonts(),
    }


@app.get("/api/fonts")
async def get_fonts():
    return {"fonts": list_fonts()}


@app.get("/api/outputs")
async def get_outputs():
    clips = sorted(OUTPUT_DIR.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    return {"clips": [f"/outputs/{c.name}" for c in clips]}


@app.post("/api/upload")
async def upload_video(request: Request):
    form = await request.form()
    upload = form.get("upload")
    if not upload or not getattr(upload, "filename", None):
        return JSONResponse({"ok": False, "error": "No file uploaded"})
    
    suffix = Path(upload.filename).suffix or ".mp4"
    file_id = f"upload_{uuid.uuid4().hex}{suffix}"
    tmp = TEMP_DIR / file_id
    tmp.write_bytes(await upload.read())
    return {"ok": True, "file_id": file_id}


@app.post("/api/preview")
async def preview(request: Request):
    form = await request.form()
    def g(k, d=""): return str(form.get(k, d) or d)

    try:
        ar = normalize_aspect_ratio(g("aspect_ratio", "9:16 (Vertical)"))
        zm = float(g("zoom", "1.0"))
        rm = normalize_reframe_mode(g("reframe_mode", DEFAULT_REFRAME_MODE))
        background_type = g("background_type", DEFAULT_BACKGROUND_TYPE)
        background_color = g("background_color_bg", DEFAULT_BACKGROUND_COLOR)
        animation_speed_name = g("animation_speed", DEFAULT_ANIMATION_SPEED)
        animation_speed = ANIMATION_SPEEDS.get(animation_speed_name, 1.0)
        caption_case = g("caption_case", DEFAULT_CAPTION_CASE)
        word_by_word = g("word_by_word", "false").lower() == "true"
        fade_in_words = g("fade_in_words", "false").lower() == "true"
        show_hook = g("show_hook", "false").lower() == "true"
        hook_text_preview = g("hook_text_preview", "He quit his job on day one")
        hook_font_name = g("hook_font_name", "") or None
        hook_font_size = int(g("hook_font_size", str(DEFAULT_HOOK_FONT_SIZE)))
        hook_color = g("hook_color", DEFAULT_HOOK_COLOR)
        hook_outline_enabled = g("hook_outline_enabled", "true").lower() == "true"
        hook_outline_color = g("hook_outline_color", DEFAULT_HOOK_OUTLINE_COLOR)
        hook_outline_width = int(g("hook_outline_width", str(DEFAULT_HOOK_OUTLINE_WIDTH)))
        hook_shadow_enabled = g("hook_shadow_enabled", "true").lower() == "true"
        hook_shadow_color = g("hook_shadow_color", DEFAULT_HOOK_SHADOW_COLOR)
        hook_shadow_offset = int(g("hook_shadow_offset", str(DEFAULT_HOOK_SHADOW_OFFSET)))
        hook_position_pct = float(g("hook_position_pct", str(DEFAULT_HOOK_POSITION_PCT)))
        hook_case = g("hook_case", DEFAULT_HOOK_CASE)
        base_image = None

        upload_id = g("upload_id")
        if upload_id and (TEMP_DIR / upload_id).exists():
            base_image = extract_preview(
                TEMP_DIR / upload_id,
                ar,
                zm,
                rm,
                background_type,
                background_color,
            )
        elif g("youtube_url").strip() and PREVIEW_FALLBACK_PATH.exists():
            base_image = reframe_image(
                Image.open(PREVIEW_FALLBACK_PATH),
                ar,
                zm,
                rm,
                background_type,
                background_color,
            )

        if base_image is None:
            return JSONResponse({"ok": False, "image": None})

        result = render_caption_preview(
            image=base_image,
            style_name=g("caption_style", DEFAULT_CAPTION_STYLE),
            font_name=g("font_name") or None,
            font_size=int(g("font_size", str(DEFAULT_FONT_SIZE))),
            active_color=g("active_color", "#FFD700"),
            inactive_color=g("inactive_color", "#FFFFFF"),
            background_color=g("background_color", "#000000") if int(g("background_opacity", "0")) > 0 else None,
            background_opacity=int(g("background_opacity", "0")),
            position="Bottom",
            words_per_line=int(g("words_per_line", "3")),
            lines_per_subtitle=int(g("lines_per_subtitle", "1")),
            effect=g("caption_effect", "Pop"),
            animation_speed=animation_speed,
            outline_enabled=g("outline_enabled", "true").lower() == "true",
            outline_color=g("outline_color", "#000000"),
            outline_width=int(g("outline_width", "3")),
            drop_shadow_enabled=g("drop_shadow_enabled", "false").lower() == "true",
            shadow_color=g("shadow_color", "#000000"),
            shadow_offset=int(g("shadow_offset", "4")),
            caption_position_pct=float(g("caption_position_pct", "78")),
            word_by_word=word_by_word,
            fade_in_words=fade_in_words,
            caption_case=caption_case,
            hook_text=hook_text_preview,
            show_hook=show_hook,
            hook_font_name=hook_font_name,
            hook_font_size=hook_font_size,
            hook_color=hook_color,
            hook_outline_enabled=hook_outline_enabled,
            hook_outline_color=hook_outline_color,
            hook_outline_width=hook_outline_width,
            hook_shadow_enabled=hook_shadow_enabled,
            hook_shadow_color=hook_shadow_color,
            hook_shadow_offset=hook_shadow_offset,
            hook_position_pct=hook_position_pct,
            hook_case=hook_case,
        )
        return JSONResponse({"ok": True, "image": pil_to_b64(result)})
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"ok": False, "error": str(e)})


@app.post("/api/process")
async def process(request: Request):
    form = await request.form()
    def g(k, d=""): return str(form.get(k, d) or d)

    youtube_url          = g("youtube_url")
    download_quality     = g("download_quality", DEFAULT_DOWNLOAD_QUALITY)
    whisper_model        = g("whisper_model", WHISPER_MODEL)
    aspect_ratio         = g("aspect_ratio", "9:16 (Vertical)")
    zoom                 = float(g("zoom", str(DEFAULT_ZOOM)))
    reframe_mode         = g("reframe_mode", DEFAULT_REFRAME_MODE)
    background_type      = g("background_type", DEFAULT_BACKGROUND_TYPE)
    background_color_bg  = g("background_color_bg", DEFAULT_BACKGROUND_COLOR)
    caption_style        = g("caption_style", DEFAULT_CAPTION_STYLE)
    active_color         = g("active_color", "#FFD700")
    inactive_color       = g("inactive_color", "#FFFFFF")
    background_color     = g("background_color", "#000000")
    background_opacity   = int(g("background_opacity", "60"))
    outline_enabled      = g("outline_enabled", "true").lower() == "true"
    outline_color        = g("outline_color", "#000000")
    outline_width        = int(g("outline_width", "3"))
    drop_shadow_enabled  = g("drop_shadow_enabled", "false").lower() == "true"
    shadow_color         = g("shadow_color", "#000000")
    shadow_offset        = int(g("shadow_offset", "4"))
    caption_position_pct = float(g("caption_position_pct", "78"))
    words_per_line       = int(g("words_per_line", str(DEFAULT_WORDS_PER_LINE)))
    lines_per_subtitle   = int(g("lines_per_subtitle", str(DEFAULT_LINES_PER_SUBTITLE)))
    font_name            = g("font_name", "")
    font_size            = int(g("font_size", str(DEFAULT_FONT_SIZE)))
    caption_effect       = g("caption_effect", DEFAULT_CAPTION_EFFECT)
    animation_speed_name = g("animation_speed", DEFAULT_ANIMATION_SPEED)
    animation_speed      = ANIMATION_SPEEDS.get(animation_speed_name, 1.0)
    caption_case         = g("caption_case", DEFAULT_CAPTION_CASE)
    word_by_word         = g("word_by_word", "false").lower() == "true"
    fade_in_words        = g("fade_in_words", "false").lower() == "true"
    show_hook            = g("show_hook", "false").lower() == "true"
    hook_font_name       = g("hook_font_name", "")
    hook_font_size       = int(g("hook_font_size", str(DEFAULT_HOOK_FONT_SIZE)))
    hook_color           = g("hook_color", DEFAULT_HOOK_COLOR)
    hook_outline_enabled = g("hook_outline_enabled", "true").lower() == "true"
    hook_outline_color   = g("hook_outline_color", DEFAULT_HOOK_OUTLINE_COLOR)
    hook_outline_width   = int(g("hook_outline_width", str(DEFAULT_HOOK_OUTLINE_WIDTH)))
    hook_shadow_enabled  = g("hook_shadow_enabled", "true").lower() == "true"
    hook_shadow_color    = g("hook_shadow_color", DEFAULT_HOOK_SHADOW_COLOR)
    hook_shadow_offset   = int(g("hook_shadow_offset", str(DEFAULT_HOOK_SHADOW_OFFSET)))
    hook_position_pct    = float(g("hook_position_pct", str(DEFAULT_HOOK_POSITION_PCT)))
    hook_case            = g("hook_case", DEFAULT_HOOK_CASE)
    mode                 = g("mode", "captions_only")
    provider             = g("provider", DEFAULT_PROVIDER)
    groq_model           = g("groq_model", DEFAULT_GROQ_MODEL)
    gemini_model         = g("gemini_model", DEFAULT_GEMINI_MODEL)
    or_model             = g("openrouter_model", DEFAULT_OPENROUTER_MODEL)
    ollama_model         = g("ollama_model", DEFAULT_OLLAMA_MODEL)
    num_clips            = int(g("num_clips", str(DEFAULT_NUM_CLIPS)))
    min_dur              = int(g("min_duration", str(DEFAULT_MIN_DURATION)))
    max_dur              = int(g("max_duration", str(DEFAULT_MAX_DURATION)))
    user_guidance        = g("user_guidance", "")
    include_hook         = show_hook

    num_clips = max(1, min(num_clips, 25))
    min_dur = max(15, min_dur)
    max_dur = max(15, max_dur)
    if max_dur < min_dur:
        max_dur = min_dur

    upload_id = g("upload_id")
    upload_path: Path | None = None
    if upload_id and (TEMP_DIR / upload_id).exists():
        upload_path = TEMP_DIR / upload_id

    async def event_stream():
        had_errors = False
        clip_paths: list[Path] = []
        caption_settings = {
            "style": caption_style, "font_name": font_name or None,
            "font_size": font_size, "active_color": active_color,
            "inactive_color": inactive_color,
            "background_color": background_color if background_opacity > 0 else None,
            "background_opacity": background_opacity, "position": "Bottom",
            "words_per_line": words_per_line, "lines_per_subtitle": lines_per_subtitle,
            "effect": caption_effect, "animation_speed": animation_speed,
            "word_by_word": word_by_word, "fade_in_words": fade_in_words,
            "caption_case": caption_case,
            "outline_enabled": outline_enabled,
            "outline_color": outline_color, "outline_width": outline_width,
            "drop_shadow_enabled": drop_shadow_enabled, "shadow_color": shadow_color,
            "shadow_offset": shadow_offset, "caption_position_pct": caption_position_pct,
            "show_hook": show_hook,
            "hook_font_name": hook_font_name or None,
            "hook_font_size": hook_font_size,
            "hook_color": hook_color,
            "hook_outline_enabled": hook_outline_enabled,
            "hook_outline_color": hook_outline_color,
            "hook_outline_width": hook_outline_width,
            "hook_shadow_enabled": hook_shadow_enabled,
            "hook_shadow_color": hook_shadow_color,
            "hook_shadow_offset": hook_shadow_offset,
            "hook_position_pct": hook_position_pct,
            "hook_case": hook_case,
            "hook_text": "",
        }

        try:
            _, resolved = resolve_font(font_name or None, caption_style, DEFAULT_FONT_SIZE)
            if resolved is None:
                yield sse("status", {"msg": "⚠️ No fonts in fonts/ folder. Using default font."})

            if youtube_url.strip() and upload_path:
                yield sse("status", {"msg": "⚠️ Both URL and file provided — using YouTube URL."})

            # Download
            yield sse("status", {"msg": "⬇️ Downloading video..."})
            yield sse("progress", {"value": 2})
            try:
                source_video = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: prepare_input_video(
                        youtube_url,
                        str(upload_path) if upload_path else None,
                        download_quality,
                    ),
                )
            except Exception as exc:
                yield sse("error", {"msg": friendly_error(exc, "download")})
                return

            # Transcribe
            yield sse("status", {"msg": "🎙️ Transcribing audio... (this may take a few minutes)"})
            yield sse("progress", {"value": 8})

            progress_q: asyncio.Queue = asyncio.Queue()

            def _cb(value, message):
                progress_q.put_nowait((value, message))

            loop = asyncio.get_event_loop()
            transcribe_task = loop.run_in_executor(
                None,
                lambda: transcribe_video(source_video, model_name=whisper_model, progress_callback=_cb),
            )

            while not transcribe_task.done():
                try:
                    val, msg = progress_q.get_nowait()
                    yield sse("progress", {"value": int(8 + val * 42)})
                    yield sse("status", {"msg": f"🎙️ {msg}"})
                except asyncio.QueueEmpty:
                    pass
                await asyncio.sleep(0.2)

            try:
                transcript = await transcribe_task
            except Exception as exc:
                traceback.print_exc()
                yield sse("error", {"msg": friendly_error(exc, "transcription")})
                return

            log("transcription complete")
            yield sse("progress", {"value": 55})

            video_duration = max((w["end"] for w in transcript["words"]), default=0.0)
            if mode == "captions_only":
                highlights = [{
                    "start_time": 0.0,
                    "end_time": video_duration,
                    "reason": "Full video with captions",
                    "virality_score": "N/A",
                    "hook": "",
                }]
            else:
                yield sse("status", {"msg": "🤖 Finding highlight moments with AI..."})
                yield sse("progress", {"value": 55})

                model = (
                    groq_model if provider == "Groq"
                    else gemini_model if provider == "Gemini"
                    else or_model if provider == "OpenRouter"
                    else ollama_model
                )
                api_keys = {
                    "groq":        os.environ.get("GROQ_API_KEY", ""),
                    "gemini":      os.environ.get("GOOGLE_API_KEY", ""),
                    "openrouter":  os.environ.get("OPENROUTER_API_KEY", ""),
                }
                detector = HighlightDetector(provider=provider, model=model, api_keys=api_keys)

                try:
                    highlights = await loop.run_in_executor(
                        None,
                        lambda: detector.find_highlights(
                            transcript["words"], num_clips, min_dur, max_dur,
                            user_guidance, include_hook
                        )
                    )
                except Exception as exc:
                    yield sse("error", {"msg": str(exc)})
                    return

                if not highlights:
                    yield sse("error", {"msg": "❌ AI returned no usable highlight segments. Try again."})
                    return

                yield sse("status", {"msg": f"✂️ Found {len(highlights)} highlight(s). Starting render..."})
                yield sse("progress", {"value": 62})

            ar_value = normalize_aspect_ratio(aspect_ratio)
            clip_prefix = "captions_only_" if mode == "captions_only" else "clip_"

            for idx, segment in enumerate(highlights, start=1):
                n = len(highlights)
                clip_caption_settings = {
                    **caption_settings,
                    "hook_text": segment.get("hook", "") if show_hook else "",
                }
                base_pct = 65 + int((idx - 1) / max(n, 1) * 28)
                yield sse("progress", {"value": base_pct})
                yield sse("status", {"msg": f"✂️ Cutting clip {idx} of {n}..."})
                yield sse("progress", {"value": min(base_pct + 7, 95)})
                if is_inset_mode(reframe_mode):
                    yield sse("status", {"msg": "🎨 Applying inset style (this takes a moment)..."})
                yield sse("status", {"msg": f"🎨 Rendering captions for clip {idx} of {n}..."})

                try:
                    clip_path = await loop.run_in_executor(
                        None,
                        lambda seg=segment, i=idx, clip_settings=clip_caption_settings: render_clip(
                            source_video=source_video,
                            clip_index=i,
                            segment=seg,
                            transcript_words=transcript["words"],
                            aspect_ratio=ar_value,
                            zoom=zoom,
                            reframe_mode=normalize_reframe_mode(reframe_mode),
                            background_type=background_type,
                            background_color=background_color_bg,
                            caption_settings=clip_settings,
                            clip_prefix=clip_prefix,
                        ),
                    )
                    clip_paths.append(clip_path)
                    yield sse("clip", {
                        "url": f"/outputs/{clip_path.name}",
                        "label": "Captioned Video" if mode == "captions_only" else (segment.get("hook") or f"Clip {idx}"),
                        "index": idx,
                        "mode": mode,
                        "score": segment.get("virality_score", "N/A"),
                    })
                    yield sse("status", {"msg": f"✅ Clip {idx} ready."})
                except Exception as exc:
                    had_errors = True
                    traceback.print_exc()
                    yield sse("status", {"msg": f"⚠️ Clip {idx} failed. {friendly_error(exc, 'clip rendering')}"})

            yield sse("progress", {"value": 98})
            yield sse("status", {"msg": "📦 Packaging outputs..."})
            try:
                zip_path = await loop.run_in_executor(None, lambda: build_zip_from_files(clip_paths))
                if zip_path:
                    yield sse("zip", {"url": f"/outputs/{zip_path.name}"})
            except Exception as exc:
                had_errors = True
                yield sse("status", {"msg": friendly_error(exc, "packaging")})

            if not had_errors:
                await loop.run_in_executor(None, clean_temp_dir)

            yield sse("progress", {"value": 100})
            yield sse("done", {"msg": f"✅ Done! {len(clip_paths)} clip(s) generated."})

        except Exception as exc:
            traceback.print_exc()
            yield sse("error", {"msg": friendly_error(exc, "pipeline")})
        finally:
            # We don't unlink upload_path here because the user might generate clips again
            pass

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/download/zip")
async def download_zip():
    clips = sorted(OUTPUT_DIR.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    zip_path = build_zip_from_files(clips)
    if not zip_path:
        return JSONResponse({"error": "No clips found."}, status_code=404)
    return FileResponse(str(zip_path), filename=zip_path.name, media_type="application/zip")


if __name__ == "__main__":
    import threading, webbrowser, time
    # Fix: ProactorEventLoop on Windows throws OSError when a client disconnects
    # from an SSE stream mid-transfer. SelectorEventLoop handles this cleanly.
    if sys.platform == "win32":
        import asyncio
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    def _open():
        time.sleep(1.2)
        webbrowser.open("http://localhost:7860")
    threading.Thread(target=_open, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=7860, log_level="info")
