#!/usr/bin/env bash
# CFD Studio GPU 압력 솔버 설치
# 공식 경로: NVIDIA WSL CUDA Toolkit + NVIDIA AmgX + PETSc release + OpenFOAM external-solver
# p_rgh만 GPU PETSc CG+AmgX, 나머지 OpenFOAM 방정식은 CPU 유지
set -euo pipefail

step(){ printf '\n══════ [%s] %s ══════\n' "$1" "$2"; }
fail(){ echo "✗ $*" >&2; exit 1; }

ROOT="$(cd "$(dirname "$0")" && pwd)"
PREFIX="$HOME/.local/cfd-studio-gpu"
PETSC_DIR="$PREFIX/petsc"
PETSC_ARCH="arch-cfd-cuda-opt"
AMGX_SRC="$PREFIX/AMGX"
AMGX_DIR="$PREFIX/amgx-install"
EXTERNAL_DIR="$PREFIX/external-solver"
JOBS="${GPU_BUILD_JOBS:-$(( $(nproc) * 2 / 5 ))}"
[ "$JOBS" -ge 2 ] || JOBS=2
# Codex/Windows에서 전달된 TEMP가 /mnt/c를 가리켜도 빌드는 Linux ext4 안에서 수행한다.
export TMPDIR=/tmp TMP=/tmp TEMP=/tmp
# WSL에서는 Windows NVIDIA 드라이버가 제공하는 CUDA 라이브러리를 Linux 드라이버보다 우선한다.
# 네이티브 Linux에는 이 경로가 없으므로 자동으로 생략된다.
WSL_GPU_LIB=""
[ -d /usr/lib/wsl/lib ] && WSL_GPU_LIB=/usr/lib/wsl/lib
export LD_LIBRARY_PATH="${WSL_GPU_LIB:+$WSL_GPU_LIB:}${LD_LIBRARY_PATH:-}"

step 0 "WSL GPU와 OpenFOAM 확인"
command -v nvidia-smi >/dev/null || fail "WSL에서 nvidia-smi를 찾지 못함"
nvidia-smi >/dev/null || fail "WSL에서 NVIDIA GPU를 사용할 수 없음"
FOAM_BASH="$(find /usr/lib/openfoam /opt -maxdepth 4 -type f -path '*/openfoam*/etc/bashrc' 2>/dev/null | sort | tail -1)"
[ -n "$FOAM_BASH" ] || fail "ESI OpenFOAM 환경을 찾지 못함"
# shellcheck disable=SC1090
set +e +u
source "$FOAM_BASH"
foam_rc=$?
set -e -u
[ "$foam_rc" -eq 0 ] || fail "OpenFOAM 환경 로딩 실패: $FOAM_BASH"
[ "${WM_MPLIB:-}" = "SYSTEMOPENMPI" ] || fail "OpenFOAM이 SYSTEMOPENMPI가 아님 — PETSc와 MPI ABI를 맞출 수 없음"

step 1 "공식 CUDA Toolkit과 빌드 도구 확인"
missing=()
for cmd in python3 cmake git make flex bison mpicc mpicxx gcc g++; do
    command -v "$cmd" >/dev/null || missing+=("$cmd")
done
dpkg -s zlib1g-dev libopenmpi-dev >/dev/null 2>&1 || missing+=("zlib1g-dev/libopenmpi-dev")
if [ "${#missing[@]}" -gt 0 ]; then
    echo "필수 도구 누락: ${missing[*]}"
    sudo -v || fail "sudo 인증 실패"
    sudo apt-get update
    sudo apt-get install -y build-essential cmake git flex bison zlib1g-dev \
        libopenmpi-dev openmpi-bin gcc g++ python3-dev wget ca-certificates
fi

if ! command -v nvcc >/dev/null; then
    echo "NVIDIA 권장 WSL-Ubuntu 저장소에서 현재 CUDA Toolkit 설치"
    sudo -v || fail "CUDA Toolkit 설치에 sudo 인증 필요"
    tmp_deb="$(mktemp /tmp/cuda-keyring.XXXXXX.deb)"
    wget -qO "$tmp_deb" https://developer.download.nvidia.com/compute/cuda/repos/wsl-ubuntu/x86_64/cuda-keyring_1.1-1_all.deb
    sudo dpkg -i "$tmp_deb"
    sudo apt-get update
    # WSL 안에는 Linux GPU 드라이버를 설치하지 않는다.
    sudo apt-get install -y cuda-toolkit
fi
nvcc --version

GPU_INDEX="${CFD_STUDIO_GPU_INDEX:-auto}"
if ! [[ "$GPU_INDEX" =~ ^[0-9]+$ ]]; then
    # 앱의 auto 선택과 동일하게 VRAM×최대 그래픽 클럭이 큰 GPU를 고른다. 동률이면 낮은 번호다.
    GPU_INDEX="$(nvidia-smi --query-gpu=index,memory.total,clocks.max.graphics \
        --format=csv,noheader,nounits 2>/dev/null | \
        awk -F, '{gsub(/ /,"",$1); gsub(/ /,"",$2); gsub(/ /,"",$3); s=$2*$3;
                    if (!seen || s>best || (s==best && $1<idx)) {seen=1; best=s; idx=$1}}
                 END {if (seen) print idx}')"
fi
[ -n "$GPU_INDEX" ] || fail "계산용 GPU 자동 선택 실패"
nvidia-smi -i "$GPU_INDEX" >/dev/null 2>&1 || fail "선택한 GPU $GPU_INDEX 를 사용할 수 없음"
GPU_ARCH="$(nvidia-smi -i "$GPU_INDEX" --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | head -1 | tr -d '.[:space:]')"
[ -n "$GPU_ARCH" ] || fail "GPU compute capability 자동 감지 실패"

# nvcc가 실제로 받아들이는 호스트 C++ 컴파일러를 시험해 선택한다.
# CUDA/Ubuntu 조합마다 지원 GCC 범위가 달라 특정 버전을 고정하지 않는다.
CUDA_PROBE_SRC="$(mktemp /tmp/cfd_cuda_probe.XXXXXX.cu)"
CUDA_PROBE_OBJ="${CUDA_PROBE_SRC%.cu}.o"
printf 'int main(){return 0;}\n' > "$CUDA_PROBE_SRC"
HOST_CXX=""
try_cuda_host() {
    local candidate="$1"
    [ -n "$candidate" ] && [ -x "$candidate" ] || return 1
    "$(command -v nvcc)" -ccbin "$candidate" -c "$CUDA_PROBE_SRC" -o "$CUDA_PROBE_OBJ" >/dev/null 2>&1 || return 1
    HOST_CXX="$candidate"
}
CXX_CANDIDATES=()
[ -n "${CUDAHOSTCXX:-}" ] && CXX_CANDIDATES+=("$CUDAHOSTCXX")
default_cxx="$(command -v g++ 2>/dev/null || true)"
[ -n "$default_cxx" ] && CXX_CANDIDATES+=("$default_cxx")
# 설치된 버전형 g++ 실행 파일을 최신순으로 찾는다. 특정 Ubuntu/GCC 버전을 전제하지 않는다.
while IFS= read -r candidate; do
    CXX_CANDIDATES+=("$candidate")
done < <(find /usr/bin /usr/local/bin -maxdepth 1 \( -type f -o -type l \) \
         -name 'g++-[0-9]*' -print 2>/dev/null | sort -Vru)
for candidate in "${CXX_CANDIDATES[@]}"; do
    try_cuda_host "$candidate" && break
done
if [ -z "$HOST_CXX" ]; then
    sudo -v || fail "CUDA 호환 C++ 컴파일러 설치에 sudo 인증 필요"
    sudo apt-get update
    # 이 배포판 저장소가 실제로 제공하는 g++ 버전만 동적으로 열거한다.
    while IFS= read -r cxx_package; do
        version="${cxx_package#g++-}"
        sudo apt-get install -y "gcc-$version" "$cxx_package" || continue
        try_cuda_host "$(command -v "$cxx_package" 2>/dev/null || true)" && break
        [ -n "$HOST_CXX" ] && break
    done < <(apt-cache pkgnames 2>/dev/null | grep -E '^g\+\+-[0-9]+$' | sort -Vru)
    if [ -z "$HOST_CXX" ]; then
        fail "이 배포판 저장소에서 CUDA 호환 C++ 컴파일러를 자동 구성하지 못함"
    fi
fi
rm -f "$CUDA_PROBE_SRC" "$CUDA_PROBE_OBJ"
[ -n "$HOST_CXX" ] || fail "설치된 CUDA와 호환되는 C++ 컴파일러를 찾지 못함"
host_cxx_name="$(basename "$HOST_CXX")"
case "$host_cxx_name" in
    g++*) HOST_CC="$(command -v "${host_cxx_name/g++/gcc}" 2>/dev/null || true)" ;;
    clang++*) HOST_CC="$(command -v "${host_cxx_name/clang++/clang}" 2>/dev/null || true)" ;;
    *) HOST_CC="$(command -v gcc 2>/dev/null || true)" ;;
esac
[ -n "$HOST_CC" ] || fail "선택한 C++ 컴파일러와 짝인 C 컴파일러를 찾지 못함"
export OMPI_CC="$HOST_CC" OMPI_CXX="$HOST_CXX"
export CUDAHOSTCXX="$HOST_CXX" CUDACXX="$(command -v nvcc)"
echo "CUDA=$CUDACXX · GPU=$GPU_INDEX · compute capability=$GPU_ARCH · host=$HOST_CXX · build jobs=$JOBS"

step 2 "공식 NVIDIA AmgX 라이브러리 빌드"
mkdir -p "$PREFIX"
if [ ! -d "$AMGX_SRC/.git" ]; then
    git clone --depth 1 --branch v2.4.0 --recursive https://github.com/NVIDIA/AMGX.git "$AMGX_SRC"
else
    git -C "$AMGX_SRC" fetch --depth 1 origin tag v2.4.0
    git -C "$AMGX_SRC" checkout -f v2.4.0
    git -C "$AMGX_SRC" submodule update --init --recursive
fi

# Ubuntu의 분리형 CUDA 패키지에서는 AmgX 예제가 폐기된 빈 include 변수를
# CMake에 넘긴다. CFD Studio는 PETSc가 링크할 라이브러리만 필요하므로 예제만 제외한다.
python3 - "$AMGX_SRC/CMakeLists.txt" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
needle = "add_subdirectory(examples)"
replacement = "# CFD Studio: library-only build; examples are not required\n# add_subdirectory(examples)"
if replacement not in text:
    if needle not in text:
        raise SystemExit("AmgX CMake 구조가 예상과 다릅니다")
    path.write_text(text.replace(needle, replacement, 1), encoding="utf-8")
PY

# 공식 소스의 재귀 GLOB은 테스트 구현까지 libamgx 본체에 포함한다. PETSc에는
# 런타임 라이브러리만 필요하므로 테스트 소스는 본체 대상에서 제외한다.
python3 - "$AMGX_SRC/src/CMakeLists.txt" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
needle = 'FILE(GLOB_RECURSE SRCS "*.cu")'
addition = '''FILE(GLOB_RECURSE SRCS "*.cu")
# CFD Studio: keep unit-test implementations out of the runtime library
list(FILTER SRCS EXCLUDE REGEX "/tests/")
list(FILTER SRCS EXCLUDE REGEX "/(testframework|test_utils|unit_test|utest)[.]cu$")'''
if "keep unit-test implementations out" not in text:
    if needle not in text:
        raise SystemExit("AmgX src CMake 구조가 예상과 다릅니다")
    path.write_text(text.replace(needle, addition, 1), encoding="utf-8")
PY

AMGX_BUILD="$AMGX_SRC/build-cfd"
MPI_INCLUDE_DIRS="$(mpicc --showme:incdirs)"
[ -n "$MPI_INCLUDE_DIRS" ] || fail "OpenMPI 헤더 경로 자동 감지 실패"
MPI_INCLUDE_LIST="${MPI_INCLUDE_DIRS// /;}"
MPI_CUDA_FLAGS=""
for include_dir in $MPI_INCLUDE_DIRS; do
    MPI_CUDA_FLAGS+=" -I$include_dir"
done
cmake -S "$AMGX_SRC" -B "$AMGX_BUILD" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_COMPILER=mpicc \
    -DCMAKE_CXX_COMPILER=mpicxx \
    -DCMAKE_CUDA_COMPILER="$(command -v nvcc)" \
    -DCMAKE_CUDA_HOST_COMPILER="$HOST_CXX" \
    -DCMAKE_CUDA_FLAGS="$MPI_CUDA_FLAGS" \
    -DCMAKE_CUDA_ARCHITECTURES="$GPU_ARCH" \
    -DMPI_INCLUDE_PATH="$MPI_INCLUDE_LIST" \
    -DCMAKE_INSTALL_PREFIX="$AMGX_DIR"
nice -n 10 cmake --build "$AMGX_BUILD" -j "$JOBS" --target amgx amgxsh
cmake --install "$AMGX_BUILD"
[ -f "$AMGX_DIR/lib/libamgxsh.so" ] || fail "AmgX 공유 라이브러리 설치 확인 실패"

step 3 "PETSc release + CUDA + AmgX 빌드"
if [ ! -d "$PETSC_DIR/.git" ]; then
    git clone --depth 1 --branch release https://gitlab.com/petsc/petsc.git "$PETSC_DIR"
else
    git -C "$PETSC_DIR" fetch --depth 1 origin release
    git -C "$PETSC_DIR" checkout -f release
    git -C "$PETSC_DIR" reset --hard origin/release
fi
cd "$PETSC_DIR"
export PETSC_DIR PETSC_ARCH
./configure \
    PETSC_ARCH="$PETSC_ARCH" \
    --with-debugging=0 \
    --with-shared-libraries=1 \
    --with-64-bit-indices=0 \
    --with-precision=double \
    --with-cc=mpicc --with-cxx=mpicxx --with-fc=0 \
    --with-cuda=1 --with-cuda-arch="$GPU_ARCH" \
    --with-amgx-dir="$AMGX_DIR" --download-f2cblaslapack=1 \
    COPTFLAGS="-O3 -march=native" \
    CXXOPTFLAGS="-O3 -march=native" \
    CUDAOPTFLAGS="-O3"
nice -n 10 make -j "$JOBS" PETSC_DIR="$PETSC_DIR" PETSC_ARCH="$PETSC_ARCH" all
PETSC_GPU_MPI_OPTION=""
if command -v ompi_info >/dev/null 2>&1 && \
   ! ompi_info --parsable --all 2>/dev/null | grep -q 'mpi_built_with_cuda_support:value:true'; then
    # 일반 Ubuntu/WSL OpenMPI는 GPU 버퍼 직접 전송을 지원하지 않으므로 PETSc가 안전하게 호스트를 경유한다.
    PETSC_GPU_MPI_OPTION="-use_gpu_aware_mpi 0"
fi
make PETSC_DIR="$PETSC_DIR" PETSC_ARCH="$PETSC_ARCH" \
    PETSC_TEST_OPTIONS="$PETSC_GPU_MPI_OPTION" check

step 4 "OpenFOAM 공식 external-solver(petsc4Foam) 빌드"
if [ ! -d "$EXTERNAL_DIR/.git" ]; then
    git clone --depth 1 https://develop.openfoam.com/modules/external-solver.git "$EXTERNAL_DIR"
else
    git -C "$EXTERNAL_DIR" pull --ff-only
fi
PETSC_RUNTIME_PATH="$PETSC_DIR/$PETSC_ARCH"
# OpenFOAM have_petsc는 in-source PETSc에서 루트+PETSC_ARCH를 받아야 공통/arch 헤더를 함께 찾는다.
export PETSC_ARCH_PATH="$PETSC_DIR"
export LD_LIBRARY_PATH="$PETSC_RUNTIME_PATH/lib:${LD_LIBRARY_PATH:-}"
cd "$EXTERNAL_DIR"
# OpenFOAM 환경 스크립트 일부는 정의되지 않은 변수를 전제로 하므로 Allwmake 동안만 nounset을 해제한다.
set +u
nice -n 10 ./Allwmake
set -u

LIB="${FOAM_MODULE_LIBBIN:-${FOAM_USER_LIBBIN:-}}/libpetscFoam.so"
[ -f "$PETSC_RUNTIME_PATH/lib/libpetsc.so" ] || fail "libpetsc.so 빌드 확인 실패"
[ -f "$LIB" ] || fail "libpetscFoam.so 빌드 확인 실패: $LIB"

step 5 "CFD Studio 자동 활성 환경 저장"
cat > "$HOME/.of_gpu_env" <<ENV
export PETSC_DIR="$PETSC_DIR"
export PETSC_ARCH="$PETSC_ARCH"
export PETSC_ARCH_PATH="$PETSC_RUNTIME_PATH"
export AMGX_DIR="$AMGX_DIR"
export FOAM_MODULE_LIBBIN="${FOAM_MODULE_LIBBIN:-${FOAM_USER_LIBBIN:-}}"
export LD_LIBRARY_PATH="${WSL_GPU_LIB:+$WSL_GPU_LIB:}$PETSC_RUNTIME_PATH/lib:$AMGX_DIR/lib:${FOAM_MODULE_LIBBIN:-${FOAM_USER_LIBBIN:-}}:\${LD_LIBRARY_PATH:-}"
export PETSC_OPTIONS="\${PETSC_OPTIONS:-} $PETSC_GPU_MPI_OPTION"
export CFD_STUDIO_GPU_PRESSURE=1
ENV

step 6 "설치 검증"
# shellcheck disable=SC1090
source "$HOME/.of_gpu_env"
ldd "$LIB" | grep -q "libpetsc" || fail "petscFoam이 PETSc와 연결되지 않음"
echo "✓ 설치 완료"
echo "  다음 CFD 시작/재개 시 p_rgh만 GPU PETSc CG+AmgX로 자동 전환됩니다."
echo "  현재 실행 중인 솔버의 fvSolution은 변경하지 않았습니다."
