#!/usr/bin/env bash
set -euo pipefail

# OpenCFD feature-gpu build validation for CFD Studio.
# Usage: validate_gpu_only.sh [gpu-bashrc] [physical-gpu-index]

BASHRC_PATH=${1:-$HOME/OpenFOAM/openfoam-ecse/etc/bashrc}
GPU_INDEX=${2:-0}
MARKER=$HOME/.cfd_studio_gpu_only_ready.json
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SOURCE_CASE=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

if pgrep -f '[i]coReactingMultiphaseInterFoam([[:space:]]|$)' >/dev/null 2>&1; then
    echo "[중단] CFD 솔버 실행 중에는 GPU 런타임 검증을 수행하지 않습니다."
    exit 20
fi
if [ ! -f "$BASHRC_PATH" ]; then
    echo "[중단] GPU OpenFOAM bashrc 없음: $BASHRC_PATH"
    exit 21
fi

export CUDA_VISIBLE_DEVICES=$GPU_INDEX
export FOAM_MEMORY_POOL='managed; size=1024; incr=1024'
source "$BASHRC_PATH" WM_COMPILER=Nvidia-gpu

[ "${WM_COMPILER:-}" = Nvidia-gpu ] || { echo "[중단] WM_COMPILER=Nvidia-gpu가 아닙니다."; exit 22; }
command -v nvc++ >/dev/null || { echo "[중단] NVIDIA HPC SDK nvc++가 없습니다."; exit 23; }
SOLVER=$(command -v icoReactingMultiphaseInterFoam || true)
[ -n "$SOLVER" ] || { echo "[중단] GPU 빌드 icoReactingMultiphaseInterFoam이 없습니다."; exit 24; }
GPU_LIST=$(nvidia-smi --query-gpu=index --format=csv,noheader 2>/dev/null | tr -d ' ')
printf '%s\n' "$GPU_LIST" | grep -qx "$GPU_INDEX" || { echo "[중단] 선택 GPU를 WSL에서 사용할 수 없습니다."; exit 25; }

TEST_DIR=$WM_PROJECT_DIR/applications/test/std_execution
[ -d "$TEST_DIR" ] || { echo "[중단] 공식 std_execution 테스트 소스가 없습니다."; exit 26; }
if ! command -v Test-std_execution >/dev/null 2>&1; then
    echo "[검증] OpenCFD 공식 std::execution 테스트 빌드"
    (cd "$TEST_DIR" && wmake)
fi
TEST_EXE=$(command -v Test-std_execution)

CASE_DIR=$(find "$WM_PROJECT_DIR/tutorials" -type d -path '*/icoFoam/cavity/cavity' -print -quit 2>/dev/null || true)
[ -n "$CASE_DIR" ] || { echo "[중단] std::execution 테스트용 cavity 케이스가 없습니다."; exit 27; }
LOG=$(mktemp /tmp/cfd_gpu_only_validation.XXXXXX.log)
SMOKE_DIR=$(mktemp -d /tmp/cfd_gpu_only_case.XXXXXX)
trap 'rm -f "$LOG"; rm -rf "$SMOKE_DIR"' EXIT

echo "[검증] GPU std::execution + Umpire managed pool 실행"
(cd "$CASE_DIR" && timeout 300 "$TEST_EXE") 2>&1 | tee "$LOG"
grep -q 'Parallel fill took' "$LOG" || { echo "[중단] GPU 병렬 STL 테스트가 완료되지 않았습니다."; exit 28; }
grep -qE 'memory pool[[:space:]]*:[[:space:]]*managed' "$LOG" || {
    echo "[중단] Umpire managed memory pool이 활성화되지 않았습니다."
    exit 29
}

echo "[검증] CFD Studio 3상 상변화 솔버 초단기 GPU 실행"
cp -a "$SOURCE_CASE/." "$SMOKE_DIR/"
rm -rf "$SMOKE_DIR"/processor* "$SMOKE_DIR"/[1-9]* "$SMOKE_DIR"/VTK "$SMOKE_DIR"/postProcessing
rm -f "$SMOKE_DIR"/log.* "$SMOKE_DIR"/.cfd_studio_*
python3 - "$SMOKE_DIR/config.json" <<'PY'
import json, sys
p = sys.argv[1]
with open(p, encoding="utf-8") as f: c = json.load(f)
c.setdefault("mesh", {})["dx_mm"] = 12.0
r = c.setdefault("run", {})
r.update(end_time_s=0.004, write_interval_s=0.004, viz_interval_s=0.002,
         max_dt_s=0.001, output_fields=["therm"])
with open(p, "w", encoding="utf-8") as f:
    json.dump(c, f, ensure_ascii=False, indent=2); f.write("\n")
PY
SMOKE_LOG="$SMOKE_DIR/log.gpu-smoke"
(cd "$SMOKE_DIR" && timeout 900 env CFD_STUDIO_COMPUTE_MODE=gpu_only \
    CFD_STUDIO_PRESSURE_SOLVER_MODE=gpu_only NP=1 ./Allrun) 2>&1 | tee "$SMOKE_LOG"
SOLVER_LOG="$SMOKE_DIR/log.icoReactingMultiphaseInterFoam"
[ -s "$SOLVER_LOG" ] || { echo "[중단] GPU 실제 케이스 솔버 로그가 생성되지 않았습니다."; exit 30; }
grep -q '^Time = ' "$SOLVER_LOG" || { echo "[중단] GPU 실제 케이스가 시간 적분을 시작하지 못했습니다."; exit 31; }
grep -qE '^End[[:space:]]*$' "$SOLVER_LOG" || { echo "[중단] GPU 실제 케이스가 정상 종료되지 않았습니다."; exit 32; }
grep -qE 'memory pool[[:space:]]*:[[:space:]]*managed' "$SOLVER_LOG" || { echo "[중단] 실제 케이스에서 managed pool이 확인되지 않았습니다."; exit 33; }
if grep -qiE 'cudaError|Thrust failure|parallel_for: failed|floating point exception|segmentation fault' "$SOLVER_LOG"; then
    echo "[중단] GPU 실제 케이스 로그에서 치명적 오류를 발견했습니다."
    exit 34
fi

COMMIT=$(git -C "$WM_PROJECT_DIR" rev-parse HEAD 2>/dev/null || true)
CC=$(nvidia-smi -i "$GPU_INDEX" --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | head -1 | tr -d ' ')
GPU_NAME=$(nvidia-smi -i "$GPU_INDEX" --query-gpu=name --format=csv,noheader | head -1 | sed 's/^ *//;s/ *$//')
GPU_UUID=$(nvidia-smi -i "$GPU_INDEX" --query-gpu=uuid --format=csv,noheader | head -1 | tr -d ' ')
DRIVER=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1 | tr -d ' ')
COMPILER=$(nvc++ --version 2>/dev/null | head -1)
python3 - "$MARKER" "$SOLVER" "$BASHRC_PATH" "$COMMIT" "$CC" "$GPU_NAME" "$GPU_UUID" "$DRIVER" "$COMPILER" <<'PY'
import datetime, json, os, sys
path, solver, bashrc, commit, cc, gpu_name, gpu_uuid, driver, compiler = sys.argv[1:]
st = os.stat(solver)
data = {
    "ready": True,
    "umpire": True,
    "case_smoke": True,
    "solver": os.path.realpath(solver),
    "solver_size": st.st_size,
    "solver_mtime_ns": st.st_mtime_ns,
    "bashrc": os.path.realpath(bashrc),
    "source_commit": commit,
    "compute_capability": cc,
    "gpu_name": gpu_name,
    "gpu_uuid_at_validation": gpu_uuid,
    "driver_version": driver,
    "compiler": compiler,
    "wsl_kernel": os.uname().release,
    "validated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "validator": "OpenCFD Test-std_execution + CFD Studio three-phase smoke",
}
tmp = path + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.write("\n")
os.replace(tmp, path)
PY

echo "[완료] CFD Studio GPU Only 검증 완료: $MARKER"
