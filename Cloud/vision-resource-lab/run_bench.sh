#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
LAB_ROOT="$PWD"
VENV_PATH="${EG_VISION_VENV:-$HOME/.cache/evidenceguard-vision-lab/venv}"
PYTHON_BIN="$VENV_PATH/bin/python"
RUN_NAME="${1:-$(date +%Y%m%d-%H%M%S)}"
if [[ ! "$RUN_NAME" =~ ^[A-Za-z0-9_-]+$ ]]; then
  printf 'Invalid run name\n' >&2
  exit 2
fi
if [[ -e "results/$RUN_NAME" ]]; then
  printf 'Run already exists; choose a fresh name: %s\n' "$RUN_NAME" >&2
  exit 2
fi
mkdir -p "results/$RUN_NAME"
for PROFILE in server-budget worker-budget; do
  if [[ "$PROFILE" == server-budget ]]; then
    CPU_BUDGET=2; THREADS=2; MEMORY_GIB=4
  else
    CPU_BUDGET=1; THREADS=1; MEMORY_GIB=2
  fi
  run_case() {
    local case_name="$1"
    shift
    systemd-run --unit="eg-vision-${RUN_NAME}-${PROFILE}-${case_name}" \
      --wait --pipe --collect --quiet \
      -p "CPUQuota=$((CPU_BUDGET * 100))%" \
      -p "MemoryMax=${MEMORY_GIB}G" -p MemorySwapMax=0 \
      -p CPUAccounting=yes -p MemoryAccounting=yes \
      /usr/bin/env "OMP_NUM_THREADS=$THREADS" "OPENBLAS_NUM_THREADS=$THREADS" \
      "MKL_NUM_THREADS=$THREADS" PYTHONUNBUFFERED=1 \
      "$PYTHON_BIN" "$LAB_ROOT/benchmark.py" \
      --cpu-budget "$CPU_BUDGET" --memory-gib "$MEMORY_GIB" --threads "$THREADS" \
      --run "$RUN_NAME" --profile "$PROFILE" "$@" \
      2>&1 | tee "$LAB_ROOT/results/$RUN_NAME/${PROFILE}-${case_name}.log"
  }
  run_case depthart224 --kind depth --model depthart224 --resolution 224
  run_case depthart448 --kind depth --model depthart448 --resolution 448
  run_case dav2small --kind depth --model dav2small --resolution 518
  run_case dis --kind flow --algorithm dis
  run_case farneback --kind flow --algorithm farneback
done
printf 'Complete: %s/results/%s\n' "$LAB_ROOT" "$RUN_NAME"
