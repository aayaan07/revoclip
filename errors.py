def friendly_error(e: Exception, context: str = "") -> str:
    msg = str(e).lower()

    if "api key" in msg or "401" in msg or "unauthorized" in msg:
        return "❌ API key invalid or missing. Check your .env file."
    if "429" in msg or "rate limit" in msg:
        return "⏳ Rate limit hit. Wait a moment and try again."
    if "model" in msg and ("not found" in msg or "404" in msg):
        return "❌ Model not found. Check the model name and try again."
    if "timeout" in msg or "timed out" in msg:
        return "⏱️ AI provider timed out. Try again or switch providers."
    if "connection" in msg or "refused" in msg or "network" in msg:
        return "🌐 Cannot connect. Check your internet connection."
    if "ffmpeg" in msg or "no such file" in msg:
        return "⚙️ FFmpeg not found. Make sure FFmpeg is installed and in PATH."
    if "cuda" in msg or "gpu" in msg:
        return "🖥️ GPU error. Try switching Whisper to CPU in config.py."
    if "whisper" in msg or "transcri" in msg:
        return "🎙️ Transcription failed. Check that the video has audio."
    if "download" in msg or "yt" in msg or "youtube" in msg:
        return "📥 Download failed. Check the URL or try a different video."
    if "json" in msg or "parse" in msg:
        return "🤖 AI returned unexpected output. Retrying may help."
    if "disk" in msg or "space" in msg or "no space" in msg:
        return "💾 Disk full. Free up space and try again."
    return f"❌ Something went wrong{' during ' + context if context else ''}. Please try again."
