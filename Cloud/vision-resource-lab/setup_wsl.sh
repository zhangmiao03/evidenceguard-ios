#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
VENV_PATH="${EG_VISION_VENV:-$HOME/.cache/evidenceguard-vision-lab/venv}"
python3 -m venv "$VENV_PATH"
"$VENV_PATH/bin/python" -m pip install --disable-pip-version-check -r requirements.txt
"$VENV_PATH/bin/python" -m pip freeze > requirements-resolved.txt
printf 'Environment ready: %s\n' "$VENV_PATH"
