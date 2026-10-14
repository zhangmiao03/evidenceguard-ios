#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
VENV_PATH="${EG_VISION_VENV:-$HOME/.cache/evidenceguard-vision-lab/venv}"
RUN_NAME="${1:?Pass the result run name}"
DURATION="${2:-60}"
if [[ ! "$RUN_NAME" =~ ^[A-Za-z0-9_-]+$ || ! "$DURATION" =~ ^[0-9]+$ ]]; then
  printf 'Invalid arguments\n' >&2
  exit 2
fi
systemd-run --unit="eg-vision-${RUN_NAME}-sustained" --wait --pipe --collect --quiet \
  -p CPUQuota=100% -p MemoryMax=2G -p MemorySwapMax=0 \
  -p CPUAccounting=yes -p MemoryAccounting=yes \
  /usr/bin/env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONUNBUFFERED=1 \
  "$VENV_PATH/bin/python" "$PWD/sustained.py" --run "$RUN_NAME" --seconds "$DURATION"
