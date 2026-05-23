import hashlib
import json
import subprocess
import sys
from pathlib import Path

from config import TEMP_DIR, WHISPER_COMPUTE_TYPE, WHISPER_DEVICE, WHISPER_MODEL


def _video_hash(video_path: Path, model_name: str) -> str:
    stat = video_path.stat()
    payload = f"{video_path.name}:{stat.st_size}:{model_name}".encode("utf-8")
    return hashlib.md5(payload).hexdigest()


def transcript_cache_path(video_path: Path, model_name: str) -> Path:
    return TEMP_DIR / f"transcript_{_video_hash(video_path, model_name)}.json"


def _read_worker_events(process, progress_callback, model_name: str):
    final_complete_event = None
    if process.stdout is None:
        return final_complete_event

    for raw_line in process.stdout:
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            print(f"[Revoclip] worker log: {line}", flush=True)
            continue

        event_type = event.get("type")
        if event_type == "stage":
            print(f"[Revoclip] {event.get('message', 'worker stage')}", flush=True)
        elif event_type == "progress":
            if progress_callback:
                progress_callback(float(event.get("value", 0.0)), event.get("message", "Transcribing audio..."))
        elif event_type == "complete":
            final_complete_event = event
            print(
                (
                    f"[Revoclip] transcription complete model={model_name} "
                    f"device={event.get('device')} compute_type={event.get('compute_type')} "
                    f"elapsed={float(event.get('elapsed_seconds', 0.0)):.1f}s "
                    f"audio_duration={float(event.get('audio_duration', 0.0)):.1f}s "
                    f"speed={float(event.get('speed_multiple', 0.0)):.2f}x"
                ),
                flush=True,
            )
            if progress_callback:
                progress_callback(1.0, event.get("message", "Transcription complete."))

    return final_complete_event


def _run_transcription_worker(video_path: Path, output_path: Path, model_name: str, device: str, compute_type: str, progress_callback=None):
    worker_script = Path(__file__).resolve().with_name("transcribe_worker.py")
    command = [
        sys.executable,
        str(worker_script),
        str(video_path),
        str(output_path),
        model_name,
        device,
        compute_type,
    ]
    print(
        f"[Revoclip] transcription start model={model_name} device={device} compute_type={compute_type}",
        flush=True,
    )
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    complete_event = _read_worker_events(process, progress_callback, model_name)
    process.wait()
    if process.returncode != 0:
        if complete_event is not None and output_path.exists():
            print(
                (
                    f"[Revoclip] transcription worker exited with code {process.returncode} "
                    "after completion event; using completed transcript output"
                ),
                flush=True,
            )
            return json.loads(output_path.read_text(encoding="utf-8"))
        if process.returncode < 0:
            raise RuntimeError(f"transcription worker terminated by signal {-process.returncode}")
        raise RuntimeError(f"transcription worker exited with code {process.returncode}")
    if not output_path.exists():
        raise RuntimeError("transcription worker completed without producing transcript output")
    if progress_callback and complete_event is None:
        progress_callback(1.0, f"Transcription complete on {device}/{compute_type}.")
    return json.loads(output_path.read_text(encoding="utf-8"))


def transcribe_video(video_path: Path, model_name: str | None = None, progress_callback=None) -> dict:
    model_name = model_name or WHISPER_MODEL
    cache_path = transcript_cache_path(video_path, model_name)
    if cache_path.exists():
        if progress_callback:
            progress_callback(1.0, f"Loaded cached transcript for {model_name}.")
        print(f"[Revoclip] transcription cache hit file={video_path.name} model={model_name}", flush=True)
        return json.loads(cache_path.read_text(encoding="utf-8"))

    output_path = cache_path
    try:
        if progress_callback:
            progress_callback(0.02, f"Loading Whisper model {model_name} on {WHISPER_DEVICE}...")
        return _run_transcription_worker(
            video_path=video_path,
            output_path=output_path,
            model_name=model_name,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE,
            progress_callback=progress_callback,
        )
    except Exception as primary_exc:
        if WHISPER_DEVICE != "cpu":
            if progress_callback:
                progress_callback(0.04, f"GPU transcription failed, retrying on CPU... ({primary_exc})")
            print(
                f"[Revoclip] gpu transcription failed device={WHISPER_DEVICE} compute_type={WHISPER_COMPUTE_TYPE}: {primary_exc}",
                flush=True,
            )
            return _run_transcription_worker(
                video_path=video_path,
                output_path=output_path,
                model_name=model_name,
                device="cpu",
                compute_type="int8",
                progress_callback=progress_callback,
            )
        raise RuntimeError(f"Whisper transcription failed on cpu/{WHISPER_COMPUTE_TYPE}: {primary_exc}") from primary_exc
