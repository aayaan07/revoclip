#!/usr/bin/env bash
set -e
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
mkdir -p outputs temp fonts
if [ ! -f .env ]; then
  cat <<'EOF' > .env
GROQ_API_KEY=your_groq_key_here
OPENROUTER_API_KEY=your_openrouter_key_here
EOF
fi
echo "1. FFmpeg is bundled automatically — no manual install needed."
echo "2. Get free Groq API key: https://console.groq.com"
echo "3. Get free OpenRouter API key: https://openrouter.ai"
echo "4. Add keys to .env file"
echo "5. Add font .ttf files to fonts/ folder"
echo "6. Run: python run.py"
