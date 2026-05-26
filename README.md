# Revoclip

Revoclip is a local FastAPI-based short-form video clipping tool that helps you turn a long video into captioned vertical clips. You can paste a YouTube URL or upload a local video, transcribe it with Whisper, optionally let AI find the best highlight moments, and export ready-to-post MP4 clips with styled captions.

## Main Features

- Two working modes:
  - `AI Clip`: finds highlight moments with AI and renders multiple short clips
  - `Captions Only`: renders the full video with captions
- Input options:
  - YouTube URL
  - Local video upload
- AI provider support:
  - Groq
  - Gemini
  - OpenRouter
  - Ollama
- Whisper transcription with cached transcript reuse
- Multiple caption presets and custom caption controls
- Custom font loading from the `fonts/` folder
- Live preview before final render
- Automatic output packaging into ZIP
- Temporary working folder cleanup after successful runs


## Requirements

Before running Revoclip, make sure you have:

- Python 3.12 recommended
- `pip`
- Internet access for:
  - downloading Python packages
  - downloading YouTube videos
  - calling cloud AI providers if you use `AI Clip`
- Enough disk space for temporary video processing

## FFmpeg Note

This project tries to use `imageio-ffmpeg` automatically, so in many cases you do not need to install FFmpeg manually.

If FFmpeg is not detected correctly on your machine, install FFmpeg and make sure it is available in your system `PATH`.

## Installation

Clone the repository first:
```bash
git clone https://github.com/aayaan07/revoclip.git
cd revoclip
```

### Option 1: Quick setup (Windows)
1. Open the project folder in Command Prompt or PowerShell
2. Run:
```bat
setup.bat
```

3. Wait for the script to:
   - create a virtual environment
   - install dependencies
   - create `outputs/`, `temp/`, and `fonts/`
   - create a starter `.env` file if one does not exist
4. Edit the `.env` file and add your API keys if you want to use AI clipping.
5. Add your `.ttf` or `.otf` fonts into the `fonts/` folder if you want custom fonts.
6. Start the app:

```powershell
python run.py
```

7. Open `http://localhost:7860` in your browser if it does not open automatically.

### Option 2: Quick setup on macOS or Linux

1. Open a terminal in the project folder.
2. Make the script executable if needed:

```bash
chmod +x setup.sh
```

3. Run:

```bash
./setup.sh
```

4. Edit the `.env` file and add your API keys if you want to use AI clipping.
5. Add your `.ttf` or `.otf` fonts into the `fonts/` folder if you want custom fonts.
6. Start the app:

```bash
python run.py
```

7. Open `http://localhost:7860`.

## Manual Installation

If you want to do everything manually, follow these exact steps.

### Step 1: Open the project folder

Clone the repo and open the folder.

### Step 2: Create a virtual environment

Windows:

```powershell
python -m venv venv
```

macOS/Linux:

```bash
python3 -m venv venv
```

### Step 3: Activate the virtual environment

Windows PowerShell:

```powershell
venv\Scripts\Activate.ps1
```

Windows Command Prompt:

```cmd
venv\Scripts\activate.bat
```

macOS/Linux:

```bash
source .venv/bin/activate
```

### Step 4: Upgrade pip

```bash
python -m pip install --upgrade pip
```

### Step 5: Install all dependencies

```bash
pip install -r requirements.txt
```

### Step 6: Create required folders

The app usually creates these automatically, but you can create them yourself too:

```bash
mkdir outputs temp fonts
```

On Windows PowerShell, if `mkdir` is used multiple times, this also works:

```powershell
mkdir outputs
mkdir temp
mkdir fonts
```

### Step 7: Create the environment file

Copy the example file:

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

macOS/Linux:

```bash
cp .env.example .env
```

If that does not work, manually create a file named `.env` in the project root.

### Step 8: Add your API keys

Open `.env` and fill in the values you want:

```env
GROQ_API_KEY=
GOOGLE_API_KEY=
OPENROUTER_API_KEY=
```

Notes:

- `Captions Only` mode does not need an AI provider key.
- `AI Clip` mode needs a provider depending on what you select in the UI.
- Ollama works locally and does not use an API key, but Ollama must be running on your machine.

### Step 9: Add fonts

Put your custom `.ttf` or `.otf` files into the `fonts/` folder.

### Step 10: Start the application

```bash
python run.py
```

### Step 11: Open the app

Open:

```text
http://localhost:7860
```

## How To Use Revoclip

### 1. Launch the app

Run:

```bash
python run.py
```

### 2. Choose a mode

- `AI Clip`: finds multiple highlight clips using AI
- `Captions Only`: captions the full video without highlight extraction

### 3. Add a video source

Choose one:

- Paste a YouTube URL
- Upload a local video file

Supported local upload types from the current config:

- `.mp4`
- `.mov`
- `.mkv`
- `.webm`

### 4. Configure video settings

You can adjust settings such as:

- aspect ratio
- zoom
- reframe mode
- background type
- background color
- caption style
- words per line
- lines per subtitle
- font
- font size
- hook text styling
- animation speed

### 5. If using AI Clip mode, choose an AI provider

Available provider choices:

- Groq
- Gemini
- OpenRouter
- Ollama

You can also set:

- provider model
- number of clips
- minimum clip duration
- maximum clip duration
- optional guidance for what type of clips the AI should find

### 6. Generate clips

Click the generate/process button in the UI and wait for:

- video preparation
- transcription
- optional AI highlight detection
- caption rendering
- packaging

### 7. Find your results

Final clips are saved in `outputs/`.

## Fonts

Revoclip supports custom fonts placed inside the `fonts/` folder.

### How fonts work

- The app scans the `fonts/` folder for `.ttf` and `.otf` files.
- Fonts found there are shown in the UI.
- If a selected font file cannot be found, the app falls back to Pillow's default font.

### Bundled fonts currently present in this repository

- `SuperJoyful-lxwPq.ttf`
- `naked-power.bold.ttf`
- `naked-power.bold-italic.ttf`
- `montserrat.semibold.ttf`
- `montserrat.semibold-italic.ttf`
- `montserrat.medium.ttf`
- `montserrat.medium-italic.ttf`
- `montserrat.bold.ttf`
- `montserrat.bold-italic.ttf`
- `Montserrat-Black.ttf`
- `bcc-mro-serif.regular.ttf`

NOTE: All the fonts have been downloaded from [1001fonts](https://www.1001fonts.com/).

### Important note about presets

Some caption presets in `config.py` reference font candidate names such as `Montserrat-Bold.ttf`, `Montserrat-Regular.ttf`, and `BebasNeue-Regular.ttf`. If those exact files are not present in `fonts/`, the app will use the next available fallback.

If you want exact preset matching, add font files with the expected filenames into `fonts/`.

## Output Folder

The `outputs/` folder stores the final generated files.

Typical contents:

- rendered clip files such as `clip_1.mp4`
- full-video caption exports such as `captions_only_clip_1.mp4`
- ZIP packages like `revoclip_YYYYMMDD_HHMMSS.zip`

Notes:

- This folder is mounted by FastAPI and served at `/outputs`
- The frontend reads generated clips from here
- This is the main folder you will use for final exported results

## Temp Folder

The `temp/` folder is used for intermediate working files.

Typical contents may include:

- uploaded video files
- copied source videos
- downloaded YouTube videos
- transcript cache files like `transcript_<hash>.json`
- temporary cut/reframed/captioned video files
- saved raw AI responses when debug saving is enabled

Notes:

- `config.py` currently sets `DEBUG_SAVE_AI_RESPONSE = True`
- successful runs trigger cleanup of most temporary files
- cached transcript files named `transcript_*.json` are intentionally preserved

## Contributing

Contributions are welcome.

If you want to contribute:

1. Fork the repository.
2. Create a new branch for your change.
3. Make your edits.
4. Test the app locally.
5. Open a pull request with a clear description of what changed and why.

Suggested contribution areas:

- better caption styles
- improved clip scoring prompts
- more robust model/provider handling
- performance improvements
- UI polish
- bug fixes
- documentation improvements

When contributing, try to:

- keep changes focused
- document new settings
- avoid breaking existing workflow
- mention any required environment variables or model changes

## License

Revoclip is licensed under the Revoclip Community License (RCL).

✔ Personal use  
✔ Creator monetization  
✔ Freelance / agency content creation  
✔ Self-hosting  
✔ Modifications for personal/internal use  

✘ Reselling the software  
✘ SaaS hosting / competing services  
✘ Commercial software integration  
✘ White-label redistribution



