#!/bin/bash
# Fresh installation only; existing cases are never replaced.
set -o pipefail
PARENT="$1"    # OpenFOAM_케이스 폴더의 WSL 경로
CASE_SETTING="${2:-~/tmc49_full_tank}"
fail(){ echo; echo "[중단] $1"; exit 1; }

case "$CASE_SETTING" in
  "~") CASE="$HOME" ;;
  "~/"*) CASE="$HOME/${CASE_SETTING#\~/}" ;;
  /*) CASE="$CASE_SETTING" ;;
  *) fail "wsl_case는 ~ 또는 절대 Linux 경로여야 합니다: $CASE_SETTING" ;;
esac

# An installer must never replace a running or historical project.
if [ -e "$CASE" ]; then
  fail "기존 케이스는 변경하지 않습니다: $CASE. studio_config.json의 wsl_case에 새 경로를 지정하세요."
fi

echo "[1/5] OpenFOAM 확인"
FOUND="$(ls /usr/lib/openfoam/openfoam2312/etc/bashrc /opt/openfoam2312/etc/bashrc 2>/dev/null | head -1)"
if [ -n "$FOUND" ]; then
  echo "  이미 설치됨: $FOUND"
else
  echo "  설치 중 (sudo 비밀번호를 물을 수 있음)"
  if ! command -v curl >/dev/null; then
    sudo apt-get update || fail "패키지 목록 갱신 실패"
    sudo apt-get install -y curl ca-certificates || fail "다운로드 도구 설치 실패"
  fi
  curl -fsSL https://dl.openfoam.com/add-debian-repo.sh | sudo bash || fail "OpenFOAM 저장소 등록 실패 (인터넷 연결 확인)"
  sudo apt-get update -y >/dev/null || fail "패키지 목록 갱신 실패"
  sudo apt-get install -y openfoam2312-default || fail "OpenFOAM 설치 실패"
  FOUND="$(ls /usr/lib/openfoam/openfoam2312/etc/bashrc /opt/openfoam2312/etc/bashrc 2>/dev/null | head -1)"
  [ -n "$FOUND" ] || fail "설치 후 OpenFOAM 환경 파일을 찾지 못함"
fi

SOLVER_OK=0
( . "$FOUND" >/dev/null 2>&1; command -v icoReactingMultiphaseInterFoam >/dev/null 2>&1 ) && SOLVER_OK=1
if [ "$SOLVER_OK" = "0" ]; then
  echo "  [경고] icoReactingMultiphaseInterFoam 을 찾지 못했습니다."
  echo "         openfoam.org(Foundation) 판에는 이 솔버가 없습니다 — ESI 판(openfoam.com)이 필요합니다."
  echo "         설치된 것: $FOUND"
  fail "필수 솔버를 확인하지 못했습니다"
fi

echo "[2/5] 필수 보조 도구 확인 (python3·numpy·util-linux·procps)"
need=""
command -v python3 >/dev/null || need="$need python3"
command -v taskset >/dev/null || need="$need util-linux"
command -v pgrep   >/dev/null || need="$need procps"
command -v python3 >/dev/null && python3 -c "import numpy" 2>/dev/null || need="$need python3-numpy"
if [ -n "$need" ]; then
  echo "  설치:$need"
  sudo -v || fail "sudo 인증 실패 — Linux 사용자 비밀번호를 확인한 뒤 다시 실행하세요"
  sudo apt-get install -y $need || fail "필수 보조 도구 설치 실패"
else
  echo "  OK"
fi
command -v python3 >/dev/null || fail "python3 확인 실패"
command -v taskset >/dev/null || fail "taskset(util-linux) 확인 실패"
command -v pgrep >/dev/null || fail "pgrep(procps) 확인 실패"
python3 -c "import numpy" 2>/dev/null || fail "python3-numpy 확인 실패"

echo "[3/5] 케이스 배치"
TAR="$PARENT/tmc49_full_tank_case.tar.gz"
if [ -d "$CASE" ]; then
  echo "  이미 있음: $CASE (건너뜀)"
  if [ -f "$TAR" ] && [ "$TAR" -nt "$CASE/config.json" ]; then
    echo "  [주의] 배포 압축본이 기존 케이스보다 최신입니다."
    echo "         최신 설정으로 갈아엎으려면: rm -rf $CASE 후 이 스크립트를 다시 실행"
  fi
elif [ -f "$TAR" ]; then
  mkdir -p "$CASE" || fail "케이스 폴더 생성 실패: $CASE"
  tar xzf "$TAR" -C "$CASE" --strip-components=1 || fail "케이스 압축 해제 실패"
  echo "  풀기 완료: $CASE"
elif [ -d "$PARENT/tmc49_full_tank" ]; then
  mkdir -p "$(dirname "$CASE")" || fail "상위 폴더 생성 실패"
  cp -r "$PARENT/tmc49_full_tank" "$CASE" || fail "케이스 복사 실패"
  rm -f "$CASE/conditions.csv.bak" "$CASE/run_overrides.json" 2>/dev/null
  echo "  압축본이 없어 Windows 폴더에서 복사: $CASE"
else
  fail "케이스를 찾을 수 없습니다.
        $TAR 또는 $PARENT/tmc49_full_tank 중 하나가 있어야 합니다"
fi

echo "[4/5] Windows 폴더의 최신 설정·도구 반영"
SRC="$PARENT/tmc49_full_tank"
if [ -d "$SRC" ]; then
  mkdir -p "$CASE/tools"
  cp "$SRC/config.json" "$CASE/" 2>/dev/null
  cp "$SRC"/tools/*.py "$CASE/tools/" 2>/dev/null
  cp "$SRC/Allrun" "$CASE/" 2>/dev/null && chmod +x "$CASE/Allrun"
  cp "$SRC/gpu_setup_amgx.sh" "$CASE/" 2>/dev/null && chmod +x "$CASE/gpu_setup_amgx.sh" || true
  cp "$SRC/fvSolution_gpu_snippet" "$CASE/" 2>/dev/null || true
  echo "  반영 완료 (config.json · tools · Allrun · GPU 선택 설치 파일)"
else
  echo "  건너뜀 (Windows 케이스 폴더 없음)"
fi

echo "[5/5] 케이스 검증"
cd "$CASE" || fail "케이스 폴더 접근 실패"
python3 - <<'PY' || exit 1
import json, sys
c = json.load(open('config.json', encoding='utf-8'))
n = len(c.get('conditions') or [])
need = ['tank','layers','board','heater','coil','mesh','run']
miss = [k for k in need if k not in c]
if miss:
    print("  [오류] config.json에 항목 없음:", ", ".join(miss)); sys.exit(1)
print(f"  config.json OK · 조건 {n}개 · 격자 dx={c['mesh'].get('dx_mm')}mm · 종료 {c['run'].get('end_time_s')}s")
PY
python3 tools/build_case.py --check || fail "케이스 검증 실패 (위 메시지 참고)"

echo
echo "완료! 이제 cfd_studio 폴더의 실행.bat 을 더블클릭하세요."
