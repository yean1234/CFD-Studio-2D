#!/usr/bin/env bash
set -euo pipefail

# Build the OpenCFD feature-gpu runtime selected by CFD Studio.
# The NVIDIA installer requires explicit EULA acknowledgement:
#   CFD_STUDIO_ACCEPT_NVIDIA_EULA=YES ./tools/install_gpu_only_openfoam.sh

GPU_INDEX=${GPU_INDEX:-0}
JOBS=${JOBS:-4}
OF_ROOT=${OF_ROOT:-$HOME/OpenFOAM/openfoam-ecse}
OF_COMMIT=${OF_COMMIT:-f36870083be0f391cf44c4aa6e1623214282e271}
TP_ROOT=${TP_ROOT:-$HOME/OpenFOAM/ThirdParty-v2606}
NVHPC_ROOT=${NVHPC_ROOT:-$HOME/.local/nvidia/hpc_sdk}
DOWNLOAD_DIR=${DOWNLOAD_DIR:-$HOME/.cache/cfd-studio-gpu}
NVHPC_URL=https://developer.download.nvidia.com/hpc-sdk/24.9/nvhpc_2024_249_Linux_x86_64_cuda_12.6.tar.gz
THIRDPARTY_URL=https://downloads.sourceforge.net/project/openfoam/v2606/ThirdParty-v2606.tar.gz
UMPIRE_URL=https://github.com/LLNL/Umpire/releases/download/v2025.03.0/umpire-2025.03.0.tar.gz
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
NVARCH=$(uname -s)_$(uname -m)
export NVCOMPILERS="$NVHPC_ROOT"
export PATH="$NVCOMPILERS/$NVARCH/24.9/compilers/bin:$NVCOMPILERS/$NVARCH/24.9/cuda/12.6/bin:$PATH"
export LD_LIBRARY_PATH="$NVCOMPILERS/$NVARCH/24.9/cuda/12.6/lib64:${LD_LIBRARY_PATH:-}"

die() { echo "[중단] $*" >&2; exit 1; }
has_supported_nvcxx() {
    command -v nvc++ >/dev/null 2>&1 &&
        nvc++ --version 2>/dev/null | head -1 | grep -Eq 'nvc\+\+[[:space:]]+24[.]9([-.[:space:]]|$)'
}

if pgrep -f '[i]coReactingMultiphaseInterFoam([[:space:]]|$)' >/dev/null 2>&1; then
    die "CFD 솔버가 실행 중입니다. 현재 계산이 끝난 뒤 GPU 빌드를 시작하세요."
fi
case "$JOBS" in ''|*[!0-9]*) die "JOBS는 1 이상의 정수여야 합니다.";; esac
[ "$JOBS" -ge 1 ] || die "JOBS는 1 이상이어야 합니다."
for cmd in curl tar git cmake make gcc g++ python3 nvidia-smi; do
    command -v "$cmd" >/dev/null 2>&1 || die "필수 도구가 없습니다: $cmd"
done
GPU_LIST=$(nvidia-smi --query-gpu=index --format=csv,noheader 2>/dev/null | tr -d ' ')
printf '%s\n' "$GPU_LIST" | grep -qx "$GPU_INDEX" || die "GPU $GPU_INDEX 를 WSL에서 사용할 수 없습니다."
CC=$(nvidia-smi -i "$GPU_INDEX" --query-gpu=compute_cap --format=csv,noheader | head -1 | tr -d ' ')
printf '%s\n' "$CC" | grep -Eq '^[0-9]+[.][0-9]+$' || die "GPU compute capability를 확인할 수 없습니다: $CC"
CC_TAG=${CC/./}

mkdir -p "$DOWNLOAD_DIR" "$HOME/OpenFOAM"
if ! has_supported_nvcxx; then
    [ "${CFD_STUDIO_ACCEPT_NVIDIA_EULA:-}" = YES ] || die \
        "NVIDIA HPC SDK EULA 동의가 필요합니다. 문서를 확인한 뒤 CFD_STUDIO_ACCEPT_NVIDIA_EULA=YES 로 다시 실행하세요: https://docs.nvidia.com/hpc-sdk/eula/index.html"
    SDK_TAR="$DOWNLOAD_DIR/${NVHPC_URL##*/}"
    [ -s "$SDK_TAR" ] || curl -L --fail --retry 3 -C - -o "$SDK_TAR" "$NVHPC_URL"
    tar -tzf "$SDK_TAR" >/dev/null || die "NVIDIA HPC SDK 압축 파일 검증 실패"
    SDK_DIR="$DOWNLOAD_DIR/nvhpc_2024_249_Linux_x86_64_cuda_12.6"
    [ -x "$SDK_DIR/install" ] || tar -xzf "$SDK_TAR" -C "$DOWNLOAD_DIR"
    NVHPC_SILENT=true NVHPC_INSTALL_DIR="$NVHPC_ROOT" NVHPC_INSTALL_TYPE=single \
        NVHPC_DEFAULT_CUDA=12.6 NVHPC_STDPAR_CUDACC="$CC_TAG" "$SDK_DIR/install"
fi
export NVCOMPILERS="$NVHPC_ROOT"
export PATH="$NVCOMPILERS/$NVARCH/24.9/compilers/bin:$NVCOMPILERS/$NVARCH/24.9/cuda/12.6/bin:$PATH"
export LD_LIBRARY_PATH="$NVCOMPILERS/$NVARCH/24.9/cuda/12.6/lib64:${LD_LIBRARY_PATH:-}"
export MANPATH="${MANPATH:-}:$NVCOMPILERS/$NVARCH/24.9/compilers/man"
has_supported_nvcxx || die "설치 후에도 지원 버전인 NVIDIA HPC SDK nvc++ 24.9를 찾지 못했습니다."
export CUDA_VISIBLE_DEVICES="$GPU_INDEX"
PREFLIGHT_DIR=$(mktemp -d /tmp/cfd_nvc_gpu.XXXXXX)
trap 'rm -rf "$PREFLIGHT_DIR"' EXIT
cat > "$PREFLIGHT_DIR/test.cpp" <<'CPP'
#include <algorithm>
#include <execution>
#include <vector>
int main() { std::vector<int> v(1024, 1); std::for_each(std::execution::par_unseq, v.begin(), v.end(), [](int& x){ x += 1; }); return v[0] == 2 ? 0 : 1; }
CPP
nvc++ -std=c++17 -stdpar=gpu -gpu="cc${CC_TAG},mem:managed" \
    "$PREFLIGHT_DIR/test.cpp" -o "$PREFLIGHT_DIR/test" >/dev/null 2>&1 || \
    die "NVIDIA HPC SDK 24.9가 이 GPU 아키텍처 cc${CC_TAG}를 지원하지 않습니다. 이 PC에서는 GPU Only를 활성화할 수 없습니다."
"$PREFLIGHT_DIR/test" || die "선택 GPU에서 nvc++ stdpar 사전 검증이 실패했습니다."

if [ ! -d "$OF_ROOT/.git" ]; then
    git clone --depth 1 --single-branch --branch feature-gpu \
        https://gitlab.com/openfoam/gpu/openfoam-ecse.git "$OF_ROOT"
fi
CURRENT_COMMIT=$(git -C "$OF_ROOT" rev-parse HEAD)
if [ "$CURRENT_COMMIT" != "$OF_COMMIT" ]; then
    [ -z "$(git -C "$OF_ROOT" status --porcelain)" ] || die "OpenCFD 소스에 로컬 변경이 있어 검증 커밋으로 전환할 수 없습니다: $OF_ROOT"
    git -C "$OF_ROOT" fetch --depth 1 origin "$OF_COMMIT"
    git -C "$OF_ROOT" checkout --detach "$OF_COMMIT"
fi
[ "$(git -C "$OF_ROOT" rev-parse HEAD)" = "$OF_COMMIT" ] || die "OpenCFD 검증 커밋 고정 실패"
if [ ! -f "$TP_ROOT/makeUMPIRE" ]; then
    TP_TAR="$DOWNLOAD_DIR/${THIRDPARTY_URL##*/}"
    [ -s "$TP_TAR" ] || curl -L --fail --retry 3 -C - -o "$TP_TAR" "$THIRDPARTY_URL"
    tar -tzf "$TP_TAR" >/dev/null || die "ThirdParty 압축 파일 검증 실패"
    tar -xzf "$TP_TAR" -C "$HOME/OpenFOAM"
fi

RULE="$OF_ROOT/wmake/rules/General/Nvidia-gpu/c++"
[ -f "$RULE" ] || die "Nvidia-gpu 컴파일 규칙이 없습니다."
python3 - "$RULE" "$CC_TAG" <<'PY'
from pathlib import Path
import re
import sys
p, cc = Path(sys.argv[1]), sys.argv[2]
s = p.read_text()
s, n = re.subn(r"-gpu=cc[0-9]+,mem:(?:unified[:,]managed|managed)", f"-gpu=cc{cc},mem:managed", s, count=1)
if n != 1 or f"-gpu=cc{cc},mem:managed" not in s:
    raise SystemExit(f"GPU cc{cc}용 Nvidia-gpu 플래그를 적용하지 못했습니다")
p.write_text(s)
PY

export WM_NCOMPPROCS="$JOBS"
export FOAM_MEMORY_POOL='managed; size=1024; incr=1024'
source "$OF_ROOT/etc/bashrc" WM_COMPILER=Nvidia-gpu
[ "$WM_THIRD_PARTY_DIR" = "$TP_ROOT" ] || die "ThirdParty 탐지 경로 불일치: $WM_THIRD_PARTY_DIR"
BUILD_TARGET="$OF_COMMIT:cc${CC_TAG}:nvhpc24.9"
BUILD_TARGET_FILE="$DOWNLOAD_DIR/openfoam_gpu_build_target"
PREVIOUS_TARGET=$(cat "$BUILD_TARGET_FILE" 2>/dev/null || true)
if [ "$PREVIOUS_TARGET" != "$BUILD_TARGET" ]; then
    echo "[준비] GPU 빌드 대상 변경: ${PREVIOUS_TARGET:-없음} -> $BUILD_TARGET"
    rm -rf "$OF_ROOT/platforms/$WM_OPTIONS" "${UMPIRE_ARCH_PATH:-/nonexistent}"
fi

if [ ! -d "$TP_ROOT/umpire-2025.03.0" ]; then
    UMP_TAR="$DOWNLOAD_DIR/${UMPIRE_URL##*/}"
    [ -s "$UMP_TAR" ] || curl -L --fail --retry 3 -C - -o "$UMP_TAR" "$UMPIRE_URL"
    tar -tzf "$UMP_TAR" >/dev/null || die "Umpire 압축 파일 검증 실패"
    tar -xzf "$UMP_TAR" -C "$TP_ROOT"
fi

rm -f "$HOME/.cfd_studio_gpu_only_ready.json"
(
    cd "$TP_ROOT"
    ./makeUMPIRE -DENABLE_CUDA=ON -DUMPIRE_ENABLE_CUDA=ON umpire-2025.03.0
)
(
    cd "$OF_ROOT"
    ./Allwmake -j "$JOBS" -s -q -l
)

"$SCRIPT_DIR/validate_gpu_only.sh" "$OF_ROOT/etc/bashrc" "$GPU_INDEX"
printf '%s\n' "$BUILD_TARGET" > "$BUILD_TARGET_FILE"
echo "[완료] CFD Studio를 다시 열면 GPU Only를 선택할 수 있습니다."
