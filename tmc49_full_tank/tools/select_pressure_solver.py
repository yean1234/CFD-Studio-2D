#!/usr/bin/env python3
"""다음 OpenFOAM 시작 직전에 p_rgh만 CPU GAMG 또는 PETSc CUDA PCGAMG로 선택한다.

실행 중인 솔버 파일은 건드리지 않는다. Allrun/CFD Studio 재개 스크립트가
새 solver 프로세스를 띄우기 직전에만 호출한다.
"""
from pathlib import Path
import ctypes
import ctypes.util
import os, re, shutil, subprocess, sys

ROOT = Path(__file__).resolve().parents[1]
FVS = ROOT / "system" / "fvSolution"
CTRL = ROOT / "system" / "controlDict"
# Previous AmgX experiments used the generic marker. The current GPU backend
# is PETSc PCGAMG CUDA, so an AmgX-only failure must not disable this path.
GPU_FAILED = ROOT / ".cfd_studio_gpu_pcgammg_failed"
GPU_FAILED_GLOBAL = Path.home() / ".cfd_studio_gpu_pcgammg_failed"

CPU = '''    // CFD_STUDIO_PRESSURE_BEGIN
    p_rgh       { solver GAMG; smoother DIC; tolerance 1e-7; relTol 0.01; }
    p_rghFinal  { $p_rgh; relTol 0; }
    // CFD_STUDIO_PRESSURE_END'''

# OpenFOAM external-solver 공식 구조 + PETSc CUDA PCGAMG:
# KSP와 행렬/벡터를 CUDA 형식으로 두어 host/device 왕복을 줄인다.
# AmgX PC는 현재 RTX 4090/WSL 조합에서 첫 AMG setup 중 illegal address가
# 재현되어 기본 GPU 경로에서 제외했다. PCGAMG는 PETSc가 공식 지원하는
# CUDA 행렬·벡터 기반 GPU AMG 경로다.
GPU = '''    // CFD_STUDIO_PRESSURE_BEGIN
    p_rgh
    {
        solver          petsc;
        preconditioner  petsc;
        petsc
        {
            options
            {
                ksp_type                 cg;
                ksp_cg_single_reduction  true;
                ksp_norm_type            unpreconditioned;
                pc_type                  gamg;
                pc_gamg_type             agg;
                pc_gamg_sym_graph       true;
                mat_type                 aijcusparse;
                vec_type                 cuda;
            }
            caching
            {
                matrix         { update always; }
                preconditioner { update always; }
            }
        }
        tolerance       1e-7;
        relTol          0.01;
    }
    p_rghFinal  { $p_rgh; relTol 0; }
    // CFD_STUDIO_PRESSURE_END'''

# OpenCFD feature-gpu 공식 위험 안내에 따라 명시적 직렬 선형 솔버를 피하고
# GPU 오프로딩 경로에서 지원하는 GAMG + twoStageGaussSeidel을 사용한다.
GPU_NATIVE = '''    // CFD_STUDIO_PRESSURE_BEGIN
    p_rgh
    {
        solver          GAMG;
        smoother        twoStageGaussSeidel;
        tolerance       1e-7;
        relTol          0.01;
    }
    p_rghFinal  { $p_rgh; relTol 0; }
    // CFD_STUDIO_PRESSURE_END'''


def gpu_library_ready():
    mode = os.environ.get("CFD_STUDIO_PRESSURE_SOLVER_MODE", "cpu").strip().lower()
    if mode not in ("cpu", "gpu", "gpu_only"):
        sys.exit("[압력 솔버 설정 오류] 계산 모드는 cpu, gpu, gpu_only 중 하나여야 합니다")
    if mode == "gpu_only":
        print("[압력 솔버] OpenCFD GPU 네이티브 GAMG + twoStageGaussSeidel")
        return None
    if mode == "cpu":
        print("[압력 솔버] 사용자 선택 CPU GAMG")
        return False
    if os.environ.get("CFD_STUDIO_GPU_PRESSURE") != "1":
        print("[압력 솔버] GPU 선택됐지만 GPU 환경이 없어 CPU GAMG 사용")
        return False
    # CUDA illegal-address/PETSc 76가 한 번이라도 발생한 케이스는 같은 GPU 경로를
    # 자동 재시도하지 않는다. 반복 재시도는 WSL의 NVIDIA 컨텍스트와 Windows 화면을
    # 함께 불안정하게 만들 수 있다. 사용자가 원인을 조치한 뒤 명시적으로 지운 경우만 재허용.
    if (GPU_FAILED.exists() or GPU_FAILED_GLOBAL.exists()) and os.environ.get("CFD_STUDIO_GPU_RETRY") != "1":
        print("[압력 솔버] GPU 선택됐지만 이전 CUDA/PETSc 실패 표식으로 CPU GAMG 안전 전환")
        return False
    petsc = os.environ.get("PETSC_ARCH_PATH", "")
    if not petsc or not Path(petsc, "lib", "libpetsc.so").exists():
        sys.exit("[GPU 설정 오류] PETSC_ARCH_PATH/lib/libpetsc.so 없음 — gpu_setup_amgx.sh 재실행")
    candidates = [os.environ.get("FOAM_MODULE_LIBBIN"), os.environ.get("FOAM_USER_LIBBIN")]
    if not any(p and Path(p, "libpetscFoam.so").exists() for p in candidates):
        sys.exit("[GPU 설정 오류] libpetscFoam.so 없음 — gpu_setup_amgx.sh 재실행")
    smi = shutil.which("nvidia-smi")
    if not smi:
        sys.exit("[GPU 설정 오류] nvidia-smi 없음 — NVIDIA WSL/리눅스 드라이버 확인")
    try:
        probe = subprocess.run([smi, "-L"], capture_output=True, timeout=8)
        if probe.returncode != 0 or not probe.stdout.strip():
            raise RuntimeError("GPU 목록 없음")
        cudart_name = ctypes.util.find_library("cudart") or "libcudart.so"
        cudart = ctypes.CDLL(cudart_name)
        count = ctypes.c_int(0)
        rc = int(cudart.cudaGetDeviceCount(ctypes.byref(count)))
        if rc != 0 or count.value < 1:
            raise RuntimeError(f"CUDA runtime rc={rc}, device={count.value}")
    except Exception as exc:
        sys.exit(f"[GPU 설정 오류] CUDA 실행 장치 확인 실패: {exc}")
    return True


def replace_pressure(text, block):
    marked = re.compile(r"(?ms)^\s*// CFD_STUDIO_PRESSURE_BEGIN.*?^\s*// CFD_STUDIO_PRESSURE_END")
    if marked.search(text):
        return marked.sub(block, text, count=1)
    legacy = re.compile(
        r"(?ms)^\s*p_rgh\s*(?:\{[^{}]*\}|\{.*?^\s*\})\s*"
        r"^\s*p_rghFinal\s*\{[^{}]*\}"
    )
    if not legacy.search(text):
        sys.exit("[압력 솔버 설정 오류] fvSolution의 p_rgh/p_rghFinal 블록을 찾지 못함")
    return legacy.sub(block, text, count=1)


def main():
    use_gpu = gpu_library_ready()
    text = FVS.read_text(encoding="utf-8")
    updated = replace_pressure(text, GPU_NATIVE if use_gpu is None else (GPU if use_gpu else CPU))
    FVS.write_text(updated, encoding="utf-8", newline="\n")

    control = CTRL.read_text(encoding="utf-8")
    control = re.sub(r"(?m)^\s*libs\s+\(\s*petscFoam\s*\);\s*\n?", "", control)
    if use_gpu is True:
        # Insert after the complete FoamFile header. Inserting after the
        # header's first line places a dictionary entry inside FoamFile and
        # makes OpenFOAM reject controlDict before the solver starts.
        header = re.search(r"(?ms)^\s*FoamFile\s*\{.*?^\s*\}\s*", control)
        if not header:
            sys.exit("[controlDict 설정 오류] FoamFile 헤더를 찾지 못함")
        pos = header.end()
        control = control[:pos] + "\nlibs            (petscFoam);\n" + control[pos:]
    CTRL.write_text(control, encoding="utf-8", newline="\n")
    if use_gpu is None:
        print("[압력 솔버] GPU Only · OpenCFD 네이티브 GAMG")
    else:
        print("[압력 솔버] " + ("GPU PETSc CG + PCGAMG CUDA (p_rgh만)" if use_gpu else "CPU GAMG"))


if __name__ == "__main__":
    main()
