import json
import os
import sys
import time
from pathlib import Path

from faster_whisper import WhisperModel


def emit(event: dict):
    print(json.dumps(event, ensure_ascii=True), flush=True)


def format_elapsed(seconds: float) -> str:
    total_seconds = max(int(seconds), 0)
    minutes, secs = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def main():
    if len(sys.argv) != 6:
        raise SystemExit("usage: transcribe_worker.py <video_path> <output_path> <model> <device> <compute_type>")

    video_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    model_name = sys.argv[3]
    device = sys.argv[4]
    compute_type = sys.argv[5]

    start_time = time.perf_counter()
    emit(
        {
            "type": "stage",
            "message": f"transcription worker start model={model_name} device={device} compute_type={compute_type}",
        }
    )
    model = WhisperModel(model_name, device=device, compute_type=compute_type)
    segments, info = model.transcribe(str(video_path), word_timestamps=True, vad_filter=True)

    transcript_segments = []
    all_words = []
    full_text = []
    total_duration = max(float(getattr(info, "duration", 0.0) or 0.0), 0.0)

    for segment in segments:
        seg_words = []
        for word in segment.words or []:
            item = {
                "word": word.word.strip(),
                "start": float(word.start or 0.0),
                "end": float(word.end or word.start or 0.0),
            }
            if not item["word"]:
                continue
            seg_words.append(item)
            all_words.append(item)
        transcript_segments.append(
            {
                "start": float(segment.start),
                "end": float(segment.end),
                "text": segment.text.strip(),
                "words": seg_words,
            }
        )
        if segment.text.strip():
            full_text.append(segment.text.strip())
        if total_duration > 0:
            progress_value = min(float(segment.end) / total_duration, 1.0)
            elapsed = time.perf_counter() - start_time
            emit(
                {
                    "type": "progress",
                    "value": progress_value,
                    "message": (
                        f"Transcribing audio on {device}/{compute_type}... "
                        f"{int(progress_value * 100)}% | elapsed {format_elapsed(elapsed)}"
                    ),
                }
            )

    payload = {
        "language": getattr(info, "language", None),
        "segments": transcript_segments,
        "words": all_words,
        "text": "\n".join(full_text),
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    elapsed = time.perf_counter() - start_time
    audio_duration = max(float(getattr(info, "duration", 0.0) or 0.0), 0.0)
    speed_multiple = (audio_duration / elapsed) if elapsed > 0 and audio_duration > 0 else 0.0
    emit(
        {
            "type": "complete",
            "elapsed_seconds": elapsed,
            "audio_duration": audio_duration,
            "speed_multiple": speed_multiple,
            "device": device,
            "compute_type": compute_type,
            "message": (
                f"Transcription complete on {device}/{compute_type}. "
                f"Elapsed {format_elapsed(elapsed)} at {speed_multiple:.2f}x realtime."
            ),
        }
    )
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    main()
