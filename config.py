from pathlib import Path

try:
    # pyrefly: ignore [missing-import]
    import imageio_ffmpeg

    FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG_PATH = "ffmpeg"  # fallback to system ffmpeg


ROOT_DIR = Path(__file__).resolve().parent
WHISPER_MODEL = "large-v2"
WHISPER_MODEL_OPTIONS = ["tiny", "base", "small", "medium", "large-v2", "large-v3"]
WHISPER_DEVICE = "cuda"
WHISPER_COMPUTE_TYPE = "float16"
OUTPUT_DIR = ROOT_DIR / "outputs"
TEMP_DIR = ROOT_DIR / "temp"
FONTS_DIR = ROOT_DIR / "fonts"
DEFAULT_ASPECT_RATIO = "9:16"
DEFAULT_ZOOM = 1.0
DEFAULT_REFRAME_MODE = "Contain/Fit"
REFRAME_MODE_OPTIONS = [
    "Cover",
    "Contain/Fit",
    "Inset 16:9",
    "Inset Tall",
    "Inset 1:1",
]
BACKGROUND_TYPE_OPTIONS = ["Blur", "Solid Color"]
DEFAULT_BACKGROUND_TYPE = "Solid Color"
DEFAULT_BACKGROUND_COLOR = "#000000"
DEFAULT_DOWNLOAD_QUALITY = "1080p"
DEFAULT_CAPTION_STYLE = "CapCut"
DEFAULT_POSITION = "Bottom"


DEFAULT_WORDS_PER_LINE = 3
DEFAULT_LINES_PER_SUBTITLE = 1
DEFAULT_CAPTION_EFFECT = "None"
DEFAULT_ANIMATION_SPEED = "Medium"
DEFAULT_WORD_BY_WORD = False
DEFAULT_FADE_IN_WORDS = False
ANIMATION_SPEED_OPTIONS = ["Quick", "Medium", "Slow"]

DEFAULT_FONT_SIZE = 40
DEFAULT_CAPTION_CASE = "upper"
DEFAULT_SHOW_HOOK = False
DEFAULT_HOOK_CASE = "upper"
DEFAULT_HOOK_FONT_SIZE = 30
DEFAULT_HOOK_COLOR = "#FFFFFF"
DEFAULT_HOOK_OUTLINE = False
DEFAULT_HOOK_OUTLINE_COLOR = "#000000"
DEFAULT_HOOK_OUTLINE_WIDTH = 4
DEFAULT_HOOK_SHADOW = False
DEFAULT_HOOK_SHADOW_COLOR = "#000000"
DEFAULT_HOOK_SHADOW_OFFSET = 5
DEFAULT_HOOK_POSITION_PCT = 18.0
DEFAULT_HOOK_UPPERCASE = True
HOOK_LINE_CHAR_LIMIT = 18
DEFAULT_PROVIDER = "Gemini"
DEFAULT_GROQ_MODEL = "llama-3.1-8b-instant"
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash" # gemma-4-31b-it | gemini-3.5-flash
DEFAULT_OPENROUTER_MODEL = "google/gemma-4-26b-a4b-it:free"
DEFAULT_OLLAMA_MODEL = "qwen3.5:4b"
DEFAULT_NUM_CLIPS = 5
DEFAULT_MIN_DURATION = 15
DEFAULT_MAX_DURATION = 45
DEBUG_SAVE_AI_RESPONSE = True  # Set to False to disable saving raw AI responses in temp/
SUPPORTED_UPLOADS = [".mp4", ".mov", ".mkv", ".webm"]
DOWNLOAD_QUALITY_OPTIONS = ["2160p", "1440p", "1080p", "720p", "480p", "360p", "Best available"]

STYLE_PRESETS = {
    "CapCut": {
        "font_candidates": ["Montserrat-Bold.ttf", "Montserrat-Bold"],
        "font_size": 40,
        "active_color": "#FFD700",
        "inactive_color": "#FFFFFF",
        "background_color": "#000000",
        "background_opacity": 0,
        "outline_enabled": True,
        "outline_color": "#000000",
        "outline_width": 3,
        "drop_shadow_enabled": False,
        "shadow_color": "#000000",
        "shadow_offset": 4,
        "uppercase": True,
        "position": "Bottom",
    },
    "Minimal": {
        "font_candidates": ["Montserrat-Regular.ttf", "Montserrat-Regular"],
        "font_size": 40,
        "active_color": "#00CFFF",
        "inactive_color": "#EEEEEE",
        "background_color": None,
        "background_opacity": 0,
        "outline_enabled": True,
        "outline_color": "#333333",
        "outline_width": 2,
        "drop_shadow_enabled": False,
        "shadow_color": "#000000",
        "shadow_offset": 4,
        "uppercase": False,
        "position": "Bottom",
    },
    "Bold Drop Shadow": {
        "font_candidates": ["BebasNeue-Regular.ttf", "BebasNeue-Regular"],
        "font_size": 40,
        "active_color": "#FF4E50",
        "inactive_color": "#FFFFFF",
        "background_color": None,
        "background_opacity": 0,
        "outline_enabled": False,
        "outline_color": "#000000",
        "outline_width": 2,
        "drop_shadow_enabled": True,
        "shadow_color": "#000000",
        "shadow_offset": 4,
        "uppercase": True,
        "position": "Center",
    },
    "Neon Glow": {
        # Bright cyan active word on dark pill background — cyberpunk/gaming feel
        "font_candidates": ["Montserrat-Bold.ttf", "Montserrat-Bold"],
        "font_size": 40,
        "active_color": "#00FFC8",
        "inactive_color": "#AAAAAA",
        "background_color": "#0A0A0A",
        "background_opacity": 75,
        "outline_enabled": True,
        "outline_color": "#00FFC8",
        "outline_width": 2,
        "drop_shadow_enabled": True,
        "shadow_color": "#00FFC8",
        "shadow_offset": 3,
        "uppercase": True,
        "position": "Bottom",
    },

    "Fire": {
        # Orange-red active word, warm dark background — hype/sports content
        "font_candidates": ["BebasNeue-Regular.ttf", "BebasNeue-Regular"],
        "font_size": 44,
        "active_color": "#FF6B00",
        "inactive_color": "#FFD4A8",
        "background_color": "#1A0800",
        "background_opacity": 80,
        "outline_enabled": True,
        "outline_color": "#FF2200",
        "outline_width": 2,
        "drop_shadow_enabled": True,
        "shadow_color": "#FF4400",
        "shadow_offset": 3,
        "uppercase": True,
        "position": "Bottom",
    },

    "Clean White": {
        # Pure white text, no background, heavy shadow — works on any video
        "font_candidates": ["Montserrat-Bold.ttf", "Montserrat-Bold"],
        "font_size": 40,
        "active_color": "#FFFFFF",
        "inactive_color": "#CCCCCC",
        "background_color": None,
        "background_opacity": 0,
        "outline_enabled": False,
        "outline_color": "#000000",
        "outline_width": 2,
        "drop_shadow_enabled": True,
        "shadow_color": "#000000",
        "shadow_offset": 6,
        "uppercase": False,
        "position": "Bottom",
    },

    "Podcast": {
        # Muted palette, soft pill background — clean for talking head/podcast clips
        "font_candidates": ["Montserrat-Regular.ttf", "Montserrat-Regular"],
        "font_size": 36,
        "active_color": "#FFFFFF",
        "inactive_color": "#888888",
        "background_color": "#1C1C1E",
        "background_opacity": 85,
        "outline_enabled": False,
        "outline_color": "#000000",
        "outline_width": 2,
        "drop_shadow_enabled": False,
        "shadow_color": "#000000",
        "shadow_offset": 4,
        "uppercase": False,
        "position": "Bottom",
    },

    "Viral Yellow": {
        # Heavy black outline, yellow active — the classic viral short style
        "font_candidates": ["Montserrat-Bold.ttf", "Montserrat-Bold"],
        "font_size": 44,
        "active_color": "#FFE500",
        "inactive_color": "#FFFFFF",
        "background_color": None,
        "background_opacity": 0,
        "outline_enabled": True,
        "outline_color": "#000000",
        "outline_width": 6,
        "drop_shadow_enabled": True,
        "shadow_color": "#000000",
        "shadow_offset": 5,
        "uppercase": True,
        "position": "Bottom",
    },

    "Soft Pastel": {
        # Lavender active word, light semi-transparent pill — aesthetic/lifestyle content
        "font_candidates": ["Montserrat-Regular.ttf", "Montserrat-Regular"],
        "font_size": 36,
        "active_color": "#C8AAFF",
        "inactive_color": "#DDDDDD",
        "background_color": "#2A1F3D",
        "background_opacity": 70,
        "outline_enabled": False,
        "outline_color": "#000000",
        "outline_width": 2,
        "drop_shadow_enabled": True,
        "shadow_color": "#1A0A2E",
        "shadow_offset": 3,
        "uppercase": False,
        "position": "Bottom",
    },

    "Horrorcore": {
        # Deep red active word, heavy black bg, strong shadow — dark/edgy content
        "font_candidates": ["BebasNeue-Regular.ttf", "BebasNeue-Regular"],
        "font_size": 46,
        "active_color": "#FF1A1A",
        "inactive_color": "#888888",
        "background_color": "#0D0000",
        "background_opacity": 90,
        "outline_enabled": True,
        "outline_color": "#FF0000",
        "outline_width": 2,
        "drop_shadow_enabled": True,
        "shadow_color": "#FF0000",
        "shadow_offset": 5,
        "uppercase": True,
        "position": "Center",
    },
}

for directory in (OUTPUT_DIR, TEMP_DIR, FONTS_DIR):
    directory.mkdir(parents=True, exist_ok=True)
