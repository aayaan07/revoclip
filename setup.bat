@echo off
echo.
echo  Setting up Revoclip...
echo.

:: Check Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python not found. Install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

:: Create virtual environment
echo  Creating virtual environment...
python -m venv venv
if errorlevel 1 (
    echo  ERROR: Failed to create virtual environment.
    pause
    exit /b 1
)

:: Activate and upgrade pip
call venv\Scripts\activate
echo  Upgrading pip...
python -m pip install --upgrade pip --quiet

:: Install dependencies
echo  Installing dependencies (this may take a few minutes)...
pip install -r requirements.txt
if errorlevel 1 (
    echo  ERROR: Failed to install dependencies. Check requirements.txt.
    pause
    exit /b 1
)

:: Create folders
if not exist outputs mkdir outputs
if not exist temp    mkdir temp
if not exist fonts   mkdir fonts

:: Create .env only if it doesn't exist
if not exist .env (
    echo GROQ_API_KEY=your_groq_key_here>  .env
    echo GOOGLE_API_KEY=your_google_key_here>> .env
    echo OPENROUTER_API_KEY=your_openrouter_key_here>> .env
    echo  Created .env file with placeholder keys.
) else (
    echo  .env file already exists -- skipping.
)

echo.
echo  ============================================
echo   Revoclip setup complete!
echo  ============================================
echo.
echo  Next steps:
echo.
echo   1. Add your API keys to the .env file
echo      - Groq (free):        https://console.groq.com
echo      - Google (free):      https://aistudio.google.com/app/apikey
echo      - OpenRouter (free):  https://openrouter.ai
echo      - Ollama (offline):   https://ollama.com  then: ollama pull qwen2.5:4b
echo.
echo   2. Add font .ttf files to the fonts/ folder
echo      - Recommended: Montserrat, Bebas Neue from https://fonts.google.com
echo.
echo   3. FFmpeg is bundled automatically -- no manual install needed.
echo.
echo   4. Start Revoclip:
echo      python run.py
echo.
pause
