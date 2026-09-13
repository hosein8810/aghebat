#!/usr/bin/env bash
# اجرای بات عاقبت روی لینوکس (و macOS). از ریشه پروژه صدا بزنید: ./run.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 پیدا نشد. روی لینوکس مثلاً: sudo apt install python3 python3-venv python3-pip"
  exit 1
fi

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install -q --upgrade pip
python -m pip install -q -r requirements.txt

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "فایل .env ساخته شد. BOT_TOKEN و OWNERS را پر کنید و دوباره ./run.sh را اجرا کنید."
  exit 1
fi

if grep -qE '^BOT_TOKEN=123456:ABC-DEF[[:space:]]*$' .env || grep -qE '^BOT_TOKEN=[[:space:]]*$' .env; then
  echo "BOT_TOKEN در فایل .env هنوز نمونه است. توکن واقعی را از @BotFather بگذارید."
  exit 1
fi

mkdir -p data
exec python main.py
