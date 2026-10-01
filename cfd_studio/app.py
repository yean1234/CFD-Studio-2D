# -*- coding: utf-8 -*-
"""CFD Studio — 액침냉각 CFD 실행·모니터링·3D 시각화 (로컬 프로그램, 표준 라이브러리만 사용)

실행: 실행.bat 더블클릭 (또는 python app.py) → 브라우저 자동 열림 (http://127.0.0.1:8712)

기능
  1) 실행: [실행](새 계산·재개 자동 판단)/[리셋] → 명령 프롬프트 창이 열리며 WSL에서 CFD 자동 실행
  2) 진행 상황: 진행률·ETA·열전대·증기량·코일 온도·로그를 3초마다 갱신
  3) 3D 결과: 프로젝트 폴더의 config.json·C·기포·유동·온도 데이터 자동 탐지·재생
"""
import base64, json, math, os, re, shutil, socket, subprocess, sys, threading, time, uuid, webbrowser
sys.dont_write_bytecode = True                             # __pycache__ 생성 방지 (폴더 청결)
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

APP_VER   = "0.229"         # 화면 우상단·콘솔에 표시 — 업데이트 반영 확인용
PROCESS_STARTED = time.time()
HERE      = os.path.dirname(os.path.abspath(__file__))
# The bundled isolated Python also needs the application and repository modules.
for module_root in (os.path.join(HERE, "internal"), HERE, os.path.dirname(HERE)):
    if module_root not in sys.path:
        sys.path.insert(0, module_root)

# ── 환경 설정 (studio_config.json) — 어떤 PC에서도 값만 바꾸면 동작 ──
_SDEF = {"wsl_case": "~/cfd_studio_case",     # WSL 안 케이스 폴더
         "openfoam_bashrc": "auto",            # auto = /usr/lib/openfoam/openfoam*/etc/bashrc 자동 탐색
         "mpi_np": "auto",                     # auto = 논리 CPU의 cpu_pct% (총 사용률 목표)
         "gpu_index": "auto", "wsl_distro": "Ubuntu",                  # auto = 성능 점수가 가장 높은 NVIDIA GPU
         "pressure_solver_mode": "cpu",        # cpu=CPU, gpu=CPU+GPU(p_rgh), gpu_only=OpenCFD 전체 오프로딩
         "gpu_only_bashrc": "auto",            # OpenCFD GPU feature 브랜치 전용 bashrc. auto=표준 위치 탐색
         "cpu_pct": 60,                        # 기본 60%: Windows·시각화·드라이버 응답 여유 확보
         "auto_resume": False,                 # Automatic restart requires explicit opt-in.
         "archive_completed_projects": True,  # 완료 프로젝트 전체를 Raw 저장 드라이브로 이관
         "trash_retention_days": 30,           # 삭제 프로젝트 휴지통 보관 기간
         "raw_archive_dir": "",                # 빈 값=사용 안 함. PC마다 Studio에서 직접 선택
         "port": 8712}
_SCP = os.path.join(HERE, "studio_config.json")
try:
    SCFG = {**_SDEF, **json.load(open(_SCP, encoding="utf-8"))}
except Exception:
    SCFG = dict(_SDEF)
try:
    open(_SCP, "w", encoding="utf-8").write(json.dumps(SCFG, ensure_ascii=False, indent=2))
except Exception:
    pass
_CFG_PORT = int(SCFG["port"])
PORT      = int(os.environ.get("CFD_STUDIO_PORT", _CFG_PORT) or _CFG_PORT)
WSL_CASE  = SCFG["wsl_case"]
from cfd_studio.storage_layout import compatibility_folder
FRAME_DIR  = compatibility_folder(HERE, "frames", "frames")
LEGACY_PROJECT_DIR = os.path.join(FRAME_DIR, "Project")
PROJECT_DIR = compatibility_folder(HERE, "Project", "legacy_results")
TRASH_DIR = compatibility_folder(HERE, "Trash", "Trash")
LEGACY_TRASH_DIR = os.path.join(HERE, "휴지통")
os.makedirs(FRAME_DIR, exist_ok=True)
os.makedirs(PROJECT_DIR, exist_ok=True)
if os.path.isdir(LEGACY_TRASH_DIR) and not os.path.exists(TRASH_DIR):
    try: shutil.move(LEGACY_TRASH_DIR, TRASH_DIR)
    except Exception: pass
os.makedirs(TRASH_DIR, exist_ok=True)
RUNTIME_DIR = os.path.join(HERE, "_runtime")               # 임시·자동 생성물 전용 (앱이 관리)
os.makedirs(RUNTIME_DIR, exist_ok=True)
SILO_ROOT = os.path.abspath(os.path.join(HERE, "..", "silo_reproduction"))
SILO_CONFIG = os.path.join(SILO_ROOT, "config.json")
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from warehouse_workspace import Workspace, get_route as warehouse_get, post_route as warehouse_post
from config_presets import finite_number, validate_numerics, save_new_preset
WAREHOUSE_WORKSPACE = Workspace(os.path.join(HERE, "_runtime", "warehouse"), SCFG)
from study_platform import http as study_http
from execution_workspace import ExecutionWorkspace, get_route as execution_get, post_route as execution_post
EXECUTION_WORKSPACE = ExecutionWorkspace(os.path.dirname(HERE), lambda: _project_search_roots(), settings=SCFG,
    busy=lambda: bool(get_status().get("running")) or time.time()-STATE.get("group_launch_t", 0)<60 or any(j.get("status") in ("queued", "running") for j in WAREHOUSE_WORKSPACE.jobs.values()),
    live=lambda: {**(_STATUS_CACHE.get("data") or {}), "rid": _active_rid()})
EXECUTION_WORKSPACE.storage_busy = lambda: _extract_any_busy() or bool(RAW_ARCHIVE_STATE.get('busy')) or bool(PROJECT_ARCHIVE_STATE.get('busy'))
WAREHOUSE_WORKSPACE.resolve_result = lambda rid: EXECUTION_WORKSPACE.result_path(rid, 'warehouse')
WAREHOUSE_WORKSPACE.result_paths = lambda: [Path(e['path']) for e in EXECUTION_WORKSPACE.managed_result_entries() if e['kind'] == 'warehouse']
UISTF = os.path.join(RUNTIME_DIR, "uistate.json")          # 마지막 화면 상태 (재실행 시 복원)
STUDIO_PIDF = os.path.join(RUNTIME_DIR, "studio.pid")      # 포트 없는 잔존 인스턴스까지 식별

def _studio_pid_record():
    try:
        obj = json.load(open(STUDIO_PIDF, encoding="ascii"))
        return int(obj.get("pid") or 0), float(obj.get("started") or 0)
    except Exception:
        return 0, 0.0

def _wsl_case_token():
    """WSL 경로에서 `~`는 셸에서만 확장되어야 하므로, 기본 인용 시 예외 처리."""
    p = str(WSL_CASE or "").replace("\\", "/").strip()
    if p.startswith("~"):
        return p
    return _shq(p)

def _janitor():
    """기동 시 1회 — 과거 부산물과 보관기간이 지난 프로젝트 휴지통 정리."""
    for junk in ("_console_run.sh",):
        p = os.path.join(HERE, junk)
        if os.path.isfile(p):
            try: shutil.move(p, os.path.join(RUNTIME_DIR, junk))
            except Exception:
                try: os.remove(p)
                except Exception: pass
    pc = os.path.join(HERE, "__pycache__")
    if os.path.isdir(pc):
        shutil.rmtree(pc, ignore_errors=True)
    _purge_project_trash()

def _trash_retention_days():
    try: return max(1, min(3650, int(SCFG.get("trash_retention_days", 30))))
    except Exception: return 30

def _trash_marker(path):
    return os.path.join(path, ".trash_info.json")

def _project_trash_dir(pd):
    """프로젝트와 같은 저장 장치의 Trash를 사용해 대용량 교차 복사를 막는다."""
    parent = os.path.dirname(os.path.abspath(pd))
    archive = _archive_project_root()
    if archive and os.path.normcase(parent) == os.path.normcase(os.path.abspath(archive)):
        return os.path.join(os.path.dirname(archive), "Trash")
    return TRASH_DIR

def _move_project_to_trash(pd, rid):
    """프로젝트 폴더를 같은 디스크의 휴지통으로 이동한다.

    즉시 삭제하지 않으며, 고유한 삭제시각 접미사를 붙여 같은 이름의 프로젝트도
    서로 덮어쓰지 않는다. 마커 기록에 실패해도 폴더는 보존되고 자동 삭제 대상에서
    제외되므로 데이터 안전 쪽으로 실패한다.
    """
    src = os.path.abspath(pd)
    allowed = {os.path.normcase(os.path.abspath(root)) for root in _project_search_roots()}
    if os.path.normcase(os.path.dirname(src)) not in allowed or not os.path.isdir(src):
        raise ValueError("Project 바로 아래 폴더만 Trash로 이동할 수 있습니다")
    trash_dir = _project_trash_dir(src)
    os.makedirs(trash_dir, exist_ok=True)
    deleted = time.time()
    stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(deleted))
    base = _project_folder_name(os.path.basename(src))
    target = os.path.join(trash_dir, f"{base}__{stamp}_{uuid.uuid4().hex[:6]}")
    shutil.move(src, target)
    info = {"original_folder": os.path.basename(src), "run_id": str(rid or ""),
            "deleted_at": deleted, "purge_after": deleted + _trash_retention_days() * 86400,
            "retention_days": _trash_retention_days(), "app_ver": APP_VER}
    try: meta_write(_trash_marker(target), info)
    except Exception: pass                         # 마커 없음 = 자동 삭제 금지
    return target, info

def _move_project_progress_to_trash(pd, rid):
    """설정 파일은 남기고 계산·변환 진행 데이터만 Trash로 이동한다."""
    root = os.path.realpath(PROJECT_DIR)
    src = os.path.realpath(pd)
    if os.path.dirname(src) != root or not os.path.isdir(src):
        raise ValueError("Project 바로 아래 폴더만 리셋할 수 있습니다")
    os.makedirs(TRASH_DIR, exist_ok=True)
    deleted = time.time()
    stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(deleted))
    base = _project_folder_name(os.path.basename(src))
    target = os.path.join(TRASH_DIR, f"{base}__reset_{stamp}_{uuid.uuid4().hex[:6]}")
    os.makedirs(target, exist_ok=False)
    keep = {"meta.json", "case_config.json", "config.json"}
    moved = []
    for name in os.listdir(src):
        if name in keep:
            continue
        shutil.move(os.path.join(src, name), os.path.join(target, name))
        moved.append(name)
    info = {"kind": "reset_progress", "original_folder": os.path.basename(src),
            "run_id": str(rid or ""), "deleted_at": deleted,
            "purge_after": deleted + _trash_retention_days() * 86400,
            "retention_days": _trash_retention_days(), "items": moved, "app_ver": APP_VER}
    try: meta_write(_trash_marker(target), info)
    except Exception: pass                         # 마커 없음 = 자동 삭제 금지
    mp = os.path.join(src, "meta.json")
    meta = _read_json_file(mp) or {}
    meta.pop("provenance", None)
    meta["reset_at"] = deleted
    meta["tmax"] = 0
    meta_write(mp, meta)
    return target, info

def _purge_project_trash(now=None):
    """유효한 휴지통 마커가 있고 보관기간이 지난 폴더만 영구 삭제한다."""
    now = time.time() if now is None else float(now)
    removed = []
    try: names = list(os.listdir(TRASH_DIR))
    except Exception: return removed
    root = os.path.realpath(TRASH_DIR)
    for name in names:
        p = os.path.join(TRASH_DIR, name)
        if os.path.islink(p) or not os.path.isdir(p) or os.path.dirname(os.path.realpath(p)) != root:
            continue
        info = _read_json_file(_trash_marker(p)) or {}
        try: purge_after = float(info.get("purge_after"))
        except Exception: continue                 # 출처 불명 폴더는 절대 자동 삭제하지 않음
        if purge_after <= 0 or now < purge_after:
            continue
        try:
            shutil.rmtree(p)
            removed.append(name)
        except Exception as e:
            print("  [Trash] 자동 삭제 실패:", name, str(e)[:80])
    if removed:
        print(f"  [Trash] {_trash_retention_days()}일 지난 항목 {len(removed)}개 영구 삭제")
    return removed

def trash_loop():
    """앱을 계속 켜 둔 경우에도 6시간마다 보관기간 만료 여부를 확인."""
    while True:
        time.sleep(6 * 3600)
        try: _purge_project_trash()
        except Exception: pass

def _project_key(value):
    """Project 바로 아래의 단일 폴더명만 허용한다.

    CFD Studio 실행 ID(숫자) 외에 사용자가 넣은 외부 CFD 폴더명도
    프로젝트 ID로 쓰되, 경로 탈출·제어문자는 차단한다.
    """
    key = str(value or "").strip()
    if (not key or key in (".", "..") or len(key) > 120 or
            "/" in key or "\\" in key or any(ord(c) < 32 for c in key)):
        return ""
    return key

def _project_folder_name(value):
    """화면 이름을 Windows에서도 안전한 사람 가독 폴더명으로 변환."""
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", str(value or "")).strip().rstrip(". ")[:80]
    if not name:
        name = "새 프로젝트"
    if name.upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        name = "_" + name
    return name

def _unique_project_path(name, current=None, preferred_root=None):
    base = _project_folder_name(name)
    used = set()
    for root in _project_search_roots():
        try:
            for d in os.listdir(root):
                path = os.path.join(root, d)
                if os.path.isdir(path) and os.path.abspath(path) != os.path.abspath(current or ""):
                    used.add(d.casefold())
        except OSError:
            pass
    cand, i = base, 2
    while cand.casefold() in used:
        cand = f"{base} ({i})"; i += 1
    return os.path.join(preferred_root or PROJECT_DIR, cand)

def _archive_project_root():
    """완료 프로젝트 패키지가 놓이는 선택 드라이브의 Project 폴더."""
    try:
        root = _raw_archive_dir()
    except NameError:
        root = ""
    return os.path.join(root, "Project") if root else ""

def _project_search_roots():
    """로컬 작업 프로젝트와 외부 완료 프로젝트를 한 목록으로 취급한다."""
    roots = [PROJECT_DIR]
    archive = _archive_project_root()
    if archive and os.path.normcase(os.path.abspath(archive)) != os.path.normcase(os.path.abspath(PROJECT_DIR)):
        roots.append(archive)
    return roots

def _project_entries():
    """동일 폴더명은 작업본(C)을 우선하고 D 보관본은 중복 표시하지 않는다."""
    found = []
    seen = set()
    for root in _project_search_roots():
        try:
            names = os.listdir(root)
        except OSError:
            continue
        for name in names:
            path = os.path.join(root, name)
            marker = name.casefold()
            if marker in seen or not _project_key(name) or not os.path.isdir(path) or name.startswith("_"):
                continue
            seen.add(marker)
            found.append((name, path))
    for pd in [*EXECUTION_WORKSPACE.external_paths(), *[Path(e['path']) for e in EXECUTION_WORKSPACE.managed_result_entries() if e['kind'] == 'legacy']]:
        name, path = pd.name, str(pd)
        if os.path.isdir(path) and os.path.normcase(os.path.abspath(path)) not in {os.path.normcase(os.path.abspath(p)) for _, p in found}:
            found.append((name, path))
    return found

def proj_dir(rid):
    managed = EXECUTION_WORKSPACE.result_path(str(rid), "legacy")
    if managed:
        return str(managed)
    key = _project_key(rid)
    if not key:
        return FRAME_DIR
    for root in _project_search_roots():
        exact = os.path.join(root, key)
        if os.path.isdir(exact):
            return exact
    try:
        for folder, pd in _project_entries():
            meta = _read_json_file(os.path.join(pd, "meta.json")) or {}
            if str(meta.get("run_id") or meta.get("project_id") or "") == key:
                return pd
    except Exception:
        pass
    return exact

def _active_rid():
    rid = cur_rid()
    if rid and not os.path.isdir(proj_dir(rid)):
        try:
            os.remove(os.path.join(FRAME_DIR, "_runid.txt"))
        except Exception:
            pass
        return ""
    return rid

def _normalize_project_dir(pdir, rid):
    """빈/깨진 프로젝트 폴더가 남아 있어도 즉시 보존 규격(meta.json)으로 보정"""
    os.makedirs(pdir, exist_ok=True)
    mp = os.path.join(pdir, "meta.json")
    meta = _read_json_file(mp) or {}
    changed = not os.path.exists(mp)
    try:
        cfg = (_read_json_file(os.path.join(pdir, "case_config.json")) or
               _read_json_file(os.path.join(pdir, "config.json")) or get_config())
        end = float((cfg or {}).get("run", {}).get("end_time_s") or 30)
    except Exception:
        end = 30.0
    if not meta.get("name"): meta["name"] = f"프로젝트 {rid}" if str(rid).isdigit() else str(rid); changed = True
    if "settings" not in meta: meta["settings"] = {}; changed = True
    if "end" not in meta: meta["end"] = end; changed = True
    if str(rid).isdigit() and not meta.get("run_id"): meta["run_id"] = str(rid); changed = True
    if not str(rid).isdigit() and not meta.get("run_id") and not meta.get("project_id"):
        meta["project_id"] = "ext-" + uuid.uuid4().hex; meta["external"] = True; changed = True
    if "external" not in meta: meta["external"] = not bool(meta.get("run_id")); changed = True
    if "created" not in meta: meta["created"] = os.path.getmtime(pdir); changed = True
    meta["end_locked"] = True; meta["heal2"] = True
    if changed: meta_write(mp, meta)

def _create_run_project(rid, name, meta):
    """실행 ID는 meta에 고정하고, 실제 폴더는 프로젝트 이름으로 생성."""
    old = proj_dir(rid)
    if os.path.isdir(old):
        return old
    meta = dict(meta or {})
    attempt_path = meta.pop("execution_attempt_path", None)
    if attempt_path:
        pd = os.path.join(attempt_path, "Results", str(rid))
    elif meta.get("execution_project_id"):
        pd = str(EXECUTION_WORKSPACE.project_folder(meta["execution_project_id"])/"Results"/str(rid))
    else:
        pd = _unique_project_path(name)
    os.makedirs(pd, exist_ok=False)
    meta.update({"name": name, "run_id": str(rid), "external": False})
    raw_root = pd if meta.get("execution_project_id") else _raw_archive_dir()
    ok_raw, raw_root, _ = _validate_raw_archive_dir(raw_root, require_writable=False)
    if ok_raw and raw_root:
        # 프로젝트 생성 순간 보관 루트를 고정해 설정 변경 시 실행 데이터가 섞이지 않게 한다.
        meta.setdefault("raw_archive_root", raw_root)
        meta.setdefault("raw_archive_run", _desired_project_raw_path(pd, raw_root))
    meta_write(os.path.join(pd, "meta.json"), meta)
    return pd

def cur_rid():
    try: return open(os.path.join(FRAME_DIR, "_runid.txt")).read().strip()
    except Exception: return ""

PENDF = os.path.join(FRAME_DIR, "_pending.json")
CFGDIR = os.path.join(HERE, "configs")           # [config.json 생성]으로 저장한 config 모음

def cfg_safe(name):
    """파일명으로 쓸 수 있게 정리 — 경로 탈출·구분자 차단"""
    n = re.sub(r"[\\/:*?\"<>|\n\r\t]", "_", str(name or "")).strip().strip(".")[:40]
    return n or "설정"

def _normalize_silo_config(value):
    """저장고 설정을 기준 파일에 덮어쓰지 않고 검증·정규화한다."""
    base = _read_json_file(SILO_CONFIG) or {}
    if not isinstance(value, dict) or value.get("_해석유형") != "grain_silo":
        return False, None, "식량 저장고 설정 형식을 확인해 주세요"
    if not base:
        return False, None, "식량 저장고 기본 설정을 불러오지 못했습니다"
    for section in ("published", "openfoam_mapping", "solver_controls", "mesh", "run", "silo"):
        if section in value and not isinstance(value[section], dict):
            return False, None, "저장고 설정 객체를 확인해 주세요: " + section
    out = json.loads(json.dumps(base))
    incoming_pub = value.get("published") or {}
    pub = out.setdefault("published", {})
    limits = {
        "outer_diameter_m": (0.05, 100.0), "total_height_m": (0.05, 100.0),
        "storage_diameter_m": (0.05, 100.0), "storage_height_m": (0.05, 100.0),
        "grain_height_m": (0.01, 100.0), "bottom_central_duct_diameter_m": (0.001, 100.0),
        "inlet_speed_m_s": (0.001, 200.0), "rho_kg_m3": (0.01, 100.0),
        "mu_Pa_s": (1e-9, 1.0), "grain_particle_diameter_m": (1e-6, 1.0),
        "grain_porosity": (0.01, 0.99), "darcy_d_1_m2": (0.0, 1e15),
        "forchheimer_f_1_m": (0.0, 1e12),
    }
    try:
        for key, (lo, hi) in limits.items():
            number = finite_number(incoming_pub.get(key, pub.get(key)), key)
            if not math.isfinite(number) or not lo <= number <= hi:
                raise ValueError(key)
            pub[key] = number
    except (TypeError, ValueError) as exc:
        return False, None, "저장고 수치 설정을 확인해 주세요: " + str(exc)
    if pub["storage_diameter_m"] > pub["outer_diameter_m"]:
        return False, None, "저장부 직경은 전체 외경보다 클 수 없습니다"
    if pub["storage_height_m"] > pub["total_height_m"] or pub["grain_height_m"] > pub["storage_height_m"]:
        return False, None, "곡물 높이 ≤ 저장부 높이 ≤ 전체 높이 순서로 입력해 주세요"
    if pub["bottom_central_duct_diameter_m"] >= pub["storage_diameter_m"]:
        return False, None, "하부 유입구 직경은 저장부 직경보다 작아야 합니다"
    pub["nu_m2_s"] = pub["mu_Pa_s"] / pub["rho_kg_m3"]

    options = out.get("solver_options") or {}
    incoming_map = value.get("openfoam_mapping") or {}
    solver = str(incoming_map.get("solver") or "simpleFoam")
    if solver not in options:
        return False, None, "선택할 수 없는 저장고 솔버입니다"
    turbulence_options = list(out.get("turbulence_options") or [])
    turbulence = str(incoming_map.get("turbulence") or "kEpsilon")
    if turbulence not in turbulence_options:
        return False, None, "선택할 수 없는 난류 모델입니다"
    selected = options[solver]
    out["openfoam_mapping"] = {
        "version": "v2312", "solver": solver,
        "pressure_velocity_coupling": selected["pressure_velocity_coupling"],
        "turbulence": turbulence,
        "porosity_source": "explicitPorositySource/DarcyForchheimer"
    }

    controls_in = value.get("solver_controls") or {}
    controls = out.setdefault("solver_controls", {})
    try:
        intensity = finite_number(controls_in.get("turbulence_intensity", controls.get("turbulence_intensity", 0.05)), "난류 강도")
        length = finite_number(controls_in.get("turbulence_length_scale_m", controls.get("turbulence_length_scale_m", 0.05)), "난류 길이")
        tolerance = finite_number(controls_in.get("convergence_tolerance", controls.get("convergence_tolerance", 1e-6)), "수렴 기준")
    except (TypeError, ValueError):
        return False, None, "난류·수렴 설정을 숫자로 입력해 주세요"
    if not (0 < intensity <= 1 and 1e-5 <= length <= pub["total_height_m"] and 1e-12 <= tolerance <= 0.1):
        return False, None, "난류 강도·길이와 수렴 기준 범위를 확인해 주세요"
    controls.update(turbulence_intensity=intensity, turbulence_length_scale_m=length,
                    convergence_tolerance=tolerance)

    mesh_in = value.get("mesh") or {}
    try: target_cells = finite_number(mesh_in.get("target_cells", (out.get("mesh") or {}).get("target_cells", 1056000)), "목표 격자 수", integer=True)
    except (TypeError, ValueError): return False, None, "목표 격자 수는 정수로 입력해 주세요"
    if not 1000 <= target_cells <= 100000000:
        return False, None, "목표 격자 수는 1,000~100,000,000 범위여야 합니다"
    out.setdefault("mesh", {})["target_cells"] = target_cells

    run_in = value.get("run") or {}
    stop_mode = str(run_in.get("stop_mode", "fixed")).strip().lower()
    if stop_mode not in ("fixed", "converged"):
        return False, None, "종료 기준은 고정 길이 또는 수렴 도달을 선택해 주세요"
    if solver != "simpleFoam":
        stop_mode = "fixed"
    try:
        if solver == "simpleFoam":
            end = finite_number(run_in.get("max_iterations", run_in.get("end_time_s", 1000)), "목표 반복 횟수")
            write = finite_number(run_in.get("write_interval_iterations", run_in.get("write_interval_s", 100)), "저장 반복 간격")
            playback_duration = finite_number(run_in.get("playback_duration_s", 60), "총 재생 시간")
        else:
            end = finite_number(run_in.get("end_time_s", 10), "목표 해석 시간")
            write = finite_number(run_in.get("write_interval_s", 0.1), "저장 시간 간격")
            playback_duration = end
        time_step = finite_number(run_in.get("time_step_s", run_in.get("max_dt_s", 0.01)), "계산 시간간격")
    except (TypeError, ValueError): return False, None, "계산 목표·계산 단위·저장 간격을 확인해 주세요"
    if not (end > 0 and 0 < write <= end and time_step > 0):
        return False, None, "계산 종료값보다 저장 간격이 크지 않아야 합니다"
    if solver == "simpleFoam" and not (end.is_integer() and write.is_integer()):
        return False, None, "simpleFoam의 목표·저장 간격은 정수 반복 횟수로 입력해 주세요"
    if solver == "simpleFoam" and not 0.1 <= playback_duration <= 86400:
        return False, None, "총 재생 시간은 0.1~86,400초 범위로 입력해 주세요"
    outputs = [x for x in (run_in.get("output_fields") or []) if x in ("flow", "pressure", "turbulence")]
    if not outputs: outputs = ["flow"]
    if solver == "simpleFoam":
        out["run"] = {"time_basis": "iterations", "max_iterations": int(end),
                      "write_interval_iterations": int(write),
                      # 기존 프로젝트·진행률 코드와의 하위 호환 키
                      "end_time_s": int(end), "write_interval_s": int(write),
                      "viz_interval_s": int(write),
                      # 정상상태 simpleFoam의 deltaT=1은 초가 아니라 반복 번호다.
                      "iteration_step": 1,
                      "playback_duration_s": playback_duration,
                      "stop_mode": stop_mode,
                      "output_fields": outputs}
    else:
        out["run"] = {"time_basis": "physical_time", "end_time_s": end,
                      "time_step_s": time_step, "write_interval_s": write,
                      "viz_interval_s": write, "max_dt_s": time_step,
                      "stop_mode": "fixed",
                      "output_fields": outputs}

    silo = value.get("silo") or {}
    design = silo.get("design", {})
    if not isinstance(design, dict):
        return False, None, "덕트 설계 설정을 확인해 주세요"
    domains = out.get("design_domains") or {}
    values = {}
    for short, key, default in (("A", "A_mm", 20), ("B", "B_layers", 12),
                                ("C", "C_mm", 5), ("D", "D_count", 6)):
        try: number = finite_number(design.get(short, default), short, integer=True)
        except (TypeError, ValueError): return False, None, "A/B/C/D 설정을 확인해 주세요"
        if number not in set(domains.get(key) or []):
            return False, None, f"{short} 설정이 허용 범위에 없습니다"
        values[short] = number
    kind = str(silo.get("kind") or "custom").strip().lower()
    if kind not in ("custom", "original", "optimized"):
        return False, None, "저장고 설계 구분을 확인해 주세요"
    normalized_silo = {"kind": kind, "design": values}
    geometry_model = str(silo.get("geometry_model") or "").strip()
    if geometry_model:
        if geometry_model != "equivalent_boundary_ports_v1":
            return False, None, "선택할 수 없는 저장고 형상 모델입니다"
        assumptions_in = silo.get("geometry_assumptions", {})
        if not isinstance(assumptions_in, dict):
            return False, None, "저장고 등가 형상 설정을 확인해 주세요"
        try:
            ports_per_layer = finite_number(assumptions_in.get("ports_per_layer", 4), "층별 개수", integer=True)
            z_min = finite_number(assumptions_in.get("layer_z_min_m", 0.25 if kind == "original" else 0.05), "최소 높이")
            z_max = finite_number(assumptions_in.get("layer_z_max_m", 0.75 if kind == "original" else 0.95), "최대 높이")
            ring_radius = finite_number(assumptions_in.get("bottom_ring_radius_m", 0.34), "하부 반경")
        except (TypeError, ValueError):
            return False, None, "저장고 등가 형상 값을 확인해 주세요"
        if not (1 <= ports_per_layer <= 64 and 0 < z_min <= z_max < pub["grain_height_m"]
                and 0 < ring_radius < pub["storage_diameter_m"] / 2.0):
            return False, None, "저장고 등가 형상 범위를 확인해 주세요"
        normalized_silo["geometry_model"] = geometry_model
        normalized_silo["geometry_assumptions"] = {
            "ports_per_layer": ports_per_layer,
            "layer_z_min_m": z_min,
            "layer_z_max_m": z_max,
            "bottom_outlets_enabled": bool(assumptions_in.get("bottom_outlets_enabled", kind != "original")),
            "bottom_ring_radius_m": ring_radius,
            "source": str(assumptions_in.get("source") or "")[:500],
        }
    out["silo"] = normalized_silo
    out["_해석유형"] = "grain_silo"
    out["schema_version"] = 3
    return True, out, ""

def _silo_info():
    cfg = _read_json_file(SILO_CONFIG) or {}
    pub = dict(cfg.get("published") or {})
    return {"ok": bool(cfg), "config": {"study": cfg.get("study") or {}, "published": pub,
            "published_numerics": cfg.get("published_numerics") or {},
            "openfoam_mapping": cfg.get("openfoam_mapping") or {},
            "mesh": cfg.get("mesh") or {}, "design_domains": cfg.get("design_domains") or {},
            "solver_options": cfg.get("solver_options") or {},
            "turbulence_options": cfg.get("turbulence_options") or [],
            "solver_controls": cfg.get("solver_controls") or {}, "run": cfg.get("run") or {}}}

def saved_configs():
    try:
        return sorted(f[:-5] for f in os.listdir(CFGDIR) if f.endswith(".json"))
    except Exception:
        return []

def saved_config_types():
    return {name: ("grain_silo" if (saved_config(name) or {}).get("_해석유형") == "grain_silo" else "immersion")
            for name in saved_configs()}

def _seed_saved_configs():
    """처음 설치한 configs 폴더가 비어 있으면 현재의 실제 설정을 기본 목록으로 보존한다.

    이후에는 사용자가 만든/지운 파일을 존중해 자동으로 덮어쓰거나 되살리지 않는다.
    """
    try:
        os.makedirs(CFGDIR, exist_ok=True)
        initialized = os.path.join(CFGDIR, ".initialized")
        # 최초 1회만 기본 목록을 만든다. 이후 사용자가 설정을 모두 지워도
        # 다음 실행에서 자동으로 되살아나지 않아야 한다.
        if os.path.exists(initialized):
            return
        if any(n.lower().endswith(".json") for n in os.listdir(CFGDIR)):
            open(initialized, "a", encoding="utf-8").close()
            return
        seeds = [("기본", source_config())]
        for p in list_projects():
            if p.get("pending"):
                continue
            cfg = project_config(p.get("rid"))
            if cfg:
                seeds.append((p.get("name") or p.get("rid") or "프로젝트", cfg))
        used = set()
        for label, cfg in seeds:
            if not cfg:
                continue
            base = cfg_safe(label)
            name = base
            suffix = 2
            while name.casefold() in used or os.path.exists(os.path.join(CFGDIR, name + ".json")):
                name = f"{base}_{suffix}"
                suffix += 1
            used.add(name.casefold())
            meta_write(os.path.join(CFGDIR, name + ".json"), cfg)
        open(initialized, "a", encoding="utf-8").close()
    except Exception as e:
        print(f"  [점검] 기본 config 목록 생성 실패: {e}")

def _read_json_file(path):
    try:
        with open(path, encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None

def source_config():
    """Windows 케이스의 기준 config.json. WSL 실행 상태와 분리해 재로드한다."""
    return _read_json_file(os.path.abspath(os.path.join(HERE, "..", "tmc49_full_tank", "config.json")))

def saved_config(name):
    n = cfg_safe(name)
    return _read_json_file(os.path.join(CFGDIR, n + ".json"))

def project_config(rid):
    rid = _project_key(rid)
    if not rid:
        return None
    pd = proj_dir(rid)
    return (_read_json_file(os.path.join(pd, "case_config.json")) or
            _read_json_file(os.path.join(pd, "config.json")))

def _apply_board_floor_revision(cfg):
    """Copy and correct the one known raised-board legacy geometry.

    Historical project snapshots stay untouched because their Raw fields were
    solved on that geometry. This migration is only for a new setting/project.
    """
    if not isinstance(cfg, dict):
        return cfg, False
    board = cfg.get("board") or {}
    cpus = (cfg.get("heater") or {}).get("cpus") or []
    try:
        legacy_board = all(abs(float(board.get(k)) - v) < 1e-9 for k, v in {
            "x0": 80, "x1": 380, "y0": 40, "y1": 340, "z0": 15, "z1": 23,
        }.items())
        legacy_cpus = bool(cpus) and all(
            abs(float(cpu.get("y0")) - 130) < 1e-9 and
            abs(float(cpu.get("y1")) - 170) < 1e-9 for cpu in cpus
        )
    except (TypeError, ValueError):
        return cfg, False
    if not (legacy_board and legacy_cpus):
        return cfg, False
    out = json.loads(json.dumps(cfg))
    out["board"]["y0"], out["board"]["y1"] = 0, 300
    for cpu in out["heater"]["cpus"]:
        cpu["y0"] = float(cpu["y0"]) - 40
        cpu["y1"] = float(cpu["y1"]) - 40
        if cpu["y0"].is_integer(): cpu["y0"] = int(cpu["y0"])
        if cpu["y1"].is_integer(): cpu["y1"] = int(cpu["y1"])
    out["board"]["_형상근거"] = (
        "이권영 교수님 발표자료의 치수 표기 수조 사진: 보드 하단은 수조 바닥, "
        "높이 300 mm. 이전 y=40~340에서 y=0~300으로 수정하고 CPU 발열면도 "
        "같은 상대 위치로 40 mm 하향"
    )
    out["_형상개정"] = "board-floor-v1: 새 계산용으로 보드와 CPU를 40 mm 하향"
    return out, True

OUTPUT_FIELDS = ("bubble", "phase", "flow", "therm", "pressure", "turbulence")

def _valid_cell_centres(path):
    """C가 존재하는지뿐 아니라 OpenFOAM 셀 중심좌표 파일인지 확인한다.

    변환이 중단되면 빈 파일 또는 일부만 복사된 C가 남을 수 있다. 그런 파일을
    정상으로 취급하면 Viewer에서는 원인을 알 수 없는 '셀 좌표 없음' 또는 파싱
    오류가 반복되므로, 가벼운 헤더 검사로 재생성 대상으로 분류한다.
    """
    try:
        if not os.path.isfile(path) or os.path.getsize(path) < 128:
            return False
        with open(path, "rb") as f:
            head = f.read(16384)
        return (b"internalField" in head and
                re.search(rb"nonuniform\s+List<vector>\s+\d+", head) is not None)
    except OSError:
        return False

def _valid_viz_output(path, kind):
    """시각화 파생 파일의 헤더와 길이를 가벼게 검증한다.

    중단된 쓰기나 외부 복사로 생긴 0 byte/부분 파일을 단순히
    ``exists``로 완료 처리하지 않도록 한다. RAW OpenFOAM 필드는 읽기
    전용 호환 입력이고, 나머지는 CFD Studio가 작성한 고정 포맷이다.
    """
    import struct as _st
    try:
        size = os.path.getsize(path)
        if kind == "foam_scalar":
            if size < 128:
                return False
            with open(path, "rb") as f:
                head = f.read(min(size, 65536))
            i0 = head.find(b"internalField")
            if i0 < 0:
                return False
            m = re.search(rb"List<scalar>\s*\n(\d+)\s*\n\(", head[i0:i0 + 2048])
            if not m:
                return False
            count = int(m.group(1))
            data_at = i0 + m.end()
            return count > 0 and size >= data_at + count * 8
        with open(path, "rb") as f:
            head = f.read(16)
        if kind == "bubble":
            if len(head) < 12 or head[:4] != b"BUB1":
                return False
            count, total = _st.unpack_from("<2I", head, 4)
            return total > 0 and count <= total and size == 12 + count * 8
        if len(head) < 16:
            return False
        nx, ny, nz = _st.unpack_from("<3I", head, 4)
        cells = nx * ny * nz
        if not cells or max(nx, ny, nz) > 100000:
            return False
        if kind == "flow":
            return head[:4] == b"FLW1" and size == 40 + cells * 12
        if kind == "therm":
            return head[:4] == b"THM1" and size == 40 + cells * 4
        if kind == "pressure":
            return head[:4] == b"PRS1" and size == 40 + cells * 4
        if kind == "turbulence":
            return head[:4] == b"TRB1" and size == 40 + cells * 8
        if kind == "phase":
            stride = 3 if head[:4] == b"PHS2" else 2 if head[:4] == b"PHS1" else 0
            return bool(stride) and size == 40 + cells * stride
    except (OSError, ValueError, OverflowError, _st.error):
        pass
    return False

def _cleanup_extract_temps(pdir):
    """Studio 강제 종료 후 남은 파생 임시 파일만 제거한다."""
    fixed = {"_C_tmp", "_A_tmp", "_W_tmp", "_U_tmp", "_T_tmp",
             "_P_tmp", "_K_tmp", "_E_tmp"}
    try:
        names = os.listdir(pdir)
    except OSError:
        return
    for name in names:
        generated_tmp = (name.endswith(".bin.tmp") and
                         name.startswith(("bub_", "flow_", "therm_", "phase_",
                                          "pressure_", "turbulence_")))
        if name not in fixed and not generated_tmp and not name.startswith(".no_phase_"):
            continue
        if name.startswith(".no_phase_") and not name.endswith(".tmp"):
            continue
        try: os.remove(os.path.join(pdir, name))
        except OSError: pass

def _normalize_output_fields(value):
    """시각화 고빈도 저장 선택. 필드가 없던 v75 이전 config는 모두 선택으로 호환한다."""
    if value is None:
        return list(OUTPUT_FIELDS)
    if not isinstance(value, list):
        return list(OUTPUT_FIELDS)
    return [name for name in OUTPUT_FIELDS if name in value]

def project_inventory(pdir):
    """UI에 표시할 6종 입력을 폴더 자체에서 독립적으로 탐지."""
    try:
        names = os.listdir(pdir)
    except Exception:
        names = []
    cfg_name = next((n for n in ("case_config.json", "config.json")
                     if os.path.isfile(os.path.join(pdir, n))), "")
    num = r"[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?"
    bubs = [n for n in names if re.fullmatch(r"bub_" + num + r"\.bin", n)]
    raws = [n for n in names if re.fullmatch(r"alpha\.vapour_" + num, n)]
    flows = [n for n in names if re.fullmatch(r"flow_" + num + r"\.bin", n)]
    therms = [n for n in names if re.fullmatch(r"therm_" + num + r"\.bin", n)]
    phases = [n for n in names if re.fullmatch(r"phase_" + num + r"\.bin", n)]
    pressures = [n for n in names if re.fullmatch(r"pressure_" + num + r"\.bin", n)]
    turbulences = [n for n in names if re.fullmatch(r"turbulence_" + num + r"\.bin", n)]
    tracer_frames = (_read_json_file(os.path.join(pdir, "tracer_frames.json")) or {}).get("frames", [])
    times = []
    for n in bubs:
        try: times.append(float(n[4:-4]))
        except Exception: pass
    for n in raws:
        try: times.append(float(n.split("_")[1]))
        except Exception: pass
    for n, a, b in ([(n, 5, -4) for n in flows]
                    + [(n, 6, -4) for n in therms]
                    + [(n, 6, -4) for n in phases]
                    + [(n, 9, -4) for n in pressures]
                    + [(n, 11, -4) for n in turbulences]):
        try: times.append(float(n[a:b]))
        except Exception: pass
    return {"config": bool(cfg_name), "config_name": cfg_name,
            "C": _valid_cell_centres(os.path.join(pdir, "C")),
            "bubble": len(bubs) + len(raws), "flow": len(flows), "therm": len(therms),
            "phase": len(phases), "pressure": len(pressures),
            "turbulence": len(turbulences), "concentration": len(tracer_frames), "sorbed": len(tracer_frames),
            "tmax": max(times + [float(f["t"]) for f in tracer_frames], default=0.0)}

def _apply_config_file(src):
    """선택한 config 파일을 검증한 뒤 WSL 케이스에 원자적으로 교체."""
    if not src or not os.path.isfile(src):
        return False, "config 파일을 찾을 수 없음"
    wsrc = win2wsl(os.path.abspath(src))
    return wsl(f"cd {_wsl_case_token()} || exit 1; "
               f"cp {_shq(wsrc)} config.json.cfdstudio.tmp || exit 2; "
               "python3 -c \"import json; json.load(open('config.json.cfdstudio.tmp'))\" || exit 3; "
               "mv -f config.json.cfdstudio.tmp config.json; echo APPLIED")

def _write_runtime_config(cfg):
    """브라우저에서 읽은 config를 WSL로 옮기기 위한 안전한 임시 파일."""
    valid_immersion = isinstance(cfg, dict) and "tank" in cfg and "run" in cfg
    valid_silo = isinstance(cfg, dict) and cfg.get("_해석유형") == "grain_silo" and "run" in cfg
    if not (valid_immersion or valid_silo):
        return None
    path = os.path.join(RUNTIME_DIR, "selected_config.json")
    meta_write(path, cfg)
    return path
META_LK = threading.Lock()
STUDIO_CFG_LK = threading.Lock()

def meta_write(path, obj):
    """임시파일 → 원자 교체. 폴링 경쟁으로 meta.json이 깨져 이름이 사라지는 문제 방지"""
    with META_LK:
        tmp = path + ".tmp"
        json.dump(obj, open(tmp, "w"))
        os.replace(tmp, path)

def _save_studio_config(**changes):
    """실행 중 바꾼 PC별 설정을 원자적으로 저장한다."""
    with STUDIO_CFG_LK:
        SCFG.update(changes)
        tmp = _SCP + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(SCFG, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, _SCP)

def _canonical_raw_studio_dir(path):
    """선택한 드라이브에서 실제 데이터 폴더 `CFD Studio`를 결정한다."""
    raw = str(path or "").strip().strip('"')
    if not raw:
        return ""
    # 진단·복구 작업을 WSL Python으로 실행해도 Windows 드라이브 경로를 현재
    # 작업 폴더의 상대 경로로 오해하지 않게 먼저 /mnt/<drive>로 정규화한다.
    win_drive = re.match(r"^([A-Za-z]):[\\/]*(.*)$", raw)
    if os.name != "nt" and win_drive:
        raw = "/mnt/" + win_drive.group(1).lower() + "/" + win_drive.group(2).replace("\\", "/")
    raw = os.path.abspath(os.path.expandvars(os.path.expanduser(raw)))
    drive, _ = os.path.splitdrive(raw)
    app_drive, _ = os.path.splitdrive(HERE)
    if drive:
        # 설정은 드라이브 선택으로 해석한다. 같은 드라이브는 현재 Studio를,
        # 다른 드라이브는 루트의 'CFD Studio' 폴더를 사용한다.
        if app_drive and os.path.normcase(drive) == os.path.normcase(app_drive):
            return HERE
        return os.path.join(drive + os.sep, "CFD Studio")
    return raw if os.path.basename(os.path.normpath(raw)).casefold() == "cfd studio" else os.path.join(raw, "CFD Studio")

def _raw_archive_dir():
    return _canonical_raw_studio_dir(SCFG.get("raw_archive_dir"))

def _project_raw_root(rid):
    key = _project_key(rid)
    if not key:
        return ""
    meta = _read_json_file(os.path.join(proj_dir(key), "meta.json")) or {}
    return str(meta.get("raw_archive_root") or "").strip()

def _usable_raw_root(path):
    ok, norm, _ = _validate_raw_archive_dir(path, require_writable=False)
    return norm if ok and norm else ""

def _storage_volume_key(path):
    """존재하지 않는 하위 경로도 비교할 수 있는 Windows/WSL 볼륨 식별자."""
    raw = os.path.abspath(os.path.expandvars(os.path.expanduser(str(path or ""))))
    drive = os.path.splitdrive(raw)[0]
    if drive:
        return os.path.normcase(drive.rstrip("\\/"))
    m = re.match(r"^/mnt/([A-Za-z])(?:/|$)", raw)
    if m:
        return m.group(1).casefold() + ":"
    probe = raw
    while probe and not os.path.exists(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    try:
        return "dev:" + str(os.stat(probe).st_dev)
    except OSError:
        return ""

def _same_storage_volume(left, right):
    a, b = _storage_volume_key(left), _storage_volume_key(right)
    return bool(a and b and a == b)

def _desired_project_raw_path(pdir, root):
    """양쪽 CFD Studio에서 Project/프로젝트명/Raw_Data 구조를 맞춘다."""
    if not pdir or not root:
        return ""
    project = os.path.abspath(pdir)
    base = os.path.abspath(os.path.expandvars(os.path.expanduser(str(root))))
    if _same_storage_volume(project, base):
        return os.path.join(project, "Raw_Data")
    return os.path.join(base, "Project", os.path.basename(os.path.normpath(project)), "Raw_Data")

def _resolved_project_raw_root(rid, preferred=""):
    """기존 데이터는 유지하고, 끊긴 PC 경로만 현재 Studio 설정으로 재연결한다."""
    key = _project_key(rid)
    if not key:
        return ""
    meta = _read_json_file(os.path.join(proj_dir(key), "meta.json")) or {}
    if meta.get("execution_project_id"):
        return proj_dir(key)
    saved = str(meta.get("raw_archive_run") or "").strip()
    stored = str(meta.get("raw_archive_root") or "").strip()
    configured = _raw_archive_dir()
    # 데이터가 있는 프로젝트는 설정 변경만으로 다른 루트에 분산하지 않는다.
    if saved and os.path.isdir(saved):
        return _usable_raw_root(stored) or _usable_raw_root(os.path.dirname(saved))
    # 다른 PC에서 과거 드라이브가 사라진 경우 현재 옵션의 Studio 루트를 우선한다.
    seen = set()
    for candidate in (preferred, configured, stored):
        marker = os.path.normcase(os.path.normpath(str(candidate or "")))
        if not candidate or marker in seen:
            continue
        seen.add(marker)
        usable = _usable_raw_root(candidate)
        if usable:
            return usable
    return str(preferred or configured or stored).strip()

def _project_raw_run_path(rid, root=""):
    """현재 접근 가능한 프로젝트 Raw 경로. 이전 경로도 마이그레이션 전까지 읽는다."""
    key = _project_key(rid)
    if not key:
        return ""
    pdir = proj_dir(key)
    meta = _read_json_file(os.path.join(pdir, "meta.json")) or {}
    if meta.get("execution_project_id"):
        return os.path.join(pdir, "Raw_Data")
    saved = str(meta.get("raw_archive_run") or "").strip()
    # 저장된 경로가 다른 PC의 드라이브이거나 과거 진단에서 깨졌다면 현재 PC의
    # 유효한 Studio 루트를 사용한다. 존재하는 saved 데이터는 아래에서 계속 우선한다.
    base = str(root or _resolved_project_raw_root(key)).strip()
    desired = _desired_project_raw_path(pdir, base)
    if saved and os.path.isdir(saved):
        return saved
    if desired and os.path.isdir(desired):
        return desired
    return saved or desired

def _project_raw_run_dir(rid):
    """프로젝트에 귀속된 외부 Raw 보관 폴더만 반환한다."""
    key = _project_key(rid)
    if not key:
        return ""
    candidate = _project_raw_run_path(key)
    return candidate if candidate and os.path.isdir(candidate) else ""

def _open_explorer(path):
    """Studio는 Windows에서 실행되므로 탐색기만 비동기로 연다."""
    try:
        os.startfile(path)  # type: ignore[attr-defined]
    except AttributeError:
        subprocess.Popen(["explorer.exe", path])

def _migrate_project_raw_layout(rid):
    """중단된 기존 Raw를 현재 드라이브 규칙으로 옮기고 관련 WSL 링크를 복구한다."""
    key = _project_key(rid)
    if not key:
        return False
    run_id = str((_read_json_file(os.path.join(proj_dir(key), "meta.json")) or {}).get("run_id") or key)
    if key == _active_rid() and get_status().get("running"):
        RAW_ARCHIVE_STATE.update(msg="실행 중 프로젝트 Raw 경로 전환은 중단 후 진행")
        return False
    lock = _raw_io_lock(key)
    if not lock.acquire(timeout=180):
        RAW_ARCHIVE_STATE.update(msg="프로젝트별 Raw 경로 전환 대기 시간 초과")
        return False
    try:
        pdir = proj_dir(key)
        meta_path = os.path.join(pdir, "meta.json")
        meta = _read_json_file(meta_path) or {}
        if meta.get("execution_project_id"):
            return False
        old = str(meta.get("raw_archive_run") or "").strip()
        old_root = str(meta.get("raw_archive_root") or "").strip()
        # 새 규칙의 현재 Studio 루트를 우선한다. 기존 Raw가 있으면 아래에서 같은
        # 드라이브 안의 새 위치로 원자적으로 이동하고, 실행 중이면 아예 건드리지 않는다.
        root = _raw_archive_dir() or _resolved_project_raw_root(key)
        target = _desired_project_raw_path(pdir, root)
        if not root or not target:
            return False
        same_path = bool(old and os.path.normcase(os.path.normpath(old)) == os.path.normcase(os.path.normpath(target)))
        if same_path:
            if old != target:
                meta["raw_archive_run"] = target
                meta_write(meta_path, meta)
            _transfer_raw_archive_index(old_root, root, run_id)
            _reconcile_raw_archive_index(root, run_id, target)
            case_src = WSL_CASE if key == _active_rid() else f"{WSL_CASE}/ProjectRuns/{run_id}"
            ok_links, broken = _repair_raw_links(case_src, run_id)
            if not ok_links:
                RAW_ARCHIVE_STATE.update(msg=f"Raw 링크 복구 미완료: {broken}개 시각")
            return ok_links
        if not old or not os.path.isdir(old):
            if os.path.isdir(target):
                meta["raw_archive_root"] = root
                meta["raw_archive_run"] = target
                meta_write(meta_path, meta)
                _transfer_raw_archive_index(old_root, root, run_id)
                _reconcile_raw_archive_index(root, run_id, target)
                case_src = WSL_CASE if key == _active_rid() else f"{WSL_CASE}/ProjectRuns/{run_id}"
                ok_links, broken = _repair_raw_links(case_src, run_id)
                if not ok_links:
                    RAW_ARCHIVE_STATE.update(msg=f"Raw 링크 복구 미완료: {broken}개 시각")
                return ok_links
            # 아직 Raw가 생성되지 않은 프로젝트는 경로 예약만 한다.
            meta["raw_archive_root"] = root
            meta["raw_archive_run"] = target
            meta_write(meta_path, meta)
            return True
        if os.path.exists(target):
            RAW_ARCHIVE_STATE.update(msg="Raw 경로 전환 중단: 대상 폴더에 기존 데이터가 있습니다")
            return False
        if not _same_storage_volume(old, target):
            RAW_ARCHIVE_STATE.update(msg="Raw 경로 전환 중단: 기존 데이터와 새 위치의 드라이브가 다릅니다")
            return False
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.move(old, target)
        meta["raw_archive_root"] = root
        meta["raw_archive_run"] = target
        meta_write(meta_path, meta)
        _transfer_raw_archive_index(old_root, root, run_id)
        _reconcile_raw_archive_index(root, run_id, target)
        case_src = WSL_CASE if key == _active_rid() else f"{WSL_CASE}/ProjectRuns/{run_id}"
        ok, msg = _repair_raw_links(case_src, run_id)
        RAW_ARCHIVE_STATE.update(msg=("프로젝트별 Raw 경로 전환 완료" if ok else "Raw 이동 후 링크 복구 확인 필요: " + str(msg)[:100]))
        return ok
    except Exception as e:
        RAW_ARCHIVE_STATE.update(msg="프로젝트별 Raw 경로 전환 실패: " + str(e)[:100])
        return False
    finally:
        lock.release()

def _migrate_all_project_raw_layouts():
    """시작 시 중단/보관 프로젝트를 새 경로 규칙으로 순차 정리한다."""
    try:
        projects = [p.get("rid") for p in list_projects() if p.get("rid") and not p.get("pending")]
    except Exception:
        projects = []
    for rid in projects:
        try: _migrate_project_raw_layout(rid)
        except Exception: pass

def _validate_raw_archive_dir(path, require_writable=True):
    """PC별 원본 보관 폴더를 검사한다. 없는 드라이브를 임의 생성하거나 대체하지 않는다."""
    raw = str(path or "").strip().strip('"')
    if not raw:
        return True, "", "사용 안 함"
    raw = os.path.abspath(os.path.expandvars(os.path.expanduser(raw)))
    if not os.path.isdir(raw):
        return False, raw, "선택한 폴더를 찾을 수 없습니다"
    if require_writable:
        probe = os.path.join(raw, ".cfd_studio_write_test_" + uuid.uuid4().hex)
        try:
            with open(probe, "wb") as f:
                f.write(b"ok")
            os.remove(probe)
        except Exception as e:
            try:
                if os.path.isfile(probe): os.remove(probe)
            except Exception: pass
            return False, raw, "선택한 폴더에 쓸 수 없습니다: " + str(e)[:80]
    return True, raw, "사용 가능"

def _raw_archive_public():
    raw = _raw_archive_dir()
    ok, norm, msg = _validate_raw_archive_dir(raw, require_writable=False)
    st = dict(globals().get("RAW_ARCHIVE_STATE") or {})
    return {"enabled": bool(raw), "path": norm or raw, "available": bool(raw and ok),
            "message": st.get("msg") or msg, "busy": bool(st.get("busy")),
            "archived_frames": int(st.get("archived_frames") or 0),
            "archived_bytes": int(st.get("archived_bytes") or 0),
            "last_time": st.get("last_time")}

def _repair_raw_links(case_src, rid):
    """다른 PC/드라이브 문자로 옮긴 원본의 끊어진 시간 링크를 현재 설정으로 복구한다."""
    run_id = re.sub(r"[^0-9]", "", str(rid or ""))
    roots = []
    for candidate in (_project_raw_root(run_id), _raw_archive_dir()):
        ok, norm, _ = _validate_raw_archive_dir(candidate, require_writable=False)
        if ok and norm and norm.casefold() not in {r.casefold() for r in roots}:
            roots.append(norm)
    repair = ""
    if run_id:
        run_dirs = []
        saved = _project_raw_run_path(run_id)
        if saved: run_dirs.append(saved)
        pname = os.path.basename(os.path.normpath(proj_dir(run_id)))
        for root in roots:
            for candidate in (os.path.join(root, "Project", pname, "Raw_Data"),
                              os.path.join(root, pname, "raw_data"),
                              os.path.join(root, "runs", run_id)):
                if candidate.casefold() not in {p.casefold() for p in run_dirs}:
                    run_dirs.append(candidate)
        run_args = " ".join(_shq(win2wsl(path)) for path in run_dirs)
        if run_dirs: repair = (
            "N=0; TIMES=$(find processor[0-9]* -mindepth 1 -maxdepth 1 -type l -printf '%f\\n' 2>/dev/null | sort -gu); "
            "for T in $TIMES; do CANON=''; "
            f"for RUN in {run_args}; do [ -f \"$RUN/times/$T/.cfd_complete\" ] && {{ CANON=\"$RUN\"; break; }}; done; "
            "if [ -z \"$CANON\" ]; then N=$((N+1)); continue; fi; "
            "for P in processor[0-9]*; do D=\"$P/$T\"; [ -L \"$D\" ] || continue; "
            "ln -sfn \"$CANON/times/$T/$P\" \"$D\" || N=$((N+1)); done; done; "
            "echo BROKEN=$N; "
        )
    check = "[ -n \"${N+x}\" ] || echo BROKEN=0"
    ok_w, out = wsl(f"cd {case_src} 2>/dev/null || exit 2; {repair}{check}", timeout=180)
    m = re.search(r"(?m)^BROKEN=([0-9]+)$", out or "")
    broken = int(m.group(1)) if m else 0
    return ok_w and broken == 0, broken

def _repair_active_raw_links():
    """Raw 위치를 바꾼 직후에만 전체 링크를 검사한다."""
    rid = _active_rid()
    if rid:
        _repair_raw_links(WSL_CASE, rid)

def _pick_raw_archive_dir():
    """Windows 기본 폴더 선택 창. 브라우저 보안상 감춰지는 실제 경로를 서버가 직접 받는다."""
    if os.name != "nt" or not POWERSHELL_EXE:
        return False, "", "Windows 폴더 선택 창을 열 수 없습니다"
    ps = (
        "[Console]::OutputEncoding=[Text.UTF8Encoding]::new();"
        "Add-Type -AssemblyName System.Windows.Forms;"
        "$d=New-Object System.Windows.Forms.FolderBrowserDialog;"
        "$d.Description='Raw 저장에 사용할 드라이브 또는 폴더 선택';"
        "$d.ShowNewFolderButton=$true;"
        "if($env:CFD_STUDIO_PICK_START -and (Test-Path -LiteralPath $env:CFD_STUDIO_PICK_START)){"
        "$d.SelectedPath=$env:CFD_STUDIO_PICK_START};"
        "if($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK){[Console]::Write($d.SelectedPath)}"
    )
    env = os.environ.copy()
    env["CFD_STUDIO_PICK_START"] = _raw_archive_dir()
    flags = 0x08000000
    try:
        r = subprocess.run([POWERSHELL_EXE, "-NoProfile", "-STA", "-Command", ps],
                           capture_output=True, timeout=600, creationflags=flags, env=env)
        path = r.stdout.decode("utf-8", "replace").strip()
        if r.returncode != 0:
            return False, "", r.stderr.decode("utf-8", "replace")[:120] or "폴더 선택 실패"
        if not path:
            return True, "", "취소"
        ok, path, msg = _validate_raw_archive_dir(path)
        if not ok:
            return False, path, msg
        path = _canonical_raw_studio_dir(path)
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as e:
            return False, path, "CFD Studio 폴더를 만들 수 없습니다: " + str(e)[:80]
        return _validate_raw_archive_dir(path)
    except Exception as e:
        return False, "", str(e)[:120]

def _solver_mode():
    mode = str(SCFG.get("pressure_solver_mode", "cpu")).strip().lower()
    return mode if mode in ("cpu", "gpu", "gpu_only") else "cpu"


def _mode_public(mode=None):
    mode = mode or _solver_mode()
    return {
        "cpu": ("cpu_only", "CPU Only"),
        "gpu": ("hybrid", "CPU + GPU 병행"),
        "gpu_only": ("gpu_only", "GPU Only (OpenCFD 개발)"),
    }.get(mode, ("cpu_only", "CPU Only"))


def _settings_public(refresh_gpu=False, rid=""):
    logical, physical = _cpu_topology()
    if refresh_gpu:
        _ENV.update(gpu=None, gpu_info=None)
    devices = gpu_devices(refresh=refresh_gpu)
    project_key = _project_key(rid) or _active_rid()
    raw = _raw_archive_public()
    project_raw_path = _project_raw_run_path(project_key) if project_key else ""
    solver_mode = _solver_mode()
    compute_mode, compute_label = _mode_public(solver_mode)
    gpu_only = _gpu_only_status(refresh=refresh_gpu)
    return {
        "cpu_pct": cpu_pct(), "cpu_pct_setting": SCFG.get("cpu_pct", 60),
        "cpu_logical": logical, "cpu_physical": physical,
        "mpi_np": SCFG.get("mpi_np", "auto"),
        "mpi_effective": (1 if solver_mode == "gpu_only" else mpi_np()),
        "gpu_index": SCFG.get("gpu_index", "auto"), "gpu_effective": gpu_index(),
        "pressure_solver_mode": solver_mode,
        "compute_mode": compute_mode, "compute_mode_label": compute_label,
        "pressure_solver_labels": {
            "cpu": "CPU Only · GAMG",
            "gpu": "CPU + GPU 병행 · p_rgh PETSc CUDA",
            "gpu_only": "GPU Only · OpenCFD std::execution/UMPIRE",
        },
        "gpu_only": gpu_only,
        "gpu_devices": devices, "raw_archive": {**raw, "project_rid": project_key,
                                                   "project_path": project_raw_path},
        "defaults": {"cpu_pct": 60, "mpi_np": "auto", "gpu_index": "auto", "pressure_solver_mode": "cpu", "raw_archive_dir": ""}
    }

def _apply_studio_settings(payload):
    try: cpu = int(float(payload.get("cpu_pct", SCFG.get("cpu_pct", 60))))
    except Exception: return False, "CPU 상한은 1~80 사이 숫자여야 합니다"
    if not 1 <= cpu <= 80:
        return False, "CPU 상한은 1~80% 범위에서 설정해 주세요"
    logical = max(1, _cpu_topology()[0])
    mpi_raw = payload.get("mpi_np", SCFG.get("mpi_np", "auto"))
    if str(mpi_raw).strip().lower() == "auto":
        mpi = "auto"
    else:
        try: mpi = int(float(mpi_raw))
        except Exception: return False, "MPI 작업자는 자동 또는 1 이상의 숫자여야 합니다"
        if not 1 <= mpi <= logical:
            return False, f"MPI 작업자는 이 PC의 논리 CPU 수({logical})를 넘을 수 없습니다"
    gpu_raw = payload.get("gpu_index", SCFG.get("gpu_index", "auto"))
    if str(gpu_raw).strip().lower() == "auto":
        gpu = "auto"
    else:
        try: gpu = int(gpu_raw)
        except Exception: return False, "GPU 선택값이 올바르지 않습니다"
        devices = gpu_devices(refresh=True)
        if not any(int(g.get("index", -1)) == gpu for g in devices):
            return False, "현재 PC에서 선택한 GPU를 찾을 수 없습니다"
    solver_mode = str(payload.get("pressure_solver_mode", SCFG.get("pressure_solver_mode", "cpu"))).strip().lower()
    if solver_mode not in ("cpu", "gpu", "gpu_only"):
        return False, "계산 모드는 CPU Only, CPU+GPU 병행, GPU Only 중에서 선택해야 합니다"
    if solver_mode == "gpu_only":
        gpu_only = _gpu_only_status(refresh=True)
        if not gpu_only.get("ready"):
            return False, "GPU Only 준비 안 됨: " + str(gpu_only.get("message") or "전용 실행 환경을 확인해 주세요")
    _save_studio_config(cpu_pct=cpu, mpi_np=mpi, gpu_index=gpu,
                        pressure_solver_mode=solver_mode)
    # 실행 중 솔버는 건드리지 않는다. 다음 시작/재개가 새 하드웨어 설정을 사용한다.
    _ENV.update(np=None, cset=None, gpu=None, gpu_info=None)
    RAW_ARCHIVE_WAKE.set()
    threading.Thread(target=_storage_refresh, name="cfd-storage-settings", daemon=True).start()
    return True, "저장 완료"

def _persist_project_progress(rid, value, case_archive=None):
    """실시간 케이스가 교체돼도 중단 시각과 WSL 보관 케이스를 유지한다."""
    key = _project_key(rid)
    if not key:
        return
    pd = proj_dir(key)
    if not os.path.isdir(pd) or pd == FRAME_DIR:
        return
    try:
        t = max(0.0, float(value or 0))
    except Exception:
        t = 0.0
    mp = os.path.join(pd, "meta.json")
    meta = _read_json_file(mp) or {}
    try:
        old = max(float(meta.get("last_time") or 0), float(meta.get("tmax") or 0))
    except Exception:
        old = 0.0
    changed = False
    if t > old:
        meta["last_time"] = t
        changed = True
    if case_archive and meta.get("case_archive") != case_archive:
        meta["case_archive"] = case_archive
        meta.pop("raw_archive", None)            # v107 이전의 의미가 불명확한 필드
        changed = True
    if changed:
        meta_write(mp, meta)

def list_projects():
    # 이전 버전 인스턴스가 구형 frames/<rid> 폴더를 다시 만든 경우도
    # 조회 시 즉시 Project/<rid>로 합쳐 목록에서 사라지지 않게 한다.
    try: _migrate_project_dirs()
    except Exception: pass
    out = []
    external = {os.path.normcase(os.path.abspath(p)) for p in EXECUTION_WORKSPACE.external_paths()}
    for d, p in _project_entries():
        linked = os.path.normcase(os.path.abspath(p)) in external
        if not linked:
            _normalize_project_dir(p, d)
        ts = []
        n = 0
        for f in os.listdir(p):
            try:
                if f.startswith("bub_") and f.endswith(".bin"): ts.append(float(f[4:-4])); n += 1
                elif f.startswith("alpha.vapour_"): ts.append(float(f.split("_")[1])); n += 1
            except Exception: pass
        meta = {}
        try: meta = json.load(open(os.path.join(p, "meta.json")))
        except Exception: pass
        project_cfg = (_read_json_file(os.path.join(p, "case_config.json")) or
                       _read_json_file(os.path.join(p, "config.json")) or {})
        project_analysis = project_cfg.get("_해석유형") or "immersion"
        project_solver = (project_cfg.get("openfoam_mapping") or {}).get("solver") or ""
        project_run = project_cfg.get("run") or {}
        playback_duration = float(project_run.get("playback_duration_s") or 60)
        inv = project_inventory(p)
        project_id = str(meta.get("run_id") or meta.get("project_id") or d)
        if not linked and not meta.get("heal2"):            # 1회 치유: end는 프로젝트 자신의 값이어야 함
            try:
                own = (meta.get("settings") or {}).get("end_time_s")
                if not own:
                    cfg = get_config() or {}
                    own = float(cfg.get("run", {}).get("end_time_s") or 30)
                meta["end"] = float(own); meta["heal2"] = True; meta["end_locked"] = True
                meta_write(os.path.join(p, "meta.json"), meta)
            except Exception: pass
        stored_t = max(ts + [float(inv.get("tmax") or 0), float(meta.get("tmax") or 0),
                             float(meta.get("last_time") or 0)])
        out.append({"rid": project_id, "folder": d, "n": n, "tmax": stored_t,
                    "end": meta.get("end"), "name": meta.get("name") or "",
                    "analysis": project_analysis, "solver": project_solver,
                    "playback_duration_s": playback_duration,
                    "settings": meta.get("settings"),
                    "completed": bool(meta.get("completed")),
                    "completion_reason": str(meta.get("completion_reason") or ""),
                    "reset_ready": bool(meta.get("reset_at")),
                    "archived": bool(meta.get("storage_tier") == "archive" or
                                     os.path.normcase(os.path.abspath(os.path.dirname(p))) !=
                                     os.path.normcase(os.path.abspath(PROJECT_DIR))),
                    "external": bool(meta.get("external")), "data": inv,
                    "extract": _extract_public(project_id),
                    "config_available": inv["config"],
                    "preset_available": bool(meta.get("settings")) or inv["config"],
                    "mtime": os.path.getmtime(p)})
    out.sort(key=lambda x: -x["mtime"])
    try:
        pj = json.load(open(PENDF))
        out.insert(0, {"rid": "", "n": 0, "tmax": 0, "end": None, "pending": True,
                      "name": pj.get("name") or "새 프로젝트", "mtime": pj.get("created", 0)})
    except Exception:
        pass
    return out

def flist(pd, pre, key):
    if not os.path.isdir(pd): return []
    return sorted([f for f in os.listdir(pd) if f.startswith(pre) and (pre == "alpha.vapour_" or f.endswith(".bin"))], key=key)

_ENV = {"bashrc": None, "np": None, "cset": None, "topo": None,
        "gpu": None, "gpu_info": None, "gpu_devices": None}
GPU_ONLY_STATUS = {"t": 0.0, "data": None}

def _find_wsl_exe():
    """PATH가 빠져 있어도 Windows 기본 경로에서 wsl.exe를 찾는다."""
    override = str(os.environ.get("CFD_STUDIO_WSL_EXE") or "").strip().strip('"')
    found = shutil.which("wsl.exe") or shutil.which("wsl")
    candidates = [override, found]
    if os.name == "nt":
        winroot = os.environ.get("SystemRoot") or os.environ.get("WINDIR") or r"C:\Windows"
        # 32비트 Python의 System32 리다이렉션까지 피하기 위해 Sysnative도 확인한다.
        candidates.extend((os.path.join(winroot, "System32", "wsl.exe"),
                           os.path.join(winroot, "Sysnative", "wsl.exe")))
    else:
        # WSL/Codex 쉘에서 Windows PATH가 노출되지 않은 경우의 폴백.
        candidates.append("/mnt/c/Windows/System32/wsl.exe")
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return found or ("wsl.exe" if os.name == "nt" else "wsl")

WSL_EXE = _find_wsl_exe()


def _find_host_executable(name, override_env, relative_candidates=()):
    """Windows PATH가 제한된 PC에서도 표준 설치 위치와 명시적 재정의를 함께 탐색한다."""
    override = str(os.environ.get(override_env) or "").strip().strip('"')
    candidates = [override, shutil.which(name)]
    if os.name == "nt":
        roots = []
        for key in ("SystemRoot", "WINDIR", "ProgramW6432", "ProgramFiles"):
            value = os.environ.get(key)
            if value and value not in roots:
                roots.append(value)
        for root in roots:
            for rel in relative_candidates:
                candidates.append(os.path.join(root, *rel))
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return shutil.which(name)


NVIDIA_SMI = _find_host_executable(
    "nvidia-smi.exe" if os.name == "nt" else "nvidia-smi",
    "CFD_STUDIO_NVIDIA_SMI",
    (("System32", "nvidia-smi.exe"), ("NVIDIA Corporation", "NVSMI", "nvidia-smi.exe")),
)
POWERSHELL_EXE = _find_host_executable(
    "powershell.exe" if os.name == "nt" else "powershell",
    "CFD_STUDIO_POWERSHELL",
    (("System32", "WindowsPowerShell", "v1.0", "powershell.exe"),),
)


def _shq(s):
    """쉘 단일 따옴표 문자열 인용."""
    return "'" + str(s).replace("'", "'\"'\"'") + "'"


def _scope_case_process_snip():
    """현재 케이스 디렉터리에서만 동작하는 pid 탐지에 재사용할 sh 스니펫."""
    return (
        f"CFD_CASE_DIR=$({('cd ' + _wsl_case_token() + ' && pwd -P')}); "
        "in_case_pid(){ "
        "  local p=\"$1\"; "
        "  [ -n \"$p\" ] || return 1; "
        "  [ -d \"/proc/$p\" ] || return 1; "
        "  local cwd; cwd=$(readlink /proc/$p/cwd 2>/dev/null || true); "
        "  [ -n \"$cwd\" ] || return 1; "
        f"  case \"$cwd\" in \"$CFD_CASE_DIR\"|\"$CFD_CASE_DIR\"/*) return 0;; esac; "
        "  return 1; "
        "}; "
    )


def _case_kill_script(match_patterns):
    """현재 케이스에 한정하여 패턴 매칭 프로세스를 TERM→KILL 정리."""
    pats = str(match_patterns).strip().strip("'\"")
    return (
        f"{_scope_case_process_snip()}"
        "PIDS=\"$(cat .cfd_studio_solver.pid .cfd_studio_allrun.pid "
        ".cfd_studio_supervisor.pid 2>/dev/null || true)\"; "
        f"PIDS=\"$PIDS $(pgrep -f '{pats}' 2>/dev/null || true)\"; "
        "for p in $PIDS; do "
        "[ \"$p\" = \"$$\" ] && continue; "
        "in_case_pid \"$p\" && kill -TERM \"$p\" 2>/dev/null || true; "
        "done; "
        "sleep 1; "
        f"PIDS=\"$(pgrep -f '{pats}' 2>/dev/null || true)\"; "
        "for p in $PIDS; do "
        "[ \"$p\" = \"$$\" ] && continue; "
        "in_case_pid \"$p\" && kill -KILL \"$p\" 2>/dev/null || true; "
        "done; "
        "rm -f .cfd_studio_solver.pid .cfd_studio_allrun.pid .cfd_studio_supervisor.pid; "
    )


def _archive_current_progress_script(next_rid, previous_rid=None):
    """새 실행 전 현재 원본 결과를 WSL 내부 프로젝트 보관소로 이동한다."""
    nr = re.sub(r"[^0-9]", "", str(next_rid or ""))
    pr = _project_key(previous_rid)
    old_cfg = os.path.join(proj_dir(pr), "case_config.json") if pr else ""
    old_cfg_wsl = win2wsl(old_cfg) if old_cfg and os.path.isfile(old_cfg) else ""
    return (
        'OLD="$(cat .cfd_studio_runid 2>/dev/null | tr -cd "0-9")"; '
        f'NEXT={_shq(nr)}; '
        'if [ -n "$OLD" ] && [ "$OLD" != "$NEXT" ]; then '
        'mkdir -p ProjectRuns; R="ProjectRuns/$OLD"; '
        'if [ -e "$R/processor0" ] || [ -e "$R/log.icoReactingMultiphaseInterFoam" ]; then '
        'R="ProjectRuns/${OLD}_$(date +%Y%m%d_%H%M%S)"; fi; '
        'mkdir -p "$R/system"; cp -a system/. "$R/system/" 2>/dev/null || true; '
        # 물성·격자·초기장을 공용 링크로 두면 다음 프로젝트가 과거 재개 상태를 바꾼다.
        'for d in constant 0 0.orig; do if [ -e "$d" ]; then rm -rf "$R/$d"; cp -a "$d" "$R/$d" || exit 31; fi; done; '
        'for f in log.* processor* postProcessing VTK .cfd_studio_solver.pid .cfd_studio_allrun.pid '
        '.cfd_studio_supervisor.pid .cfd_studio_solver_exit.json; do '
        '[ -e "$f" ] && mv "$f" "$R/"; done; '
        'for d in *; do if [ -d "$d" ] && [ "$d" != 0 ] && [ "$d" != ProjectRuns ] '
        '&& [ "$d" != Trash ] && echo "$d" | grep -Eq "^[0-9]+([.][0-9]+)?$"; then mv "$d" "$R/"; fi; done; '
        'for f in config.json run_overrides.json; do [ -f "$f" ] && cp -f "$f" "$R/"; done; '
        + (f'cp -f {_shq(old_cfg_wsl)} "$R/config.json" || exit 32; ' if old_cfg_wsl else '') +
        'echo "$OLD" > "$R/.cfd_studio_runid"; '
        'echo "[CFD Studio] previous raw results archived: $R"; '
        'fi; '
    )


def _mesh_signature(cfg):
    """보관본이 구버전 공용 constant 링크일 때 현재 격자를 재사용해도 되는지 판정하는 형상 지문."""
    cfg = cfg if isinstance(cfg, dict) else {}
    def take(group, keys):
        src = cfg.get(group) or {}
        return {k: src.get(k) for k in keys}
    if cfg.get("_해석유형") == "grain_silo":
        shape = {
            "analysis": "grain_silo",
            "published": take("published", (
                "outer_diameter_m", "total_height_m", "storage_diameter_m",
                "storage_height_m", "grain_height_m", "bottom_central_duct_diameter_m",
            )),
            "design": (cfg.get("silo") or {}).get("design"),
            "mesh": take("mesh", ("target_cells",)),
        }
        return json.dumps(shape, ensure_ascii=False, sort_keys=True)
    shape = {
        "tank": take("tank", ("width_mm", "depth_mm", "liquid_height_mm")),
        "layers": take("layers", ("dielectric_mm",)),
        "board": take("board", ("x0", "x1", "y0", "y1", "z0", "z1")),
        "heater_cpus": (cfg.get("heater") or {}).get("cpus"),
        "coil": take("coil", ("x0", "x1", "y0", "y1", "z0", "z1")),
        "mesh": take("mesh", ("dx_mm",)),
    }
    return json.dumps(shape, ensure_ascii=False, sort_keys=True)


def _resume_anchor_shell(var="LF", root=".", use_cache=False):
    """모든 MPI 파티션에 필수 필드가 있는 최신 재시작 시각을 찾는 셸 조각."""
    fields = (f'$(if grep -q \"grain_silo\" {root}/config.json 2>/dev/null; '
              'then echo \"p U k epsilon\"; else echo \"p_rgh T U alpha.vapour alpha.liquid alpha.water\"; fi)')
    prefix = ""
    suffix = ""
    if use_cache:
        prefix = (
            f'CACHE={root}/.cfd_studio_resume_anchor.cache; '
            'TARGET=$(printf \'%s\\n\' "$CANDS" | head -1); '
            f'RID=$(cat {root}/.cfd_studio_runid 2>/dev/null | tr -cd \'0-9\'); '
            f'NP=$(ls -d {root}/processor[0-9]* 2>/dev/null | wc -l); KEY="$RID:$NP:$TARGET"; '
            'read CK CA < "$CACHE" 2>/dev/null || true; '
            '[ -n "$TARGET" ] && [ "$CK" = "$KEY" ] && [ -n "$CA" ] && { echo "$CA"; exit 0; }; '
        )
        suffix = (
            'FOUND="$B"; mkdir -p "$(dirname "$CACHE")"; '
            'printf \'%s %s\\n\' "$KEY" "$FOUND" > "$CACHE.tmp" && mv -f "$CACHE.tmp" "$CACHE"; '
        )
    return (
        f'{var}=$(ALL=$(ls {root}/processor0 2>/dev/null '
        "| grep -E '^[0-9]+([.][0-9]+)?$' | sort -gr); "
        f'WI=$(awk \'/^writeInterval[[:space:]]/{{gsub(";","",$2); print $2; exit}}\' {root}/system/controlDict 2>/dev/null); '
        "CANDS=$(printf '%s\\n' \"$ALL\" | awk -v w=\"${WI:-0}\" "
        "'w+0<=0 {print; next} {q=$1/w; n=int(q+0.5); if((q-n<1e-5)&&(n-q<1e-5)) print}'); "
        + prefix +
        'for B in $CANDS $ALL; do '
        f'OK=1; for P in {root}/processor[0-9]*; do '
        f'for F in {fields}; do [ -s "$P/$B/$F" ] || {{ OK=0; break 2; }}; done; done; '
        '[ "$OK" -eq 1 ] && { ' + suffix + 'echo "$B"; break; }; done); '
    )


def _activate_archived_project(rid):
    """보관된 병렬 케이스를 현재 케이스와 교환하고 해당 프로젝트 설정만 복원한다."""
    rid = _project_key(rid)
    current = _active_rid()
    if not rid:
        return False, "재개할 프로젝트가 없습니다"
    selected_meta = _read_json_file(os.path.join(proj_dir(rid), "meta.json")) or {}
    if selected_meta.get("storage_tier") == "archive":
        return False, "D 드라이브에 완료 보관된 프로젝트입니다 — Viewer에서 바로 재생할 수 있습니다"
    if rid == current:
        return True, ""
    if get_status().get("running"):
        return False, "실행 중에는 보관 프로젝트로 전환할 수 없습니다"
    if _extract_any_busy() or RAW_ARCHIVE_STATE.get("busy"):
        return False, "Raw 보관·시각화 작업이 끝난 뒤 다시 시도하세요"
    selected_cfg = os.path.join(proj_dir(rid), "case_config.json")
    if not os.path.isfile(selected_cfg):
        return False, "이 프로젝트의 case_config.json이 없어 설정을 안전하게 복원할 수 없습니다"
    try:
        old_cfg = json.load(open(selected_cfg, encoding="utf-8"))
    except Exception as e:
        return False, "프로젝트 설정 파싱 실패: " + str(e)[:80]
    ok_legacy, legacy = wsl(f"test -L {WSL_CASE}/ProjectRuns/{rid}/constant && echo LINK || true")
    if ok_legacy and "LINK" in legacy:
        cur_cfg = get_config() or {}
        if _mesh_signature(old_cfg) != _mesh_signature(cur_cfg):
            return False, "구버전 보관본의 격자 설정이 현재 케이스와 달라 자동 전환을 차단했습니다"
    cfg_wsl = win2wsl(selected_cfg)
    script = f'''set -e
cd {WSL_CASE}
CASE=$(pwd -P)
SEL="$CASE/ProjectRuns/{rid}"
CUR={_shq(current)}
CFG={_shq(cfg_wsl)}
[ -d "$SEL/processor0" ] || {{ echo 'SWITCH_ERROR=보관 processor 원본 없음'; exit 40; }}
{_resume_anchor_shell("LF", '"$SEL"')}
[ -n "$LF" ] || {{ echo 'SWITCH_ERROR=재개용 전체 상태 앵커 없음'; exit 41; }}
R="$CASE/ProjectRuns/$CUR"
[ -n "$CUR" ] || {{ echo 'SWITCH_ERROR=현재 프로젝트 ID 없음'; exit 42; }}
[ ! -e "$R/processor0" ] || {{ echo 'SWITCH_ERROR=현재 프로젝트 보관 위치 충돌'; exit 43; }}

move_state() {{
  S="$1"; D="$2"; mkdir -p "$D"
  for N in system constant 0 0.orig config.json run_overrides.json postProcessing VTK \
           .cfd_studio_runid .cfd_studio_solver_exit.json .cfd_studio_gpu_failed .cfd_studio_gpu_pcgammg_failed \
           .cfd_studio_user_stopped; do
    if [ -e "$S/$N" ] || [ -L "$S/$N" ]; then rm -rf "$D/$N"; mv "$S/$N" "$D/$N"; fi
  done
  for X in "$S"/processor[0-9]* "$S"/log.*; do
    [ -e "$X" ] || [ -L "$X" ] || continue
    N=$(basename "$X"); rm -rf "$D/$N"; mv "$X" "$D/$N"
  done
}}

# v123 이전 보관본은 constant/0이 현재 케이스 링크였다. 전환 전 실파일로 물질화한다.
if [ -L "$SEL/constant" ]; then rm -f "$SEL/constant"; cp -a constant "$SEL/constant"; fi
if [ -L "$SEL/0" ]; then rm -f "$SEL/0"; cp -a 0 "$SEL/0"; fi
[ -d "$SEL/constant" ] || cp -a constant "$SEL/constant"
[ -d "$SEL/0" ] || cp -a 0 "$SEL/0"

SWAPPED=0
rollback() {{
  [ "$SWAPPED" -eq 1 ] || return 0
  move_state "$CASE" "$SEL" || true
  move_state "$R" "$CASE" || true
}}
trap 'rollback' ERR INT TERM
move_state "$CASE" "$R"
SWAPPED=1
move_state "$SEL" "$CASE"
cp -f "$CFG" config.json
rm -f run_overrides.json
python3 tools/build_case.py >/tmp/cfd_studio_switch_build.log 2>&1
rm -rf 0; cp -a 0.orig 0
echo {rid} > .cfd_studio_runid
rm -f .cfd_studio_solver.pid .cfd_studio_allrun.pid .cfd_studio_supervisor.pid .cfd_studio_user_stopped
SWAPPED=0
trap - ERR INT TERM
echo "SWITCH_OK=$LF"
'''
    ok, out = wsl(script, timeout=180)
    if not ok or "SWITCH_OK=" not in (out or ""):
        msg = re.search(r"SWITCH_ERROR=([^\r\n]+)", out or "")
        return False, (msg.group(1) if msg else (out or "프로젝트 전환 실패")[-180:])
    _flow_invalidate()
    _STATUS_CACHE.update(t=0.0, data=None)
    try:
        open(os.path.join(FRAME_DIR, "_runid.txt"), "w").write(rid)
        meta = _read_json_file(os.path.join(proj_dir(rid), "meta.json")) or {}
        meta.pop("case_archive", None)
        meta_write(os.path.join(proj_dir(rid), "meta.json"), meta)
        if current:
            _persist_project_progress(current, None, f"ProjectRuns/{current}")
    except Exception:
        pass
    return True, re.search(r"SWITCH_OK=([^\r\n]+)", out).group(1)

def _wsl_argv(*args):
    distro = ["-d", str(SCFG["wsl_distro"])] if SCFG.get("wsl_distro") else []
    return [WSL_EXE] + distro + list(args)

def of_bash():
    """OpenFOAM bashrc — 설정값 또는 자동 탐색 (버전 무관)"""
    if _ENV["bashrc"] is None:
        v = SCFG.get("openfoam_bashrc")
        if v and v != "auto":
            _ENV["bashrc"] = f"source {v}"
        else:
            ok, out = wsl("ls -d /usr/lib/openfoam/openfoam*/etc/bashrc /opt/openfoam*/etc/bashrc 2>/dev/null | sort | tail -1")
            p = out.strip().splitlines()[-1].strip() if ok and out.strip() else ""
            if p:
                _ENV["bashrc"] = f"source {_shq(p)}"
            else:
                # 초기 조회 실패 시에도 특정 버전 경로를 추측하지 않고 실행 시 다시 탐색한다.
                _ENV["bashrc"] = (
                    'OF_BASHRC="$(ls -d /usr/lib/openfoam/openfoam*/etc/bashrc '
                    '/opt/openfoam*/etc/bashrc 2>/dev/null | sort | tail -1)"; '
                    '[ -n "$OF_BASHRC" ] || { echo "OpenFOAM 환경을 찾지 못함" >&2; exit 1; }; '
                    'source "$OF_BASHRC"'
                )
    return _ENV["bashrc"]


def _gpu_only_status(refresh=False):
    """OpenCFD feature-gpu 전용 런타임을 검증한다. CPU 폴백은 허용하지 않는다."""
    now = time.time()
    cached = GPU_ONLY_STATUS.get("data")
    if cached and not refresh and now - float(GPU_ONLY_STATUS.get("t") or 0) < 30:
        return dict(cached)
    configured = str(SCFG.get("gpu_only_bashrc", "auto") or "auto").strip()
    explicit = "" if configured.lower() == "auto" else configured
    selected_gpu = gpu_index()
    script = (
        f"EXPLICIT={_shq(explicit)}; GPU_INDEX={int(selected_gpu)}; "
        "if [ -n \"$EXPLICIT\" ]; then case \"$EXPLICIT\" in '~/'*) B=\"$HOME/${EXPLICIT#~/}\";; *) B=\"$EXPLICIT\";; esac; "
        "else for C in \"$HOME/OpenFOAM/openfoam-ecse/etc/bashrc\" \"$HOME/OpenFOAM/OpenFOAM-gpu/etc/bashrc\" "
        "\"/opt/openfoam-gpu/etc/bashrc\"; do [ -f \"$C\" ] && { B=\"$C\"; break; }; done; fi; "
        "[ -n \"${B:-}\" ] && [ -f \"$B\" ] && echo BASHRC=$B || { echo MISSING_BASHRC=1; exit 0; }; "
        "source \"$B\" WM_COMPILER=Nvidia-gpu >/dev/null 2>&1 || { echo SOURCE_FAILED=1; exit 0; }; "
        "echo WM_COMPILER=${WM_COMPILER:-}; echo WM_OPTIONS=${WM_OPTIONS:-}; "
        "NVC=$(command -v nvc++ 2>/dev/null || true); [ -n \"$NVC\" ] && echo NVCXX=$NVC || echo MISSING_NVCXX=1; "
        "SOLVER=$(command -v icoReactingMultiphaseInterFoam 2>/dev/null || true); "
        "[ -n \"$SOLVER\" ] && echo SOLVER=$SOLVER || echo MISSING_SOLVER=1; "
        "GPU_CC=$(nvidia-smi -i \"$GPU_INDEX\" --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | head -1 | tr -d ' '); "
        "GPU_UUID=$(nvidia-smi -i \"$GPU_INDEX\" --query-gpu=uuid --format=csv,noheader 2>/dev/null | head -1 | tr -d ' '); "
        "[ -n \"$GPU_CC\" ] && [ -n \"$GPU_UUID\" ] && { echo GPU_OK=1; echo GPU_CC=$GPU_CC; echo GPU_UUID=$GPU_UUID; } || echo MISSING_GPU=1; "
        "MARK=$HOME/.cfd_studio_gpu_only_ready.json; "
        "if [ -n \"$SOLVER\" ] && [ -f \"$MARK\" ] && python3 - \"$MARK\" \"$SOLVER\" \"$GPU_CC\" \"$GPU_UUID\" <<'PY'\n"
        "import json,os,sys\n"
        "try:\n"
        " d=json.load(open(sys.argv[1])); st=os.stat(sys.argv[2]); ok=bool(d.get('ready') and d.get('umpire') and d.get('case_smoke') and os.path.realpath(str(d.get('solver','')))==os.path.realpath(sys.argv[2]) and int(d.get('solver_size',-1))==st.st_size and int(d.get('solver_mtime_ns',-1))==st.st_mtime_ns and str(d.get('compute_capability',''))==sys.argv[3] and str(d.get('gpu_uuid_at_validation',''))==sys.argv[4])\n"
        "except Exception: ok=False\n"
        "raise SystemExit(0 if ok else 1)\n"
        "PY\n"
        "then echo VALIDATED=1; else echo MISSING_VALIDATION=1; fi"
    )
    ok, out = wsl(script, timeout=25)
    values = {}
    for line in (out or "").splitlines():
        if "=" in line:
            k, v = line.strip().split("=", 1)
            values[k] = v
    checks = {
        "bashrc": bool(values.get("BASHRC")),
        "compiler": bool(values.get("NVCXX")),
        "architecture": "Nvidia-gpu" in values.get("WM_COMPILER", ""),
        "solver": bool(values.get("SOLVER")),
        "gpu": values.get("GPU_OK") == "1",
        "validated": values.get("VALIDATED") == "1",
    }
    ready = bool(ok and all(checks.values()))
    if not checks["bashrc"]:
        msg = "OpenCFD feature-gpu 전용 bashrc가 없습니다"
    elif not checks["compiler"]:
        msg = "NVIDIA HPC SDK nvc++가 없습니다"
    elif not checks["architecture"]:
        msg = "OpenFOAM이 Nvidia-gpu 아키텍처로 빌드되지 않았습니다"
    elif not checks["solver"]:
        msg = "GPU 빌드 icoReactingMultiphaseInterFoam이 없습니다"
    elif not checks["gpu"]:
        msg = "WSL에서 NVIDIA GPU를 사용할 수 없습니다"
    elif not checks["validated"]:
        msg = "공식 GPU 테스트와 CFD Studio 3상 smoke 검증이 완료되지 않았습니다"
    else:
        msg = "단일 GPU 전용 실행 준비 완료"
    data = {"ready": ready, "message": msg, "checks": checks,
            "bashrc": values.get("BASHRC", ""), "solver": values.get("SOLVER", ""),
            "wm_options": values.get("WM_OPTIONS", ""), "single_gpu": True,
            "compute_capability": values.get("GPU_CC", ""),
            "gpu_uuid": values.get("GPU_UUID", ""),
            "source": "OpenCFD openfoam-ecse feature-gpu"}
    GPU_ONLY_STATUS.update(t=now, data=data)
    return dict(data)


def _run_of_bash(mode=None):
    """선택 모드와 정확히 일치하는 OpenFOAM 환경. GPU Only는 일반 빌드로 대체하지 않는다."""
    mode = mode or _solver_mode()
    if mode != "gpu_only":
        return of_bash()
    status = _gpu_only_status()
    path = str(status.get("bashrc") or "")
    if not status.get("ready") or not path:
        return "echo '[중단] GPU Only 전용 OpenCFD 환경이 준비되지 않았습니다' >&2; exit 92"
    return f"source {_shq(path)} WM_COMPILER=Nvidia-gpu"


def _run_mpi_np(mode=None):
    return 1 if (mode or _solver_mode()) == "gpu_only" else mpi_np()


def _project_compute_mode(rid):
    key = _project_key(rid)
    meta = _read_json_file(os.path.join(proj_dir(key), "meta.json")) if key else {}
    mode = str((meta or {}).get("compute_mode") or "cpu").strip().lower()
    return mode if mode in ("cpu", "gpu", "gpu_only") else "cpu"


def _resume_mode_error(rid, mode=None):
    """GPU 전용/기존 MPI 상태를 서로 재개해 분할 필드를 손상시키는 일을 막는다."""
    selected = mode or _solver_mode()
    stored = _project_compute_mode(rid)
    if (selected == "gpu_only") != (stored == "gpu_only"):
        return (f"이 프로젝트는 { _mode_public(stored)[1] }로 생성되었습니다. "
                f"{_mode_public(selected)[1]}로 바로 재개할 수 없습니다 — 같은 모드를 선택해 주세요")
    return ""

def _cpu_topology():
    if _ENV["topo"] is None:
        logical = os.cpu_count() or 1
        physical = max(1, logical // 2)
        ok, out = wsl("lscpu -p=Core,Socket 2>/dev/null | grep -v '^#' | sort -u | wc -l")
        try:
            p = int(out.strip())
            if p > 0:
                physical = p
        except Exception:
            pass
        if physical <= 0:
            physical = 1
        ok3, out3 = wsl("nproc 2>/dev/null")
        try:
            logical = max(1, int((out3.strip().splitlines()[-1] or "0").strip()) or logical)
        except Exception:
            pass
        if logical > 1 and physical > logical:
            physical = max(1, logical // 2)
        _ENV["topo"] = (logical, physical)
    return _ENV["topo"]


def cpu_pct():
    # 환경 변수 우선 적용(다른 PC 자동 배포 시 유동 조정용)
    raw = os.environ.get("CFD_STUDIO_CPU_PCT") or SCFG.get("cpu_pct")
    if isinstance(raw, str):
        raw = raw.strip().replace("%", "")
    try:
        return min(80, max(1, int(float(raw or 60))))
    except Exception:
        return 60


def cpu_set():
    """이 프로그램이 쓸 논리 CPU 집합(taskset 범위) — 총 CPU 사용률을 cpu_pct%로 강제 상한"""
    if _ENV.get("cset") is None:
        logical, _ = _cpu_topology()
        n = max(1, int(logical * cpu_pct() / 100))
        _ENV["cset"] = f"0-{n - 1}" if n > 1 else "0"
    return _ENV["cset"]


def cpu_slots():
    """총 CPU 80% 상한 안에서 실제로 배정할 논리 프로세서 수."""
    logical, _ = _cpu_topology()
    return max(1, int(logical * cpu_pct() / 100))


def extract_cpu_set():
    """솔버 밖 마지막 2개 CPU만 변환에 쓰고 나머지는 Windows에 남긴다."""
    logical, _ = _cpu_topology()
    first = max(min(max(0, cpu_slots()), max(0, logical - 1)), logical - 2)
    return f"{first}-{logical - 1}" if first < logical - 1 else str(first)


def mpi_np():
    """병렬 작업자 수 — auto면 논리 CPU의 cpu_pct%, 수동값도 같은 상한 안으로 제한."""
    if _ENV["np"] is None:
        v = os.environ.get("CFD_STUDIO_MPI_NP") or SCFG.get("mpi_np")
        if isinstance(v, str):
            v = v.strip().replace("%", "")
        if isinstance(v, (int, float)):
            _ENV["np"] = min(cpu_slots(), max(1, int(v)))
        elif isinstance(v, str) and v.lower() != "auto" and re.fullmatch(r"[1-9][0-9]*", v or ""):
            _ENV["np"] = min(cpu_slots(), max(1, int(v)))
        else:
            _ENV["np"] = cpu_slots()
    return _ENV["np"]


def _prepare_run_hardware():
    """Refresh per-machine runtime capabilities immediately before a run.

    The bundled settings are portable defaults, not a hardware fingerprint.
    Re-probe WSL and GPU state before every fresh run/resume so a copied
    project cannot inherit CPU, MPI, or GPU decisions from another PC.
    """
    _ENV.update(bashrc=None, np=None, cset=None, topo=None,
                gpu=None, gpu_info=None, gpu_devices=None)
    logical, physical = _cpu_topology()
    if logical < 1 or physical < 1:
        return False, "CPU 하드웨어를 확인하지 못했습니다"
    mode = _solver_mode()
    ok, out = wsl(
        "echo WSL_OK; command -v mpirun; command -v taskset; "
        "ls -d /usr/lib/openfoam/openfoam*/etc/bashrc "
        "/opt/openfoam*/etc/bashrc 2>/dev/null | sort | tail -1",
        timeout=20)
    lines = [x.strip() for x in (out or "").splitlines() if x.strip()]
    if not ok or "WSL_OK" not in lines:
        return False, "WSL을 실행할 수 없습니다"
    if not any(x.endswith("/mpirun") for x in lines):
        return False, "WSL에서 mpirun을 찾지 못했습니다"
    if mode != "gpu_only" and not any(x.endswith("/bashrc") for x in lines):
        return False, "OpenFOAM 환경을 찾지 못했습니다"
    devices = gpu_devices(refresh=True)
    if mode == "gpu_only":
        gpu_only = _gpu_only_status(refresh=True)
        if not gpu_only.get("ready"):
            return False, "GPU Only 준비 안 됨: " + str(gpu_only.get("message") or "전용 환경 확인 실패")
    np_now, slots_now = _run_mpi_np(mode), cpu_slots()
    print(f"[CFD Studio] 하드웨어 재감지: 논리 CPU {logical} · 물리 코어 {physical} · "
          f"MPI {np_now}/{slots_now} · GPU {len(devices)}개 · "
          f"선택 GPU {gpu_index()} · {_mode_public(mode)[1]}")
    return True, ""


def gpu_devices(refresh=False):
    """현재 PC에서 인식한 NVIDIA GPU 목록. 설정 창과 자동 선택이 같은 목록을 쓴다."""
    if _ENV.get("gpu_devices") is not None and not refresh:
        return list(_ENV["gpu_devices"])
    flags = 0x08000000 if os.name == "nt" else 0
    found = []
    try:
        if not NVIDIA_SMI:
            raise FileNotFoundError("nvidia-smi")
        r = subprocess.run([NVIDIA_SMI, "--query-gpu=index,name,memory.total,clocks.max.graphics",
                            "--format=csv,noheader,nounits"], capture_output=True, timeout=8,
                           creationflags=flags)
        for line in r.stdout.decode("utf-8", "replace").splitlines():
            q = [x.strip() for x in line.split(",")]
            if len(q) < 4: continue
            try:
                i, mem, clk = int(q[0]), float(q[2]), float(q[3])
                found.append({"index": i, "name": q[1], "memory_mib": int(mem),
                              "max_clock_mhz": int(clk), "score": mem * clk})
            except Exception: pass
    except Exception:
        pass
    _ENV["gpu_devices"] = found
    return list(found)

def gpu_index():
    """CUDA 보조 기능용 GPU. auto는 VRAM×최대 클럭 점수가 큰 장치, 동률이면 낮은 번호."""
    if _ENV.get("gpu") is not None:
        return _ENV["gpu"]
    raw = os.environ.get("CFD_STUDIO_GPU_INDEX")
    if raw is None:
        raw = SCFG.get("gpu_index", "auto")
    found = gpu_devices()
    if str(raw).strip().lower() != "auto":
        try: requested = max(0, int(raw))
        except Exception: requested = 0
        selected = next((g for g in found if g["index"] == requested), None)
        if not selected and found:
            selected = sorted(found, key=lambda g: g["index"])[0]
        _ENV["gpu"] = int(selected["index"]) if selected else requested
        _ENV["gpu_info"] = {"mode": "manual", "index": _ENV["gpu"],
                            "name": (selected or {}).get("name", "선택 GPU")}
        return _ENV["gpu"]
    best = sorted(found, key=lambda g: (-g["score"], g["index"]))[0] if found else None
    _ENV["gpu"] = int(best["index"]) if best else 0
    _ENV["gpu_info"] = {"mode": "auto", "index": _ENV["gpu"],
                        "name": best["name"] if best else "기본 GPU",
                        "detected": len(found)}
    return _ENV["gpu"]

STATE = {"eta": [], "autosync": False}
EXTRACT_STATES = {}
EXTRACT_LOCKS = {}
RAW_IO_LOCKS = {}
PROJECT_ARCHIVE_LK = threading.Lock()
PROJECT_ARCHIVE_STATE = {"busy": False, "rid": "", "msg": ""}
EXTRACT_REGISTRY_LK = threading.RLock()
AUTOSYNC_EV = threading.Event()   # 자동 동기화 즉시 1회 실행 신호 (켤 때)
_STATUS_LK = threading.Lock()
_STATUS_CACHE = {"t": 0.0, "data": None}

def _extract_key(rid=None):
    return _project_key(rid) or _active_rid() or "__active__"

def _extract_state(rid=None):
    key = _extract_key(rid)
    with EXTRACT_REGISTRY_LK:
        return EXTRACT_STATES.setdefault(key, {"rid": "" if key == "__active__" else key,
            "busy": False, "done": 0, "processed": 0, "total": 0,
            "backfill": 0, "reused": 0, "remaining": 0,
            "failed": 0, "last_error": "", "already_complete": False, "msg": ""})

def _extract_lock(rid=None):
    key = _extract_key(rid)
    with EXTRACT_REGISTRY_LK:
        return EXTRACT_LOCKS.setdefault(key, threading.Lock())

def _raw_io_lock(rid=None):
    key = _extract_key(rid)
    with EXTRACT_REGISTRY_LK:
        return RAW_IO_LOCKS.setdefault(key, threading.Lock())

def _extract_public(rid=None):
    return dict(_extract_state(rid))

def _extract_any_busy():
    with EXTRACT_REGISTRY_LK:
        return any(bool(s.get("busy")) for s in EXTRACT_STATES.values())

def _verify_tree_copy(source, target):
    """원본의 모든 일반 파일이 대상에 같은 크기로 존재하는지 확인한다."""
    for base, dirs, files in os.walk(source):
        dirs[:] = [name for name in dirs if not os.path.islink(os.path.join(base, name))]
        rel = os.path.relpath(base, source)
        dst_base = target if rel == "." else os.path.join(target, rel)
        for name in files:
            src = os.path.join(base, name)
            dst = os.path.join(dst_base, name)
            if os.path.islink(src):
                continue
            try:
                if not os.path.isfile(dst) or os.path.getsize(src) != os.path.getsize(dst):
                    return False, os.path.relpath(src, source)
            except OSError:
                return False, os.path.relpath(src, source)
    return True, ""

def _offload_case_state(rid, project_target):
    """WSL의 프로젝트 계산 상태를 D의 Raw_Data/Case_State로 옮기고 읽기 링크만 남긴다."""
    key = _project_key(rid)
    if not key:
        return False, "실행 ID 없음"
    active = key == _active_rid()
    case = _wsl_case_token()
    destination = win2wsl(os.path.join(project_target, "Raw_Data", "Case_State"))
    if active:
        # 현재 케이스에는 다음 실행에서도 쓰는 tools/ProjectRuns가 함께 있으므로
        # 프로젝트 소유 항목만 옮긴 뒤 같은 위치에 링크를 되돌려 놓는다.
        script = f'''set -eu
CASE={case}; cd "$CASE"; CASE=$(pwd -P)
DST={_shq(destination)}; mkdir -p "$DST"
move_one() {{
  S="$1"; [ -e "$S" ] || [ -L "$S" ] || return 0
  N=$(basename "$S"); T="$DST/$N"
  if [ -L "$S" ] && [ "$(readlink -f "$S" 2>/dev/null || true)" = "$(readlink -f "$T" 2>/dev/null || true)" ]; then return 0; fi
  rsync -a --remove-source-files "$S" "$DST/" || exit 51
  [ -d "$S" ] && find "$S" -depth -type d -empty -delete 2>/dev/null || true
  [ ! -e "$S" ] && [ ! -L "$S" ] || {{ echo "ARCHIVE_LEFT=$N"; exit 52; }}
  ln -s "$T" "$S"
}}
for N in system constant 0 0.orig config.json run_overrides.json postProcessing VTK \
 .cfd_studio_runid .cfd_studio_solver_exit.json .cfd_studio_gpu_failed \
 .cfd_studio_gpu_pcgammg_failed .cfd_studio_user_stopped; do move_one "$CASE/$N"; done
for S in "$CASE"/processor[0-9]* "$CASE"/log.*; do move_one "$S"; done
for S in "$CASE"/*; do N=$(basename "$S"); [ "$N" = 0 ] && continue; \
 echo "$N" | grep -Eq '^[0-9]+([.][0-9]+)?$' && move_one "$S" || true; done
echo ARCHIVE_OK=1'''
    else:
        script = f'''set -eu
CASE={case}; cd "$CASE"; CASE=$(pwd -P)
SRC="$CASE/ProjectRuns/{key}"; DST={_shq(destination)}
if [ -L "$SRC" ] && [ "$(readlink -f "$SRC" 2>/dev/null || true)" = "$(readlink -f "$DST" 2>/dev/null || true)" ]; then echo ARCHIVE_OK=1; exit 0; fi
[ -d "$SRC" ] || {{ [ -d "$DST" ] && echo ARCHIVE_OK=1 || echo ARCHIVE_MISSING=1; exit 0; }}
mkdir -p "$DST"
rsync -a --remove-source-files "$SRC/" "$DST/" || exit 53
find "$SRC" -depth -type d -empty -delete 2>/dev/null || true
[ ! -e "$SRC" ] && [ ! -L "$SRC" ] || {{ echo ARCHIVE_LEFT=ProjectRuns/{key}; exit 54; }}
ln -s "$DST" "$SRC"
echo ARCHIVE_OK=1'''
    ok, out = wsl(script, timeout=86400)
    return bool(ok and "ARCHIVE_OK=1" in (out or "")), (out or "")[-240:]

def archive_project(rid, force=False):
    """완료 프로젝트 전체를 선택한 보관 드라이브로 이관한다.

    대상에 먼저 복사하고 크기를 검증한 뒤 원본을 지운다. 중간 실패 시에는
    C 원본과 D의 재개 가능한 부분 복사본을 모두 남겨 데이터 손실을 막는다.
    """
    key = _project_key(rid)
    if not key or not PROJECT_ARCHIVE_LK.acquire(blocking=False):
        return False, "다른 프로젝트 이관 작업이 진행 중입니다"
    raw_lock = _raw_io_lock(key)
    raw_acquired = False
    try:
        PROJECT_ARCHIVE_STATE.update(busy=True, rid=key, msg="이관 준비")
        if key == _active_rid() and get_status().get("running"):
            return False, "실행 중인 프로젝트는 이관하지 않습니다"
        if _extract_state(key).get("busy"):
            return False, "시각화·Raw 작업이 끝난 뒤 이관합니다"
        raw_acquired = raw_lock.acquire(timeout=900)
        if not raw_acquired:
            return False, "시각화·Raw 작업이 끝난 뒤 이관합니다"
        source = proj_dir(key)
        meta = _read_json_file(os.path.join(source, "meta.json")) or {}
        if meta.get("execution_project_id"):
            return False, "프로젝트 지정 폴더에 저장됨"
        if not force and not meta.get("completed"):
            return False, "완료 전 프로젝트"
        root = _archive_project_root()
        ok_root, _, msg_root = _validate_raw_archive_dir(_raw_archive_dir())
        if not ok_root or not root:
            return False, msg_root
        os.makedirs(root, exist_ok=True)
        target = os.path.join(root, os.path.basename(os.path.normpath(source)))
        os.makedirs(target, exist_ok=True)
        PROJECT_ARCHIVE_STATE["msg"] = "WSL 계산 상태 이관 중"
        ok_case, msg_case = _offload_case_state(key, target)
        if not ok_case:
            return False, "WSL 계산 상태 이관 실패: " + msg_case
        if os.path.normcase(os.path.abspath(source)) != os.path.normcase(os.path.abspath(target)):
            PROJECT_ARCHIVE_STATE["msg"] = "시각화·설정 이관 중"
            shutil.copytree(source, target, dirs_exist_ok=True, copy_function=shutil.copy2)
            copied, missing = _verify_tree_copy(source, target)
            if not copied:
                return False, "복사 검증 실패: " + missing
        target_meta_path = os.path.join(target, "meta.json")
        archived_meta = _read_json_file(target_meta_path) or meta
        archived_meta.update(storage_tier="archive", archived_at=time.time(),
                             archive_root=_raw_archive_dir(), archive_path=target)
        archived_meta["raw_archive_root"] = _raw_archive_dir()
        archived_meta["raw_archive_run"] = os.path.join(target, "Raw_Data")
        meta_write(target_meta_path, archived_meta)
        if os.path.normcase(os.path.abspath(source)) != os.path.normcase(os.path.abspath(target)):
            shutil.rmtree(source)
        _flow_invalidate(source)
        PROJECT_ARCHIVE_STATE["msg"] = "D 드라이브 이관 완료"
        return True, target
    except Exception as e:
        return False, str(e)[:200]
    finally:
        if raw_acquired:
            raw_lock.release()
        PROJECT_ARCHIVE_STATE.update(busy=False, rid="")
        PROJECT_ARCHIVE_LK.release()

def completed_project_archive_loop():
    """완료 프로젝트를 순차 이관한다. 실행·변환·Raw 쓰기와 겹치지 않는다."""
    time.sleep(30)
    while True:
        if SCFG.get("archive_completed_projects", True) and not RAW_ARCHIVE_STATE.get("busy"):
            for project in list_projects():
                if (project.get("rid") and project.get("completed") and not project.get("archived")
                        and not _extract_state(project["rid"]).get("busy")):
                    archive_project(project["rid"])
                    break
        time.sleep(60)

# ---------------------------------------------------------------- WSL 유틸
def wsl(cmd, timeout=25):
    """WSL에서 bash 스크립트 실행 → (ok, stdout).
    스크립트를 인자가 아니라 **표준입력**으로 전달 — wsl.exe 버전에 따라 여러 줄
    인자가 공백으로 합쳐지며 변수 대입이 증발하는 문제(진단 P=// 증상)를 원천 차단."""
    try:
        argv = _wsl_argv("bash", "-ls")
        r = subprocess.run(argv, input=cmd.encode(), capture_output=True, timeout=timeout,
                           creationflags=0x08000000 if os.name == "nt" else 0)
        # 종료코드와 stderr 를 반영한다 — 예전에는 wsl.exe 가 존재하기만 하면 ok=True 라서
        # 배포판이 망가져도 화면에 '연결됨'(초록불)이 떴다 (2026-08-15 감사)
        out = r.stdout.decode("utf-8", "replace")
        if r.returncode != 0:
            return False, out + "\n[wsl stderr] " + r.stderr.decode("utf-8", "replace")[:400]
        return True, out
    except Exception as e:
        return False, str(e)

def win2wsl(p):
    p = os.path.abspath(p)
    if len(p) > 2 and p[1] == ":":
        if WSL_EXE:
            try:
                ok, out = wsl(f"wslpath -a -u {_shq(p)}", timeout=6)
                if ok:
                    q = out.strip().splitlines()[-1].strip().replace("\\", "/")
                    if q:
                        return q
            except Exception:
                pass
        drive, rest = p[0].lower(), p[2:].replace("\\", "/")
        return f"/mnt/{drive}{rest}"
    return p.replace("\\", "/")                      # 이미 POSIX 경로면 그대로

def open_console(inner_bash):
    """보이는 명령 프롬프트 창에서 WSL 스크립트 실행 (실행 상황 라이브 표시).
    스크립트를 파일로 저장하고 콘솔은 그 파일만 실행 — cmd.exe가 따옴표/리다이렉트(>)를
    자기 문법으로 해석해 명령이 통째로 깨지던 문제(콘솔이 빈 프롬프트만 남던 증상)를 원천 차단."""
    sh = os.path.join(RUNTIME_DIR, "console_run.sh")
    gsel = gpu_index()
    solver_mode = _solver_mode()
    with open(sh, "w", encoding="utf-8", newline="\n") as f:
        f.write("#!/bin/bash\necho '[CFD Studio] 시작'\n"
                # GPU 계산(AmgX 등 CUDA)이 있을 때 자동 선정 GPU 사용. 기본 OpenFOAM 솔버 계산은 CPU 기반.
                f"export CUDA_VISIBLE_DEVICES={gsel}\n"
                f"export CFD_STUDIO_PRESSURE_SOLVER_MODE={solver_mode}\n"
                f"export CFD_STUDIO_COMPUTE_MODE={solver_mode}\n"
                + ("export FOAM_MEMORY_POOL='managed; size=1024; incr=1024'\n" if solver_mode == "gpu_only" else "") +
                # Open MPI may count only physical-core slots on one PC and
                # hardware threads on another. The actual rank count is
                # already capped from a fresh WSL probe; this removes the
                # machine-specific slot interpretation from both run paths.
                "export OMPI_MCA_rmaps_base_oversubscribe=1\n"
                # Windows TEMP가 /mnt/c로 전달되면 Open MPI FIFO 생성이 errno 95로 실패한다.
                "export TMPDIR=/tmp TMP=/tmp TEMP=/tmp\n"
                # 사용자가 AmgX/PETSc를 설치한 PC에서는 기존 GPU 압력솔버 환경을 그대로 활성화한다.
                # 파일이 없으면 CPU 솔버 경로에 아무 영향 없이 통과한다.
                + ("" if solver_mode == "gpu_only" else
                   "[ -f \"$HOME/.of_gpu_env\" ] && source \"$HOME/.of_gpu_env\" || true\n") +
                # CPU 총량 상한 — 이 셸(과 모든 자식: Allrun·mpirun·솔버)을 논리 CPU의 {cpu_pct()}% 집합에 고정
                f"command -v taskset >/dev/null 2>&1 && taskset -pc {cpu_set()} $$ >/dev/null 2>&1; true\n"
                + inner_bash + "\n")
    body = open(sh, encoding="utf-8").read()
    run_path = None
    try:   # 1순위: 스크립트 내용을 WSL 안 고정 경로로 직접 전달 (명령줄에 한글·공백 경로가 없음)
        r = subprocess.run(_wsl_argv("bash", "-lc",
                            "tmp=/tmp/cfd_studio_run.sh; cat > \"$tmp\" && chmod +x \"$tmp\" && echo OK"),
                           input=body.encode(), capture_output=True, timeout=20,
                           creationflags=0x08000000 if os.name == "nt" else 0)
        if b"OK" in r.stdout: run_path = "/tmp/cfd_studio_run.sh"
    except Exception:
        pass
    if not run_path:                     # 2순위: 마운트 경로 직접 실행
        run_path = _shq(win2wsl(sh))
    wsl_cmd = subprocess.list2cmdline(_wsl_argv("bash", "-lc", f"bash {run_path}"))
    ok_check = subprocess.run(_wsl_argv("bash", "-lc", f"test -f {run_path} && echo OK"),
                              capture_output=True, timeout=8, creationflags=0x08000000 if os.name == "nt" else 0)
    if b"OK" not in (ok_check.stdout or b""):
        return False
    p = subprocess.Popen(f"start \"CFD 실행 - 닫으면 tail만 끊기고 계산은 계속됨\" cmd /k {wsl_cmd}", shell=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return p is not None

def _resume_supervisor_launch():
    """콘솔·Studio와 독립된 재개 감독 프로세스를 만들고 실행하는 셸 조각."""
    script = r'''#!/bin/bash
set -u
cd "$(dirname "$0")" || exit 90
export TMPDIR=/tmp TMP=/tmp TEMP=/tmp
LOGF=log.restart
MAX_TRIES=3
TRY=0
RUN_ID=$(cat .cfd_studio_runid 2>/dev/null | tr -cd '0-9')
NPD=${1:-1}
SOLVER=$(foamDictionary -entry application -value system/controlDict 2>/dev/null)
case "$SOLVER" in icoReactingMultiphaseInterFoam|simpleFoam|pimpleFoam) ;; *) echo '[감독] 지원하지 않는 솔버' >> "$LOGF"; exit 91;; esac
clear_overlap(){
  ANCHOR=$1
  STAMP=$(date +%Y%m%d_%H%M%S)
  HOLD="Trash/restart_overlap_${RUN_ID}_${STAMP}"
  TIMES=$(for D in processor0/[0-9]*; do basename "$D"; done 2>/dev/null | \
    awk -v a="$ANCHOR" '$1 ~ /^[0-9]+([.][0-9]+)?$/ && $1>a {print}' | sort -g)
  [ -n "$TIMES" ] || return 0
  for T in $TIMES; do
    # 외부 Raw 링크는 링크만 지우면 재계산본 보관 시 같은 시각 폴더와 충돌한다.
    # 기존 외부 시각 전체를 같은 드라이브의 숨김 보존 폴더로 먼저 옮긴다.
    if [ -L "processor0/$T" ]; then
      TARGET=$(readlink -f "processor0/$T" 2>/dev/null || true)
      FINAL=$(dirname "$TARGET")
      if [ -n "$TARGET" ] && [ "$(basename "$FINAL")" = "$T" ] && [ -d "$FINAL" ]; then
        EXT_HOLD="$(dirname "$FINAL")/.restart_overlap_${RUN_ID}_${STAMP}"
        mkdir -p "$EXT_HOLD" && mv "$FINAL" "$EXT_HOLD/$T" || {
          echo "[감독] 외부 Raw 롤백 보존 실패 · ${T}s" >> "$LOGF"; return 1;
        }
      fi
    fi
    for P in processor[0-9]*; do
      D="$P/$T"
      if [ -L "$D" ]; then
        rm -f "$D"
      elif [ -d "$D" ]; then
        mkdir -p "$HOLD/$P"
        mv "$D" "$HOLD/$P/"
      fi
    done
  done
  echo "[감독] 재개 앵커 이후 중복 출력 정리 · ${ANCHOR}s 이후 $(echo "$TIMES" | wc -w)개 시각" >> "$LOGF"
}
finish_record(){
  RC=$1
  LAST=$(tail -c 524288 "$LOGF" 2>/dev/null | awk '/^Time = /{t=$3} END{print t+0}')
  STAMP=$(date -Is)
  TMP=.cfd_studio_solver_exit.json.tmp
  printf '{"run_id":"%s","exit_code":%s,"attempt":%s,"last_time":%s,"ended_at":"%s"}\n' \
    "$RUN_ID" "$RC" "$TRY" "${LAST:-0}" "$STAMP" > "$TMP"
  mv -f "$TMP" .cfd_studio_solver_exit.json
}
while [ "$TRY" -lt "$MAX_TRIES" ]; do
  [ ! -f .cfd_studio_user_stopped ] || { echo '[감독] 사용자 중단 확인' >> "$LOGF"; break; }
  TRY=$((TRY+1))
  if [ "$TRY" -gt 1 ]; then
    LF=$(for B in $(for D in processor0/[0-9]*; do basename "$D"; done 2>/dev/null | \
      grep -E '^[0-9]+([.][0-9]+)?$' | sort -gr); do
      OK=1
      for P in processor[0-9]*; do
        FIELDS="p_rgh T U alpha.vapour alpha.liquid alpha.water"
        [ "$SOLVER" = icoReactingMultiphaseInterFoam ] || FIELDS="p U k epsilon"
        for F in $FIELDS; do
          [ -s "$P/$B/$F" ] || { OK=0; break 2; }
        done
      done
      [ "$OK" -eq 1 ] && { echo "$B"; break; }
    done)
    [ -n "$LF" ] || { echo '[감독] 재시도 가능한 전체 상태 앵커 없음' >> "$LOGF"; break; }
    foamDictionary -entry startFrom -set startTime system/controlDict >/dev/null 2>&1 || break
    foamDictionary -entry startTime -set "$LF" system/controlDict >/dev/null 2>&1 || break
    clear_overlap "$LF"
    echo "[감독] 비정상 종료 후 자동 재개 $TRY/$MAX_TRIES · ${LF}s" >> "$LOGF"
  else
    echo "[감독] 독립 실행 시작 · MPI ${NPD}개" >> "$LOGF"
  fi
  nice -n 8 mpirun --oversubscribe -np "$NPD" "$SOLVER" -parallel >> "$LOGF" 2>&1 &
  SOLVER_PID=$!
  echo "$SOLVER_PID" > .cfd_studio_solver.pid
  wait "$SOLVER_PID"
  RC=$?
  finish_record "$RC"
  rm -f .cfd_studio_solver.pid
  [ "$RC" -ne 0 ] || { echo '[감독] 계산 정상 종료' >> "$LOGF"; break; }
  [ ! -f .cfd_studio_user_stopped ] || { echo '[감독] 사용자 중단으로 재시도하지 않음' >> "$LOGF"; break; }
  if [ "${CFD_STUDIO_COMPUTE_MODE:-cpu}" = gpu_only ] && \
     grep -qE 'cudaError|Thrust failure|parallel_for: failed|illegal memory access' "$LOGF" 2>/dev/null; then
    touch .cfd_studio_gpu_only_failed .cfd_studio_user_stopped
    echo '[감독] GPU Only 오류 감지 · CPU 전환 없이 자동 재개 차단' >> "$LOGF"
    break
  fi
  if [ "$TRY" -lt "$MAX_TRIES" ]; then
    echo "[감독] 종료 코드 ${RC} · 60초 후 재시도" >> "$LOGF"
    sleep 60
  fi
done
rm -f .cfd_studio_supervisor.pid
'''
    payload = base64.b64encode(script.encode("utf-8")).decode("ascii")
    return (
        f"printf '%s' {_shq(payload)} | base64 -d > .cfd_studio_solver_supervisor.sh; "
        "chmod +x .cfd_studio_solver_supervisor.sh; "
        "rm -f .cfd_studio_solver_exit.json; "
        "nohup setsid bash ./.cfd_studio_solver_supervisor.sh \"$NPD\" "
        "> log.supervisor 2>&1 < /dev/null & SUPERVISOR_PID=$!; "
        "echo \"$SUPERVISOR_PID\" > .cfd_studio_supervisor.pid; "
        "sleep 1; kill -0 \"$SUPERVISOR_PID\" 2>/dev/null || "
        "{ echo '[중단] 솔버 감독 프로세스 시작 실패'; exit 1; }; "
    )

def _resume_overlap_cleanup():
    """앵커 이후 과거 출력 링크를 해제해 재개 솔버가 외부 Raw에 직접 쓰지 않게 한다."""
    return (
        "STAMP=$(date +%Y%m%d_%H%M%S); HOLD=Trash/restart_overlap_$(cat .cfd_studio_runid 2>/dev/null)_$STAMP; "
        "OVER=$(for D in processor0/[0-9]*; do basename \"$D\"; done 2>/dev/null | "
        "awk -v a=\"${LF:-0}\" '$1 ~ /^[0-9]+([.][0-9]+)?$/ && $1>a {print}' | sort -g); "
        "if [ -n \"$OVER\" ]; then for T in $OVER; do "
        "if [ -L \"processor0/$T\" ]; then TARGET=$(readlink -f \"processor0/$T\" 2>/dev/null || true); "
        "FINAL=$(dirname \"$TARGET\"); if [ -n \"$TARGET\" ] && [ \"$(basename \"$FINAL\")\" = \"$T\" ] && [ -d \"$FINAL\" ]; then "
        "EXT_HOLD=$(dirname \"$FINAL\")/.restart_overlap_$(cat .cfd_studio_runid 2>/dev/null)_$STAMP; "
        "mkdir -p \"$EXT_HOLD\" && mv \"$FINAL\" \"$EXT_HOLD/$T\" || { echo '[중단] 외부 Raw 롤백 보존 실패'; exit 44; }; fi; fi; "
        "for P in processor[0-9]*; do D=\"$P/$T\"; "
        "if [ -L \"$D\" ]; then rm -f \"$D\"; elif [ -d \"$D\" ]; then mkdir -p \"$HOLD/$P\"; mv \"$D\" \"$HOLD/$P/\"; fi; "
        "done; done; echo \"[CFD Studio 재개] 앵커 이후 중복 출력 $(echo \"$OVER\" | wc -w)개 시각 정리\" >> log.restart; fi; "
    )

def build_resume_inner(r_end=None, tail=True, user_requested=True):
    """중단 지점 재개 스크립트. tail=False면 콘솔 없이 백그라운드 실행용(자동 재개)."""
    scope = _scope_case_process_snip()
    solver_mode = _solver_mode()
    s = (f"echo '[CFD Studio] 이어서 실행 - 설정 변경 없음, 저장된 상태 그대로 재개'; "
         f"{_run_of_bash(solver_mode)}; export CUDA_VISIBLE_DEVICES={gpu_index()}; "
         f"export CFD_STUDIO_PRESSURE_SOLVER_MODE={solver_mode}; export CFD_STUDIO_COMPUTE_MODE={solver_mode}; "
         + ("export FOAM_MEMORY_POOL='managed; size=1024; incr=1024'; " if solver_mode == "gpu_only" else "") +
         f"cd {WSL_CASE} || {{ echo 케이스 폴더 없음: {WSL_CASE}; " + ("exec bash" if tail else "exit 1") + f"; }}; "
         f"RID=$(cat .cfd_studio_runid 2>/dev/null); "
         + (f"REQ_END={r_end:g}; CUR_END=$(foamDictionary -entry endTime -value system/controlDict 2>/dev/null); "
            f"EXTEND=$(awk -v n=\"$REQ_END\" -v o=\"${{CUR_END:-0}}\" 'BEGIN{{print (n>o)?1:0}}'); " if r_end else
            "EXTEND=0; ") +
         f"if [ -s .cfd_studio_solver_exit.json ] && grep -q '\"run_id\":\"'$RID'\"' .cfd_studio_solver_exit.json "
         f"&& grep -q '\"exit_code\":0' .cfd_studio_solver_exit.json && [ \"$EXTEND\" -ne 1 ]; then "
         f"echo '[안내] 이 프로젝트는 정상 종료되어 재개할 필요가 없습니다'; " + ("exec bash" if tail else "exit 0") + f"; fi; "
         f"APP=$(foamDictionary -entry application -value system/controlDict 2>/dev/null); "
         f"case \"$APP\" in icoReactingMultiphaseInterFoam|simpleFoam|pimpleFoam) ;; *) echo '[중단] 지원하지 않는 솔버'; " + ("exec bash" if tail else "exit 1") + f";; esac; "
         f"LOG_DONE=$(ls -t \"log.$APP\" log.restart 2>/dev/null | head -1); "
         f"if [ -n \"$LOG_DONE\" ] && grep -q 'solution converged in' \"$LOG_DONE\"; then "
         f"echo '[안내] 이 프로젝트는 수렴 기준으로 정상 완료되어 재개할 필요가 없습니다'; " + ("exec bash" if tail else "exit 0") + f"; fi; "
         + ("rm -f .cfd_studio_user_stopped; " if user_requested else
            "if [ -f .cfd_studio_user_stopped ]; then echo '[CFD Studio] 사용자 중단 상태 — 자동 재개 취소'; exit 0; fi; ") +
         # 중단 후 재개 직전에 설치 상태를 확인해 p_rgh만 공식 PETSc CUDA PCGAMG 경로로 전환한다.
         # 실행 중 fvSolution은 절대 건드리지 않으며, 미완성 GPU 설치는 계산을 시작하지 않는다.
         f"if [ \"$APP\" = icoReactingMultiphaseInterFoam ]; then python3 tools/select_pressure_solver.py || {{ echo '[중단] 압력 솔버 설정 실패'; " + ("exec bash" if tail else "exit 1") + f"; }}; fi; "
         # vizFields.objects는 시작 시 선택한 출력 필드를 그대로 유지한다.
         # 재개가 임의로 4개 필드를 다시 켜면 프로젝트 선택과 저장 용량이 달라진다.
         f"{scope} "
         f"P1=0; for p in $(cat .cfd_studio_solver.pid .cfd_studio_supervisor.pid 2>/dev/null || true); do in_case_pid \"$p\" && P1=$((P1+1)); done; "
         f"P3=0; for p in $(pgrep -f \"$APP\" 2>/dev/null || true); do EXE=$(readlink /proc/$p/exe 2>/dev/null || true); [ \"${{EXE##*/}}\" = \"$APP\" ] && in_case_pid \"$p\" && P3=$((P3+1)); done; "
         f"if [ \"$P1\" -gt 0 ] || [ \"$P3\" -gt 0 ]; then "
         f"if [ \"$P1\" -gt 0 ]; then echo '[CFD Studio 재개] 기존 solver PID 유효성 확인 완료'; fi; "
         f"echo '이미 실행 중 - 현재 로그에 연결합니다'; "
         f"else "
         f"[ ! -s .cfd_studio_solver.pid ] || rm -f .cfd_studio_solver.pid; "
         + _resume_anchor_shell("LF", ".") +
         f"NT=$(ls processor0 2>/dev/null | grep -cE '^[0-9]'); "
         f"if [ -z \"$LF\" ]; then "
         f"echo '[중단] 0초 초기 상태까지 손상되어 안전하게 재개할 수 없습니다.'; " + ("exec bash" if tail else "exit 1") + f"; fi; "
         + (f"foamDictionary -entry endTime -set {r_end:g} system/controlDict >/dev/null 2>&1; "
            f"echo '[CFD Studio 재개] 이 프로젝트의 종료 시각 {r_end:g}s 복원'; " if r_end else "") +
         f"ET=$(foamDictionary -entry endTime -value system/controlDict 2>/dev/null); "
         f"awk -v a=\"${{LF:-0}}\" -v b=\"${{ET:-0}}\" 'BEGIN{{exit !(a>=b)}}' && "
         f"{{ echo \"[안내] 이미 종료 시각(${{ET}}s)까지 완주 - [리셋] 또는 [새 프로젝트]\"; " + ("exec bash" if tail else "exit 0") + f"; }}; "
         f"LATEST=$(for D in processor0/[0-9]*; do basename \"$D\"; done 2>/dev/null | grep -E '^[0-9]+([.][0-9]+)?$' | sort -g | tail -1); "
         f"echo \"[CFD Studio 재개] 복구 앵커: ${{LF}}s · 최신 부분 저장: ${{LATEST:-없음}}s · 후보 폴더 $NT개\" > log.restart; "
         f"awk -v a=\"$LF\" -v b=\"${{LATEST:-$LF}}\" 'BEGIN{{if(b>a) printf \"[CFD Studio 재개] 최근 %.6gs 구간은 불완전하여 직전 전체 저장으로 롤백\\n\", b-a}}' >> log.restart; "
         f"foamDictionary -entry startFrom -set startTime system/controlDict >>log.restart 2>&1; "
         f"foamDictionary -entry startTime -set ${{LF:-0}} system/controlDict >>log.restart 2>&1; "
         f"echo \"[CFD Studio 재개] controlDict: startFrom=$(foamDictionary -entry startFrom -value system/controlDict 2>/dev/null) startTime=$(foamDictionary -entry startTime -value system/controlDict 2>/dev/null) endTime=${{ET}}\" >> log.restart; "
         + _resume_overlap_cleanup() +
         f"echo \"재개 시각: ${{LF}}s (모든 MPI 파티션 검증 완료)\"; "
         f"NPD=$(ls -d processor[0-9]* 2>/dev/null | wc -l); "
         f"command -v taskset >/dev/null 2>&1 && taskset -pc {cpu_set()} $$ >/dev/null 2>&1; "
         # The fresh-run path already permits the configured logical-thread
         # count. Resume must do the same or Open MPI rejects 25 ranks on a
         # host that advertises only physical-core slots.
         + _resume_supervisor_launch() +
         f"fi; ")
    if tail:
        s += (f"sleep 3; LOGF=$(ls -t log.restart \"log.$APP\" 2>/dev/null | head -1); "
              f"echo 로그 연결: $LOGF; tail -n 40 -f $LOGF")
    else:
        s += "sleep 2; echo '[CFD Studio] 자동 재개 시도 완료'"
    return s

def _auto_resume_fire(r_end=None):
    """콘솔 창 없이 재개 (자동 재개 전용)"""
    body = "#!/bin/bash\n# CFD_STUDIO_AUTO_RESUME_MARKER=1\n" + build_resume_inner(r_end, tail=False, user_requested=False) + "\n"
    try:
        mk = subprocess.run(_wsl_argv("bash", "-lc", "tmp=$(mktemp /tmp/cfd_auto_resume.XXXXXX.sh); cat > \"$tmp\"; chmod +x \"$tmp\"; echo \"$tmp\""),
                           input=body.encode(), capture_output=True, timeout=20,
                           creationflags=0x08000000 if os.name == "nt" else 0)
        if mk.returncode != 0:
            return False
        tmp = mk.stdout.decode("utf-8", "replace").strip().splitlines()[-1] if mk.stdout else ""
        if not tmp:
            return False
        ok, out = wsl(f"grep -q 'CFD_STUDIO_AUTO_RESUME_MARKER=1' {tmp} && nohup setsid bash {tmp} >> /tmp/cfd_auto_resume.log 2>&1 < /dev/null & echo FIRED", timeout=30)
        if not (ok and "FIRED" in out):
            return False
        ok2, out2 = wsl(f"test -f {tmp} && echo OK")
        ok3, out3 = wsl(f"test -x {tmp} && test -s {tmp} && echo OK")
        return ok2 and ok3 and "OK" in out2 and "OK" in out3
    except Exception:
        return False

def resume_loop():
    """중단된 계산 자동 이어서 실행 — 사용자가 [중단]을 누른 경우는 제외."""
    time.sleep(90)
    while True:
        try:
            managed = any(c.get("result_key") == "legacy:"+_active_rid() for c in EXECUTION_WORKSPACE.queue_data()["cases"].values())
            if SCFG.get("auto_resume", True) and not STATE.get("user_stopped") and not managed:
                # GPU 라이브러리 실패를 단순한 비정상 종료로 보고 같은 PCGAMG 경로를
                # 반복 실행하지 않는다. 원본 결과는 보존하고 다음 수동 실행을 CPU로 전환한다.
                only_gpu = _solver_mode() == "gpu_only"
                gpu_check = (
                    f"cd {WSL_CASE} 2>/dev/null || exit 0; "
                    "L=$(ls -t log.restart log.icoReactingMultiphaseInterFoam 2>/dev/null | head -1); "
                    + ("if [ ! -f .cfd_studio_gpu_only_failed ] && [ -n \"$L\" ] && " if only_gpu else
                       "if [ ! -f .cfd_studio_gpu_pcgammg_failed ] && [ -n \"$L\" ] && ") +
                    "grep -qE 'cudaErrorIllegalAddress|PETSc error code:[[:space:]]*76|Thrust failure' \"$L\"; then "
                    + ("touch .cfd_studio_gpu_only_failed .cfd_studio_user_stopped; echo GPU_ONLY_FAILED; fi" if only_gpu else
                       "touch .cfd_studio_gpu_pcgammg_failed \"$HOME/.cfd_studio_gpu_pcgammg_failed\" .cfd_studio_user_stopped; "
                       f"{of_bash()}; CFD_STUDIO_GPU_PRESSURE=0 python3 tools/select_pressure_solver.py >/dev/null 2>&1 || true; "
                       "echo GPU_FAILED; fi")
                )
                ok_g, out_g = wsl(gpu_check, timeout=20)
                if ok_g and ("GPU_FAILED" in out_g or "GPU_ONLY_FAILED" in out_g):
                    STATE["user_stopped"] = True
                    if "GPU_ONLY_FAILED" in out_g:
                        STATE["auto_msg"] = time.strftime("%H:%M") + " GPU Only 오류 — 자동 재개 차단"
                        print("  [GPU Only] CUDA 오류 감지 — CPU 전환 없이 자동 재개 차단")
                    else:
                        STATE["auto_msg"] = time.strftime("%H:%M") + " GPU 오류 — CPU 전환, 자동 재개 차단"
                        print("  [안전 전환] CUDA/PETSc 오류 감지 — CPU GAMG로 전환, 자동 재개 차단")
                    time.sleep(180)
                    continue
                ok_us, out_us = wsl(f"cd {WSL_CASE} 2>/dev/null && [ -f .cfd_studio_user_stopped ] && echo STOPPED || true", timeout=12)
                if ok_us and "STOPPED" in out_us:
                    time.sleep(180)
                    continue
                st = get_status()
                now = time.time()
                if (st.get("case") and not st.get("running") and not st.get("completed")
                        and now - STATE.get("run_t", 0) > 420          # 방금 시작한 직후는 제외
                        and now - STATE.get("auto_t", 0) > 900):       # 15분 쿨다운
                    tmax = float(st.get("snap_max") or 0.0)
                    anchor = st.get("resume_anchor")
                    anchor = float(anchor) if anchor is not None else None
                    end = None
                    try:
                        pj = [p for p in list_projects() if p["rid"] == _active_rid()]
                        end = pj[0].get("end") if pj else None
                    except Exception: pass
                    end = float(end or st.get("endTime") or 0)
                    if tmax > 0 and anchor is not None and end > 0 and tmax < end - 1e-6:
                        auto_key = f"{_active_rid()}:{anchor:.9g}"
                        if (STATE.get("auto_anchor_key") == auto_key
                                and int(STATE.get("auto_anchor_fires") or 0) >= 1):
                            msg = time.strftime("%H:%M") + f" 자동 재개 중단: {anchor:g}s에서 반복 실패"
                            STATE["auto_msg"] = msg
                            time.sleep(180)
                            continue
                        STATE["auto_t"] = now
                        mode_error = _resume_mode_error(_active_rid())
                        if mode_error:
                            STATE["auto_msg"] = time.strftime("%H:%M") + " 자동 재개 대기: 계산 모드 불일치"
                            print("  [자동 재개] " + mode_error)
                            time.sleep(180)
                            continue
                        hw_ok, hw_msg = _prepare_run_hardware()
                        if hw_ok:
                            same_anchor = STATE.get("auto_anchor_key") == auto_key
                            STATE["auto_anchor_key"] = auto_key
                            STATE["auto_anchor_fires"] = (int(STATE.get("auto_anchor_fires") or 0) + 1
                                                          if same_anchor else 1)
                        ok = _auto_resume_fire(end) if hw_ok else False
                        STATE["auto_n"] = STATE.get("auto_n", 0) + (1 if ok else 0)
                        suffix = " 자동 재개" if ok else (" 자동 재개 대기: " + hw_msg if not hw_ok else " 자동 재개 실패")
                        STATE["auto_msg"] = time.strftime("%H:%M") + suffix
                        print(f"  [자동 재개] {STATE['auto_msg']} (복구={anchor:g}, 최신={tmax:g}/{end:g}s)")
        except Exception as e:
            print("  [자동 재개] 점검 실패:", str(e)[:80])
        time.sleep(180)

# ---------------------------------------------------------------- 상태 수집
MET_AWK = (
    'BEGIN{cm="";dt="";t="";rp=""} '
    '/^Courant Number/{cm=$NF} '
    '/^deltaT = /{dt=$3} '
    '/^Time = /{t=$3;rp=""} '
    '/Solving for p(_rgh)?/{if(rp==""){n=split($0,A,"Initial residual = ");if(n>1){split(A[2],B,",");rp=B[1]}}} '
    '/^ExecutionTime = /{if(t!=""){print t,(cm==""?0:cm),(dt==""?0:dt),$3,(rp==""?0:rp);t=""}}'
)

STATUS_SCRIPT = f"""
{_scope_case_process_snip()}
cd {WSL_CASE} 2>/dev/null || {{ echo NOCASE; exit 0; }}
# 상태 조회는 OpenFOAM 환경을 매번 다시 불러오지 않고 controlDict를 직접 읽는다.
# Windows에서 시작한 Studio의 WSL 로그인 셸에는 foamDictionary가 없을 수 있다.
APP=$(awk '$1=="application" {{gsub(/;/,"",$2); print $2; exit}}' system/controlDict 2>/dev/null)
case "$APP" in icoReactingMultiphaseInterFoam|simpleFoam|pimpleFoam) ;; *) APP=icoReactingMultiphaseInterFoam;; esac
LOG=$(ls -t "log.$APP" log.restart 2>/dev/null | head -1)
SIDS=""
for p in $(cat .cfd_studio_solver.pid .cfd_studio_supervisor.pid 2>/dev/null || true); do in_case_pid "$p" && SIDS="$SIDS $p"; done
P1=0; for p in $SIDS; do [ -n "$p" ] && P1=$((P1+1)); done
P3=0
for p in $(pgrep -f "$APP" 2>/dev/null || true); do
  # 로그 tail 명령 인자에도 솔버 이름이 들어간다. 실제 실행 파일이 솔버인 PID만 센다.
  EXE=$(readlink "/proc/$p/exe" 2>/dev/null || true)
  [ "${{EXE##*/}}" = "$APP" ] && in_case_pid "$p" && P3=$((P3+1))
done
P4=0; [ -n "$LOG" ] && [ -n "$(find $LOG -newermt '-90 seconds' 2>/dev/null)" ] && P4=1
M=$P1; [ "$P3" -gt "$M" ] && M=$P3; [ "$M" -eq 0 ] && M=$P4
A1=0
for p in $(cat .cfd_studio_allrun.pid 2>/dev/null || true); do [ -n "$p" ] && [ -d "/proc/$p" ] && A1=$((A1+1)); done
# 마커 앞에 빈 줄 강제(printf \\n) — 기록 중인 로그·계측 파일은 마지막 줄에 개행이 없는 경우가
# 많아, 다음 마커가 그 줄 끝에 붙어(예: "ClockTime = 25 s==TIME==") 구간이 통째로 사라지던
# 버그("실행은 되는데 반영이 안 됨") 원천 차단
printf "\\n==RUN==\\n"; echo "$M $P1 $P3 $P4"
printf "\\n==LOG=%s==\\n" "$LOG"; [ -n "$LOG" ] && tail -n 25 "$LOG"
printf "\\n==TIME==\\n"; [ -n "$LOG" ] && tail -c 262144 "$LOG" | grep "^Time = " | tail -1
printf "\\n==END==\\n"; grep -m1 "^endTime" system/controlDict
printf "\\n==WI==\\n"; grep -m1 "^writeInterval" system/controlDict
printf "\\n==VI==\\n"; grep -A8 "vizFields" system/controlDict 2>/dev/null | grep -m1 "writeInterval"
printf "\\n==PROBE==\\n"; cat $(ls postProcessing/probesT/*/T 2>/dev/null | sort -g) </dev/null 2>/dev/null | grep -v "^#" | tail -n 1
printf "\\n==VAPOR==\\n"; cat $(ls postProcessing/vaporVol/*/volFieldValue*.dat 2>/dev/null | sort -g) </dev/null 2>/dev/null | grep -v "^#" | tail -n 1
printf "\\n==COIL==\\n"; cat $(ls postProcessing/coilT/*/surfaceFieldValue*.dat 2>/dev/null | sort -g) </dev/null 2>/dev/null | grep -v "^#" | tail -n 1
printf "\\n==TIMES==\\n"; ls processor0 2>/dev/null | awk '$0 ~ /^[0-9]+([.][0-9]+)?$/ {{n++; if(($0+0)>m)m=$0+0}} END{{print n+0, m+0}}'
{_resume_anchor_shell("RA", ".", use_cache=True)}
printf "\\n==ANCHOR==\\n"; echo "${{RA:-}}"
printf "\\n==MET==\\n"; [ -n "$LOG" ] && tail -c 400000 "$LOG" | awk '{MET_AWK}' | tail -n 200
printf "\\n==EXIT==\\n"; cat .cfd_studio_solver_exit.json 2>/dev/null || true
printf "\\n==DBG==\\n"; pwd; echo "LOG=[$LOG] P=$P1/$P3/$P4 A=$A1"; ls -t log.* 2>&1 | head -3; echo "pp:"; ls postProcessing 2>&1 | head -5
"""

def _status_template():
    st = {"wsl": True, "case": True, "running": False, "time": None, "endTime": 30.0, "log": "", "probes": None,
          "vapor_mL": None, "coilT": None, "snap_times": [], "snap_count": 0, "snap_max": 0.0,
          "resume_anchor": None, "resume_loss_s": None,
          "eta_s": None, "eta_h": None, "solver_exit": None,
          "completed": False, "completion_reason": "",
          "extract": _extract_public(_active_rid()),
          "autosync": STATE.get("autosync", False), "autosync_period": STATE.get("autosync_period"),
          # WSL 상태 조회가 일시 실패해도 독립적으로 수집한 하드웨어 현재값은 유지한다.
          "sys": dict(SYSSTAT) if SYSSTAT else None,
          "auto_resume": bool(SCFG.get("auto_resume", True)),
          "auto_msg": STATE.get("auto_msg", ""), "auto_n": STATE.get("auto_n", 0), "user_stopped": bool(STATE.get("user_stopped")),
          "gpu_sel": gpu_index(), "gpu_auto": dict(_ENV.get("gpu_info") or {})}
    return st

def get_status():
    now = time.time()
    cached = _STATUS_CACHE.get("data")
    if cached and now - _STATUS_CACHE.get("t", 0) < 1.2:
        return cached
    if not _STATUS_LK.acquire(blocking=False):
        if cached:
            return cached
        _STATUS_LK.acquire()
    ok, out = wsl(STATUS_SCRIPT, timeout=40)
    st = _status_template()
    if not ok:
        st["wsl"] = False
        st["log"] = "WSL 호출 실패: " + out
        st["case"] = False
        _STATUS_CACHE["t"] = now
        _STATUS_CACHE["data"] = st
        _STATUS_LK.release()
        return st
    st["case"] = "NOCASE" not in out
    if not st["case"]:
        st["log"] = out
        _STATUS_CACHE["t"] = now
        _STATUS_CACHE["data"] = st
        _STATUS_LK.release()
        return st
    # 줄 단위 스캔 파서 — 빈 구간이 다음 구간 마커를 삼키지 않도록 (구버전 regex 버그 수정)
    # + 마커가 앞 줄 끝에 붙어 온 경우(개행 없는 파일 꼬리)도 복구 (이중 안전장치)
    secs, cur = {}, None
    for line in out.splitlines():
        m = re.match(r"^==([A-Z]+)(?:=.*)?==$", line)
        if m: cur = m.group(1); secs[cur] = []; continue
        g = re.search(r"==([A-Z]+)(?:=[^=]*)?==$", line)
        if g:                                   # "...ClockTime = 25 s==TIME==" 형태 → 분리 수거
            head = line[:g.start()]
            if cur is not None and head: secs[cur].append(head)
            cur = g.group(1); secs[cur] = []; continue
        if cur is not None: secs[cur].append(line)
    def sec(name): return "\n".join(secs.get(name, [])).strip()
    try:
        rp = [int(float(x)) for x in sec("RUN").split()[:4]]
        st["running"] = rp[0] > 0
        # [중단] 직후에는 프로세스가 없는데도 로그 신선도(P4)만으로 90초간 '실행 중'으로
        # 남던 문제 — 중단 후 3분 안이고 실제 프로세스(P1·P3)가 0이면 정지로 판정
        if (st["running"] and len(rp) >= 3 and rp[1] == 0 and rp[2] == 0
                and time.time() - STATE.get("stop_t", 0) < 180):
            st["running"] = False
    except Exception: pass
    st["log"] = sec("LOG")
    m = re.search(r"Time = ([\d.eE+-]+)", sec("TIME"))
    if m: st["time"] = float(m.group(1))
    m = re.search(r"endTime\s+([\d.]+)", sec("END"))
    if m: st["endTime"] = float(m.group(1))
    m = re.search(r"writeInterval\s+([\d.]+)", sec("WI"))
    st["writeInt"] = float(m.group(1)) if m else None
    m = re.search(r"writeInterval\s+([\d.]+)", sec("VI"))
    st["vizInt"] = float(m.group(1)) if m else None
    pr = sec("PROBE").split()
    if len(pr) >= 5:
        st["probes"] = {"t": float(pr[0]), "T": [round(float(v) - 273.15, 2) for v in pr[1:5]]}
    vp = sec("VAPOR").split()
    if len(vp) >= 2: st["vapor_mL"] = round(float(vp[1]) * 1e6, 1)
    cl = sec("COIL").split()
    if len(cl) >= 2: st["coilT"] = round(float(cl[1]) - 273.15, 2)
    met = []
    for ln in sec("MET").splitlines():          # t, Courant max, Δt, CPU 실행시간, p_rgh 초기잔차
        v = ln.split()
        if len(v) >= 5:
            try:
                met.append([float(x) for x in v[:5]])
            except ValueError: pass
    st["met"] = met[-200:]
    try:
        ex = json.loads(sec("EXIT"))
        if isinstance(ex, dict):
            st["solver_exit"] = ex
            active_rid = _active_rid()
            if str(ex.get("run_id") or "") == active_rid and int(ex.get("exit_code")) == 0:
                st["completed"] = True
                cfg_done = project_config(active_rid) or get_config() or {}
                run_done = cfg_done.get("run") or {}
                last_done = float(ex.get("last_time") or 0)
                cap_done = float(run_done.get("max_iterations", run_done.get("end_time_s", st.get("endTime") or 0)) or 0)
                convergence_run = (run_done.get("stop_mode") == "converged"
                                   and (cfg_done.get("openfoam_mapping") or {}).get("solver") == "simpleFoam")
                converged = convergence_run and cap_done > 0 and last_done < cap_done - 1e-9
                hit_limit = convergence_run and cap_done > 0 and last_done >= cap_done - 1e-9
                st["completion_reason"] = "converged" if converged else ("limit" if hit_limit else "end")
                pd_done = proj_dir(active_rid)
                mp_done = os.path.join(pd_done, "meta.json")
                meta_done = _read_json_file(mp_done) or {}
                if not meta_done.get("completed") or meta_done.get("completion_reason") != st["completion_reason"]:
                    meta_done.update(completed=True, completion_reason=st["completion_reason"],
                                     completed_at=ex.get("ended_at"), last_time=max(float(meta_done.get("last_time") or 0), last_done))
                    meta_write(mp_done, meta_done)
    except Exception:
        pass
    tv = sec("TIMES").split()
    try:
        st["snap_count"] = int(tv[0])
        st["snap_max"] = float(tv[1]) if len(tv) > 1 else 0.0
        # 구버전 화면 호환: 전체 수천 개 이름 대신 최신 시각 하나만 전달한다.
        st["snap_times"] = [str(st["snap_max"])] if st["snap_count"] else []
    except (ValueError, IndexError):
        pass
    try:
        av = sec("ANCHOR").splitlines()[-1].strip()
        if av:
            st["resume_anchor"] = float(av)
            st["resume_loss_s"] = max(0.0, st["snap_max"] - st["resume_anchor"])
    except (ValueError, IndexError):
        pass
    # 새 프로젝트를 준비하는 짧은 구간에는 직전 프로젝트의 로그가 아직
    # 보관되기 전일 수 있다. 그 로그의 End/수렴 문구를 새 프로젝트 완료로
    # 기록하지 않고, 새 솔버 로그가 시작될 때까지 실행 준비 상태를 유지한다.
    launching_fresh = 0 <= time.time() - float(STATE.get("run_t") or 0) < 240
    if not st["running"] and not launching_fresh:
        converged_log = re.search(r"solution converged in\s+([\d.]+)\s+iterations", st.get("log") or "", re.I)
        reached_end = (st.get("time") is not None and st.get("endTime")
                       and float(st["time"]) >= float(st["endTime"]) - 1e-9
                       and re.search(r"(?:^|\n)End(?:\n|$)", st.get("log") or ""))
        if converged_log or reached_end:
            st["completed"] = True
            cfg_done = project_config(_active_rid()) or get_config() or {}
            run_done = cfg_done.get("run") or {}
            convergence_run = (run_done.get("stop_mode") == "converged"
                               and (cfg_done.get("openfoam_mapping") or {}).get("solver") == "simpleFoam")
            st["completion_reason"] = "converged" if converged_log else ("limit" if convergence_run else "end")
            active_done = _active_rid()
            pd_done = proj_dir(active_done)
            mp_done = os.path.join(pd_done, "meta.json")
            meta_done = _read_json_file(mp_done) or {}
            if not meta_done.get("completed") or meta_done.get("completion_reason") != st["completion_reason"]:
                meta_done.update(completed=True, completion_reason=st["completion_reason"],
                                 last_time=max(float(meta_done.get("last_time") or 0), float(st.get("time") or 0)))
                meta_write(mp_done, meta_done)
    st["dbg"] = sec("DBG")
    # 기동 직후 시스템 폴링 스레드가 WSL 초기화와 겹쳐 늦어지면 상태 요청이
    # 단발 갱신을 깨운다. _SYS_COLLECT_LK가 중복 수집은 차단한다.
    if not SYSSTAT.get("ok") and time.time() - float(SYSSTAT.get("last_attempt_at") or 0) > 5:
        threading.Thread(target=_sys_refresh, name="cfd-sys-wakeup", daemon=True).start()
    st["sys"] = dict(SYSSTAT) if SYSSTAT else None
    st["auto_resume"] = bool(SCFG.get("auto_resume", True))
    st["auto_msg"] = STATE.get("auto_msg", ""); st["auto_n"] = STATE.get("auto_n", 0)
    st["user_stopped"] = bool(STATE.get("user_stopped"))
    st["gpu_sel"] = gpu_index(); st["gpu_auto"] = dict(_ENV.get("gpu_info") or {})
    # ETA: (벽시계, 물리시간) 기울기
    if st["running"] and st["time"] is not None:
        STATE["eta"].append((time.time(), st["time"]))
        STATE["eta"] = STATE["eta"][-40:]
        if len(STATE["eta"]) >= 2:
            (w0, s0), (w1, s1) = STATE["eta"][0], STATE["eta"][-1]
            if s1 > s0 + 1e-6:
                eta_s = max(0.0, (st["endTime"] - s1) * (w1 - w0) / (s1 - s0))
                st["eta_s"] = int(round(eta_s))
                st["eta_h"] = round(eta_s / 3600, 2)
    _STATUS_CACHE["t"] = time.time()
    _STATUS_CACHE["data"] = st
    _STATUS_LK.release()
    return st

# ---------------------------------------------------------------- 프레임 추출 (+속도장 압축)
def _parse_foam_bin(path, ncomp, expected_count=None):
    """OpenFOAM binary 필드 → (n, array('d'))"""
    import array as _ar
    b = open(path, "rb").read()
    i0 = b.find(b"internalField")
    m = re.search(rb"List<(?:scalar|vector)>\s*\n(\d+)\s*\n\(", b[i0:i0 + 240])
    if not m:
        uniform = re.search(rb"internalField\s+uniform\s+(\([^)]*\)|[-+0-9.eE]+)\s*;",
                            b[i0:i0 + 512])
        if not uniform or not expected_count:
            raise ValueError("OpenFOAM field data not found")
        raw = uniform.group(1).strip().strip(b"()")
        numbers = [float(value) for value in raw.split()]
        if len(numbers) != ncomp:
            raise ValueError("OpenFOAM uniform field component mismatch")
        a = _ar.array("d", numbers * expected_count)
        return expected_count, a
    n = int(m.group(1)); off = i0 + m.start() + len(m.group(0))
    a = _ar.array("d"); a.frombytes(b[off:off + n * 8 * ncomp])
    return n, a

FLOW_CONTEXTS = {}         # 프로젝트별 C 기반 10mm 격자 bin 인덱스
FLOW_CONTEXTS_LK = threading.RLock()

def _flow_context(pdir):
    key = os.path.realpath(pdir)
    with FLOW_CONTEXTS_LK:
        return FLOW_CONTEXTS.setdefault(key, {"ready": False, "dir": pdir})

def _flow_invalidate(pdir=None):
    with FLOW_CONTEXTS_LK:
        if pdir:
            FLOW_CONTEXTS.pop(os.path.realpath(pdir), None)
        else:
            FLOW_CONTEXTS.clear()

def _flow_prepare(pdir=None, flow=None):
    """셀 중심 C → 10mm 정규격자 bin 인덱스 사전 계산 (물 흐름 시각화 압축용)"""
    import array as _ar
    pdir = pdir or proj_dir(cur_rid())
    flow = _flow_context(pdir) if flow is None else flow
    if flow.get("ready") and flow.get("dir") == pdir and flow.get("occ") is not None: return True
    cpath = os.path.join(pdir, "C")
    if not os.path.exists(cpath): return False
    try:
        n, c = _parse_foam_bin(cpath, 3)
        xs, ys, zs = c[0::3], c[1::3], c[2::3]
        x0, x1 = min(xs), max(xs); y0, y1 = min(ys), max(ys); z0, z1 = min(zs), max(zs)
        nx = max(2, round((x1 - x0) / 0.01)); ny = max(2, round((y1 - y0) / 0.01))
        z_layers = sorted({round(value, 10) for value in zs})
        nominal_nz = max(2, round((z1 - z0) / 0.01))
        use_source_layers = len(z_layers) <= nominal_nz
        nz = max(2, len(z_layers)) if use_source_layers else nominal_nz
        z_layer_index = ({value: index for index, value in enumerate(z_layers)}
                         if use_source_layers else None)
        fx = nx / (x1 - x0 + 1e-12); fy = ny / (y1 - y0 + 1e-12); fz = nz / (z1 - z0 + 1e-12)
        idx = _ar.array("i", bytes(4 * n))
        occ = bytearray(nx * ny * nz)
        for i in range(n):
            ix = int((xs[i] - x0) * fx); iy = int((ys[i] - y0) * fy)
            iz = (z_layer_index[round(zs[i], 10)] if z_layer_index is not None
                  else int((zs[i] - z0) * fz))
            if ix >= nx: ix = nx - 1
            if iy >= ny: iy = ny - 1
            if iz >= nz: iz = nz - 1
            idx[i] = (iz * ny + iy) * nx + ix
            occ[idx[i]] = 255
        flow.update(ready=True, dir=pdir, n=n, idx=idx, nx=nx, ny=ny, nz=nz,
                    bbox=(x0, y0, z0, x1, y1, z1), occ=occ)
        return True
    except Exception:
        return False

def _flow_compress(u_path, out_path, flow):
    """U(943k셀 벡터) → 10mm 격자 평균 flow_*.bin (수백 KB) : 'FLW1'+dims+bbox+float32*3N"""
    import array as _ar, struct as _st
    n, u = _parse_foam_bin(u_path, 3, flow["n"])
    if n != flow["n"]: return False
    nb = flow["nx"] * flow["ny"] * flow["nz"]; idx = flow["idx"]
    acc = _ar.array("d", bytes(8 * nb * 3)); cnt = _ar.array("i", bytes(4 * nb))
    for i in range(n):
        b3 = idx[i] * 3; i3 = i * 3
        acc[b3] += u[i3]; acc[b3 + 1] += u[i3 + 1]; acc[b3 + 2] += u[i3 + 2]
        cnt[idx[i]] += 1
    out = _ar.array("f", bytes(4 * nb * 3))
    for b in range(nb):
        if cnt[b]:
            b3 = b * 3
            out[b3] = acc[b3] / cnt[b]; out[b3 + 1] = acc[b3 + 1] / cnt[b]; out[b3 + 2] = acc[b3 + 2] / cnt[b]
    tmp = out_path + ".tmp"
    try:
        with open(tmp, "wb") as f:
            f.write(b"FLW1" + _st.pack("<3I", flow["nx"], flow["ny"], flow["nz"])
                    + _st.pack("<6f", *flow["bbox"]) + out.tobytes())
        os.replace(tmp, out_path)
    finally:
        try:
            if os.path.exists(tmp): os.remove(tmp)
        except Exception: pass
    return True

def _therm_compress(t_path, out_path, flow):
    """T(스칼라) → 10mm 격자 평균 therm_*.bin : 'THM1'+dims+bbox+float32*N (빈 бин=0)"""
    import array as _ar, struct as _st
    n, tv = _parse_foam_bin(t_path, 1, flow["n"])
    if n != flow["n"]: return False
    nb = flow["nx"] * flow["ny"] * flow["nz"]; idx = flow["idx"]
    acc = _ar.array("d", bytes(8 * nb)); cnt = _ar.array("i", bytes(4 * nb))
    for i in range(n):
        acc[idx[i]] += tv[i]; cnt[idx[i]] += 1
    out = _ar.array("f", bytes(4 * nb))
    for b in range(nb):
        if cnt[b]: out[b] = acc[b] / cnt[b]
    tmp = out_path + ".tmp"
    try:
        with open(tmp, "wb") as f:
            f.write(b"THM1" + _st.pack("<3I", flow["nx"], flow["ny"], flow["nz"])
                    + _st.pack("<6f", *flow["bbox"]) + out.tobytes())
        os.replace(tmp, out_path)
    finally:
        try:
            if os.path.exists(tmp): os.remove(tmp)
        except Exception: pass
    return True

def _scalar_grid_values(path, flow):
    """OpenFOAM scalar field -> regular-grid float32 averages."""
    import array as _ar
    n, values = _parse_foam_bin(path, 1, flow["n"])
    if n != flow["n"]: return None
    nb = flow["nx"] * flow["ny"] * flow["nz"]; idx = flow["idx"]
    acc = _ar.array("d", bytes(8 * nb)); cnt = _ar.array("i", bytes(4 * nb))
    for i in range(n):
        acc[idx[i]] += values[i]; cnt[idx[i]] += 1
    out = _ar.array("f", bytes(4 * nb))
    for b in range(nb):
        if cnt[b]: out[b] = acc[b] / cnt[b]
    return out

def _scalar_compress(path, out_path, flow, magic):
    import struct as _st
    out = _scalar_grid_values(path, flow)
    if out is None: return False
    tmp = out_path + ".tmp"
    try:
        with open(tmp, "wb") as f:
            f.write(magic + _st.pack("<3I", flow["nx"], flow["ny"], flow["nz"])
                    + _st.pack("<6f", *flow["bbox"]) + out.tobytes())
        os.replace(tmp, out_path)
    finally:
        try:
            if os.path.exists(tmp): os.remove(tmp)
        except Exception: pass
    return True

def _turbulence_compress(k_path, epsilon_path, out_path, flow):
    import struct as _st
    kval = _scalar_grid_values(k_path, flow)
    epsilon = _scalar_grid_values(epsilon_path, flow)
    if kval is None or epsilon is None: return False
    tmp = out_path + ".tmp"
    try:
        with open(tmp, "wb") as f:
            f.write(b"TRB1" + _st.pack("<3I", flow["nx"], flow["ny"], flow["nz"])
                    + _st.pack("<6f", *flow["bbox"]) + kval.tobytes() + epsilon.tobytes())
        os.replace(tmp, out_path)
    finally:
        try:
            if os.path.exists(tmp): os.remove(tmp)
        except Exception: pass
    return True

def _phase_compress(water_path, vapour_path, out_path, flow):
    """alpha.water+alpha.vapour → 10mm 상분율.

    ``PHS2`` + dims + bbox + water(uint8*N) + vapour(uint8*N) + occupancy(uint8*N).
    alpha.liquid는 화면에서 max(0, 1-water-vapour)로 복원한다. 시각화에
    충분한 8-bit 정밀도를 써 프레임당 크기와 브라우저 메모리를 억제한다.
    """
    import array as _ar, struct as _st
    n_w, water = _parse_foam_bin(water_path, 1, flow["n"])
    n_v, vapour = _parse_foam_bin(vapour_path, 1, flow["n"])
    if n_w != flow["n"] or n_v != flow["n"]:
        return False
    nb = flow["nx"] * flow["ny"] * flow["nz"]
    idx = flow["idx"]
    acc_w = _ar.array("d", bytes(8 * nb)); acc_v = _ar.array("d", bytes(8 * nb))
    cnt = _ar.array("i", bytes(4 * nb))
    for i in range(n_w):
        b = idx[i]
        acc_w[b] += water[i]; acc_v[b] += vapour[i]; cnt[b] += 1
    out_w = bytearray(nb); out_v = bytearray(nb)
    for b in range(nb):
        if cnt[b]:
            w = max(0.0, min(1.0, acc_w[b] / cnt[b]))
            v = max(0.0, min(1.0, acc_v[b] / cnt[b]))
            out_w[b] = int(w * 255.0 + 0.5)
            out_v[b] = int(v * 255.0 + 0.5)
    tmp = out_path + ".tmp"
    try:
        with open(tmp, "wb") as f:
            f.write(b"PHS2" + _st.pack("<3I", flow["nx"], flow["ny"], flow["nz"])
                    + _st.pack("<6f", *flow["bbox"]) + out_w + out_v + flow["occ"])
        os.replace(tmp, out_path)
    finally:
        try:
            if os.path.exists(tmp): os.remove(tmp)
        except Exception: pass
    return True

def _upgrade_phase_project(pdir):
    """PHS1 캐시에 C에서 유체 셀 occupancy를 붙여 PHS2로 원자 교체.

    PHS1은 빈 10 mm bin이 water=0, vapour=0이어서 화면이 이를
    liquid=1로 오해했다. alpha 배열은 변경하지 않고 점유 마스크만 추가한다.
    """
    if any(os.path.normcase(os.path.abspath(pdir)) == os.path.normcase(os.path.abspath(p))
           for p in EXECUTION_WORKSPACE.external_paths()):
        return 0
    try:
        files = [os.path.join(pdir, n) for n in os.listdir(pdir)
                 if n.startswith("phase_") and n.endswith(".bin")]
    except Exception:
        return 0
    legacy = []
    for path in files:
        try:
            with open(path, "rb") as f: magic = f.read(4)
            if magic == b"PHS1": legacy.append(path)
        except Exception: pass
    flow = _flow_context(pdir)
    if not legacy or not _flow_prepare(pdir, flow): return 0
    import struct as _st
    mask = bytes(flow.get("occ") or b"")
    changed = 0
    for path in legacy:
        try:
            raw = open(path, "rb").read()
            nx, ny, nz = _st.unpack_from("<3I", raw, 4); n = nx * ny * nz
            if ((nx, ny, nz) != (flow["nx"], flow["ny"], flow["nz"])
                    or len(raw) < 40 + 2*n or len(mask) != n):
                continue
            tmp = path + ".tmp"
            with open(tmp, "wb") as f: f.write(b"PHS2" + raw[4:40 + 2*n] + mask)
            os.replace(tmp, path); changed += 1
        except Exception:
            try: os.remove(path + ".tmp")
            except Exception: pass
    return changed

def _bub_compress(a_path, out_path, expected_count=None, th=0.03):
    """alpha.vapour → 희소 압축 bub_*.bin : 'BUB1'+u32 n+u32 total + n×(u32 idx, f32 a)"""
    import array as _ar, struct as _st
    n, a = _parse_foam_bin(a_path, 1, expected_count)
    idx = _ar.array("I"); val = _ar.array("f")
    for i in range(n):
        if a[i] > th:
            idx.append(i); val.append(a[i])
    body = _ar.array("f", bytes(8 * len(idx)))
    tmp = out_path + ".tmp"
    try:
        with open(tmp, "wb") as f:
            f.write(b"BUB1" + _st.pack("<2I", len(idx), n))
            iv = _ar.array("f")
            for i in range(len(idx)):
                f.write(_st.pack("<If", idx[i], val[i]))
        os.replace(tmp, out_path)
    finally:
        try:
            if os.path.exists(tmp): os.remove(tmp)
        except Exception: pass
    return True

def _isolated_reconstruct_script(case_src, sim_time, fields, after="", phase_fields=""):
    """한 시각만 보이는 임시 케이스를 만들어 외부 Raw 링크 전체 스캔을 피한다.

    ``after``는 재조립 성공 뒤 같은 WSL 셸에서 실행되며 ``$TMP``, ``$T``,
    ``$HAS_PHASE``를 사용할 수 있다.
    """
    base_fields = _shq(fields)
    phase_select = ""
    if phase_fields:
        phase_select = f"[ \"$HAS_PHASE\" -eq 0 ] || FIELDS={_shq(phase_fields)}; "
    with_zero = "-withZero " if abs(float(sim_time)) < 1e-12 else ""
    return (
        f"{of_bash()}; cd {case_src} || exit 2; "
        f"taskset -pc {_shq(extract_cpu_set())} $$ >/dev/null 2>&1 || true; "
        "renice 15 -p $$ >/dev/null 2>&1 || true; ionice -c3 -p $$ >/dev/null 2>&1 || true; "
        f"CASE=$(pwd -P); T={_shq(sim_time)}; "
        "TMP=$(mktemp -d /tmp/cfd_studio_reconstruct.XXXXXX) || exit 3; "
        "trap 'rm -rf \"$TMP\"' EXIT HUP INT TERM; "
        "ln -s \"$CASE/system\" \"$TMP/system\" || exit 4; "
        "ln -s \"$CASE/constant\" \"$TMP/constant\" || exit 4; N=0; HAS_PHASE=1; "
        "for P in processor[0-9]*; do [ -d \"$P/constant\" ] || continue; "
        "[ -d \"$P/$T\" ] || exit 5; mkdir -p \"$TMP/$P\" || exit 5; "
        "[ -f \"$P/$T/alpha.water\" ] || HAS_PHASE=0; "
        "ln -s \"$CASE/$P/constant\" \"$TMP/$P/constant\" || exit 5; "
        "SRC=$(readlink -f \"$CASE/$P/$T\") || exit 5; "
        "ln -s \"$SRC\" \"$TMP/$P/$T\" || exit 5; N=$((N+1)); done; "
        "[ \"$N\" -gt 0 ] || exit 6; cd \"$TMP\" || exit 6; "
        f"FIELDS={base_fields}; {phase_select}"
        f"reconstructPar {with_zero}-time \"$T\" -fields \"$FIELDS\" >/dev/null 2>&1 || exit 7; "
        + after
    )

def _ensure_project_cell_centres(pdir, case_src, times):
    """프로젝트 C를 원자적으로 확보한다. 실패한 최신 스냅샷 하나에 묶이지 않는다."""
    cpath = os.path.join(pdir, "C")
    if _valid_cell_centres(cpath):
        return True, ""
    candidates = []
    for pos in (0, len(times) // 2, len(times) - 1):
        if times:
            value = str(times[pos])
            if value not in candidates:
                candidates.append(value)
    if not candidates:
        return False, "완료된 원본 스냅샷이 없습니다"

    wdir = win2wsl(pdir)
    ctmp = os.path.join(pdir, "_C_tmp")
    cfg = (_read_json_file(os.path.join(pdir, "case_config.json")) or
           _read_json_file(os.path.join(pdir, "config.json")) or {})
    reconstruct_fields = "(U)" if cfg.get("_해석유형") == "grain_silo" else "(alpha.vapour U T)"
    errors = []
    for sim_time in candidates:
        try: os.remove(ctmp)
        except OSError: pass
        # 임시 파일 검증 후 교체한다. Viewer가 복사 중인 C를 읽는 경쟁 상태를 막는다.
        c_after = (
            "ZERO_OPT=; [ \"$T\" = 0 ] && ZERO_OPT=-withZero; "
            "postProcess $ZERO_OPT -func writeCellCentres -time \"$T\" >/dev/null 2>&1 || exit 8; "
            f"cp \"$TMP/$T/C\" {_shq(wdir + '/_C_tmp')} 2>/dev/null || exit 9; "
            f"test -s {_shq(wdir + '/_C_tmp')} || exit 10"
        )
        ok, err = wsl(_isolated_reconstruct_script(case_src, sim_time,
                      reconstruct_fields, c_after), timeout=720)
        if ok and _valid_cell_centres(ctmp):
            os.replace(ctmp, cpath)
            return True, ""
        errors.append(f"t={sim_time}: {(err or 'C 파일 생성 실패')[-90:]}")
    try: os.remove(ctmp)
    except OSError: pass
    return False, " | ".join(errors)[-240:]

def extract_worker(rid=None):
    key = _extract_key(rid)
    lock = _extract_lock(key)
    raw_lock = _raw_io_lock(key)
    S = _extract_state(key)
    if not lock.acquire(blocking=False):          # 같은 프로젝트의 수동+자동 중복 진입만 차단
        return
    # Raw 보관과 같은 프로젝트의 재조립은 디렉터리 교체 구간만 직렬화한다.
    # 예전에는 보관 중 클릭한 업데이트 요청을 즉시 버려 사용자가 반복 클릭해야 했다.
    S.update(busy=True, msg="Raw 보관 중인 시각 완료 대기")
    if not raw_lock.acquire(timeout=900):
        S.update(busy=False, msg="Raw 보관 대기 시간 초과 — 업데이트를 다시 눌러주세요")
        lock.release()
        return
    try:
        _extract_worker_inner(key, S)
    except Exception as e:
        S.update(busy=False, msg="오류: " + str(e)[:90])
    finally:
        raw_lock.release()
        lock.release()

def _extract_worker_inner(requested_rid, S):
    S.update(busy=True, done=0, processed=0, total=0, backfill=0, reused=0, remaining=0,
             failed=0, last_error="", already_complete=False, msg="스냅샷 목록 확인 중")
    requested_rid = _project_key(requested_rid)
    active_rid = _active_rid()
    case_src = WSL_CASE if not requested_rid or requested_rid == active_rid else f"{WSL_CASE}/ProjectRuns/{requested_rid}"
    ok, out = wsl(f"cd {case_src} && ls processor0 2>/dev/null | grep -E '^[0-9]' | sort -g; "
                  "echo ==PHASE==; "
                  "echo ==FRESH==; "
                  f"L=$(ls processor0 2>/dev/null | grep -E '^[0-9]' | sort -g | tail -1); "
                  f"[ -n \"$L\" ] && find processor0/$L -maxdepth 0 -newermt '-25 seconds' 2>/dev/null; "
                  f"echo ==ET==; {of_bash()} >/dev/null 2>&1; foamDictionary -entry endTime -value system/controlDict 2>/dev/null")
    if not ok:
        S.update(busy=False, last_error=(out or "WSL 스냅샷 조회 실패")[-160:],
                 msg="스냅샷 조회 실패 — 원본 연결을 확인하세요")
        return
    times_part, phase_mark, rest = out.partition("==PHASE==")
    phase_part, fresh_mark, tail = rest.partition("==FRESH==") if phase_mark else ("", "", "")
    if not phase_mark:                                  # 구형/비정상 응답도 안전하게 빈 목록 처리
        times_part, _, tail = out.partition("==FRESH==")
    # The decomposed 0/ directory is the reproducible initial state for both
    # immersion and storage cases, so it belongs at the start of playback.
    times = list(dict.fromkeys(times_part.split()))
    # alpha.water 유무를 여기서 모든 시각에 대해 검사하면 외부 Raw 링크를
    # 수천 번 따라가게 된다. 실제 처리할 한 시각의 임시 케이스에서만 검사한다.
    phase_times = set(times)
    etp = tail.split("==ET==")
    et = None
    try: et = float(etp[1].strip().splitlines()[-1])
    except Exception: pass
    # 솔버가 아직 쓰는 중일 수 있는 최신 스냅샷(25초 이내 생성)은 건너뜀 — 다음 주기에 처리.
    if times and etp[0].strip():
        times = times[:-1]
    # 프로젝트 ID — 1순위: 실행 시 발급된 케이스 마커 · 2순위(구버전 케이스): 격자 파일 시각
    # 확인 실패 시(무거운 계산 중 WSL 응답 지연 등)는 이번 주기를 건너뜀 — 잘못된 폴더에
    # 귀속시키는 것보다 한 주기 늦는 편이 안전 (프로젝트 독립성 보장)
    ok2, rid = wsl(f"cd {case_src} && cat .cfd_studio_runid 2>/dev/null || stat -c %Y constant/polyMesh/points 2>/dev/null")
    rid = re.sub(r"[^0-9]", "", (rid or "").strip().splitlines()[-1].strip()) if (ok2 and rid.strip()) else ""
    if not rid:
        S.update(busy=False, msg="실행 확인 실패 — 다음 주기에 재시도")
        return
    newborn = active_rid != rid
    if newborn: _flow_invalidate()
    if not newborn:
        try: open(os.path.join(FRAME_DIR, "_runid.txt"), "w").write(rid)
        except Exception: pass
    PDIR = proj_dir(rid)
    if not os.path.isdir(PDIR):
        pj0 = {}
        try: pj0 = json.load(open(PENDF))
        except Exception: pass
        nm0 = pj0.get("name") or time.strftime("실행 %m/%d %H:%M")
        PDIR = _create_run_project(rid, nm0, {"settings": pj0.get("settings") or {},
                    "end": float((pj0.get("settings") or {}).get("end_time_s") or 30),
                    "end_locked": True, "heal2": True})
    if not newborn and os.path.exists(PENDF):              # [새 프로젝트]로 시작된 현재 실행 → 이름 승계
        try:
            pj = json.load(open(PENDF))
            mp = os.path.join(PDIR, "meta.json")
            meta = {}
            try: meta = json.load(open(mp))
            except Exception: pass
            if pj.get("name"): meta["name"] = pj["name"]
            if pj.get("settings"): meta["settings"] = pj["settings"]
            meta_write(mp, meta)
            os.remove(PENDF)
        except Exception: pass
    wdir = win2wsl(PDIR)
    _cleanup_extract_temps(PDIR)
    sel = S.get("sel") or {"alpha": True, "flow": True, "therm": True, "phase": True,
                           "pressure": False, "turbulence": False}
    if not any(sel.values()):
        sel = {"alpha": True, "flow": True, "therm": True, "phase": True,
               "pressure": False, "turbulence": False}
    for field in ("alpha", "flow", "therm", "phase", "pressure", "turbulence"):
        sel.setdefault(field, False)
    def rf_for(with_phase):
        fields = []
        if sel["alpha"] or (sel["phase"] and with_phase): fields.append("alpha.vapour")
        if sel["phase"] and with_phase: fields.append("alpha.water")
        if sel["flow"]: fields.append("U")
        if sel["therm"]: fields.append("T")
        if sel["pressure"]: fields.append("p")
        if sel["turbulence"]: fields.extend(("k", "epsilon"))
        return "(" + " ".join(fields) + ")"
    def apath(t): return os.path.join(PDIR, f"alpha.vapour_{t}")
    def fpath(t): return os.path.join(PDIR, f"flow_{t}.bin")
    def tpath(t): return os.path.join(PDIR, f"therm_{t}.bin")
    def ppath(t): return os.path.join(PDIR, f"phase_{t}.bin")
    def pressure_path(t): return os.path.join(PDIR, f"pressure_{t}.bin")
    def turbulence_path(t): return os.path.join(PDIR, f"turbulence_{t}.bin")
    def pnopath(t): return os.path.join(PDIR, f".no_phase_{t}")
    def bpath0(t): return os.path.join(PDIR, f"bub_{t}.bin")
    def output_ok(path, kind, remove_invalid=True):
        if _valid_viz_output(path, kind):
            return True
        if remove_invalid and os.path.exists(path):
            try: os.remove(path)
            except OSError: pass
        return False
    def bubble_ok(t):
        return (output_ok(bpath0(t), "bubble") or
                output_ok(apath(t), "foam_scalar"))
    def flow_ok(t): return output_ok(fpath(t), "flow")
    def therm_ok(t): return output_ok(tpath(t), "therm")
    def pressure_ok(t): return output_ok(pressure_path(t), "pressure")
    def turbulence_ok(t): return output_ok(turbulence_path(t), "turbulence")
    def phase_ok(t):
        valid = output_ok(ppath(t), "phase")
        if valid:
            # 예전 버전이 정상 phase와 '상분율 없음' 표식을 동시에 남긴
            # 모순 상태를 정리한다. 정상 데이터가 항상 우선이다.
            try: os.remove(pnopath(t))
            except OSError: pass
            return True
        return os.path.isfile(pnopath(t))
    def need(t):
        return ((sel["alpha"] and not bubble_ok(t))
                or (sel["flow"] and not flow_ok(t))
                or (sel["therm"] and not therm_ok(t))
                or (sel["pressure"] and not pressure_ok(t))
                or (sel["turbulence"] and not turbulence_ok(t))
                or (sel["phase"] and t in phase_times and not phase_ok(t)))
    def existing_times(prefix, suffix=""):
        found = set()
        try:
            for name in os.listdir(PDIR):
                if name.startswith(prefix) and (not suffix or name.endswith(suffix)):
                    raw = name[len(prefix):len(name) - len(suffix) if suffix else None]
                    try: found.add(float(raw))
                    except ValueError: pass
        except OSError: pass
        return found
    completed_sets = []
    if sel["alpha"]:
        completed_sets.append(existing_times("bub_", ".bin") | existing_times("alpha.vapour_"))
    if sel["flow"]: completed_sets.append(existing_times("flow_", ".bin"))
    if sel["therm"]: completed_sets.append(existing_times("therm_", ".bin"))
    if sel["pressure"]: completed_sets.append(existing_times("pressure_", ".bin"))
    if sel["turbulence"]: completed_sets.append(existing_times("turbulence_", ".bin"))
    if sel["phase"]:
        completed_sets.append(existing_times("phase_", ".bin") | existing_times(".no_phase_"))
    common = set.intersection(*completed_sets) if completed_sets and all(completed_sets) else set()
    completed_until = max(common) if common else 0.0
    # 정상 업데이트는 마지막 완성 시각 이후만 이어 붙인다. 다만 이전 변환이
    # 중단된 뒤 더 나중 시각만 성공한 경우는 max(common)만으로 판단하면 구멍이
    # 영구적으로 누락된다. 실제 파일이 없는 과거 시각만 선별해 먼저 보완한다.
    backfill = [t for t in times if float(t) <= completed_until + 1e-9 and need(t)]
    forward = [t for t in times if float(t) > completed_until + 1e-9 and need(t)]
    todo = sorted(backfill + forward, key=float)
    S["already_complete"] = bool(times) and not todo
    S["from_time"] = round(float(todo[0]), 9) if todo else round(completed_until, 9)
    S["backfill"] = len(backfill)
    S["reused"] = max(0, len(times) - len(todo))
    S["total"] = len(todo)
    S["remaining"] = len(todo)
    S["msg"] = (f"대상 점검 완료 · 기존 {S['reused']} 재사용 · "
                f"누락 보완 {len(backfill)} · 신규 {len(forward)}")
    if not _valid_cell_centres(os.path.join(PDIR, "C")):
        S["msg"] = "셀 중심좌표(C) 생성 중"
        ok_c, c_err = _ensure_project_cell_centres(PDIR, case_src, times)
        if not ok_c:
            S.update(busy=False, last_error=(c_err or "C 파일 누락")[-240:],
                     msg="C 생성 실패 — 원본과 격자를 확인하세요")
            return
    flow = _flow_context(PDIR)
    utmp = os.path.join(PDIR, "_U_tmp"); ttmp = os.path.join(PDIR, "_T_tmp")
    prtmp = os.path.join(PDIR, "_P_tmp"); ktmp = os.path.join(PDIR, "_K_tmp")
    etmp = os.path.join(PDIR, "_E_tmp")
    atmp = os.path.join(PDIR, "_A_tmp"); wtmp = os.path.join(PDIR, "_W_tmp")
    fast_helper = win2wsl(os.path.join(HERE, "internal", "wsl_frame_compress.py"))
    fast_cache = win2wsl(os.path.join(PDIR, "Cache", "Visualization"))
    def bpath(t): return os.path.join(PDIR, f"bub_{t}.bin")
    done = processed = 0
    failed_times = []
    # 한 시각씩 재조립해 완료 즉시 Viewer에 공개한다. 여러 시각을 한 호출에
    # 묶으면 외부 Raw 링크가 섞인 경우 첫 결과까지 수분간 진행률이 0에 머문다.
    BATCH = 1
    # 구형 고빈도 스냅샷에는 alpha.water가 없을 수 있다. 해당 시각과 전체 상태
    # 시각을 분리 재조립해, 한 필드 누락이 기포/U/T 변환까지 막지 않게 한다.
    groups = [(False, [t for t in todo if t not in phase_times]),
              (True, [t for t in todo if t in phase_times])]
    for with_phase, group in groups:
        for b0 in range(0, len(group), BATCH):
            chunk = group[b0:b0 + BATCH]
            S["msg"] = f"연속 시각 재조립 {processed+1}/{len(todo)} · t={chunk[0]}"
            for t in chunk:
                need_bubble = bool(sel["alpha"] and not bubble_ok(t))
                need_phase = bool(sel["phase"] and not phase_ok(t))
                need_flow = bool(sel["flow"] and not flow_ok(t))
                need_therm = bool(sel["therm"] and not therm_ok(t))
                need_pressure = bool(sel["pressure"] and not pressure_ok(t))
                need_turbulence = bool(sel["turbulence"] and not turbulence_ok(t))
                phase_this = bool(need_phase and with_phase)
                need_vap = bool(need_bubble or phase_this)
                cps = (f"cp \"$TMP/$T/alpha.vapour\" {_shq(wdir + '/_A_tmp')} 2>/dev/null || exit 9; " if need_vap else "") + \
                      (f"if [ \"$HAS_PHASE\" -ne 0 ]; then cp \"$TMP/$T/alpha.water\" {_shq(wdir + '/_W_tmp')} 2>/dev/null || exit 9; fi; " if phase_this else "") + \
                      (f"cp \"$TMP/$T/U\" {_shq(wdir + '/_U_tmp')} 2>/dev/null || exit 9; " if need_flow else "") + \
                      (f"cp \"$TMP/$T/T\" {_shq(wdir + '/_T_tmp')} 2>/dev/null || exit 9; " if need_therm else "") + \
                      (f"cp \"$TMP/$T/p\" {_shq(wdir + '/_P_tmp')} 2>/dev/null || exit 9; " if need_pressure else "") + \
                      (f"cp \"$TMP/$T/k\" {_shq(wdir + '/_K_tmp')} 2>/dev/null || exit 9; cp \"$TMP/$T/epsilon\" {_shq(wdir + '/_E_tmp')} 2>/dev/null || exit 9; " if need_turbulence else "")
                for tmp in (atmp, wtmp, utmp, ttmp, prtmp, ktmp, etmp):
                    try: os.remove(tmp)
                    except Exception: pass
                fast_args = (f"--centres \"$CACHE/C\" --out {_shq(wdir)} --time \"$T\" "
                             + ("--alpha \"$TMP/$T/alpha.vapour\" --bubble " if need_bubble else "")
                             + ("--alpha \"$TMP/$T/alpha.vapour\" --water \"$TMP/$T/alpha.water\" --phase " if phase_this else "")
                             + ("--flow \"$TMP/$T/U\" " if need_flow else "")
                             + ("--temperature \"$TMP/$T/T\" " if need_therm else "")
                             + ("--pressure \"$TMP/$T/p\" " if need_pressure else "")
                             + ("--k \"$TMP/$T/k\" --epsilon \"$TMP/$T/epsilon\" " if need_turbulence else ""))
                # Large reconstructed fields stay in WSL. If the local helper fails,
                # copy those fields and use the proven Windows compressor below.
                fast_after = (f"CACHE={_shq(fast_cache)}; ERR=\"$CACHE/compress.err\"; mkdir -p \"$CACHE\" || exit 8; "
                              "if [ ! -s \"$CACHE/C\" ]; then "
                              "ZERO_OPT=; [ \"$T\" = 0 ] && ZERO_OPT=-withZero; "
                              "postProcess $ZERO_OPT -func writeCellCentres -time \"$T\" >/dev/null 2>&1 || exit 8; "
                              "cp \"$TMP/$T/C\" \"$CACHE/C.tmp\" && mv \"$CACHE/C.tmp\" \"$CACHE/C\" || exit 8; fi; "
                              f"python3 {_shq(fast_helper)} {fast_args} >/dev/null 2>\"$ERR\" || "
                              f"{{ cat \"$ERR\" >&2; {cps} }}")
                rec = _isolated_reconstruct_script(case_src, t, rf_for(False), fast_after,
                                                     rf_for(True) if phase_this else "")
                ok_cp, rec_err = wsl(rec, timeout=720)
                # 기동 직후 OpenFOAM 파일 동기화·외부 Raw 링크 연결이 겹치면
                # 유효한 시각도 일시적으로 재조립에 실패할 수 있다. 사용자에게
                # 업데이트를 다시 누르게 하지 말고 해당 시각만 한 번 재시도한다.
                if not ok_cp:
                    time.sleep(0.5)
                    ok_retry, retry_err = wsl(rec, timeout=720)
                    ok_cp = ok_retry
                    if retry_err:
                        rec_err = retry_err
                processed += 1
                S["processed"] = processed
                raw_or_final = ((not need_bubble or output_ok(bpath(t), "bubble") or os.path.exists(atmp))
                                and (not need_phase or phase_ok(t)
                                     or os.path.exists(atmp))
                                and (not need_flow or output_ok(fpath(t), "flow") or os.path.exists(utmp))
                                and (not need_therm or output_ok(tpath(t), "therm") or os.path.exists(ttmp))
                                and (not need_pressure or output_ok(pressure_path(t), "pressure") or os.path.exists(prtmp))
                                and (not need_turbulence or output_ok(turbulence_path(t), "turbulence")
                                     or (os.path.exists(ktmp) and os.path.exists(etmp))))
                if not ok_cp or not raw_or_final:
                    reason = (rec_err or "필수 임시 파일 누락")[-160:]
                    failed_times.append((t, reason));S.update(failed=len(failed_times),last_error=reason,
                        msg=f"t={t} 재조립 실패 · 다음 업데이트에서 재시도")
                    continue
                errors = []
                prepared = _flow_prepare(PDIR, flow)
                if sel["alpha"] and not bubble_ok(t) and os.path.exists(atmp):
                    S["msg"] = f"t={t} 기포 압축 ({done+1}/{len(todo)})"
                    try: _bub_compress(atmp, bpath(t), flow["n"] if prepared else None)
                    except Exception as e: errors.append("기포: " + str(e)[:80])
                if prepared:
                    if phase_this and os.path.exists(wtmp) and not phase_ok(t):
                        S["msg"] = f"t={t} 액체 상분율 압축 ({done+1}/{len(todo)})"
                        try: _phase_compress(wtmp, atmp, ppath(t), flow)
                        except Exception as e: errors.append("상분율: " + str(e)[:80])
                    elif (phase_this and not os.path.exists(wtmp) and
                          not _valid_viz_output(ppath(t), "phase")):
                        try:
                            marker = pnopath(t) + ".tmp";open(marker, "a").close();os.replace(marker, pnopath(t))
                        except Exception as e: errors.append("상분율 표시: " + str(e)[:80])
                    if sel["flow"] and not flow_ok(t) and os.path.exists(utmp):
                        S["msg"] = f"t={t} 흐름 압축 ({done+1}/{len(todo)})"
                        try: _flow_compress(utmp, fpath(t), flow)
                        except Exception as e: errors.append("유동: " + str(e)[:80])
                    if sel["therm"] and not therm_ok(t) and os.path.exists(ttmp):
                        S["msg"] = f"t={t} 온도 압축 ({done+1}/{len(todo)})"
                        try: _therm_compress(ttmp, tpath(t), flow)
                        except Exception as e: errors.append("온도: " + str(e)[:80])
                    if sel["pressure"] and not pressure_ok(t) and os.path.exists(prtmp):
                        S["msg"] = f"t={t} 압력장 압축 ({done+1}/{len(todo)})"
                        try: _scalar_compress(prtmp, pressure_path(t), flow, b"PRS1")
                        except Exception as e: errors.append("압력: " + str(e)[:80])
                    if (sel["turbulence"] and not turbulence_ok(t) and
                            os.path.exists(ktmp) and os.path.exists(etmp)):
                        S["msg"] = f"t={t} 난류장 압축 ({done+1}/{len(todo)})"
                        try: _turbulence_compress(ktmp, etmp, turbulence_path(t), flow)
                        except Exception as e: errors.append("난류: " + str(e)[:80])
                else:
                    errors.append("셀 격자 압축 준비 실패")
                missing = []
                if sel["alpha"] and not bubble_ok(t): missing.append("기포")
                if sel["phase"] and not phase_ok(t): missing.append("상분율")
                if sel["flow"] and not flow_ok(t): missing.append("유동")
                if sel["therm"] and not therm_ok(t): missing.append("온도")
                if sel["pressure"] and not pressure_ok(t): missing.append("압력")
                if sel["turbulence"] and not turbulence_ok(t): missing.append("난류")
                if errors or missing:
                    reason = "; ".join(errors + (["누락=" + ",".join(missing)] if missing else []))[-160:]
                    failed_times.append((t, reason));S.update(failed=len(failed_times),last_error=reason,
                        msg=f"t={t} 변환 불완전 · 다음 업데이트에서 재시도")
                    continue
                # 변환 후에도 processor 원본은 유지한다. 외부 보관이 켜져 있으면 별도
                # 보관 스레드가 SHA-256 검증 후 링크로 바꾸며, 꺼져 있으면 WSL에 그대로 둔다.
                done += 1
                S["done"] = done
                # A failed time remains outstanding; only verified outputs reduce this count.
                S["remaining"] = max(0, len(todo) - done)
                # Keep the visible progress current even if Studio closes before
                # the whole extraction pass finishes.
                if done % 4 == 0 or done == len(todo):
                    try:
                        partial = max(float(x[4:-4]) for x in os.listdir(PDIR)
                                      if x.startswith("bub_") and x.endswith(".bin"))
                        mp_partial = os.path.join(PDIR, "meta.json")
                        meta_partial = {}
                        try: meta_partial = json.load(open(mp_partial))
                        except Exception: pass
                        if not meta_partial.get("end"):
                            meta_partial["end"] = et
                        meta_partial["end_locked"] = True
                        meta_partial["tmax"] = round(partial, 2)
                        meta_write(mp_partial, meta_partial)
                    except Exception:
                        pass
    # 작업 도중 Studio가 닫히거나 특정 시각만 실패해도 마지막 파일의
    # 시각만으로 완료를 판정하지 않는다. 시작 때와 동일한 기준으로 전체
    # 대상을 다시 검증하고, 하나라도 남으면 반드시 부분 완료로 남긴다.
    remaining_times = sorted((t for t in times if need(t)), key=float)
    S["remaining"] = len(remaining_times)
    if remaining_times:
        reason = (f"종료 검증: {len(remaining_times)}개 시각 누락 "
                  f"(t={remaining_times[0]}~{remaining_times[-1]})")
        if failed_times:
            reason += " · " + failed_times[-1][1]
        S["last_error"] = reason
    names_now = os.listdir(PDIR)
    n_a = len([f for f in names_now
               if ((f.startswith("bub_") and f.endswith(".bin") and
                    _valid_viz_output(os.path.join(PDIR, f), "bubble")) or
                   (f.startswith("alpha.vapour_") and
                    _valid_viz_output(os.path.join(PDIR, f), "foam_scalar")))])
    n_f = len([f for f in names_now if f.startswith("flow_") and f.endswith(".bin") and
               _valid_viz_output(os.path.join(PDIR, f), "flow")])
    n_t = len([f for f in names_now if f.startswith("therm_") and f.endswith(".bin") and
               _valid_viz_output(os.path.join(PDIR, f), "therm")])
    n_p = len([f for f in names_now if f.startswith("phase_") and f.endswith(".bin") and
               _valid_viz_output(os.path.join(PDIR, f), "phase")])
    n_pr = len([f for f in names_now if f.startswith("pressure_") and f.endswith(".bin") and
                _valid_viz_output(os.path.join(PDIR, f), "pressure")])
    n_tr = len([f for f in names_now if f.startswith("turbulence_") and f.endswith(".bin") and
                _valid_viz_output(os.path.join(PDIR, f), "turbulence")])
    try:
        ts2 = []
        for f in os.listdir(PDIR):
            try:
                if (f.startswith("bub_") and f.endswith(".bin") and
                        _valid_viz_output(os.path.join(PDIR, f), "bubble")):
                    ts2.append(float(f[4:-4]))
                elif (f.startswith("alpha.vapour_") and
                      _valid_viz_output(os.path.join(PDIR, f), "foam_scalar")):
                    ts2.append(float(f.split("_")[1]))
                elif f.startswith("flow_") and f.endswith(".bin"):
                    ts2.append(float(f[5:-4]))
                elif f.startswith("therm_") and f.endswith(".bin"):
                    ts2.append(float(f[6:-4]))
                elif f.startswith("phase_") and f.endswith(".bin"):
                    ts2.append(float(f[6:-4]))
                elif f.startswith("pressure_") and f.endswith(".bin"):
                    ts2.append(float(f[9:-4]))
                elif f.startswith("turbulence_") and f.endswith(".bin"):
                    ts2.append(float(f[11:-4]))
            except Exception: pass
        mp2 = os.path.join(PDIR, "meta.json")
        meta2 = {}
        try: meta2 = json.load(open(mp2))
        except Exception: pass
        if not meta2.get("end"):                            # 종료 시각은 최초 1회만 기록 — 프로젝트 독립성
            meta2["end"] = et
        meta2["end_locked"] = True
        meta2["tmax"] = round(max(ts2), 2) if ts2 else 0
        meta_write(mp2, meta2)
    except Exception: pass
    try:
        # 계측 이력(열전대·증기·코일)을 프로젝트 폴더에 함께 보관 —
        # 다음 실행이 케이스를 교체해도 이 프로젝트의 차트가 계속 표시되도록
        h = get_histories(2500, case_src)
        if h.get("probes") or h.get("vapor"):
            h["measured"] = True
            meta_write(os.path.join(PDIR, "history.json"), h)
    except Exception: pass
    # 이 실행에 실제로 쓰인 설정 전체를 프로젝트 폴더에 1회 스냅샷 —
    # 저장된 데이터만으로 나중에 재현·검증할 수 있게 (2026-08-15 감사)
    try: snapshot_provenance(os.path.basename(PDIR))
    except Exception: pass
    for tmp in (atmp, wtmp, utmp, ttmp, prtmp, ktmp, etmp):
        try: os.remove(tmp)
        except OSError: pass
    if remaining_times:
        S.update(busy=False, failed=len(remaining_times), remaining=len(remaining_times),
                 msg=f"부분 완료 — 성공 {done} · 잔여 누락 {len(remaining_times)} · 업데이트 시 재시도")
    elif failed_times:
        S.update(busy=False, failed=len(failed_times), last_error=failed_times[-1][1],
                 msg=f"부분 완료 — 성공 {done} · 실패 {len(failed_times)} · 업데이트 시 재시도")
    elif S.get("already_complete"):
        S.update(busy=False, failed=0, remaining=0,
                 msg="이미 시각화가 완성되었습니다")
    else:
        S.update(busy=False, failed=0, remaining=0,
                 msg=f"시각화가 완성되었습니다 · 전체 검증 통과 — 기존 {S.get('reused', 0)} 재사용 · "
                     f"변환 {done} · 기포 {n_a} · 흐름 {n_f} · 온도 {n_t} · 상분율 {n_p}")
        if n_pr or n_tr:
            S["msg"] += f" · 압력 {n_pr} · 난류 {n_tr}"

def get_histories(n=1500, case_dir=None):
    """probesT·vaporVol·coilT 전체 이력 (재시작 폴더 이어붙임) — 대시보드 차트용"""
    source_case = case_dir or WSL_CASE
    script = f"""
cd {source_case} 2>/dev/null || exit 0
echo "==PH=="; cat $(ls postProcessing/probesT/*/T 2>/dev/null | sort -g) </dev/null 2>/dev/null | grep -v "^#" | tail -n {n}
echo "==VH=="; cat $(ls postProcessing/vaporVol/*/volFieldValue*.dat 2>/dev/null | sort -g) </dev/null 2>/dev/null | grep -v "^#" | tail -n {n}
echo "==CH=="; cat $(ls postProcessing/coilT/*/surfaceFieldValue*.dat 2>/dev/null | sort -g) </dev/null 2>/dev/null | grep -v "^#" | tail -n 400
"""
    ok, out = wsl(script, timeout=40)
    secs, cur = {}, None
    for line in (out.splitlines() if ok else []):
        m = re.match(r"^==([A-Z]+)==$", line)
        if m: cur = m.group(1); secs[cur] = []
        elif cur is not None: secs[cur].append(line)
    def rows(name, ncol, conv):
        # 재시작 구간 겹침 병합 — 같은 시각은 '나중 파일'이 이긴다.
        # 예전에는 정렬 순서에 의존해 뒤로 가는 행을 잘라냈는데, sort -V 가
        # 0.5 를 0.25 앞에 놓는 바람에 재시작한 실행의 뒷구간이 통째로 사라졌다.
        # (2026-08-15) 이제 시각을 키로 모아 정렬하므로 입력 순서와 무관하다.
        d = {}
        for l in secs.get(name, []):
            v = l.split()
            if len(v) >= ncol:
                try: r = conv(v)
                except ValueError: continue
                d[round(r[0], 9)] = r
        return [d[k] for k in sorted(d)]
    return {"probes": rows("PH", 5, lambda v: [float(v[0])] + [round(float(x) - 273.15, 3) for x in v[1:5]]),
            "vapor":  rows("VH", 2, lambda v: [float(v[0]), round(float(v[1]) * 1e6, 2)]),
            "coil":   rows("CH", 2, lambda v: [float(v[0]), round(float(v[1]) - 273.15, 2)])}

def _therm_load(path):
    import struct as _st, array as _ar
    b = open(path, "rb").read()
    if b[:4] != b"THM1": return None
    nx, ny, nz = _st.unpack_from("<3I", b, 4)
    bb = _st.unpack_from("<6f", b, 16)
    v = _ar.array("f"); v.frombytes(b[40:40 + 4 * nx * ny * nz])
    return nx, ny, nz, bb, v

def _therm_at(g, x, y, z):
    nx, ny, nz, bb, v = g
    def ix(p, lo, hi, n): return max(0, min(n - 1, int((p - lo) / max(1e-9, hi - lo) * n)))
    return v[(ix(z, bb[2], bb[5], nz) * ny + ix(y, bb[1], bb[4], ny)) * nx + ix(x, bb[0], bb[3], nx)]

def _cellv_mean(pd, cfg):
    """이 실행의 평균 유체 셀 부피 [m³]. C 파일의 실제 셀 수 + config 형상으로 산출.
    예전에는 dx_mm³ 을 그대로 썼는데, 격자는 블록별로 2.9~3.1 mm 로 갈리고
    보드·코일이 빠지므로 실제와 크게 어긋났다(최대 37배). 한 곳에서만 정한다."""
    try:
        n = None
        cp = os.path.join(pd, "C")
        if os.path.exists(cp):
            head = open(cp, "rb").read(4096)
            m = re.search(rb"nonuniform\s+List<vector>\s*\n?(\d+)", head)
            if m: n = int(m.group(1))
        if not n: return None
        t = cfg.get("tank") or {}; b = cfg.get("board") or {}; k = cfg.get("coil") or {}
        V = (t.get("width_mm", 456) * t.get("depth_mm", 70) * t.get("liquid_height_mm", 800)
             - (b.get("x1", 0)-b.get("x0", 0))*(b.get("y1", 0)-b.get("y0", 0))*(b.get("z1", 0)-b.get("z0", 0))
             - (k.get("x1", 0)-k.get("x0", 0))*(k.get("y1", 0)-k.get("y0", 0))*(k.get("z1", 0)-k.get("z0", 0)))
        return (V * 1e-9) / n if n > 0 and V > 0 else None
    except Exception:
        return None

def snapshot_provenance(rid):
    """실행별 출처 스냅샷 — 저장된 데이터만으로 나중에 재현·검증할 수 있게 한다.
    meta.json 의 settings 는 화면 입력 10개뿐이라 물성·형상·격자·프로브가 빠져 있었다."""
    pd = proj_dir(rid)
    if not os.path.isdir(pd): return
    sp = os.path.join(pd, "case_config.json")
    cfg = get_config() or {}
    if cfg and not os.path.exists(sp):
        try: meta_write(sp, cfg)
        except Exception: pass
    try:
        mp = os.path.join(pd, "meta.json")
        m = json.load(open(mp))
        pr = m.get("provenance") or {}
        if not pr.get("app_ver"):
            cv = _cellv_mean(pd, cfg)
            pr.update({"app_ver": APP_VER, "bub_threshold": 0.03, "bin_mm": 10,
                       "cell_volume_m3": cv, "config_snapshot": os.path.basename(sp) if cfg else None,
                       "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                       "note": "case_config.json 이 이 실행에 쓰인 설정 전체. meta.settings 는 화면 입력분만"})
            m["provenance"] = pr
            meta_write(mp, m)
    except Exception: pass

def hist_project(rid):
    """보관 프로젝트의 차트 이력.
    1순위: 실행 중 자동 저장된 계측 이력(history.json — 실측). 없으면(구버전 실행)
    보관된 온도·기포 프레임에서 프로브 온도·증기 부피를 복원해 캐시로 저장."""
    pd = proj_dir(rid)
    hp = os.path.join(pd, "history.json")
    try: return json.load(open(hp))
    except Exception: pass
    # derived=True 인 이력은 계측이 아니라 '보관 프레임에서 되짚은 근사'다.
    # probes_binned/coil_binned 로 키를 나눠 계측 계열과 섞이지 않게 한다.
    out = {"probes": [], "vapor": [], "coil": [], "derived": True,
           "derived_note": "보관 프레임에서 복원한 근사값 — 프로브·코일은 10 mm 평균장 샘플이며 "
                           "실행 중 기록된 계측(프로브 점값·코일 면적평균)과 다릅니다."}
    if not os.path.isdir(pd): return out
    try:
        import struct as _st, array as _ar
        # 반드시 그 프로젝트의 스냅샷을 쓴다. 예전에는 get_config()(=지금 케이스)를 읽어
        # 앱을 재시작하거나 새 실행을 할 때마다 과거 프로젝트의 숫자가 바뀌었다.
        cfg = None
        try: cfg = json.load(open(os.path.join(pd, "case_config.json")))
        except Exception: pass
        if not cfg:
            out["derived_note"] = ("이 실행의 설정 스냅샷이 없어 복원할 수 없습니다 "
                                   "(구버전 실행). 보관 프레임은 그대로 있습니다.")
            return out
        pts = [(p[0] / 1000.0, p[1] / 1000.0, p[2] / 1000.0)
               for p in (cfg.get("probes_mm", {}).get("points") or [])][:4]
        k = cfg.get("coil") or {}
        cc = ((k.get("x0", 0) + k.get("x1", 0)) / 2000.0, (k.get("y0", 0) + k.get("y1", 0)) / 2000.0,
              (k.get("z0", 0) + k.get("z1", 0)) / 2000.0)
        cellv = _cellv_mean(pd, cfg)
        if cellv is None:
            out["derived_note"] = "셀 좌표(C) 파일이 없어 증기 부피를 복원할 수 없습니다."
            cellv = 0.0
        vap = {}
        for f in os.listdir(pd):
            try:
                if f.startswith("therm_") and f.endswith(".bin"):
                    t = float(f[6:-4]); g = _therm_load(os.path.join(pd, f))
                    if not g: continue
                    if len(pts) >= 4:
                        out["probes"].append([t] + [round(_therm_at(g, *p) - 273.15, 2) for p in pts])
                    out["coil"].append([t, round(_therm_at(g, *cc) - 273.15, 2)])
                elif f.startswith("bub_") and f.endswith(".bin"):
                    t = float(f[4:-4]); b = open(os.path.join(pd, f), "rb").read()
                    if b[:4] != b"BUB1": continue
                    nnz, _tot = _st.unpack_from("<2I", b, 4)
                    iv = _ar.array("f"); iv.frombytes(b[12:12 + 8 * nnz])
                    vap[t] = round(sum(iv[1::2]) * cellv * 1e6, 2)   # (idx,val) 짝 → 값만
                elif f.startswith("alpha.vapour_"):
                    t = float(f.split("_")[1])
                    _n, a = _parse_foam_bin(os.path.join(pd, f), 1)
                    vap[t] = round(sum(a) * cellv * 1e6, 2)
            except Exception: pass
        out["probes"].sort(); out["coil"].sort()
        out["vapor"] = [[t, vap[t]] for t in sorted(vap)]
        if out["probes"] or out["vapor"]:
            meta_write(hp, out)                  # 1회 복원 후 캐시
    except Exception: pass
    return out

def get_config():
    ok, out = wsl(f"cat {WSL_CASE}/config.json 2>/dev/null")
    if ok and out.strip().startswith("{"):
        try: return json.loads(out)
        except Exception: pass
    return None

def _cond_rows(lst):
    """config.json의 conditions 배열 → 화면용 행 정규화"""
    rows = []
    for r in (lst or []):
        if isinstance(r, dict) and r.get("name"):
            rows.append({"name": str(r["name"]), "Ta_C": str(r.get("Ta_C", "")),
                         "flow_LPM": str(r.get("flow_LPM", "")), "h": str(r.get("h_model_W_m2K", r.get("h", "")))})
    return rows

def get_conditions(cfg=None):
    """조건표 — config.json 안의 conditions 배열이 기준.
    (구버전 케이스 호환: 배열이 없으면 conditions.csv를 읽음 — 시작 시 자동 통합됨)"""
    if cfg and cfg.get("_해석유형") == "grain_silo":
        return []
    if cfg and isinstance(cfg.get("conditions"), list):
        return _cond_rows(cfg["conditions"])
    ok, out = wsl(f"cat {WSL_CASE}/conditions.csv 2>/dev/null")
    rows = []
    if ok and "," in out:
        lines = [l for l in out.splitlines() if l.strip()]
        for l in lines[1:]:
            v = l.split(",")
            if len(v) >= 4: rows.append({"name": v[0], "Ta_C": v[3], "flow_LPM": v[2],
                                         "h": v[5] if len(v) > 5 else ""})
    return rows

# ---------------------------------------------------------------- HTTP
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")   # 구버전 화면 캐시 방지
        self.end_headers()
        self.wfile.write(body)
    def _json(self, obj, code=200): self._send(code, json.dumps(obj, ensure_ascii=False).encode())
    def _send_file(self, path):
        """완료된 시각화 바이너리는 ETag로 재사용하고 큰 파일을 메모리에 통째로 읽지 않는다."""
        st = os.stat(path)
        etag = '"%x-%x"' % (st.st_mtime_ns, st.st_size)
        if self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", "private, max-age=0, must-revalidate")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(st.st_size))
        self.send_header("ETag", etag)
        self.send_header("Cache-Control", "private, max-age=0, must-revalidate")
        self.end_headers()
        with open(path, "rb") as f:
            shutil.copyfileobj(f, self.wfile, length=1024 * 1024)

    def do_GET(self):
        try:
            self._do_GET()
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass
        except Exception as e:
            try: self._json({"err": str(e)[:120]}, 500)
            except Exception: pass

    def _do_GET(self):
        u = urlparse(self.path)
        if (u.path.startswith("/api/executions") or u.path in ("/execution_workspace.js", "/spatial_editor.js", "/form_config_editor.js", "/form_wizard.js", "/config_editor.js", "/input_validation.js", "/warehouse_viewer.js", "/data_sheet_viewer.js", "/i18n.js", "/i18n_help.js")) and execution_get(self, EXECUTION_WORKSPACE):
            return
        if u.path.startswith(('/studies', '/api/studies', '/api/attempts', '/api/study-packages', '/api/capabilities')):
            if study_http.get(self, study_http.service(HERE, SCFG, PROJECT_DIR)):
                return
        if warehouse_get(self, u.path, WAREHOUSE_WORKSPACE):
            return
        if u.path == "/":
            self._send(200, INDEX_HTML.encode(), "text/html; charset=utf-8")
        elif u.path == "/api/status":
            self._json(get_status())
        elif u.path == "/api/sys":                    # WSL 상태 조회와 독립된 하드웨어 현재값
            if (not SYSSTAT.get("ok") and
                    time.time() - float(SYSSTAT.get("last_attempt_at") or 0) > 5):
                threading.Thread(target=_sys_refresh, name="cfd-sys-api", daemon=True).start()
            payload = dict(SYSSTAT)
            if STORAGESTAT:
                payload["storage"] = dict(STORAGESTAT)
            self._json(payload)
        elif u.path == "/api/extract-state":       # WSL 호출 없는 프로젝트별 경량 상태
            rid = _project_key((parse_qs(u.query or "").get("rid") or [""])[0]) or _active_rid()
            self._json(_extract_public(rid))
        elif u.path == "/api/history":
            prid = _project_key((parse_qs(u.query or "").get("proj") or [""])[0])
            cur = _active_rid()
            if prid and prid != cur:
                self._json(hist_project(prid))   # 보관 프로젝트: 자체 보관 이력(없으면 프레임에서 복원)
            else:
                self._json(get_histories())
        elif u.path == "/api/probes":
            self._json({"rows": get_histories()["probes"]})
        elif u.path == "/api/uistate":
            st0 = {}
            try: st0 = json.load(open(UISTF))
            except Exception: pass
            self._json(st0)
        elif u.path == "/api/projects":
            self._json({"cur": _active_rid(), "projects": list_projects()})
        elif u.path == "/api/settings":
            q = parse_qs(u.query or "")
            refresh = (q.get("refresh") or [""])[0] == "1"
            rid = _project_key((q.get("rid") or [""])[0]) or _active_rid()
            self._json({"ok": True, "settings": _settings_public(refresh_gpu=refresh, rid=rid)})
        elif u.path == "/api/info":
            # app 키 = CFD Studio 식별자. 실행.bat·_kill_previous 가 포트 소유자 확인에 씀
            q = parse_qs(u.query or "")
            rid = _project_key((q.get("rid") or [""])[0]) or _active_rid()
            pd = proj_dir(rid)
            if rid and os.path.isdir(pd):
                try: _upgrade_phase_project(pd)
                except Exception: pass
            pcfg = project_config(rid)
            cfg0 = pcfg or get_config()
            inv = project_inventory(pd) if rid and os.path.isdir(pd) else {
                "config": False, "config_name": "", "C": False,
                "bubble": 0, "flow": 0, "therm": 0, "phase": 0,
                "pressure": 0, "turbulence": 0, "tmax": 0}
            self._json({"app": "cfd-studio", "ver": APP_VER, "config": cfg0, "conditions": get_conditions(cfg0),
                        "saved_configs": saved_configs(), "saved_config_types": saved_config_types(),
                        "config_source": ("project" if pcfg else "case"),
                        "project_config_available": bool(pcfg),
                        "project_config_name": inv["config_name"], "data": inv,
                        "frames": flist(pd, "alpha.vapour_", lambda s: float(s.split("_")[1])),
                        "bubs": flist(pd, "bub_", lambda s: float(s[4:-4])),
                        "flows": flist(pd, "flow_", lambda s: float(s[5:-4])),
                        "therms": flist(pd, "therm_", lambda s: float(s[6:-4])),
                        "phases": flist(pd, "phase_", lambda s: float(s[6:-4])),
                        "pressures": flist(pd, "pressure_", lambda s: float(s[9:-4])),
                        "turbulences": flist(pd, "turbulence_", lambda s: float(s[11:-4])),
                        "tracer_frames": (_read_json_file(os.path.join(pd, "tracer_frames.json")) or {}).get("frames", []),
                        "hasC": _valid_cell_centres(os.path.join(pd, "C")),
                        "extract": _extract_public(rid),
                        "rid": rid, "cur": _active_rid(), "projects": list_projects(),
                        "env": {"case": WSL_CASE, "np": mpi_np(), "np_setting": str(SCFG.get("mpi_np")),
                                "cpu_pct": cpu_pct(), "cpu_slots": cpu_slots(),
                                "cpu_logical": _cpu_topology()[0], "cpu_physical": _cpu_topology()[1],
                                "gpu_index": gpu_index(), "gpu": dict(_ENV.get("gpu_info") or {}),
                                "port": PORT, "raw_archive": _raw_archive_public()},
                        "frameDir": PROJECT_DIR})
        elif u.path == "/api/silo/info":
            self._json(_silo_info())
        elif u.path == "/api/config":
            q = parse_qs(u.query or "")
            prid = _project_key((q.get("project") or [""])[0])
            name = (q.get("name") or [""])[0]
            if prid:
                cfg0 = project_config(prid)
                label = project_inventory(proj_dir(prid))["config_name"] or "config.json"
            elif name:
                cfg0 = saved_config(name)
                label = cfg_safe(name) + ".json"
            else:
                cfg0 = source_config()
                label = "config.json"
            if not cfg0:
                self._json({"ok": False, "msg": "저장된 config.json을 찾을 수 없습니다"}, 404)
            else:
                self._json({"ok": True, "config": cfg0, "conditions": get_conditions(cfg0), "name": label})
        elif u.path.startswith("/files/"):
            parts = [unquote(x) for x in u.path[7:].split("/") if x]
            key = _project_key(parts[0]) if len(parts) == 2 else ""
            if key:
                p = os.path.join(proj_dir(key), os.path.basename(parts[1]))
            elif parts:
                rid = _active_rid()
                p = os.path.join(proj_dir(rid), os.path.basename(parts[-1])) if rid else ""
            else:
                p = ""
            if p and os.path.exists(p):
                self._send_file(p)
            else:
                self._json({"err": "no file"}, 404)
        else:
            self._json({"err": "unknown"}, 404)

    def do_POST(self):
        try:
            self._do_POST()
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass
        except Exception as e:
            try: self._json({"err": str(e)[:120]}, 500)
            except Exception: pass

    def _run_legacy(self, body):
        group_id = body.get("execution_project_id")
        if group_id:
            from execution_workspace import validate_settings, label
            try:
                if (body.get("mode") != "fresh" and not (body.get("mode") == "resume_archived" and body.get("_queue_authorized") is EXECUTION_WORKSPACE)) or body.get("reset_rid"):
                    raise ValueError("새 실행으로 시작해 주세요")
                if validate_settings(body.get("config")) not in ("immersion", "grain_silo"):
                    raise ValueError("실행 모델을 확인해 주세요")
                execution_name = label(body.get("execution_name"))
                snapshot = EXECUTION_WORKSPACE.snapshot()
                if not any(p["id"] == group_id for p in snapshot["projects"]):
                    raise ValueError("프로젝트를 찾을 수 없습니다")
                if (snapshot["busy"] and body.get("_queue_authorized") is not EXECUTION_WORKSPACE) or get_status().get("running") or _extract_state(_active_rid()).get("busy") or time.time()-STATE.get("group_launch_t", 0) < 60:
                    self._json({"ok": False, "msg": "계산 또는 결과 보존 작업이 진행 중입니다. 완료 후 시작해 주세요"}, 409)
                    return
            except (ValueError, TypeError) as e:
                self._json({"ok": False, "msg": str(e)}, 400)
                return
        mode = body.get("mode", "resume")
        incoming_cfg = body.get("config")
        selected_cfg = project_config(_project_key(body.get("selected_rid")) or _active_rid()) or {}
        if ((incoming_cfg or {}).get("_해석유형") == "gas_transport" or
                (mode != "fresh" and selected_cfg.get("_해석유형") == "gas_transport")):
            self._json({"ok": False, "msg": "가스 수송 결과 프로젝트입니다. tracer_transport 실행기로 새 계산 또는 재개를 수행해 주세요."}, 409)
            return
        if isinstance(incoming_cfg, dict) and incoming_cfg.get("_해석유형") == "grain_silo":
            ok_silo, incoming_cfg, msg_silo = _normalize_silo_config(incoming_cfg)
            if not ok_silo:
                self._json({"ok": False, "msg": msg_silo}, 400); return
            body["config"] = incoming_cfg
        run_mode = _solver_mode()
        if mode in ("resume", "resume_archived"):
            check_rid = (_project_key(body.get("selected_rid")) if mode == "resume_archived" else _active_rid())
            mode_error = _resume_mode_error(check_rid, run_mode)
            if mode_error:
                self._json({"ok": False, "msg": mode_error}, 409); return
        ok_hw, hw_msg = _prepare_run_hardware()
        if not ok_hw:
            self._json({"ok": False, "msg": "시작 전 하드웨어 점검 실패: " + hw_msg}, 503)
            return
        try: r_end = float(body.get("end"))
        except Exception: r_end = None
        cond_raw = str(body.get("condition") or "")
        config_ref = str(body.get("config_ref") or "").strip()
        config_name_raw = str(body.get("config_name") or "").strip()
        config_name = cfg_safe(config_name_raw) if config_name_raw else ""
        config_payload = body.get("config")
        raw_outputs = body.get("output_fields")
        if raw_outputs is None and isinstance(config_payload, dict):
            raw_outputs = (config_payload.get("run") or {}).get("output_fields")
        output_fields = _normalize_output_fields(raw_outputs)
        if mode == "fresh" and not output_fields:
            self._json({"ok": False, "msg": "출력 데이터를 1개 이상 선택해 주세요"}, 400)
            return
        if mode == "fresh" and isinstance(config_payload, dict):
            config_payload = json.loads(json.dumps(config_payload))
            config_payload.setdefault("run", {})["output_fields"] = output_fields
            if config_name:
                config_payload["_설정이름"] = config_name
        # 구버전 화면에서 조건 선택기에 config가 섞여 들어오던 형식의 하위 호환.
        if cond_raw.startswith("cfg:") and not config_ref:
            config_ref = cond_raw
            cond_raw = ""
        cond = re.sub(r"[^A-Za-z0-9_]", "", cond_raw)
        reset_rid = re.sub(r"[^0-9]", "", str(body.get("reset_rid") or ""))
        selected_rid = re.sub(r"[^0-9]", "", str(body.get("selected_rid") or ""))
        if mode == "fresh" and not reset_rid and isinstance(config_payload, dict):
            config_payload, geometry_revised = _apply_board_floor_revision(config_payload)
            if geometry_revised:
                print("[CFD Studio] 새 프로젝트 형상 개정 적용: 보드·CPU 40 mm 하향")
        if mode == "resume_archived":
            if not selected_rid:
                self._json({"ok": False, "msg": "재개할 보관 프로젝트를 선택하세요"}, 400)
                return
            ok_switch, switch_msg = _activate_archived_project(selected_rid)
            if not ok_switch:
                self._json({"ok": False, "msg": "보관 프로젝트 전환 실패: " + switch_msg}, 409)
                return
            mode = "resume"
            print(f"[CFD Studio] 보관 프로젝트 {selected_rid} 활성화 · 앵커 {switch_msg}s")
        if reset_rid and not isinstance(config_payload, dict):
            config_ref = "proj:" + reset_rid       # 구버전 화면은 프로젝트 스냅샷으로 안전 폴백
        if mode == "fresh" and not reset_rid:
            # 새 프로젝트는 반드시 /api/proj-new가 만든 대기 카드에서만 시작한다.
            # UI 갱신 경쟁이나 오래된 탭이 현재 프로젝트를 새 계산으로 오인하는 것을 서버에서도 차단.
            try:
                pending = {"name": execution_name} if group_id else _read_json_file(PENDF)
            except Exception:
                pending = None
            if not pending or not pending.get("name"):
                # 시작 중 실패해 대기 파일은 사라졌지만 프로젝트 카드만 남은 경우.
                # 선택한 프로젝트에 보관 진행 데이터가 전혀 없을 때만 같은 ID로
                # 재시작한다. 진행 데이터가 있으면 기존 안전 차단을 유지한다.
                pd_sel = proj_dir(selected_rid) if selected_rid else ""
                meta_sel = _read_json_file(os.path.join(pd_sel, "meta.json")) if pd_sel else None
                inv_sel = project_inventory(pd_sel) if pd_sel and os.path.isdir(pd_sel) else {}
                try:
                    stored_sel = max(float((meta_sel or {}).get("last_time") or 0),
                                     float((meta_sel or {}).get("tmax") or 0),
                                     float(inv_sel.get("tmax") or 0))
                except Exception:
                    stored_sel = 0.0
                has_saved = stored_sel > 0 or any(int(inv_sel.get(k) or 0) > 0
                                                 for k in ("bubble", "flow", "therm", "phase"))
                if selected_rid and pd_sel and os.path.isdir(pd_sel) and not has_saved:
                    reset_rid = selected_rid
                    config_ref = "proj:" + selected_rid
                else:
                    self._json({"ok": False, "msg": "실행할 프로젝트 준비 정보를 확인할 수 없습니다 — 프로젝트를 다시 선택해 주세요"}, 409)
                    return
            if _extract_state(_active_rid()).get("busy"):
                self._json({"ok": False, "msg": "중단 프로젝트 결과를 보존하는 중입니다 — 완료 후 다시 실행해 주세요"}, 409)
                return
        ovin = body.get("overrides") or {}
        OVMAP = {"end_time_s": ("run", "end_time_s"), "write_interval_s": ("run", "write_interval_s"),
                 "viz_interval_s": ("run", "viz_interval_s"), "total_W": ("heater", "total_W"),
                 "evap_C": ("phase_change", "evap_C"), "cond_C": ("phase_change", "cond_C"),
                 "coil_h": ("coil", "h_W_m2K"), "flow_LPM": ("coil", "flow_LPM"),
                 "coil_UA": ("coil", "UA_target_W_K"), "Ta_C": ("coil", "Ta_C"),
                 "liquid_height_mm": ("tank", "liquid_height_mm"),
                 "dielectric_mm": ("layers", "dielectric_mm"),
                 "init_T_d": ("layers", "init_T_dielectric_C"),
                 "init_T_w": ("layers", "init_T_water_C"), "dx_mm": ("mesh", "dx_mm")}
        ovr = {}
        for k in OVMAP:
            try: ovr[k] = float(ovin[k])
            except Exception: pass
        previous_rid = _active_rid()
        if mode == "fresh" and previous_rid:
            try:
                previous_status = get_status()
                _persist_project_progress(previous_rid, previous_status.get("time"))
            except Exception:
                pass
        STATE["eta"] = []
        STATE["stop_t"] = 0                # 새 실행 — 중단 앵커 해제(정상 실행 감지 복원)
        STATE["user_stopped"] = False; STATE["run_t"] = time.time()
        if mode == "fresh":
            ok_sync, sync_msg = sync_case_files()   # Windows 폴더의 설정·도구를 WSL 케이스에 자동 반영 (버튼 없이)
            if not ok_sync:
                self._json({"ok": False, "msg": "설정 동기화 실패: " + (sync_msg or "오류")})
                return
            # 화면에 이미 로딩된 config 전체를 우선 적용한다. 원본 파일을 이동·삭제했더라도
            # 메인 화면의 빠른 수정값과 함께 실행할 수 있어야 한다.
            selected_src = None
            config_label = "config.json"
            if reset_rid:
                # 기존 프로젝트의 0초 재실행은 생성 당시 스냅샷만 사용한다.
                # 브라우저에 남은 다른 프리셋/입력값이 원본을 덮지 않게 한다.
                config_label = "프로젝트 " + reset_rid + " / case_config.json"
                selected_src = os.path.join(proj_dir(reset_rid), "case_config.json")
                if not os.path.isfile(selected_src):
                    self._json({"ok": False, "msg": "이 프로젝트의 원본 case_config.json이 없어 0초 재실행을 차단했습니다"}, 409)
                    return
            elif isinstance(config_payload, dict):
                config_label = "화면에 로딩된 설정"
                # 유량은 CFD 방정식 입력이 아니라 T6 냉각회로 계산·출처 기록용이지만,
                # 프로젝트 config 안에 함께 보존되도록 inline config에 키를 만든다.
                if "flow_LPM" in ovr:
                    config_payload = json.loads(json.dumps(config_payload))
                    config_payload.setdefault("coil", {})["flow_LPM"] = ovr["flow_LPM"]
                selected_src = _write_runtime_config(config_payload)
            elif config_ref.startswith("cfg:"):
                config_label = cfg_safe(config_ref[4:]) + ".json"
                selected_src = os.path.join(CFGDIR, config_label)
            elif config_ref.startswith("proj:"):
                prid = _project_key(config_ref[5:])
                config_label = "프로젝트 " + prid + " / config.json"
                selected_src = os.path.join(proj_dir(prid), "case_config.json")
                if prid and not os.path.isfile(selected_src):
                    selected_src = os.path.join(proj_dir(prid), "config.json")
            elif config_ref == "inline":
                config_label = "선택한 config.json"
                selected_src = _write_runtime_config(config_payload)
            if config_ref or selected_src:
                ok_p, out_p = _apply_config_file(selected_src)
                if not ok_p or "APPLIED" not in out_p:
                    self._json({"ok": False, "msg": config_label + " 적용 실패: " + (out_p or "파일 없음")[:100]})
                    return
                print(f"[CFD Studio] config 적용: {config_label}")
            if reset_rid and os.path.isdir(proj_dir(reset_rid)):
                # [리셋] — 같은 프로젝트를 저장된 설정 그대로 0초부터. 이전 시도의 프레임을
                # /api/reset이 이미 Trash로 이동했다. 이 경로에서는 설정·이름·ID만 유지하고
                # 파일을 다시 지우지 않음(외부 프로젝트 config.json 보존).
                rid_new = reset_rid
                pd_new = proj_dir(rid_new)
                try:
                    meta = {}
                    try: meta = json.load(open(os.path.join(pd_new, "meta.json")))
                    except Exception: pass
                    st0 = meta.get("settings") or {}
                    # 리셋은 저장된 프로젝트 설정의 재현이다. 화면의 오래된 입력은 무시한다.
                    ovr = {}
                    for k in OVMAP:
                        if st0.get(k) is not None:
                            try: ovr[k] = float(st0[k])
                            except Exception: pass
                    cond = re.sub(r"[^A-Za-z0-9_]", "", str(st0.get("condition") or ""))
                    output_fields = _normalize_output_fields(st0.get("output_fields"))
                    meta["settings"] = {**st0, **ovr, "condition": cond,
                                        "output_fields": output_fields}
                    meta["compute_mode"] = run_mode
                    meta["end"] = float(ovr.get("end_time_s") or meta.get("end") or 30)
                    meta.pop("reset_at", None)
                    meta["end_locked"] = True; meta["heal2"] = True
                    meta_write(os.path.join(pd_new, "meta.json"), meta)
                    with open(os.path.join(FRAME_DIR, "_runid.txt"), "w") as run_file: run_file.write(rid_new)
                    _flow_invalidate(pd_new)     # 셀 좌표 캐시 무효화 (C 재생성)
                except Exception: pass
            else:
                # 프로젝트 ID를 지금 발급 — 격자 파일 시각을 지문으로 쓰던 방식은 Allrun이
                # 격자 생성을 건너뛰면 이전 프로젝트와 ID가 겹쳐, 새 실행의 진행이 이전
                # 프로젝트 위에 표시되던 문제(95% 프로젝트가 0%로 보임)의 원인이었음
                rid_new = str(time.time_ns()) if group_id else str(int(time.time()))
                try:                # 이 프로젝트의 폴더·이름·설정을 즉시 확정 (독립 운영)
                    pj = {}
                    try: pj = {"name": execution_name} if group_id else json.load(open(PENDF))
                    except Exception: pass
                    meta = {"name": pj.get("name") or time.strftime("실행 %m/%d %H:%M"),
                            "settings": {**ovr, "condition": cond,
                                         "output_fields": output_fields,
                                         **({"config_ref": config_ref} if config_ref else {})},
                            "compute_mode": run_mode,
                            "end": float(ovr.get("end_time_s") or (get_config() or {}).get("run", {}).get("end_time_s") or 30),
                            "end_locked": True, "heal2": True,
                            "execution_project_id": group_id,
                            "execution_attempt_path": body.get("execution_attempt_path") if body.get("_queue_authorized") is EXECUTION_WORKSPACE else None}
                    pd_new = _create_run_project(rid_new, meta["name"], meta)
                    if group_id:
                        EXECUTION_WORKSPACE.attach_legacy(group_id, rid_new)
                    with open(os.path.join(FRAME_DIR, "_runid.txt"), "w") as run_file: run_file.write(rid_new)
                    if not group_id and os.path.exists(PENDF): os.remove(PENDF)
                except Exception as e:
                    if group_id:
                        self._json({"ok": False, "msg": "실행 기록 생성 실패: " + str(e)}, 500)
                        return
            if previous_rid and previous_rid != rid_new:
                _persist_project_progress(previous_rid, 0, f"ProjectRuns/{previous_rid}")
            # 직접 입력값 → run_overrides.json (build_case가 config 위에 덮어 적용)
            j = {}
            for k, v in ovr.items():
                g, kk = OVMAP[k]
                j.setdefault(g, {})[kk] = v
            if j:
                ok_o, out_o = wsl(f"cd {WSL_CASE} && printf '%s' { _shq(json.dumps(j))} > run_overrides.json")
                if not ok_o:
                    print("[CFD Studio] run_overrides 반영 실패:", out_o[:120])
                    self._json({"ok": False, "msg": "설정 반영 실패(입력값 저장)"})
                    return
            else:
                wsl(f"cd {WSL_CASE} && rm -f run_overrides.json")

            # 계산 시작 즉시 config+화면 입력값을 프로젝트에 고정. 이후 독립 설정으로 재사용 가능.
            used_cfg = get_config() or {}
            try:
                used_cfg = json.loads(json.dumps(used_cfg))
                for k, v in ovr.items():
                    g, kk = OVMAP[k]
                    used_cfg.setdefault(g, {})[kk] = v
                used_cfg.setdefault("run", {})["output_fields"] = output_fields
                # case_config.json은 해석 생성 시점의 불변 기록이다.
                # 기존 프로젝트 리셋에서는 다시 쓰지 않는다.
                if used_cfg and not reset_rid:
                    meta_write(os.path.join(pd_new, "case_config.json"), used_cfg)
                    # 실행용 config.json은 OpenFOAM 규약상 고정 이름으로 유지하고,
                    # 프로젝트 안에는 사용자가 지정한 설정명으로 동일한 스냅샷을 보존한다.
                    setting_name = config_name or str(used_cfg.get("_설정이름") or "").strip()
                    if not setting_name and config_ref.startswith("cfg:"):
                        setting_name = cfg_safe(config_ref[4:])
                    if setting_name:
                        meta_write(os.path.join(pd_new, cfg_safe(setting_name) + ".json"), used_cfg)
            except Exception as e:
                self._json({"ok": False, "msg": "프로젝트 config 스냅샷 저장 실패: " + str(e)[:80]})
                return

            run_np = _run_mpi_np(run_mode)
            pre = f"CONDITION={cond} NP={run_np} " if cond else f"NP={run_np} "
            inner = (f"{_run_of_bash(run_mode)}; export CUDA_VISIBLE_DEVICES={gpu_index()}; "
                     f"export CFD_STUDIO_PRESSURE_SOLVER_MODE={run_mode}; export CFD_STUDIO_COMPUTE_MODE={run_mode}; "
                     + ("export FOAM_MEMORY_POOL='managed; size=1024; incr=1024'; " if run_mode == "gpu_only" else "") +
                     f"cd {WSL_CASE} || exit 1; touch .cfd_studio_user_stopped; "
                     f"{_case_kill_script('icoReactingMultiphaseInterFoam|simpleFoam|pimpleFoam|Allrun|cfd_studio_solver_supervisor')}sleep 2; "
                     f"rm -f .cfd_studio_user_stopped; "
                     # 새 프로젝트는 이전 원본을 지우지 않고 실행 ID별 WSL 보관소로 이동한다.
                     f"echo '[CFD Studio] preparing an independent project'; "
                     f"{_archive_current_progress_script(rid_new, previous_rid)}"
                     f"echo {rid_new} > .cfd_studio_runid; "
                     f"foamDictionary -entry numberOfSubdomains -set {run_np} system/decomposeParDict >/dev/null 2>&1; "
                     f"echo '[CFD Studio] 자동 성능 설정: {_mode_public(run_mode)[1]} · MPI {run_np}개 · CPU 상한 {cpu_pct()}% · GPU {gpu_index()}'; "
                     f"{pre}nice -n 8 ./Allrun & RUNPID=$!; echo \"$RUNPID\" > .cfd_studio_allrun.pid; "
                     f"sleep 25; APP=$(foamDictionary -entry application -value system/controlDict 2>/dev/null); "
                     f"if [ -n \"$APP\" ] && [ -f \"log.$APP\" ]; then tail --pid=\"$RUNPID\" -f \"log.$APP\"; fi; "
                     f"wait \"$RUNPID\"; RC=$?; rm -f .cfd_studio_allrun.pid; "
                     f"echo \"[CFD Studio] 계산 작업 종료 (exit $RC)\"; exit \"$RC\"")
        else:
            # 이어서 실행 — 설정을 일절 바꾸지 않는 순수 재개 (입력값 적용은 [처음부터] 전용)
            # 앵커 = p_rgh·T·U가 모두 있는 마지막 전체 상태 폴더. 앵커가 없으면 0초 재시작 대신 중단·안내.
            inner = build_resume_inner(r_end, tail=True)
        if not open_console(inner):
            self._json({"ok": False, "msg": "콘솔 실행 실패 — WSL/파이썬 경로 확인 필요"})
            return
        if group_id:
            STATE["group_launch_t"] = time.time()
        if mode == "resume":
            # 연장/재개가 시작됐는데 이전 완료 표식이 남으면 프로젝트 카드가
            # 실행 중에도 완료로 보인다. 실행 상태로 되돌리고 새 상한을 함께 보존한다.
            active = _active_rid()
            if active:
                mp = os.path.join(proj_dir(active), "meta.json")
                meta = _read_json_file(mp) or {}
                for key in ("completed", "completion_reason", "completed_at"):
                    meta.pop(key, None)
                if r_end is not None:
                    meta["end"] = r_end
                    meta.setdefault("settings", {})["end_time_s"] = r_end
                meta_write(mp, meta)
        STATE["user_stopped"] = False; STATE["run_t"] = time.time()
        self._json({"ok": True, "msg": "명령 프롬프트 창에서 실행 시작됨",
                    "rid": _active_rid(), "cur": _active_rid(), "projects": list_projects()})

    def _do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        u = urlparse(self.path)
        if u.path.startswith('/api/stud') and (n <= 0 or n > (28*1024*1024 if u.path.endswith('/import') else 65536)):
            self._json({"ok": False, "msg": "실험 요청 크기를 확인해 주세요"}, 413)
            return
        if (u.path.startswith('/api/warehouse/') or u.path.startswith('/api/executions')) and (n <= 0 or n > 65536):
            self._json({"ok": False, "msg": "설정 요청 크기를 확인해 주세요"}, 413)
            return
        if u.path == "/api/screenshot" and (n <= 0 or n > 32 * 1024 * 1024):
            self._json({"ok": False, "msg": "스크린샷 크기가 허용 범위를 벗어났습니다"}, 413)
            return
        try: body = json.loads(self.rfile.read(n) or b"{}")
        except Exception: body = {}
        if u.path.startswith("/api/executions") and execution_post(self, EXECUTION_WORKSPACE, body):
            return
        if u.path.startswith('/api/stud') and study_http.post(self, study_http.service(HERE, SCFG, PROJECT_DIR), body):
            return
        if warehouse_post(self, u.path, body, WAREHOUSE_WORKSPACE):
            return
        if u.path == "/api/open-raw":
            rid = _project_key(body.get("rid"))
            path = _project_raw_run_dir(rid)
            if not path:
                self._json({"ok": False, "msg": "이 프로젝트의 보관된 Raw 데이터를 찾을 수 없습니다"}, 404)
                return
            try:
                _open_explorer(path)
            except Exception as e:
                self._json({"ok": False, "msg": "Raw 폴더를 열지 못했습니다: " + str(e)[:80]}, 500)
                return
            self._json({"ok": True, "folder": path})
        elif u.path == "/api/screenshot":
            rid = _project_key(body.get("rid"))
            pdir = proj_dir(rid)
            encoded = str(body.get("png") or "")
            if not rid or not os.path.isdir(pdir):
                self._json({"ok": False, "msg": "스크린샷을 저장할 프로젝트를 찾을 수 없습니다"}, 404); return
            if encoded.startswith("data:image/png;base64,"):
                encoded = encoded.split(",", 1)[1]
            try:
                data = base64.b64decode(encoded, validate=True)
            except Exception:
                self._json({"ok": False, "msg": "PNG 데이터 형식이 올바르지 않습니다"}, 400); return
            if len(data) < 64 or len(data) > 24 * 1024 * 1024 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
                self._json({"ok": False, "msg": "유효한 PNG 스크린샷이 아닙니다"}, 400); return
            shot_dir = os.path.join(pdir, "Screenshots")
            os.makedirs(shot_dir, exist_ok=True)
            name = "viewer_" + time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6] + ".png"
            path = os.path.join(shot_dir, name)
            tmp = path + ".tmp"
            try:
                with open(tmp, "wb") as f: f.write(data)
                os.replace(tmp, path)
            finally:
                try:
                    if os.path.exists(tmp): os.remove(tmp)
                except OSError: pass
            self._json({"ok": True, "name": name, "folder": "Screenshots"})
        elif u.path in ("/api/raw-storage-pick", "/api/raw-storage-set"):
            self._json({"ok": False, "msg": "프로젝트 설정에서 저장 폴더를 지정하세요"}, 410)
        elif u.path == "/api/settings":
            if get_status().get("running"):
                self._json({"ok": False, "msg": "실행 중에는 설정을 할 수 없습니다"}, 409); return
            ok, msg = _apply_studio_settings(body)
            if not ok:
                self._json({"ok": False, "msg": msg}, 400); return
            self._json({"ok": True, "msg": msg, "settings": _settings_public()})
        elif u.path == "/api/run":
            with EXECUTION_WORKSPACE.lock:
                if EXECUTION_WORKSPACE.queue_summary().get("active"):
                    self._json({"ok": False, "msg": "대기열의 실행이 진행 중입니다"}, 409)
                    return
                self._run_legacy(body)
        elif u.path == "/api/stop":
            # 솔버 + (격자 생성 단계였다면) Allrun 체인까지 정지 — 안 죽이면 뒤늦게 솔버가 켜짐
            active = _active_rid()
            try:
                before = get_status()
                _persist_project_progress(active, before.get("time"))
            except Exception:
                pass
            wsl(f"cd {WSL_CASE} || exit 1; touch .cfd_studio_user_stopped; "
                f"{_case_kill_script('icoReactingMultiphaseInterFoam|simpleFoam|pimpleFoam|Allrun|cfd_studio_solver_supervisor')}")
            STATE["stop_t"] = time.time()      # 로그 신선도 기반 '실행 중' 오탐 차단 앵커
            STATE["user_stopped"] = True       # 사용자가 멈춘 것 — 자동 재개 대상 아님
            if active:
                threading.Thread(target=_migrate_project_raw_layout, args=(active,),
                                 name="cfd-raw-layout-" + active, daemon=True).start()
            self._json({"ok": True, "rid": active, "time": (before or {}).get("time") if 'before' in locals() else None,
                        "preserving": False})
        elif u.path == "/api/extract":
            f = body.get("fields") or {}
            extract_rid = _project_key(body.get("rid")) or _active_rid()
            if not extract_rid:
                self._json({"ok": False, "msg": "변환할 프로젝트를 선택해 주세요"}, 400); return
            if (project_config(extract_rid) or {}).get("_해석유형") == "gas_transport":
                self._json({"ok": True, "started": False, "msg": "저장된 농도 시각화가 준비되어 있습니다"})
                return
            if extract_rid != _active_rid():
                ok_arc, _ = wsl(f"test -d {WSL_CASE}/ProjectRuns/{extract_rid}/processor0")
                if not ok_arc:
                    self._json({"ok": False, "msg": "이 프로젝트의 원본 CFD 데이터가 보관되어 있지 않습니다"}, 404)
                    return
            S = _extract_state(extract_rid)
            L = _extract_lock(extract_rid)
            started = False
            with EXTRACT_REGISTRY_LK:
                if not S.get("busy") and not L.locked():
                    S.update({"busy": True, "done": 0, "processed": 0, "total": 0,
                              "backfill": 0, "reused": 0, "remaining": 0,
                              "failed": 0, "last_error": "", "already_complete": False, "msg": "작업 시작 대기",
                              "rid": extract_rid,
                              "sel": {"alpha": bool(f.get("alpha", True)),
                                      "flow": bool(f.get("flow", True)),
                                      "therm": bool(f.get("therm", True)),
                                      "phase": bool(f.get("phase", True)),
                                      "pressure": bool(f.get("pressure", False)),
                                      "turbulence": bool(f.get("turbulence", False))}})
                    started = True
            if started:
                threading.Thread(target=extract_worker, args=(extract_rid,),
                                 name="cfd-extract-" + extract_rid, daemon=True).start()
            self._json({"ok": True, "rid": extract_rid, "started": started,
                        "state": _extract_public(extract_rid)})
        elif u.path == "/api/autosync":
            STATE["autosync"] = bool(body.get("on"))
            f = body.get("fields") or {}
            STATE["autosel"] = {"alpha": bool(f.get("alpha", True)), "flow": bool(f.get("flow", True)),
                                "therm": bool(f.get("therm", True)), "phase": bool(f.get("phase", True)),
                                "pressure": bool(f.get("pressure", False)),
                                "turbulence": bool(f.get("turbulence", False))}
            if STATE["autosync"]:
                AUTOSYNC_EV.set()          # 켜는 즉시 1회 동기화 → 이후 주기는 실측으로 조절
            self._json({"ok": True, "on": STATE["autosync"]})
        elif u.path == "/api/config-save":
            # [config.json 생성] — 현재 config를 복제·수정한 독립 config 파일로 보관.
            # 화면에서만 새 기반 파일로 선택하고, WSL에는 새 프로젝트 실행 시 반영한다.
            try:
                if get_status().get("running"):
                    self._json({"ok": False, "msg": "실행 중에는 설정을 할 수 없습니다"}, 409); return
                name = cfg_safe(body.get("name"))
                cfg = body.get("config")
                cfg_type = str((cfg or {}).get("_해석유형") or "immersion") if isinstance(cfg, dict) else ""
                valid_immersion = isinstance(cfg, dict) and "tank" in cfg and "run" in cfg and cfg_type == "immersion"
                valid_silo = isinstance(cfg, dict) and cfg_type == "grain_silo" and isinstance(cfg.get("silo"), dict)
                if not (valid_immersion or valid_silo):
                    self._json({"ok": False, "msg": "설정 형식이 올바르지 않습니다"}, 400); return
                if valid_silo:
                    ok_silo, normalized, msg_silo = _normalize_silo_config(cfg)
                    if not ok_silo:
                        self._json({"ok": False, "msg": msg_silo}, 400); return
                    cfg = normalized
                    geometry_revised = False
                else:
                    cfg["_해석유형"] = "immersion"
                    cfg, geometry_revised = _apply_board_floor_revision(cfg)
                validate_numerics(cfg)
                cfg["_생성"] = f"CFD Studio [config.json 생성] {time.strftime('%Y-%m-%d %H:%M')} · 이름 {name}"
                cfg["_설정이름"] = name
                save_new_preset(CFGDIR, name, cfg)
                # 저장 즉시 현재 WSL config에 쓰면 중단된 기존 프로젝트의
                # 재개 설정이 바뀌다. 프리셋은 저장만 하고 실행 전환은 /api/run에서만 한다.
                self._json({"ok": True, "saved": name, "applied": False,
                            "geometry_revised": geometry_revised,
                            "config": cfg, "list": saved_configs(), "types": saved_config_types()})
            except FileExistsError as e:
                self._json({"ok": False, "msg": str(e)[:120]}, 409)
            except Exception as e:
                self._json({"ok": False, "msg": str(e)[:120]}, 400)
        elif u.path == "/api/config-del":
            try:
                if get_status().get("running"):
                    self._json({"ok": False, "msg": "실행 중에는 설정을 할 수 없습니다"}, 409); return
                raw = str(body.get("name") or "").strip()
                name = cfg_safe(raw)
                if not raw or raw != name:
                    raise ValueError("설정 이름이 올바르지 않습니다")
                path = os.path.join(CFGDIR, name + ".json")
                if not os.path.isfile(path):
                    self._json({"ok": False, "msg": "설정 파일을 찾을 수 없습니다"}, 404); return
                os.remove(path)
                self._json({"ok": True, "list": saved_configs(), "types": saved_config_types()})
            except Exception as e:
                self._json({"ok": False, "msg": str(e)[:120]}, 400)
        elif u.path == "/api/sync-case":
            ok, out = sync_case_files()
            self._json({"ok": ok, "msg": out[:120]})
        elif u.path == "/api/uistate":
            try:
                body["_t"] = time.time()
                meta_write(UISTF, body)
            except Exception: pass
            self._json({"ok": True})
        elif u.path == "/api/proj-new":
            if body.get("cancel"):
                try: os.remove(PENDF)
                except Exception: pass
                self._json({"ok": True}); return
            name = str(body.get("name") or "새 프로젝트")[:40].strip()
            json.dump({"name": name, "created": time.time()}, open(PENDF, "w"))
            self._json({"ok": True})
        elif u.path == "/api/auto-resume":
            SCFG["auto_resume"] = bool(body.get("on"))
            try: open(_SCP, "w", encoding="utf-8").write(json.dumps(SCFG, ensure_ascii=False, indent=2))
            except Exception: pass
            if SCFG["auto_resume"]: STATE["user_stopped"] = False
            self._json({"ok": True, "on": SCFG["auto_resume"]})
        elif u.path == "/api/reset":
            # [리셋] = 초기화만 — 설정은 남기고 진행 자료는 Trash로 옮긴 뒤 대기.
            raw_rid = str(body.get("rid") or "").strip()
            rid = raw_rid if raw_rid.isdigit() else ""   # 외부 폴더에서 숫자만 뽑아 다른 실행을 리셋하지 않음
            pd = proj_dir(rid)
            if not rid or pd == FRAME_DIR or not os.path.isdir(pd):
                self._json({"ok": False, "msg": "프로젝트를 찾을 수 없습니다"}); return
            reset_meta = _read_json_file(os.path.join(pd, "meta.json")) or {}
            if reset_meta.get("storage_tier") == "archive":
                self._json({"ok": False, "msg": "D 드라이브 완료 보관 프로젝트는 열람 전용입니다"}, 409); return
            if _extract_state(rid).get("busy"):
                self._json({"ok": False, "msg": "이 프로젝트의 시각화 변환 중에는 리셋할 수 없습니다"}, 409); return
            raw_lock = _raw_io_lock(rid)
            if not raw_lock.acquire(blocking=False):
                self._json({"ok": False, "msg": "Raw 데이터 이동·검증 중입니다 — 완료 후 다시 리셋해 주세요"}, 409); return
            try:
                meta_before = _read_json_file(os.path.join(pd, "meta.json")) or {}
                external_raw = str(meta_before.get("raw_archive_run") or "").strip()
                if external_raw and os.path.isdir(external_raw):
                    try:
                        rel_raw = os.path.relpath(external_raw, pd)
                        raw_inside = rel_raw != os.pardir and not rel_raw.startswith(os.pardir + os.sep)
                    except ValueError:
                        raw_inside = False
                    if not raw_inside:
                        raw_root = str(meta_before.get("raw_archive_root") or os.path.dirname(os.path.dirname(external_raw)))
                        raw_trash = os.path.join(raw_root, "Trash",
                            _project_folder_name(os.path.basename(pd)) + "__reset_" +
                            time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6], "Raw_Data")
                        os.makedirs(os.path.dirname(raw_trash), exist_ok=False)
                        shutil.move(external_raw, raw_trash)
                trashed, tinfo = _move_project_progress_to_trash(pd, rid)
                is_current = rid == _active_rid()
                if is_current:
                    stamp = time.strftime("%Y%m%d_%H%M%S")
                    # WSL의 원본 진행 자료도 같은 파일시스템 안의 영문 Trash로 이동(O(1)).
                    # 새 계산은 이 폴더를 건드리지 않으며, 30일 지난 묶음만 리셋 시 정리한다.
                    cmd = (f"cd {WSL_CASE} || exit 1; touch .cfd_studio_user_stopped; "
                           f"{_case_kill_script('icoReactingMultiphaseInterFoam|simpleFoam|pimpleFoam|Allrun|cfd_studio_solver_supervisor')}sleep 1; "
                           f"mkdir -p Trash/reset_{rid}_{stamp}; R=Trash/reset_{rid}_{stamp}; "
                           "for f in log.* processor* postProcessing VTK .cfd_studio_solver.pid .cfd_studio_allrun.pid "
                           ".cfd_studio_supervisor.pid .cfd_studio_solver_exit.json; do "
                           "[ -e \"$f\" ] && mv \"$f\" \"$R/\"; done; "
                           "for d in *; do if [ -d \"$d\" ] && [ \"$d\" != 0 ] && echo \"$d\" | grep -Eq '^[0-9]+([.][0-9]+)?$'; then mv \"$d\" \"$R/\"; fi; done; "
                           f"find Trash -mindepth 1 -maxdepth 1 -type d -mtime +{_trash_retention_days()} -exec rm -rf -- {{}} +; "
                           f"echo {rid} > .cfd_studio_runid")
                    ok_reset, reset_msg = wsl(cmd, timeout=180)
                    if not ok_reset:
                        self._json({"ok": False, "msg": "WSL 진행 자료 이동 실패: " + reset_msg[:80]}); return
                    open(os.path.join(FRAME_DIR, "_runid.txt"), "w").write(rid)
                meta_reset = _read_json_file(os.path.join(pd, "meta.json")) or {}
                for key in ("last_time", "tmax", "completed", "completion_reason", "completed_at"):
                    meta_reset.pop(key, None)
                meta_reset["tmax"] = 0
                meta_write(os.path.join(pd, "meta.json"), meta_reset)
                STATE["eta"] = []; STATE["stop_t"] = time.time(); _flow_invalidate(proj_dir(rid))
                self._json({"ok": True, "trashed": os.path.basename(trashed),
                            "retention_days": tinfo["retention_days"]})
            except Exception as e:
                self._json({"ok": False, "msg": str(e)[:80]})
            finally:
                raw_lock.release()
        elif u.path == "/api/proj-del":
            rid = _project_key(body.get("rid"))
            pd = proj_dir(rid)
            if not rid or pd == FRAME_DIR or not os.path.isdir(pd):
                self._json({"ok": False, "msg": "프로젝트를 찾을 수 없습니다"}); return
            cur = _active_rid()
            if _extract_state(rid).get("busy"):
                self._json({"ok": False, "msg": "이 프로젝트의 시각화 변환 중에는 삭제할 수 없습니다"}, 409)
                return
            if rid == cur:
                st = get_status()
                if st.get("running"):
                    self._json({"ok": False, "msg": "현재 실행 중인 프로젝트는 삭제할 수 없습니다"})
                    return
                if st.get("extract") and st["extract"].get("busy"):
                    self._json({"ok": False, "msg": "현재 실행 프로젝트 동기화 중 — 잠시 후 다시 시도하세요"})
                    return
            try:
                trashed, tinfo = _move_project_to_trash(pd, rid)
                if rid == cur:
                    try: os.remove(os.path.join(FRAME_DIR, "_runid.txt"))
                    except OSError: pass
                self._json({"ok": True, "projects": list_projects(), "rid": _active_rid(),
                            "trashed": os.path.basename(trashed),
                            "purge_after": tinfo["purge_after"],
                            "retention_days": tinfo["retention_days"]})
            except Exception as e:
                self._json({"ok": False, "msg": str(e)[:80]})
        elif u.path == "/api/proj-name":
            rid = _project_key(body.get("rid"))
            name = str(body.get("name") or "")[:40].strip()
            if not rid:                                     # 대기(새) 프로젝트 이름
                try:
                    pj = json.load(open(PENDF))
                except Exception:
                    pj = {"created": time.time()}
                pj["name"] = name
                meta_write(PENDF, pj)
                self._json({"ok": True}); return
            pd = proj_dir(rid)
            if rid and os.path.isdir(pd):
                if _extract_state(rid).get("busy"):
                    self._json({"ok": False, "msg": "동기화 중에는 이름을 바꿀 수 없습니다"}); return
                if rid == _active_rid() and get_status().get("running"):
                    self._json({"ok": False, "msg": "실행 중에는 프로젝트 이름을 바꿀 수 없습니다"}, 409); return
                meta_before = _read_json_file(os.path.join(pd, "meta.json")) or {}
                preferred_root = (os.path.dirname(pd) if meta_before.get("storage_tier") == "archive" else PROJECT_DIR)
                target = _unique_project_path(name, current=pd, preferred_root=preferred_root)
                lock = _raw_io_lock(rid)
                if not lock.acquire(blocking=False):
                    self._json({"ok": False, "msg": "Raw 데이터 작업 중에는 이름을 바꿀 수 없습니다"}, 409); return
                project_moved = False
                raw_moved_from = raw_moved_to = ""
                try:
                    mp = os.path.join(pd, "meta.json")
                    meta = _read_json_file(mp) or {}
                    root = str(meta.get("raw_archive_root") or _raw_archive_dir()).strip()
                    old_raw = str(meta.get("raw_archive_run") or "").strip()
                    new_raw = _desired_project_raw_path(target, root)
                    if old_raw and os.path.isdir(old_raw) and new_raw and os.path.exists(new_raw):
                        self._json({"ok": False, "msg": "새 프로젝트명의 Raw_Data 폴더가 이미 존재합니다"}, 409); return
                    if os.path.abspath(target) != os.path.abspath(pd):
                        shutil.move(pd, target)
                        project_moved = True
                    actual_raw = old_raw
                    if old_raw and os.path.isdir(old_raw):
                        try:
                            rel = os.path.relpath(old_raw, pd)
                            inside = rel != os.pardir and not rel.startswith(os.pardir + os.sep)
                        except ValueError:
                            inside = False
                        if inside:
                            actual_raw = os.path.join(target, rel)
                        if new_raw and os.path.normcase(os.path.normpath(actual_raw)) != os.path.normcase(os.path.normpath(new_raw)):
                            if not _same_storage_volume(actual_raw, new_raw):
                                raise OSError("기존 Raw 데이터와 새 경로의 드라이브가 다릅니다")
                            os.makedirs(os.path.dirname(new_raw), exist_ok=True)
                            shutil.move(actual_raw, new_raw)
                            raw_moved_from, raw_moved_to = actual_raw, new_raw
                            try: os.rmdir(os.path.dirname(actual_raw))
                            except OSError: pass
                            actual_raw = new_raw
                    meta["name"] = name
                    if meta.get("storage_tier") == "archive":
                        meta["archive_path"] = target
                    if root and new_raw:
                        meta["raw_archive_root"] = root
                        meta["raw_archive_run"] = new_raw
                    meta_write(os.path.join(target, "meta.json"), meta)
                    run_id = str(meta.get("run_id") or rid)
                    case_src = WSL_CASE if rid == _active_rid() else f"{WSL_CASE}/ProjectRuns/{run_id}"
                    _repair_raw_links(case_src, run_id)
                except Exception as e:
                    try:
                        if raw_moved_to and os.path.exists(raw_moved_to) and not os.path.exists(raw_moved_from):
                            os.makedirs(os.path.dirname(raw_moved_from), exist_ok=True)
                            shutil.move(raw_moved_to, raw_moved_from)
                        if project_moved and os.path.isdir(target) and not os.path.exists(pd):
                            shutil.move(target, pd)
                    except Exception: pass
                    self._json({"ok": False, "msg": "프로젝트 이름 변경 실패: " + str(e)[:90]}, 500); return
                finally:
                    lock.release()
                self._json({"ok": True, "folder": os.path.basename(target), "rid": rid})
            else:
                self._json({"ok": False}, 404)
        elif u.path == "/api/clear-frames":
            rid = _project_key(body.get("rid")) or _active_rid()
            pd = proj_dir(rid)
            if _extract_state(rid).get("busy"):
                self._json({"ok": False, "msg": "이 프로젝트의 시각화 변환 중에는 캐시를 비울 수 없습니다"}, 409); return
            if os.path.isdir(pd) and pd != FRAME_DIR:
                for name in os.listdir(pd):
                    if (name == "C" or name.startswith(("bub_", "alpha.vapour_", "flow_", "therm_", "phase_",
                                                        "pressure_", "turbulence_", ".no_phase_", "_C_tmp",
                                                        "_A_tmp", "_W_tmp", "_U_tmp", "_T_tmp", "_P_tmp",
                                                        "_K_tmp", "_E_tmp"))):
                        path = os.path.join(pd, name)
                        try:
                            if os.path.isdir(path): shutil.rmtree(path)
                            else: os.remove(path)
                        except OSError: pass
            _flow_invalidate(pd)
            self._json({"ok": True})
        else:
            self._json({"err": "unknown"}, 404)

# ---------------------------------------------------------------- UI (전체 내장)
INDEX_HTML = r'''<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"><title>CFD Studio — CFD 실행·3D 결과</title>
<link rel="icon" href='data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><rect x="2.5" y="2.5" width="19" height="19" rx="5" fill="none" stroke="%233987e5" stroke-width="1.6"/><path d="M12 6.5c2.6 3.1 4 5.2 4 7a4 4 0 0 1-8 0c0-1.8 1.4-3.9 4-7z" fill="%233987e5"/></svg>'>
<style>
 :root{
  --page:#0d0d0d; --surface:#1a1a19; --surface2:#242422; --ink:#ffffff; --ink2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --line:rgba(255,255,255,.10);
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --acc:#3987e5;
  --good:#0ca30c; --warn:#fab219; --crit:#d03b3b;
 }
 html{color-scheme:dark}
 ::-webkit-scrollbar{width:9px;height:9px}
 ::-webkit-scrollbar-thumb{background:#3a3a38;border-radius:5px;border:2px solid #1a1a19}
 ::-webkit-scrollbar-thumb:hover{background:#4c4c49}
 ::-webkit-scrollbar-track{background:transparent}
 input[type=number]::-webkit-inner-spin-button,input[type=number]::-webkit-outer-spin-button{
  -webkit-appearance:none;margin:0}
 *{box-sizing:border-box} html,body{margin:0;height:100%;background:var(--page);color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI","Malgun Gothic",sans-serif;overflow:hidden;font-size:13.5px}
 ::-webkit-scrollbar{width:9px;height:9px} ::-webkit-scrollbar-thumb{background:#33332f;border-radius:5px}
 ::-webkit-scrollbar-track{background:transparent}

 /* ── 헤더 ── */
 #hdr{height:50px;display:flex;align-items:center;gap:14px;padding:0 16px;background:var(--surface);
  border-bottom:1px solid var(--line)}
 #logo{display:flex;align-items:center;gap:9px;font-weight:700;font-size:14.5px}
 #logo svg{display:block}
 #logo .tag{font-weight:400;color:var(--muted);font-size:11.5px;margin-left:2px}
 .pill{display:inline-flex;align-items:center;gap:7px;background:var(--surface2);border:1px solid var(--line);
  border-radius:999px;padding:5px 13px;font-size:12px;color:var(--ink2)}
 .dot{width:8px;height:8px;border-radius:50%;background:var(--muted);flex:none}
 .dot.ok{background:var(--good)}
 .dot.off{background:var(--crit)}
 .dot.warn{background:var(--warn)}
 .dot.run{background:var(--s1);box-shadow:0 0 7px rgba(57,135,229,.9);animation:pulse 1.6s infinite}
 @keyframes pulse{50%{opacity:.4}}
 #hdr .path{margin-left:auto;color:var(--muted);font-size:11px;font-family:Consolas,monospace}
 #hdr .path{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 #hdr .tag2{color:var(--ink2);font-size:11.5px;margin-left:14px;white-space:nowrap}
 #modeSeg{display:flex;background:var(--surface2);border:1px solid var(--line);border-radius:999px;padding:3px;gap:2px}
 .seg{border:none;background:none;color:var(--ink2);padding:5px 15px;border-radius:999px;font-size:12px;
  cursor:pointer;font-family:inherit;transition:background .12s}
 .seg:hover{color:var(--ink)}
 .seg.on{background:var(--s1);color:#fff;font-weight:600}
 #errBanner{position:absolute;left:50%;transform:translateX(-50%);top:14px;display:none;align-items:flex-start;gap:12px;
  background:rgba(64,22,22,.93);border:1px solid #a04040;border-radius:10px;padding:10px 14px;max-width:620px;z-index:30;
  backdrop-filter:blur(8px);font-size:12px;line-height:1.6}
 #errBanner b{color:#ffb0a8;font-size:12.5px}
 #errBanner #ebG{color:#e8d8d4;margin-top:2px;white-space:pre-line}
 .bad{border-color:#e05252!important}
 #vizWarn{position:absolute;left:50%;transform:translateX(-50%);bottom:74px;display:none;align-items:center;gap:12px;
  background:rgba(26,26,25,.92);border:1px solid rgba(250,178,25,.5);border-radius:12px;padding:10px 12px 10px 16px;
  font-size:12.5px;color:var(--ink2);backdrop-filter:blur(8px);z-index:15}
 #vizWarn .btn{height:32px;white-space:nowrap;flex:none}
 #tcbar{background:rgba(26,26,25,.85);border:1px solid var(--line);
  border-radius:10px;padding:9px 11px;display:none;flex-direction:column;backdrop-filter:blur(8px)}
 #tcbar .grad{width:13px;height:132px;border-radius:4px;border:1px solid var(--grid);
  background:linear-gradient(180deg,#fffbe0 0%,#fac830 12%,#f68a10 25%,#e65434 40%,#bc207e 55%,#780a94 70%,#280658 87%,#08041a 100%)}
 #tcSat{position:absolute;left:-3px;right:-3px;height:0;border-top:2px solid rgba(255,255,255,.92)}
 #tcSatL{position:absolute;left:0;transform:translateY(50%);white-space:nowrap;font-size:9.5px;
  color:#fff;font-weight:700}
 #plabels{position:absolute;inset:0;pointer-events:none;overflow:hidden}
 #plabels span{position:absolute;transform:translate(8px,-50%);background:rgba(20,20,19,.82);border:1px solid var(--line);
  border-radius:6px;padding:2px 7px;font-size:11px;color:var(--ink2);white-space:nowrap;font-variant-numeric:tabular-nums}
 #plabels span b{color:var(--ink)}

 /* ── 레이아웃: 사이드바(평면 섹션) + 뷰어 ── */
 #app{display:flex;height:calc(100% - 50px)}
 #side{width:340px;min-width:340px;background:var(--surface);overflow-y:auto;display:flex;flex-direction:column}
 #main{flex:1;position:relative;border-left:1px solid var(--line)}
 section{padding:13px 16px 14px;border-bottom:1px solid var(--grid)}
 /* 사이드바 전체 스크롤 금지 — 프로젝트 리스트만 남은 높이를 차지하며 내부 스크롤
    (창이 아주 낮아 최소 높이도 안 나올 때만 사이드바 스크롤이 예비로 동작) */
 #side>section{display:flex;flex-direction:column;flex:1 1 auto;min-height:0}
 #side>section>*{flex-shrink:0}
 #immersionSetup{flex:1 1 auto;min-height:0;display:flex;flex-direction:column}
 /* 프로젝트 리스트: 자체 스크롤 영역(항상 스크롤바 표시) + 주변과 확실히 구분되는 패널 */
 #side #projList,#side #projList2{flex:1 1 150px;min-height:104px;max-height:46vh;
  background:var(--page);border:1px solid var(--line);border-radius:10px;padding:7px;
  overflow-y:scroll;overscroll-behavior:contain;scrollbar-gutter:stable}
 #projList::-webkit-scrollbar,#projList2::-webkit-scrollbar{width:9px}
 #projList::-webkit-scrollbar-track,#projList2::-webkit-scrollbar-track{background:#151514;border-radius:8px}
 #projList::-webkit-scrollbar-thumb,#projList2::-webkit-scrollbar-thumb{background:#3d3d3a;border-radius:8px;border:2px solid #151514}
 #projList::-webkit-scrollbar-thumb:hover,#projList2::-webkit-scrollbar-thumb:hover{background:#54544f}
 .prow{display:flex;flex-direction:row;align-items:center;justify-content:space-between;gap:8px;
  background:var(--surface2);border:1px solid var(--line);border-left:3px solid transparent;
  border-radius:8px;padding:8px 10px;cursor:pointer;font-size:10.5px;color:var(--ink2);
  transition:background .12s,border-color .12s}
 .prow:hover{background:#2c2c29;border-color:rgba(255,255,255,.2)}
 .prow.on{border-color:#e08a3a;border-left-color:#e08a3a;background:rgba(224,138,58,.10)}
 .prow b{font-size:12px;color:var(--ink)}
 section h2{margin:0 0 12px;font-size:11px;font-weight:700;letter-spacing:1.2px;color:var(--muted);
  display:flex;align-items:center}
 .hint{font-size:11px;color:var(--muted);line-height:1.65;margin-top:10px}
 .dim{color:var(--muted);font-size:11px}

 /* ── 버튼: 크게, 전부 라벨 ── */
 .btn{display:inline-flex;align-items:center;justify-content:center;gap:7px;border-radius:8px;height:38px;
  padding:0 14px;font-size:13px;cursor:pointer;border:1px solid var(--line);background:var(--surface2);
  color:var(--ink);transition:background .12s,border-color .12s;user-select:none;font-family:inherit}
 .btn:hover{background:#2c2c29;border-color:rgba(255,255,255,.2)}
 .btn.pri{background:var(--s1);border-color:var(--s1);color:#fff;font-weight:600}
 .btn.pri:hover{background:#4a95ee}
 .btn.dng{color:#ff9b93;border-color:rgba(211,59,59,.5)} .btn.dng:hover{background:rgba(211,59,59,.15)}
 .btn:disabled{opacity:.4;cursor:default}
 .btn svg{display:block;flex:none}
 .btnrow{display:flex;gap:8px} .btnrow .btn{flex:1}
 .btnrow .btn.sm{flex:0 0 auto}
 select{background:var(--surface2);color:var(--ink);border:1px solid var(--line);border-radius:8px;
  height:38px;padding:0 28px 0 10px;font-size:13px;width:100%;outline:none;font-family:inherit;margin-bottom:11px;
  appearance:none;-webkit-appearance:none;cursor:pointer;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'%3E%3Cpath d='M1 1l4 4 4-4' stroke='%238a8a82' stroke-width='1.6' fill='none' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:right 10px center}
 select:hover{border-color:rgba(255,255,255,.28)}
 select:focus{border-color:var(--s1)}
 label.fld,.fld{display:block;font-size:11px;color:var(--muted);margin:0 0 4px}
 .ck{display:inline-flex;align-items:center;gap:6px;font-size:12.5px;color:var(--ink2);cursor:pointer}
 .ck input{accent-color:var(--s1);width:14px;height:14px;margin:0}
 input.num:disabled,select:disabled{opacity:.55}
 .fgroup{font-size:10px;letter-spacing:.9px;color:var(--muted);font-weight:700;margin:10px 0 6px}
 .fgrid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
 .outGrid{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-bottom:11px}
 .outOpt{display:flex;align-items:center;gap:8px;min-width:0;padding:8px 9px;border:1px solid var(--line);
  border-radius:9px;background:rgba(255,255,255,.018);cursor:pointer;transition:background .12s,border-color .12s}
 .outOpt:hover{background:#2c2c29;border-color:rgba(255,255,255,.2)}
 .outOpt:has(input:checked){border-color:rgba(57,135,229,.72);background:rgba(57,135,229,.10)}
 .outOpt:has(input:disabled){opacity:.55;cursor:default}
 .outOpt input{accent-color:var(--s1);width:15px;height:15px;margin:0;flex:none}
 .outOpt span{display:flex;flex-direction:column;gap:1px;min-width:0}
 .outOpt b{font-size:11.5px;color:var(--ink);font-weight:650;white-space:nowrap}
 .outOpt small{font-size:9.5px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
 /* 라벨 왼쪽 · 작은 입력 오른쪽 (보정·초기값처럼 값이 짧은 항목) */
 .frows{display:flex;flex-direction:column;gap:4px}
 .frow{display:flex;align-items:center;justify-content:space-between;gap:10px}
 .frow .fld{margin:0;flex:1;min-width:0;font-size:11.5px;color:var(--ink2);
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 input.num.sm{width:94px;flex:none;height:27px;padding:0 7px;font-size:12px;text-align:right}
 #slots{display:grid;grid-template-columns:1fr 1fr;gap:7px}
 .dstat{border:1px solid var(--line);border-radius:9px;padding:8px 10px;background:rgba(255,255,255,.018);
  font-size:10.5px;color:var(--ink2);line-height:1.5;display:flex;flex-direction:column;gap:3px;min-width:0}
 .dstat b{font-size:11.5px;color:var(--ink)}
 .dstat .sst{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 .slot{border:1.5px dashed rgba(255,255,255,.2);border-radius:9px;padding:8px 10px;cursor:pointer;
  font-size:10.5px;color:var(--ink2);line-height:1.5;display:flex;flex-direction:column;gap:3px;
  transition:border-color .13s,background .13s}
 .slot:hover,.slot.over{border-color:var(--s1);background:rgba(57,135,229,.07);color:var(--ink)}
 .slot b{font-size:11.5px;color:var(--ink)}
 .sst{font-size:10px;color:var(--muted)}
 .sst.ok{color:#31c46a;font-weight:700}
 body,body *{user-select:none;-webkit-user-select:none}
 body input:not([type=checkbox]):not([type=radio]):not([type=range]):not([type=button]):not([type=submit]),body textarea,body [contenteditable=true],body .settings-row output,body .ds-cursor,body .ds-cursor *,body.execution-viewer #tlab{user-select:text;-webkit-user-select:text}
 summary{cursor:pointer;user-select:none;outline:none}
 input.num{background:var(--surface2);color:var(--ink);border:1px solid var(--line);border-radius:8px;
  height:31px;padding:0 9px;font-size:12.5px;width:100%;outline:none;font-family:inherit}
 input.num:focus{border-color:var(--s1)}

 /* ── 진행 상황 ── */
 .ptxt{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:7px}
 .ptxt b{font-size:19px;font-weight:700;font-variant-numeric:tabular-nums}
 .ptxt b .un{font-size:12px;color:var(--ink2);font-weight:400}
 .ptxt .pc{font-size:13px;color:var(--s1);font-weight:700;font-variant-numeric:tabular-nums}
 .pbar{height:8px;background:#111110;border:1px solid var(--grid);border-radius:5px;overflow:hidden}
 .pbar>div{height:100%;background:linear-gradient(90deg,var(--s1),#6db1f5);width:0%;transition:width .5s}
 .meta{display:flex;justify-content:space-between;font-size:11.5px;color:var(--muted);margin-top:7px;
  font-variant-numeric:tabular-nums}
 .meta b{color:var(--ink2);font-weight:600}

 /* ── 차트 ── */
 #chartBox{margin-top:14px}
 #chartBox .lab{font-size:11px;color:var(--muted);margin-bottom:6px;display:flex;justify-content:space-between}
 #spark,#vchart{width:100%;height:236px;display:block;background:#161615;border:1px solid var(--grid);border-radius:8px}
 #viz{position:absolute;inset:0}
 #dash{position:absolute;inset:0;padding:16px;display:flex;flex-direction:column;gap:13px;overflow:auto;background:var(--page)}
 .dcard{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px 17px}
 .mgrid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
 @media(max-width:1180px){.mgrid{grid-template-columns:repeat(2,1fr)}}
 .mlab{display:flex;justify-content:space-between;align-items:baseline;font-size:10.5px;color:var(--muted);margin-bottom:5px}
 .mlab b{font-size:12px;color:var(--ink);font-variant-numeric:tabular-nums}
 svg.mchart{width:100%;height:64px;display:block}
 /* 작은 노트북(세로 860px 이하)에서도 사이드바 전체 스크롤 없이 리스트만 스크롤 */
 @media(max-height:880px){
  section{padding:10px 14px 11px}
  .fgroup{margin:8px 0 5px}
  input.num{height:29px}
  input.num.sm{height:25px}
  .frows{gap:3px}
  .fgrid{gap:7px}
  #runIdle .btn,#runBusy .btn{height:36px!important}
  #side #projList,#side #projList2{min-height:86px;max-height:40vh}
  #side select{height:32px;margin-bottom:8px}
  #cfgToggle{height:32px}
  #side .slot{padding:6px 9px}
  #side .btn{height:34px}
 }
 @media(max-height:780px){
  section{padding:8px 13px 9px}
  .fgroup{margin:6px 0 4px}
  input.num{height:27px}
  input.num.sm{height:24px}
  #side #projList,#side #projList2{min-height:76px}
  #side select{height:30px;margin-bottom:6px}
  #cfgToggle{height:30px}
  #side .slot{padding:5px 8px}
  #side .btn{height:32px}
  h2{margin:0 0 8px}
 }
 .drow1{display:flex;align-items:baseline;gap:22px;flex-wrap:wrap}
 .dbig b{font-size:35px;font-weight:700;font-variant-numeric:tabular-nums}
 .dbig .un{font-size:15px;color:var(--ink2);font-weight:400}
 .dbig .pc{font-size:20px;color:var(--s1);font-weight:700;margin-left:12px;font-variant-numeric:tabular-nums}
 .dstats{display:flex;gap:22px;margin-left:auto;font-size:12.5px;color:var(--muted);align-items:baseline;flex-wrap:wrap}
 .dstats b{color:var(--ink);font-size:16.5px;font-variant-numeric:tabular-nums}
 .dlab{display:flex;justify-content:space-between;font-size:11px;color:var(--muted);letter-spacing:.8px;margin-bottom:9px;font-weight:700}
 .dgrid{display:grid;grid-template-columns:1.55fr 1fr;gap:13px}
 .dlog{flex:1;display:flex;flex-direction:column;min-height:130px}
 .dlog pre{flex:1;max-height:none;margin:0}
 .lg{display:flex;flex-wrap:wrap;gap:4px 13px;margin-top:8px}
 .lg span{display:inline-flex;align-items:center;gap:5px;font-size:11.5px;color:var(--ink2);
  font-variant-numeric:tabular-nums}
 .sw{width:9px;height:9px;border-radius:2.5px;display:inline-block;flex:none}

 /* ── 로그 (접기 가능) ── */
 details{margin-top:13px}
 summary{cursor:pointer;font-size:11px;color:var(--muted);letter-spacing:.6px;user-select:none;outline:none}
 summary:hover{color:var(--ink2)}
 pre#mLog{background:#111110;border:1px solid var(--grid);border-radius:7px;padding:10px;font-size:10.5px;
  line-height:1.55;max-height:170px;overflow:auto;white-space:pre-wrap;color:#a4a49b;
  font-family:Consolas,"D2Coding",monospace;margin:8px 0 0}
 pre#mLog .hl{color:#7db4f5}

 /* ── 뷰포트 ── */
 #gl{position:absolute;inset:0;width:100%;height:100%;cursor:grab}
 #rcol{position:absolute;top:14px;right:14px;display:flex;gap:9px;align-items:flex-start;
  max-height:calc(100% - 88px)}
 #legcol{display:flex;flex-direction:column;gap:9px;align-items:stretch}
 /* 좌상단 그래프 카드 — 켜진 항목만 위에서부터 차례로 배치(유동적) */
 #gcol{position:absolute;top:14px;left:14px;display:flex;flex-direction:column;gap:9px;
  align-items:stretch;max-height:calc(100% - 96px);pointer-events:none}
 .gcard{background:rgba(26,26,25,.85);border:1px solid var(--line);border-radius:10px;
  padding:8px 10px 7px;backdrop-filter:blur(8px);width:274px}
 .gcard .gtit{display:flex;justify-content:space-between;align-items:baseline;font-size:10px;
  color:var(--muted);margin-bottom:4px}
 .gcard .gtit b{font-size:11.5px;color:var(--ink);font-variant-numeric:tabular-nums}
 .gcard svg{width:100%;height:62px;display:block}
 .gcard .glg{display:grid;grid-template-columns:1fr 1fr;gap:3px 8px;margin-top:6px;font-size:9.5px;color:var(--muted)}
 .gcard .glg span{display:flex;align-items:center;gap:4px;white-space:nowrap;overflow:hidden}
 .gcard .glg i{width:8px;height:8px;border-radius:2px;flex:none}
 .gcard .glg b{color:var(--ink);font-variant-numeric:tabular-nums}
 #lcol{display:flex;flex-direction:column;gap:9px;align-items:stretch;width:240px;flex:none;min-height:0;max-height:calc(100vh - 152px)}
 #hud{flex:none}#vlegend{min-height:0}
 #hud{background:rgba(26,26,25,.85);border:1px solid var(--line);
  backdrop-filter:blur(8px);border-radius:11px;padding:10px 14px;min-width:238px}
 .hgrp+.hgrp{margin-top:8px;padding-top:8px;border-top:1px solid var(--grid)}
 .htit{font-size:9.5px;letter-spacing:1px;color:var(--muted);font-weight:700;margin-bottom:4px}
 .hrow{display:flex;gap:13px;font-size:11.5px;color:var(--ink2);flex-wrap:wrap}
 .hrow b{font-size:13.5px;color:var(--ink);font-variant-numeric:tabular-nums;font-weight:700}
 .hgrp.live .hrow b{color:#7db4f5}
 .hgeo{margin-top:8px;padding-top:7px;border-top:1px solid var(--grid);font-size:10px;color:var(--muted)}
 #vlegend{background:rgba(26,26,25,.85);backdrop-filter:blur(8px);overflow-y:auto;
  border:1px solid var(--line);border-radius:10px;padding:9px 12px;font-size:11px;color:var(--ink2);min-width:186px}
 #flowControls{display:flex;align-items:center;gap:8px;padding-bottom:10px;margin-bottom:10px;border-bottom:1px solid var(--line)}
 #flowControls label{flex:none;color:var(--muted)}
 #flowDensity{flex:1;min-width:0;padding:5px 8px;border:1px solid var(--line);border-radius:7px;background:var(--surface2);color:var(--ink);font:inherit}
 #vlegend .ltit{font-size:10px;letter-spacing:.8px;color:var(--muted);margin-bottom:6px;font-weight:700}
 #vlegend label{display:flex;align-items:center;gap:6px;padding:2.5px 0;cursor:pointer;user-select:none}
 #vlegend label:hover{color:var(--ink)}
 #vlegend input{accent-color:var(--s1);width:13px;height:13px;margin:0;flex:none}
 #vlegend label.off2{opacity:.4;cursor:default}
 .mini{margin-left:auto;background:none;border:1px solid var(--line);color:var(--ink2);border-radius:6px;
  padding:3px 9px;font-size:10.5px;cursor:pointer;font-family:inherit;letter-spacing:0}
 .mini:hover{background:var(--surface2);color:var(--ink)}
 #cfgBg{position:fixed;inset:0;background:rgba(0,0,0,.55);display:none;align-items:center;justify-content:center;z-index:70}
 #cfgBox{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:20px 22px;width:680px;
  max-height:84vh;overflow-y:auto;box-shadow:0 18px 60px rgba(0,0,0,.6)}
 #cfgBox h3{margin:0 0 4px;font-size:14.5px;display:flex;align-items:center;gap:8px}
 #cfgBox .src{font-size:11px;color:var(--muted);margin-bottom:12px}
 #cfgBox .cfgRuntime{background:rgba(57,135,229,.09);border:1px solid rgba(90,158,238,.28);border-radius:8px;
  padding:10px 14px;margin:10px 0 9px}
 #cfgBox .cfgRuntime .cr{grid-template-columns:minmax(130px,.75fr) minmax(0,2.25fr) 0;align-items:start}
 #cfgBox .cfgRuntime .cr em{text-align:left;font-weight:650}
 #cfgBox .cfgRuntime .rawPath{font:11px/1.55 Consolas,"Malgun Gothic",monospace;font-weight:500;word-break:break-all}
 #cfgBox table{width:100%;border-collapse:collapse;font-size:12px}
 #cfgBox th{background:var(--surface2);color:var(--muted);font-size:10.5px;letter-spacing:.8px;text-align:left;
  padding:6px 9px;border-top:1px solid var(--grid)}
 #cfgBox td{padding:5px 9px;border-top:1px solid #232320;vertical-align:top}
 #cfgBox td:first-child{color:var(--ink2);white-space:nowrap;width:128px}
 #cfgBox td b{font-variant-numeric:tabular-nums;font-weight:600}
 #cfgBox .st{color:#ff8f8f;font-weight:700}
 #cfgBox .cfghint{font-size:11px;color:var(--muted);margin-top:11px;line-height:1.6}
 /* config.json 생성 · 정보 안내 공용 창 */
 .mbg{position:fixed;inset:0;background:rgba(0,0,0,.6);display:none;align-items:center;justify-content:center;z-index:88}
 .mbox{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:18px 20px;
  max-height:86vh;overflow-y:auto;box-shadow:0 18px 60px rgba(0,0,0,.6)}
 .mbox h3{margin:0 0 3px;font-size:14.5px;display:flex;align-items:center;gap:8px}
 .mbox h3 .x{margin-left:auto}
 .mhint{font-size:11px;color:var(--muted);line-height:1.65;margin:0 0 12px}
 .tabs{display:flex;gap:6px;margin:10px 0 14px}
 .tabs button{flex:1;background:var(--surface2);border:1px solid var(--line);color:var(--ink2);
  border-radius:8px;padding:8px 6px;font-size:12px;font-weight:600;cursor:pointer;font-family:inherit}
 .tabs button.on{background:var(--acc);border-color:var(--acc);color:#fff}
 .cbg{margin:0 0 12px}
 .cbg>.t{font-size:11px;letter-spacing:.8px;color:var(--muted);font-weight:700;
  padding:5px 0 5px;border-bottom:1px solid var(--grid);margin-bottom:7px}
 .cbg .n{font-size:10.5px;color:var(--muted);line-height:1.55;margin:-2px 0 7px}
 .cbr{display:flex;align-items:center;gap:9px;padding:3px 0}
 .cbr label{flex:1;font-size:12px;color:var(--ink2);min-width:0}
 .cbr label i{display:block;font-style:normal;font-size:10.5px;color:var(--muted)}
 .cbr input,.cbr select{width:168px;flex:none;height:30px;background:var(--surface2);border:1px solid var(--line);
  border-radius:7px;color:var(--ink);padding:0 9px;font-size:12px;font-family:inherit;text-align:right}
 .cbr input:focus,.cbr select:focus{outline:none;border-color:var(--acc)}
 .cbr .u{width:44px;flex:none;font-size:10.5px;color:var(--muted)}
 .ibx{font-size:12.5px;line-height:1.8;color:var(--ink2)}
 .ibx b{color:var(--ink)} .ibx h4{margin:14px 0 5px;font-size:12.5px;color:var(--ink)}
 .ibx ul{margin:4px 0 10px;padding-left:17px} .ibx li{margin:3px 0}
 .ibx table{width:100%;border-collapse:collapse;font-size:12px;margin:6px 0 10px}
 .ibx td{padding:5px 9px;border-top:1px solid #232320}
 .ibx td:first-child{color:var(--muted);white-space:nowrap;width:78px}
 .kv{background:var(--surface2);border:1px solid var(--line);border-radius:9px;padding:11px 14px;margin:8px 0}
 .badge{display:inline-block;background:var(--acc);color:#fff;border-radius:6px;padding:1px 7px;font-size:10.5px;font-weight:700}
 .exgrid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:12px}
 .excard{background:var(--surface2);border:1px solid var(--line);border-radius:11px;padding:13px 14px;min-width:0}
 .excard.wide{grid-column:1/-1}
 .excard h4{margin:0 0 5px;font-size:13px;color:var(--ink)}
 .excard p{margin:0 0 10px;font-size:11px;line-height:1.55;color:var(--muted)}
 .excard select{margin-bottom:8px}
 .excard .btnrow{margin-top:3px}
 .exnote{font-size:10.5px;color:#c9a86b;line-height:1.5;margin-top:8px}
 #settingsBtn,#infoBtn{width:26px;height:26px;flex:none;border-radius:50%;border:1px solid var(--line);background:var(--surface2);
  color:var(--ink2);font-size:13px;font-weight:700;cursor:pointer;font-family:inherit;line-height:1;
  display:inline-flex;align-items:center;justify-content:center;padding:0;box-sizing:border-box}
 #settingsBtn svg{display:block;flex:none}
 #settingsBtn{margin-left:10px;font-size:14px} #infoBtn{margin-left:6px}
 #settingsBtn:hover,#infoBtn:hover{border-color:var(--acc);color:var(--acc)}
 .setrow{display:grid;grid-template-columns:170px minmax(0,1fr);gap:16px;align-items:center;padding:12px 0;border-bottom:1px solid var(--grid)}
 .setrow label{font-size:12.5px;font-weight:700;color:var(--ink)}
 .setrow label span{display:block;margin-top:4px;font-size:10.5px;line-height:1.45;font-weight:400;color:var(--muted)}
 .setrow input,.setrow select{width:100%;height:36px;margin:0}
 .setpath{display:grid;grid-template-columns:minmax(0,1fr) 76px;gap:7px}
 .setpath .btn{height:36px;padding:0 10px}
 .settingHead{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:0 0 7px}
 .settingHead>span{font-size:13px;font-weight:700;letter-spacing:.6px;color:var(--ink)}
 .settingHead .mini{margin-left:0;font-size:11px;padding:4px 9px}
 .cfgDrop{position:relative;display:grid;grid-template-columns:minmax(0,1fr) 38px;gap:6px;margin-bottom:7px}
 #cfgPick{display:none}
 #cfgToggle{width:100%;height:36px;display:flex;align-items:center;justify-content:space-between;gap:10px;
  padding:0 10px;background:var(--surface2);color:var(--ink);border:1px solid var(--line);border-radius:8px;
  cursor:pointer;font:12.5px/1.2 inherit;text-align:left}
 #cfgToggle:hover{border-color:rgba(255,255,255,.28)}
 #cfgToggle:disabled{opacity:.55;cursor:default}
 #cfgAdd{width:38px;height:36px;border:1px solid var(--line);border-radius:8px;background:var(--surface2);color:var(--ink2);
  cursor:pointer;font:20px/1 inherit;display:flex;align-items:center;justify-content:center}
 #cfgAdd:hover{border-color:var(--acc);color:var(--acc)}
 #cfgAdd:disabled{opacity:.4;cursor:default}
 #cfgToggle .arr{font-size:12px;color:var(--muted);transition:transform .12s}
 #cfgToggle.open .arr{transform:rotate(180deg)}
 #cfgMenu{display:none;position:absolute;left:0;right:44px;top:calc(100% + 5px);z-index:45;
  max-height:190px;overflow-y:auto;overscroll-behavior:contain;padding:5px;background:#20201f;
  border:1px solid var(--line);border-radius:9px;box-shadow:0 12px 34px rgba(0,0,0,.55);scrollbar-gutter:stable}
 #cfgMenu.open{display:block}
 #cfgMenu::-webkit-scrollbar{width:8px} #cfgMenu::-webkit-scrollbar-track{background:#181817;border-radius:7px}
 #cfgMenu::-webkit-scrollbar-thumb{background:#464642;border-radius:7px;border:2px solid #181817}
 .cfgOpt{display:flex;align-items:center;gap:5px;border-radius:7px;min-width:0}
 .cfgOpt+.cfgOpt{margin-top:3px}
 .cfgChoose{height:32px;flex:1;min-width:0;border:1px solid transparent;background:transparent;color:var(--ink2);
  border-radius:7px;padding:0 9px;text-align:left;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
  cursor:pointer;font:12px/1 inherit}
 .cfgChoose:hover,.cfgOpt.on .cfgChoose{background:rgba(57,135,229,.10);color:var(--ink);border-color:rgba(57,135,229,.30)}
 .cfgTrash{width:30px;height:30px;flex:none;border:1px solid transparent;border-radius:7px;background:transparent;
  color:#a7a69f;cursor:pointer;font:13px/1 inherit}
 .cfgTrash:hover{color:#ff9a92;border-color:rgba(255,100,100,.34);background:rgba(255,80,80,.10)}
 .baseRow{display:block}
 .baseSlot{height:60px;min-width:0;padding:9px 11px!important;display:flex!important;flex-direction:column!important;
  align-items:stretch!important;justify-content:center!important;gap:4px!important;overflow:hidden}
 .baseTitle{font-size:11.5px;line-height:18px;min-height:18px;font-weight:650;color:var(--ink);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 .baseMeta{display:flex;align-items:center;gap:6px;min-width:0;line-height:1}
 .baseState{display:inline-flex;align-items:center;gap:4px;color:var(--muted);font-size:10px;white-space:nowrap;flex:none}
 .baseState::before{content:"";width:5px;height:5px;border-radius:50%;background:var(--muted);flex:none}
 .baseState.ok{color:#45cf78;font-weight:700}
 .baseState.ok::before{background:#31c46a;box-shadow:0 0 0 3px rgba(49,196,106,.10)}
 .baseName{min-width:0;max-width:none;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
  color:var(--ink2);font:10px/18px Consolas,"Malgun Gothic",monospace;background:rgba(255,255,255,.055);
  border:1px solid rgba(255,255,255,.07);border-radius:5px;padding:0 6px}
 .baseCount{margin-left:auto;color:var(--muted);font-size:9.5px;white-space:nowrap;flex:none}
 #cbAdd{display:none}
 #runIdle,#runBusy{margin-top:14px;margin-bottom:12px}
 #cfgBox .cgrp{background:var(--surface2);border:1px solid var(--grid);border-radius:11px;padding:11px 14px;margin-bottom:9px}
 #cfgBox .ct{font-size:10px;letter-spacing:1.1px;color:#6da7ec;font-weight:700;margin-bottom:5px}
 #cfgBox .cr{display:grid;grid-template-columns:minmax(150px,1fr) minmax(0,1.6fr) 62px;align-items:baseline;gap:10px;padding:4.5px 0;font-size:12.3px}
 #cfgBox .cr+.cr{border-top:1px solid rgba(255,255,255,.05)}
 #cfgBox .cr span{color:var(--ink2);min-width:0}
 #cfgBox .cr em{font-style:normal;color:var(--ink);text-align:right;font-variant-numeric:tabular-nums;line-height:1.45;min-width:0;overflow-wrap:anywhere}
 #cfgBox .cr small{color:var(--muted);font-size:10.5px;text-align:left;white-space:nowrap}
 #cfgBox .cfghint{display:none}
 @media(max-width:600px){#cfgBox{width:calc(100vw - 24px);padding:16px}#cfgBox .cr{grid-template-columns:minmax(112px,1fr) minmax(0,1.25fr) 52px;gap:7px;font-size:11.5px}#cfgBox .cfgRuntime .cr{grid-template-columns:112px minmax(0,1fr) 0}}
 #controls{position:absolute;left:50%;transform:translateX(-50%);bottom:16px;display:flex;gap:11px;align-items:center;
  background:rgba(26,26,25,.88);backdrop-filter:blur(8px);border:1px solid var(--line);border-radius:999px;
  padding:9px 16px;width:min(880px,calc(100% - 32px));max-width:calc(100% - 32px);box-sizing:border-box}
 #tbar{width:min(420px,40vw);min-width:30px;flex:1 1 auto;accent-color:var(--s1)}
 #controls #btnExport{height:32px;padding:0 12px;border-radius:16px;flex:none;white-space:nowrap}
 #controls #btnExport.recording{color:var(--s3);border-color:var(--s3)}
 #tlab{font-size:12.5px;min-width:80px;white-space:nowrap;font-variant-numeric:tabular-nums;color:var(--ink2)}
 #controls select{width:88px;height:30px;margin:0;font-size:12px;background-position:right 8px center;padding:0 24px 0 10px}
 .iconbtn{width:36px;height:36px;border-radius:50%;display:flex;align-items:center;justify-content:center;
  background:var(--s1);border:none;cursor:pointer;transition:background .12s;flex:none}
 .iconbtn:hover{background:#4a95ee}
 #empty{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;pointer-events:none}
 #empty .box{background:rgba(26,26,25,.92);border:1px solid var(--line);border-radius:14px;padding:28px 36px;
  text-align:center;max-width:460px;pointer-events:auto}
 #empty h3{margin:12px 0 6px;font-size:15.5px} #empty p{margin:0 0 4px;color:var(--ink2);font-size:12.5px;line-height:1.7}
 #empty .steps{text-align:left;margin:15px auto 0;display:inline-block;color:var(--ink2);font-size:12.5px;line-height:2.1}
 #empty .steps b{color:var(--s1);margin-right:8px;font-variant-numeric:tabular-nums}
 #empty .steps .k{background:var(--surface2);border:1px solid var(--line);border-radius:5px;padding:1px 6px;
  font-size:11px;font-family:Consolas,monospace}
 #drop{position:fixed;left:0;top:52px;bottom:0;width:341px;display:none;align-items:center;justify-content:center;z-index:20;
  background:rgba(57,135,229,.13);border:2.5px dashed var(--s1);border-radius:16px;pointer-events:none;
  font-size:19px;font-weight:600;color:#bcd9ff}

 /* ── 토스트/모달 ── */
 body.grouped.execution-viewer:not(.data-sheet-viewer) #toasts{bottom:84px}
 #toasts{position:fixed;right:16px;bottom:16px;display:flex;flex-direction:column;gap:8px;z-index:60}
 .toast{background:var(--surface);border:1px solid var(--line);border-left:3px solid var(--s1);border-radius:9px;
  padding:12px 16px;font-size:12.5px;min-width:250px;box-shadow:0 8px 26px rgba(0,0,0,.5);animation:in .18s ease-out}
 .toast.err{border-left-color:var(--crit)}
 @keyframes in{from{transform:translateY(8px);opacity:0}}
 #modalBg{position:fixed;inset:0;background:rgba(0,0,0,.55);display:none;align-items:center;justify-content:center;z-index:70}
 #modal{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:22px;max-width:410px;
  box-shadow:0 18px 60px rgba(0,0,0,.6)}
 #modal h3{margin:0 0 9px;font-size:14.5px} #modal p{margin:0 0 18px;color:var(--ink2);font-size:12.5px;line-height:1.65}
 #modal .row{display:flex;gap:8px;justify-content:flex-end}
 @media(max-width:1100px){
  #envPath,#appContext,#hdr .pill{display:none}
 }
 @media(max-width:700px){
  #hdr{display:grid;grid-template-columns:minmax(0,1fr) auto;height:88px;gap:4px 8px;padding:8px 10px}
  #logo{grid-column:1;grid-row:1;white-space:nowrap;font-size:13px}
  #logo img,#logo span,#infoBtn{display:none}
  #settingsBtn{grid-column:2;grid-row:1;justify-self:end;margin:0}
  #modeSeg{grid-column:1;grid-row:2;justify-self:start}
  #app{height:calc(100% - 88px)}
  body:is(.tracerView,.grouped.execution-viewer) #app{flex-direction:column}
  body:is(.tracerView,.grouped.execution-viewer) #side{width:100%;min-width:0;flex:0 0 140px;border-bottom:1px solid var(--line)}
  body:is(.tracerView,.grouped.execution-viewer) #main{min-height:0;min-width:0;border-left:0}
  body:is(.tracerView,.grouped.execution-viewer) #rcol{left:8px;right:8px;top:8px;gap:6px;max-height:220px;overflow:auto}
  body:is(.tracerView,.grouped.execution-viewer) #lcol{min-width:0;flex:1;gap:5px}
  body:is(.tracerView,.grouped.execution-viewer) #hud,body:is(.tracerView,.grouped.execution-viewer) #vlegend{min-width:0;border-radius:6px;padding:7px}
  body:is(.tracerView,.grouped.execution-viewer) #vlegend{display:grid;grid-template-columns:1fr 1fr;gap:3px}
  body:is(.tracerView,.grouped.execution-viewer) #flowControls{display:flex;align-items:center;gap:8px;padding-bottom:10px;margin-bottom:10px;border-bottom:1px solid var(--line)}
 #flowControls label{flex:none;color:var(--muted)}
 #flowDensity{flex:1;min-width:0;padding:5px 8px;border:1px solid var(--line);border-radius:7px;background:var(--surface2);color:var(--ink);font:inherit}
 #vlegend .ltit{grid-column:1 / -1;margin:2px 0}
  body:is(.tracerView,.grouped.execution-viewer) #vlegend label{min-width:0;font-size:10px}
  body:is(.tracerView,.grouped.execution-viewer) #tcbar{max-width:88px;padding:7px;border-radius:6px}
  body:is(.tracerView,.grouped.execution-viewer) #tcbar .grad{height:94px}
  body:is(.tracerView,.grouped.execution-viewer) #controls{left:8px;right:8px;bottom:8px;transform:none;width:auto;max-width:none;gap:7px;padding:8px;border-radius:8px;flex-wrap:wrap}
  body:is(.tracerView,.grouped.execution-viewer) #tbar{min-width:30px;width:auto;flex:1}
  body:is(.tracerView,.grouped.execution-viewer) #tlab{min-width:0;font-size:11px}
  body:is(.tracerView,.grouped.execution-viewer) #speed{width:62px}
 }
#warehouseDetails{border-top:1px solid var(--line);margin-top:9px;padding-top:4px}#warehouseDetails summary{cursor:pointer;padding:7px 0;font-size:11px;color:var(--ink2)}#warehouseDetails p{font-size:10px;line-height:1.55;white-space:pre-wrap;overflow-wrap:anywhere}.wh-inputs{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:5px}#warehouseDetails .wh-inputs label{display:grid;font-size:10px;gap:3px;margin:0}#warehouseDetails input{width:100%;min-width:0;height:28px;padding:4px;font-size:11px;background:var(--surface2);border:1px solid var(--line);border-radius:5px;color:var(--ink)}#warehouseDetails button{margin:7px 0}body.grouped #hLiveG,body.grouped #vizWarn{display:none!important}
</style></head>
<body>
<div id="hdr">
  <div id="logo">
    <img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAALgAAABACAYAAACp8r2zAAA1QklEQVR42u29e5xcR3Unfk7Vvbfv7cd0z/RMPzSSbGzLWJbWYMsxb5B+2dhgCCEBCQg2JFkCJMsjEDALGEtyMCR8AiTgJZDgBQJJsAQsLJhgIEiEBfOQjU0kY0vYskfS9O2e7un3fVed/UNVoj2eGUmWZPz5RfX53M9IfR/1OnXqPL+F8DgXIkIAYIgoAABqtdo6wzCuR0Q7SZLbKpXKp9RzBgAIRKQz2A7YvXs337hxo0REudgzi9Wv+wAAoPux4L6xc+dO2rx5s1yi/bh161bctm0bbNu2DQAAtm3bRup7tKAe1M8s9dzWrVvZyH0AAFrwHb5z507YsmWLWKQfuh2EiAAAdJxnlm3fUmVhu4mIHe+9hfWNztu2bdtwYV+JCHfv3s0BADZu3HjGaGcpgmK6cQAAMzMzE81mc2ur1Zrr9/vU6/Wo1+tRq9X6yqFDh9Ys9d7pasvC3w4fPlxst9vnHj58eNXs7OzUrl27jBN5d35+Pt9sNlfWarVzm83m9MzMjDN6f5T4HueCC9t6usfxiVIUjSw6zvh4c2wiKjYajasNw3hPJpN58nA4hCRJhB78fD7PfN9vCiGu931/5+rVq+dPd3sQkb7xjW+knvGMZ1SjKHoZIj5XSrkGEScBICaigW3bbhiG7yuXy98iIoaIcuvWrWz79u1y//79YxMTEy8VQvw2AFxAREUAsBDRR8Q6ANwLAF9oNBo/Xr9+/byuU/+dm5u7SEr5QcaYIaUkIpKFQsFst9u3VKvVnURkImLcaDQuRcT3CSH0TiIKhYLV7XY/XSqVblVjlqrX6/9kGIYjhCCiY0wrrXYZYZrmvO/7n1m5cuXXdV+azeZYkiQfS6VSU1EUxYVCIdXtdm8qlUrf37Vrl7Fp06Zkz5495qpVqz5jWdZ4GIYik8kYnud9pFwuf2t+fj4fRdHfpFKpyTAMCREfRWR6zqWUolgsGvPz87sqlcqHZmdnN5im+RdCCP0cEZFUO4ieJ7AsC8Mw/HC1Wv2u+ja5rvv3tm2vDMNQ77gcEW01Fj7nvCeEuCOKoh233HJL7YwSNhFx/f/Z2dm1rVbr861WK5ifn6dut0uu6yau68p6vU76cl03abVa1G63aW5ubui67sd7vd6k+t4pLUjNTWdnZ9e22+2fz8/Ph91ul4bDIUVRRJ7nked5NBwOiYio0Wh8WvXF1JNXq9W2tNvtRqfTIc/zSAhBvu8f+4b+99zcHHU6naHrun+sxQQ9Hq7rvtj3/WPPDgYDXd8PRp9rNBofJSLq9XrkeR71ej393Hv1GM/NzeXm5uYoiqJjbSAiUguHPM+jIAio2+1SrVb7bT0Wc3NzK+r1ejdJEhoMBuT7PtVqtU0j4iHUarWM67p+kiTH6q7X67+n+nBes9mk0eJ5Hvm+f6zOhaXRaHxcffcVcRwfG2/d5sVKvV5/6cj4oeu6s0REg8GAwjB8RF+jKDrW13a7HdXr9dcYZ4q4Ncc5fPhwMZfLvSWO4zen0+l8v98HKSUp2Ykv8jqL4zi2LMvM5XLpbrd7aRRFtpa7FsqIJ7mT0Jvf/OZVQojbLcta1e/3AQBkJpNh7XZ7lxDiVsMwukQ0GQTBS4joF79iRihnZ2evzmQyt8ZxDEmSyDiOWb/f301EXyWiGmPsv3LOX2wYRilJkiSTyaSDIHh3rVb7ZwDw7rzzTq1XrEqSRHielxCRBQDC932UUv4XALARcdjpdMaDIHhVq9VKkiThACARMUqn0xYADHS/1Fh2ut1uljEGg8HgCCL+PQDMCSGea1nWy5MkEfl83g6C4LUA8DX1XhoR/Xa7nQEASJKkiYgP6+FSY5ZGxH632zXiOBaMMUMI0QQACILAt21753A4nPA8b0ZKaTiO80rf96VhGEwIMUDEW4hogIjn2La9MkmSrwMAmKaZ9Pv9JIoiYowhAHQB4KdEtE9KGQAAMcYyjLH/QkT7dVcZY1Sr1TqdTqekFsUAAD4CALOMsRVE9EbO+XiSJJROp00A+FPjDBA3R0Sxa9cu46lPfeqrAeCdqVTqwjiOodvtCkTkeHQvwkXeFZxznsvlzH6//0Cn03lvpVL5F02g27dvl6fQNIaIYnZ29sbJyclV8/PzESKanHMYDofXVyqVmxY8f/PIYo2UbP1hIoIkSRLTNHkcx28ql8s3j7xza6PR+CAAfMlxnHW9Xi/O5XLnDgaDqxDxyzMzMwYAxIi4Mp1O8+FwCIjYJaIs55wLIWSj0UAiwmazebXjOBO+7xMiNomoqEQXLqVcOHZcSmlkMhno9Xo/LZfL71e//4Pruk+ybftZcRwDAOQ085FSphhjKUTknHMQQoSI6I1+1DCMgpTS1hwdADhjLAYAOOecc1xE3KKfrdfrz3Ic59ogCCLTNI0kSZrlcvnti01EHMc5x3EMAEiy2azR7/d/UC6Xf2dZheKoGMPr9boJANy2bfB9/+FKpXKjfqbRaPwilUrtSJJEep5HAHA5O92CPiKKw4cPr7rkkku+Y1nWLYh4YbvdFkmSLMWxgYgkAIh8Ps8BwO90On+JiJdVKpV/0aKJ6uBjUjhH2nVhOp1+Sa/XEwDAstksCiE+VqlUbiIitmvXLkPVwfWWCAAcAMCyrJeMjY092ff9OJPJGHEcf6pcLt9MRIZ6lhGRVSqVDvT7/bcwxtiI1eAqxfWk5rpCCLBtmxPRtxHxsGEYAACmEKKIiJQkye+bpkm2bSMi3oKIA7VIYXQcTdPU7QTGGBCRv4AwbCklMMaIiGJtWUDEMSLKCCFINTXodruPIHAppQMAx5gg54+YPkZEfP/+/Ski4lLKwoj8r5VcPjI+hl4ojLEsYwwQUcvd/mJKsJ5v/fvs7Ow4ADhSSlDjEO7Zs+eY+CilbBMRIGLiOA4g4i52OsSRHTt2cNVYWa/XX2ZZ1u50Ov28Xq8ngiCQjDHNtRclbsdxmOM4vNfrfTVJkisqlcq7Jicne2o3oJGdQT5G0w+qSV2XTqcLSZJIy7KM4XDYklK+Xw/Qpk2bElWHUNdoXU9JpVKkCBWI6GNExHbu3EnqWakUVLZy5cofD4fD/7Bt2/R9H4noaiJia9asSTRdSinBtm1AxLsQcUcqlQLOeRoALq7VaiXLsq6I4xijKDqMiN8CgBQiQhRFQER93ahut4tqfIhzDpzzbq1We1IQBFc3Go2PWZa1IQzDRI3/D45RJ2Mrc7mcAQCJIlx/zZo13iiRIWJOt5UxhlEURUmS+KNK5Jo1axJEFIpJjZZEKZl6LJORe+dblgVExAaDARDRC13XPdhoNB50Xfeg67r7kyQ56LruqxGRlGj3CAVULUpvw4YN4siRI+O1Wu1JhmF8AAAEY8w0TROllH/PToWwNQFu2bJF1Gq1pzUajW+m0+mdpmme1+12hSJsthRhSylFNptlYRje5/v+S8vl8kuq1ereEe4pdR2IKI4cOXJVo9F4zlKmvqXKzp07NbdbFccxISIwxkBKOahWqw29OJd4XduOy0mSIAAwKSUYhtFGRLlv3z5awDElInqIOGuaJiiOYu3cuRMBQCpOmBdCgGEYIKVsENFPTNOETCYDnPN1hmFcnMvlJlUbfx7H8V7DMFIAwDqdDgDAA3p3SKVSJh4txDkHIuoyxi5NpVK3WZb1xjAMpRID5oQQH9cELKXMq91BMMaAMeYrIsTdu3ejamfJMAxDSilN0+S+79fCMKyNyukjC8YkomPEh4j3LbTU3XnnnfrfRUWgoMYy6zjOubZtn+s4zrmGYazhnJ+LiBMAABs2bEAAgFQqlUJEY6SOCAC4aZo7LMv6Eef88jiOuWmavW63+8ZqtbqDnQphK6Jb3Wg0/o4x9sNMJnOV53kiDEO5mDiiFGMppRSmabJiscgHg8E3GGNPK5fLX96xYwdXhCvVdkyIKA4ePFip1+sfKpVK35RSXqTH9GTbLqXkyzl9TqDvx31PjY9NRMUkSQARgYj6o04fIcTEiImMEdHP2u320LZtkFJOCyGuieOYFOF8adT2p4jRGFlQGQDg+hEpJQZBcLcyv4JpmgwAmoj4h9PT080DBw5Yi/VHzQ0CAG7cuBGJCKWUF4+NjQEAJIqgBuPj48ESBO7oRaeI111mHB/BTIQQ4Pu+CIJABEEgkiQJhRCSiOJHKBqcWwv6aiFiDACzhUKhJKUUSZL8JAzDDdVq9X8SEWMnSdzHCLter2fr9fo7Oef35HK5NyAi6/f7Qtkl2VKdchyHFQoFbhjG7GAweEu5XH7x5ORkb9euXYb2tOk6iMis1WpvzGQyd2cymbcpAvFOlrA3b96sJ6HGOUfNaQAgrSwFpHcNdWl5HEcW0pxpmgAA0jAMGA6HFUSkzZs3G/q9ffv2mYhIR44cWWvb9mVKXgdE/I62gytxblwTOABkK5XKg3Ecz8ZxDIj4AsbYS8MwxDAMYynlbY7jpNVOAFJKgYj+CHEUlGxLSpRwVq9e/VC32/1dIcQfCCE23n///WtLpdJtRIRr1qzRtmlLE4pahEKJA0xZjYiIHCW+aLk9juNYLDbGSZIU1bhqkam38JkNGzbo7+gxTQqFAhDRLXEcnxuG4UVSyguI6KI4ji9IpVL/qJ9TfXWIyBpZmKTq/sf5+XnBGONEVOx2u4eVqZWME+XaqtPi7rvvzqxatepFSZLckM/nLx4MBtDtdhNENJbi2gAg0+k0V/Ljft/3d/u+f9P09PTMyPeldkLs2bPHXLNmzVX1ev3GfD5/aRAEMBwOfdu2naVEnuMK4UeJ417P82LOOQvDMMlkMlNzc3M3AsDbF7jcSYsTI0Tw4yiKgHMuDMMwMpnMtoMHD77sSU96UjDyXnTw4EHbtu33GYbBkiSJlCz6db1wm81mRggxLYQAxeETNbYzcRyv4Zw/WQghU6kU9Pv9b5XL5YbruusMw9CKVWAYRmdEydQOHTkqJgHAVxYz3e7atUsvdgsRJRFhGIZkGMaKubm53NTUVH/Exv4bvu8DIqJhGNL3/UG5XPZGxY4R8S87umC0KVOJZrCA65tqwZJpmoCIv1y1atXh4+lQUspJxZSkooMYAGDFihW76/X6fs752mw2ez5j7BplouTGCbi0UU0+NZvN32WMvceyrA2GYUC3200UVzeWImzDMHg6neZBEOyLomjb5OTkF0d3BNVpXQe4rvtbpmlebxjGc9PpNGiLx2J1nARxC9XOn9dqteuLxeJftdtt4Xlekkql/tx13YsQ8aOmaf44jmNHCLGKc76ec/4tRDyi3v2S67ofnZqaenOz2Yxs235hJpPZXavVPoKIu4mIGGPPRsTrLMt62nA4DIrFot1sNn9UrVa/TkQGIiac8wkp5ZOFENTpdBLG2H+o4boFAP4/IUQMAFyJeZ9BRKrVapO/GlKAOI5HF/mYIgCpHtBKeUpxPhqN19i4caPmooeFEAwRMQzDxHGc84Ig+Nzhw4e3I+L9jUbjL7LZ7JW9Xi9BREilUqzf7/8IEeWuXbsMrTRu3ryZFPGVtH9DlXARJqmZxngcx0RErN/vk5Ty/Hq9fqUS7YQyX1pCiMF99933zZGFsaZQKPButxsQkT26s9Tr9Q+m0+n/5XmeJKLr5ubmdgDAwDhB97rRaDTe6zjODUmSQL/fl4qbGIsZR4hIMsZYLpfjnud1BoPB3zQajQ+tX79+oHeDnTt34u7du3HTpk1CedYuMgzjXUmSXJtKpbDX68mFJrFTLFJxsQ+6rjuZTqffwRiDMAwhnU6/0PO8K+M47hARsywrAwA2AKwcWa/swIED1zHGxrLZ7B9EUQSO4zzN87wvAEBLPTSRzWYxiiIoFAr2cDh0TdO8YVRWj6KIK66FURQlANBTHPV+IkLGmGXbNnie12y327er7zqWZaGUEsIwNJVzRJdqOp3G4XBoGIZxzKypHENiqXE4cODA14joXycnJ18wHA4hiiIwDON3AOC/AsAQAEqe54HjOEYmk4Fms3lXOp3+oOrLYgFmF3POEQBMy7JQycaPsmXv3bvXQsQJzjkyxlJxHINpmq9FxNdqWkJEcBwHOp3OAxs3blynObWUMptKpZCIDNM0cQHTqwEARlGExWLxwvn5+Zci4meMZQhbzM3NbSCi97bb7QtM01w3GAxASim1jXcJRS7JZDJGkiSB7/ufSJLk5nK5/MACJxDfsmVLAgBw6NChS2zb/hAiXmbb9kSv14PBYCAYY6eLsEcdBdqmfl2tVvsS5/ydhmFcIaWcLpVKJiJOKSKEbrf7wHA4bI1urRdeeGEIAH9Yq9VuZ4xtjeP4SZOTkynGWFErS81mc2BZ1iHP825ttVr/a82aNYcWKFZlIURXTea8EKKj7u8fDof/bprmU5UN+ZNr167tq7YbSZL0hBASAHwpZTLSrws5533G2DCKoowizuOOw4UXXhjW6/Ut3W73FUKIPyOic8fGxjJqcWdUXwLO+cF+v/+PYRh+slKptBeJsNRcdCoMw97R4YssIuqO6j9ql6FSqVSUUmZ93+8QEQkhHhWCocyKnDF2cPfu3WLjxo3HFOwwDPuI6EVR5GjmoHSQf3dd9we2bV/S7/cTKeWbG43G7bjQAwkA0Gw2p5MkeQ/n/I8VsYLyDC1lztYTSBMTE9zzvJ8lSfKGycnJn4yIInLnzp1s8+bNhIjy7rvvzlQqlbenUqk3OY5THAwGkCSJWIZjxxMTE7zVar2mUql8Xm/5pxhKAK7rlhljzzMMoxjHMTDGZJIk3VQqdcfExMTDS723d+9ea2pq6grDMNaFYcg559pCdNf09PRPtTih9YrR6MMwDFeapklSymRqauqg5nZzc3MrkiSZQEQUQjwwPT3t6chL0zSrRESmaUrf9x9evXq1r98JgmDStu0oCALLNM16pVKpLxXqu1RpNBqXSik3cM5NKSUyxhJEvKdYLP5kNBx1qW/W6/ULpJQptXsbtm0fLhQK7YXPzczMOKZpnj9qSbEs6xHfjKIIEJGlUqn+xMTEjP7ddd0yAJQ457EQwhRCdKenp2d0EFyz2VyZJMm4lDIRQli5XO4QAgDs2LGDb9myRRw8eNBOp9NvRMTrxsbGprrdLqmG4BLKnY4Ck7Ztm4gIQRD87263+5Y1a9YcUitLqrhrtmnTpkQF27zcNM2bstns+YPBAOI4FojIlnMGIWJQKpXSjUbjj8rl8qdPhcB1n/ViO9nFsXPnTrYwtnoxi5OSfSU8QcuIlWhZB5pmUI9rfPUpMK1Fbbmu6/5Oo9HY5/s+tVotqtVqieu6NBrptzDqr9FokO/7FEURNRqNva7rvmR0ULTJbSTm+plzc3O3DwYD6nQ6ug65TB3CdV2pI9lardbBubm5Jy/87mmIejQWudiJ+AOUq9ggImPPnj3mjh07+Am8xxaLYV5wDx/DO485dl69+4gxOF5fFgvVOJF2LPLsotfCWPqFfV14f+vWrY9qAxIR1mq1m3K53LuICHzf15aRpRooiAiz2SzzPC9BxE8IIX5YLpf/DyIOteVllHs1Go3LiOgdjLFXpNNp6Pf7UilUuJy44zgOZ4yB53lfz+VyO5rN5h2rV6/+5cluv2fLf96Cruu+cmxs7J8Hg4FQQSxLefuO2bMBAHzf/y4A3FAul38wyrWVZSQZkeWvQ8Q35PN5q9PpkNrqluIMJKWUtm1zy7IgjuO9Qoi/KBaLO467FZ0tZ8tiBF6v139hWdaFYRjCMnEjZBgGKrv0XYj4nu9973vf3rJli1AcW0fOacvIU9Lp9GeFEJVsNlseDocghEiWs2Ur+yfP5/MwHA5niOimTqdz6/nnn99VZi1LWTEec0z42fKfkMDn5uZICAFLSSRSSrIsC+M47gHA1maz+fH169dHI46gY96zXbt22ZdeeukfAcB7TdOsBEEAyrW7nAJJRERjY2MsCALfNM2PB0HwoVKpVFP3LRVUAz/72c8Kl156aefstJ0tJ1oMIQQtR3yWZSERDYnot6rV6k90PMXmzZtpgWXkhbZt32Db9hXD4RB835cqyo0vYzOXpmkyx3HQ87zbiOiGYrF4FwDAnj17zAcffFAiYnTw4MGCbdvvzWazL3ddd3OlUrljofntbDlbFiXw5YhbBdAnURS9bMWKFT/Zs2ePCQDJiHlNzs7OXpxOp99FRNcYhgHtdlsiIi7nDFLyvMjn84bv+/NxHP/J1NTUjhGTFNO24Vqt9nLDMN7nOM4FmUwGfN9fCwB3wIL4i9NhTVEpcYvCFZwtp0diGIlXoROdk1OZD6zX67SUTJzL5Xiv1/tEtVr9E+0I0pzzF7/4RW5qaup60zTfYFnWWLfb1TEPyxI2EclUKsUdx4Eoin7a6/X+eNWqVfcocYdrwp6dnV1rWdaHUqnUC6SUEASBPzExYbdarVefqqNn1FwFI3EwJ2VfPQ3ffkx23ZOrH37du5xOoD6ZcRh1Op5qWZIYdVwvIt6lB0sTd6PRuGzFihU/zmaz10VRNNbpdIQSR5YjboGIMD4+zolottvt/lk+n3+6Im5z9+7dDBHjI0eOpOv1+rZUKvXjdDr9guFwKHzfl3q3WcZ8edIDr7N31E6Refjhh8+v1+vndzqdcRWWuSTwzyLXI+zU+tsnEWuOo+lZxyPu47QBdRLHErZkJCJUdmM8ge+z47V3iftcZ0cBHPViPvTQQ086ePBgZf/+/anFMGNU23UMVH5mZuaC2dnZqf3796dOOwfP5/N8fn7+LdPT0x/V3qx77rknXalU9hYKhXM7nU68nJijlVREpFwux1RO4kejKPqAyqQBKaU5Io68yDTNv85ms0/WHs6RmJS4WCyarVbr1eVy+XOnw1V/5MiR1dls9iVBELzSMIzz4ji2FHGFACA553Ecx1++77773qFxQi6//PLYdd0/n5yc/PNWq5WMJOQCABDnHKWUc6Zpfsf3/dunp6e/tVw7AIC7rrvbtu3zwjAUlmXxOI7nOOcvnJycPLyYrkFEZqPR+JlpmhNRFBH8KnxV1x/Ytr0zDMNPlUqlAxpnZW5u7sWFQuETrVYrtizLDMOwKYR44cqVKw9t3bqVbdy4kW3atCmZm5vbNDY29k+dTidKp9OW7/ufLZVK79L9bzabVwLAZ4QQcbFYNJvN5icrlcp2Xc8oY5idnb08nU5fHYbhFs75pBAiBQAJEUUqSOwahXti6KjV2dnZ15im+VZEXJEkiYWIEWNMAMA8Il45OTl5RLvnjyuDH5fFMyYBAA4cOGBceOGF4dzc3Buy2ey53W43RkTzeOKI4zjcMAwMguDbURRdX61WdXyKqWzi8ZEjRy6ybfsmwzB+DwCg0+kkcDSDm5+JLVNl178+m81utW27KqUEKSWk02mwrKMJL0EQ6Ii2l61fv/4GAOjbtq25a55zXmWMgWEYMKpuSCkBAKq2bV9i2/bbXNfdWqlUbly47Y604/cnJiaeNRwOIZVKgRACSqVStVarbSKizy+ja6yyLGtMzdExK5iUEogI0un0dXEc/7darfY8APiFqjNjGEYVEcG2bYiiCBljgdY7du/erdvmWJZVJSJwHAcGg4EAANiwYYO+n06lUtUwDGGBqnUM3Gj//v2pYrH4AcMw/tRxnJS21FmWBZxz8H0fcrkcBEEwCQCwb98+RkSiVqt9sFqtvqPb7UKSJOA4DpimCUEQQDabrdTr9SIAHNm2bRts374dTpnAdTFNEwEAkiS50DTNZbdPbR3JZrN8MBg86Pv+u6vV6q0jhE2aazcajedwzr+RTqez3W5XKgI6U3gtTKXZvXt8fPwm3/eh1WqFKtcPPM87EATBPVLKLAA8lTE2AUedTxkA6K9bt05/JxFCkJQyDsPQVGZMHVVnIyJ0Op0wn89bAPAiALhR5zmOcG6amZlxEPHP4ziWSZJIRDSklPFgMOCc81cg4ueIaClZNAzDkFRqm9S7GSLaAECtVissFovFVqu1DRF1SJ9IkoQAIIyiKIWI7Wq12l1knGQYhqTqSCFic8EjIgxDEkKIXq/HAWBWSwQ7d+5kd999t53P53fk8/mrW60WeJ4XZTIZK4oi8H1/hojqAHBRHMeOHrf169dH9Xr9qel0+h2NRkMQEdm2bXieV2OMHQaAiz3PcyzLOikR9aTjOdRkLiuS5HI5ZhhGu9/vv8913adUq9VbNawCIsaImDz88MMrer3ehxhj3yWirJLj2WPN2DlRmbvVal2VzWZvGgwGIoqiJJvNpgzDeEBK+VuIeFmpVNpcLpevHg6HF8VxfAERvWkwGJDiMqPWADQMwwKAPel0enUqlZput9urpJRXElHHMAxzJCcTN23alIzIqwwRpWEYW8bGxi7p9/tk27YhpdyKiG0pJZNSbmw0GlUd3rr4VCAyxpAxdm0cxysVuM57j65X5L7vS8bYBfV6PTvCOBAA0DAMJKIIAJI9e/aYu3fv5tPT01yJCtpvgYwx1Fn8+/bt0zuYjknnKvLwWJb/li1bRKVS2VosFq9utVoREclcLmcNh8MfSik3MsbWl8vlZ0dRdK7v++uJ6PsjaW5XMMakEo+NOI7/wfO8tZ7nPTcMw9VxHD9NSrlo0vMpc/DRgV2Oedu2jWEY3tXtdn//vPPOu1813EbEAACiI0eOTDqOs1lK+S7btlf5vq9NkhzOUNHZJAcPHrTjOL4xlUpBkiSUSqWMMAx/Hobhb+v0uREFr6uuQ/r3IAiO5RQSERiGAUmSHM7lco2R6r7tuu4vHce5XMmabFTu14pVrVbLmKb5P6Iokrlcjg+Hw7uFEH9tGMYLpJSlbDbreJ73KgD4a8WIxCIUDvJoeWDlypUtAIB6vf71KIreCwCGypHkOuYnjmOu2nKME2tzr/q/9mn4KtmE1N85AADNPZMkmUilUqB2N5RShqo9cb1evwAR/3un05FwFKCHDYfDHffdd9+rtM9ElXl1gQrqEkQ0e1TiYpIxBnEcd5Qnmyn6mV8wR6efgx+HkKTKaHnHeeedd//BgwdtNbHBnj17zLm5uT9xHOcO27Y/zhhbNT8/r7fVMw0CyhCRbNt+Ri6Xu2IwGCSmaRpCiEEQBJunp6dnVARdam5uLlev17MK8y83Pz+fX0SDx5EkYH8BBuPzTdO8KAxDmcvlDCI6goikYX3XrVuHiCiklP8jm81eFIahjOM4tCzr1dPT0x4RfTGTyUAURQAAr1HQbnKUi2tOqpmKYRjJnj17zIcffniFlHK7bdsGEYWZTIYR0R6dZ2lZlp5vFgQBIOL5ruv+o+u6n3Zd9zOu6362Xq9/kjG2dTgcwki//FExFQAqKgEbkyRJFOCopoFXFgqFtBAidhyHh2H483vvvfdVmzZtSnQi9wKrD+qQj0984hPf8Dzv4xMTE3a73RbZbPYdjUbjrVrJVnN0UrRyJqDbgHOeVpwrAgCzVqu9inP+umw2+/QgCHSeJZ4pWXuZtq1RXIkMw4AgCOZXrly5X4cD1Ov1bRMTE386Pz9PQggLAJKxsTEjiqK3AsCnisUiB4BYw08oCIeB6uM2y7LWJ0nyfIV2mszNzX3Btu33wFEoBu1DEI1G49JUKvWmXq8nLMsyoiiaRcTnua77TES8VGEfJo7jrG82m1dPTU19RVuxAIAymYw2RQIACM55c+XKlV+2LOtZRDQeRRFMTk46zWbzl0R0o473j+M4rwLqUEFK5CcmJq5dOE5xHEOr1YKRaE8JAHDuuedq7rlaKeOEiImUsjcyxlWtbarUu3uVeGYuksZGoxxZMY3/7rpu1zTNd8ZxDJZlfbjT6Vzq+/6nEXHXr53A9YDoVTc7O/uuarW6rdvtQqfTWTbPUilU7HRzdJ35zRjLjGKB6G1uRLauGoYxbpomCCFACEEqvzBZYFlylLUEpJQMEQPXdZ81MTGxqV6va4SrPyyXy/+0UKwjItZoND5ummbe930RhqFAxFX5fP5jKmEEer2eZIwxhRn4FgD4qnYAIyJks1lTCKG5MU5MTLQajcaR8fHx8WazCZzzBweDwQ8Gg8HbL7jggoY2ZSJiQUNmKPEqrNfrP0VETr/CxxOIuNo0zdVCCJ3JIwEAHnroocXEVTGKaYiIloZW0/4ArVQfj//A0YMBWKVSeXetVrvHcZxbkiSxM5nMtVLKa1zX/T1E/MrJhGmccXB2zvlVvu8nQRDEjDG2FGYKEVEul+Mat+R0Fp0XiIiHlHKlidPctWuXsW7dOqkSNP4hiqI/iKLop6ZpEmMsTJKENODkueeeq7fKohBCm8i0gvUBhVYb53I5ExGrW7duZSq8gbRiWavVfi+bzT5d7WI8n8/zYrGIRAQazs22bSalZMPhkGzbvrxerz9FTSgDAFAWkGMRnA899JAVBMG7arXatVLKF3ied0WhUHi1Im4ckbEd1XfpOA4AwJcqlcpzyuXyMyuVyrPU3+cAwP/MZDKaUS2md/HRuTNNMx5Z/HOGYZCUElWE6holnpFOJBnBfnwULWzbtg2JKFWtVm8dDofXcs5lr9eLlML7KaV4yxNNeGGPg1jgq51iqVBckclkmGVZOBwOvy2l9BQQ5Wnn4FLKXwRBMGSMsTAMhW3b1bVr174WERNEFJVK5UepVOqziNhX2dvEGEMpJRvdUjWXUiJKHwAgnU7/zPf9By3LSnW7XZBSvuV1r3udffnll8cavP3IkSNpzvl7NWc0DAP6/f7X5ufnP9Lr9f621+v97fz8/N9EUXTAsiyQUiaO42RBgXcqUB7IZrMTAGApbkzD4ZCdc8457RUrVny+XC5/c+XKlS2dUTWqjCHiuN4F1Lv6OZOImMpO4kruBwBAZesO1QLXEBEa1wQRUSZJEo9Y0X4yHA4REY3hcCiy2exvXHzxxe/Q+IQLsB/lQueb+j0EAJienv7fvu8PTNO0wjBM0ul0UQhxmZpTfEIQ+FJ1SClJSinHxsb4cDi8J0mSF01NTV1FRH+ruEdyuhqglBherVb3DYfD2wqFAle2bDBN88Pz8/M3zM7Orm00GtV6vf5MRJxWHkIehqFUONTHZFEiyo9swwgAMDY21kTE2zKZDCRJEudyuZWGYbxci4KIKBljL8/lcpf4vp+kUikmpXyoVCq9pFwuv61cLv9ZuVz+s2q1+lYiujGXyyEiku/7IKX8YyJiX/va14Sy5qThKLorAABkMhmplDZzhLBHwUP13xVCCBhBox0ioti5c6dERLlhwwahsApzyjFjDYfDDvwKhk1bcvIjIdbS87wA4GjKWLlc/qrv+z8tFAocAES/35e2bb/fdd3PttvtTUeOHLlodnb2N3zf/816vX7t/v37pwAA2u32WL1e/2S3233NkSNHnl2v1y9wXfc3TdO0tDg4ikSr8VieCAT+KA+nlFKkUiksFotsOBz+SxRFzyiVSrep+JfGGTKqEABgOp1+d7fbdQuFQiqOY4rj2E6lUtsZY3cQ0XcR8QeI+GSVjse73W4kpTykA4aIyAGAShzHCRxFrToGcCOE+Eqv10tUNxMAeN3evXstAEhmZmYcxtg7oyhKiChxHAellB9T262tuGdKiTQ/HAwGcxrR1bKsla7rPm/ENZ1RBJ0gYpLNZjUxJ4ug4sII9PRaZfUQRJQQUWcJ5pNR7U8AIJSawpQ1hzHmCCH0faGVUWUhkpzzaz3Pe7BYLFpSSvB9XziO82rbtr/LOb+DMXaHbdvfIaKttm0PAADGx8f7RHTF2NjYZ2zb/j4A3ME5/w4ROXEcJ7lczvB9/wHHcX52gjL940/gCuAex8fHOQA8NBgMrp2amvr91atX+8qkyH81lqe3aGWnUCg8IKV8vud5/5ZOp1kmk0Eignw+nx8fH7/IcRzIZDJQKBTMQqHAFT5HOGIGnCoUCpc6jmNYlmXo7VyBVf5ICBFNTU1ZiGiUSqWnT05OblGoA1tLpdKTOedGqVRyut3uPBF9Xk1WdPnll8eIGG7YsEEqrMJ7JicnTcuyrImJiRRj7A0jDpFzi8ViKpfLGZzzwgkq5QgAq/P5vJHJZOxsNvsoqL2RU8+el81mjXw+byBiUfsolEhhE9HqbDZrFAoFAwAmdP2bN2+WRIRTU1P3t1qtq/r9/ldSqRTL5XLcMAyIogjGxsYKmUxGf6+1evVqX4EBSUTsKnMk5PP5yVQqBdlslhUKBSNJkkNBEFyroChOONLSeLyYNgDIsbExM47j/mAw+ORwOHz/Oeec0yYiduedd3KN8Ver1TYmSXI8h9KpEDlDxHu2bt165Vvf+tYNw+HwZYZhXJIkSRoAMspTO+CcCyLqMMa+2ul09msZMZfL+d1u9xsAIGzb5lLKewGOHUfoNxqNG4MgeO5wOEw45xwRL1CWk1WdTue2KIqEWhj/Vq1WG0tZBBBxh+/7kUJb5QCQtNvtMQDoElESx/E3+v0+EFFQLpfjE5kHRNzZ7XbHoygSyuz4M2VFIh2PouI77up0OjNqHvowcmTKgQMHzHw+//1Op/OAAhAdpFKpaOFugYi/BIDfnZubu7zf7/+BaZpr4jjO+r5vAkBbeSy/P+pAI6KPNJvNFhFlPM/LAIDlOE47juMfhGH4dytXrmzqSMkTnvTlYCHUwURvBAA4ePCgDQDguu7NSZJQvV6PFnknVhASV+vvu677f4mI2u02zc/Pf2lmZma9vrd3715La8MzMzMXNJvNz7VaLarX64tBSUSq3mu10f9UYlIW+/2xhmSeoof1/5dl69atbAlYvxP2WC+ErXgsUCFnXERBxH2e590rhHjpxMTES1evXr2XiMw9e/aY69evj9SRdu/JZrN3ZTIZjYu9bP7m6RJXRkxWhoYz05OgvG6LYoMsh58yelzH6PsLfx89vWKpRbjw+aXunWi/dZ+Oh/2yyHO43P3FvrF9+3YppRyFoj6W+KBw4I2FxD7SLz7i4eQjivNJy69nVETZtWuX0e1233z33XcbV1111ZCI2L59+wydRPzQQw9Vs9nsDYVC4Q3tdhs6nc6SmITKQ4qMMes0LTxaoKiMJhuI47ybLHNPnMzvyy1CWCIlb7l7y5UFsSCP+bkT/c7IGMvRHWuZMZKjz44mPzzWcsZlcMUVw4MHDx4LuHr44YfHx8bG3soYe7VlWec0m01x1Gq1JHGLVCqF7Xa7ZVnW90ZNdqdTYjjzITH/ucvJpOCdrpzYMyqi5HI51EdiayVyfn7+Vblc7keO47xXSnnOgqMFFyVuRGSFQsGIouhLhULhAR36epZkzpZfGwdX8p1Q7ul1+Xz+sl6vd41lWVfGcQztdlssByuhUt1kNpvlcRx7c3NzH1TH/eEZ4N5ny1kCP/GiAv1lvV7Pdjqdt0kp32rbdkGB55Ny6CwHESds2zZSqRT3PO+HURS9ecWKFXeena6z5QlB4Iwxs16vP9M0zY9lMpnLOp0ONBqNGI7mWbKlrCRSSmEYBs/lcka/3z8Ux/FflEqlTym6P5aUenbazpZfiwyOiEan0wFE/GcA+L5pmpc1m02h0LPM5c7MJCJZKBQ4Y8wbDAZ/ORgMLimVSv+ggoKYslycMnETEWqzlb4e43f4It9ZFjJ44fO7du0y9uzZY+pr5GS3s+WJysF1woOUEobDoTxeKpqUUqbTaQYAMBwOvxBF0Y0rVqzQWeD8dHNtHbNxGr5z2sx+iy2Gs0r0E1sGpxMAApKIKMfGxowwDP8jjuPryuXyN9U9Qymo4jQuPEREmp2dXWsYxvOFEEKdDCySJPm0Shc74RiHw4cP/5FlWXmNmiuEGBiG8S/lcnkw+h1NrLVa7WmGYTxPSukpDi455wYirlXnyQsi2hfH8a2IeOgsTPQTmMCXC/7ReCm2bXPHcVi3271VSvnfqtXqcOTYj+QMNEsn7l4+Njb2Yd/3IZ1OQ7vdPgAAnz5RsUQhez3bNM1bVMYNMMbAcRxoNpttAPgiHE0ISAAA7rzzTg5HQYSePzk5uW1+fh5UPiNwzkElQINOeAjD8O3NZvMaRPzOWU7+BJPBT4BABOccJyYmOCIeHAwGr7333nuvUcRtLAyCP0MKcCYIAhmGYRRFkWSMPbhixQr/5LpB19i2TZ7nSRUOGgkhiDH24qXMmOqYaZkkSej7vvQ8L+73+91Wq9UNggA8z4N+vx+l0+myEOKvHqtucLY8zgSuIgkTIpJjY2McADzP8z7g+/7TJycnb9F4IWeIay9G4GnOOUNE4JwzAOhp7JHjxYYAgDx8+PCFjLFrFDDOkSRJ7shkMmav1wMp5UsOHTo0PpKH+IiqFdwE5XI5hojfA4DnSimv9H3/xUKIn1uWZarziCq1Wm3lyaRmnS1LzDed7gTIR4oiIpVKsbGxMUOd6fNVKeUzx8fH361CRfnjLWsS0YSChT4G+3Ai7+3cuRMRkTjnNziOk85kMgwRPwoAf63ySGUmk8mlUqkXLcc8RtLFvlepVH5erVZ/Uq1WvyalvNmyLFRnw5uj59GfLacgg3POcbkTHh6rKKKOI+GdTuchIcS9nPNbJicnv6xlWVj6JN4zUlQ+owCANeqkYalyKrsLZPRHFQ27UK/Xn80Y2xKGIXme10bEryKi2+12m4ZhTBqGAVLKa/bu3fsFtWvhnXce80/pAUYVR51tNpvTcRxbRFTknL9aCAG2bWMcx19cLlb8bDkJDi6EcA3DkKMHc54K15ZSimw2yznnfr/f/5Dv+8+cnJx84fj4+JdHrAri12Uh0LAJcBSJFfSJvLCMDXvz5s1ERCiE+MtUKmUahoFxHF9XKpUOTE1N9Tnnn8lms9Dr9RLHcX6zVCqtV/1jGzZsOJaorG36CnTnTUKIHyLivzPG/q9pms8OgkB0u91rK5XKn54l7tNnRfmrTCbzkV6vJ1Vg02NSbqSUgnPOJyYmuDpj/fqpqak9I2Y/Cb/Gg1E1oS0kZCmlUBwel7GciFqttjmTyTzL933BjpbfmJ2dtdS6vjiKIkJEsiyLeZ73CgC4CwBAI7Zqy5IWUZQusBrg6BHgSZKAbds8iqI1Ovb5rKnwNHDwcrn80W63e71t2yyTyXAiEifDzbUXMp/Pc9M0vV6v9+Gbb7756qmpqT1ExFVmh4YL+HVO1iM4qSY2LSY9+OCDqIhfX6BwBOX8/PxqxtgnlTkPGWM4MTHx+lKp9PFSqfR3Y2NjV4dhiERk+L5PlmX9ocLoO3bOuhCiqDLaQQELvT6KogoRrQaAtUKIXQqu+IZarfZvo7meZ8n0FDi4IrqbZmdn7zJN8wO5XO4pQgjwPC8+jv5JRCT0Ya1BEHxxMBhsX7169V4ttz6eMvZxGooj+HZ5JQNr6AS9mB/lMd22bRsiopydnb2+WCyOz8/PJ6ZpGnEcdzqdTk2JEaTG4jzOeSqO47hYLE7Ozc1dCQC/3Ldvnwbo0T4HVHjk969YsaKu2kH1ev16zvkPhsNhks1mN9Xr9edUKpV/U/qKOEuqj11E0Umi/0pEtzcajVcZhvHmVCp1ueM40O/35QIzm1TbulEoFJjv+/8RBMG2crn85RFxRDxRiHvBgkw1Go2sztxXMrG5f//+VBRF5v79+2MAgDVr1gAAiG3btsnZ2dm1mUzmFf1+XxzNIcaIiJ5fqVR+PPrxWq12XSaT+avBYACe5xEiXrt169ZPrFu3LlZ12dpyo8YxHN1ZAOCFqo2Jsi6lj6cbnC0nIKIo7iIVx5XlcvlztVrtWVLKV4ZheDcR2QuoxDFNk5umOTccDt9x9913X1Eul79MREx9I3miyo1HjhzJSilzSZIkRMTm5+cTInpbPp+fmZqaeiCfzz88Pj4+02g07p+dnb1k+/btEhHfwznPJkkSZrNZHkXRv1ar1R9rE6fKL0QhxFfCMIwAgIIgEIyxy17/+tdfpCGIGWOGlDJR1pUEEd/puu77Xdf9gOu6t3HO3+l5npicnLQ9z3Nt29a42We59+ksOgMHAOD222/P1Ov1yqgsOD8/fw4RPa3Vaq0aVcSeyH3S7XNd9+lCCPJ9n4IgoCAIKIoiEkJQkiQUxzEREdXrdZqdnZ1qNpsvVdBoJISgZrPZbzQaa9ThTcfAL3VCseu6/4eIqNvtEhGR67pfICKcmZlxXNf9BRGR53kUBAEtLEEQULvdplardXu73b70rPx9+kSUR5SRkwgYIg4BYKi4PAEATExMPAwAD+vFsHHjxieiOPIoI4+ymNTCMHxPt9s9hsakMAaPQZyZpsmklP35+fnuxMQEhWH47sFgkCCiEcfxg9Vq9cAC64Y+PlHU6/UPhmF4h+d5QgWatXfv3s2npqbE1NTUze12OxfHozB+Up9FGito4dqIqHfWgnIayv8D1oIGjKHlTrEAAAAASUVORK5CYII=" alt="COMPUTER GRAPHICS LAB" width="92" height="32" style="flex:none;display:block">
    <span style="opacity:.35;font-weight:400;margin:0 2px">│</span> CFD Studio
  </div>
  <div id="modeSeg">
    <button class="seg on" id="mCFD" onclick="setMode('cfd')">CFD</button>
    <button class="seg" id="mViz" onclick="setMode('viz')">Viewer</button>
  </div>
  <span class="pill"><span class="dot" id="stDot"></span><span id="stTxt">연결 확인 중…</span></span>
  <span class="path" id="envPath">환경 확인 중…</span><span class="tag2" id="appContext" hidden style="display:none">액침냉각 디지털트윈 · __APP_VER__</span>
  <button id="settingsBtn" onclick="showSettings()" title="환경 설정" aria-label="환경 설정"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" aria-hidden="true"><polygon points="18.47,9.32 20.83,10.28 20.83,13.72 18.47,14.68 19.46,17.03 17.03,19.46 14.68,18.47 13.72,20.83 10.28,20.83 9.32,18.47 6.97,19.46 4.54,17.03 5.53,14.68 3.17,13.72 3.17,10.28 5.53,9.32 4.54,6.97 6.97,4.54 9.32,5.53 10.28,3.17 13.72,3.17 14.68,5.53 17.03,4.54 19.46,6.97"/><circle cx="12" cy="12" r="3"/></svg></button>
  <button id="infoBtn" onclick="showInfo()" title="이 소프트웨어에 대하여 · 사용법 · 제작자">!</button>
</div>

<div id="app">
 <div id="side">

  <section id="secRun">
   <div class="settingHead"><span>설정</span><button class="mini" onclick="showCfg()">현재 설정 보기</button></div>
   <div class="cfgDrop" id="cfgDrop">
    <select id="cfgPick" onchange="settingChanged()" aria-hidden="true" tabindex="-1">
      <option value="">기본 설정</option>
    </select>
   <button type="button" id="cfgToggle" onclick="toggleConfigMenu()" title="기본 설정 또는 저장된 설정을 선택합니다">
      <span id="cfgToggleTxt">기본 설정</span><span class="arr">▾</span></button>
    <button type="button" id="cfgAdd" onclick="event.stopPropagation();openCB()" title="새 설정 만들기" aria-label="새 설정 만들기">＋</button>
    <div id="cfgMenu" role="listbox"></div>
   </div>
   <div class="baseRow">
    <div class="slot baseSlot" onclick="pickBase('json')" title="config.json 파일을 선택합니다">
     <div class="baseTitle">현재 설정</div>
     <div class="baseMeta">
      <span class="baseState" id="slCfgState">확인 중</span>
      <span class="baseName" id="slCfgName" title="config.json">config.json</span>
      <span class="baseCount" id="slCfgCount"></span>
     </div>
    </div>
   </div>
   <input type="file" id="fBaseJson" accept=".json" style="display:none" onchange="baseFile(this)">
   <div id="immersionSetup">
   <div class="fgroup">출력 데이터</div>
   <div class="outGrid" id="outGrid">
    <label class="outOpt" id="outOptBub"><input type="checkbox" id="outBub" data-output="bubble" checked><span><b>TMC-49 증기</b><small>기포 형상·부피</small></span></label>
    <label class="outOpt" id="outOptPhase"><input type="checkbox" id="outPhase" data-output="phase" checked><span><b>액체 상분율</b><small>하단·상단 액체</small></span></label>
    <label class="outOpt" id="outOptFlow"><input type="checkbox" id="outFlow" data-output="flow" checked><span><b>유동</b><small>유속장</small></span></label>
    <label class="outOpt" id="outOptTherm"><input type="checkbox" id="outTherm" data-output="therm" checked><span><b>온도장</b><small>3D 온도</small></span></label>
   </div>
   <div hidden aria-hidden="true">
    <input id="ovViz"><input id="ovEnd"><input id="ovWatt"><input id="ovCoilUA"><input id="ovUpper"><input id="ovLower">
    <input id="ovWrite"><input id="ovFlow"><input id="ovTa"><input id="ovEvap"><input id="ovCond">
    <input id="ovCoilH"><input id="ovDx"><input id="ovInitD"><input id="ovInitW">
   </div>
   <div id="runIdle" class="btnrow">
     <button class="btn pri" id="btnGo" onclick="goRun()" style="flex:1;justify-content:center;height:40px">
       <svg width="12" height="12" viewBox="0 0 24 24"><path d="M6 4l12 8-12 8V4z" fill="#fff"/></svg><span id="btnGoTxt">실행</span></button>
     <button class="btn" id="btnReset" onclick="goReset()" style="width:86px;justify-content:center;height:40px;display:none"
       title="0초 상태로 초기화만 — 진행 자료는 Trash로 이동, 설정 유지 (계산 시작은 [실행])">
       <svg width="11" height="11" viewBox="0 0 24 24"><path d="M12 5V1L7 6l5 5V7a5 5 0 1 1-5 5H5a7 7 0 1 0 7-7z" fill="currentColor"/></svg>리셋</button>
   </div>
   <div id="runBusy" class="btnrow" style="display:none">
     <button class="btn dng" onclick="stop()" style="width:100%;justify-content:center;height:40px">
       <svg width="11" height="11" viewBox="0 0 24 24"><rect x="5" y="5" width="14" height="14" rx="2" fill="currentColor"/></svg>중단</button>
   </div>
   <label class="ck" id="arWrap" style="white-space:nowrap" title="예기치 않게 멈춘 계산(절전·재부팅·솔버 종료)을 앱이 확인해 자동으로 이어서 실행합니다. [중단]으로 직접 멈춘 경우는 제외."><input type="checkbox" id="autoRes" onchange="setAutoRes()">
    중단 시 자동 이어서 실행</label>
   <div class="fgroup" style="margin-top:16px">프로젝트 리스트</div>
   <button class="btn" style="width:100%;justify-content:center;margin-bottom:7px" onclick="newProj()">＋ 새 프로젝트</button>
   <div id="projList" style="display:flex;flex-direction:column;gap:6px"><span class="sst">확인 중</span></div>
   </div>
  </section>

    <section id="secData" style="display:none">
   <h2 class="result-data-summary">결과 데이터</h2>
   <div id="exSel" hidden>
    <input type="checkbox" id="exBub" checked>
    <input type="checkbox" id="exPhase" checked>
    <input type="checkbox" id="exFlow" checked>
    <input type="checkbox" id="exTherm" checked>
   </div>
   <div class="fld result-data-summary" style="margin:13px 0 7px;display:flex;align-items:center;justify-content:space-between">
    <span>선택 Case</span><span class="sst" id="projDataName"></span></div>
   <div id="slots" class="result-data-summary">
    <div class="dstat"><div><b>TMC-49 증기</b></div><span class="sst" id="slBub">확인 중</span></div>
    <div class="dstat"><div><b>액체 상분율</b></div><span class="sst" id="slPhase">확인 중</span></div>
    <div class="dstat"><div><b>유동</b></div><span class="sst" id="slFlow">확인 중</span></div>
    <div class="dstat"><div><b>온도</b></div><span class="sst" id="slTherm">확인 중</span></div>
   </div>
   <div class="pbar" style="margin-top:13px"><div id="exBar"></div></div>
   <div class="meta"><span id="exSt"></span><span id="frSt"></span></div>
   <button class="btn pri" id="btnRun" style="width:100%;margin-top:13px;justify-content:center;height:42px;font-size:13.5px" onclick="vizRun()">
     <span id="btnRunTxt">생성</span></button>
   <button class="btn" id="btnUpdateViz" style="width:100%;margin-top:8px;justify-content:center;display:none" onclick="fetchResults()"
     title="현재 계산에서 새로 저장된 스냅샷만 기존 시각화에 추가">업데이트</button>
   <div class="fgroup" style="margin-top:16px">프로젝트 리스트</div>
   <button class="btn" style="width:100%;justify-content:center;margin-bottom:7px" onclick="newProj()">＋ 새 프로젝트</button>
   <div id="projList2" style="display:flex;flex-direction:column;gap:6px"><span class="sst">확인 중</span></div>
  </section>

 </div>

 <div id="main">
 <div id="viz" style="display:none">
  <canvas id="gl"></canvas>
  <div id="gcol"></div>
  <div id="rcol">
  <div id="legcol">
   <div id="vbar" style="background:rgba(26,26,25,.85);border:1px solid var(--line);
   border-radius:10px;padding:9px 11px;display:none;backdrop-filter:blur(8px)">
   <div id="vbarTitle" style="font-size:10px;color:var(--ink2);margin-bottom:5px">유속 |U| m/s <span style="color:var(--muted)">화살표=방향</span></div>
   <div style="display:flex;gap:6px;align-items:center">
    <div style="width:110px;height:10px;border-radius:4px;border:1px solid var(--grid);
     background:linear-gradient(90deg,#0d1b33,#2f65c2,#9fc4ff)"></div>
    <span id="vbarRange" style="font-size:10px;color:var(--ink2)">0 ~ 0.15+</span>
   </div></div>
   <div id="tcbar"><div style="font-size:10px;color:var(--ink2);margin-bottom:5px" title="냉각수 입구 온도 ~ 기화점+5°C 선형 · 흰 눈금선 = 기화점(비등 시작)">온도 °C</div>
   <div style="display:flex;gap:6px;align-items:stretch">
    <div class="grad" style="position:relative">
     <div id="tcSat"></div>
    </div>
    <div style="position:relative;display:flex;flex-direction:column;justify-content:space-between;font-size:10px;color:var(--ink2);min-width:56px">
     <span id="tcHi">—</span><span id="tcSatL"></span><span id="tcLo">—</span></div>
   </div></div>
  </div>
  <div id="lcol">
  <div id="hud">
   <div class="hgrp"><div class="htit" id="hFrTit">재생 프레임</div>
    <div class="hrow"><span><span id="hTimeLabel">t</span> <b id="hT">—</b> <span id="hTimeUnit">s</span></span><span>TMC-49 증기 <b id="hV">—</b> mL</span><span>기포 셀 <b id="hC">—</b></span></div></div>
   <div class="hgrp live" id="hLiveG" style="display:none"><div class="htit">실시간 솔버</div>
    <div class="hrow"><span>t <b id="hLt">—</b> s</span><span>TMC-49 증기 <b id="hLv">—</b> mL</span><span>코일 <b id="hLc">—</b> °C</span></div></div>
   <div class="hgeo" id="hGeo">config.json 연결 대기</div>
  </div>
  <div id="vlegend">
    <div id="flowControls" title="속도 벡터 표시 개수. 계산 격자와 결과값은 변경하지 않습니다." >
      <label for="flowDensity">표시 밀도</label>
      <select id="flowDensity" aria-label="속도장 표시 밀도"><option value="1500">표준</option><option value="6000" selected>세밀</option><option value="18000">매우 세밀</option></select>
    </div>
    <div class="ltit">결과 데이터</div>
    <label id="lbBub" title="TMC-49 액체에서 발생한 증기 · 밝을수록 증기율 높음"><input type="checkbox" id="lyBub" checked><span class="sw" style="background:#ffe36a"></span>TMC-49 증기 기포</label>
    <label id="lbPhase" title="실제 alpha.water와 alpha.liquid 분포 · 초기 계면을 넘은 액체와 혼합 계면 표시"><input type="checkbox" id="lyPhase" checked><span class="sw" style="background:linear-gradient(90deg,#f59a38,#8c75ba,#4a9ef5)"></span>액체 상분율</label>
    <label id="lbSlice" title="3D 혼합 속도장 U의 방향·세기 화살표"><input type="checkbox" id="lySlice"><span class="sw" style="background:#3987e5"></span>유속장</label>
    <label id="lbTvol" title="열화상 팔레트 · 백=기화점"><input type="checkbox" id="lyTvol"><span class="sw" style="background:#e34948"></span>온도 히트맵</label>
    <div class="ltit" style="margin-top:8px">설계 레이어</div>
    <label><input type="checkbox" id="lyGeo" checked><span class="sw" style="background:#1c8a55"></span>보드 · <span style="color:#ff8c28">CPU</span></label>
    <label><input type="checkbox" id="lyCoil" checked><span class="sw" style="background:#8ea9cf"></span>코일</label>
    <label><input type="checkbox" id="lyTank" checked><span class="sw" style="background:#9a9ca3"></span>수조(유리) · 공기층</label>
    <label title="계산 시작 시 400 mm 기준선 · 실제 계면은 액체 상분율 레이어에서 확인"><input type="checkbox" id="lyBound" checked><span class="sw" style="background:#e07b3a"></span>초기 계면 기준선</label>
    <label><input type="checkbox" id="lyProbe" checked><span class="sw" style="background:#d55181"></span>열전대</label>
    <label><input type="checkbox" id="lyInfo" checked><span class="sw" style="background:#c3c2b7"></span>실시간 정보 텍스트</label>
    <div class="ltit" id="graphControlsTitle" style="margin-top:8px">그래프</div>
    <label title="프로브 4점 온도 추이 · 재생 시점 표시"><input type="checkbox" id="gcT" checked onchange="renderGCol()"><span class="sw" style="background:#3987e5"></span>열전대 온도</label>
    <label title="재생 프레임의 기포(증기) 부피 추이"><input type="checkbox" id="gcV" checked onchange="renderGCol()"><span class="sw" style="background:#31c46a"></span>기포 부피</label>
    <label title="증기율 임계 이상 셀 수 — 비등 활성도"><input type="checkbox" id="gcB" onchange="renderGCol()"><span class="sw" style="background:#c76bd6"></span>기포 셀 수</label>
    <label title="하단·상단 액체층 평균 온도 추이"><input type="checkbox" id="gcL" onchange="renderGCol()"><span class="sw" style="background:#e08a3a"></span>층별 평균 온도</label>
  </div>
  </div>
  </div>
  <div id="plabels"></div>
  <div id="empty"><div class="box">
    <svg width="42" height="42" viewBox="0 0 24 24" fill="none" style="opacity:.9"><rect x="2.5" y="2.5" width="19" height="19" rx="5" stroke="#3987e5" stroke-width="1.4"/><path d="M12 6.5c2.6 3.1 4 5.2 4 7a4 4 0 0 1-8 0c0-1.8 1.4-3.9 4-7z" fill="#3987e5" opacity=".85"/></svg>
    <h3>3D 시각화</h3>
    <div id="emptyIntro">
    <p>선택한 프로젝트의 시각화 데이터가 여기에 표시됩니다</p>
    </div>
    <div id="emptyReady" style="display:none">
      <p id="emptyReadyTxt">데이터 준비 완료</p>
      <button class="btn pri" style="margin-top:12px;justify-content:center;min-width:200px;height:40px"
        onclick="vizRun()"><span id="btnRunReadyTxt">생성</span></button>
    </div>
  </div></div>
  <div id="controls">
    <button class="iconbtn" id="saveShot" onclick="saveProjectScreenshot()" title="UI 없이 3D 화면을 프로젝트 Screenshots 폴더에 저장"
      style="background:var(--surface2);border:1px solid var(--line)">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#cfcdc0" stroke-width="2" stroke-linejoin="round">
       <path d="M4 7h3l1.4-2h7.2L17 7h3a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2z"/>
       <circle cx="12" cy="13" r="3.4"/>
      </svg></button>
    <button class="iconbtn" id="play" onclick="togglePlay()" title="재생" aria-label="재생"><svg id="playIco" width="13" height="13" viewBox="0 0 24 24"><path d="M6 4l12 8-12 8V4z" fill="#fff"/></svg></button>
    <input type="range" id="tbar" min="0" max="0" value="0" oninput="scrub(this.value)">
    <span id="tlab" title="현재 시간 · 전체 저장 프레임 수">—s (0프레임)</span>
    <select id="speed" title="재생 배속" aria-label="재생 배속" onchange="changePlaybackSpeed()"><option value="0.1">0.1×</option><option value="0.25">0.25×</option><option value="0.5">0.5×</option><option value="1" selected>1×</option><option value="1.5">1.5×</option><option value="2">2×</option><option value="4">4×</option><option value="8">8×</option></select>
    <button class="btn" id="btnExport" onclick="openExport()" title="3D 영상·이미지 내보내기">Export</button>
  </div>
  <div id="vizWarn"><span id="vwTxt"></span><button class="btn pri" onclick="fetchResults()">지금 생성</button></div>
  <div id="errBanner"><div style="flex:1">
    <b id="ebT"></b><div id="ebG"></div></div>
    <button class="btn sm" onclick="hideErr()" style="flex:none">닫기</button></div>
 </div>
 <div id="dash">
  <div class="dcard">
   <div class="drow1">
    <div class="dbig"><b id="mTime"></b><span class="pc" id="mPct"></span></div>
    <div class="dstats">
     <span id="stEtaW"></span><span id="stVapW"></span><span id="stCoilW"></span><span id="dSnap"></span><button class="iconbtn" id="openRaw" onclick="openRawSnapshots()" title="이 프로젝트의 Raw 데이터 폴더 열기" aria-label="Raw 데이터 폴더 열기" style="display:none;width:23px;height:23px;vertical-align:middle;margin-left:-3px;position:relative;top:2px">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M3 6.5A2.5 2.5 0 0 1 5.5 4H10l2 2h6.5A2.5 2.5 0 0 1 21 8.5v9A2.5 2.5 0 0 1 18.5 20h-13A2.5 2.5 0 0 1 3 17.5z"/></svg>
     </button>
    </div>
   </div>
   <div class="pbar" style="height:10px;margin-top:11px"><div id="runBar"></div></div>
   <div id="dashWarn" style="display:none;color:#ff9c8a;font-size:11.5px;margin-top:8px"></div>
  </div>
  <div class="dgrid">
   <div class="dcard">
    <div class="dlab"><span title="실측 6채널(T1~T6)에 대응하는 지점 온도">가상 열전대 (°C)</span><span id="chartT"></span></div>
    <svg id="spark" preserveAspectRatio="none"></svg>
    <div class="lg" style="margin-top:10px">
     <span><i class="sw" style="background:var(--s1)"></i>T1 CPU <b id="v1"></b></span>
     <span><i class="sw" style="background:var(--s2)"></i>T2 계면↓ <b id="v2"></b></span>
     <span><i class="sw" style="background:var(--s3)"></i>T3 계면↑ <b id="v3"></b></span>
     <span><i class="sw" style="background:var(--s4)"></i>T4 코일↑ <b id="v4"></b></span>
     <span style="color:var(--muted)">│ 냉각회로</span>
     <span><i class="sw" style="background:#d55181"></i>T5 입구 <b id="v5"></b></span>
     <span><i class="sw" style="background:#008300"></i>T6 출구 <b id="v6"></b></span>
    </div>
   </div>
   <div class="dcard">
    <div class="dlab"><span>TMC-49 증기 부피 (mL)</span><span id="vchartT"></span></div>
    <svg id="vchart" preserveAspectRatio="none"></svg>
   </div>
  </div>
  <div class="dcard" id="engCard" style="display:none;padding:12px 18px">
   <div class="dlab" style="margin-bottom:8px"><span title="발열 입력이 냉각으로 얼마나 빠져나가는지. 이 비율이 오래 낮으면 열이 어딘가에 갇혀 있다는 뜻입니다">에너지 수지</span><span id="engT"></span></div>
   <div id="engRow" style="display:flex;gap:26px;align-items:center;font-size:12px;flex-wrap:wrap"></div>
  </div>
  <div class="dcard" id="metCard" style="display:none">
   <div class="dlab"><span title="Courant 수·시간 간격·압력 잔차·계산 속도">솔버 지표</span><span id="metT"></span></div>
   <div class="mgrid">
    <div><div class="mlab">Courant 수 (max)<b id="mv1"></b></div><svg id="mc1" class="mchart" preserveAspectRatio="none"></svg></div>
    <div><div class="mlab">시간 간격 Δt (s)<b id="mv2"></b></div><svg id="mc2" class="mchart" preserveAspectRatio="none"></svg></div>
    <div><div class="mlab">압력 잔차 (초기)<b id="mv3"></b></div><svg id="mc3" class="mchart" preserveAspectRatio="none"></svg></div>
    <div><div class="mlab"><span id="mlSpeed">계산 속도 (물리 s / 실제 h)</span><b id="mv4"></b></div><svg id="mc4" class="mchart" preserveAspectRatio="none"></svg></div>
   </div>
  </div>
  <div class="dcard" id="sysCard" style="display:none;padding:12px 18px">
   <div id="sysRow" style="display:flex;gap:26px;align-items:center;font-size:12px;flex-wrap:wrap"></div>
  </div>
  <div class="dcard dlog">
   <div class="dlab"><span>솔버 로그 (실시간)</span></div>
   <pre id="mLog"></pre>
  </div>
 </div>
  <div id="drop">파일을 여기에 놓으세요</div>
 </div>
</div>
<div id="toasts"></div>
<div id="nmBg" style="position:fixed;inset:0;background:rgba(0,0,0,.55);display:none;align-items:center;justify-content:center;z-index:90">
 <div style="background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:20px 22px;width:340px;box-shadow:0 18px 60px rgba(0,0,0,.6)">
  <h3 style="margin:0 0 12px;font-size:14px" id="nmTitle">프로젝트 이름</h3>
  <input class="num" id="nmInput" maxlength="40" style="height:38px;font-size:13px">
  <div class="btnrow" style="margin-top:14px">
   <button class="btn pri" onclick="nmOk()">확인</button>
   <button class="btn sm" onclick="nmClose()">취소</button>
  </div>
 </div>
</div>
<div id="cfgBg" onclick="if(event.target===this)this.style.display='none'"><div id="cfgBox">
  <h3>현재 설정 <button class="mini" onclick="document.getElementById('cfgBg').style.display='none'">닫기 ✕</button></h3>
  <div class="cfgRuntime" id="cfgRuntime"><div class="cr"><span>실행 환경</span><em>확인 중</em><small></small></div></div>
  <div class="src" id="cfgSrc"></div>
  <div id="cfgBody">설정이 아직 로딩되지 않았습니다</div>
  <div class="cfghint">▪ 값 수정: 화면의 숫자 입력 또는 <b>config.json</b> 하나(형상·물성·가열·냉각·층높이·격자) 편집 후 실행 — 코드 수정 불필요<br>
  ▪ 외부 결과: <b>cfd_studio\Project\프로젝트명</b> 폴더에 config.json · C · bub_*/alpha.vapour_* · phase_*.bin · flow_*.bin · therm_*.bin을 넣으면 자동 인식</div>
</div></div>
<div id="cbBg" class="mbg" onclick="if(event.target===this)closeCB()"><div class="mbox" style="width:660px">
  <h3>새 설정 만들기
      <button class="mini x" onclick="closeCB()">닫기 ✕</button></h3>
  <p class="mhint" id="cbHint">해석 유형과 조건을 선택해 독립 config.json으로 저장합니다.</p>
  <div class="cbr" style="padding:0 0 8px">
   <label style="flex:none;width:120px">해석 유형</label>
   <select id="cbType" onchange="renderCBForm()" style="flex:1;width:auto;margin:0">
    <option value="warehouse">포대식 저장고 · 형상 사전 검사</option>
    <option value="immersion">액침냉각용</option>
    <option value="grain_silo">식량 저장고용</option>
   </select>
   <span class="u"></span>
  </div>
  <div class="cbr" style="padding:0 0 12px">
   <label style="flex:none;width:auto">설정 이름</label>
   <input id="cbName" style="flex:1;width:auto;text-align:left" maxlength="40" placeholder="예: 3mm_60초 또는 Chen_L9">
  </div>
  <div id="cbForm"></div>
  <div class="btnrow" style="margin-top:14px">
   <button class="btn pri" id="cbSave" onclick="saveCB()">설정 저장</button>
   <button class="btn sm" onclick="closeCB()">취소</button>
  </div>
</div></div>

<div id="exportBg" class="mbg" onclick="if(event.target===this)closeExport()"><div class="mbox" style="width:680px">
  <h3>Export <span class="badge" id="exProjName">현재 프로젝트</span>
      <button class="mini x" onclick="closeExport()">닫기 ✕</button></h3>
  <p class="mhint">현재 Viewer 프로젝트의 데이터와 지금 선택한 레이어·카메라·재생 배속을 기준으로 내보냅니다.</p>
  <div class="exgrid">
   <div class="excard">
    <h4>시뮬레이션 영상</h4>
    <p>현재 화면 옵션으로 첫 프레임부터 끝까지 재생·녹화합니다.</p>
    <select id="exVidFmt" aria-label="영상 형식">
     <option value="mp4">MP4</option><option value="webm">WebM</option>
    </select>
    <button class="btn pri" style="width:100%" onclick="startExportVideo()">영상 내보내기</button>
    <div class="exnote" id="exVidNote" style="display:none"></div>
   </div>
   <div class="excard">
    <h4>현재 3D 화면</h4>
    <p>현재 카메라와 레이어를 그대로 한 장의 고해상도 PNG로 저장합니다.</p>
    <button class="btn" style="width:100%" onclick="exportViewPNG()">현재 화면 PNG</button>
   </div>
  </div>
</div></div>

<div id="infoBg" class="mbg" onclick="if(event.target===this)closeInfo()"><div class="mbox" style="width:600px">
  <h3>CFD Studio <span class="badge" id="ifVer">__APP_VER__</span>
      <button class="mini x" onclick="closeInfo()">닫기 ✕</button></h3>
  <div class="tabs">
   <button id="ifT0" class="on" onclick="infoTab(0)">설명서</button>
   <button id="ifT1" onclick="infoTab(1)">사용법</button>
   <button id="ifT2" onclick="infoTab(2)">성능</button>
   <button id="ifT3" onclick="infoTab(3)">제작자</button>
  </div>
  <div class="ibx" id="ifB0">
   <p><a href="https://github.com/ReYoungSung/CFD-Studio/blob/main/docs/CFD-STUDIO-MANUAL.md" target="_blank" rel="noopener noreferrer"><b>설명서</b></a></p>
   <p>CFD Studio는 해석 양식 정의, 실행별 입력 보관, 대기열 관리와 결과 비교를 연결하는 작업 환경입니다.</p>
   <h4>작업 구조</h4>
   <ul><li><b>CFD Template</b>: 선택한 솔버의 빈 입력 양식·자료형·단위 정의</li><li><b>프리셋</b>: Template에 속한 재사용 가능한 입력값 묶음</li><li><b>프로젝트</b>: 같은 목적의 여러 Case와 결과를 보관하는 폴더</li><li><b>Case</b>: 독립적인 Config·종료 조건·로그·결과. 시작 시 입력 스냅샷 보존</li></ul>
   <h4>솔버와 Config</h4>
   <ul><li>솔버: 어떤 방정식과 알고리즘으로 계산할지 결정</li><li>유체 종류: 액체·기체·다상 구분. 물질과 물성값은 사용자가 입력</li><li>형상·격자: 해석 영역의 치수·배치·공간 분할 정의</li><li>물성·초기장·경계조건: 재료 특성, 시작 상태, 경계에서의 속도·압력·온도 등</li><li>수치 설정: 이산화 기법·선형 솔버·연결 알고리즘·시간간격</li><li>필수: 선택한 솔버·조건에 필요한 입력을 빨간색으로 표시</li></ul>
   <h4>솔버 선택</h4>
   <div class="kv"><table>
    <tr><td>icoFoam</td><td>비정상 층류. U·운동학적 압력 p·nu·PISO</td></tr>
    <tr><td>simpleFoam</td><td>정상 비압축성 유동. U·p·점성·SIMPLE</td></tr>
    <tr><td>pisoFoam / pimpleFoam</td><td>비정상 비압축성 유동. PISO / PIMPLE 및 시간간격</td></tr>
    <tr><td>buoyantSimpleFoam / buoyantPimpleFoam</td><td>정상 / 비정상 부력·열전달. 열역학·중력·T·p_rgh</td></tr>
    <tr><td>chtMultiRegionFoam</td><td>영역별 유체·고체 열전달. 고체 물성·접합면·영역별 수치 설정</td></tr>
    <tr><td>interFoam / interIsoFoam</td><td>등온 2상 계면. 상별 rho·nu·상분율·표면장력. MULES / isoAdvector</td></tr>
    <tr><td>rhoPimpleFoam</td><td>압축성 유동·에너지. 상태방정식·열물성·U·p·T</td></tr>
    <tr><td>전용 구성</td><td>다상 열전달·상변화 구성과 저장고 열·스칼라 구성. 각 Template의 조건·제한 확인</td></tr>
   </table></div>
   <h4>상태 읽기</h4>
   <ul><li><b>설치 확인</b>: 현재 OpenFOAM 환경에 실행 파일이 존재하는지 확인</li><li><b>입력 검사</b>: 정의한 필수값·자료형·기본 범위 확인. 물리 정확도 보증은 별도</li><li><b>실행 연결</b>: Config를 솔버 입력으로 변환하고 결과를 읽는 어댑터. 새 Template의 JSON만으로 자동 연결되지 않음</li><li><b>실행 상태 / 수치 검사 / 시각화</b>: 계산 진행, 수치 점검, Viewer 준비 상태를 각각 표시</li></ul>
   <h4>결과와 시간</h4>
   <ul><li>3D Virtual Viewer: 저장된 장·형상·시간별 변화 탐색</li><li>Data Sheet Viewer: 왼쪽 전체 평균 최대 3개 물리량, 오른쪽 좌표별 최근접 저장 셀의 시계열 조회</li><li>그래프 형식: 선·막대·산점도 · 표시 형식 변경은 원본값에 영향 없음</li><li>계산 시간간격·저장 간격·재생 속도·종료 조건은 서로 독립</li><li>파일 검사·입력 검사 통과와 격자 수렴·실험 검증은 각각 별도 판단</li></ul>
   <p><a href="https://github.com/ReYoungSung/CFD-Studio/blob/main/docs/solver-input-definitions-20260929.md" target="_blank" rel="noopener noreferrer">솔버별 입력 정의</a></p>
  </div>
  <div class="ibx" id="ifB1" style="display:none">
   <p><b>CFD</b>: 입력·계산·결과 준비. <b>Viewer</b>: 저장 결과 조회·내보내기.</p>
   <p>프로젝트는 여러 Case를 묶는 공간이며, CFD Case는 입력과 결과를 독립적으로 보관하는 계산 단위입니다. 항목을 펼치면 조작 순서가 표시됩니다.</p>
   <h4>CFD</h4>
   <p>화면 상단 <b>CFD</b> 탭. 프로젝트 생성 → Case 저장 → 대기열 실행 → 결과 준비</p>
   <details><summary>기존 프로젝트 등록</summary><ul><li>CFD 화면 왼쪽 상단 <b>프로젝트 찾기</b> 클릭</li><li><b>찾기</b>로 프로젝트 폴더 선택 또는 전체 경로 입력 → <b>추가</b></li><li>프로젝트 파일·실행 목록 검증 후 왼쪽 목록에 등록. 이미 등록된 폴더는 해당 프로젝트 선택</li><li>검증 실패 시 안내 내용을 확인하고 올바른 폴더 선택. 가져온 대기열은 일시정지 상태로 복원</li></ul></details>
   <details><summary>프로젝트 생성</summary><ul><li>왼쪽 <b>프로젝트</b> 제목 아래 <b>새 프로젝트</b> 클릭</li><li><b>프로젝트 이름</b> 입력 → <b>프로젝트 폴더</b> 옆 <b>찾기</b>로 저장 폴더 지정</li><li><b>프로젝트 설명</b> 입력 → <b>CFD Template</b> 선택 → <b>직접 입력 → Config 입력</b> 또는 해당 Template의 프리셋 선택 → <b>저장</b></li><li><b>프리셋에 저장</b> 체크 시 새 이름으로 입력값 프리셋 저장 · 기본 해제</li><li>저장한 프로젝트는 왼쪽 목록에서 이름을 클릭해 선택</li></ul></details>
   <details><summary>프로젝트 정보 및 저장 폴더 변경</summary><ul><li>프로젝트 선택 → 화면 오른쪽 상단 <b>프로젝트 관리</b></li><li>이름·설명·폴더·기본 프리셋 수정 → <b>저장</b>. C·D 등 드라이브 선택 가능</li><li>기본 프리셋 변경은 이후 생성하는 Case에 적용</li><li>폴더 변경은 복사·검증 후 연결 전환. 원본 보존. 계산·결과 저장 중에는 변경 불가</li></ul></details>
   <details><summary>Config 및 공간 정보</summary><ul><li>Template·프로젝트·Case에 공통 편집 화면 사용</li><li>왼쪽 Config 입력 · 가운데 3D 형상 · JSON 선택 시 맨 오른쪽 편집창 표시</li><li>네임태그 또는 요소 목록 선택 → 물질 상태·위치·Scale·물성 입력</li><li>형상 JSON: shape·unit·좌표·치수 직접 입력 · 기본 형상 예시에서 직육면체·구·원기둥 선택 가능</li><li><b>물질 상태</b>: 고체·액체·기체 선택 → 솔버에 맞는 기본 입력 확인</li><li><b>+ 속성</b>: 상태·솔버에 맞는 추가 속성 선택 또는 직접 정의 · 계산 반영에는 실행 연결 필요</li><li>목록 값: 각 입력칸에 작성 · <b>+</b>로 추가 · 행 오른쪽 <b>−</b>로 삭제</li><li>액체 요소 선택 → <b>증기 물성·상변화</b> 입력 · 종료 조건·격자·결과 저장·측정 위치는 공통 분류에서 입력</li><li><b>온도별 물성</b>: 절대온도(K)와 물성값을 같은 행에 입력 · <b>+</b>와 <b>−</b>로 행 추가·삭제</li><li>측정 좌표는 X·Y·Z 입력 · 솔버에 모델 후보가 있으면 드롭다운에서 선택</li><li><b>JSON 가져오기</b>: Config 또는 Studio 필드 정의 선택 → 중첩 입력·목록·표로 표시 · 저장 전에는 기존 프로젝트·프리셋 유지</li><li>항목 제목 옆 <b>JSON</b> 또는 <b>전체 JSON</b> 선택 → 직접 편집 → <b>JSON 저장</b></li><li>JSON 저장은 현재 초안에 반영 · <b>실행 저장</b> 또는 상위 Template·프로젝트 <b>저장</b>으로 완료</li><li>시작한 Case는 조회 전용 · <b>이 Config로 새 Case</b>로 수정</li><li>Template 정의 파일은 Studio 설치 폴더 내부 · 프로젝트·Case 정의 파일은 프로젝트 폴더 내부에 자동 저장</li><li>직접 정의한 형상은 파일 경로 입력 불필요 · 기존 격자 가져오기는 실제 원본 필요</li><li>형상·격자 설정 JSON과 실제 계산 격자·솔버 실행은 별도</li><li>드래그 회전 · 휠 확대·축소 · 더블클릭 시점 초기화</li></ul></details><details><summary>CFD Template 생성 및 편집</summary><ul><li>새 프로젝트의 <b>CFD Template</b> 선택란 옆 <b>+</b>로 생성 가능 · 프로젝트 입력 유지</li><li>Template 저장 후 자동 선택 · 취소하면 기존 선택 유지</li><li>왼쪽 <b>CFD Template 리스트 → +</b></li><li><b>해석 대상 → 유동·시간 → 영역·종료</b> 순서로 설문 작성 → <b>솔버 추천</b></li><li><b>여기에 없음</b>: 지원하지 않는 항목 안내 후 추천·생성 중지 · 선택 수정 또는 취소 가능 · 현재 등록된 솔버·양식 기준</li><li>후보의 기능·출력·제한 확인 → 솔버 선택 → <b>양식 생성</b></li><li>후보가 없으면 <b>선택한 조건</b>과 후보별 변경값 확인 → 목적에 맞는 경우 <b>이 조건으로 다시 추천</b> · 버튼을 누르기 전에는 응답 유지</li><li>다상 유체의 일반 유동·열전달 목적도 지원 솔버와 연결 · 추천과 설치·실행 연결은 별도</li><li><b>양식 확인</b>에서 이름·설명 입력 → <b>양식 편집</b>에서 항목명·입력 형식·단위 확인 → <b>저장 → Template 저장</b></li><li><b>설문 수정</b>으로 재구성 · 취소하면 기존 양식 유지 · 초기 형상은 Template에서 정의 · 물성·운전값은 프로젝트 생성 시 입력</li><li>기존 Template의 솔버는 고정 · 다른 솔버는 새 Template 생성</li><li><b>JSON 내보내기 / JSON 가져오기</b>: Template 정의 파일 · 실제 입력값 JSON은 프로젝트의 <b>Config 입력</b>에서 관리</li><li><b>설치 확인</b>: 실행 파일 유무 확인 · 신규 Template 계산은 실행기 연결 필요</li></ul></details>
   <details><summary>Config 입력 양식</summary><ul><li>왼쪽 분류 선택 → 항목명 옆에 값 입력 · 단위는 입력칸 옆에 표시</li><li>필요한 입력 항목 우선 표시 · <b>필수</b>는 빨간색으로 표시 · <b>전체 항목</b>에서 선택 입력과 자동 설정 확인</li><li><b>항목 추가</b>: 표시 이름·입력 형식·단위 지정 · 숫자·정수·문자·사용 여부·목록·항목 묶음 선택</li><li><b>구조 편집</b>: JSON 키·자료형 변경 · 프로젝트 값 입력 화면에는 표시하지 않음</li><li>오른쪽 <b>JSON / JSON 가져오기 / JSON 내보내기</b>: 전체 데이터 편집·파일 관리</li><li><b>입력 검사</b> 결과의 항목명을 눌러 누락 입력으로 이동</li><li>선택 항목의 기존값과 프리셋 유지 · 물성·경계조건·시간간격은 임의의 기본값으로 채우지 않음</li><li><b>적용</b> 후 상위 화면에서 저장</li></ul></details>
   <details><summary>CFD Case 생성 및 Config 입력</summary><ul><li>프로젝트 선택 → 화면 오른쪽 상단 파란 <b>+ CFD Case</b></li><li><b>Case 이름</b> 입력 → 왼쪽 Config 항목 선택 → 오른쪽 값 입력</li><li>숫자 입력란은 문자 입력·붙여넣기를 차단. 정수 입력란은 소수도 차단. 빈 필수값·미완성 숫자·잘못된 JSON은 수정 후 저장</li><li><b>종료 조건·목표</b>에서 <b>특정 물리시간</b> 또는 <b>저장 프레임 수</b> 선택 → 목표값 입력</li><li>프레임 수 선택 시 <b>0초 초기 프레임 포함</b> 여부 확인. <b>수렴 기준</b>은 현재 선택 불가</li><li>창 하단 파란 <b>실행 저장</b> → 실행 목록에 Case 추가. 계산 시작은 대기열에서 진행</li></ul></details>
   <details><summary>프리셋 저장 및 불러오기</summary><ul><li>Case의 Config 편집창 상단 <b>프리셋에 저장</b> 체크박스</li><li>체크 해제: 해당 Case에만 저장. 체크: 새 프리셋 이름 입력 → <b>실행 저장</b> 시 별도 프리셋 저장</li><li>기존 값 사용: <b>프리셋 불러오기</b>에서 선택 → <b>불러오기</b></li></ul></details>
   <details><summary>대기열 구성 및 CFD 실행</summary><ul><li>가운데 <b>실행 목록</b>에서 Case 선택 → 오른쪽 <b>대기열에 추가</b></li><li>아래 <b>대기열</b> 영역의 파란 <b>대기열 시작</b> → <b>계산 중</b> 상태 확인</li><li>여러 Case는 각각 추가. 대기열 행의 <b>↑ / ↓</b>로 순서 변경, <b>제외</b>로 대기열에서 제거</li><li><b>다음 실행부터 일시정지</b>: 현재 Case 계산 유지. <b>실행 중단</b>: 선택한 실행 중 Case 중단</li><li>진행 내용: 오른쪽 <b>솔버 로그</b>에서 확인 · 항상 표시</li><li>실패: 원인 확인 → <b>실패 사유 및 복구</b> → <b>다시하기 / 이어하기 / 건너뛰기</b> → <b>대기열 시작</b>. 앱 재시작 후에도 대기열을 확인하고 시작</li><li><b>다시하기</b>: 기존 기록을 보존하고 처음부터 계산. Config 검증 실패 시 입력 수정 필요</li><li><b>이어하기</b>: 확인된 재시작 저장 지점부터 계산. 재시작 데이터가 없거나 실행기가 지원하지 않으면 사유 표시. 저장고 실행기는 현재 재개 미지원</li></ul></details>
   <details><summary>실행 Config 조회 및 비교</summary><ul><li>실행 목록에서 Case 선택 → 오른쪽 <b>Config 편집</b> 또는 <b>Config 보기</b></li><li>계산 전: 입력 수정 → <b>실행 저장</b>. 시작한 Case: 실행 당시 입력 조회</li><li>입력을 변경하여 새 Case 생성: <b>Config 보기 → 이 Config로 새 Case</b></li><li><b>Config 차이 / 솔버 로그</b>: Case 선택 시 접힘 없이 표시 · 긴 내용은 각 영역에서 스크롤</li><li><b>Config 차이</b>: Case 생성 시 저장한 기준 Config와 비교</li><li>항목 찾기: 편집창 왼쪽 <b>Config 검색</b></li></ul></details>
   <details><summary>결과 생성 및 Viewer 열기</summary><ul><li>실행 목록에서 Case 선택 → 오른쪽 파란 결과 버튼</li><li><b>생성</b>: 계산 결과를 시각화용으로 준비. <b>업데이트</b>: 새 결과 반영. <b>열기</b>: 준비된 Viewer 열기</li><li><b>생성 / 업데이트</b> 완료 후 <b>열기</b>. 회색 버튼이면 실행 상태·솔버 로그 확인</li><li>원본 확인: 같은 영역의 <b>결과 폴더</b></li></ul></details>
   <details><summary>전체 CSV 내보내기</summary><ul><li><b>CFD → 실행 목록에서 Case 선택 → 오른쪽 전체 CSV</b></li><li>모든 저장 시점의 시계열과 공간 데이터를 CSV로 묶어 ZIP 다운로드. 그래프 선택·표시 밀도와 무관</li><li><b>time_series.csv</b>: 전체 결과 항목·통계·단위. <b>fields/</b>: 저장된 공간 배열. <b>manifest.json</b>: Case·Config·행 수</li><li>시각화 격자로 저장된 Case는 해당 격자를 내보냅니다. 저장되지 않은 원본 셀은 복원하지 않습니다.</li></ul></details>
   <h4>Viewer</h4>
   <p>화면 상단 <b>Viewer</b> 탭 또는 Case의 <b>열기</b>. Case 선택 → 시각화율 확인 → 3D·그래프 조회</p>
   <details><summary>프로젝트 및 CFD Case 선택</summary><ul><li>왼쪽 프로젝트 이름 클릭 → 아래 <b>CFD Case</b> 목록에서 Case 선택</li><li>선택 항목은 파란 테두리. 3D·그래프 모두 선택한 Case의 결과 표시</li><li>다른 Case 비교: 목록에서 다른 항목 선택. 한 번에 한 Case 표시</li><li>계산 화면 복귀: 상단 <b>CFD</b> 탭</li></ul></details>
   <details><summary>데이터 시각화율 확인 및 업데이트</summary><ul><li>왼쪽 <b>CFD Case</b> 목록의 각 항목 안 게이지에서 현재 시각화 준비 상태 확인</li><li>갱신: <b>CFD Case</b> 제목 오른쪽 둥근 사각형의 <b>원형 화살표</b> 클릭. 포인터를 올리면 <b>다시 읽기</b> 표시</li><li>프로젝트 내 Case들의 준비 상태 확인 및 선택한 Case의 결과 다시 읽기</li><li><b>100%</b>: 시각화 준비 완료. CFD 계산 진행률·수렴·실험 검증과 별도</li><li>새 원본의 변환이 필요하면 <b>CFD</b> 탭 → Case 선택 → <b>생성 / 업데이트</b> → <b>열기</b></li></ul></details>
   <details><summary>3D Virtual Viewer 조작</summary><ul><li>왼쪽 상단 <b>3D Virtual</b> 버튼 클릭 → 중앙 3D 화면 표시. 선택한 모드는 파란 테두리와 배경으로 표시</li><li>아래 파란 <b>▶</b>: 재생·일시정지. 시간 막대: 시점 선택. 오른쪽 <b>1×</b>: 재생 배속</li><li>시간 표시: <b>0.00s (전체 프레임 수)</b></li><li>드래그: 회전. 휠: 확대·축소. 더블클릭: 기본 시점 복원</li><li>오른쪽 패널 맨 위 <b>표시 밀도</b>: <b>표준 / 세밀 / 매우 세밀</b> 선택. 속도 벡터 표시 개수 조절</li><li>오른쪽 <b>결과 데이터 / 설계 레이어</b>: 물리량·형상 표시. 항목은 Case의 저장 데이터에 따라 변경</li></ul></details>
   <details><summary>Data Sheet Viewer 전환 및 수치 조회</summary><ul><li>왼쪽 상단 두 버튼: 왼쪽 <b>3D Virtual</b>, 오른쪽 <b>Data Sheet</b> · 선택 테두리가 현재 모드로 이동</li><li>왼쪽 <b>전체 평균</b>: 윗줄 <b>그래프 형식 → 선 / 막대 / 산점도</b> 선택 → 아랫줄 <b>요소 1 / 2 / 3</b>에서 최대 3개 물리량 선택. 단위별 Y축 사용. <b>요소 2 / 3 → 선택 안 함</b>으로 해제. 형식 변경 시 물리량·조회 시점 유지. 그래프 클릭·드래그 → 세로 점선과 X·Y 수치 확인</li><li>두 그래프 배경 패널의 높이와 그래프·상세값 위치 정렬 · 좁은 화면에서는 세로 배치</li><li>일반 문구는 선택 방지. Config 입력값·조회값과 Viewer 하단 상세 수치는 선택·복사 가능</li><li>그래프에 초점을 둔 뒤 <b>← / →</b>로 시점 이동. 이 화면에는 재생 버튼 없음</li><li>전체 저장 구간을 조회하려면 그래프 위 <b>전체 구간 읽기</b> · 읽는 중 <b>읽기 중지</b>, 완료 후 <b>다시 읽기</b> 표시. 그래프 저장: 각 그래프 상단 <b>Export</b> → <b>PNG 이미지 / CSV 데이터</b></li><li>오른쪽 <b>좌표 조회</b>: 결과 항목 선택 → 입력란의 <b>최소값 ~ 최대값</b> 확인 → <b>X·Y·Z</b>(m) 입력 → <b>조회</b>. 범위 밖 입력은 확정·조회 불가. 가장 가까운 저장 셀의 시간별 값 표시</li><li>3D 화면 전환: 왼쪽 상단 <b>3D Virtual</b> 버튼 클릭</li></ul></details>
   <details><summary>영상·이미지·CSV 내보내기</summary><ul><li><b>3D Virtual</b>: 하단 재생 바 오른쪽 <b>Export</b> → <b>영상 내보내기</b> 또는 <b>현재 화면 PNG</b></li><li>영상 녹화 종료: 재생 바의 <b>녹화 종료</b></li><li><b>Data Sheet</b>: 저장할 그래프 상단 <b>Export</b> → <b>PNG 이미지</b> 또는 <b>CSV 데이터</b></li><li>그래프 이미지는 현재 축·곡선·조회 위치를 포함하며, CSV는 해당 그래프에 읽어온 구간의 수치를 저장</li><li>전체 저장 구간이 필요한 경우 해당 그래프의 <b>전체 구간 읽기</b> 완료 후 Export</li></ul></details>
   <h4>언어변환</h4>
   <ul><li>오른쪽 상단 <b>환경 설정 → 언어변환 → 한국어 / English / 日本語</b></li><li>즉시 적용 · 별도 저장 없이 현재 브라우저에 보관 · 같은 주소로 재접속하면 복원</li><li>계산 중에도 언어 변경 가능 · 프로젝트명·입력값·원본 로그·JSON 키는 원문 유지</li><li>다른 브라우저·접속 주소를 사용하거나 브라우저 데이터를 삭제하면 다시 선택</li></ul>
   <h4>설치 및 프로그램 실행</h4>
   <p><b>Windows 10/11 x64 지원 · macOS(Mac) 미지원</b></p>
   <ul><li>최초 설치: WSL2 Ubuntu 설치·사용자 초기화 → <b>cfd_studio/설치.bat</b> → <b>cfd_studio/실행.bat</b></li><li>설치 완료 후 실행: <b>실행.bat</b> 더블클릭. Windows Python 포함. 전용 솔버·GPU 환경은 별도 준비</li></ul>
   <p><a href="https://github.com/ReYoungSung/CFD-Studio/blob/main/docs/CFD-STUDIO-USER-GUIDE.md" target="_blank" rel="noopener noreferrer"><b>사용법</b></a> · <a href="https://github.com/ReYoungSung/CFD-Studio/blob/main/cfd_studio/README.md" target="_blank" rel="noopener noreferrer">설치</a> · 모델·단위·검증 범위는 위 <b>설명서</b> 탭</p>
  </div>
  <div class="ibx" id="ifB2" style="display:none">
   <h4 style="margin-top:0">계산 성능</h4>
   <ul><li>계산 시간은 격자 수, 해석 모델, 시간간격, 종료 조건과 CPU·메모리 성능에 따라 달라집니다.</li><li>격자 세분화와 저장 간격 축소 시 계산량·메모리·저장 공간 요구량이 증가합니다.</li><li>실행 목록에서 계산 상태와 마지막 저장 시점을 확인하고, 솔버 로그에서 진행 내용을 조회할 수 있습니다.</li></ul>
   <h4>계산 자원</h4>
   <ul><li>오른쪽 상단 <b>환경 설정</b>에서 CPU 사용 상한, MPI 작업자 수, GPU와 계산 모드를 지정합니다.</li><li>자동 설정은 논리 CPU 수와 사용 상한을 기준으로 병렬 작업자 수를 정합니다. 작업자 수에 따른 성능은 격자 규모와 통신 비용에 따라 달라집니다.</li><li><b>CPU Only</b>: CPU 계산. <b>CPU + GPU 병행</b>: 지원 구성에서 압력 방정식에 GPU 사용. <b>GPU Only</b>: 별도의 OpenCFD GPU 실행 환경 필요</li><li>GPU 사용에는 솔버 지원, 호환 라이브러리와 GPU 메모리 확보가 필요합니다.</li></ul>
   <h4>시각화 성능</h4>
   <ul><li>3D 표시에는 WebGL2 지원 브라우저가 필요합니다.</li><li>표시할 셀·벡터·프레임 수가 많을수록 메모리 사용량과 읽기 시간이 증가합니다.</li><li>표시 밀도는 화면에 표시할 표본 수를 조절합니다. 계산 격자와 저장된 결과값은 변경하지 않습니다.</li><li>재생 배속은 저장된 결과의 재생 속도이며 CFD 계산 속도와 별개입니다.</li></ul>
   <h4>저장 공간</h4>
   <ul><li>프로젝트 폴더에 입력, 실행 기록, 원본 결과와 시각화 캐시를 보관합니다.</li><li>장시간 계산 전에는 저장 간격과 출력 항목을 확인하고 충분한 디스크 공간을 확보하세요.</li></ul>
  </div>
  <div class="ibx" id="ifB3" style="display:none">
   <div class="kv">
    <table>
     <tr><td>제작자</td><td><b>이영성</b></td></tr>
     <tr><td>소속</td><td>한동대학교 CGLAB</td></tr>
     <tr><td>지원</td><td>한동대학교 Credo Flagship</td></tr>
    </table>
   </div>
   <h4>협력</h4>
   <p style="margin:0 0 10px">한동대학교 <b>이권영 교수님 연구실</b> — 이중 액침냉각 실증 실험 및 실측 데이터 제공.
      이 소프트웨어는 그 실험을 CFD로 재현하기 위해 만들어졌습니다.</p>
   <h4>문의</h4>
   <p style="margin:0">문제 보고 시 개인정보와 저장 경로를 제외한 오류 로그를 첨부해 주세요.</p>
  </div>
</div></div>

<div id="settingsBg" class="mbg" onclick="if(event.target===this)closeSettings()"><div class="mbox" style="width:620px">
 <h3>환경 설정 <span class="badge">PC별</span><button class="mini x" onclick="closeSettings()">닫기 ✕</button></h3>
 <div class="language-row"><span>화면 언어</span><button class="btn" id="languageToggle" type="button" aria-expanded="false" aria-controls="languageOptions">언어변환 <span aria-hidden="true">⌄</span></button></div>
 <div id="languageOptions" class="language-options" role="group" aria-label="화면 언어" hidden><button class="btn" type="button" data-language="ko" lang="ko" translate="no" aria-pressed="true">한국어</button><button class="btn" type="button" data-language="en" lang="en" translate="no" aria-pressed="false">English</button><button class="btn" type="button" data-language="ja" lang="ja" translate="no" aria-pressed="false">日本語</button><small style="flex-basis:100%;color:var(--muted)">이 브라우저에 저장되며 즉시 적용됩니다</small></div>
 <p class="mhint">현재 PC에서 계산에 사용할 CPU·MPI·GPU 자원을 지정합니다. 저장한 변경은 다음 계산 시작·재개 시 적용됩니다. 프로젝트별 물성·경계조건·격자는 Case의 Config에서 입력합니다.</p>
 <div class="setrow"><label>CPU 사용 상한<span>계산에 배정할 논리 CPU 비율입니다. 다른 작업의 여유를 남기며, 최대 80%까지 지정할 수 있습니다.</span></label><div><input id="setCpu" type="number" min="1" max="80" step="1"></div></div>
 <div class="setrow"><label>MPI 작업자<span id="setMpiHint">CPU 상한 안에서 자동 배정</span></label><div><select id="setMpi"></select></div></div>
 <div class="setrow"><label>계산 GPU<span>GPU 계산을 지원하는 실행 구성에서 사용할 장치입니다. 자동 선택은 감지된 NVIDIA GPU의 성능 점수를 기준으로 합니다.</span></label><div><select id="setGpu"></select></div></div>
 <div class="setrow"><label>계산 모드<span>CPU Only는 CPU 계산, 병행 모드는 지원 구성의 압력 계산만 GPU 사용, GPU Only는 별도 OpenCFD 환경이 필요합니다. 솔버 설치만으로 GPU 지원이 생기지는 않습니다.</span></label><div><select id="setPressureMode"><option value="cpu">CPU Only (권장)</option><option value="gpu">CPU + GPU 병행 (p_rgh)</option><option value="gpu_only">GPU Only (OpenCFD 개발)</option></select><div id="setGpuOnlyHint" class="mhint" style="margin-top:6px"></div></div></div>
 <details style="margin-top:12px"><summary>환경 설정 안내</summary><ul class="mhint"><li>MPI 작업자는 영역을 나누어 계산하는 병렬 프로세스 수입니다. 많을수록 통신·메모리 비용도 늘어나므로 격자 규모에 맞게 선택합니다.</li><li>자원 수는 계산 속도·메모리 사용에 영향을 줍니다. 격자 정확도나 수렴 기준을 대신하지 않습니다.</li><li>원본·결과·캐시는 프로젝트 생성·관리에서 지정한 폴더에 보관합니다.</li><li>Template에서 솔버·입력 항목을 정의하고, 프리셋과 Case에서 실제 값을 채웁니다.</li><li>설치 확인은 실행 파일 유무를 확인합니다. 라이브러리 호환성·GPU 지원·새 Template의 실행 연결은 별도로 확인합니다.</li></ul></details>
 <div id="setSummary" class="mhint" style="margin:12px 0 0"></div>
 <div class="row" style="margin-top:16px"><button class="btn" onclick="closeSettings()">취소</button><button class="btn pri" id="setSave" onclick="saveSettings()">저장</button></div>
</div></div>

<div id="modalBg"><div id="modal">
  <h3 id="mdTitle"></h3>
  <p id="mdMsg"></p>
  <div class="row"><button class="btn" onclick="closeModal()">취소</button>
  <button class="btn pri" id="mdOk"></button></div>
</div></div>

<script>
"use strict";
// ══════════════ 상태 ══════════════
let CFG=null, RUNCFG=null, VIZCFG=null, IMMERSIONCFG=null, CFGREF='', CFGFILE='config.json', ACTIVE_CONFIG_FILE=null;
let CFGLOAD=null, CFGLOADSEQ=0;
let FRAMES=[], idx=0, playing=false, clock=0, last=performance.now();
let Cxyz=null, HIST=[];   // HIST: [t,T1..T4]

function toast(msg,err){const d=document.createElement('div');d.className='toast'+(err?' err':'');d.textContent=msg;
 document.getElementById('toasts').appendChild(d);setTimeout(()=>d.remove(),4200);}

// 확인 모달 (처음부터 실행 / 캐시 비우기 공용)
let mdFn=null;
function confirmBox(title,msg,okLabel,fn){
 document.getElementById('mdTitle').textContent=title;
 document.getElementById('mdMsg').textContent=msg;
 document.getElementById('mdOk').textContent=okLabel;
 mdFn=fn; document.getElementById('modalBg').style.display='flex';}
document.getElementById('mdOk').onclick=()=>{closeModal(); if(mdFn)mdFn();};
function closeModal(){document.getElementById('modalBg').style.display='none';}
function askClear(){confirmBox('시각화 캐시를 비울까요?',
 '변환된 프레임 파일이 삭제됩니다. [결과 가져오기]로 언제든 다시 만들 수 있지만 시간이 걸립니다.',
 '비우기',doClear);}

// ══════════════ OpenFOAM 바이너리 파서 ══════════════
function findStr(u8,s,from){const n=s.length;outer:for(let i=from||0;i<u8.length-n;i++){for(let j=0;j<n;j++)if(u8[i+j]!==s.charCodeAt(j))continue outer;return i;}return -1;}
function parseFoam(buf,ncomp){
 if(Object.prototype.toString.call(buf)!=='[object ArrayBuffer]'||![1,3].includes(ncomp))throw Error('OpenFOAM 필드 입력 형식 오류');
 const u8=new Uint8Array(buf);
 const i0=findStr(u8,"internalField",0); if(i0<0) throw "internalField 없음";
 const head=String.fromCharCode.apply(null,u8.subarray(i0,i0+220));
 const m=head.match(/List<(?:scalar|vector)>\s*\n(\d+)\s*\n\(/); if(!m) throw "binary 형식 인식 실패";
 const n=parseInt(m[1]); const start=i0+m.index+m[0].length;
 if(!Number.isSafeInteger(n)||n<1||start+n*8*ncomp>buf.byteLength)throw Error('OpenFOAM 필드 길이 불일치');
 return {n, data:finitePacked(new Float64Array(buf.slice(start,start+n*8*ncomp)),'OpenFOAM')};
}

// ══════════════ 흐름장 (10mm 격자 압축 U) ══════════════
let FLOWMAP={};           // t(number) → {nx,ny,nz,bb:[x0,y0,z0,x1,y1,z1], u:Float32Array}
function showErr(t,g){document.getElementById('ebT').textContent=t;
 document.getElementById('ebG').textContent=g||'';
 document.getElementById('errBanner').style.display='flex';}
function hideErr(){document.getElementById('errBanner').style.display='none';}
let GRIDWARNED=false;
function chkGrid(g,name){ // 흐름·온도 격자 범위 vs 현재 형상 — 다른 실행 파일 조합 감지
 const c=VIZCFG||CFG;if(!c||GRIDWARNED)return;
 let mismatch=false;
 if(isSiloConfig(c)){
  const p=c.published||{},D=+p.storage_diameter_m,H=+p.total_height_m;
  if(!(D>0&&H>0))return;
  mismatch=Math.abs(g.bb[3]-g.bb[0]-D)>D*.12||Math.abs(g.bb[4]-g.bb[1]-D)>D*.12||Math.abs(g.bb[5]-g.bb[2]-H)>H*.15;
 }else{
  const tank=c.tank;if(!tank)return;
  const W=+tank.width_mm/1e3,H=+tank.liquid_height_mm/1e3;
  if(!(W>0&&H>0))return;
  mismatch=Math.abs(g.bb[3]-g.bb[0]-W)>W*.12||Math.abs(g.bb[4]-g.bb[1]-H)>H*.15;
 }
 if(mismatch){
  GRIDWARNED=true;
  showErr(name+' 격자 범위가 현재 형상(config)과 다릅니다',
   '다른 격자·형상의 파일이 섞였습니다. 해당 Project 폴더의 config.json과 결과 파일이 같은 해석인지 확인하세요.');}}
function packedGridHeader(buf,magicText,channels,bytesPerValue=4){
 if(Object.prototype.toString.call(buf)!=='[object ArrayBuffer]'||buf.byteLength<40)throw Error(magicText+' 헤더 길이 불일치');
 const dv=new DataView(buf),magic=[...magicText].reduce((n,c)=>(n<<8)|c.charCodeAt(0),0)>>>0;
 if(dv.getUint32(0,false)!==magic)throw Error(magicText+' 형식 아님');
 const nx=dv.getUint32(4,true),ny=dv.getUint32(8,true),nz=dv.getUint32(12,true),n=nx*ny*nz;
 if(!nx||!ny||!nz||!Number.isSafeInteger(n)||buf.byteLength!==40+n*channels*bytesPerValue)
  throw Error(magicText+' 격자·데이터 길이 불일치');
 const bb=[];for(let i=0;i<6;i++)bb.push(dv.getFloat32(16+4*i,true));
 if(bb.some(x=>!Number.isFinite(x))||bb.some((x,i)=>i<3&&x>=bb[i+3]))
  throw Error(magicText+' 공간 범위 불일치');
 return {nx,ny,nz,n,bb};
}
function finitePacked(values,name){
 for(const value of values)if(!Number.isFinite(value))throw Error(name+' 유효하지 않은 필드값');
 return values;
}
function parseFlow(buf){
 const {nx,ny,nz,bb}=packedGridHeader(buf,'FLW1',3);
 const g=compactSparsePlanes({nx,ny,nz,bb,u:finitePacked(new Float32Array(buf.slice(40)),'유동')},['u'],3);
 chkGrid(g,'유동(flow)'); return g;
}
function flowFor(t){ // 현재 프레임 t와 가장 가까운 흐름장 (0.6s 이내)
 let best=null,bd=0.6;
 for(const k in FLOWMAP){const d=Math.abs(+k-t); if(d<bd){bd=d;best=FLOWMAP[k];}}
 return best;
}
// ── 액체 상분율 (10mm 격자 alpha.water + alpha.vapour, liquid는 합=1로 복원) ──
let PHASEMAP={},PHASETIMES=[],PHASESEQ=0,PHASECACHE=new Map();
function parsePhase(buf){
 if(Object.prototype.toString.call(buf)!=='[object ArrayBuffer]'||buf.byteLength<40)throw Error('phase 헤더 길이 불일치');
 const magic=new DataView(buf).getUint32(0,false),version=magic===0x50485331?'PHS1':magic===0x50485332?'PHS2':null;
 if(!version)throw Error('phase 형식 아님');
 const {nx,ny,nz,n,bb}=packedGridHeader(buf,version,version==='PHS2'?3:2,1);
 const g={nx,ny,nz,bb,w:new Uint8Array(buf,40,n),v:new Uint8Array(buf,40+n,n),
  m:magic===0x50485332?new Uint8Array(buf,40+2*n,n):null,_pid:++PHASESEQ};
 chkGrid(g,'액체 상분율(phase)');return g;
}
function phaseFor(t){
 const keys=Object.keys(PHASEMAP);
 if(PHASETIMES.length!==keys.length){
  PHASETIMES=keys.map(Number).filter(Number.isFinite).sort((a,b)=>a-b);PHASECACHE.clear();
 }
 if(!PHASETIMES.length)return null;
 if(t<=PHASETIMES[0])return PHASEMAP[PHASETIMES[0]];
 const last=PHASETIMES[PHASETIMES.length-1];if(t>=last)return PHASEMAP[last];
 let hi=1;while(hi<PHASETIMES.length&&PHASETIMES[hi]<t)hi++;
 const ta=PHASETIMES[hi-1],tb=PHASETIMES[hi],A=PHASEMAP[ta],B=PHASEMAP[tb];
 if(!A||!B)return A||B||null;
 if(A.nx!==B.nx||A.ny!==B.ny||A.nz!==B.nz)return (t-ta<tb-t)?A:B;
 // 구형 프로젝트에서 CFD 값을 새로 만드는 것이 아니라, 저장된 두 alpha 스냅샷 사이를
 // 20단계로 선형 보간해 거친 저장 간격의 계단식 재생만 완화한다. 새 프로젝트는 모든 필드가 같은 실제 시각으로 저장된다.
 const q=Math.round(Math.max(0,Math.min(1,(t-ta)/(tb-ta)))*20)/20;
 if(q<=0)return A;if(q>=1)return B;
 const ck=A._pid+':'+B._pid+':'+q;if(PHASECACHE.has(ck))return PHASECACHE.get(ck);
 const n=A.w.length,w=new Uint8Array(n),v=new Uint8Array(n),qa=1-q;
 for(let i=0;i<n;i++){w[i]=Math.round(A.w[i]*qa+B.w[i]*q);v[i]=Math.round(A.v[i]*qa+B.v[i]*q);}
 const P={nx:A.nx,ny:A.ny,nz:A.nz,bb:A.bb,w,v,m:A.m||B.m||null,_pid:ck,_interpolated:true};
 PHASECACHE.set(ck,P);return P;
}
function samplePhase(P,x,y,z,out){
 if(!P){out[0]=out[1]=0;return;}
 const [x0,y0,z0,x1,y1,z1]=P.bb;
 let gx=(x-x0)/(x1-x0)*P.nx-.5,gy=(y-y0)/(y1-y0)*P.ny-.5,gz=(z-z0)/(z1-z0)*P.nz-.5;
 gx=Math.max(0,Math.min(P.nx-1.001,gx));gy=Math.max(0,Math.min(P.ny-1.001,gy));gz=Math.max(0,Math.min(P.nz-1.001,gz));
 const i=gx|0,j=gy|0,k=gz|0,fx=gx-i,fy=gy-j,fz=gz-k;let sw=0,sv=0;
 for(let dz=0;dz<2;dz++)for(let dy=0;dy<2;dy++)for(let dx=0;dx<2;dx++){
  const q=(dx?fx:1-fx)*(dy?fy:1-fy)*(dz?fz:1-fz),b=((k+dz)*P.ny+(j+dy))*P.nx+(i+dx);
  sw+=q*P.w[b];sv+=q*P.v[b];
 }
 out[0]=sw/255;out[1]=sv/255;
}
// ── 온도장 (10mm 격자 압축 T) ──
let THERMMAP={};
function parseTherm(buf){
 const {nx,ny,nz,bb}=packedGridHeader(buf,'THM1',1);
 const g={nx,ny,nz,bb,v:finitePacked(new Float32Array(buf.slice(40)),'온도')};
 chkGrid(g,'온도(therm)'); return g;
}
function thermFor(t){
 let best=null,bd=0.6;
 for(const k in THERMMAP){const d=Math.abs(+k-t); if(d<bd){bd=d;best=THERMMAP[k];}}
 return best;
}
// Generic steady/transient scalar results used by storage and future analyses.
let PRESSUREMAP={},TURBMAP={};
function compactSparsePlanes(g,fields,components=1){
 // Legacy 105만-cell silo conversions sampled a 100-layer source mesh onto
 // 139 display layers. The resulting periodic all-zero slabs are a cache
 // defect, not zero-flow physics. Compact only severe interior sparsity so
 // legitimate zero boundaries and zero-valued initial states stay intact.
 const plane=g.nx*g.ny,keep=[];
 for(let k=0;k<g.nz;k++){
  let populated=false;
  for(const name of fields){const a=g[name],begin=k*plane*components,end=begin+plane*components;
   for(let i=begin;i<end;i++)if(Math.abs(a[i])>1e-30){populated=true;break;}
   if(populated)break;
  }
  if(populated)keep.push(k);
 }
 const missing=g.nz-keep.length,hasInterior=keep.some((k,i)=>i&&k>keep[i-1]+1);
 if(keep.length<2||missing<3||missing<g.nz*.05||!hasInterior)return g;
 for(const name of fields){const src=g[name],dst=new src.constructor(keep.length*plane*components);let out=0;
  for(const k of keep){const begin=k*plane*components,end=begin+plane*components;dst.set(src.subarray(begin,end),out);out+=plane*components;}
  g[name]=dst;
 }
 g.nz=keep.length;g._sparsePlanesCompacted=missing;return g;
}
function parseScalarField(buf,magicText,channels){
 const {nx,ny,nz,n,bb}=packedGridHeader(buf,magicText,channels);
 const g={nx,ny,nz,bb,v:finitePacked(new Float32Array(buf.slice(40,40+n*4)),magicText)};
 if(channels>1)g.epsilon=finitePacked(new Float32Array(buf.slice(40+n*4,40+n*8)),magicText);
 compactSparsePlanes(g,channels>1?['v','epsilon']:['v']);
 chkGrid(g,magicText);return g;
}
const parsePressure=b=>{const g=parseScalarField(b,'PRS1',1),density=((VIZCFG||CFG||{}).published||{}).rho_kg_m3;
 const rho=density==null?1:+density;if(!Number.isFinite(rho)||rho<=0)throw Error('압력 변환 밀도 오류');
 for(let i=0;i<g.v.length;i++)g.v[i]*=rho;finitePacked(g.v,'압력');return g;};
const parseTurbulence=b=>parseScalarField(b,'TRB1',2);
function scalarFor(map,t){let best=null,bd=Infinity;for(const k in map){const d=Math.abs(+k-t);if(d<bd){bd=d;best=map[k];}}return best;}
function sampleU(F,x,y,z,out){ // m 단위 좌표 → 삼선형 보간
 const [x0,y0,z0,x1,y1,z1]=F.bb;
 let gx=(x-x0)/(x1-x0)*F.nx-0.5, gy=(y-y0)/(y1-y0)*F.ny-0.5, gz=(z-z0)/(z1-z0)*F.nz-0.5;
 gx=Math.max(0,Math.min(F.nx-1.001,gx)); gy=Math.max(0,Math.min(F.ny-1.001,gy)); gz=Math.max(0,Math.min(F.nz-1.001,gz));
 const i=gx|0,j=gy|0,k=gz|0,fx=gx-i,fy=gy-j,fz=gz-k;
 out[0]=out[1]=out[2]=0;
 for(let dz=0;dz<2;dz++)for(let dy=0;dy<2;dy++)for(let dx=0;dx<2;dx++){
  const w=(dx?fx:1-fx)*(dy?fy:1-fy)*(dz?fz:1-fz);
  const b=(((k+dz)*F.ny+(j+dy))*F.nx+(i+dx))*3;
  out[0]+=w*F.u[b]; out[1]+=w*F.u[b+1]; out[2]+=w*F.u[b+2];
 }
}

function parseBub(buf){
 if(Object.prototype.toString.call(buf)!=='[object ArrayBuffer]'||buf.byteLength<12)throw Error('bub 헤더 길이 불일치');
 const dv=new DataView(buf);
 if(dv.getUint32(0,false)!==0x42554231) throw "bub 형식 아님";   // 'BUB1'
 const n=dv.getUint32(4,true), total=dv.getUint32(8,true);
 if(!total||n>total||buf.byteLength!==12+n*8)throw Error('bub 데이터 길이 불일치');
 const idx=new Uint32Array(n), al=new Float32Array(n);
 for(let i=0;i<n;i++){idx[i]=dv.getUint32(12+8*i,true);al[i]=dv.getFloat32(16+8*i,true);
  if(idx[i]>=total||!Number.isFinite(al[i]))throw Error('bub 필드값 오류');}
 return {idx,al,total};
}
function pushFrame(f){
 FRAMES.push(f);
}
function makeFrameSparse(t,b){
 if(Cxyz&&b.total&&b.total*3!==Cxyz.length){
  showErr('기포 프레임(t='+t+') 격자 '+b.total.toLocaleString()+'셀 ≠ 셀 좌표 C '+(Cxyz.length/3).toLocaleString()+'셀',
   '셀 좌표 C와 bub 파일의 격자가 다릅니다. 해당 Project 폴더의 파일이 같은 해석인지 확인하세요.');
  return null;}
 const n=b.idx.length, pos=new Float32Array(n*3), al=new Float32Array(n); let sum=0;
 for(let i=0;i<n;i++){const ci=b.idx[i]*3;
  pos[i*3]=Cxyz[ci]*1000;pos[i*3+1]=Cxyz[ci+1]*1000;pos[i*3+2]=Cxyz[ci+2]*1000;
  al[i]=Math.min(b.al[i]/0.35,1);sum+=b.al[i];}
 return {t,pos,al,n,v:(CFG&&Cxyz)?sum*fluidCellVol()*1e6:0,statsReady:true};
}
function addFrameSparse(t,b){
 const f=makeFrameSparse(t,b);if(f)pushFrame(f);
}

// ══════════════ 프레임 ══════════════
let SRV={bub:0,flow:0,therm:0,phase:0,pressure:0,turbulence:0,hasC:false,hasConfig:false,configName:'',tb:0,tf:0,tt:0,tp:0,tpr:0,ttr:0}, SRVDIRTY=false;
const CENTRE_REPAIR=new Set(); // 프로젝트별 C 복구 요청 중복 방지
let BUBLOADED=0;   // 유동·온도 전용 타임라인 프레임과 실제 기포 프레임을 구분
let VLOADGEN=0;    // 프로젝트를 빠르게 바꿀 때 이전 비동기 로딩을 무효화
let PROJGEN=0;     // 사용자의 CFD 프로젝트 선택을 늦게 끝난 서버 응답이 덮지 못하게 함
let PROJ='', CURC='', LASTST=null, HASPEND=false, LAUNCHT=0, PTIMER=0;
let VPROJ=null, VHIST=[], VHISTV=[], VHISTC=[],LOADED_RID=''; // 뷰어 전용 프로젝트 이력
function vzrid(){return VPROJ==null?PROJ:VPROJ;}        // 뷰어가 실제로 보는 프로젝트('' = 현재)                  // PROJ: 선택 프로젝트(''=현재) · CURC: 현재 실행 rid
function srvFromInfo(i){
 const bubs=i.bubs||[], raws=(i.frames||[]).filter(f=>!bubs.some(x=>x.slice(4,-4)===f.split('_')[1]));
 const nums=(a,cut0,cut1,split)=>a.map(f=>+(split?f.split('_')[1]:f.slice(cut0,cut1))).filter(Number.isFinite);
 const bt=nums(bubs,4,-4,false).concat(nums(raws,0,0,true)), ft=nums(i.flows||[],5,-4,false), tt=nums(i.therms||[],6,-4,false),pt=nums(i.phases||[],6,-4,false),
  prt=nums(i.pressures||[],9,-4,false),trt=nums(i.turbulences||[],11,-4,false);
 SRV={bub:bubs.length+raws.length, flow:(i.flows||[]).length, therm:(i.therms||[]).length,phase:(i.phases||[]).length, hasC:!!i.hasC,
  pressure:(i.pressures||[]).length,turbulence:(i.turbulences||[]).length,concentration:(i.tracer_frames||[]).length,
  hasConfig:!!i.project_config_available,configName:i.project_config_name||'',
  tb:bt.length?Math.max(...bt):0,tf:ft.length?Math.max(...ft):0,tt:tt.length?Math.max(...tt):0,tp:pt.length?Math.max(...pt):0,
  tpr:prt.length?Math.max(...prt):0,ttr:trt.length?Math.max(...trt):0};
}
async function refreshSrvInfo(){
 const gen=PROJGEN, requested=PROJ;
 try{const i=await (await fetch('/api/info'+(requested?('?rid='+encodeURIComponent(requested)):''))).json();
  if(gen!==PROJGEN)return;
  renderProjects(i); if(!NEWMODE)PROJ=i.rid||requested||'';
  const rp=LASTPROJS.find(p=>p.rid===(PROJ||i.rid||i.cur));
  if(rp&&rp.reset_ready&&!projectHasProgress(rp)){RESETREADY=true;NEWMODE=true;}
  if(MODE!=="viz"||vzrid()===requested){srvFromInfo(i);updateSlots();}}catch(_){}
}
let LASTPROJS=[];
function renderProjects(info){
 CURC=info.cur||'';
 LASTPROJS=info.projects||[];
 HASPEND=LASTPROJS.some(p=>p.pending);
 const el=document.getElementById('projList'); if(!el)return;
 const ps=(info.projects||[]).slice()
  .sort((a,b)=>(b.pending?2:(b.rid===CURC?1:0))-(a.pending?2:(a.rid===CURC?1:0))||b.mtime-a.mtime);   // 새 프로젝트 → 현재 → 최근순
 const mkRow=(p,vz)=>{                                    // vz=true → Viewer 리스트(독립 선택·실행 중에도 열람)
  const d=new Date(p.mtime*1000);
  const lb=p.name||((d.getMonth()+1)+'/'+d.getDate()+' '+String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0'));
  const liveT=(p.rid===CURC&&LASTST&&LASTST.time!=null)?+LASTST.time:null;
  const shownT=liveT!=null?Math.max(+p.tmax||0,liveT):(+p.tmax||0);
  const endv=+p.end||((p.rid===CURC&&LASTST)?+LASTST.endTime:0); // 현재만 실시간, 보관본은 프로젝트 고유값
 const pct=(!p.external&&endv)?(p.completed?'100.00':Math.min(100,100*shownT/endv).toFixed(2)):null;
 const dd=p.data||{}, dataN=[dd.config,dd.C,dd.bubble>0,dd.phase>0,dd.flow>0,dd.therm>0,dd.pressure>0,dd.turbulence>0].filter(Boolean).length;
 const ex=p.extract||{};
  let sel;
  if(vz){const va=(VPROJ==null)?(PROJ||CURC):(VPROJ||CURC); sel=!p.pending&&p.rid===va;}
  else{const activeRid=(NEWMODE&&HASPEND)?'__pending__':(PROJ||CURC);
   sel=p.pending?(activeRid==='__pending__'):(p.rid===activeRid);}
 const ridq=encodeURIComponent(p.rid||'').replace(/'/g,'%27');
  const nmq=encodeURIComponent(lb).replace(/'/g,'%27');
  const ridArg="decodeURIComponent('"+ridq+"')", nmArg="decodeURIComponent('"+nmq+"')";
  const click=p.pending?'newProj()':(vz?('selVz('+ridArg+')'):('selectProj('+ridArg+')'));
  const steady=p.analysis==='grain_silo'&&p.solver==='simpleFoam';
  const done=p.completed?(p.completion_reason==='converged'?' · 수렴 완료':p.completion_reason==='limit'?' · 수렴 미도달':' · 계산 완료'):'';
  const production=steady?('재생 '+fmtPlaybackSeconds(playbackDuration(null,p))+'초 ('+(shownT||0).toFixed(0)+'회)'+done)
   :((shownT||0).toFixed(2)+' 시뮬레이션 초'+done);
  return '<div class="prow'+(sel?' on':'')+(p.pending?' pend':'')+'" data-rid="'+ridq
   +'" onclick="'+click+'" title="'+(vz?'클릭하면 이 프로젝트를 재생합니다 (실행 중에도 가능)':'클릭하면 이 프로젝트로 전환합니다')+'">'
  +'<div style="display:flex;align-items:center;gap:6px;min-width:0">'
  +'<b style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:126px" title="더블클릭: 이름 바꾸기" '
  +'ondblclick="event.stopPropagation();renameProj('+ridArg+','+nmArg+')">'+esc(lb)+'</b>'
  +'<button class="mini" style="padding:1px 6px;flex:none" title="프로젝트를 Trash로 이동" onclick="event.stopPropagation();delProj('+ridArg+','+nmArg+')">🗑</button></div>'
  +'<div style="text-align:right;flex:none;line-height:1.35">'
  +(p.external?('<b style="font-size:12.5px" title="확인된 데이터 종류">'+(p.analysis==='gas_transport'?([dd.concentration>0,dd.sorbed>0].filter(Boolean).length+'/2'):(dataN+'/6'))+'</b>'):(pct!=null?('<b class="projPct" style="font-size:12.5px">'+pct+'%</b>'):''))
  +'<div class="sst projTime">'+(ex.busy?('변환 '+(+(ex.processed??ex.done)||0)+'/'+(+ex.total||0)):production)+'</div></div>'
  +'</div>';
 };
 const emptyHtml='<div class="sst" style="padding:14px 6px;text-align:center">아직 없음 — [＋ 새 프로젝트]로 시작하세요</div>';
 el.innerHTML=!ps.length?emptyHtml:ps.map(p=>mkRow(p,false)).join('');
 const el2=document.getElementById('projList2');
 if(el2)el2.innerHTML=!ps.length?emptyHtml:ps.map(p=>mkRow(p,true)).join('');
 renderSettings();
}
function updateLiveProjectProgress(s){
 if(!s||s.time==null||!CURC)return;
 const p=LASTPROJS.find(x=>x.rid===CURC); if(!p||p.external)return;
 const t=Math.max(+p.tmax||0,+s.time||0), end=+p.end||+s.endTime||0;
 const pct=s.completed?'100.00%':(end?Math.min(100,100*t/end).toFixed(2)+'%':'—');
 const key=encodeURIComponent(CURC);
 for(const rootId of ['projList','projList2']){
  const root=document.getElementById(rootId); if(!root)continue;
  for(const row of root.querySelectorAll('.prow[data-rid]'))if(row.dataset.rid===key){
   const pe=row.querySelector('.projPct'),te=row.querySelector('.projTime');
   if(pe)pe.textContent=pct;
   if(te){const ex=p.extract||{},axis=runAxis(RUNCFG||CFG,p),done=s.completed?(s.completion_reason==='converged'?' · 수렴 완료':s.completion_reason==='limit'?' · 수렴 미도달':''):'';
    const label=axis.steady?('재생 '+fmtPlaybackSeconds(playbackDuration(RUNCFG||CFG,p))+'초 ('+t.toFixed(0)+'회)'+done):(t.toFixed(axis.digits)+' 시뮬레이션 초'+done);
    te.textContent=ex.busy?('변환 '+(+(ex.processed??ex.done)||0)+'/'+(+ex.total||0)):label;}
  }
 }
}
async function refreshProjectList(){
 const gen=PROJGEN;
 try{
  const r=await (await fetch('/api/projects')).json();
  renderProjects(r);
  const ids=new Set((r.projects||[]).filter(p=>!p.pending).map(p=>p.rid));
  if(VPROJ&& !ids.has(VPROJ)){VPROJ=null;FRAMES=[];Cxyz=null;FLOWMAP={};THERMMAP={};PHASEMAP={};PRESSUREMAP={};TURBMAP={};BUBLOADED=0;}
  if(gen===PROJGEN&&PROJ&&PROJ!==r.cur&&!ids.has(PROJ))PROJ='';
 }catch(_){}
}
async function delProj(rid,nm){
 const lb=nm||'';
 if(!rid){                                                 // 대기(새 프로젝트) 카드 = 취소
  confirmBox('새 프로젝트 카드를 삭제할까요?','아직 실행 전이라 저장된 데이터는 없습니다.','삭제',async()=>{
   await fetch('/api/proj-new',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cancel:true})});
   if(NEWMODE){NEWMODE=false;PROJ='';}
   await refreshSrvInfo(); if(LASTST)setStatus(LASTST); toast('삭제됨');});return;}
 if(rid===CURC && LASTST&&LASTST.running){toast('현재 실행 중인 프로젝트는 삭제할 수 없습니다 — [중단] 후 진행하세요',true);return;}
  const p=LASTPROJS.find(x=>x.rid===rid);
  confirmBox('프로젝트를 Trash로 이동','"'+lb+'" 프로젝트 폴더 전체를 Trash로 옮깁니다. 30일 동안 복구할 수 있으며 이후 자동 삭제됩니다.','Trash로 이동',async()=>{
   const r=await (await fetch('/api/proj-del',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rid})})).json();
   if(!r.ok){toast(r.msg||'삭제 실패',true);return;}
   if(Array.isArray(r.projects)){
    LASTPROJS=r.projects;
    renderProjects({cur:r.rid||CURC,projects:LASTPROJS});
   }
   if(PROJ===rid)PROJ='';
   if(VPROJ===rid){VPROJ=null;}
  FRAMES=[];PHASEMAP={};PRESSUREMAP={};TURBMAP={};await refreshSrvInfo(); if(LASTST)setStatus(LASTST);
 toast('프로젝트 "'+lb+'" Trash 이동됨 · '+(r.retention_days||30)+'일 후 자동 삭제');});}
let NMFN=null;
function nameBox(title,def,fn){NMFN=fn;
 document.getElementById('nmTitle').textContent=title;
 const i=document.getElementById('nmInput'); i.value=def||'';
 document.getElementById('nmBg').style.display='flex';
 setTimeout(()=>{i.focus();i.select();},60);}
function nmClose(){document.getElementById('nmBg').style.display='none';NMFN=null;}
function nmOk(){const v=document.getElementById('nmInput').value.trim();const f=NMFN;nmClose();if(f&&v)f(v);}
function renameProj(rid,curEnc){
 nameBox('프로젝트 이름', curEnc, async name=>{
  const r=await (await fetch('/api/proj-name',{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({rid,name})})).json();
  if(!r.ok){toast(r.msg||'이름 변경 실패',true);return;}
  await refreshProjectList();toast('프로젝트 이름·폴더 변경됨');});}
async function selVz(rid){                                // 뷰어 전용 선택 — 실행 중에도 자유롭게 열람
 const p=LASTPROJS.find(x=>x.rid===rid);
 if(p&&p.pending){toast('실행 전 프로젝트 — 아직 볼 데이터가 없습니다',true);return;}
 VPROJ=(rid===CURC)?'':rid;
 VHIST=[];VHISTV=[];VHISTC=[];
 if(LOADED_RID!==rid){document.getElementById('tlab').textContent='불러오는 중';document.getElementById('hFrTit').textContent='재생 프레임 · 불러오는 중';document.getElementById('tbar').value=0;document.getElementById('tbar').max=0;FRAMES=[];BUBLOADED=0;Cxyz=null;FLOWMAP={};THERMMAP={};PHASEMAP={};PRESSUREMAP={};TURBMAP={};}
 SRVDIRTY=true;
 renderProjects({cur:CURC,projects:LASTPROJS});
 // 이력은 loadFrames에서 프레임과 병렬로 읽는다. 마지막 화면 복원·직접 열기도 동일 경로를 탄다.
 await loadFrames();}
function openProj(rid){
 PROJ=rid;SRVDIRTY=true;
 if(LOADED_RID!==rid){FRAMES=[];BUBLOADED=0;Cxyz=null;FLOWMAP={};THERMMAP={};PHASEMAP={};PRESSUREMAP={};TURBMAP={};}
 setMode('viz'); loadFrames();
}
const uiTick=()=>new Promise(r=>setTimeout(r,0));            // 로딩 중에도 화면이 멈추지 않게 양보
function loadMsg(t){document.getElementById('frSt').textContent=t;
 const e=document.getElementById('emptyReadyTxt'); if(e)e.textContent=t;}
let VFRAMEGEN=0,VFILEURL=null,VSTREAMERR=new Set(),VPREFETCHEND=-1,VPREFETCHBUSY=false,VPREFETCHTOKEN=0;
const vkey=t=>(+t).toFixed(9);
function nearestFile(src,t){
 if(!src||!src.length)return null;
 let lo=0,hi=src.length-1;
 while(lo<hi){const m=(lo+hi)>>1;if(src[m].t<t)lo=m+1;else hi=m;}
 const a=src[lo],b=lo?src[lo-1]:null,best=(!b||Math.abs(a.t-t)<=Math.abs(b.t-t))?a:b;
 return Math.abs(best.t-t)<=0.6000001?best:null;
}
function trimFieldCache(map,t,keep){
 const ks=Object.keys(map);if(ks.length<=keep)return;
 ks.sort((a,b)=>Math.abs(+a-t)-Math.abs(+b-t));
 for(const k of ks.slice(keep))delete map[k];
}
function trimVizCache(center){
 // 최대 6초 앞의 표본 프레임을 메모리에 유지해 재생 중 디스크 버퍼링을 줄인다.
 const radius=Math.max(120,Math.ceil(Math.max(.1,+document.getElementById('speed').value||1)*6/Math.max(FDT,.001)));
 for(let i=0;i<FRAMES.length;i++)if(Math.abs(i-center)>radius&&FRAMES[i].pos){
  FRAMES[i].pos=null;FRAMES[i].al=null;FRAMES[i].ready=false;FRAMES[i].loading=null;
 }
 const t=FRAMES[center]?FRAMES[center].t:0;
 trimFieldCache(FLOWMAP,t,128);trimFieldCache(THERMMAP,t,128);trimFieldCache(PHASEMAP,t,128);trimFieldCache(PRESSUREMAP,t,128);trimFieldCache(TURBMAP,t,128);
 PHASETIMES=[];PHASECACHE.clear();
}
async function fetchVizField(meta,parser,map,gen){
 if(!meta)return null;
 if(map[meta.t]!=null)return map[meta.t];
 const b=await fetchVizBuffer(VFILEURL(meta.f));
 if(gen!==VFRAMEGEN)throw new Error('취소된 로딩');
 const v=parser(b);map[meta.t]=v;return v;
}
async function fetchVizBuffer(url){
 let last=null;
 for(let attempt=0;attempt<3;attempt++){
  try{
   const r=await fetch(url,{cache:'no-store'});
   if(!r.ok)throw new Error('HTTP '+r.status);
   return await r.arrayBuffer();
  }catch(e){
   last=e;
   if(attempt<2)await new Promise(resolve=>setTimeout(resolve,150*(attempt+1)));
  }
 }
 throw last||new Error('파일 읽기 실패');
}
function vizFrameReady(i,withFields=true){
 if(typeof warehouseActive==='function'&&warehouseActive()){return warehouseFrameReady(i);}
 if(isTracerConfig(VIZCFG||CFG))return tracerFrameReady(i);
 const f=FRAMES[i];if(!f)return false;
 // 꺼 레이어의 파일은 재생 준비 판정에서 제외한다. 표시하지 않는 4 GB 기포
 // 파일 때문에 상분율 화면까지 멈추던 상호 의존을 없앤다.
 if(LY('lyBub')&&f.bub&&!f.pos)return false;
 if(!withFields)return true;
 return (!LY('lySlice')||!f.flow||FLOWMAP[f.flow.t]!=null)
  &&(!LY('lyTvol')||!f.therm||THERMMAP[f.therm.t]!=null)
  &&(!LY('lyPhase')||!f.phase||PHASEMAP[f.phase.t]!=null)
  &&(!LY('lyBub')||!f.pressure||PRESSUREMAP[f.pressure.t]!=null)
  &&(!LY('lyPhase')||!f.turbulence||TURBMAP[f.turbulence.t]!=null);
}
async function ensureVizFrame(i,withFields=true){
 if(typeof warehouseActive==='function'&&warehouseActive()){return ensureWarehouseFrame(i);}
 if(isTracerConfig(VIZCFG||CFG))return ensureTracerFrame(i);
 const f=FRAMES[i],gen=VFRAMEGEN;if(!f)return false;
 if(vizFrameReady(i,withFields))return true;if(f.loading)return f.loading;
 f.loading=(async()=>{
  try{
   const jobs=[];
   jobs.push(LY('lyBub')&&f.bub&&Cxyz&&!f.pos?(async()=>{
    const b=await fetchVizBuffer(VFILEURL(f.bub.f));
    if(gen!==VFRAMEGEN)throw new Error('취소된 로딩');
    let made;
    if(f.bub.sp)made=makeFrameSparse(f.t,parseBub(b));
    else{const before=FRAMES.length;addFrame(f.t,parseFoam(b,1).data);made=FRAMES.length>before?FRAMES.pop():null;}
    if(!made)throw new Error('t='+f.t+' 기포 격자 불일치');
    f.pos=made.pos;f.al=made.al;f.n=made.n;f.v=made.v;f.statsReady=true;
   })():Promise.resolve());
   if(withFields){
    if(LY('lySlice'))jobs.push(fetchVizField(f.flow,parseFlow,FLOWMAP,gen));
    if(LY('lyTvol'))jobs.push(fetchVizField(f.therm,parseTherm,THERMMAP,gen));
    if(LY('lyPhase'))jobs.push(fetchVizField(f.phase,parsePhase,PHASEMAP,gen));
    if(LY('lyBub'))jobs.push(fetchVizField(f.pressure,parsePressure,PRESSUREMAP,gen));
    if(LY('lyPhase'))jobs.push(fetchVizField(f.turbulence,parseTurbulence,TURBMAP,gen));
   }
   await Promise.all(jobs);
   if(gen!==VFRAMEGEN)return false;
   f.ready=true;
   if(Object.keys(FLOWMAP).length<=2||Object.keys(THERMMAP).length<=2||Object.keys(PHASEMAP).length<=2||Object.keys(PRESSUREMAP).length<=2||Object.keys(TURBMAP).length<=2)setDataAvail();
   if(i===idx)uploadPoints();
   return f.ready;
  }catch(e){
   if(gen!==VFRAMEGEN)return false;
   f.ready=false;
   if(isWatching())SRVDIRTY=true;
   else if(!VSTREAMERR.has('frame-load')){
    VSTREAMERR.add('frame-load');
    toast('일부 시각화 파일을 읽지 못했습니다. 업데이트에서 자동으로 다시 확인합니다',true);
   }
   return false;
  }finally{if(gen===VFRAMEGEN)f.loading=null;}
 })();
 return f.loading;
}
function playbackStride(){
 const spd=Math.max(.1,+document.getElementById('speed').value||1);
 return Math.max(1,Math.ceil((spd/12)/Math.max(FDT,0.001)));
}
function prefetchViz(start,reset=false){
 if(!FRAMES.length||(typeof DataSheetViewer!=='undefined'&&DataSheetViewer.mode==='data'))return;
 // 계산 저장 간격(0.01 s)은 화면 FPS가 아니다. 모든 파일을 1×에서 100개/s로
 // 읽으면 디스크·파싱이 포화된다. 앞 구간은 약 12 fps로 표본 로딩한다.
 const spd=Math.max(.1,+document.getElementById('speed').value||1),stride=playbackStride();
 if(reset){VPREFETCHTOKEN++;VPREFETCHBUSY=false;VPREFETCHEND=-1;}
 VPREFETCHEND=Math.max(VPREFETCHEND,Math.min(FRAMES.length-1,start+Math.ceil(spd*6/Math.max(FDT,0.001))));
 if(VPREFETCHBUSY)return;
 const gen=VFRAMEGEN,token=VPREFETCHTOKEN;VPREFETCHBUSY=true;
 (async()=>{
  try{
   if(isTracerConfig(VIZCFG||CFG))await ensureVizFrame(Math.max(0,Math.min(start,FRAMES.length-1)));
   let p=Math.ceil(Math.max(0,start)/stride)*stride;
   while(gen===VFRAMEGEN&&token===VPREFETCHTOKEN&&p<=VPREFETCHEND){
    const batch=[];for(let n=0;n<4&&p<=VPREFETCHEND;n++,p+=stride)batch.push(ensureVizFrame(p));
    await Promise.all(batch);await uiTick();
   }
  }finally{if(gen===VFRAMEGEN&&token===VPREFETCHTOKEN)VPREFETCHBUSY=false;}
 })();
}
function playbackBufferReady(from,wallSeconds=.4){
 if(!FRAMES.length)return false;
 const stride=playbackStride(),spd=Math.max(.1,+document.getElementById('speed').value||1);
 const end=Math.min(FRAMES.length-1,from+Math.max(stride,Math.ceil(wallSeconds*spd/Math.max(FDT,.001))));
 const first=Math.ceil(Math.max(0,from)/stride)*stride;
 // 마지막 프레임 인덱스가 표본 간격의 배수가 아니어도 끝 구간을 버퍼 부족으로
 // 오판하지 않는다. 준비된 마지막 표본을 보여준 뒤 첫 구간으로 반복한다.
 if(first>end)return isTracerConfig(VIZCFG||CFG)?tracerFrameReady(Math.min(from,FRAMES.length-1)):
  readyFrameAtOrBefore(Math.min(from,FRAMES.length-1))>=0;
 for(let i=first;i<=end;i+=stride)if(!vizFrameReady(i,true))return false;
 return true;
}
async function loadFrames(autoplay){
 const request=vzrid();
 if(loadFrames.busy&&loadFrames.request===request){
  if(autoplay)loadFrames.autoplay=true;
  loadFrames.pending=true;
  return;
 }
 const gen=++VLOADGEN; loadFrames.busy=gen; loadFrames.request=request;
 loadFrames.autoplay=!!autoplay;
 const live=()=>gen===VLOADGEN;
 try{
  const info=await (await fetch('/api/info'+(request?('?rid='+encodeURIComponent(request)):''))).json();
  if(!live())return;
  const target=info.rid||request;
  const incremental=!!target&&LOADED_RID===target;
  const fileUrl=n=>'/files/'+(target?(encodeURIComponent(target)+'/'):'')+encodeURIComponent(n);
  if(VPROJ==null)PROJ=info.rid||''; else VPROJ=info.rid||'';
  renderProjects(info);
  srvFromInfo(info);
  showExtract(info.extract||{},target);
  adoptExtractWatch(target,info.extract||{});
  if(info.config){setConfig(info.config);fillRunInputs(info.config);}
  fillConds(info.conditions||[]);
  if(isTracerConfig(info.config)){await loadTracerFrames(info,fileUrl,target,live);return;}
  // 보관 프로젝트의 열전대 이력을 프레임 로딩과 병렬로 불러온다.
  // 이 경로가 loadFrames 안에 있어야 클릭 뿐 아니라 마지막 화면 복원 시에도 텍스트·그래프가 채워진다.
  const histUrl='/api/history'+((target&&target!==CURC)?('?proj='+encodeURIComponent(target)):'');
  fetch(histUrl).then(r=>r.json()).then(h=>{
   if(!live())return;
   if(VPROJ==null){HIST=h.probes||[];HISTV=h.vapor||[];HISTC=h.coil||[];}
   else{VHIST=h.probes||[];VHISTV=h.vapor||[];VHISTC=h.coil||[];}
   const gc=document.getElementById('gcol');if(gc)gc._keys='';
   renderGCol();
  }).catch(()=>{if(live()&&VPROJ!=null){VHIST=[];VHISTV=[];VHISTC=[];}});
  // 기포: 압축(bub) 우선, 구형 원본(alpha)도 지원
  const bubs=info.bubs||[], raws=(info.frames||[]).filter(f=>!bubs.some(x=>x.slice(4,-4)===f.split('_')[1]));
  const listAll=bubs.map(f=>({f,t:parseFloat(f.slice(4,-4)),sp:1})).concat(raws.map(f=>({f,t:parseFloat(f.split('_')[1]),sp:0})));
  listAll.sort((a,z)=>a.t-z.t);
  const timed=(a,n)=>a.map(f=>({f,t:parseFloat(f.slice(n,-4))})).filter(x=>Number.isFinite(x.t)).sort((a,b)=>a.t-b.t);
  const flows=timed(info.flows||[],5),therms=timed(info.therms||[],6),phases=timed(info.phases||[],6),
   pressures=timed(info.pressures||[],9),turbulences=timed(info.turbulences||[],11);
  // 새 프로젝트는 네 필드가 같은 vizFields 시각을 갖는다. 메모리 상한이 필요할 때도
  // 각 목록에 같은 균등 규칙을 적용해 시간 격자를 어괋나게 만들지 않는다.
  if(!listAll.length&&!flows.length&&!therms.length&&!phases.length&&!pressures.length&&!turbulences.length){toast('이 프로젝트에 시각화할 데이터가 없습니다',true);return;}
  if(!info.project_config_available)toast('프로젝트 config.json 없음 — 현재 기반 설정으로 형상을 표시합니다',true);
  const oldT=FRAMES[idx]?FRAMES[idx].t:0;
  if(!incremental)Cxyz=null;
  FRAMES=[];BUBLOADED=0;FLOWMAP={};THERMMAP={};PHASEMAP={};PRESSUREMAP={};TURBMAP={};PHASETIMES=[];PHASECACHE.clear();
  VFRAMEGEN++;VSTREAMERR.clear();VPREFETCHEND=-1;VPREFETCHBUSY=false;VFILEURL=fileUrl;
  LOADED_RID=target;
  if(listAll.length&&!Cxyz&&info.hasC){
   try{
    const b=await (await fetch(fileUrl('C'))).arrayBuffer();if(!live())return;Cxyz=parseFoam(b,3).data;
   }catch(_){
    // 파일이 교체되는 순간 읽었거나 손상된 C일 수 있다. 아래 복구 경로로 보낸다.
    info.hasC=false; SRV.hasC=false;
   }
  }
  if(listAll.length&&!Cxyz){
   startCentreRepair(target);
  }
  const times=listAll.length?listAll.map(x=>x.t):[...new Set(flows.concat(therms,phases,pressures,turbulences).map(x=>x.t))].sort((a,b)=>a-b);
  const bubMap=new Map(listAll.map(x=>[vkey(x.t),x]));
  const steadyPlayback=runAxis(info.config||VIZCFG||CFG).steady;
  const playbackTotal=playbackDuration(info.config||VIZCFG||CFG);
  FRAMES=times.map((t,i)=>({t,pt:steadyPlayback?(times.length>1?playbackTotal*i/(times.length-1):0):t,bub:bubMap.get(vkey(t))||null,flow:nearestFile(flows,t),therm:nearestFile(therms,t),phase:nearestFile(phases,t),
   pressure:nearestFile(pressures,t),turbulence:nearestFile(turbulences,t),
   pos:null,al:null,n:0,v:0,ready:false,loading:null,statsReady:false}));
  BUBLOADED=listAll.length;
  if(!live())return;
  idx=Math.max(0,frameRawIndexAt(oldT));clock=FRAMES[idx]?framePlayTime(FRAMES[idx]):0;
  setDataAvail();finishFrames(false);
  loadMsg('결과 지점 '+FRAMES.length+'개 확인 · 현재 지점 준비 중…');
  await ensureVizFrame(idx);
  if(!live())return;
  finishFrames(!!loadFrames.autoplay);prefetchViz(idx+1);
  SRVDIRTY=false;
  if(FRAMES.length)toast('반영 완료 — 결과 지점 '+FRAMES.length+'개 · 현재 지점 주변만 로딩');
 }catch(e){ toast('불러오기 실패: '+e, true); }
 finally{if(loadFrames.busy===gen){const again=!!loadFrames.pending;loadFrames.pending=false;
  loadFrames.busy=false;loadFrames.request='';loadFrames.autoplay=false;
  if(again){SRVDIRTY=true;setTimeout(()=>loadFrames(false),0);}}}
}
function updateSlots(){
 if(typeof warehouseActive==='function'&&warehouseActive()){updateWarehouseSlots();return;}
 if(isTracerConfig(VIZCFG||CFG)){updateTracerSlots();return;}
 const set=(id,txt,ok)=>{const el=document.getElementById(id); if(!el)return;
  el.textContent=txt; el.className='sst'+(ok?' ok':'');};
 const want=vizFields();
 set('slCfg',SRV.hasConfig?('✓ '+(SRV.configName||'config.json')):'없음',SRV.hasConfig);
 const state=document.getElementById('slCfgState'), name=document.getElementById('slCfgName'), count=document.getElementById('slCfgCount');
 if(state){state.textContent=CFG?'로딩됨':'파일 필요';state.className='baseState'+(CFG?' ok':'');}
 if(name){const fn=configFileName();name.textContent=fn;name.title=fn;name.style.display=CFG?'':'none';}
 // 냉각 조건은 숫자 입력으로 통합했다. config 안의 구형 conditions 배열은
 // 예전 프로젝트 복원에만 쓰며 현재 설정 카드에는 노출하지 않는다.
 if(count)count.textContent='';
 set('slC',(Cxyz||SRV.hasC)?'✓ 확인됨':'없음',!!(Cxyz||SRV.hasC));
 const cnt=(loaded,srv)=>{const n=Math.max(loaded,srv); return n?('✓ '+n+'개'):'없음';};
 const silo=isSiloConfig(VIZCFG||CFG);
 const rename=(id,label)=>{const e=document.getElementById(id),b=e&&e.parentElement&&e.parentElement.querySelector('b');if(b)b.textContent=label;};
 rename('slBub',silo?'압력장':'기포');rename('slPhase',silo?'난류장':'상분율');
 rename('slFlow','속도장');rename('slTherm','온도장');
 if(silo){
  const npr=Math.max(Object.keys(PRESSUREMAP).length,SRV.pressure),ntr=Math.max(Object.keys(TURBMAP).length,SRV.turbulence),nf=Math.max(Object.keys(FLOWMAP).length,SRV.flow);
  set('slBub',want.pressure?cnt(Object.keys(PRESSUREMAP).length,SRV.pressure):'선택 안 함',npr>0);
  set('slPhase',want.turbulence?cnt(Object.keys(TURBMAP).length,SRV.turbulence):'선택 안 함',ntr>0);
  set('slFlow',want.flow?cnt(Object.keys(FLOWMAP).length,SRV.flow):'선택 안 함',nf>0);
  set('slTherm','해당 없음',false);
  const ready=npr>0||ntr>0||nf>0,cached=hasCachedViz(),action=cached?'업데이트':'생성';
  const bt=document.getElementById('btnRunTxt'),br=document.getElementById('btnRunReadyTxt');if(bt)bt.textContent=document.body.classList.contains('grouped')?'다시 읽기':action;if(br)br.textContent=action;
  const bg=document.getElementById('btnRun');if(bg)bg.disabled=isWatching();
  const pn=document.getElementById('projDataName'),pr=LASTPROJS.find(p=>p.rid===(vzrid()||CURC));if(pn)pn.textContent=pr?(pr.name||pr.rid):'';
  const ei=document.getElementById('emptyIntro'),er=document.getElementById('emptyReady');if(ei&&er){ei.style.display=ready?'none':'';er.style.display=ready?'':'none';}
  return;
 }
 set('slBub',want.alpha?cnt(BUBLOADED,SRV.bub):'선택 안 함',Math.max(BUBLOADED,SRV.bub)>0);
 set('slFlow',want.flow?cnt(Object.keys(FLOWMAP).length,SRV.flow):'선택 안 함',Math.max(Object.keys(FLOWMAP).length,SRV.flow)>0);
 set('slTherm',want.therm?cnt(Object.keys(THERMMAP).length,SRV.therm):'선택 안 함',Math.max(Object.keys(THERMMAP).length,SRV.therm)>0);
 const phaseN=Math.max(Object.keys(PHASEMAP).length,SRV.phase);
 set('slPhase',want.phase?(phaseN?('✓ '+phaseN+'개 · 시간 보간'):'없음'):'선택 안 함',phaseN>0);
 // 상단 버튼은 시각화 생성만 담당한다. 실제 시간 재생은 하단 타임라인 버튼에서만 시작한다.
 const nb=Math.max(BUBLOADED,SRV.bub), nf=Math.max(Object.keys(FLOWMAP).length,SRV.flow), nt=Math.max(Object.keys(THERMMAP).length,SRV.therm), np=Math.max(Object.keys(PHASEMAP).length,SRV.phase);
 const ready=(nb>0&&(Cxyz||SRV.hasC))||nf>0||nt>0||np>0;
 const cached=hasCachedViz();
 // 생성 이력이 있는 프로젝트의 명령은 항상 업데이트다. 저장된 프레임은 프로젝트
 // 선택/Viewer 진입 시 자동 복원되므로 별도 '실행' 명령을 둘 필요가 없다.
 const action=cached?'업데이트':'생성';
 const bt=document.getElementById('btnRunTxt'),br=document.getElementById('btnRunReadyTxt');
 if(bt)bt.textContent=document.body.classList.contains('grouped')?'다시 읽기':action;if(br)br.textContent=action;
 const bg=document.getElementById('btnRun');if(bg)bg.disabled=isWatching();
 const bu=document.getElementById('btnUpdateViz');
 if(bu){bu.style.display='none';bu.disabled=isWatching();}
 const pn=document.getElementById('projDataName'), pr=LASTPROJS.find(p=>p.rid===(vzrid()||CURC));
 if(pn)pn.textContent=pr?(pr.name||pr.rid):'';
  const ei=document.getElementById('emptyIntro'), er=document.getElementById('emptyReady');
  if(ei&&er){ei.style.display=ready?'none':'';er.style.display=ready?'':'none';
  if(ready&&!loadFrames.busy)document.getElementById('emptyReadyTxt').textContent='시각화 데이터 준비 완료';}
}
function configFileName(){
 return CFGFILE||'config.json';
}
function setDataAvail(){
 if(typeof warehouseActive==='function'&&warehouseActive()){updateWarehouseSlots();return;}
 if(isTracerConfig(VIZCFG||CFG)){updateTracerSlots();return;}
 const hb=BUBLOADED>0,hf=Object.keys(FLOWMAP).length>0,ht=Object.keys(THERMMAP).length>0,hp=Object.keys(PHASEMAP).length>0;
 const want=vizFields();
 const en=(lb,cb,loaded,available,what,wanted)=>{
  document.getElementById(lb).classList.toggle('off2',!available);
  document.getElementById(cb).disabled=!available;
  document.getElementById(lb).title=loaded?'':(available?what+' 불러오는 중':(wanted?what+' 데이터 없음':'실행 시 선택하지 않은 출력'));
 };
 if(isSiloConfig(VIZCFG||CFG)){
  const hpr=Object.keys(PRESSUREMAP).length>0,htr=Object.keys(TURBMAP).length>0;
  en('lbBub','lyBub',hpr,hpr||SRV.pressure>0,'압력장',want.pressure);
  en('lbPhase','lyPhase',htr,htr||SRV.turbulence>0,'난류장',want.turbulence);
  en('lbSlice','lySlice',hf,hf||SRV.flow>0,'속도장',want.flow);
  en('lbTvol','lyTvol',false,false,'온도장',false);
  const miss=[];if(want.flow&&!hf&&!SRV.flow)miss.push('속도장');if(want.pressure&&!hpr&&!SRV.pressure)miss.push('압력장');if(want.turbulence&&!htr&&!SRV.turbulence)miss.push('난류장');
  document.getElementById('vizWarn').style.display=(FRAMES.length&&miss.length&&!isWatching())?'flex':'none';
  if(miss.length)document.getElementById('vwTxt').textContent=miss.join('·')+' 데이터가 이 프로젝트에 없습니다';
  updateSlots();return;
 }
 en('lbBub','lyBub',hb,hb||SRV.bub>0,'기포',want.alpha);
  en('lbSlice','lySlice',hf,hf||SRV.flow>0,'유속장',want.flow);
 en('lbTvol','lyTvol',ht,ht||SRV.therm>0,'온도장',want.therm);
 en('lbPhase','lyPhase',hp,hp||SRV.phase>0,'액체 상분율',want.phase);
 // 선행 1프레임만 먼저 그리는 동안에도 폴더 탐지 결과를 사용한다.
 // 그렇지 않으면 실제 파일이 있어도 ‘데이터 없음’ 경고가 잠깐 혹은 계속 표시된다.
 const availF=hf||SRV.flow>0, availT=ht||SRV.therm>0;
 const need=FRAMES.length>0&&((want.flow&&!availF)||(want.therm&&!availT));
 document.getElementById('vizWarn').style.display=(need&&!isWatching())?'flex':'none';
 updateSlots();
 if(need){const miss=[];if(want.flow&&!availF)miss.push('유동');if(want.therm&&!availT)miss.push('온도장');
  document.getElementById('vwTxt').textContent=miss.join('·')+' 데이터가 이 프로젝트에 없습니다';}
}
function addFrame(t,a){
 if(Cxyz&&a.length*3!==Cxyz.length){
  showErr('기포 프레임(t='+t+') 셀 수 '+a.length.toLocaleString()+'개 ≠ 셀 좌표 C '+(Cxyz.length/3).toLocaleString()+'개',
   '셀 좌표 C와 기포 파일의 격자가 다릅니다. 해당 Project 폴더의 파일이 같은 해석인지 확인하세요.');
  return;}
 const TH=0.045,n=a.length; let cnt=0;
 for(let i=0;i<n;i++) if(a[i]>TH) cnt++;
 const pos=new Float32Array(cnt*3), al=new Float32Array(cnt); let k=0,sum=0;
 for(let i=0;i<n;i++){ sum+=a[i]; if(a[i]>TH){ pos[k*3]=Cxyz[i*3]*1000; pos[k*3+1]=Cxyz[i*3+1]*1000; pos[k*3+2]=Cxyz[i*3+2]*1000; al[k]=Math.min(a[i]/0.35,1); k++; } }
 pushFrame({t,pos,al,n:cnt,v:(CFG&&Cxyz)? sum*fluidCellVol()*1e6 : 0});
}
function fluidCellVol(){
 const c=CFG,W=c.tank.width_mm/1e3,D=c.tank.depth_mm/1e3,H=c.tank.liquid_height_mm/1e3;
 const vol=b=>((b.x1-b.x0)*(b.y1-b.y0)*(b.z1-b.z0))/1e9;
 return (W*D*H - vol(c.board) - vol(c.coil))/(Cxyz.length/3);
}
function finishFrames(autoplay){
 if(FRAMES.length>1) FRAMES.sort((x,y)=>x.t-y.t);
 document.getElementById('frSt').textContent='프레임 '+FRAMES.length+'개';
 document.getElementById('tbar').max=Math.max(0,FRAMES.length-1);
 if(FRAMES.length>1){
  const gaps=[];for(let i=1;i<FRAMES.length;i++){const d=framePlayTime(FRAMES[i])-framePlayTime(FRAMES[i-1]);if(d>1e-9)gaps.push(d);}
  if(gaps.length){gaps.sort((a,b)=>a-b);FDT=Math.max(0.001,gaps[Math.floor(gaps.length/2)]);}
 }
 if(FRAMES.length){
  const t0=framePlayTime(FRAMES[0]),t1=framePlayTime(FRAMES[FRAMES.length-1]);
  if(!Number.isFinite(clock)||clock<t0||clock>t1+FDT)clock=t0;
  idx=frameIndexAt(Math.min(clock,t1));
  PLAYENDED=false;
  setPlay(false,true);
  if(autoplay)setTimeout(()=>startBufferedPlayback(false),0);
  document.getElementById('empty').style.display='none';
  const ax=runAxis(VIZCFG||CFG);document.getElementById('hFrTit').textContent=ax.steady?
   ('재생 프레임 · '+FRAMES.length+'개 (총 '+fmtPlaybackSeconds(t1-t0)+'초 · '+FRAMES[0].t.toFixed(0)+'~'+FRAMES[FRAMES.length-1].t.toFixed(0)+'회)'):
   ('재생 프레임 · '+FRAMES.length+'개 (t '+FRAMES[0].t+'~'+FRAMES[FRAMES.length-1].t+' s)'); }
 uploadPoints();
 updateSlots();
}

// ══════════════ 결과 가져오기 = 프로젝트별 추출 + 자동 로딩 ══════════════
const VIZWATCH=new Map();let EXBUSY=false;
const OUTIDS={bubble:'outBub',phase:'outPhase',flow:'outFlow',therm:'outTherm',pressure:'outBub',turbulence:'outPhase',concentration:'outBub',sorbed:'outPhase'};
const OUTPUT_LAYOUTS={
 gas_transport:[['outOptBub','outBub','concentration','농도장','C/C_ref'],['outOptPhase','outPhase','sorbed','흡착량','Q/C_ref · 벌크 체적 기준']],
 immersion:[['outOptBub','outBub','bubble','기포','증기 형상·부피'],['outOptPhase','outPhase','phase','상분율','액체 분포'],['outOptFlow','outFlow','flow','속도장','유속·방향'],['outOptTherm','outTherm','therm','온도장','온도 분포']],
 grain_silo:[['outOptBub','outBub','pressure','압력장','압력 분포'],['outOptPhase','outPhase','turbulence','난류장','k · epsilon'],['outOptFlow','outFlow','flow','속도장','유속·방향']]
};
function refreshViewerFields(){
 if(!FRAMES.length)return;
 const at=Math.max(0,Math.min(idx,FRAMES.length-1));
 ensureVizFrame(at,true).then(ok=>{if(ok&&at===idx){uploadPoints();prefetchViz(at);}});
}
const VIEWLAYERSTATE={};
function configureViewerFields(c){
 if(c?._해석유형==='warehouse'){configureWarehouseUI();return;}
 if(isTracerConfig(c)){configureTracerFields(c);return;}
 document.body.classList.remove('tracerView');
 const tracerStats=document.getElementById('tracerStats');if(tracerStats)tracerStats.style.display='none';
 const scalarGrad=document.querySelector('#tcbar .grad');if(scalarGrad)scalarGrad.style.background='';
 for(const id of ['lyGeo','lyCoil','lyTank','lyBound'])document.getElementById(id).closest('label').style.display='';
 for(const id of ['lbBub','lbPhase','lbSlice','lbTvol'])document.getElementById(id).style.display='';
 const silo=isSiloConfig(c),mode=silo?'grain_silo':'immersion',layerIds=['lyBub','lyPhase','lySlice','lyTvol','lyGeo','lyCoil','lyTank','lyBound'];
 const prior=configureViewerFields.mode;
 if(prior&&prior!==mode)VIEWLAYERSTATE[prior]=Object.fromEntries(layerIds.map(id=>[id,!!document.getElementById(id)?.checked]));
 if(prior!==mode){const saved=VIEWLAYERSTATE[mode];
  if(saved)for(const id of layerIds)if(document.getElementById(id)&&saved[id]!=null)document.getElementById(id).checked=saved[id];
  else if(silo){document.getElementById('lyBub').checked=true;document.getElementById('lyPhase').checked=false;document.getElementById('lySlice').checked=true;
   for(const id of ['lyGeo','lyCoil','lyTank','lyBound'])document.getElementById(id).checked=true;}
 }
 configureViewerFields.mode=mode;
 const set=(id,text,title,show=true)=>{const el=document.getElementById(id);if(!el)return;el.style.display=show?'':'none';el.title=title||'';const sw=el.querySelector('.sw');while(sw&&sw.nextSibling)sw.nextSibling.remove();el.appendChild(document.createTextNode(text));};
 set('lbBub',silo?'압력장':'TMC-49 증기 기포',silo?'정압 출구를 기준으로 한 압력 분포':'액체에서 발생한 증기 분포');
 set('lbPhase',silo?'난류장 (k)':'액체 상분율',silo?'난류 운동에너지 k 분포':'액체 상분율 분포');
 set('lbSlice',silo?'속도장 · 흐름 마커':'속도장',silo?'공기 속도 U 기반 화살표와 이동 마커':'유체 속도 U의 방향과 크기');
 set('lbTvol','온도장','온도 분포',!silo);
 const design=[
  ['lyGeo',silo?'다공성 저장 영역':'보드 · CPU',silo?'다공성 매질로 계산된 저장 영역':'발열체와 보드 형상'],
  ['lyCoil',silo?'중앙 유입 덕트':'코일',silo?'유체가 유입되는 덕트':'냉각 코일 형상'],
  ['lyTank',silo?'저장고 외곽':'수조 · 공기층',silo?'계산 영역의 외곽 형상':'수조와 상부 공간 형상'],
  ['lyBound',silo?'저장 영역 상단':'초기 계면 기준선',silo?'다공성 저장 영역의 상단 경계':'계산 시작 시 액체 계면 기준선']
 ];
 for(const [id,label,title] of design){const input=document.getElementById(id),row=input&&input.closest('label'),sw=row&&row.querySelector('.sw');if(!row||!sw)continue;row.title=title;while(sw.nextSibling)sw.nextSibling.remove();row.appendChild(document.createTextNode(label));}
 const hud=document.querySelector('#hud .hrow');if(hud)hud.style.display=silo?'none':'';
 const tlab=document.getElementById('tlab');if(tlab&&!FRAMES.length)tlab.textContent='—s (0프레임)';
 for(const id of ['lyProbe','lyInfo','gcT','gcV','gcB','gcL']){const e=document.getElementById(id),row=e&&e.closest('label');if(row)row.style.display=silo?'none':'';if(silo&&e)e.checked=false;}
 const graphTitle=[...document.querySelectorAll('#vlegend .ltit')].find(e=>e.textContent.trim()==='그래프');if(graphTitle)graphTitle.style.display=silo?'none':'';
 if(silo){const gc=document.getElementById('gcol');if(gc)gc.innerHTML='';}
 // 저장고 스칼라장은 서로 덮어쓰면 색을 해석할 수 없다. 한 번에 하나만 표시한다.
 if(silo){
  const p=document.getElementById('lyBub'),k=document.getElementById('lyPhase');
  if(p&&k&&!p.dataset.scalarBound){
   p.addEventListener('change',()=>{if(p.checked)k.checked=false;refreshViewerFields();});
   k.addEventListener('change',()=>{if(k.checked)p.checked=false;refreshViewerFields();});
   p.dataset.scalarBound=k.dataset.scalarBound='1';
  }
  if(p&&k&&p.checked&&k.checked)k.checked=false;
 }
}
function configureOutputFields(c,selected){
 const type=isTracerConfig(c)?'gas_transport':isSiloConfig(c)?'grain_silo':'immersion',defs=OUTPUT_LAYOUTS[type],active=new Set(selected||((c&&c.run&&c.run.output_fields)||defs.map(x=>x[2])));
 for(const id of ['outOptBub','outOptPhase','outOptFlow','outOptTherm']){const row=document.getElementById(id);if(row)row.style.display='none';}
 for(const [rowId,inputId,key,title,sub] of defs){const row=document.getElementById(rowId),input=document.getElementById(inputId);if(!row||!input)continue;
  row.style.display='';input.dataset.output=key;input.checked=active.has(key);row.querySelector('b').textContent=title;row.querySelector('small').textContent=sub;}
}
function outputFlags(raw){
 const all={alpha:true,phase:true,flow:true,therm:true,pressure:true,turbulence:true};
 if(!Array.isArray(raw))return all;                         // v75 이전 프로젝트 호환
 return {alpha:raw.includes('bubble'),phase:raw.includes('phase'),
  flow:raw.includes('flow'),therm:raw.includes('therm'),pressure:raw.includes('pressure'),
  turbulence:raw.includes('turbulence')};
}
function selectedOutputList(){
 return [...document.querySelectorAll('#outGrid input[data-output]')].filter(el=>el.closest('.outOpt').style.display!=='none'&&el.checked).map(el=>el.dataset.output);
}
function configOutputFlags(c){return outputFlags(c&&c.run&&c.run.output_fields);}
function vizFields(){
 const target=vzrid()||CURC, p=LASTPROJS.find(x=>x.rid===target);
 if(p&&p.settings&&Array.isArray(p.settings.output_fields))return outputFlags(p.settings.output_fields);
 return configOutputFlags((MODE==='viz'?(VIZCFG||CFG):(RUNCFG||CFG)));
}
function extractTarget(){return vzrid()||CURC||'';}
function isWatching(rid){return VIZWATCH.has(rid==null?extractTarget():rid);}
function showExtract(ex,target){
 if(target&&target!==extractTarget())return;
 document.getElementById('exSt').textContent=ex.busy?ex.msg:(ex.msg||'');
 document.getElementById('exBar').style.width=(ex.total? (100*(+(ex.processed??ex.done)||0)/ex.total):0)+'%';
}
function showProjectExtract(rid,ex){
 const key=encodeURIComponent(rid||'');
 for(const rootId of ['projList','projList2']){const root=document.getElementById(rootId);if(!root)continue;
  for(const row of root.querySelectorAll('.prow[data-rid]'))if(row.dataset.rid===key){const e=row.querySelector('.projTime');
   if(e)e.textContent=ex.busy?('변환 '+(+(ex.processed??ex.done)||0)+'/'+(+ex.total||0)):(e.dataset.time||e.textContent);}}
}
function runExtractWatch(target,lastLoaded){
 const btn=document.getElementById('btnRun');
 const timer=setInterval(async()=>{
  try{
   const ex=await (await fetch('/api/extract-state?rid='+encodeURIComponent(target))).json();
   showExtract(ex,target);showProjectExtract(target,ex);
   // A restarted/new browser adopts the backend job and displays each completed frame.
   if(ex.busy&&target===extractTarget()&&(+ex.done||0)>lastLoaded&&!loadFrames.busy){
    lastLoaded=+ex.done||0;SRVDIRTY=true;loadFrames(false);
   }
   if(!ex.busy){clearInterval(timer);VIZWATCH.delete(target);
    if((+ex.failed||0)>0)toast('일부 변환 실패 '+ex.failed+'개 — 업데이트를 다시 누르면 실패 구간을 재시도합니다',true);
    if(target===extractTarget()){if(btn)btn.disabled=false;SRVDIRTY=true;if((+ex.failed||0)===0&&ex.msg)toast(ex.msg);loadFrames(false);}
    else{refreshProjectList();const p=LASTPROJS.find(x=>x.rid===target);toast((p?(p.name||p.rid):target)+' 시각화 업데이트 완료');}}
  }catch(_){clearInterval(timer);VIZWATCH.delete(target);if(btn&&target===extractTarget())btn.disabled=false;}
 },1500);
}
function adoptExtractWatch(target,ex){
 if(!target||!ex.busy||isWatching(target))return;
 VIZWATCH.set(target,true);
 const btn=document.getElementById('btnRun');if(btn&&target===extractTarget())btn.disabled=true;
 runExtractWatch(target,+ex.done||0);
}
async function startCentreRepair(target){
 if(!target||CENTRE_REPAIR.has(target)||isWatching(target))return;
 CENTRE_REPAIR.add(target);
 try{
  const fields=vizFields();
  const r=await (await fetch('/api/extract',{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({fields,rid:target})})).json();
  if(!r.ok){toast(r.msg||'셀 좌표 C를 복구할 원본 CFD 데이터를 찾을 수 없습니다',true);return;}
  toast(r.started?'셀 좌표(C) 복구 중입니다 · 완료되면 기포를 자동으로 표시합니다':'셀 좌표(C) 복구 작업을 확인 중입니다');
  if(r.started){VIZWATCH.set(target,true);runExtractWatch(target,0);}
  else if(r.state&&r.state.busy)adoptExtractWatch(target,r.state);
 }catch(_){toast('셀 좌표(C) 복구 요청에 실패했습니다',true);}
 finally{CENTRE_REPAIR.delete(target);}
}
async function fetchResults(){
 const fields=vizFields();
 const target=extractTarget();
 if(!target){toast('프로젝트를 선택해 주세요',true);return;}
 if(isWatching(target)){toast('이 프로젝트는 이미 변환 중입니다');return;}
 VIZWATCH.set(target,true);document.getElementById('vizWarn').style.display='none';
 const btn=document.getElementById('btnRun'); if(btn)btn.disabled=true;
 let er;
 try{er=await (await fetch('/api/extract',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fields,rid:target})})).json();}
 catch(_){VIZWATCH.delete(target);if(btn&&target===extractTarget())btn.disabled=false;toast('변환 요청 중 서버 응답이 끊겼습니다',true);return;}
 if(!er.ok){VIZWATCH.delete(target);if(btn&&target===extractTarget())btn.disabled=false;toast(er.msg||'원본 CFD 데이터를 찾을 수 없습니다',true);return;}
 toast(er.started?'시각화 데이터 상태를 확인합니다':'이 프로젝트는 이미 변환 중입니다');
 runExtractWatch(target,0);
}
function hasCachedViz(){return SRV.concentration>0||(SRV.bub>0&&SRV.hasC)||SRV.flow>0||SRV.therm>0||SRV.phase>0||SRV.pressure>0||SRV.turbulence>0;}
function cacheNeedsUpdate(){
 const vz=vzrid();if(vz&&vz!==CURC)return false;
 const newest=+(LASTST&&LASTST.snap_max||0);
 if(!(newest>0)||!hasCachedViz())return false;
 const ends=[],want=vizFields(),silo=isSiloConfig(VIZCFG||CFG);
 if(!silo&&want.alpha)ends.push(SRV.bub>0&&SRV.hasC?SRV.tb:-1);
 if(want.flow)ends.push(SRV.flow>0?SRV.tf:-1);
 if(silo&&want.pressure)ends.push(SRV.pressure>0?SRV.tpr:-1);
 if(silo&&want.turbulence)ends.push(SRV.turbulence>0?SRV.ttr:-1);
 if(!silo&&want.therm)ends.push(SRV.therm>0?SRV.tt:-1);
 if(!silo&&want.phase)ends.push(SRV.phase>0?SRV.tp:-1);
 return ends.length>0&&Math.min(...ends)+1e-7<newest;
}
function vizRun(){ // 시각화 준비만 담당 — 시간 재생은 하단 재생 버튼에서 시작
 if(typeof warehouseActive==='function'&&warehouseActive()){loadWarehouseResult(WH.id,WH.name);return;}
 if(isTracerConfig(VIZCFG||CFG)){loadFrames(false);return;}
 if(isWatching()){toast('이 프로젝트는 변환 중입니다 — 위 진행바를 확인하세요');return;}
 const vz=vzrid();
 if(hasCachedViz()){
  fetchResults();return;
 }
 if(!vz||vz===CURC){fetchResults();return;}
 toast('이 프로젝트에 생성할 시각화 데이터가 없습니다',true);
}
async function doClear(){const r=await (await fetch('/api/clear-frames',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rid:vzrid()})})).json();
 if(!r.ok){toast(r.msg||'캐시를 비우지 못했습니다',true);return;}FRAMES=[];GPUFRAME=-1;GPUN=0;BUBLOADED=0;Cxyz=null;FLOWMAP={};THERMMAP={};PHASEMAP={};PRESSUREMAP={};TURBMAP={};LOADED_RID='';setDataAvail();
 document.getElementById('frSt').textContent='';document.getElementById('empty').style.display='flex';
 document.getElementById('exBar').style.width='0%';document.getElementById('exSt').textContent='대기';
 toast('캐시를 비웠습니다');}

// ══════════════ 드래그&드롭 (파일·폴더 모두) ══════════════
const drop=document.getElementById('drop');
function inDropZone(e){return !!(e.target&&e.target.closest&&e.target.closest('.baseSlot'));}
addEventListener('dragover',e=>{e.preventDefault();          // 기본 동작(파일 열기) 차단은 전역, 표시는 영역 안에서만
 drop.style.display=inDropZone(e)?'flex':'none';});
addEventListener('dragleave',e=>{if(!e.relatedTarget)drop.style.display='none';});
function walkEntry(entry){ // 폴더 드롭 → 내부 파일 전부 수집
 return new Promise(res=>{
  if(entry.isFile) entry.file(f=>res([f]),()=>res([]));
  else if(entry.isDirectory){
   const r=entry.createReader(), all=[];
   const read=()=>r.readEntries(async es=>{
    if(!es.length) return res((await Promise.all(all)).flat());
    for(const en of es) all.push(walkEntry(en));
    read();
   },()=>res([]));
   read();
  } else res([]);
 });
}
addEventListener('drop',async e=>{
 e.preventDefault(); drop.style.display='none';
 if(!inDropZone(e))return;                                    // 3D 공간 등 영역 밖 드롭은 무시
 let files=[];
 if(e.dataTransfer.items&&[...e.dataTransfer.items].some(i=>i.webkitGetAsEntry&&i.webkitGetAsEntry()&&i.webkitGetAsEntry().isDirectory)){
  for(const it of [...e.dataTransfer.items]){const en=it.webkitGetAsEntry&&it.webkitGetAsEntry(); if(en) files.push(...await walkEntry(en));}
 } else files=[...e.dataTransfer.files];
 const cfgs=files.filter(f=>f.name.endsWith('.json')||f.name.endsWith('.csv'));
 if(cfgs.length)processFiles(cfgs);else toast('외부 CFD 데이터는 Project 폴더에 넣으면 자동 인식됩니다',true);
});
function pickBase(kind){
 if(runBusyNow()){toast('실행 중에는 설정을 할 수 없습니다',true);return;}
 if(document.getElementById('cfgPick').disabled){toast('잠금 상태 — 설정을 바꾸려면 [새 프로젝트]를 누르세요',true);return;}
 document.getElementById('fBaseJson').click();}
function baseFile(inp){
 if(inp.files&&inp.files.length){ACTIVE_CONFIG_FILE=inp.files[0];CFGREF='inline';CFGFILE=ACTIVE_CONFIG_FILE.name;processFiles([...inp.files]);}
}
async function settingChanged(){
 const sl=document.getElementById('cfgPick'),v=sl?sl.value:'';
 updateConfigDeleteButton();
 const seq=++CFGLOADSEQ;
 const load=(async()=>{
  try{
   let url='/api/config',label='기본 설정';
   if(v.startsWith('cfg:')){url+='?name='+encodeURIComponent(v.slice(4));label=v.slice(4);}
   const r=await (await fetch(url)).json();
   if(seq!==CFGLOADSEQ)return false;                         // 더 최근에 고른 설정이 우선
   if(!r.ok||!r.config)throw new Error(r.msg||'설정 없음');
   CFGREF=v;CFGFILE=r.name||label+'.json';ACTIVE_CONFIG_FILE=null;
   setConfig(r.config);fillRunInputs(r.config,true);fillConds(r.conditions||[]);
   CFGSRC=v?('저장된 설정 / '+CFGFILE):'기본 config.json';
   updateSlots();toast(label+' 설정을 불러왔습니다');return true;
  }catch(e){
   if(seq===CFGLOADSEQ){toast('설정을 불러올 수 없습니다: '+e.message,true);renderSettings(CFGREF);}
   return false;
  }
 })();
 CFGLOAD=load;
 try{return await load;}finally{if(CFGLOAD===load)CFGLOAD=null;}
}
async function processFiles(files){
 const got={cfg:0,csv:0,C:0,fr:0,fl:0,th:0,ph:0,pr:0,tr:0,skip:0}, bad=[];
 for(const f of files){
  if(f.name==='config.json'||(f.name.endsWith('.json')&&files.length<4)){
   try{ const cj=JSON.parse(await f.text()); setConfig(cj); fillRunInputs(cj,true); ACTIVE_CONFIG_FILE=f;CFGREF='inline';CFGFILE=f.name;CFGSRC='선택한 '+f.name; got.cfg++;
    if(Array.isArray(cj.conditions))fillConds(cj.conditions.map(r=>({name:''+r.name,Ta_C:''+(r.Ta_C??''),flow_LPM:''+(r.flow_LPM??''),h:''+(r.h_model_W_m2K??r.h??'')}))); }
   catch(_){toast(f.name+' 파싱 실패',true);} }
  else if(f.name==='conditions.csv'||f.name.endsWith('.csv')){   // 구버전 조건표 — 읽어서 통합 표시
   const t=await f.text();
   fillConds(t.split(/\r?\n/).slice(1).filter(l=>l.includes(',')).map(l=>{const v=l.split(',');
    return {name:v[0],Ta_C:v[3]||'',flow_LPM:v[2]||'',h:v[5]||''};})); got.csv++; }
  else if(f.name==='C'){ Cxyz=parseFoam(await f.arrayBuffer(),3).data; got.C++; }
 }
 for(const f of files){
  const m=f.name.match(/^alpha\.vapour_([\d.]+)$/), fm=f.name.match(/^flow_([\d.]+)\.bin$/),
        tm=f.name.match(/^therm_([\d.]+)\.bin$/), pm=f.name.match(/^phase_([\d.]+)\.bin$/), bm=f.name.match(/^bub_([\d.]+)\.bin$/),
        prm=f.name.match(/^pressure_([\d.]+)\.bin$/), trm=f.name.match(/^turbulence_([\d.]+)\.bin$/);
  if(m){ if(!Cxyz){ toast('C 파일을 먼저(또는 같이) 드롭하세요',true); got.skip++; continue; }
   try{ addFrame(parseFloat(m[1]), parseFoam(await f.arrayBuffer(),1).data); got.fr++; }catch(_){got.skip++;bad.push(f.name);} }
  else if(bm){ if(!Cxyz){ toast('C 파일을 먼저(또는 같이) 드롭하세요',true); got.skip++; continue; }
   try{ addFrameSparse(parseFloat(bm[1]), parseBub(await f.arrayBuffer())); got.fr++; }catch(_){got.skip++;bad.push(f.name);} }
  else if(fm){ try{ FLOWMAP[parseFloat(fm[1])]=parseFlow(await f.arrayBuffer()); got.fl++; }catch(_){got.skip++;bad.push(f.name);} }
  else if(tm){ try{ THERMMAP[parseFloat(tm[1])]=parseTherm(await f.arrayBuffer()); got.th++; }catch(_){got.skip++;bad.push(f.name);} }
  else if(pm){ try{ PHASEMAP[parseFloat(pm[1])]=parsePhase(await f.arrayBuffer()); got.ph++; }catch(_){got.skip++;bad.push(f.name);} }
  else if(prm){ try{ PRESSUREMAP[parseFloat(prm[1])]=parsePressure(await f.arrayBuffer()); got.pr++; }catch(_){got.skip++;bad.push(f.name);} }
  else if(trm){ try{ TURBMAP[parseFloat(trm[1])]=parseTurbulence(await f.arrayBuffer()); got.tr++; }catch(_){got.skip++;bad.push(f.name);} }
 }
 if(bad.length)showErr('형식이 맞지 않는 파일 '+bad.length+'개: '+bad.slice(0,4).join(', ')+(bad.length>4?' 외':''),
  '스튜디오가 만든 원본 그대로여야 합니다 (Project 폴더의 *_*.bin·alpha.vapour_*).\n이름을 바꾸거나 내용이 변형된 파일은 읽을 수 없습니다.');
 if(got.fl||got.th||got.ph||got.pr||got.tr) setDataAvail();
 if(got.fr) finishFrames(true);
 updateSlots();
 const parts=[];
 if(got.cfg)parts.push('형상·조건 설정'); if(got.csv)parts.push('조건표(구버전 — config.json에 통합됨)'); if(got.C)parts.push('셀 좌표');
 if(got.fr)parts.push('기포 '+got.fr); if(got.fl)parts.push('흐름 '+got.fl); if(got.th)parts.push('온도 '+got.th); if(got.ph)parts.push('액체 상분율 '+got.ph);
 if(got.pr)parts.push('압력 '+got.pr); if(got.tr)parts.push('난류 '+got.tr);
 toast(parts.length?('적용됨: '+parts.join(' · ')):'인식된 파일이 없습니다 — config.json·C·CFD Studio 변환 파일', !parts.length);
}

// ══════════════ WebGL 엔진 ══════════════
const cv=document.getElementById('gl'); const gl=cv.getContext('webgl',{antialias:true,alpha:false,preserveDrawingBuffer:true,powerPreference:'high-performance'});
function sh(t,s){const o=gl.createShader(t);gl.shaderSource(o,s);gl.compileShader(o);if(!gl.getShaderParameter(o,gl.COMPILE_STATUS))throw gl.getShaderInfoLog(o);return o;}
function prog(v,f){const p=gl.createProgram();gl.attachShader(p,sh(gl.VERTEX_SHADER,v));gl.attachShader(p,sh(gl.FRAGMENT_SHADER,f));gl.linkProgram(p);return p;}
const ptsP=prog(`attribute vec3 aP;attribute float aA;uniform mat4 uM;uniform float uK;varying float vA;
 void main(){gl_Position=uM*vec4(aP,1.);float w=max(gl_Position.w,1.);gl_PointSize=clamp((4.+7.*aA)*uK/w,1.5,42.);vA=aA;}`,
`precision mediump float;varying float vA;void main(){vec2 q=gl_PointCoord*2.-1.;float d=dot(q,q);if(d>1.)discard;
 float f=smoothstep(1.,0.,d);vec3 c=mix(vec3(1.,.66,.12),vec3(1.,1.,.88),vA);gl_FragColor=vec4(c*f*(.35+.65*vA),1.);}`);
const solP=prog(`attribute vec3 aP;uniform mat4 uM;void main(){gl_Position=uM*vec4(aP,1.);}`,
`precision mediump float;uniform vec4 uC;void main(){gl_FragColor=uC;}`);
const phaseP=prog(`attribute vec3 aP;attribute float aK;attribute float aA;uniform mat4 uM;uniform float uK;varying float vK;varying float vA;
 void main(){gl_Position=uM*vec4(aP,1.);float w=max(gl_Position.w,1.);gl_PointSize=clamp(10.*uK/w,1.5,34.);vK=aK;vA=aA;}`,
`precision mediump float;varying float vK;varying float vA;void main(){vec2 q=gl_PointCoord*2.-1.;float d=dot(q,q);if(d>1.)discard;
 float edge=smoothstep(1.,.35,d);vec3 c=mix(vec3(1.,.54,.14),vec3(.20,.55,1.),clamp((vK+1.)*.5,0.,1.));
 gl_FragColor=vec4(c,.08+.64*vA*edge);}`);
const texP=prog(`attribute vec3 aP;attribute vec2 aT;uniform mat4 uM;varying vec2 vT;
 void main(){gl_Position=uM*vec4(aP,1.);vT=aT;}`,
`precision mediump float;varying vec2 vT;uniform sampler2D uS;void main(){vec4 c=texture2D(uS,vT);
 if(c.a<0.02)discard;gl_FragColor=c;}`);
const arrowP=prog(`attribute vec3 aP;attribute float aS;uniform mat4 uM;varying float vS;varying float vY;
 void main(){gl_Position=uM*vec4(aP,1.);vS=aS;vY=aP.y;}`,
`precision mediump float;varying float vS;varying float vY;uniform float uIf;uniform float uSilo;
 void main(){vec3 hue=uSilo>.5?mix(vec3(.10,.70,1.),vec3(1.,.88,.24),vS):(vY<uIf?vec3(1.,.60,.20):vec3(.28,.62,1.));
 gl_FragColor=vec4(hue*(.42+.58*vS),.48+.52*vS);}`);
const flowDotP=prog(`attribute vec3 aP;attribute float aS;uniform mat4 uM;varying float vS;
 void main(){gl_Position=uM*vec4(aP,1.);gl_PointSize=4.5+4.5*aS;vS=aS;}`,
`precision mediump float;varying float vS;void main(){vec2 q=gl_PointCoord*2.-1.;float d=dot(q,q);if(d>1.)discard;
 float edge=smoothstep(1.,.18,d);vec3 c=mix(vec3(.16,.78,1.),vec3(1.,.91,.32),vS);
 gl_FragColor=vec4(c,edge*(.62+.38*vS));}`);
const thermP=prog(`attribute vec3 aP;attribute float aV;uniform mat4 uM;uniform float uK;varying float vV;
 void main(){gl_Position=uM*vec4(aP,1.);float w=max(gl_Position.w,1.);gl_PointSize=clamp(9.5*uK/w,1.,30.);vV=aV;}`,
`precision mediump float;varying float vV;void main(){if(vV<1.)discard;
 vec2 q=gl_PointCoord*2.-1.;float d=dot(q,q);if(d>1.)discard;
 float u=clamp((vV-288.15)/40.,0.,1.);
 vec3 c=u<.5?mix(vec3(.16,.47,.84),vec3(.93,.91,.86),u*2.):mix(vec3(.93,.91,.86),vec3(.89,.27,.27),u*2.-1.);
 gl_FragColor=vec4(c,.14*smoothstep(1.,.2,d));}`);
function persp(fv,a,n,f){const t=1/Math.tan(fv/2);return[t/a,0,0,0,0,t,0,0,0,0,(f+n)/(n-f),-1,0,0,2*f*n/(n-f),0];}
function lookAt(e,c,up){let z=[e[0]-c[0],e[1]-c[1],e[2]-c[2]];let l=Math.hypot(...z);z=z.map(v=>v/l);
 let x=[up[1]*z[2]-up[2]*z[1],up[2]*z[0]-up[0]*z[2],up[0]*z[1]-up[1]*z[0]];l=Math.hypot(...x);x=x.map(v=>v/l);
 const y=[z[1]*x[2]-z[2]*x[1],z[2]*x[0]-z[0]*x[2],z[0]*x[1]-z[1]*x[0]];
 return[x[0],y[0],z[0],0,x[1],y[1],z[1],0,x[2],y[2],z[2],0,
 -(x[0]*e[0]+x[1]*e[1]+x[2]*e[2]),-(y[0]*e[0]+y[1]*e[1]+y[2]*e[2]),-(z[0]*e[0]+z[1]*e[1]+z[2]*e[2]),1];}
function mul(a,b){const o=new Array(16);for(let r=0;r<4;r++)for(let c=0;c<4;c++){let s=0;for(let k=0;k<4;k++)s+=a[k*4+c]*b[r*4+k];o[r*4+c]=s;}return o;}
function boxTris(x0,y0,z0,x1,y1,z1){const v=[[x0,y0,z0],[x1,y0,z0],[x1,y1,z0],[x0,y1,z0],[x0,y0,z1],[x1,y0,z1],[x1,y1,z1],[x0,y1,z1]];
 const F=[[0,1,2,3],[4,5,6,7],[0,1,5,4],[2,3,7,6],[1,2,6,5],[0,3,7,4]];const o=[];for(const q of F){o.push(...v[q[0]],...v[q[1]],...v[q[2]],...v[q[0]],...v[q[2]],...v[q[3]]);}return o;}
function boxEdges(x0,y0,z0,x1,y1,z1){const v=[[x0,y0,z0],[x1,y0,z0],[x1,y1,z0],[x0,y1,z0],[x0,y0,z1],[x1,y0,z1],[x1,y1,z1],[x0,y1,z1]];
 const E=[[0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],[0,4],[1,5],[2,6],[3,7]];const o=[];for(const q of E){o.push(...v[q[0]],...v[q[1]]);}return o;}
function cylinderEdges(r,z0,z1,n=48){const o=[];for(let i=0;i<n;i++){const a=2*Math.PI*i/n,b=2*Math.PI*(i+1)/n,x=r*Math.cos(a),y=r*Math.sin(a),xb=r*Math.cos(b),yb=r*Math.sin(b);o.push(x,y,z0,xb,yb,z0,x,y,z1,xb,yb,z1);if(i%6===0)o.push(x,y,z0,x,y,z1);}return o;}
function cylinderTris(r,z0,z1,n=48){const o=[];for(let i=0;i<n;i++){const a=2*Math.PI*i/n,b=2*Math.PI*(i+1)/n,x=r*Math.cos(a),y=r*Math.sin(a),xb=r*Math.cos(b),yb=r*Math.sin(b);o.push(x,y,z0,xb,yb,z0,xb,yb,z1,x,y,z0,xb,yb,z1,x,y,z1);}return o;}
function mesh(a){const b=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,b);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(a),gl.STATIC_DRAW);return{b,n:a.length/3};}
// 우클릭 팬 이동은 사용하지 않는다. 좌클릭은 수조 중심(tgt) 기준의 기본 궤도 회전이다.
let G={}, tgt=[228,380,35], th=0, ph=0, rad=1650;
let PROBEPTS=[];
const PCOL=[[.22,.53,.9,.95],[.85,.35,.15,.95],[.1,.62,.44,.95],[.79,.52,0,.95],
            [.84,.32,.5,.95],[0,.52,0,.95]];   // T1~T4 + T5·T6(냉각회로)
const PNAMES=['T1 CPU','T2 계면↓','T3 계면↑','T4 코일↑','T5 입구','T6 출구'];
let LIVET5=null,LIVET6=null,HISTC=[];   // HISTC: [t, 코일 T(°C)] 이력 — 재생 시점 T6 계산용

let DERIVED=false, DERIVEDNOTE='';
// 복원 이력 배너 — derived 플래그가 파일에는 있었지만 화면에 표시되지 않아
// 근사 복원값이 계측값과 똑같이 보이던 문제(2026-08-15 감사) 수정
function renderDerived(){
 let el=document.getElementById('drvBanner');
 if(!el){
  const host=document.getElementById('dash'); if(!host)return;
  el=document.createElement('div'); el.id='drvBanner';
  el.style.cssText='display:none;margin:0 0 10px;padding:8px 12px;border-radius:8px;'+
   'background:#3a2a12;border:1px solid #7a5a20;color:#f0c060;font-size:11.5px;line-height:1.6';
  host.insertBefore(el, host.firstChild);
 }
 if(DERIVED){ el.style.display='';
  el.innerHTML='<b>복원된 근사 이력</b> — '+(DERIVEDNOTE||'보관 프레임에서 되짚은 값입니다.')+
               ' 계측값으로 인용하지 마세요.';
 } else el.style.display='none';
}

// 에너지 수지 — 발열 입력 대비 코일 배출. 2026-08-15 추가.
// 이 한 줄이 없어서 "입력 265 W / 배출 57 W"라는 4배 불일치를 오래 못 봤다.
// 검토 스킬(cfd-thermal-multiphase-review) E항이 매 실행 감사하라고 지정한 항목.
function renderEnergy(){
 const row=document.getElementById('engRow'), card=document.getElementById('engCard');
 if(!row||!card)return;
 // CFD 대시보드 카드이므로 Viewer가 별도 프로젝트를 보고 있어도
 // 실행 프로젝트의 설정·코일 이력만 사용한다. 실행 중 새 계산의 현재 시각보다
 // 뒤에 있는 과거 행도 제외해 재시작 직후 이전 프로젝트 값이 잠깐 보이지 않게 한다.
 const ecfg=RUNCFG||CFG;
 let hc=HISTC;
 if(LASTST&&LASTST.running&&LASTST.time!=null)
  hc=hc.filter(x=>+x[0]<=+LASTST.time+1e-6);
 if(!ecfg||!ecfg.coil||!ecfg.heater||!hc.length||DERIVED){card.style.display='none';return;}
 const k=ecfg.coil, Qin=+ecfg.heater.total_W||0, Ta=+k.Ta_C;
 const A=2*((k.x1-k.x0)*(k.y1-k.y0)+(k.x1-k.x0)*(k.z1-k.z0)+(k.y1-k.y0)*(k.z1-k.z0))*1e-6;
 const hA=(+k.h_W_m2K||0)*A;
 const last=hc[hc.length-1], Qout=coilPowerW(last[1],ecfg);
 const r=Qin>0?Qout/Qin:0;
 // 추세: 최근 30% 구간이 그 앞 구간보다 배출이 늘고 있는가
 let trend='';
 if(hc.length>=8){
  const n=hc.length, a=hc.slice(0,Math.floor(n*0.5)), b=hc.slice(Math.floor(n*0.5));
  const av=a.reduce((s,x)=>s+x[1],0)/a.length, bv=b.reduce((s,x)=>s+x[1],0)/b.length;
  trend = bv>av+0.02 ? '<span style="color:var(--ok)">↑ 증가</span>'
        : bv<av-0.02 ? '<span style="color:var(--bad)">↓ 감소</span>' : '→ 유지';
 }
 const col = r<0.3?'var(--bad)' : r<0.7?'var(--warn)' : 'var(--ok)';
 const note = r<0.3 ? '열이 갇혀 있음 — 계면·상단 액체 순환을 확인하세요'
            : r<0.7 ? '축열 구간 (정상상태로 갈수록 100%에 접근)' : '수지 근접';
 row.innerHTML =
  '<span>발열 입력 <b>'+Qin.toFixed(0)+'</b> W</span>'+
  '<span>코일 배출 <b style="color:'+col+'">'+Qout.toFixed(1)+'</b> W'+(trend?' '+trend:'')+'</span>'+
  '<span>폐합률 <b style="color:'+col+'">'+(r*100).toFixed(0)+'</b>%</span>'+
  '<span style="color:var(--muted)">코일면 '+last[1].toFixed(2)+' °C · 냉각수 '+Ta.toFixed(0)+' °C · hA '+hA.toFixed(2)+' W/K</span>'+
  '<span style="color:var(--muted)">'+note+'</span>';
 document.getElementById('engT').textContent='t = '+last[0].toFixed(2)+' s';
 card.style.display='';
}
function coilPowerW(coilC,cfg){
 cfg=cfg||RUNCFG||CFG;
 if(coilC==null||!cfg||!cfg.coil)return null;
 const k=cfg.coil,A=2*((k.x1-k.x0)*(k.y1-k.y0)+(k.x1-k.x0)*(k.z1-k.z0)+(k.y1-k.y0)*(k.z1-k.z0))*1e-6;
 const q=(+k.h_W_m2K||0)*A*(+coilC-(+k.Ta_C));
 return isFinite(q)?q:null;
}
function histAt(arr,t){ // 시각 t에 가장 가까운 이력 행 (이분 탐색)
 if(!arr.length)return null;
 let lo=0,hi=arr.length-1;
 while(lo<hi){const m=(lo+hi)>>1; if(arr[m][0]<t)lo=m+1; else hi=m;}
 const a=arr[Math.max(0,lo-1)],b=arr[lo];
 return (Math.abs(a[0]-t)<=Math.abs(b[0]-t))?a:b;
}
function coilPars(){ // 냉각회로 파라미터 (T5 입구, hA, ṁcp)
 if(!CFG)return null;
 const k=CFG.coil||{},tf=document.getElementById('ovTa'),ff=document.getElementById('ovFlow');
 let t5=tf&&tf.value!==''?parseFloat(tf.value):parseFloat(k.Ta_C),flow=ff&&ff.value!==''?parseFloat(ff.value):parseFloat(k.flow_LPM);
 if(!isFinite(flow)){const rid=vzrid()||CURC,p=LASTPROJS.find(x=>x.rid===rid),legacy=CONDROWS.find(r=>r.name===String((p&&p.settings||{}).condition||''));
  if(legacy){flow=parseFloat(legacy.flow_LPM);if(!isFinite(t5))t5=parseFloat(legacy.Ta_C);}}
 let hA=null,mcp=null;
 if(isFinite(flow)&&flow>0){
  const A=2*((k.x1-k.x0)*(k.y1-k.y0)+(k.y1-k.y0)*(k.z1-k.z0)+(k.z1-k.z0)*(k.x1-k.x0))/1e6;
  const mdot=flow/60;hA=k.h_W_m2K*A;mcp=mdot*4178;
 }
 return {t5,hA,mcp};
}
function calcT6(coilC){const p=coilPars();
 return (p&&coilC!=null&&p.hA!=null)?p.t5+p.hA*(coilC-p.t5)/p.mcp:null;}
let LBREC=[];   // 영상 녹화 오버레이용 — 라벨 화면좌표·텍스트 (updateProbeLabels가 매 프레임 갱신)
function updateProbeLabels(M){
 const box=document.getElementById('plabels');
 if(!LY('lyProbe')||!PROBEPTS.length){box.innerHTML='';LBREC=[];return;}
 const info=LY('lyInfo')&&(HASRUN||FRAMES.length>0);      // 진행/재생 데이터가 있을 때만 값 표시
 const F=FRAMES.length?FRAMES[idx]:null, ft=F?F.t:null;   // 재생 중인 프레임의 물리 시각
 const LHP=(VPROJ==null)?HIST:VHIST, LHC=(VPROJ==null)?HISTC:VHISTC;
 const rowH=(ft!=null&&LHP.length)?histAt(LHP,ft):(LHP.length?LHP[LHP.length-1]:null);
 const coilRow=(ft!=null&&LHC.length)?histAt(LHC,ft):null;
 const cpv=(VPROJ!=null)?coilPars():null;
 const t5p=(cpv&&isFinite(cpv.t5))?cpv.t5:LIVET5;
 const t6p=coilRow?calcT6(coilRow[1]):LIVET6;
 let h=''; LBREC=[];
 for(let i=0;i<PROBEPTS.length;i++){
  const [x,y,z]=PROBEPTS[i];
  const cx=M[0]*x+M[4]*y+M[8]*z+M[12], cy=M[1]*x+M[5]*y+M[9]*z+M[13],
        cw=M[3]*x+M[7]*y+M[11]*z+M[15];
  if(cw<1)continue;
  const px=(cx/cw*0.5+0.5)*VW, py=(1-(cy/cw*0.5+0.5))*VH;
  if(px<-40||px>VW+40||py<0||py>VH)continue;
  let vs='';
  if(info){
   if(i<4&&rowH)vs=rowH[i+1].toFixed(1)+'°';
   else if(i===4&&t5p!=null)vs=t5p.toFixed(1)+'°';
   else if(i===5&&t6p!=null)vs='≈'+t6p.toFixed(2)+'°';
   else if(i===5&&VPROJ!=null)vs='—';
  }
  const val=vs?' <b>'+vs+'</b>':'';
  const col='rgb('+(PCOL[i][0]*255|0)+','+(PCOL[i][1]*255|0)+','+(PCOL[i][2]*255|0)+')';
  h+='<span style="left:'+px.toFixed(0)+'px;top:'+py.toFixed(0)+'px;border-left:2px solid '+col+'">'
    +PNAMES[i]+val+'</span>';
  LBREC.push({x:px,y:py,text:PNAMES[i]+(vs?' '+vs:''),col});
 }
 box.innerHTML=h;
}
function setConfig(c){
 CFG=c;
 if(c?._해석유형==='warehouse'){VIZCFG=c;configureWarehouseUI();return;}
 if(isTracerConfig(c)){setTracerConfig(c);return;}
 if(isSiloConfig(c)){
  VIZCFG=c;
  if(MODE==='cfd')RUNCFG=c;
  const p=c.published||{},r=(+p.storage_diameter_m||.8)*500,H=(+p.total_height_m||1.4)*1000,Hg=(+p.grain_height_m||1)*1000,rd=(+p.bottom_central_duct_diameter_m||.3)*500;
  G.silo=mesh(cylinderTris(r,0,H));G.siloE=mesh(cylinderEdges(r,0,H));
  G.grain=mesh(cylinderTris(r,0,Hg));G.grainE=mesh(cylinderEdges(r,0,Hg));
  G.duct=mesh(cylinderTris(rd,0,Math.min(Hg,180)));G.ductE=mesh(cylinderEdges(rd,0,Math.min(Hg,180)));
  PROBEPTS=[];G.probes=[];tgt=[0,0,H*.48];rad=Math.max(r*2,H)*2.15;th=0;ph=.12;
  document.getElementById('hGeo').textContent='저장고 Ø'+(r*2).toFixed(0)+' × '+H.toFixed(0)+' mm · 다공성 영역 '+Hg.toFixed(0)+' mm · 입구 Ø'+(rd*2).toFixed(0)+' mm';
  applyAnalysisTypeUI();
  return;
 }
 IMMERSIONCFG=c;
 if(MODE==='viz')VIZCFG=c; else RUNCFG=c;                  // CFD 실행 설정과 Viewer 형상 설정을 분리
 lastPhaseP=null;                                          // 계면 높이가 바뀌면 침투 강조를 다시 계산
 const W=c.tank.width_mm,D=c.tank.depth_mm,H=c.tank.liquid_height_mm,Hd=c.layers.dielectric_mm,b=c.board,k=c.coil;
 const AIR=(c.layers.air_mm!=null)?c.layers.air_mm:200;   // 실측 상단 공기층 (표시 전용 — CFD는 액체만 해석)
 G.tank=mesh(boxEdges(0,0,0,W,H+AIR,D));                  // 수조 외곽 = 실물 전체 높이
 G.glass=mesh(boxTris(0,0,0,W,H+AIR,D));                  // 내부 유리감 — 층 구분 색 없음(경계는 선으로)
 G.liqTop=mesh([0,H,0,W,H,0, W,H,0,W,H,D, W,H,D,0,H,D, 0,H,D,0,H,0]); // 계산영역 상단
 const irect=[0,Hd,0,W,Hd,0, W,Hd,0,W,Hd,D, W,Hd,D,0,Hd,D, 0,Hd,D,0,Hd,0];
 G.ifaceE=mesh(irect.concat([0,Hd,D/2,W,Hd,D/2, W/2,Hd,0,W/2,Hd,D]));  // 계면 테두리+십자
 G.board=mesh(boxTris(b.x0,b.y0,b.z0,b.x1,b.y1,b.z1)); G.boardE=mesh(boxEdges(b.x0,b.y0,b.z0,b.x1,b.y1,b.z1));
 let cpuT=[]; for(const u of c.heater.cpus){cpuT.push(...boxTris(u.x0,u.y0,b.z1,u.x1,u.y1,b.z1+0.3));} G.cpu=mesh(cpuT);
 G.coil=mesh(boxTris(k.x0,k.y0,k.z0,k.x1,k.y1,k.z1)); G.coilE=mesh(boxEdges(k.x0,k.y0,k.z0,k.x1,k.y1,k.z1));
 // 열전대 마커(십자) + 라벨 좌표
 PROBEPTS=(c.probes_mm&&c.probes_mm.points)?c.probes_mm.points.slice(0,4):[];
 // T5 입구(좌)·T6 출구(우) — 발표본 21쪽 사진: 수조 상단 뚜껑 배관부 좌/우
 PROBEPTS=PROBEPTS.concat([[W*0.175,H+AIR*0.7,D/2],[W*0.825,H+AIR*0.7,D/2]]);
 G.probes=PROBEPTS.map(p=>{const r=9,[x,y,z]=p;
  return mesh([x-r,y,z,x+r,y,z, x,y-r,z,x,y+r,z, x,y,z-r,x,y,z+r]);});
 tgt=[W/2,(H+AIR)*0.45,D/2]; rad=Math.max(W,H+AIR)*2.25;
 document.getElementById('hGeo').textContent='수조 '+W+'×'+D+'×'+(H+AIR)+' mm · 유전체 '+Hd+'/물 '+(H-Hd)+'/공기 '+AIR+'(표시) · CPU '+c.heater.total_W+' W';
 applyAnalysisTypeUI();
}
function frameVapourML(F){
 const vh=VPROJ==null?HISTV:VHISTV;
 // 이력이 늦게 시작하는 기존 프로젝트에서 첫 이력값을 0초 값으로 오인하지 않는다.
 const vr=F&&vh.length&&F.t>=vh[0][0]-1e-9?histAt(vh,F.t):null;
 return Math.max(0,+(vr?vr[1]:((F&&F.v)||0)));
}
let pBuf=gl.createBuffer(),aBuf=gl.createBuffer(),GPUFRAME=-1,GPUN=0;
function inSolid(x,y,z){
 if(!CFG)return false;const b=CFG.board,k=CFG.coil;
 return (x>b.x0&&x<b.x1&&y>b.y0&&y<b.y1&&z>b.z0&&z<b.z1)
     || (x>k.x0&&x<k.x1&&y>k.y0&&y<k.y1&&z>k.z0&&z<k.z1);
}

// ── 실제 액체 상분율 점군: 순수 영역은 옅게, 혼합·초기 계면 침투는 진하게 ──
let phaseBuf=gl.createBuffer(),phaseN=0,lastPhaseP=null;
function buildPhasePoints(P){
 if(P===lastPhaseP)return;lastPhaseP=P;
 const [x0,y0,z0,x1,y1,z1]=P.bb,Hd=((CFG&&CFG.layers)?CFG.layers.dielectric_mm:400)/1000;
 const a=[];
 for(let k=0;k<P.nz;k++)for(let j=0;j<P.ny;j++)for(let i=0;i<P.nx;i++){
  // PHS2 occupancy=0은 고체·미점유 bin. PHS1도 기하 고체는 최소한 제거한다.
  const b=(k*P.ny+j)*P.nx+i,w=P.w[b]/255,v=P.v[b]/255,l=Math.max(0,1-w-v);
  if(P.m&&!P.m[b])continue;
  if(v>.985||w+l<.02)continue;
  const x=(x0+(i+.5)*(x1-x0)/P.nx)*1000,y=y0+(j+.5)*(y1-y0)/P.ny,z=(z0+(k+.5)*(z1-z0)/P.nz)*1000;
  if(inSolid(x,y*1000,z))continue;
  const mix=2*Math.min(w,l),dx=((b*17)%7-3)*.42,dz=((b*29)%7-3)*.42;
  // 우세한 상 하나로 섞어 그리면 물 안의 소량 TMC 액적이 파랑에 가려진다.
  // 따라서 각 액상을 독립 점으로 그리고, 소량 상도 자신의 색으로 보이게 한다.
  if(l>.015){const e=Math.min(1,Math.max(mix,y>Hd?l:0,l<.985?l*.6:0));a.push(x-dx,y*1000,z-dz,-1,e);}
  if(w>.015){const e=Math.min(1,Math.max(mix,y<Hd?w:0,w<.985?w*.6:0));a.push(x+dx,y*1000,z+dz, 1,e);}
 }
 phaseN=a.length/5;gl.bindBuffer(gl.ARRAY_BUFFER,phaseBuf);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(a),gl.STATIC_DRAW);
}
function drawPhase(P,M,uK){
 buildPhasePoints(P);if(!phaseN)return;
 gl.useProgram(phaseP);gl.uniformMatrix4fv(gl.getUniformLocation(phaseP,'uM'),false,new Float32Array(M));
 gl.uniform1f(gl.getUniformLocation(phaseP,'uK'),uK);gl.bindBuffer(gl.ARRAY_BUFFER,phaseBuf);
 const lp=gl.getAttribLocation(phaseP,'aP'),lk=gl.getAttribLocation(phaseP,'aK'),la=gl.getAttribLocation(phaseP,'aA');
 gl.enableVertexAttribArray(lp);gl.vertexAttribPointer(lp,3,gl.FLOAT,false,20,0);
 gl.enableVertexAttribArray(lk);gl.vertexAttribPointer(lk,1,gl.FLOAT,false,20,12);
 gl.enableVertexAttribArray(la);gl.vertexAttribPointer(la,1,gl.FLOAT,false,20,16);
 gl.drawArrays(gl.POINTS,0,phaseN);
}

// ── 유속 단면 (|U| 히트맵, 깊이 중앙) ──
let sliceTex=gl.createTexture(),sliceCv=document.createElement('canvas'),lastSliceF=null;
function updateSlice(F){
 if(F===lastSliceF)return; lastSliceF=F;
 const nx=F.nx,ny=F.ny,k=F.nz>>1; sliceCv.width=nx;sliceCv.height=ny;
 const ctx=sliceCv.getContext('2d'),img=ctx.createImageData(nx,ny);
 for(let j=0;j<ny;j++)for(let i=0;i<nx;i++){
  const b=((k*ny+j)*nx+i)*3, s=Math.min(Math.hypot(F.u[b],F.u[b+1],F.u[b+2])/0.15,1);
  const p=(j*nx+i)*4;   // 반전 없음 — 쿼드 UV(v=0=아래)와 texImage2D 행 순서가 그대로 일치
  img.data[p]=13+s*180; img.data[p+1]=40+s*140; img.data[p+2]=90+s*165; img.data[p+3]=s>0.015?70+s*160:0;
 }
 ctx.putImageData(img,0,0);
 gl.bindTexture(gl.TEXTURE_2D,sliceTex);
 gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,sliceCv);
 gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);
 gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
 gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);
 gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
}
// ── 온도장 볼륨(격자점 구름) + 온도 단면 ──
let thPosBuf=gl.createBuffer(),thValBuf=gl.createBuffer(),thPosKey='',thN=0,lastThV=null;
function thermUpload(T){
 const key=T.nx+'x'+T.ny+'x'+T.nz;
 if(thPosKey!==key){                                   // 격자 중심 좌표는 프레임 간 공유
  const [x0,y0,z0,x1,y1,z1]=T.bb; thN=T.nx*T.ny*T.nz;
  const P=new Float32Array(thN*3); let o=0;
  for(let k=0;k<T.nz;k++)for(let j=0;j<T.ny;j++)for(let i=0;i<T.nx;i++){
   P[o++]=(x0+(i+.5)*(x1-x0)/T.nx)*1000; P[o++]=(y0+(j+.5)*(y1-y0)/T.ny)*1000; P[o++]=(z0+(k+.5)*(z1-z0)/T.nz)*1000;
  }
  gl.bindBuffer(gl.ARRAY_BUFFER,thPosBuf);gl.bufferData(gl.ARRAY_BUFFER,P,gl.STATIC_DRAW);
  thPosKey=key;
 }
 if(lastThV!==T.v){gl.bindBuffer(gl.ARRAY_BUFFER,thValBuf);gl.bufferData(gl.ARRAY_BUFFER,T.v,gl.STATIC_DRAW);lastThV=T.v;}
}
function drawTherm(T,M,uK){
 thermUpload(T);
 gl.useProgram(thermP);
 gl.uniformMatrix4fv(gl.getUniformLocation(thermP,'uM'),false,new Float32Array(M));
 gl.uniform1f(gl.getUniformLocation(thermP,'uK'),uK);
 gl.bindBuffer(gl.ARRAY_BUFFER,thPosBuf);const lp=gl.getAttribLocation(thermP,'aP');
 gl.enableVertexAttribArray(lp);gl.vertexAttribPointer(lp,3,gl.FLOAT,false,0,0);
 gl.bindBuffer(gl.ARRAY_BUFFER,thValBuf);const lv=gl.getAttribLocation(thermP,'aV');
 gl.enableVertexAttribArray(lv);gl.vertexAttribPointer(lv,1,gl.FLOAT,false,0,0);
 gl.drawArrays(gl.POINTS,0,thN);
}
// 온도 히트맵 — 물리적으로 정직한 단일 눈금: 저점=냉각수 입구(고정), 고점=유전체 기화점(백색)
// (구버전은 층별로 눈금을 따로 잡아, 30°C대 상단 액체가 46°C대 하단 액체와 비슷한 색으로 보이는 문제가 있었음)
function thermRange(T){
 if(T._g)return;
 const lo=((CFG&&CFG.coil&&CFG.coil.Ta_C!=null)?CFG.coil.Ta_C:20)+273.15;
 const sat=Math.max(((CFG&&CFG.dielectric_fluid&&CFG.dielectric_fluid.Tsat_C!=null)?CFG.dielectric_fluid.Tsat_C:47)+273.15, lo+1);
 // 상한 = 기화점 + 5K. 유전체 초기온도(46.85°C)가 기화점(47°C) 바로 아래라, 상한을 기화점에 두면
 // 층 전체가 백색으로 보여 "모두 기화 도달"로 오독됨 → 기화점은 컬러바에 눈금으로만 표시
 T._g={lo,sat,hi:sat+5};
 T._HdM=(CFG?CFG.layers.dielectric_mm:400)/1000;
}
function scalarRange(T,mode){
 if(mode==='concentration'||mode==='sorbed'){const r=(VIZCFG||CFG).scalar_ranges[mode];return T._g={lo:r[0],hi:r[1],sat:null};}
 if(mode==='therm'){thermRange(T);return T._g;}
 if(T._scalarMode===mode&&T._g)return T._g;
 const a=[];for(let i=0;i<T.v.length;i+=Math.max(1,Math.floor(T.v.length/50000))){const v=T.v[i];if(Number.isFinite(v)&&Math.abs(v)>1e-20)a.push(v);}
 a.sort((x,y)=>x-y);let lo=a.length?a[Math.floor(a.length*.02)]:0,hi=a.length?a[Math.floor(a.length*.98)]:1;if(!(hi>lo)){hi=lo+1;}
 T._g={lo,hi,sat:null};T._scalarMode=mode;return T._g;
}
function scalarRamp(mode,u){
 u=Math.max(0,Math.min(1,u));
 if(mode==='therm')return tRamp(u);
 if(mode==='pressure')return u<.5?[35+u*220,92+u*220,205+u*80]:[145+(u-.5)*210,195-(u-.5)*280,225-(u-.5)*330];
 return u<.5?[32+u*110,38+u*180,74+u*250]:[87+(u-.5)*320,128+(u-.5)*220,199-(u-.5)*330];
}
function updateScalarBar(T,mode){
 const g=scalarRange(T,mode),title=document.querySelector('#tcbar>div:first-child'),sat=document.getElementById('tcSat'),satL=document.getElementById('tcSatL');
 if(title){title.textContent=mode==='concentration'?'농도 C/C_ref':mode==='sorbed'?'흡착량 Q/C_ref · 벌크 체적 기준':mode==='pressure'?'압력 Pa':mode==='turbulence'?'난류 운동에너지 k (m²/s²)':'온도 °C';title.title='';}
 document.getElementById('tcHi').textContent=mode==='therm'?(g.hi-273.15).toFixed(1):fmtSci(g.hi);
 document.getElementById('tcLo').textContent=mode==='therm'?(g.lo-273.15).toFixed(1):fmtSci(g.lo);
 if(mode!=='therm'){if(sat)sat.style.display='none';if(satL)satL.textContent='';}else{if(sat)sat.style.display='';updateTcbar(T);}
}
function tNorm1(g,tv){ return Math.max(0,Math.min(1,(tv-g.lo)/(g.hi-g.lo))); }
function tNormY(T,tv,y){ return tNorm1(T._g,tv); }   // 전 영역 동일 눈금 → 층 간 온도 비교가 가능
function updateTcbar(T){
 if(T===updateTcbar.last)return; updateTcbar.last=T;
 const g=T._g, f=(g.sat-g.lo)/(g.hi-g.lo);          // 기화점의 막대 내 위치(아래=0)
 document.getElementById('tcHi').textContent=(g.hi-273.15).toFixed(1);
 document.getElementById('tcLo').textContent=(g.lo-273.15).toFixed(1);
 const sat=document.getElementById('tcSat'), satL=document.getElementById('tcSatL');
 if(sat)sat.style.bottom=(f*100).toFixed(1)+'%';
 if(satL){satL.style.bottom=(f*100).toFixed(1)+'%';
  satL.textContent=(g.sat-273.15).toFixed(1)+' 기화';}
}

// 온도 히트맵 볼륨 — 시점 지배축에 수직인 평면들을 뒤→앞으로 겹침 (축 자동 전환 → 어느 각도에서도 연속 볼륨)
let tvolTex=gl.createTexture(),tvolCv=document.createElement('canvas'),lastTvol=null,lastAxis=-1,lastTvolMode='',tvolBuf=gl.createBuffer();
function tvColor(T,tv,yw,img,p,alpha,mode){
 if((mode==='therm'&&tv<1)||!Number.isFinite(tv)||Math.abs(tv)<1e-20){img.data[p+3]=0;return;}
 const g=scalarRange(T,mode),c=scalarRamp(mode,(tv-g.lo)/(g.hi-g.lo));
 img.data[p]=c[0];img.data[p+1]=c[1];img.data[p+2]=c[2];img.data[p+3]=alpha;
}
function buildTvolAtlas(T,axis,mode='therm'){
 if(T===lastTvol&&axis===lastAxis&&mode===lastTvolMode)return; lastTvol=T; lastAxis=axis;lastTvolMode=mode;
 scalarRange(T,mode);
 const nx=T.nx,ny=T.ny,nz=T.nz;
 const n=[nx,ny,nz][axis];                                 // 슬라이스 수
 const A=[Math.round(255*(1-Math.pow(1-0.94,1/n)))|0];     // 총 불투명도 일정: 1-(1-0.94)^(1/n)
 const al=Math.max(6,A[0]);
 let W,H;
 if(axis===2){W=nx;H=ny*nz;} else if(axis===0){W=nz;H=ny*nx;} else {W=nx;H=nz*ny;}
 tvolCv.width=W; tvolCv.height=H;
 const ctx=tvolCv.getContext('2d'),img=ctx.createImageData(W,H);
 if(axis===2){          // z 슬라이스: 행=y(뒤집힘), 열=x
  for(let k=0;k<nz;k++)for(let j=0;j<ny;j++){
   const yw=T.bb[1]+(j+.5)*(T.bb[4]-T.bb[1])/ny;
   for(let i=0;i<nx;i++)tvColor(T,T.v[(k*ny+j)*nx+i],yw,img,((k*ny+(ny-1-j))*nx+i)*4,al,mode);}
 }else if(axis===0){    // x 슬라이스: 행=y(뒤집힘), 열=z
  for(let i=0;i<nx;i++)for(let j=0;j<ny;j++){
   const yw=T.bb[1]+(j+.5)*(T.bb[4]-T.bb[1])/ny;
   for(let k=0;k<nz;k++)tvColor(T,T.v[(k*ny+j)*nx+i],yw,img,((i*ny+(ny-1-j))*W+k)*4,al,mode);}
 }else{                 // y 슬라이스: 행=z, 열=x (층 높이 고정 → yw = 슬라이스 y)
  for(let j=0;j<ny;j++){
   const yw=T.bb[1]+(j+.5)*(T.bb[4]-T.bb[1])/ny;
   for(let k=0;k<nz;k++)for(let i=0;i<nx;i++)tvColor(T,T.v[(k*ny+j)*nx+i],yw,img,((j*nz+k)*W+i)*4,al,mode);}
 }
 ctx.putImageData(img,0,0);
 gl.bindTexture(gl.TEXTURE_2D,tvolTex);
 gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,tvolCv);
 gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);
 gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
 gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);
 gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
}
function drawTvol(T,M,mode='therm'){
 const x0=T.bb[0]*1000,y0=T.bb[1]*1000,z0=T.bb[2]*1000,x1=T.bb[3]*1000,y1=T.bb[4]*1000,z1=T.bb[5]*1000;
 const E=eye(),C=[(x0+x1)/2,(y0+y1)/2,(z0+z1)/2];
 const d=[E[0]-C[0],E[1]-C[1],E[2]-C[2]],ad=[Math.abs(d[0]),Math.abs(d[1]),Math.abs(d[2])];
 const axis=ad[1]>=ad[0]&&ad[1]>=ad[2]?1:(ad[0]>=ad[2]?0:2);   // 시점과 가장 평행한 축으로 슬라이스
 buildTvolAtlas(T,axis,mode);
 const n=[T.nx,T.ny,T.nz][axis], pos=d[axis]>0;
 gl.useProgram(texP);
 gl.uniformMatrix4fv(gl.getUniformLocation(texP,'uM'),false,new Float32Array(M));
 gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,tvolTex);
 gl.uniform1i(gl.getUniformLocation(texP,'uS'),0);
 const lp=gl.getAttribLocation(texP,'aP'),lt=gl.getAttribLocation(texP,'aT');
 for(let s=0;s<n;s++){
  const k=pos?s:(n-1-s);                                   // 먼 쪽부터
  const v0=k/n, v1=(k+1)/n; let v;
  if(axis===2){const zc=z0+(k+.5)*(z1-z0)/n;
   v=new Float32Array([x0,y0,zc,0,v1, x1,y0,zc,1,v1, x1,y1,zc,1,v0,
                       x0,y0,zc,0,v1, x1,y1,zc,1,v0, x0,y1,zc,0,v0]);}
  else if(axis===0){const xc=x0+(k+.5)*(x1-x0)/n;
   v=new Float32Array([xc,y0,z0,0,v1, xc,y0,z1,1,v1, xc,y1,z1,1,v0,
                       xc,y0,z0,0,v1, xc,y1,z1,1,v0, xc,y1,z0,0,v0]);}
  else{const yc=y0+(k+.5)*(y1-y0)/n;
   v=new Float32Array([x0,yc,z0,0,v0, x1,yc,z0,1,v0, x1,yc,z1,1,v1,
                       x0,yc,z0,0,v0, x1,yc,z1,1,v1, x0,yc,z1,0,v1]);}
  gl.bindBuffer(gl.ARRAY_BUFFER,tvolBuf);gl.bufferData(gl.ARRAY_BUFFER,v,gl.DYNAMIC_DRAW);
  gl.enableVertexAttribArray(lp);gl.vertexAttribPointer(lp,3,gl.FLOAT,false,20,0);
  gl.enableVertexAttribArray(lt);gl.vertexAttribPointer(lt,2,gl.FLOAT,false,20,12);
  gl.drawArrays(gl.TRIANGLES,0,6);
 }
 gl.disableVertexAttribArray(lt);
}
let tsliceTex=gl.createTexture(),tsliceCv=document.createElement('canvas'),lastTSlice=null,tsliceBuf=gl.createBuffer();
// 열화상 카메라 표준 '아이언보우' 팔레트 — 흑→보라→마젠타→적→주황→황→백 연속 그라데이션
const IRON=[[0,[8,4,26]],[0.13,[40,6,88]],[0.3,[120,10,148]],[0.45,[188,32,126]],
            [0.6,[230,84,52]],[0.75,[246,138,16]],[0.88,[250,200,48]],[1,[255,251,224]]];
function tRamp(u){
 for(let i=1;i<IRON.length;i++){
  if(u<=IRON[i][0]){
   const [u0,c0]=IRON[i-1],[u1,c1]=IRON[i],f=(u-u0)/(u1-u0);
   return [c0[0]+(c1[0]-c0[0])*f, c0[1]+(c1[1]-c0[1])*f, c0[2]+(c1[2]-c0[2])*f];
  }
 }
 return IRON[IRON.length-1][1];
}
function drawTSlice(T,M){
 if(T!==lastTSlice){
  lastTSlice=T;
  thermRange(T);
  const nx=T.nx,ny=T.ny,k=T.nz>>1; tsliceCv.width=nx;tsliceCv.height=ny;
  const ctx=tsliceCv.getContext('2d'),img=ctx.createImageData(nx,ny);
  for(let j=0;j<ny;j++)for(let i=0;i<nx;i++){
   const tv=T.v[(k*ny+j)*nx+i], p=((ny-1-j)*nx+i)*4;
   if(tv<1){img.data[p+3]=0;continue;}
   const u=tNormY(T,tv,T.bb[1]),c=tRamp(u);
   img.data[p]=c[0];img.data[p+1]=c[1];img.data[p+2]=c[2];img.data[p+3]=215;
  }
  ctx.putImageData(img,0,0);
  gl.bindTexture(gl.TEXTURE_2D,tsliceTex);
  gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,tsliceCv);
  gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
 }
 const x0=T.bb[0]*1000,y0=T.bb[1]*1000,x1=T.bb[3]*1000,y1=T.bb[4]*1000,zc=(T.bb[2]+T.bb[5])/2*1000+1.5;
 const v=new Float32Array([x0,y0,zc,0,0, x1,y0,zc,1,0, x1,y1,zc,1,1, x0,y0,zc,0,0, x1,y1,zc,1,1, x0,y1,zc,0,1]);
 gl.useProgram(texP);
 gl.uniformMatrix4fv(gl.getUniformLocation(texP,'uM'),false,new Float32Array(M));
 gl.bindBuffer(gl.ARRAY_BUFFER,tsliceBuf);gl.bufferData(gl.ARRAY_BUFFER,v,gl.DYNAMIC_DRAW);
 const lp=gl.getAttribLocation(texP,'aP'),lt=gl.getAttribLocation(texP,'aT');
 gl.enableVertexAttribArray(lp);gl.vertexAttribPointer(lp,3,gl.FLOAT,false,20,0);
 gl.enableVertexAttribArray(lt);gl.vertexAttribPointer(lt,2,gl.FLOAT,false,20,12);
 gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,tsliceTex);
 gl.uniform1i(gl.getUniformLocation(texP,'uS'),0);
 gl.drawArrays(gl.TRIANGLES,0,6);
 gl.disableVertexAttribArray(lt);
}
let sliceBuf=gl.createBuffer();
let arrBuf=gl.createBuffer(),arrN=0,lastArrF=null,lastArrBudget=0,arrSeeds=[],arrScale=.15;
let flowDotBuf=gl.createBuffer(),flowDotSpeedBuf=gl.createBuffer(),flowDotN=0,FLOWPHASE=0;
function viewerFlowBudget(){const value=Number(document.getElementById('flowDensity')?.value);return [1500,6000,18000].includes(value)?value:6000;}
function flowGridSamples(F,budget){
 const dims=[F.nx,F.ny,F.nz],width=dims.map((n,k)=>(F.bb[k+3]-F.bb[k])/n);
 const spacing=Math.cbrt(width.reduce((a,b)=>a*b,1)*dims.reduce((a,b)=>a*b,1)/budget);
 const steps=width.map((v,k)=>Math.min(dims[k],Math.max(1,Math.ceil(spacing/v))));
 const counts=()=>dims.map((n,k)=>Math.ceil(n/steps[k]));
 while(counts().reduce((a,b)=>a*b,1)>budget){const axes=[0,1,2].filter(k=>steps[k]<dims[k]);const axis=axes.reduce((a,b)=>steps[a]*width[a]<=steps[b]*width[b]?a:b);steps[axis]++;}
 const result=[];
 for(let k=0;k<dims[2];k+=steps[2])for(let j=0;j<dims[1];j+=steps[1])for(let i=0;i<dims[0];i+=steps[0])result.push([i,j,k].map((v,a)=>v+Math.floor((Math.min(steps[a],dims[a]-v)-1)/2)));
 return result;
}
function buildArrows(F){ // 3D 벡터장 — 전체 깊이의 화살표 (속도→길이·진하기, 층→색)
 const budget=viewerFlowBudget();if(F===lastArrF&&budget===lastArrBudget)return;lastArrF=F;lastArrBudget=budget;
 const silo=isSiloConfig(VIZCFG||CFG),raw=[];
 for(const [i,j,k] of flowGridSamples(F,budget)){
  const b=((k*F.ny+j)*F.nx+i)*3,u=F.u[b],v=F.u[b+1],w=F.u[b+2],sp=Math.hypot(u,v,w);
  if(sp>1e-8)raw.push({i,j,k,u,v,w,sp});
 }
 const speeds=raw.map(x=>x.sp).sort((a,b)=>a-b);
 arrScale=silo?(speeds.length?speeds[Math.floor((speeds.length-1)*.95)]:1):.15;
 if(!(arrScale>1e-9))arrScale=1;
 const verts=[];arrSeeds=[];
 const push=(x,y,z,sv)=>verts.push(x,y,z,sv);
 for(const q of raw){
  const {i,j,k,u,v,w,sp}=q;if(sp<(silo?arrScale*.012:.005))continue;
  const x0=(F.bb[0]+(i+.5)*(F.bb[3]-F.bb[0])/F.nx)*1000,
        y0=(F.bb[1]+(j+.5)*(F.bb[4]-F.bb[1])/F.ny)*1000,
        z0=(F.bb[2]+(k+.5)*(F.bb[5]-F.bb[2])/F.nz)*1000;
  const sv=Math.min(sp/arrScale,1),L=silo?20+sv*56:6+sv*22;
  const dx=u/sp,dy=v/sp,dz=w/sp;
  const x1=x0+dx*L, y1=y0+dy*L, z1=z0+dz*L;
  // 머리: 진행 방향과 수직인 기저 벡터
  let ax=-dy,ay=dx,az=0; const al=Math.hypot(ax,ay,az)||1; ax/=al;ay/=al;az/=al;
  const hs=silo?9:4.5,ps=silo?5:3;
  const hx=-dx*hs,hy=-dy*hs,hz=-dz*hs, px=ax*ps,py=ay*ps,pz=az*ps;
  push(x0,y0,z0,sv); push(x1,y1,z1,sv);
  push(x1,y1,z1,sv); push(x1+hx+px,y1+hy+py,z1+hz+pz,sv);
  push(x1,y1,z1,sv); push(x1+hx-px,y1+hy-py,z1+hz-pz,sv);
  if(silo)arrSeeds.push({x:x0,y:y0,z:z0,dx,dy,dz,L,sv,h:(i*.754877666+j*.569840296+k*.438289)%1});
 }
 arrN=verts.length/4;
 gl.bindBuffer(gl.ARRAY_BUFFER,arrBuf);
 gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(verts),gl.DYNAMIC_DRAW);
 const vr=document.getElementById('vbarRange'),vt=document.getElementById('vbarTitle');
 if(vr)vr.textContent='0 ~ '+arrScale.toFixed(arrScale<.1?3:2)+'+';
 if(vt)vt.innerHTML=silo?'공기 유속 |U| m/s <span style="color:var(--muted)">마커=흐름 방향</span>':'유속 |U| m/s <span style="color:var(--muted)">화살표=방향</span>';
}
function drawArrows(M){
 gl.useProgram(arrowP);
 gl.uniformMatrix4fv(gl.getUniformLocation(arrowP,'uM'),false,new Float32Array(M));
 gl.uniform1f(gl.getUniformLocation(arrowP,'uIf'),(CFG&&CFG.layers)?CFG.layers.dielectric_mm:400);
 gl.uniform1f(gl.getUniformLocation(arrowP,'uSilo'),isSiloConfig(VIZCFG||CFG)?1:0);
 gl.bindBuffer(gl.ARRAY_BUFFER,arrBuf);
 const lp=gl.getAttribLocation(arrowP,'aP'),ls=gl.getAttribLocation(arrowP,'aS');
 gl.enableVertexAttribArray(lp);gl.vertexAttribPointer(lp,3,gl.FLOAT,false,16,0);
 gl.enableVertexAttribArray(ls);gl.vertexAttribPointer(ls,1,gl.FLOAT,false,16,12);
 gl.drawArrays(gl.LINES,0,arrN);
}
function drawFlowDots(M,phase){
 if(!arrSeeds.length)return;
 const cap=viewerFlowBudget(),stride=Math.max(1,Math.ceil(arrSeeds.length/cap)),n=Math.ceil(arrSeeds.length/stride);
 const pos=new Float32Array(n*3),spd=new Float32Array(n);let o=0;
 for(let i=0;i<arrSeeds.length;i+=stride){const s=arrSeeds[i],q=(s.h+phase*(.32+.72*s.sv))%1;
  pos[o*3]=s.x+s.dx*s.L*q;pos[o*3+1]=s.y+s.dy*s.L*q;pos[o*3+2]=s.z+s.dz*s.L*q;spd[o]=s.sv;o++;}
 flowDotN=o;gl.useProgram(flowDotP);gl.uniformMatrix4fv(gl.getUniformLocation(flowDotP,'uM'),false,new Float32Array(M));
 gl.bindBuffer(gl.ARRAY_BUFFER,flowDotBuf);gl.bufferData(gl.ARRAY_BUFFER,pos,gl.DYNAMIC_DRAW);
 const lp=gl.getAttribLocation(flowDotP,'aP');gl.enableVertexAttribArray(lp);gl.vertexAttribPointer(lp,3,gl.FLOAT,false,0,0);
 gl.bindBuffer(gl.ARRAY_BUFFER,flowDotSpeedBuf);gl.bufferData(gl.ARRAY_BUFFER,spd,gl.DYNAMIC_DRAW);
 const ls=gl.getAttribLocation(flowDotP,'aS');gl.enableVertexAttribArray(ls);gl.vertexAttribPointer(ls,1,gl.FLOAT,false,0,0);
 gl.drawArrays(gl.POINTS,0,flowDotN);
}
function drawSlice(F,M){
 updateSlice(F);
 const [x0,y0,,x1,y1]=[F.bb[0]*1000,F.bb[1]*1000,0,F.bb[3]*1000,F.bb[4]*1000];
 const zc=(F.bb[2]+F.bb[5])/2*1000;
 const v=new Float32Array([x0,y0,zc,0,0, x1,y0,zc,1,0, x1,y1,zc,1,1, x0,y0,zc,0,0, x1,y1,zc,1,1, x0,y1,zc,0,1]);
 gl.useProgram(texP);
 gl.uniformMatrix4fv(gl.getUniformLocation(texP,'uM'),false,new Float32Array(M));
 gl.bindBuffer(gl.ARRAY_BUFFER,sliceBuf);gl.bufferData(gl.ARRAY_BUFFER,v,gl.DYNAMIC_DRAW);
 const lp=gl.getAttribLocation(texP,'aP'),lt=gl.getAttribLocation(texP,'aT');
 gl.enableVertexAttribArray(lp);gl.vertexAttribPointer(lp,3,gl.FLOAT,false,20,0);
 gl.enableVertexAttribArray(lt);gl.vertexAttribPointer(lt,2,gl.FLOAT,false,20,12);
 gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,sliceTex);
 gl.uniform1i(gl.getUniformLocation(texP,'uS'),0);
 gl.drawArrays(gl.TRIANGLES,0,6);
 gl.disableVertexAttribArray(lt);
}
function uploadPoints(){
 if(typeof warehouseActive==='function'&&warehouseActive()){ensureWarehouseFrame(idx);return;}
 const f=FRAMES[idx];GPUFRAME=-1;GPUN=0;
 if(!f||!f.pos||!f.al){if(f)ensureVizFrame(idx);return;}
 gl.bindBuffer(gl.ARRAY_BUFFER,pBuf);gl.bufferData(gl.ARRAY_BUFFER,f.pos,gl.DYNAMIC_DRAW);
 gl.bindBuffer(gl.ARRAY_BUFFER,aBuf);gl.bufferData(gl.ARRAY_BUFFER,f.al,gl.DYNAMIC_DRAW);
 GPUFRAME=idx;GPUN=f.n;
}
function resetCam(){
 if(typeof warehouseActive==='function'&&warehouseActive()){warehouseCamera();return;}
 th=0; ph=0;
 if(isTracerConfig(VIZCFG||CFG)){tracerCamera(VIZCFG||CFG);return;}
 if(isSiloConfig(VIZCFG||CFG)){const p=(VIZCFG||CFG).published||{},r=(+p.storage_diameter_m||.8)*500,H=(+p.total_height_m||1.4)*1000;tgt=[0,0,H*.48];rad=Math.max(r*2,H)*1.65;ph=.08;}
 else if(CFG){const W=CFG.tank.width_mm,D=CFG.tank.depth_mm,H=CFG.tank.liquid_height_mm,
  AIR=(CFG.layers&&CFG.layers.air_mm!=null)?CFG.layers.air_mm:200;
  tgt=[W/2,(H+AIR)*0.45,D/2]; rad=Math.max(W,H+AIR)*2.25;}
 else{tgt=[228,380,35];rad=1650;}
 toast('카메라를 기본 시점으로 재조정했습니다');}
function eye(){if((typeof warehouseActive==='function'&&warehouseActive())||isSiloConfig(VIZCFG||CFG)||isTracerConfig(VIZCFG||CFG))return[tgt[0]+rad*Math.cos(ph)*Math.sin(th),tgt[1]+rad*Math.cos(ph)*Math.cos(th),tgt[2]+rad*Math.sin(ph)];return[tgt[0]+rad*Math.cos(ph)*Math.sin(th),tgt[1]+rad*Math.sin(ph),tgt[2]+rad*Math.cos(ph)*Math.cos(th)];}
function viewUp(){return (typeof warehouseActive==='function'&&warehouseActive())||isSiloConfig(VIZCFG||CFG)||isTracerConfig(VIZCFG||CFG)?[0,0,1]:[0,1,0];}
let VW,VH;
function resize(){const d=Math.min(devicePixelRatio||1,2);VW=cv.clientWidth;VH=cv.clientHeight;cv.width=VW*d;cv.height=VH*d;gl.viewport(0,0,cv.width,cv.height);}
addEventListener('resize',resize); setTimeout(resize,60);
let dragV=null;
cv.addEventListener('mousedown',e=>{if(e.button!==0)return;dragV={x:e.clientX,y:e.clientY};cv.style.cursor='grabbing';});
addEventListener('mouseup',()=>{dragV=null;cv.style.cursor='grab';});
addEventListener('mousemove',e=>{if(!dragV)return;const dx=e.clientX-dragV.x,dy=e.clientY-dragV.y;dragV.x=e.clientX;dragV.y=e.clientY;
 th+=dx*0.0055*(viewUp()[2]===1?1:-1);ph=Math.min(1.5,Math.max(-0.35,ph+dy*0.0045));});
function cameraModelSpan(){
 const c=VIZCFG||CFG;
 if(c?._해석유형==='warehouse'&&c.warehouse){const g=c.warehouse.geometry;return Math.max(g.length_m,g.width_m,g.eaves_m+g.roof_rise_m)*1000;}
 if(isTracerConfig(c))return Math.max(...c.tracer.lengths_m)*1000;
 if(isSiloConfig(c))return Math.max(c.published?.storage_diameter_m||.8,c.published?.total_height_m||1.4)*1000;
 return Math.max(c?.tank?.width_mm||456,c?.tank?.depth_mm||70,(c?.tank?.liquid_height_mm||800)+(c?.layers?.air_mm??200));
}
function boundedZoomRadius(radius,delta,mode,span){
 const pixels=delta*(mode===1?16:mode===2?240:1),step=Math.max(-60,Math.min(60,pixels));
 return Math.max(span*.12,Math.min(span*10,radius*Math.exp(step*.0005)));
}
cv.addEventListener('wheel',e=>{e.preventDefault();rad=boundedZoomRadius(rad,e.deltaY,e.deltaMode,cameraModelSpan());},{passive:false});
cv.addEventListener('dblclick',()=>resetCam());
cv.addEventListener('contextmenu',e=>e.preventDefault());
function dM(m,c,M){gl.useProgram(solP);gl.uniformMatrix4fv(gl.getUniformLocation(solP,'uM'),false,new Float32Array(M));
 gl.uniform4fv(gl.getUniformLocation(solP,'uC'),c);gl.bindBuffer(gl.ARRAY_BUFFER,m.b);
 const l=gl.getAttribLocation(solP,'aP');gl.enableVertexAttribArray(l);gl.vertexAttribPointer(l,3,gl.FLOAT,false,0,0);
 gl.drawArrays(gl.TRIANGLES,0,m.n);}
function dL(m,c,M){gl.useProgram(solP);gl.uniformMatrix4fv(gl.getUniformLocation(solP,'uM'),false,new Float32Array(M));
 gl.uniform4fv(gl.getUniformLocation(solP,'uC'),c);gl.bindBuffer(gl.ARRAY_BUFFER,m.b);
 const l=gl.getAttribLocation(solP,'aP');gl.enableVertexAttribArray(l);gl.vertexAttribPointer(l,3,gl.FLOAT,false,0,0);
 gl.drawArrays(gl.LINES,0,m.n);}
const LY=id=>document.getElementById(id).checked;
let FDT=0.5, lastTbarShow=false, lastVbarShow=false;   // 프레임 간 물리 간격 중앙값 (마지막 프레임 표시 길이)
function framePlayTime(f){return f&&Number.isFinite(f.pt)?f.pt:(f?f.t:0);}
function frameIndexAt(t){
 let lo=0,hi=FRAMES.length-1;
 while(lo<hi){const mid=Math.ceil((lo+hi)/2);if(framePlayTime(FRAMES[mid])<=t)lo=mid;else hi=mid-1;}
 return lo;
}
function frameRawIndexAt(t){
 let lo=0,hi=FRAMES.length-1;
 while(lo<hi){const mid=Math.ceil((lo+hi)/2);if(FRAMES[mid].t<=t)lo=mid;else hi=mid-1;}
 return lo;
}
function readyFrameNear(target){
 if(FRAMES[target]&&FRAMES[target].ready)return target;
 for(let d=1;d<=8;d++){
  const a=target-d,b=target+d;
  if(a>=0&&FRAMES[a].ready)return a;
  if(b<FRAMES.length&&FRAMES[b].ready)return b;
 }
 return FRAMES[idx]&&FRAMES[idx].ready?idx:-1;
}
function readyFrameAtOrBefore(target){
 // 준비된 미래 프레임을 먼저 보여주지 않고, 벽시계 시각 이전의 가장 가까운 화면만 선택한다.
 const span=Math.max(8,Math.ceil((Math.max(1,+document.getElementById('speed').value||1)*.6)/Math.max(FDT,0.001)));
 for(let i=target;i>=Math.max(0,target-span);i--)if(FRAMES[i]&&FRAMES[i].ready)return i;
 return -1;
}
// ══════════════ Viewer 그래프 (좌상단 · 재생 시점 커서) ══════════════
const GDEF=[
 {id:'gcT', title:'열전대 온도 (°C)', color:'#3987e5', multi:true},
 {id:'gcV', title:'기포 부피 (mL)',   color:'#31c46a'},
 {id:'gcB', title:'기포 셀 수',       color:'#c76bd6'},
 {id:'gcL', title:'층별 평균 온도 (°C)', color:'#e08a3a', multi:true}];
const GCOL4=['#3987e5','#d95926','#199e70','#c98500'];   // --s1~--s4 (3D 라벨·대시보드 범례와 동일)
const GNAME4=['T1 CPU','T2 계면↓','T3 계면↑','T4 코일↑'];
function gSeries(id){                                   // [{name,color,pts:[[t,v]..]}], 값 없으면 []
 if(typeof warehouseActive==='function'&&warehouseActive()){return warehouseSeries(id);}
 const HP=(VPROJ==null)?HIST:VHIST;
 if(id==='gcT'){
  if(HP.length<2)return [];
  const rows=HP.slice(-600);
  const out=[0,1,2,3].map(k=>({name:GNAME4[k],color:GCOL4[k],pts:rows.map(r=>[r[0],r[k+1]])}));
  const cp=coilPars(),HC=(VPROJ==null)?HISTC:VHISTC;
  if(cp&&isFinite(cp.t5))out.push({name:'T5 입구',color:'#d65380',dash:true,pts:rows.map(r=>[r[0],cp.t5])});
  if(cp&&cp.hA!=null&&cp.mcp&&HC.length>1){
   const t6=HC.slice(-600).map(r=>[r[0],cp.t5+cp.hA*(r[1]-cp.t5)/cp.mcp]);
   out.push({name:'T6 출구(계산)',color:'#008500',dash:true,pts:t6});
  }
  return out;
 }
 if(id==='gcV'){
  const fs=FRAMES.filter(f=>f.statsReady);if(fs.length<2)return [];
  return [{name:'기포 부피',color:'#31c46a',pts:fs.map(f=>[f.t,f.v||0])}];
 }
 if(id==='gcB'){
  const fs=FRAMES.filter(f=>f.statsReady);if(fs.length<2)return [];
  return [{name:'셀 수',color:'#c76bd6',pts:fs.map(f=>[f.t,f.n])}];
 }
 if(id==='gcL'){
  if(gSeries._lk===GKEY()&&gSeries._lv)return gSeries._lv;      // 층 평균은 프레임 전체 순회 — 데이터 변동 시에만 계산
  const ts=Object.keys(THERMMAP).map(Number).sort((x,y)=>x-y);
  if(ts.length<2)return [];
  const HdM=(CFG?CFG.layers.dielectric_mm:400)/1000, d=[],w=[];
  for(const t of ts){
   const T=THERMMAP[t]; let sd=0,nd=0,sw=0,nw=0;
   for(let j=0;j<T.ny;j++){
    const y=T.bb[1]+(j+.5)*(T.bb[4]-T.bb[1])/T.ny;
    for(let k=0;k<T.nz;k++)for(let i=0;i<T.nx;i++){
     const v=T.v[(k*T.ny+j)*T.nx+i]; if(v<1)continue;
     if(y<HdM){sd+=v;nd++;} else {sw+=v;nw++;}}}
   if(nd)d.push([t,sd/nd-273.15]); if(nw)w.push([t,sw/nw-273.15]);
  }
  const out=[];
  if(d.length>1)out.push({name:'유전체층',color:'#e08a3a',pts:d});
  if(w.length>1)out.push({name:'상단 액체',color:'#4a9ef5',pts:w});
  gSeries._lk=GKEY(); gSeries._lv=out;
  return out;
 }
 return [];
}
function gDraw(card,def){
 const ser=gSeries(def.id), svg=card.querySelector('svg'), val=card.querySelector('b');
 card._ser=ser;
 if(!ser.length){svg.innerHTML='<text x="50%" y="55%" text-anchor="middle" fill="#6b6b66" font-size="10">데이터 없음</text>';
  if(val)val.textContent='—'; return;}
 const W=Math.max(120,card.clientWidth-20),H=62;
 svg.setAttribute('viewBox','0 0 '+W+' '+H);
 let lo=Infinity,hi=-Infinity,t0=Infinity,t1=-Infinity;
 for(const s of ser)for(const p of s.pts){if(!isFinite(p[1]))continue;
  lo=Math.min(lo,p[1]);hi=Math.max(hi,p[1]);t0=Math.min(t0,p[0]);t1=Math.max(t1,p[0]);}
 if(!(hi>lo)){hi=lo+1;lo-=0.5;} else {const pd=(hi-lo)*0.12;hi+=pd;lo-=pd;}
 if(def.id==='gcV'||def.id==='gcB')lo=Math.max(0,lo);
 card._map={t0,t1,W};
 const X=t=>4+(W-8)*(t-t0)/Math.max(t1-t0,1e-9), Y=v=>H-6-(H-13)*(v-lo)/(hi-lo);
 let g='';
 for(let i=0;i<3;i++){const y=7+i*(H-13)/2;g+='<line x1="4" y1="'+y+'" x2="'+(W-4)+'" y2="'+y+'" stroke="#2c2c2a"/>';}
 for(const s of ser){
  let d='M'+X(s.pts[0][0]).toFixed(1)+' '+Y(s.pts[0][1]).toFixed(1);
  for(let i=1;i<s.pts.length;i++)d+='L'+X(s.pts[i][0]).toFixed(1)+' '+Y(s.pts[i][1]).toFixed(1);
  g+='<path d="'+d+'" fill="none" stroke="'+s.color+'" stroke-width="1.6" stroke-linejoin="round"'+(s.dash?' stroke-dasharray="4 3"':'')+'/>';
 }
 g+='<text x="'+(W-5)+'" y="10" text-anchor="end" fill="#6b6b66" font-size="8.5">'+fmtSci(hi)+'</text>';
 g+='<text x="'+(W-5)+'" y="'+(H-1)+'" text-anchor="end" fill="#6b6b66" font-size="8.5">'+fmtSci(lo)+'</text>';
 g+='<line class="gcur" x1="4" y1="3" x2="4" y2="'+(H-4)+'" stroke="#ffffff" stroke-opacity=".5" stroke-width="1"/>';
 svg.innerHTML=g;
 const lg=card.querySelector('.glg');
 if(lg){
  lg.style.display=(ser.length>1)?'':'none';
  if(ser.length>1)lg.innerHTML=ser.map((s,i)=>'<span data-i="'+i+'"><i style="background:'+s.color+'"></i>'
   +esc(s.name)+' <b></b></span>').join('');
 }
}
function renderGCol(){
 const col=document.getElementById('gcol'); if(!col)return;
 const on=GDEF.filter(d=>{const e=document.getElementById(d.id);return e&&e.checked;});
 if(col._keys===on.map(d=>d.id).join()+'|'+GKEY()){gTick();return;}
 col._keys=on.map(d=>d.id).join()+'|'+GKEY();
 col.innerHTML='';
 for(const def of on){
  const c=document.createElement('div'); c.className='gcard';
  c.innerHTML='<div class="gtit"><span>'+def.title+'</span><b></b></div>'
   +'<svg preserveAspectRatio="none"></svg><div class="glg"></div>';
  col.appendChild(c); c._def=def; gDraw(c,def);
 }
 gTick();
 saveUI(false);
}
function GKEY(){const tk=Object.keys(THERMMAP).map(Number).sort((a,b)=>a-b),stats=FRAMES.reduce((n,f)=>n+(f.statsReady?1:0),0);
 return FRAMES.length+'/'+stats+'/'+((VPROJ==null?HIST:VHIST).length)+'/'+((VPROJ==null?HISTC:VHISTC).length)+'/'+
  tk.length+'/'+(tk.length?(tk[0]+'-'+tk[tk.length-1]):'')+'/'+(CFG&&CFG.coil?((CFG.coil.Ta_C||'')+'/'+(CFG.coil.flow_LPM||'')):'');}
function gTick(){                                        // 재생 시점 커서·현재값 갱신 (매 프레임, 가벼움)
 const col=document.getElementById('gcol'); if(!col||!col.children.length)return;
 const t=(typeof warehouseActive==='function'&&warehouseActive())?clock:(FRAMES.length?FRAMES[Math.min(idx,FRAMES.length-1)].t:null);
 for(const c of col.children){
  const m=c._map, ser=c._ser, cur=c.querySelector('.gcur'), val=c.querySelector('b');
  if(!m||!ser||!ser.length){continue;}
  if(t!=null&&cur){
   const x=4+(m.W-8)*Math.max(0,Math.min(1,(t-m.t0)/Math.max(m.t1-m.t0,1e-9)));
   cur.setAttribute('x1',x.toFixed(1)); cur.setAttribute('x2',x.toFixed(1));
  }
  const vals=ser.map(s=>{const r=(t!=null)?histAt(s.pts,t):s.pts[s.pts.length-1];
   return r?fmtSci(r[1]):'—';});
  if(ser.length>1){
   const bs=c.querySelectorAll('.glg b');
   for(let i=0;i<bs.length;i++)bs[i].textContent=vals[i]!=null?vals[i]:'—';
   if(val)val.textContent='';
  } else if(val) val.textContent=vals[0]||'—';
 }
}
function frame(){
 const now=performance.now(),dt=(now-last)/1000;last=now;
 if(MODE!=='viz'){requestAnimationFrame(frame);return;}
 if(!VW||VW<10)resize();
 if(typeof warehouseActive==='function'&&warehouseActive()){frameWarehouse(now,dt);requestAnimationFrame(frame);return;}
 if(isTracerConfig(VIZCFG||CFG)){frameTracer(now,dt);requestAnimationFrame(frame);return;}
 const spd=+document.getElementById('speed').value;   // 1=실시간(물리시간 배속)
 if(playing)FLOWPHASE+=Math.min(dt,.08)*spd;
 if(playing&&FRAMES.length){
  const t0=framePlayTime(FRAMES[0]),t1=framePlayTime(FRAMES[FRAMES.length-1]);
  if(!Number.isFinite(clock)||clock<t0||clock>t1)clock=t0;
  const nextClock=Math.min(t1,clock+dt*spd),reachedEnd=nextClock>=t1;
  const target=frameIndexAt(nextClock);
  // 화면을 보여준 뒤 시간만 흐르게 하지 않는다. 앞 구간 버퍼가 소진되면
  // 물리 시계도 함께 멈추고 버퍼를 다시 채운 뒤 이어서 재생한다.
  if(!playbackBufferReady(target,.5)){startBufferedPlayback(true);}
  else{
   clock=nextClock;prefetchViz(target);
   const shown=vizFrameReady(target,true)?target:readyFrameAtOrBefore(target);
   if(shown>=0&&shown!==idx){idx=shown;uploadPoints();trimVizCache(shown);}
   if(reachedEnd){idx=FRAMES.length-1;clock=t1;uploadPoints();trimVizCache(idx);setPlaybackEnded();}
  }
 }
 if(FRAMES.length&&idx>=FRAMES.length){idx=FRAMES.length-1;clock=framePlayTime(FRAMES[idx]);}   // 로딩 중 축소된 배열 보호
 document.getElementById('tbar').value=idx;
 renderGCol();
 let FL=null,TH=null,PH=null,PR=null,TR=null;
 if(FRAMES.length){const F=FRAMES[idx],shownT=playing?clock:framePlayTime(F),ax=runAxis(VIZCFG||CFG);document.getElementById('tlab').textContent=shownT.toFixed(2)+(ax.steady?'s':ax.unit)+' ('+FRAMES.length.toLocaleString()+'프레임)';document.getElementById('tlab').title=ax.steady?'재생 시간 · 전체 저장 프레임 수 · 솔버 '+F.t.toFixed(0)+'회':'현재 시간 · 전체 저장 프레임 수';
  document.getElementById('hT').textContent=shownT.toFixed(2);
  const vapourML=frameVapourML(F);document.getElementById('hV').textContent=Number.isFinite(vapourML)?vapourML.toFixed(0):'—';
  document.getElementById('hC').textContent=F.n.toLocaleString();
  FL=flowFor(F.t);TH=thermFor(F.t);PH=phaseFor(F.t);PR=scalarFor(PRESSUREMAP,F.t);TR=scalarFor(TURBMAP,F.t);}
 gl.clearColor(0.051,0.051,0.051,1);gl.enable(gl.DEPTH_TEST);gl.depthMask(true);
 gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
 if(CFG){
  const M=mul(persp(38*Math.PI/180,VW/VH,5,9000),lookAt(eye(),tgt,viewUp()));
  const silo=isSiloConfig(VIZCFG||CFG);
  gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);gl.depthMask(false);
  if(silo){if(LY('lyTank'))dM(G.silo,[.55,.6,.68,.012],M);if(LY('lyGeo'))dM(G.grain,[.24,.42,.18,.022],M);if(LY('lyCoil'))dM(G.duct,[.56,.66,.82,.11],M);}
  else{if(LY('lyTank'))dM(G.glass,[.55,.6,.68,.022],M);if(LY('lyCoil'))dM(G.coil,[.56,.66,.82,.1],M);}
  gl.depthMask(true);
  if(silo){if(LY('lyGeo'))dL(G.grainE,[.45,.72,.3,.18],M);if(LY('lyCoil'))dL(G.ductE,[.62,.72,.88,.5],M);if(LY('lyTank'))dL(G.siloE,[.8,.84,.92,.3],M);if(LY('lyBound'))dL(G.grainE,[.95,.61,.2,.46],M);}
  else{if(LY('lyGeo')){dM(G.board,[.075,.42,.26,1],M);dM(G.cpu,[1,.55,.16,1],M);dL(G.boardE,[.5,.9,.7,.35],M);}if(LY('lyCoil'))dL(G.coilE,[.62,.72,.88,.35],M);if(LY('lyTank'))dL(G.tank,[.8,.84,.92,.5],M);if(LY('lyBound')){dL(G.ifaceE,[.92,.5,.22,.75],M);dL(G.liqTop,[.72,.78,.88,.65],M);}if(LY('lyProbe')&&G.probes)for(let i=0;i<G.probes.length;i++)dL(G.probes[i],PCOL[i],M);}
  updateProbeLabels(M);
  const uK=(cv.height/2)/Math.tan(19*Math.PI/180);
  if(TH&&LY('lyTvol')&&!silo){gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);gl.depthMask(false);
   drawTvol(TH,M);updateTcbar(TH);gl.depthMask(true);}
  if(PH&&LY('lyPhase')&&!silo){gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);gl.depthMask(false);
   drawPhase(PH,M,uK);gl.depthMask(true);}
  if(PR&&LY('lyBub')&&silo){gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);gl.depthMask(false);drawTvol(PR,M,'pressure');updateScalarBar(PR,'pressure');gl.depthMask(true);}
  if(TR&&LY('lyPhase')&&silo){gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);gl.depthMask(false);drawTvol(TR,M,'turbulence');updateScalarBar(TR,'turbulence');gl.depthMask(true);}
  // 스칼라 볼륨 위에 속도 방향을 마지막으로 그려, 압력·난류장을 함께 켜도
  // 화살표와 이동 마커가 내부에 묻히지 않게 한다.
  if(FL&&LY('lySlice')){buildArrows(FL);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);gl.depthMask(false);
   if(arrN)drawArrows(M);if(silo)drawFlowDots(M,FLOWPHASE);gl.depthMask(true);}
  const showTbar=!!((TH&&LY('lyTvol')&&!silo)||(PR&&LY('lyBub')&&silo)||(TR&&LY('lyPhase')&&silo));
  const showVbar=!!(FL&&LY('lySlice'));
  if(showVbar!==lastVbarShow){lastVbarShow=showVbar;
   document.getElementById('vbar').style.display=showVbar?'':'none';}
  if(showTbar!==lastTbarShow){lastTbarShow=showTbar;
   document.getElementById('tcbar').style.display=showTbar?'flex':'none';}
  if(LY('lyBub')&&FRAMES.length&&GPUFRAME===idx&&!silo){
   gl.blendFunc(gl.SRC_ALPHA,gl.ONE);gl.depthMask(false);gl.useProgram(ptsP);
   gl.uniformMatrix4fv(gl.getUniformLocation(ptsP,'uM'),false,new Float32Array(M));
   gl.uniform1f(gl.getUniformLocation(ptsP,'uK'),uK);
   gl.bindBuffer(gl.ARRAY_BUFFER,pBuf);const lp=gl.getAttribLocation(ptsP,'aP');
   gl.enableVertexAttribArray(lp);gl.vertexAttribPointer(lp,3,gl.FLOAT,false,0,0);
   gl.bindBuffer(gl.ARRAY_BUFFER,aBuf);const la=gl.getAttribLocation(ptsP,'aA');
   gl.enableVertexAttribArray(la);gl.vertexAttribPointer(la,1,gl.FLOAT,false,0,0);
   if(GPUN>0)gl.drawArrays(gl.POINTS,0,GPUN);
   gl.depthMask(true);
  }
 }
 if(REC)recTick();
 requestAnimationFrame(frame);
}
requestAnimationFrame(frame);

// ══════════════ Export — 현재 3D 화면의 영상·이미지 ══════════════
let REC=null;
function exportProjectName(){
 if(typeof warehouseActive==='function'&&warehouseActive()){return WH?.name||"저장고";}
 const rid=vzrid()||CURC,p=LASTPROJS.find(x=>x.rid===rid);
 return (p&&p.name)||rid||'project';
}
function exportSafeName(s){return String(s||'project').replace(/[\\/:*?"<>|]+/g,'_').replace(/[. ]+$/,'').slice(0,80)||'project';}
function exportDownload(blob,name){
 const u=URL.createObjectURL(blob),a=document.createElement('a');a.href=u;a.download=name;
 document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),5000);
}
async function exportPick(name,mime,ext,desc){
 if(!window.showSaveFilePicker)return null;
 try{return await window.showSaveFilePicker({suggestedName:name,
  types:[{description:desc,accept:{[mime]:[ext]}}],excludeAcceptAllOption:false});}
 catch(e){if(e&&e.name==='AbortError')return false;throw e;}
}
async function exportSave(blob,name,handle){
 if(handle===false)return false;
 if(handle){const w=await handle.createWritable();await w.write(blob);await w.close();}
 else exportDownload(blob,name);
 toast(handle?'저장 완료 — 선택한 위치의 '+name:'저장 완료 — 다운로드 폴더의 '+name);
 return true;
}
function pickVideoMime(fmt){
 const cs=fmt==='mp4'?['video/mp4;codecs=avc1.42E01E','video/mp4;codecs=avc1','video/mp4']:
  ['video/webm;codecs=vp9','video/webm;codecs=vp8','video/webm'];
 return cs.find(x=>window.MediaRecorder&&MediaRecorder.isTypeSupported(x))||'';
}
function closeExport(){document.getElementById('exportBg').style.display='none';}
function openExport(){
 if(REC){stopVideo();return;}
 const p=document.getElementById('exProjName');p.textContent=exportProjectName();
 const sel=document.getElementById('exVidFmt'),mp4=pickVideoMime('mp4'),webm=pickVideoMime('webm');
 sel.querySelector('option[value="mp4"]').disabled=!mp4;
 sel.querySelector('option[value="webm"]').disabled=!webm;
 if(!pickVideoMime(sel.value))sel.value=mp4?'mp4':'webm';
 const n=document.getElementById('exVidNote');
 n.textContent=mp4?'':'이 브라우저는 MP4 녹화를 지원하지 않아 WebM을 사용합니다.';
 n.style.display=mp4?'none':'block';
 document.getElementById('exportBg').style.display='flex';
}
async function startExportVideo(){
 if(!FRAMES.length){toast('시각화 데이터가 있는 프로젝트를 먼저 선택하세요',true);return;}
 const fmt=document.getElementById('exVidFmt').value,mime=pickVideoMime(fmt);
 if(!mime){toast(fmt.toUpperCase()+' 녹화를 지원하지 않는 브라우저입니다',true);return;}
 const ext=fmt==='mp4'?'.mp4':'.webm';
 const name='CFD_'+exportSafeName(exportProjectName())+'_animation'+ext;
 const handle=await exportPick(name,mime.split(';')[0],ext,fmt.toUpperCase()+' 영상');
 if(handle===false)return;
 closeExport();exportVideo(fmt,mime,name,handle);
}
function exportVideo(fmt,mime,name,handle){
 const c=document.createElement('canvas');c.width=cv.width;c.height=cv.height;
 const rec=new MediaRecorder(c.captureStream(60),{mimeType:mime,videoBitsPerSecond:14000000});
 const chunks=[];rec.ondataavailable=e=>{if(e.data.size)chunks.push(e.data)};
 rec.onstop=async()=>{try{await exportSave(new Blob(chunks,{type:mime.split(';')[0]}),name,handle);}
  catch(e){toast('영상 저장 실패: '+e.message,true);}};
 REC={rec,c,x:c.getContext('2d'),prev:-1,t0:performance.now()};
 idx=0;clock=framePlayTime(FRAMES[0]);setPlay(true);rec.start(250);
 const exportButton=document.getElementById('btnExport');exportButton.textContent='녹화 종료';exportButton.title='녹화를 종료하고 영상 저장';exportButton.classList.add('recording');
 toast('녹화 시작 — 현재 레이어·카메라·배속으로 끝까지 재생합니다');
}
function stopVideo(){
 if(!REC)return;const R=REC;REC=null;
 const exportButton=document.getElementById('btnExport');exportButton.textContent='Export';exportButton.title='3D 영상·이미지 내보내기';exportButton.classList.remove('recording');
 try{R.rec.stop();}catch(_){}
}
function recTick(){
 const R=REC,d=cv.width/Math.max(1,VW);
 if(R.c.width!==cv.width||R.c.height!==cv.height){R.c.width=cv.width;R.c.height=cv.height;}
 R.x.drawImage(cv,0,0);
 drawRecOv(R.x,d);
 if(FRAMES.length>1){ if(R.prev>idx){stopVideo();return;} R.prev=idx;if(PLAYENDED){stopVideo();return;} }
 else if(performance.now()-R.t0>2000)stopVideo();
}
function rrect(x,a,b,w,h,r){x.beginPath();x.moveTo(a+r,b);x.arcTo(a+w,b,a+w,b+h,r);
 x.arcTo(a+w,b+h,a,b+h,r);x.arcTo(a,b+h,a,b,r);x.arcTo(a,b,a+w,b,r);x.closePath();}
function drawRecOv(x,d){
 if(typeof warehouseActive==='function'&&warehouseActive()){drawWarehouseOverlay(x,d);return;}
 if(isTracerConfig(VIZCFG||CFG)){drawTracerOverlay(x,d);return;}
 x.save();x.textBaseline='middle';
 const F=FRAMES[idx];
 if(F){                                                       // 시간·증기 배지 (좌상단)
  x.font=(13*d)+'px "Segoe UI",sans-serif';
  const ax=runAxis(VIZCFG||CFG),pt=framePlayTime(F);
  const txt=ax.steady?('재생 '+pt.toFixed(2)+' s ('+F.t.toFixed(0)+'회)'):('t = '+F.t.toFixed(2)+' s'+(F.v?'    증기 '+F.v.toFixed(0)+' mL':''));
  x.fillStyle='rgba(18,18,18,.72)';rrect(x,12*d,12*d,x.measureText(txt).width+20*d,27*d,7*d);x.fill();
  x.fillStyle='#eceada';x.fillText(txt,22*d,26*d);
 }
 if(LY('lyProbe'))for(const L of LBREC){                       // 열전대 라벨
  x.font=(10.5*d)+'px "Segoe UI",sans-serif';
  const tw=x.measureText(L.text).width;
  x.fillStyle='rgba(18,18,18,.7)';rrect(x,(L.x+8)*d,(L.y-9)*d,tw+13*d,18*d,4*d);x.fill();
  x.fillStyle=L.col;x.fillRect((L.x+8)*d,(L.y-9)*d,2.5*d,18*d);
  x.fillStyle='#e8e6d9';x.fillText(L.text,(L.x+14)*d,L.y*d);
 }
 const T=updateTcbar.last;
 if(lastTbarShow&&T&&T._g){                                    // 온도 컬러바 (우하단)
  const H=150*d,Wb=13*d,X=x.canvas.width-58*d,Y=x.canvas.height-H-70*d;
  x.fillStyle='rgba(18,18,18,.6)';rrect(x,X-8*d,Y-22*d,60*d,H+34*d,6*d);x.fill();
  for(let i=0;i<H;i++){const c=tRamp(1-i/H);x.fillStyle='rgb('+c[0]+','+c[1]+','+c[2]+')';
   x.fillRect(X,Y+i,Wb,2);}
  x.font=(9.5*d)+'px "Segoe UI",sans-serif';x.fillStyle='#d8d6c9';
  x.fillText('°C',X,Y-11*d);
  x.fillText((T._g.hi-273.15).toFixed(1),X+Wb+4*d,Y+5*d);
  x.fillText((T._g.lo-273.15).toFixed(1),X+Wb+4*d,Y+H-5*d);
 }
 x.restore();
}
function exportCanvasBlob(c){return new Promise((ok,no)=>c.toBlob(b=>b?ok(b):no(new Error('이미지 생성 실패')),'image/png'));}
async function saveProjectScreenshot(){
 if(typeof warehouseActive==='function'&&warehouseActive()){await exportViewPNG();return;}
 if(!FRAMES.length){toast('시각화 데이터가 있는 프로젝트를 먼저 선택하세요',true);return;}
 const rid=extractTarget();
 if(!rid){toast('스크린샷을 저장할 프로젝트를 선택하세요',true);return;}
 try{
  // Viewer UI와 시간·라벨 오버레이를 합성하지 않은 순수 3D 캔버스만 저장한다.
  const c=document.createElement('canvas');c.width=cv.width;c.height=cv.height;
  c.getContext('2d').drawImage(cv,0,0);
  const png=await new Promise((ok,no)=>{const r=new FileReader();r.onload=()=>ok(r.result);r.onerror=()=>no(new Error('이미지 변환 실패'));exportCanvasBlob(c).then(b=>r.readAsDataURL(b),no);});
  const res=await (await fetch('/api/screenshot',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rid,png})})).json();
  if(!res.ok)throw new Error(res.msg||'저장 실패');
  toast('스크린샷 저장 완료 — '+res.name);
 }catch(e){toast('스크린샷 저장 실패: '+(e.message||e),true);}
}
async function exportViewPNG(){
 if(!FRAMES.length){toast('시각화 데이터가 있는 프로젝트를 먼저 선택하세요',true);return;}
 const displayedTime=(typeof warehouseActive==='function'&&warehouseActive())?clock:FRAMES[idx].t;
 const name='CFD_'+exportSafeName(exportProjectName())+'_view_'+displayedTime.toFixed(2)+'s.png';
 const handle=await exportPick(name,'image/png','.png','PNG 화면');if(handle===false)return;
 const c=document.createElement('canvas');c.width=cv.width;c.height=cv.height;const x=c.getContext('2d');x.drawImage(cv,0,0);drawRecOv(x,cv.width/Math.max(1,VW));
 try{await exportSave(await exportCanvasBlob(c),name,handle);}catch(e){toast('화면 저장 실패: '+e.message,true);}
}
let PLAYBUFFERING=false,PLAYBUFSEQ=0,PLAYENDED=false;
function renderPlayButton(){
 const ico=document.getElementById('playIco'),b=document.getElementById('play');if(!ico||!b)return;
 if(PLAYENDED){ico.innerHTML='<path d="M20 11a8 8 0 1 0-2.34 5.66" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round"/><path d="M20 4v7h-7" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>';b.title='처음으로';}
 else if(playing||PLAYBUFFERING){ico.innerHTML='<rect x="5" y="4" width="4.5" height="16" rx="1.2" fill="#fff"/><rect x="14.5" y="4" width="4.5" height="16" rx="1.2" fill="#fff"/>';b.title=PLAYBUFFERING?'재생 준비 중':'일시정지';}
 else{ico.innerHTML='<path d="M6 4l12 8-12 8V4z" fill="#fff"/>';b.title='재생';}
 b.setAttribute('aria-label',b.title);
}
function setPlay(v,preserveClock=false){playing=v;if(v){PLAYENDED=false;if(!preserveClock)clock=FRAMES[idx]?framePlayTime(FRAMES[idx]):clock;last=performance.now();}renderPlayButton();}
function setPlaybackEnded(){playing=false;PLAYBUFFERING=false;PLAYENDED=true;renderPlayButton();}
function resetPlaybackToStart(){
 PLAYBUFSEQ++;PLAYBUFFERING=false;PLAYENDED=false;playing=false;
 idx=0;clock=FRAMES.length?framePlayTime(FRAMES[0]):0;last=performance.now();
 if(FRAMES.length){uploadPoints();trimVizCache(0);prefetchViz(0,true);document.getElementById('tbar').value=0;}
 renderPlayButton();
}
async function startBufferedPlayback(preserveClock=false){
 if(PLAYBUFFERING||!FRAMES.length)return;
 const seq=++PLAYBUFSEQ;PLAYBUFFERING=true;setPlay(false,true);
 if(!preserveClock)clock=FRAMES[idx]?framePlayTime(FRAMES[idx]):clock;
 const from=frameIndexAt(clock),old=document.getElementById('frSt').textContent;
 loadMsg('재생 버퍼 준비 중…');prefetchViz(from,true);
 while(seq===PLAYBUFSEQ&&!playbackBufferReady(from,1.5)){
  if(VSTREAMERR.has('frame-load')){
   PLAYBUFFERING=false;setPlay(false,true);loadMsg('프레임 '+FRAMES.length+'개');
   toast('재생 파일 읽기 실패 — 시각화 업데이트 후 다시 시도하세요',true);return;
  }
  await new Promise(r=>setTimeout(r,80));
 }
 if(seq!==PLAYBUFSEQ){PLAYBUFFERING=false;return;}
 PLAYBUFFERING=false;loadMsg(old.startsWith('재생 버퍼')?('프레임 '+FRAMES.length+'개'):old);
 if(!playbackBufferReady(from,.5)){setPlay(false,true);toast('재생 버퍼를 준비하지 못했습니다. 선택한 레이어 데이터를 확인하세요',true);return;}
 setPlay(true,true);
}
function togglePlay(){
 if(document.body.classList.contains('data-sheet-viewer'))return;
 if(loadFrames.busy){loadFrames.autoplay=true;toast('전체 데이터 로딩 후 자동 재생합니다');return;}
 if(!FRAMES.length){vizRun();return;}
 if(PLAYENDED){resetPlaybackToStart();startBufferedPlayback(false);return;}
 if(PLAYBUFFERING){PLAYBUFSEQ++;PLAYBUFFERING=false;setPlay(false,true);loadMsg('프레임 '+FRAMES.length+'개');return;}
 if(playing)setPlay(false,true);else startBufferedPlayback((typeof warehouseActive==='function'&&warehouseActive())||isTracerConfig(VIZCFG||CFG));
}
function changePlaybackSpeed(){const resume=playing||PLAYBUFFERING;PLAYBUFSEQ++;PLAYBUFFERING=false;setPlay(false,true);if(resume)startBufferedPlayback(true);saveUI(false);}
function scrub(v){PLAYBUFSEQ++;PLAYBUFFERING=false;idx=+v;clock=FRAMES[idx]?framePlayTime(FRAMES[idx]):0;PLAYENDED=FRAMES.length>0&&idx>=FRAMES.length-1;setPlay(false,true);uploadPoints();trimVizCache(idx);prefetchViz(idx,true);
 if(FRAMES.length)document.getElementById('tbar').value=idx;}

// ══════════════ 모드 전환 (CFD 실행 ↔ 시각화) — 자동 전환 없음, 항상 CFD로 시작 ══════════════
let MODE='cfd';
function setMode(m){
 MODE=m;
 document.body.classList.toggle('tracerView',m==='viz'&&isTracerConfig(VIZCFG||CFG));
 // Viewer에서 보관 프로젝트를 본 뒤 CFD로 돌아와도 그 프로젝트의 config가
 // 콘피그·에너지 수지에 남지 않도록 모드별 설정을 즉시 복원한다.
 if(m==='cfd'&&RUNCFG){const viewerConfig=VIZCFG;setConfig(RUNCFG);VIZCFG=viewerConfig;fillRunInputs(RUNCFG);}
 else if(m==='viz'){if(VIZCFG)setConfig(VIZCFG);else if(IMMERSIONCFG)setConfig(IMMERSIONCFG);}
 document.getElementById('mCFD').classList.toggle('on',m==='cfd');
 document.getElementById('mViz').classList.toggle('on',m==='viz');
 document.getElementById('secRun').style.display=m==='cfd'?'':'none';
 document.getElementById('secData').style.display=m==='viz'?'':'none';
 document.getElementById('viz').style.display=m==='viz'?'':'none';
 applyAnalysisTypeUI();
 if(m==='cfd'&&!isSiloConfig(CFG))setTimeout(()=>{drawSpark();drawVap();drawMetrics();},60);   // 크기 재계산
 else if(m==='viz'){setTimeout(resize,30);refreshVizInfo();}                 // 선택 프로젝트의 파일 상태를 즉시 반영
}
async function refreshVizInfo(){
 if(typeof warehouseActive==='function'&&warehouseActive()){return;}
 try{
  const r=vzrid(),i=await (await fetch('/api/info'+(r?('?rid='+encodeURIComponent(r)):''))).json();
  if(r!==vzrid()||MODE!=='viz'||document.body.classList.contains('warehouse-viewer'))return;
  srvFromInfo(i);renderProjects(i);updateSlots();
 }catch(_){}
}

// ══════════════ 해석 유형별 설정·출력 ══════════════
let SILOINFO=null;
function isSiloConfig(c){return !!(c&&c._해석유형==='grain_silo'&&c.silo);}
function runAxis(c,p){
 const steady=(p&&p.analysis==='grain_silo'&&p.solver==='simpleFoam')||
  (!p&&isSiloConfig(c)&&((c.openfoam_mapping||{}).solver||'simpleFoam')==='simpleFoam');
 return {steady,unit:steady?'회':'s',digits:steady?0:2};
}
function playbackDuration(c,p){
 const v=+(p&&p.playback_duration_s!=null?p.playback_duration_s:(((c||{}).run||{}).playback_duration_s??60));
 return Number.isFinite(v)&&v>.09?v:60;
}
function fmtPlaybackSeconds(v){return Number(v).toLocaleString(undefined,{maximumFractionDigits:2});}
function applyAnalysisTypeUI(){
 if(typeof warehouseActive==='function'&&warehouseActive()){return;}
 if(document.body.classList.contains('grouped')&&(MODE==='cfd'||document.body.classList.contains('warehouse-viewer')))return;
 const active=MODE==='viz'?(VIZCFG||CFG):CFG;
 if(isTracerConfig(active)){
  if(!document.body.classList.contains('grouped'))document.getElementById('appContext').textContent='가스 수송 CFD · 정규화 추적자';
  document.getElementById('dash').style.display=MODE==='cfd'?'flex':'none';
  configureOutputFields(CFG);configureViewerFields(VIZCFG||CFG);return;
 }
 const silo=isSiloConfig(MODE==='viz'?(VIZCFG||CFG):CFG);
 const setup=document.getElementById('immersionSetup');
 const context=document.getElementById('appContext');if(context&&!document.body.classList.contains('grouped'))context.textContent=(silo?'식량 저장고 CFD':'액침냉각 CFD')+' · __APP_VER__';
 const hTimeLabel=document.getElementById('hTimeLabel'),hTimeUnit=document.getElementById('hTimeUnit');
 if(hTimeLabel)hTimeLabel.textContent=silo?'재생':'t';if(hTimeUnit)hTimeUnit.textContent='s';
 if(setup)setup.style.display='flex';
 document.getElementById('dash').style.display=MODE==='cfd'?'flex':'none';
 const immersionCharts=document.querySelector('#dash .dgrid');if(immersionCharts)immersionCharts.style.display=silo?'none':'';
 for(const id of ['stVapW','stCoilW']){const e=document.getElementById(id);if(e)e.style.display=silo?'none':'';}
 configureOutputFields(CFG);
 configureViewerFields(VIZCFG||CFG);
}

// ══════════════ 현재 설정 창 ══════════════
let CFGSRC='아직 로딩 안 됨', ENVINFO=null;
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;');}
function escAttr(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');}
function polyAt(a,T){return Array.isArray(a)?a.reduce((s,v,i)=>s+(+v)*Math.pow(T,i),0):NaN;}
function tableAt(f,key,T){
 const x=f.T_K||[],y=f[key]||[];if(!x.length||x.length!==y.length)return Number(f[key+'_30C']??f[key]);
 if(T<=+x[0])return +y[0];if(T>=+x[x.length-1])return +y[y.length-1];
 for(let i=1;i<x.length;i++)if(T<=+x[i]){const q=(T-x[i-1])/(x[i]-x[i-1]);return +y[i-1]+q*(y[i]-y[i-1]);}
 return +y[y.length-1];
}
function sourceTableAt(f,key,T){
 const q=((f.property_tables||{})[key]||{}),x=q.T_K||[],y=q.values||[];
 if(!x.length||x.length!==y.length)return NaN;
 if(T<=+x[0])return +y[0];if(T>=+x[x.length-1])return +y[y.length-1];
 for(let i=1;i<x.length;i++)if(T<=+x[i]){const a=(T-x[i-1])/(x[i]-x[i-1]);return +y[i-1]+a*(y[i]-y[i-1]);}
 return +y[y.length-1];
}
function fluidRef(role,c){
 const lower=role==='lower',f=lower?(c.dielectric_fluid||{}):(c.water||{}),mp=f.manual_properties||{};
 if(Object.keys(mp).length)return {name:f.name||(lower?'하단 비전도 액체':'상단 액체'),manual:true,
  T:+mp.T_ref_C,rho:+mp.rho_kg_m3,cp:+mp.cp_J_kgK,mu:+mp.mu_Pa_s,k:+mp.kappa_W_mK,beta:+mp.beta_1_K};
 if(lower){const tk=+(f.Tsat_C??47)+273.15;
  if(f.property_tables){const rho=sourceTableAt(f,'rho',tk),r0=sourceTableAt(f,'rho',tk-1),r1=sourceTableAt(f,'rho',tk+1);
   return {name:f.name||'하단 비전도 액체',manual:false,T:tk-273.15,rho,cp:sourceTableAt(f,'cp',tk),mu:sourceTableAt(f,'mu',tk),k:sourceTableAt(f,'kappa',tk),beta:rho>0?-(r1-r0)/2/rho:0};}
  const rho=polyAt(f.rho_poly,tk),dr=Array.isArray(f.rho_poly)?f.rho_poly.reduce((s,v,i)=>i?s+i*(+v)*Math.pow(tk,i-1):s,0):NaN;
  return {name:f.name||'하단 비전도 액체',manual:false,T:tk-273.15,rho,cp:polyAt(f.cp_poly,tk),mu:polyAt(f.mu_poly,tk),k:polyAt(f.kappa_poly,tk),beta:isFinite(dr)&&rho>0?-dr/rho:0};}
 const tk=303.15,rho=tableAt(f,'rho',tk),r0=tableAt(f,'rho',tk-5),r1=tableAt(f,'rho',tk+5);
 return {name:f.name||'DI수',manual:false,T:30,rho,cp:tableAt(f,'cp',tk),mu:tableAt(f,'mu',tk),k:tableAt(f,'kappa',tk),beta:rho>0?-(r1-r0)/10/rho:0};
}
function resultEvidenceHtml(c){
 const silo=isSiloConfig(c),model=silo?'단상 저장고 · '+(c.openfoam_mapping?.solver||'솔버 기록 없음'):'액침냉각 · 설정 기반 해석';
 const units=silo?'속도 m/s · 압력 Pa · 난류 운동에너지 m²/s²':'온도 °C · 속도 m/s · 기포·상분율 무차원';
 const rows=[['연구 대상',c.research_target||'이 설정에 별도 기록 없음'],['계산 모델',model],
  ['결과 필드 단위',units],['수치 검사',c.performance?.pass===true?'저장본 검사 통과':'결과별 통과 기록 없음'],
  ['실험 비교','독립 실측 비교 기록 없음']];
 return '<div class="cgrp"><div class="ct">모델·검증 상태</div>'+rows.map(([label,value])=>
  '<div class="cr"><span>'+esc(label)+'</span><em>'+esc(value)+'</em><small></small></div>').join('')+'</div>';
}
async function showCfg(){
 const bg=document.getElementById('cfgBg'),body=document.getElementById('cfgBody');
 bg.style.display='flex';
 document.getElementById('cfgSrc').textContent='출처: '+CFGSRC;
 const runtime=document.getElementById('cfgRuntime'),rid=(PROJ||CURC||'');
 runtime.innerHTML='<div class="cr"><span>실행 환경</span><em>확인 중</em><small></small></div>';
 try{
  const q='?'+(rid?('rid='+encodeURIComponent(rid)+'&'):'')+'refresh=0';
  const r=await fetch('/api/settings'+q),j=await r.json();if(!r.ok||!j.ok)throw Error(j.msg||'환경 설정 조회 실패');
  STUDIOSET=j.settings||{};
  const s=STUDIOSET,a=s.raw_archive||{},mode=s.compute_mode_label||(s.pressure_solver_mode==='gpu_only'?'GPU Only (OpenCFD 개발)':(s.pressure_solver_mode==='gpu'?'CPU + GPU 병행':'CPU Only'));
  const detail=s.pressure_solver_mode==='gpu_only'?'OpenCFD std::execution GPU 오프로딩 · 단일 GPU · MPI 1개':(s.pressure_solver_mode==='gpu'?'OpenFOAM CPU 계산 · p_rgh 선형해석 GPU':'OpenFOAM 계산 · 압력 선형해석 CPU');
  runtime.innerHTML='<div class="cr"><span>계산 모드</span><em>'+esc(mode)+'</em><small></small></div>'+
   '<div class="cr"><span>실행 방식</span><em>'+esc(detail)+'</em><small></small></div>'+
   '<div class="cr"><span>CPU / MPI</span><em>CPU 상한 '+esc(s.cpu_pct)+'% · MPI '+esc(s.mpi_effective)+'개</em><small></small></div>';
 }catch(e){runtime.innerHTML='<div class="cr"><span>실행 환경</span><em>'+esc(e.message||'확인 실패')+'</em><small></small></div>';}
 if(!CFG){body.textContent='설정이 아직 로딩되지 않았습니다 — WSL 연결 또는 config.json 드롭 필요';return;}
 if(isTracerConfig(CFG)){showTracerSettings(body,CFG);return;}
 if(isSiloConfig(CFG)){
  const p=CFG.published||{},s=CFG.silo||{},m=CFG.mesh||{},om=CFG.openfoam_mapping||{},ctl=CFG.solver_controls||{},rn=CFG.run||{};
  const steady=(om.solver||'simpleFoam')==='simpleFoam';
  const runItems=steady?
   [['종료 기준',(rn.stop_mode||'fixed')==='converged'?'수렴 도달':'지정한 길이',''],[(rn.stop_mode||'fixed')==='converged'?'최대 반복 횟수':'목표 반복 횟수',rn.max_iterations??rn.end_time_s,'회'],['저장 반복 간격',rn.write_interval_iterations??rn.write_interval_s,'회'],['총 재생 시간',rn.playback_duration_s??60,'s']]:
   [['목표 해석 시간',rn.end_time_s,'s'],['계산 시간 간격',rn.time_step_s??rn.max_dt_s,'s'],['저장 시간 간격',rn.write_interval_s,'s']];
  const groups=[['해석',[['솔버',om.solver||'simpleFoam',''],['압력-속도',om.pressure_velocity_coupling||'SIMPLE',''],['난류',om.turbulence||'kEpsilon','']]],
   ['형상',[['전체 외경',p.outer_diameter_m,'m'],['전체 높이',p.total_height_m,'m'],['저장부 직경',p.storage_diameter_m,'m'],['저장부 높이',p.storage_height_m,'m'],['곡물 높이',p.grain_height_m,'m'],['하부 유입구 직경',p.bottom_central_duct_diameter_m,'m']]],
   ['유체·다공성',[['입구 속도',p.inlet_speed_m_s,'m/s'],['공기 밀도',p.rho_kg_m3,'kg/m³'],['공기 점성계수',p.mu_Pa_s,'Pa·s'],['곡물 공극률',p.grain_porosity,''],['Darcy d',p.darcy_d_1_m2,'1/m²'],['Forchheimer f',p.forchheimer_f_1_m,'1/m']]],
   ['덕트',[['A',s.design&&s.design.A,'mm'],['B',s.design&&s.design.B,'층'],['C',s.design&&s.design.C,'mm'],['D',s.design&&s.design.D,'개']]],
   ['계산',[['난류 강도',ctl.turbulence_intensity,''],['난류 길이',ctl.turbulence_length_scale_m,'m'],['수렴 기준',ctl.convergence_tolerance,''],['목표 격자',m.target_cells,'cells'],...runItems]]];
  let h='';for(const [g,items] of groups){h+='<div class="cgrp"><div class="ct">'+g+'</div>';for(const [label,value,unit] of items)h+='<div class="cr"><span>'+label+'</span><em>'+esc(value==null?'—':value)+'</em><small>'+unit+'</small></div>';h+='</div>';}body.innerHTML=resultEvidenceHtml(CFG)+h;return;
 }
 const c=CFG,air=(c.layers.air_mm!=null)?c.layers.air_mm:200;
 const d=c.dielectric_fluid||{},w=c.water||{},v=c.vapour||{},dl=fluidRef('lower',c),ul=fluidRef('upper',c),pc=c.phase_change||{},rn=c.run||{};
 const k=c.coil||{},m=c.mesh||{};
 const groups=[
  ['수조 (액체 영역)',[
   ['폭',c.tank.width_mm,'mm'],['깊이',c.tank.depth_mm,'mm'],['액체 높이',c.tank.liquid_height_mm,'mm'],['상단 공기층',air,'mm']]],
  ['층 구성·초기 온도',[
   ['하단 비전도 액체 높이',c.layers.dielectric_mm,'mm'],
   ['상단 액체 높이',c.tank.liquid_height_mm-c.layers.dielectric_mm,'mm'],
   ['하단 액체 초기 온도',c.layers.init_T_dielectric_C,'°C'],['상단 액체 초기 온도',c.layers.init_T_water_C,'°C']]],
  ['발열',[
   ['총 발열',c.heater.total_W,'W'],['발열 CPU 면 수',(c.heater.cpus||[]).length,'면']]],
  ['냉각 코일',[
   ['냉각수 유량',k.flow_LPM,'L/min'],['냉각수 입구 온도',k.Ta_C,'°C'],
   ['목표 UA',k.UA_target_W_K,'W/K'],['코일 모델 h',k.h_W_m2K,'W/m²K']]],
  ['상단 액체 물성',[
   ['액체 이름',ul.name,''],['기준 온도',ul.T,'°C'],['밀도',ul.rho,'kg/m³'],['비열',ul.cp,'J/kgK'],
   ['점성계수',ul.mu,'Pa·s'],['열전도도',ul.k,'W/mK'],['체적팽창계수',ul.beta,'1/K']]],
  ['하단 비전도 액체 물성',[
   ['액체 이름',dl.name,''],['기화점',d.Tsat_C,'°C'],['잠열',d.h_fg_J_kg,'J/kg'],['분자량',d.molWeight,'g/mol'],
   ['기준 온도',dl.T,'°C'],['밀도',dl.rho,'kg/m³'],['비열',dl.cp,'J/kgK'],['점성계수',dl.mu,'Pa·s'],
   ['열전도도',dl.k,'W/mK'],['체적팽창계수',dl.beta,'1/K']]],
  ['하단 액체 증기 물성',[
   ['비열',v.cp,'J/kgK'],['점성계수',v.mu,'Pa·s'],['열전도도',v.kappa,'W/mK']]],
  ['상변화·계면',[
   ['증발 C',pc.evap_C,'1/s'],['응축 C',pc.cond_C,'1/s'],['액체-증기 표면장력',d.sigma_lv,'N/m'],
   ['하단-상단 계면장력',d.sigma_lw,'N/m'],['증기-상단 계면장력',d.sigma_vw,'N/m']]],
  ['격자',[
   ['목표 셀 크기',m.dx_mm,'mm']]],
  ['계산 시간·데이터 추출',[
   ['총 계산 시간',rn.end_time_s,'s'],['데이터 추출 간격',rn.viz_interval_s,'s'],
   ['시간 간격 방식',(rn.time_step_mode||'adaptive')==='fixed'?'고정':'자동 안정',''],
   [(rn.time_step_mode||'adaptive')==='fixed'?'고정 시간 간격':'최대 시간 간격',rn.max_dt_s,'s'],
   ['최대 Courant',rn.maxCo,''],['최대 계면 Courant',rn.maxAlphaCo,'']]]
 ];
 let h='';
 for(const [g,items] of groups){h+='<div class="cgrp"><div class="ct">'+g+'</div>';
  for(const [label,value,unit] of items){
   const shown=(typeof value==='number'&&isFinite(value))?String(value):esc(value==null?'—':value);
   h+='<div class="cr"><span>'+label+'</span><em>'+shown+'</em><small>'+unit+'</small></div>';
  }
  h+='</div>';}
 body.innerHTML=resultEvidenceHtml(CFG)+h;
}

// 키보드: Space 재생/정지 · ←→ 프레임 이동
addEventListener('keydown',e=>{
 if(MODE!=='viz'||document.body.classList.contains('data-sheet-viewer'))return;
 const tag=(e.target.tagName||'').toUpperCase();
 if(['SELECT','INPUT','TEXTAREA','BUTTON','SUMMARY','A'].includes(tag)||e.target.isContentEditable||e.target.closest?.('dialog[open],button,summary,a,[contenteditable=true]'))return;
 if(e.code==='Space'){e.preventDefault();if(FRAMES.length)togglePlay();}
 else if(e.key==='ArrowRight'&&FRAMES.length){e.preventDefault();scrub(Math.min(FRAMES.length-1,idx+1));}
 else if(e.key==='ArrowLeft'&&FRAMES.length){e.preventDefault();scrub(Math.max(0,idx-1));}
});

// ══════════════ 스파크라인 ══════════════
const SCOL=['#3987e5','#d95926','#199e70','#c98500'];
function drawSpark(){
 const svg=document.getElementById('spark'); const Wp=svg.clientWidth||300, Hp=svg.clientHeight||96;
 svg.setAttribute('viewBox','0 0 '+Wp+' '+Hp);
 if(HIST.length<2){ svg.innerHTML='<text x="'+(Wp/2)+'" y="52" text-anchor="middle" fill="#898781" font-size="11">데이터 대기 중</text>'; return; }
 const rows=HIST.slice(-240);
 let lo=1e9,hi=-1e9; for(const r of rows) for(let i=1;i<=4;i++){lo=Math.min(lo,r[i]);hi=Math.max(hi,r[i]);}
 const pad=(hi-lo)*0.12+0.15; lo-=pad; hi+=pad;
 const t0=rows[0][0], t1=rows[rows.length-1][0]||1;
 const X=t=>8+(Wp-16)*(t-t0)/Math.max(t1-t0,1e-9), Y=v=>Hp-10-(Hp-22)*(v-lo)/(hi-lo);
 let g='';
 for(let gy=0;gy<3;gy++){const y=12+gy*(Hp-22)/2; g+='<line x1="8" y1="'+y+'" x2="'+(Wp-8)+'" y2="'+y+'" stroke="#2c2c2a" stroke-width="1"/>';}
 g+='<text x="'+(Wp-9)+'" y="11" text-anchor="end" fill="#898781" font-size="9">'+hi.toFixed(1)+'°</text>';
 g+='<text x="'+(Wp-9)+'" y="'+(Hp-3)+'" text-anchor="end" fill="#898781" font-size="9">'+lo.toFixed(1)+'°</text>';
 for(let s=1;s<=4;s++){
  let d=''; for(let i=0;i<rows.length;i++){ d+=(i?'L':'M')+X(rows[i][0]).toFixed(1)+' '+Y(rows[i][s]).toFixed(1)+' '; }
  g+='<path d="'+d+'" fill="none" stroke="'+SCOL[s-1]+'" stroke-width="2" stroke-linejoin="round"/>';
 }
 svg.innerHTML=g;
 const lastR=rows[rows.length-1];
 for(let s=1;s<=4;s++) document.getElementById('v'+s).textContent=lastR[s].toFixed(1)+'°';
 document.getElementById('chartT').textContent='t '+t0.toFixed(1)+'~'+t1.toFixed(1)+' s';
}

// ══════════════ 증기 부피 차트 ══════════════
let HISTV=[];
let METR=[];
function drawMini(id,pts,color,logscale,fmt){
 const svg=document.getElementById(id); if(!svg)return '';
 const W=svg.clientWidth||220,H=svg.clientHeight||64;
 svg.setAttribute('viewBox','0 0 '+W+' '+H);
 const ok=pts.filter(p=>isFinite(p[1])&&(!logscale||p[1]>0));
 if(ok.length<2){svg.innerHTML='<text x="'+(W/2)+'" y="'+(H/2+3)+'" text-anchor="middle" fill="#6b6b66" font-size="10">데이터 대기 중</text>';return '';}
 const f=v=>logscale?Math.log10(v):v;
 let lo=Infinity,hi=-Infinity; for(const p of ok){lo=Math.min(lo,f(p[1]));hi=Math.max(hi,f(p[1]));}
 if(hi-lo<1e-12){hi=lo+1;lo-=1;} else {const pad=(hi-lo)*0.12;hi+=pad;lo-=pad;}
 const t0=ok[0][0],t1=ok[ok.length-1][0];
 const X=t=>4+(W-8)*(t-t0)/Math.max(t1-t0,1e-12), Y=v=>H-6-(H-14)*(f(v)-lo)/(hi-lo);
 let g='';
 for(let i=0;i<3;i++){const y=7+i*(H-14)/2;g+='<line x1="4" y1="'+y+'" x2="'+(W-4)+'" y2="'+y+'" stroke="#2c2c2a"/>';}
 let d='M'+X(ok[0][0]).toFixed(1)+' '+Y(ok[0][1]).toFixed(1);
 for(let i=1;i<ok.length;i++)d+='L'+X(ok[i][0]).toFixed(1)+' '+Y(ok[i][1]).toFixed(1);
 g+='<path d="'+d+' L'+X(t1).toFixed(1)+' '+(H-6)+' L'+X(t0).toFixed(1)+' '+(H-6)+' Z" fill="'+color+'22"/>';
 g+='<path d="'+d+'" fill="none" stroke="'+color+'" stroke-width="1.7" stroke-linejoin="round"/>';
 g+='<text x="'+(W-5)+'" y="10" text-anchor="end" fill="#6b6b66" font-size="8.5">'+fmt(logscale?Math.pow(10,hi):hi)+'</text>';
 g+='<text x="'+(W-5)+'" y="'+(H-1)+'" text-anchor="end" fill="#6b6b66" font-size="8.5">'+fmt(logscale?Math.pow(10,lo):lo)+'</text>';
 svg.innerHTML=g;
 return fmt(ok[ok.length-1][1]);}
function fmtSci(v){ if(!isFinite(v))return '—';
 if(v===0)return '0';
 const e=Math.floor(Math.log10(Math.abs(v)));
 return (e<=-3||e>=4)?(v/Math.pow(10,e)).toFixed(1)+'e'+e:(Math.abs(v)>=10?v.toFixed(0):v.toFixed(Math.min(4,Math.max(1,2-e))));}
function drawMetrics(){
 const c=document.getElementById('metCard'); if(!c)return;
 const m=METR;
 if(!HASRUN||!m||m.length<2){c.style.display='none';return;}
 c.style.display='';
 const axis=runAxis(RUNCFG||CFG,LASTPROJS.find(x=>x.rid===(PROJ||CURC)));
 const grid=document.querySelector('#metCard .mgrid');
 if(grid){grid.children[0].style.display=axis.steady?'none':'';grid.children[1].style.display=axis.steady?'none':'';}
 const speedLabel=document.getElementById('mlSpeed');if(speedLabel)speedLabel.textContent=axis.steady?'계산 속도 (회 / 실제 h)':'계산 속도 (물리 s / 실제 h)';
 const sp=[];
 for(let i=4;i<m.length;i++){const dw=m[i][3]-m[i-4][3];
  if(dw>0)sp.push([m[i][0],(m[i][0]-m[i-4][0])/dw*3600]);}
 document.getElementById('mv1').textContent=drawMini('mc1',m.map(r=>[r[0],r[1]]),'#e0a03a',false,v=>fmtSci(v));
 const currentDt=drawMini('mc2',m.map(r=>[r[0],r[2]]),'#3987e5',true,v=>fmtSci(v));
 document.getElementById('mv2').textContent=currentDt;
 document.getElementById('mv3').textContent=drawMini('mc3',m.map(r=>[r[0],r[4]]),'#c76bd6',true,v=>fmtSci(v));
 document.getElementById('mv4').textContent=drawMini('mc4',sp,'#31c46a',false,v=>fmtSci(v));
 const el=document.getElementById('metT');
 if(el){
  let summary=(axis.steady?'반복 ':'t ')+m[0][0].toFixed(axis.steady?0:3)+'~'+m[m.length-1][0].toFixed(axis.steady?0:3)+' '+axis.unit+' · '+m.length+'스텝';
  if(!axis.steady){
   const dts=m.map(r=>r[2]).filter(v=>isFinite(v)&&v>0),avgDt=dts.length?dts.reduce((a,b)=>a+b,0)/dts.length:null;
   const rn=((RUNCFG||CFG)||{}).run||{},limit=+(rn.max_dt_s||0),fixed=(rn.time_step_mode||'adaptive')==='fixed';
   if(avgDt)summary+=' · 최근 평균 Δt '+fmtSci(avgDt)+'s';
   if(avgDt&&limit>0&&!fixed&&limit/avgDt>1.05)summary+=' · '+fmtSci(limit/avgDt)+'배 더 많은 계산 단계';
  }
  el.textContent=summary;
 }
}
function drawVap(){
 const svg=document.getElementById('vchart'); if(!svg)return;
 const Wp=svg.clientWidth||300, Hp=svg.clientHeight||96;
 svg.setAttribute('viewBox','0 0 '+Wp+' '+Hp);
 if(HISTV.length<2){svg.innerHTML='<text x="'+(Wp/2)+'" y="'+(Hp/2)+'" text-anchor="middle" fill="#898781" font-size="11">데이터 대기 중</text>';return;}
 const rows=HISTV.slice(-450);
 let hi=1; for(const r of rows)hi=Math.max(hi,r[1]); hi*=1.1;
 const t0=rows[0][0], t1=rows[rows.length-1][0]||1;
 const X=t=>8+(Wp-16)*(t-t0)/Math.max(t1-t0,1e-9), Y=v=>Hp-13-(Hp-28)*v/hi;
 let d='M'+X(rows[0][0]).toFixed(1)+' '+Y(rows[0][1]).toFixed(1);
 for(let i=1;i<rows.length;i++)d+='L'+X(rows[i][0]).toFixed(1)+' '+Y(rows[i][1]).toFixed(1);
 let g='';
 for(let gy=0;gy<3;gy++){const y=15+gy*(Hp-28)/2;g+='<line x1="8" y1="'+y+'" x2="'+(Wp-8)+'" y2="'+y+'" stroke="#2c2c2a"/>';}
 g+='<path d="'+d+' L'+X(t1).toFixed(1)+' '+(Hp-13)+' L'+X(t0).toFixed(1)+' '+(Hp-13)+' Z" fill="rgba(57,135,229,.16)"/>';
 g+='<path d="'+d+'" fill="none" stroke="#3987e5" stroke-width="2" stroke-linejoin="round"/>';
 g+='<text x="'+(Wp-9)+'" y="12" text-anchor="end" fill="#898781" font-size="9">'+hi.toFixed(0)+' mL</text>';
 svg.innerHTML=g;
 document.getElementById('vchartT').textContent='현재 '+rows[rows.length-1][1].toFixed(1)+' mL · t '+t0.toFixed(1)+'~'+t1.toFixed(1)+' s';
}

// ══════════════ 서버 연동 ══════════════
let CONDROWS=[],RUNPREF=false,NEWMODE=false,RESETREADY=false,RESUM=false,HASRUN=false; // RESETREADY=같은 프로젝트의 리셋 후 실행 전
async function newProj(){
 if(runBusyNow()){toast('실행 중에는 새 프로젝트를 만들 수 없습니다 — [중단] 후 진행하세요',true);return;}
 ++PROJGEN;NEWMODE=true;RESETREADY=false;PROJ='';setMode('cfd');
 if(HASPEND)renderProjects({cur:CURC,projects:LASTPROJS}); // 기존 실행 전 카드도 클릭 즉시 현재 선택으로 표시
 clearDash.done=false; clearDash();                       // 그래프·진행도 즉시 초기화
 for(const id of [...Object.values(OUTIDS),'cfgPick'])document.getElementById(id).disabled=false;
 updateConfigDeleteButton();
 const go=document.getElementById('btnGo'); if(go)go.disabled=true; // 서버 대기 카드가 확정되기 전 실행 경쟁 차단
 if(!HASPEND){                                            // 리스트에 새 항목 생성 (이미 있으면 그 항목을 이어서 편집)
  const d=new Date();
  const nm='새 프로젝트 '+(d.getMonth()+1)+'/'+d.getDate()+' '+String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0');
  await fetch('/api/proj-new',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:nm})});
  await refreshSrvInfo();
  renameProj('',nm);                                      // 바로 이름 입력
 }
 if(go)go.disabled=false;
 toast('새 프로젝트 — 설정을 조정한 뒤 [실행]을 누르세요');}
function applyProjSettings(rid){
 const p=LASTPROJS.find(x=>x.rid===rid); if(!p)return;
 if(CFG)fillRunInputs(CFG,true);                          // 1단계: config 기본값으로 전부 채움
 const st=p.settings||{};
 const ov=(id,v)=>{const el=document.getElementById(id); if(el&&v!=null&&v!=='')el.value=v;};
 ov('ovEnd',st.end_time_s!=null?st.end_time_s:p.end);     // 2단계: 이 프로젝트의 저장값만 덮어쓰기
 ov('ovViz',st.viz_interval_s); ov('ovWatt',st.total_W); ov('ovCoilUA',st.coil_UA);
 ov('ovLower',st.dielectric_mm);
 if(st.liquid_height_mm!=null&&st.dielectric_mm!=null)ov('ovUpper',+st.liquid_height_mm-(+st.dielectric_mm));
 if(Array.isArray(st.output_fields)){
  configureOutputFields(CFG,st.output_fields);
 }
}
function runBusyNow(){
 return !!(LASTST&&LASTST.running)||(LAUNCHT&&Date.now()-LAUNCHT<240000);}
function projectHasProgress(p){
 if(!p||p.pending)return false;
 const d=p.data||{};
 return (p.n||0)>0||(p.tmax||0)>0||(d.bubble||0)>0||(d.flow||0)>0||(d.therm||0)>0||(d.phase||0)>0||(d.pressure||0)>0||(d.turbulence||0)>0;
}
async function selectProj(rid,quiet){
 if(runBusyNow()){if(!quiet)toast('실행 중에는 프로젝트를 전환할 수 없습니다 — [중단] 후 이동하세요',true);return;}
 if(!NEWMODE&&(PROJ||CURC)===(rid||CURC))return;          // 같은 프로젝트 재클릭·더블클릭 → 상태 유지
 const selgen=++PROJGEN;
 NEWMODE=false;RESETREADY=false;PROJ=rid;SRVDIRTY=true;   // 만들던 새 프로젝트는 목록에 그대로 유지
 if(VPROJ==null){FRAMES=[];BUBLOADED=0;Cxyz=null;FLOWMAP={};THERMMAP={};PHASEMAP={};PRESSUREMAP={};TURBMAP={};} // 뷰어가 따로 보는 중이면 재생 상태 유지
 HIST=[];HISTV=[];HISTC=[];                               // 차트 이력도 프로젝트 단위로 분리 (섞임 방지)
 for(const id of ['spark','vchart'])document.getElementById(id).innerHTML='';
 document.getElementById('chartT').textContent='';document.getElementById('vchartT').textContent='';
 await refreshSrvInfo();
 if(selgen!==PROJGEN)return;
 const selected=LASTPROJS.find(x=>x.rid===rid);
 RESETREADY=!!(selected&&selected.reset_ready&&!projectHasProgress(selected));
 if(RESETREADY)NEWMODE=true;                              // 리셋 후에는 새 프로젝트와 같은 편집 화면
 if(selected&&selected.config_available){
  try{const cr=await (await fetch('/api/config?project='+encodeURIComponent(rid))).json();if(cr.ok&&cr.config){
   CFGREF='proj:'+rid;CFGFILE=(selected.name||rid)+' · '+(cr.name||'config.json');ACTIVE_CONFIG_FILE=null;
   setConfig(cr.config);fillRunInputs(cr.config,true);fillConds(cr.conditions||[]);renderSettings(CFGREF);CFGSRC='프로젝트 '+(selected.name||rid)+' / case_config.json';}}
  catch(_){}
 }
 try{                                                     // 프로젝트별 이력 로딩 — 현재=케이스 계측 · 보관=자체 보관본(없으면 프레임에서 복원)
  const cur2=(rid||CURC)===CURC;
  if(!cur2)chartNote('차트 이력 불러오는 중 — 첫 조회는 보관 프레임에서 복원하느라 수십 초 걸릴 수 있습니다');
  const h=await (await fetch('/api/history'+(cur2?'':'?proj='+encodeURIComponent(rid)))).json();
  if(selgen!==PROJGEN)return;
  HIST=h.probes||[];HISTV=h.vapor||[];HISTC=h.coil||[];
  DERIVED = !!h.derived; DERIVEDNOTE = h.derived_note||'';
  try{renderEnergy();}catch(_){}
  try{renderDerived();}catch(_){}
  if(HIST.length||HISTV.length){if(MODE==='cfd'){if(HIST.length)drawSpark();if(HISTV.length)drawVap();}}
  else if(!cur2)chartNote('보관 프로젝트 — 저장된 차트 이력이 없습니다 · 재생은 Viewer');
 }catch(_){}
 applyProjSettings(rid);                                  // 그 프로젝트의 저장 설정을 표시 (독립)
 if(LASTST)setStatus(LASTST);}                            // 선택 즉시 [실행] 버튼·잠금 반영
function goRun(){
 if(isTracerConfig(CFG)){toast('가스 수송 계산은 tracer_transport 실행기를 사용해 주세요. 이 프로젝트에서는 저장 결과를 재생할 수 있습니다.',true);return;}
 // NEWMODE는 UI 복원값이 남을 수 있으므로, 실제 대기 카드(PENDF)가 있을 때만
 // 새 프로젝트로 시작한다. 시작 중 실패해 카드만 남은 프로젝트는 아래의
 // 같은 프로젝트 0초 재시작 경로로 보낸다.
 if(RESETREADY){run('reset',{rid:PROJ||CURC});return;}
 const sel=LASTPROJS.find(x=>x.rid===(PROJ||CURC)&&!x.pending);
 const selCur=(!PROJ||PROJ===CURC);
 if(NEWMODE&&HASPEND){goFresh();return;}
 if(NEWMODE&&!HASPEND)NEWMODE=false;
 if(sel&&selCur&&RESUM&&!NEWMODE){                         // 중단 지점부터 재개
  run('resume',{end:sel.end||null});return;}
 if(sel&&projectHasProgress(sel)){                          // 진행 자료는 [실행]이 몰래 비우지 않음
  if(!selCur){
   confirmBox('보관 프로젝트 재개',
    '현재 프로젝트를 독립 보관한 뒤, 이 프로젝트의 case_config.json·격자·재시작 상태를 복원해 마지막 전체 저장 시점부터 이어서 계산합니다. 두 프로젝트의 설정과 Raw는 섞이지 않습니다.',
    '이 프로젝트 재개',()=>run('resume_archived',{rid:sel.rid,end:sel.end||null}));
  }else{
   // 화면의 순간 상태가 비었더라도 서버가 모든 MPI 파티션을 다시 검사한다.
   // 최신 저장이 불완전하면 직전 완전 저장(없으면 0초)으로 롤백해 같은 프로젝트를 재개한다.
   run('resume',{end:sel.end||null});
  }
  return;
 }
 if(sel&&selCur){                                          // 리셋 완료 상태 → 같은 프로젝트 ID·설정으로 새 계산
  run('reset',{rid:sel.rid});
  return;}
 if(!sel&&selCur){goFresh();return;}                       // 프로젝트가 하나도 없을 때만 새로 발급
 // 진행 표시가 없는 구버전 보관 프로젝트도 서버에서 원본·앵커를 검증한 뒤만 재개한다.
 const p=LASTPROJS.find(x=>x.rid===PROJ);
 confirmBox('보관 프로젝트 재개',
  '이 프로젝트의 보관 원본과 전체 저장 앵커를 검증한 뒤 독립 설정으로 전환해 재개합니다.',
  '이 프로젝트 재개',()=>run('resume_archived',{rid:p?p.rid:PROJ,end:p&&p.end||null}));}
function goReset(){
 if(isTracerConfig(CFG)){toast('가스 수송 원본은 보존합니다. 새 출력 폴더로 실행해 주세요.',true);return;}
 if(runBusyNow()){toast('실행 중에는 리셋할 수 없습니다 — [중단] 후 진행하세요',true);return;}
 if(NEWMODE){toast('새 프로젝트는 아직 초기 상태입니다 — [실행]으로 시작하세요',true);return;}
 const rid=PROJ||CURC, p=LASTPROJS.find(x=>x.rid===rid);
 if(!rid||!p){toast('리셋할 프로젝트가 없습니다 — [새 프로젝트]로 시작하세요',true);return;}
 confirmBox('리셋 — 0초 상태로 초기화',
  '프로젝트 "'+(p.name||rid)+'"의'+(p.n?(' 보관 프레임 '+p.n+'개와'):'')+' 케이스 진행 상태를 비웁니다.'
  +' 설정은 그대로 남고, 계산은 시작하지 않습니다 — 이후 [실행]을 누르면 저장된 설정으로 처음부터 계산합니다.',
  '리셋',async()=>{
 const r=await (await fetch('/api/reset',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rid})})).json();
   if(!r.ok){toast(r.msg||'리셋 실패',true);return;}
   HIST=[];HISTV=[];HISTC=[];clearDash.done=false;clearDash();
   if(VPROJ==null){FRAMES=[];BUBLOADED=0;Cxyz=null;FLOWMAP={};THERMMAP={};PHASEMAP={};PRESSUREMAP={};TURBMAP={};}
   SRVDIRTY=true;await refreshSrvInfo();
   PROJ=rid;RESETREADY=true;NEWMODE=true;
   const rp=LASTPROJS.find(x=>x.rid===rid);if(rp)rp.reset_ready=true;
   if(LASTST)setStatus(LASTST);                           // 긴 [실행]·입력 편집 상태를 즉시 반영
   clearTimeout(PTIMER);PTIMER=setTimeout(poll,600);
   toast('리셋 완료 — 진행 자료는 Trash에 30일 보관됩니다. [실행]으로 처음부터 시작하세요');});}
async function resetAndRun(rid){
 const r=await (await fetch('/api/reset',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rid})})).json();
 if(!r.ok){toast(r.msg||'실패 자료 보존 실패',true);return;}
 HIST=[];HISTV=[];HISTC=[];clearDash.done=false;clearDash();
 if(VPROJ==null){FRAMES=[];BUBLOADED=0;Cxyz=null;FLOWMAP={};THERMMAP={};PHASEMAP={};PRESSUREMAP={};TURBMAP={};}
 PROJ=rid;RESETREADY=true;NEWMODE=true;SRVDIRTY=true;
 await refreshSrvInfo();
 PROJ=rid;RESETREADY=true;NEWMODE=true;
 toast('실패 자료를 Trash에 보존했습니다 — 0초부터 실행합니다');
 await run('reset',{rid});
}
function validateRun(){
 if(selectedOutputList().length)return true;
 toast('출력 데이터를 1개 이상 선택해 주세요',true);return false;}
function goFresh(){
 if(!CFG){toast('현재 설정을 먼저 불러와 주세요',true);return;}
 if(!validateRun())return;
 if(RESUM)confirmBox('처음부터 새 계산을 시작할까요?',
  '격자 생성부터 새로 시작하며, 현재 케이스 폴더의 진행 데이터가 초기화됩니다.',
  '처음부터 실행',()=>run('fresh'));
 else run('fresh');}
function fillRunInputs(c,force){
 if((RUNPREF&&!force)||!c)return; RUNPREF=true;
 const r=c.run||{};
 const set=(id,v)=>{const el=document.getElementById(id); if(el&&v!=null)el.value=v;};
 set('ovViz',r.viz_interval_s); set('ovWrite',r.write_interval_s);
 set('ovEnd',r.end_time_s); set('ovWatt',c.heater&&c.heater.total_W);
 const pc2=c.phase_change||{},k2=c.coil||{},ly2=c.layers||{},m2=c.mesh||{};
 set('ovCoilUA',k2.UA_target_W_K);
 set('ovLower',ly2.dielectric_mm);
 if(c.tank&&c.tank.liquid_height_mm!=null&&ly2.dielectric_mm!=null)
  set('ovUpper',(+c.tank.liquid_height_mm)-(+ly2.dielectric_mm));
 let flow=k2.flow_LPM;
 if(flow==null&&Array.isArray(c.conditions)){
  const same=c.conditions.find(x=>x&&x.flow_LPM!=null&&Math.abs(+x.Ta_C-(+k2.Ta_C))<1e-9);
  if(same)flow=same.flow_LPM;
 }
 set('ovFlow',flow==null?'':flow);set('ovTa',k2.Ta_C);
 set('ovEvap',pc2.evap_C); set('ovCond',pc2.cond_C); set('ovCoilH',k2.h_W_m2K);
 set('ovDx',m2.dx_mm); set('ovInitD',ly2.init_T_dielectric_C); set('ovInitW',ly2.init_T_water_C);
 configureOutputFields(c,r.output_fields);
}
function fillConds(rows){CONDROWS=rows||[];updateSlots();} // 구형 프로젝트 condition→유량 복원용 내부 자료
// ══════════════ 정보 안내 창 ══════════════
function showInfo(){
 const e=document.getElementById('ifVer'), t=document.querySelector('.tag2');
 if(e&&t){const m=t.textContent.match(/v\d+/); if(m)e.textContent=m[0];}
 document.getElementById('infoBg').style.display='flex'; infoTab(INFOTAB); }
function closeInfo(){ document.getElementById('infoBg').style.display='none'; }
let INFOTAB=0;
function infoTab(i){ INFOTAB=i;
 for(let k=0;k<4;k++){
  document.getElementById('ifT'+k).classList.toggle('on',k===i);
  document.getElementById('ifB'+k).style.display=(k===i)?'':'none';
 }}
// ══════════════ PC별 환경 설정 ══════════════
let STUDIOSET=null;
async function showSettings(){
 const busy=runBusyNow();for(const id of ['setCpu','setMpi','setGpu','setPressureMode','setSave'])document.getElementById(id).disabled=busy;
 document.getElementById('settingsBg').style.display='flex';
 document.getElementById('setSummary').textContent='현재 PC의 CPU·GPU와 계산 환경을 확인 중입니다.';
 try{const r=await fetch('/api/settings?refresh=1'),j=await r.json();if(!r.ok||!j.ok)throw Error(j.msg||'설정 조회 실패');renderSettingsModal(j.settings);}
 catch(e){document.getElementById('setSummary').textContent=e.message||'설정을 읽지 못했습니다';}
}
function closeSettings(){document.getElementById('settingsBg').style.display='none';}
function renderSettingsModal(s){
 STUDIOSET=s||{};document.getElementById('setCpu').value=s.cpu_pct_setting||s.cpu_pct||60;
 const mpi=document.getElementById('setMpi');mpi.innerHTML='<option value="auto">자동</option>';
 for(let n=1;n<=+(s.cpu_logical||1);n++){const o=document.createElement('option');o.value=String(n);o.textContent=n+'개';mpi.appendChild(o);}
 mpi.value=String(s.mpi_np==null?'auto':s.mpi_np);
 document.getElementById('setMpiHint').textContent='논리 CPU '+(s.cpu_logical||'?')+'개 · 현재 '+(s.mpi_effective||'?')+'개 사용';
 const gpu=document.getElementById('setGpu');gpu.innerHTML='<option value="auto">자동 선택</option>';
 for(const g of (s.gpu_devices||[])){const o=document.createElement('option');o.value=String(g.index);o.textContent='GPU '+g.index+' · '+g.name+' · '+(g.memory_mib/1024).toFixed(0)+' GB';gpu.appendChild(o);}
 gpu.value=String(s.gpu_index==null?'auto':s.gpu_index);
 if(![...gpu.options].some(o=>o.value===gpu.value))gpu.value='auto';
 const modeSel=document.getElementById('setPressureMode'),gpuOnly=s.gpu_only||{},gpuOpt=[...modeSel.options].find(o=>o.value==='gpu_only');
 if(gpuOpt)gpuOpt.disabled=!gpuOnly.ready&&s.pressure_solver_mode!=='gpu_only';
 modeSel.value=['cpu','gpu','gpu_only'].includes(s.pressure_solver_mode)?s.pressure_solver_mode:'cpu';
 document.getElementById('setGpuOnlyHint').textContent=gpuOnly.ready?'GPU Only 준비 완료 · 선택 GPU 1개와 MPI 1개 사용':'GPU Only 사용 불가 · '+(gpuOnly.message||'전용 실행 환경 확인 필요');
 const sm=s.compute_mode_label||(s.pressure_solver_mode==='gpu_only'?'GPU Only':(s.pressure_solver_mode==='gpu'?'CPU + GPU 병행':'CPU Only'));
 document.getElementById('setSummary').textContent='현재 적용: '+sm+' · MPI '+(s.mpi_effective||'?')+'개 · GPU '+(s.gpu_effective??'없음');
}
async function saveSettings(){
 if(runBusyNow()){toast('실행 중에는 설정을 할 수 없습니다',true);return;}
 const btn=document.getElementById('setSave');btn.disabled=true;
 const body={cpu_pct:+document.getElementById('setCpu').value,mpi_np:document.getElementById('setMpi').value,
  gpu_index:document.getElementById('setGpu').value,pressure_solver_mode:document.getElementById('setPressureMode').value};
 try{const r=await fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),j=await r.json();
  if(!r.ok||!j.ok){toast(j.msg||'환경 설정을 저장하지 못했습니다',true);return;}renderSettingsModal(j.settings);closeSettings();toast('환경 설정을 저장했습니다 · 계산 자원은 다음 시작부터 적용됩니다');
 }catch(_){toast('환경 설정 저장 중 서버 응답이 끊겼습니다',true);}finally{btn.disabled=false;}
}

// ══════════════ config.json 생성 창 ══════════════
// config.json 을 손으로 편집하지 않고 값만 채워 새 설정을 만든다.
// 유체 대표 물성을 바꾸면 build_case.py가 OpenFOAM icoTabulated 표로 직접 생성한다.
let CBSAVING=false,CBFORMTYPE='',CBDRAFTS={},CBBASES=null,CBSAVECONTEXT=null;
function cbBase(type){
 if(CBBASES)return CBBASES[type];
 return type==='grain_silo'?(isSiloConfig(CFG)?CFG:(SILOINFO||{}).config):(isSiloConfig(CFG)?IMMERSIONCFG:CFG);
}
function cbFieldKey(el){
 if(el.id)return 'id:'+el.id;
 const d=el.dataset;
 if(d.g)return 'field:'+d.g+'.'+d.k;
 if(d.fp)return 'fluid:'+d.fp+'.'+d.p;
 if(d.fname)return 'name:'+d.fname;
 return 'weight:'+d.fmw;
}
function captureCBDraft(){
 return {values:Object.fromEntries([...document.querySelectorAll('#cbForm input, #cbForm select')].map(el=>[cbFieldKey(el),el.value])),dataset:{...document.getElementById('cbForm').dataset}};
}
function restoreCBDraft(draft){
 if(!draft)return;
 for(const el of document.querySelectorAll('#cbForm input, #cbForm select')){
  const key=cbFieldKey(el);if(Object.hasOwn(draft.values,key))el.value=draft.values[key];
 }
 Object.assign(document.getElementById('cbForm').dataset,draft.dataset);
 if(CBFORMTYPE==='grain_silo')updateSiloRunFields();else updateImmersionTimeStepFields();
}
function renderCBForm(){
 if(CBSAVING)return;
 if(CBFORMTYPE)CBDRAFTS[CBFORMTYPE]=captureCBDraft();
 const selected=document.getElementById('cbType'),type=selected.value;
 if(type==='warehouse'){
  selected.value=CBFORMTYPE||'immersion';
  if(confirm('저장고 형상 화면으로 이동할까요? 저장하지 않은 설정은 보관되지 않습니다.'))location.href='/warehouse';
  return;
 }
 CBFORMTYPE=type;
 const host=document.getElementById('cbForm');for(const key of Object.keys(host.dataset))delete host.dataset[key];
 buildCBForm();restoreCBDraft(CBDRAFTS[type]);
}
function cbNumber(id,label,{integer=false}={}){
 const text=document.getElementById(id).value.trim(),v=Number(text);
 if(!text||!Number.isFinite(v))throw Error(label+' 값을 입력해 주세요');
 if(integer&&!Number.isInteger(v))throw Error(label+'은 정수로 입력해 주세요');
 return v;
}
const CBDEF=[
 ['tank','수조 (액체 영역)','실물 내부 치수 중 액체가 차는 부분만 격자화합니다',
  [['width_mm','폭','mm',456],['depth_mm','깊이','mm',70],['liquid_height_mm','액체 높이','mm',800]]],
 ['layers','층 구성·초기 온도','두 층 모두 등온으로 시작합니다. 아래가 위보다 뜨거우면 자동으로 등온화됩니다',
  [['dielectric_mm','하단 비전도 액체 높이','mm',400],['air_mm','상단 공기층 (표시 전용)','mm',200],
   ['init_T_dielectric_C','하단 액체 초기 온도','°C',46.9],['init_T_water_C','상단 액체 초기 온도','°C',32.0]]],
 ['heater','발열','CPU 면에 총 발열을 면적비로 분배합니다',
  [['total_W','총 발열','W',265]]],
 ['coil','냉각 코일','OpenFOAM 경계에는 입구 온도와 UA/h가 적용됩니다. 유량은 T6 출구온도 환산과 기록에 사용합니다',
  [['flow_LPM','냉각수 유량 (T6 환산)','L/min',14.67],['Ta_C','냉각수 입구 온도','°C',20],
   ['UA_target_W_K','목표 UA','W/K',21.7],['h_W_m2K','코일 모델 h','W/m²K',3926.9]]],
 ['dielectric_fluid','상변화·계면','하단 액체의 기화와 세 상 사이 계면장력을 입력합니다',
  [['Tsat_C','기화점','°C',47.0],['h_fg_J_kg','잠열','J/kg',93220],['molWeight','분자량 (증기 밀도)','g/mol',300.05],['sigma_lv','표면장력 (액-증기)','N/m',0.01144],
   ['sigma_lw','계면장력 (하단-상단)','N/m',0.045],['sigma_vw','계면장력 (증기-상단)','N/m',0.055]]],
 ['vapour','하단 액체 증기 물성','증기는 하단 비전도 액체에서 발생하며, 밀도는 위 분자량과 1 atm 이상기체식으로 계산합니다',
  [['cp','증기 비열 cₚ','J/kgK',868],['mu','증기 점성계수 μ','Pa·s',0.00010926],['kappa','증기 열전도도 k','W/mK',0.0131]]],
 ['phase_change','상변화 (Lee 계수)','증발 > 0, 응축 < 0. 과열 완화 시상수 = Tsat·cp/(C·h_fg)',
  [['evap_C','증발 C','1/s',50],['cond_C','응축 C','1/s',-50]]],
 ['mesh','격자','작을수록 정확하지만 셀 수는 세제곱으로 늘어납니다',
  [['dx_mm','목표 셀 크기','mm',3.0]]],
 ['run','계산 시간·데이터 추출','',
  [['end_time_s','총 계산 시간','s',60],
   ['write_interval_s','전체 상태 저장 간격','s',null],
   ['viz_interval_s','데이터 추출 간격','s',0.1],['max_dt_s','최대 시간간격','s',0.002],
   ['maxCo','최대 Courant','',0.5],['maxAlphaCo','최대 계면 Courant','',0.5]]],
];
function updateImmersionTimeStepFields(){
 const mode=document.getElementById('cbTimeStepMode'),label=document.getElementById('cbRunDtLabel'),note=document.getElementById('cbTimeStepNote');
 if(!mode||!label)return;
 const fixed=mode.value==='fixed';
 const end=+document.querySelector('#cbForm input[data-g="run"][data-k="end_time_s"]')?.value;
 const dt=+document.querySelector('#cbForm input[data-g="run"][data-k="max_dt_s"]')?.value;
 const steps=end>0&&dt>0?Math.ceil(end/dt):null,stepText=steps?steps.toLocaleString()+'단계':'';
 if(label.childNodes.length)label.childNodes[0].nodeValue=fixed?'고정 시간 간격':'최대 시간 간격';
 if(note)note.textContent=fixed?('입력한 Δt를 정확히 유지합니다.'+(stepText?' 계산량 '+stepText+'.':'')+' Courant 수가 커지면 계산이 불안정해질 수 있습니다.')
  :('입력값은 상한입니다.'+(stepText?' 최소 '+stepText+'이며 실제는 더 많습니다.':'')+' 실제 Δt는 Courant 안정성에 따라 더 작아지며, 예상 소요시간은 실측 속도로 계산됩니다.');
}
function fluidEditorHTML(role,title,baseCfg){
 const srcCfg=baseCfg||CFG,q=fluidRef(role,srcCfg),path=role==='lower'?'dielectric_fluid':'water',raw=role==='lower'?(srcCfg.dielectric_fluid||{}):(srcCfg.water||{});
 const rows=[['T','기준 온도','°C',q.T],['rho','밀도 ρ','kg/m³',q.rho],['cp','비열 cₚ','J/kgK',q.cp],
  ['mu','점성계수 μ','Pa·s',q.mu],['k','열전도도 k','W/mK',q.k],['beta','체적팽창계수 β','1/K',q.beta]];
 let h='<div class="cbg" data-fluid="'+role+'"><div class="t">'+title+'</div><div class="n">'+
  '기준 온도의 대표값을 입력합니다. ρ는 β로 온도 의존성을 만들고 cₚ·μ·k는 대표값으로 OpenFOAM 물성표에 기록합니다. '+(role==='upper'?'상단 액체는 현재 3상 모델에서 기화하지 않는 액상으로 계산합니다. ':'')+
  (q.manual?'현재 사용자 입력 물성이 적용 중입니다.':'값을 바꾸지 않으면 기존 온도 의존 물성표를 그대로 유지합니다.')+'</div>'+
  '<div class="cbr"><label>액체 이름<i>'+path+'.name</i></label><input type="text" data-fname="'+role+'" value="'+escAttr(q.name)+'" style="text-align:left"><span class="u"></span></div>';
 if(role==='upper')h+='<div class="cbr"><label>분자량<i>water.molWeight</i></label><input type="number" step="any" data-fmw="upper" value="'+(raw.molWeight??18.01528)+'"><span class="u">g/mol</span></div>';
 for(const [key,label,unit,val] of rows){const v=isFinite(val)?Number(val).toPrecision(8):'';
  h+='<div class="cbr"><label>'+label+'<i>'+path+'.manual_properties</i></label><input type="number" step="any" data-fp="'+role+'" data-p="'+key+'" data-base="'+v+'" value="'+v+'"><span class="u">'+unit+'</span></div>';}
 return h+'</div>';
}
function updateSiloRunFields(){
 const host=document.getElementById('cbForm'),sel=document.getElementById('cbSiloSolver');if(!host||!sel)return;
 const solver=sel.value,prev=host.dataset.runSolver;
 const val=id=>document.getElementById(id)?.value;
 if(prev&&prev!==solver){
  if(prev==='simpleFoam'){host.dataset.steadyEnd=val('cbSiloEnd');host.dataset.steadyWrite=val('cbSiloWrite');}
  else{host.dataset.transientEnd=val('cbSiloEnd');host.dataset.transientWrite=val('cbSiloWrite');host.dataset.transientDt=val('cbSiloDt');}
  document.getElementById('cbSiloEnd').value=solver==='simpleFoam'?host.dataset.steadyEnd:host.dataset.transientEnd;
  document.getElementById('cbSiloWrite').value=solver==='simpleFoam'?host.dataset.steadyWrite:host.dataset.transientWrite;
  if(solver!=='simpleFoam')document.getElementById('cbSiloDt').value=host.dataset.transientDt;
 }
 const steady=solver==='simpleFoam',stop=document.getElementById('cbSiloStop'),converged=steady&&stop&&stop.value==='converged';
 if(stop){stop.disabled=!steady;stop.closest('.cbr').style.display=steady?'flex':'none';}
 document.getElementById('cbSiloEndLabel').textContent=steady?(converged?'최대 반복 횟수':'목표 반복 횟수'):'목표 해석 시간';
 document.getElementById('cbSiloEndUnit').textContent=steady?'회':'s';
 document.getElementById('cbSiloWriteLabel').textContent=steady?'저장 반복 간격':'저장 시간 간격';
 document.getElementById('cbSiloWriteUnit').textContent=steady?'회':'s';
 document.getElementById('cbSiloDtRow').style.display=steady?'none':'flex';
 document.getElementById('cbSiloPlaybackRow').style.display=steady?'flex':'none';
 host.dataset.runSolver=solver;
}
function buildCBForm(){
 const type=document.getElementById('cbType').value,host=document.getElementById('cbForm');host.innerHTML='';
 if(type==='grain_silo'){
  document.getElementById('cbHint').textContent='식량 저장고 CFD 설정을 새 프리셋으로 저장합니다.';
  const sc=((SILOINFO||{}).config||{}),base=cbBase('grain_silo')||{},p=base.published||sc.published||{},m=base.mesh||sc.mesh||{},om=base.openfoam_mapping||sc.openfoam_mapping||{},ctl=base.solver_controls||sc.solver_controls||{},run=base.run||sc.run||{},design=(base.silo||{}).design||{A:20,B:12,C:5,D:6};
  const domain=sc.design_domains||base.design_domains||{},opts=(values,selected)=>(values||[]).map(v=>'<option value="'+v+'"'+(String(v)===String(selected)?' selected':'')+'>'+v+'</option>').join('');
  const solverOpts=Object.entries(sc.solver_options||base.solver_options||{}).map(([v,x])=>'<option value="'+v+'"'+(v===(om.solver||'simpleFoam')?' selected':'')+'>'+esc(x.label||v)+'</option>').join('');
  const turbulenceOpts=(sc.turbulence_options||base.turbulence_options||['kEpsilon']).map(v=>'<option value="'+v+'"'+(v===(om.turbulence||'kEpsilon')?' selected':'')+'>'+v+'</option>').join('');
  const steady=(om.solver||'simpleFoam')==='simpleFoam';
  const steadyEnd=run.max_iterations??(steady?run.end_time_s:1000),steadyWrite=run.write_interval_iterations??(steady?run.write_interval_s:100);
  const transientEnd=steady?(run.transient_end_time_s??10):(run.end_time_s??10),transientWrite=steady?(run.transient_write_interval_s??.1):(run.write_interval_s??.1),transientDt=run.time_step_s??run.max_dt_s??.01;
  const row=(id,label,value,unit)=>'<div class="cbr" id="'+id+'Row"><label id="'+id+'Label">'+label+'</label><input id="'+id+'" type="number" step="any" value="'+value+'"><span class="u" id="'+id+'Unit">'+(unit||'')+'</span></div>';
  host.innerHTML='<div class="cbg"><div class="t">해석</div><div class="cbr"><label>유동 솔버</label><select id="cbSiloSolver">'+solverOpts+'</select><span class="u"></span></div><div class="cbr"><label>난류 모델</label><select id="cbSiloTurbulence">'+turbulenceOpts+'</select><span class="u"></span></div></div>'+
   '<div class="cbg"><div class="t">형상</div>'+row('cbSiloOuterD','전체 외경',p.outer_diameter_m??1,'m')+row('cbSiloTotalH','전체 높이',p.total_height_m??1.4,'m')+row('cbSiloStorageD','저장부 직경',p.storage_diameter_m??.8,'m')+row('cbSiloStorageH','저장부 높이',p.storage_height_m??1.2,'m')+row('cbSiloGrainH','곡물 높이',p.grain_height_m??1,'m')+row('cbSiloDuctD','하부 유입구 직경',p.bottom_central_duct_diameter_m??.3,'m')+'</div>'+
   '<div class="cbg"><div class="t">유체·다공성</div>'+row('cbSiloInlet','입구 속도',p.inlet_speed_m_s??3,'m/s')+row('cbSiloRho','공기 밀도',p.rho_kg_m3??1.177,'kg/m³')+row('cbSiloMu','공기 점성계수',p.mu_Pa_s??.0000185,'Pa·s')+row('cbSiloParticle','곡물 평균 입경',p.grain_particle_diameter_m??.00782,'m')+row('cbSiloPorosity','곡물 공극률',p.grain_porosity??.411,'')+row('cbSiloDarcy','Darcy d',p.darcy_d_1_m2??12256963.1,'1/m²')+row('cbSiloForch','Forchheimer f',p.forchheimer_f_1_m??3797.1,'1/m')+'</div>'+
   '<div class="cbg"><div class="t">덕트</div><div class="fgrid"><label class="fld">A 순환입구 (mm)<select id="cbSiloA">'+opts(domain.A_mm||[10,15,20,25,30],design.A??20)+'</select></label><label class="fld">B 덕트 층수<select id="cbSiloB">'+opts(domain.B_layers||[10,11,12,13,14],design.B??12)+'</select></label><label class="fld">C 하부 개구 (mm)<select id="cbSiloC">'+opts(domain.C_mm||[4,5,6,7,8],design.C??5)+'</select></label><label class="fld">D 하부 개수<select id="cbSiloD">'+opts(domain.D_count||[4,5,6,7,8],design.D??6)+'</select></label></div></div>'+
   '<div class="cbg"><div class="t">계산</div><div class="cbr"><label>종료 기준</label><select id="cbSiloStop"><option value="converged"'+((run.stop_mode||'fixed')==='converged'?' selected':'')+'>수렴 도달 (최대 길이 상한)</option><option value="fixed"'+((run.stop_mode||'fixed')!=='converged'?' selected':'')+'>지정한 길이</option></select><span class="u"></span></div>'+row('cbSiloIntensity','난류 강도',ctl.turbulence_intensity??.05,'')+row('cbSiloLength','난류 길이',ctl.turbulence_length_scale_m??.05,'m')+row('cbSiloTolerance','수렴 잔차 기준',ctl.convergence_tolerance??1e-6,'')+row('cbSiloCells','목표 격자 수',m.target_cells??1056000,'cells')+row('cbSiloEnd',steady?'목표 반복 횟수':'목표 해석 시간',steady?steadyEnd:transientEnd,steady?'회':'s')+row('cbSiloDt','계산 시간 간격',transientDt,'s')+row('cbSiloWrite',steady?'저장 반복 간격':'저장 시간 간격',steady?steadyWrite:transientWrite,steady?'회':'s')+row('cbSiloPlayback','총 재생 시간',run.playback_duration_s??60,'s')+'</div>';
  Object.assign(host.dataset,{runSolver:om.solver||'simpleFoam',steadyEnd,steadyWrite,transientEnd,transientWrite,transientDt});
  document.getElementById('cbSiloSolver').addEventListener('change',updateSiloRunFields);document.getElementById('cbSiloStop').addEventListener('change',updateSiloRunFields);updateSiloRunFields();
  return;
 }
 document.getElementById('cbHint').textContent='현재 액침냉각 설정을 복제해 새 config.json으로 저장합니다.';
 const base=cbBase('immersion');
 if(!base){host.innerHTML='<div class="cbg"><div class="n">액침냉각 기본 설정을 불러오지 못했습니다.</div></div>';return;}
 for(const [grp,title,note,fields] of CBDEF){
  const src=base[grp]||{};let h='<div class="cbg"><div class="t">'+title+'</div>';
  if(note)h+='<div class="n">'+note+'</div>';
  if(grp==='run')h+='<div class="cbr"><label>시간 간격 방식<i>run.time_step_mode</i></label><select id="cbTimeStepMode"><option value="adaptive"'+((src.time_step_mode||'adaptive')==='adaptive'?' selected':'')+'>자동 안정</option><option value="fixed"'+(src.time_step_mode==='fixed'?' selected':'')+'>고정</option></select><span class="u"></span></div><div class="n" id="cbTimeStepNote"></div>';
  for(const [key,label,unit,dflt] of fields){const v=(src[key]!=null)?src[key]:(dflt!=null?dflt:''),lid=(grp==='run'&&key==='max_dt_s')?' id="cbRunDtLabel"':'';h+='<div class="cbr"><label'+lid+'>'+label+'<i>'+grp+'.'+key+'</i></label><input type="number" step="any" data-g="'+grp+'" data-k="'+key+'" data-l="'+label+'" value="'+v+'"><span class="u">'+(unit||'')+'</span></div>';}
  host.insertAdjacentHTML('beforeend',h+'</div>');
  if(grp==='dielectric_fluid')host.insertAdjacentHTML('beforeend',fluidEditorHTML('upper','상단 액체 물성',base)+fluidEditorHTML('lower','하단 비전도 액체 물성',base));
 }
 const timeStepMode=document.getElementById('cbTimeStepMode');if(timeStepMode){
  timeStepMode.addEventListener('change',updateImmersionTimeStepFields);
  for(const key of ['end_time_s','max_dt_s'])document.querySelector('#cbForm input[data-g="run"][data-k="'+key+'"]')?.addEventListener('input',updateImmersionTimeStepFields);
  updateImmersionTimeStepFields();
 }
}
async function openCB(){
 if(CBSAVING)return;
 if(isTracerConfig(CFG)){toast('가스 수송 설정은 실행 JSON에서 변경해 주세요. 기존 결과의 설정은 유지됩니다.',true);return;}
 if(runBusyNow()){toast('실행 중에는 설정을 할 수 없습니다',true);return;}
 if(CFGLOAD){
  const loaded=await CFGLOAD;
  if(!loaded)return;
 }
 const selected=document.getElementById('cfgPick');
 // 프로젝트 전용 설정(proj:)은 프리셋 목록에 없으므로 select 값이 비어 있다.
 // 이를 불일치로 보고 기본 설정을 다시 읽으면, +버튼만 눌러도 현재 프로젝트 화면이 바뀐다.
 const listedRef=CFGREF===''||CFGREF.startsWith('cfg:');
 if(selected&&listedRef&&selected.value!==CFGREF){          // 목록형 프리셋일 때만 선택값을 다시 확정
  const loaded=await settingChanged();if(!loaded)return;
 }
 if(!CFG){toast('설정이 아직 로딩되지 않았습니다 — 기본 설정을 먼저 확인하세요',true);return;}
 if(!SILOINFO){try{SILOINFO=await (await fetch('/api/silo/info')).json();}catch(_){}}
 // 편집 중 뒤늦게 다른 설정 조회가 끝나도 복제 원본은 바꾸지 않는다.
 CBBASES=JSON.parse(JSON.stringify({immersion:isSiloConfig(CFG)?IMMERSIONCFG:CFG,grain_silo:isSiloConfig(CFG)?CFG:((SILOINFO||{}).config||{})}));
 CBDRAFTS={};CBFORMTYPE='';
 document.getElementById('cbType').value=isSiloConfig(CFG)?'grain_silo':'immersion';
 renderCBForm();
 const n=document.getElementById('cbName');
 if(!n.value){const d=new Date();
  n.value='설정 '+(d.getMonth()+1)+'/'+d.getDate()+' '+String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0');}
 document.getElementById('cbBg').style.display='flex';
}
function closeCB(force=false){ if(!CBSAVING||force)document.getElementById('cbBg').style.display='none'; }
function preserveSelectedProjectConfig(){
 const rid=PROJ||CURC;
 return !NEWMODE&&!!rid&&LASTPROJS.some(p=>p.rid===rid&&!p.pending);
}
function finishConfigSave(r,out,conditionRows){
 SAVEDCFG=r.list||[];SAVEDCFGTYPES=r.types||SAVEDCFGTYPES;
 const saved=(r.config&&typeof r.config==='object')?r.config:out;
 const changedContext=CBSAVECONTEXT&&CBSAVECONTEXT!==JSON.stringify([PROJ,CURC,NEWMODE,CFGREF]);
 const savedFile=r.saved+'.json',preserve=preserveSelectedProjectConfig()||changedContext;
 if(!preserve){
  CFGREF='cfg:'+r.saved;CFGFILE=savedFile;ACTIVE_CONFIG_FILE=null;CFGSRC='생성한 '+CFGFILE;
  setConfig(saved);fillRunInputs(saved,true);
  if(Array.isArray(conditionRows))fillConds(conditionRows,'');
 }
 renderSettings(CFGREF);
 document.getElementById('cbName').value='';closeCB(true);CBDRAFTS={};
 toast(savedFile+' 설정을 저장했습니다'+(preserve?' · 선택 프로젝트는 변경하지 않았습니다':' · 새 프로젝트에 적용했습니다')
  +(r.geometry_revised?' · 보드와 CPU를 바닥 기준으로 수정했습니다':''));
}
async function saveCB(){
 if(CBSAVING)return;
 if(runBusyNow()){toast('실행 중에는 설정을 할 수 없습니다',true);return;}
 CBSAVING=true;CBSAVECONTEXT=JSON.stringify([PROJ,CURC,NEWMODE,CFGREF]);
 const controls=[...document.querySelectorAll('#cbBg input, #cbBg select, #cbBg button')].map(el=>[el,el.disabled]);
 for(const [el] of controls)el.disabled=true;
 const button=document.getElementById('cbSave');button.textContent='저장 중';
 try{await saveCBInput();}
 catch(e){toast('저장 실패: '+(e.message||'연결 상태를 확인해 주세요'),true);}
 finally{
  CBSAVING=false;CBSAVECONTEXT=null;
  for(const [el,disabled] of controls)el.disabled=disabled;
  button.textContent='설정 저장';
 }
}
async function saveCBInput(){
 const name=document.getElementById('cbName').value.trim();
 if(!name){toast('설정 이름을 입력하세요',true);return;}
 if(document.getElementById('cbType').value==='grain_silo'){
  const base=cbBase('grain_silo')||{},design={
   A:+document.getElementById('cbSiloA').value,B:+document.getElementById('cbSiloB').value,
   C:+document.getElementById('cbSiloC').value,D:+document.getElementById('cbSiloD').value};
  const number=cbNumber;
  let out;
  try{
   out=JSON.parse(JSON.stringify(base));out._해석유형='grain_silo';out.schema_version=3;
   out.openfoam_mapping=out.openfoam_mapping||{};out.openfoam_mapping.solver=document.getElementById('cbSiloSolver').value;out.openfoam_mapping.turbulence=document.getElementById('cbSiloTurbulence').value;
   out.published=out.published||{};Object.assign(out.published,{outer_diameter_m:number('cbSiloOuterD','전체 외경'),total_height_m:number('cbSiloTotalH','전체 높이'),storage_diameter_m:number('cbSiloStorageD','저장부 직경'),storage_height_m:number('cbSiloStorageH','저장부 높이'),grain_height_m:number('cbSiloGrainH','곡물 높이'),bottom_central_duct_diameter_m:number('cbSiloDuctD','하부 유입구 직경'),inlet_speed_m_s:number('cbSiloInlet','입구 속도'),rho_kg_m3:number('cbSiloRho','공기 밀도'),mu_Pa_s:number('cbSiloMu','공기 점성계수'),grain_particle_diameter_m:number('cbSiloParticle','곡물 입경'),grain_porosity:number('cbSiloPorosity','곡물 공극률'),darcy_d_1_m2:number('cbSiloDarcy','Darcy d'),forchheimer_f_1_m:number('cbSiloForch','Forchheimer f')});
   out.solver_controls={turbulence_intensity:number('cbSiloIntensity','난류 강도'),turbulence_length_scale_m:number('cbSiloLength','난류 길이'),convergence_tolerance:number('cbSiloTolerance','수렴 기준')};
   out.mesh=out.mesh||{};out.mesh.target_cells=number('cbSiloCells','목표 격자 수',{integer:true});
   const steady=out.openfoam_mapping.solver==='simpleFoam';
   const end=number('cbSiloEnd',steady?'목표 반복 횟수':'목표 해석 시간'),write=number('cbSiloWrite',steady?'저장 반복 간격':'저장 시간 간격');
   if(!(end>0&&write>0&&write<=end))throw Error('저장 간격은 0보다 크며 계산 종료값 이하여야 합니다');
   if(steady){
    const playback=number('cbSiloPlayback','총 재생 시간');
    if(!Number.isInteger(end)||!Number.isInteger(write))throw Error('목표 반복 횟수와 저장 반복 간격은 정수로 입력해 주세요');
    if(playback<.1||playback>86400)throw Error('총 재생 시간은 0.1~86,400초로 입력해 주세요');
    out.run={time_basis:'iterations',stop_mode:document.getElementById('cbSiloStop').value,max_iterations:end,write_interval_iterations:write,end_time_s:end,write_interval_s:write,viz_interval_s:write,playback_duration_s:playback,output_fields:['flow','pressure','turbulence']};
   }else{
    const dt=number('cbSiloDt','계산 시간 간격');if(!(dt>0))throw Error('계산 시간간격은 0보다 커야 합니다');
    out.run={time_basis:'physical_time',stop_mode:'fixed',end_time_s:end,time_step_s:dt,write_interval_s:write,viz_interval_s:write,max_dt_s:dt,output_fields:['flow','pressure','turbulence']};
   }
   const priorSilo=(out.silo&&typeof out.silo==='object')?out.silo:{};
   out.silo={...priorSilo,kind:'custom',design};
  }catch(e){toast(e.message,true);return;}
  const r=await (await fetch('/api/config-save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,config:out})})).json();
  if(!r.ok){toast('저장 실패: '+(r.msg||''),true);return;}
  finishConfigSave(r,out,null);return;
 }
 const base=cbBase('immersion');
 if(!base){toast('복제할 액침냉각 기본 설정을 찾을 수 없습니다',true);return;}
 const out=JSON.parse(JSON.stringify(base));      // 원본을 복제해 입력값만 덮어쓴다
 out._해석유형='immersion';
 let bad=null;
 for(const el of document.querySelectorAll('#cbForm input[data-g][data-k]')){
  const g=el.dataset.g,k=el.dataset.k,t=el.value.trim();
  const L=el.dataset.l||(g+'.'+k);
  if(t===''){bad='「'+L+'」 값이 비어 있습니다';break;}
  const v=Number(t); if(!isFinite(v)){bad='「'+L+'」 가 숫자가 아닙니다';break;}
 out[g]=out[g]||{}; out[g][k]=v;
 }
 if(bad){toast(bad,true);return;}
 const timeStepMode=document.getElementById('cbTimeStepMode');
 out.run.time_step_mode=timeStepMode?timeStepMode.value:'adaptive';
 for(const role of ['lower','upper']){
  const base=role==='lower'?(out.dielectric_fluid||{}):(out.water||{}),nameEl=document.querySelector('[data-fname="'+role+'"]');
  base.name=(nameEl&&nameEl.value.trim())||(role==='lower'?'하단 비전도 액체':'상단 액체');
  if(role==='upper'){const mw=Number(document.querySelector('[data-fmw="upper"]').value);if(!(Number.isFinite(mw)&&mw>0)){toast('상단 액체 분자량은 0보다 커야 합니다',true);return;}base.molWeight=mw;}
  const vals={},els=[...document.querySelectorAll('[data-fp="'+role+'"]')];let changed=!!base.manual_properties;
  for(const el of els){const v=Number(el.value),b=Number(el.dataset.base);if(!el.value.trim()||!isFinite(v)){toast('「'+base.name+'」 물성값을 확인하세요',true);return;}vals[el.dataset.p]=v;if(Math.abs(v-b)>1e-10*Math.max(1,Math.abs(b)))changed=true;}
  if(!(vals.rho>0&&vals.cp>0&&vals.mu>0&&vals.k>0)){toast('밀도·비열·점성계수·열전도도는 0보다 커야 합니다',true);return;}
  if(!(vals.beta>=0&&vals.beta<=0.02)){toast('체적팽창계수는 0~0.02 1/K 범위여야 합니다',true);return;}
  if(!(vals.T>=-100&&vals.T<=500)){toast('물성 기준 온도는 -100~500 °C 범위여야 합니다',true);return;}
  if(changed)base.manual_properties={model:'linear_density',T_ref_C:vals.T,rho_kg_m3:vals.rho,cp_J_kgK:vals.cp,mu_Pa_s:vals.mu,kappa_W_mK:vals.k,beta_1_K:vals.beta};
  if(role==='lower')out.dielectric_fluid=base;else out.water=base;
 }
 // 케이스 생성기와 같은 규칙으로 미리 검사 — 저장한 뒤 실행에서 터지지 않게
 const pc=out.phase_change||{};
 if(!(pc.evap_C>0)){toast('증발 C 는 0보다 커야 합니다',true);return;}
 if(!(pc.cond_C<0)){toast('응축 C 는 0보다 작아야 합니다',true);return;}
 const df=out.dielectric_fluid||{},vp=out.vapour||{};
 if(!(df.molWeight>0&&vp.cp>0&&vp.mu>0&&vp.kappa>0)){toast('하단 액체 분자량과 증기 물성은 모두 0보다 커야 합니다',true);return;}
 const ck=out.coil||{},rr=out.run||{};
 if(!(ck.flow_LPM>0&&ck.flow_LPM<=100)){toast('냉각수 유량은 0~100 L/min 범위여야 합니다',true);return;}
 if(!(ck.Ta_C>=-10&&ck.Ta_C<=80)){toast('냉각수 입구 온도는 -10~80 °C 범위여야 합니다',true);return;}
 if(!(ck.UA_target_W_K>0)){toast('코일 목표 UA는 0보다 커야 합니다',true);return;}
 if(!(ck.h_W_m2K>0)){toast('코일 모델 h는 0보다 커야 합니다',true);return;}
 if(!(rr.viz_interval_s>0&&rr.end_time_s>0)){toast('총 계산 시간과 데이터 추출 간격은 0보다 커야 합니다',true);return;}
 if(!(rr.max_dt_s>0)){toast('시간 간격은 0보다 커야 합니다',true);return;}
 if(rr.viz_interval_s>rr.end_time_s){toast('데이터 추출 간격은 총 계산 시간보다 클 수 없습니다',true);return;}
 if(!(rr.write_interval_s>0)){toast('복구 데이터 저장 간격은 0보다 커야 합니다',true);return;}
 if(out.layers.init_T_dielectric_C>=out.dielectric_fluid.Tsat_C){
  toast('유전체 초기 온도가 기화점 이상입니다 — 시작과 동시에 전 영역이 비등합니다',true);return;}
 if(!(out.layers.dielectric_mm>0&&out.layers.dielectric_mm<out.tank.liquid_height_mm)){
  toast('하단 비전도 액체 높이는 0 과 액체 높이 사이여야 합니다',true);return;}
 const r=await (await fetch('/api/config-save',{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({name:name,config:out})})).json();
 if(!r.ok){toast('저장 실패: '+(r.msg||''),true);return;}
 const saved=(r.config&&typeof r.config==='object')?r.config:out;
 const conditionRows=Array.isArray(saved.conditions)?saved.conditions.map(r=>({name:''+r.name,Ta_C:''+(r.Ta_C??''),flow_LPM:''+(r.flow_LPM??''),h:''+(r.h_model_W_m2K??r.h??'')})):[];
 finishConfigSave(r,out,conditionRows);
}

let SAVEDCFG=[],SAVEDCFGTYPES={};
function updateConfigDeleteButton(){
 const s=document.getElementById('cfgPick'),b=document.getElementById('cfgToggle');
 if(b)b.disabled=!s;
 if(s&&b){const o=[...s.options].find(x=>x.value===s.value),txt=document.getElementById('cfgToggleTxt');
  if(CFGREF.startsWith('proj:')){const rid=CFGREF.slice(5),p=LASTPROJS.find(x=>x.rid===rid);txt.textContent='프로젝트 설정 · '+((p&&p.name)||rid);}
  else txt.textContent=o?o.textContent:'기본 설정';}
 if(s&&s.disabled)closeConfigMenu();
}
function closeConfigMenu(){
 const m=document.getElementById('cfgMenu'),b=document.getElementById('cfgToggle');
 if(m)m.classList.remove('open');if(b)b.classList.remove('open');
}
function toggleConfigMenu(){
 if(runBusyNow()){toast('실행 중에는 설정을 할 수 없습니다',true);return;}
 const s=document.getElementById('cfgPick'),m=document.getElementById('cfgMenu'),b=document.getElementById('cfgToggle');
 if(!s||s.disabled){toast('잠금 상태 — 설정을 바꾸려면 [새 프로젝트]를 누르세요',true);return;}
 const on=!m.classList.contains('open');closeConfigMenu();if(on){m.classList.add('open');b.classList.add('open');}
}
function chooseSetting(v){
 if(runBusyNow()){toast('실행 중에는 설정을 할 수 없습니다',true);return;}
 const s=document.getElementById('cfgPick');if(!s||s.disabled)return;
 s.value=v;closeConfigMenu();renderSettings(v);settingChanged();
}
function askDeleteConfig(name,ev){
 if(ev){ev.stopPropagation();ev.preventDefault();}
 if(!name)return;
 closeConfigMenu();
 confirmBox('설정을 삭제할까요?',name+'.json 파일만 삭제됩니다. 프로젝트와 계산 데이터는 그대로 유지됩니다.','삭제',()=>deleteConfig(name));
}
async function deleteConfig(name){
 if(runBusyNow()){toast('실행 중에는 설정을 할 수 없습니다',true);return;}
 try{
  const r=await (await fetch('/api/config-del',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})})).json();
  if(!r.ok)throw new Error(r.msg||'삭제 실패');
  SAVEDCFG=r.list||[];SAVEDCFGTYPES=r.types||{};CFGREF='';renderSettings('');await settingChanged();
  toast(name+'.json 설정을 삭제했습니다');
 }catch(e){toast('설정 삭제 실패: '+e.message,true);}
}
function configDisplayName(name){return name+' · '+(SAVEDCFGTYPES[name]==='grain_silo'?'식량 저장고':'액침냉각');}
function renderSettings(prefer){                           // 기본 config와 사용자가 저장한 config만 표시
 const s=document.getElementById('cfgPick'); if(!s)return;
 const cur=prefer!=null?prefer:(CFGREF||s.value);
 while(s.children.length>1)s.lastElementChild.remove();
 if(SAVEDCFG.length){
  const gf=document.createElement('optgroup'); gf.label='저장된 설정';
  for(const name of SAVEDCFG){const o=document.createElement('option');o.value='cfg:'+name;o.textContent=configDisplayName(name);gf.appendChild(o);}
  s.appendChild(gf);
 }
 s.value=(cur&&[...s.options].some(o=>o.value===cur))?cur:'';
 const menu=document.getElementById('cfgMenu');
 if(menu){
  const row=(value,label,saved,rawName)=>{const q=encodeURIComponent(value).replace(/'/g,'%27'),n=encodeURIComponent(rawName||label).replace(/'/g,'%27');
   return '<div class="cfgOpt'+(s.value===value?' on':'')+'"><button type="button" class="cfgChoose" role="option" '
    +'onclick="chooseSetting(decodeURIComponent(\''+q+'\'))" title="'+esc(label)+'">'+esc(label)+'</button>'
    +(saved?('<button type="button" class="cfgTrash" title="'+esc(rawName||label)+'.json 삭제" '
      +'onclick="askDeleteConfig(decodeURIComponent(\''+n+'\'),event)">🗑</button>'):'')+'</div>';};
  menu.innerHTML=row('','기본 설정',false)+SAVEDCFG.map(name=>row('cfg:'+name,configDisplayName(name),true,name)).join('');
 }
 updateConfigDeleteButton();}
addEventListener('click',e=>{const d=document.getElementById('cfgDrop');if(d&&!d.contains(e.target))closeConfigMenu();});
async function run(mode,extra){
 const c='',ov={};
 const outputs=(mode==='fresh'||mode==='reset')?selectedOutputList():null;
 if(outputs&&!outputs.length){toast('출력 데이터를 1개 이상 선택해 주세요',true);return;}
 const configName=CFGREF.startsWith('cfg:')?CFGREF.slice(4):((CFG&&CFG._설정이름)||'');
 const body={mode:mode==='reset'?'fresh':mode,condition:c,overrides:ov,end:extra&&extra.end,
  selected_rid:(extra&&extra.rid)||(PROJ||CURC)||'',
  config_ref:(mode==='fresh'||mode==='reset')?'inline':CFGREF,config_name:configName};
 // 실행 시점의 설정 전체와 출력 선택을 프로젝트 config에 고정한다.
 if(mode==='fresh'||mode==='reset'){
  body.config=JSON.parse(JSON.stringify(CFG));
  body.config.run=body.config.run||{};body.config.run.output_fields=outputs;
  body.output_fields=outputs;
 }
 if(mode==='reset')body.reset_rid=extra&&extra.rid;        // 같은 프로젝트를 저장된 설정으로 0초부터
 const rr=await (await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).json();
 if(!rr.ok){toast(rr.msg||'실행 시작 실패',true);return;}
 ++PROJGEN;
 if(rr.rid){PROJ=rr.rid;CURC=rr.cur||rr.rid;}
 if(Array.isArray(rr.projects))renderProjects({cur:rr.cur||rr.rid||CURC,projects:rr.projects});
 if((mode==='fresh'||mode==='reset')&&CFG){CFG.run=CFG.run||{};CFG.run.output_fields=outputs;RUNCFG=CFG;}
 NEWMODE=false;RESETREADY=false;LAUNCHT=Date.now();        // 시작 중 상태 표시 개시
 if(mode==='reset'){HIST=[];HISTV=[];HISTC=[];clearDash.done=false;clearDash();}
 toast(mode==='fresh'?'처음부터 실행 시작 — 명령 프롬프트 창을 확인하세요'
  :mode==='reset'?'처음부터 실행 시작 — 저장된 프로젝트 설정 사용 (콘솔 창 확인)'
  :'이어서 실행 — 설정 변경 없이 저장된 상태 그대로 재개합니다');}
async function setAutoRes(){
 const on=document.getElementById('autoRes').checked;
 await fetch('/api/auto-resume',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({on})});
 toast(on?'자동 이어서 실행 켜짐 — 멈추면 앱이 알아서 재개합니다':'자동 이어서 실행 꺼짐');}
async function stop(){
 await fetch('/api/stop',{method:'POST'});
 LAUNCHT=0;                                               // 시작 중 창 즉시 해제 — 중단 후 프로젝트 전환 가능
 if(LASTST)LASTST.running=false;
 toast('중지 신호를 보냈습니다');
 clearTimeout(PTIMER);PTIMER=setTimeout(poll,1200);}      // 정지 반영된 상태를 바로 재조회 (폴링 체인은 1개 유지)
async function syncCase(){
 if(CFGREF==='inline'){
  if(!ACTIVE_CONFIG_FILE){toast('이 파일은 다시 접근할 수 없습니다 — 기반 파일 카드를 눌러 다시 선택하세요',true);return;}
  try{
   const cj=JSON.parse(await ACTIVE_CONFIG_FILE.text());setConfig(cj);fillRunInputs(cj,true);CFGSRC='다시 읽은 '+ACTIVE_CONFIG_FILE.name;
   fillConds(Array.isArray(cj.conditions)?cj.conditions.map(r=>({name:''+r.name,Ta_C:''+(r.Ta_C??''),flow_LPM:''+(r.flow_LPM??''),h:''+(r.h_model_W_m2K??r.h??'')})):[]);
   toast(ACTIVE_CONFIG_FILE.name+' 다시 읽기 완료');return;
  }catch(e){toast('config.json 다시 읽기 실패',true);return;}
 }
 let url='/api/config';
 if(CFGREF.startsWith('cfg:'))url+='?name='+encodeURIComponent(CFGREF.slice(4));
 else if(CFGREF.startsWith('proj:'))url+='?project='+encodeURIComponent(CFGREF.slice(5));
 else{
  const s=await (await fetch('/api/sync-case',{method:'POST'})).json();
  if(!s.ok){toast('동기화 실패: '+(s.msg||''),true);return;}
 }
 const r=await (await fetch(url)).json();
 if(!r.ok||!r.config){toast('다시 읽기 실패: '+(r.msg||''),true);return;}
 setConfig(r.config);fillRunInputs(r.config,true);if(!CFGREF.startsWith('proj:'))CFGFILE=r.name;ACTIVE_CONFIG_FILE=null;
 CFGSRC=(CFGREF.startsWith('proj:')?'프로젝트 스냅샷 ':'다시 읽은 ')+configFileName();
 fillConds(r.conditions||[]);updateSlots();toast(configFileName()+' 다시 읽기 완료');}
function setStatus(s){
 if(document.body.classList.contains('grouped'))return;
 const d=document.getElementById('stDot'), t=document.getElementById('stTxt');
 if(!s.wsl){d.className='dot off';t.textContent='WSL 연결 안 됨';}
 else if(!s.case){d.className='dot warn';t.textContent='케이스 폴더 없음';}
 else if(s.running){d.className='dot run';t.textContent='솔버 실행 중';LAUNCHT=0;}
 else if(LAUNCHT&&Date.now()-LAUNCHT<240000){d.className='dot run';t.textContent='시작 중 — 격자 생성·초기화 (콘솔 창 참고)';}
 else{d.className='dot ok';t.textContent=s.completed?(s.completion_reason==='converged'?'수렴 완료':s.completion_reason==='limit'?'수렴 미도달 · 반복 한도 종료':'계산 완료'):'연결됨 · 대기';}
 {const ar=document.getElementById('autoRes');
  if(ar&&document.activeElement!==ar&&s.auto_resume!=null)ar.checked=!!s.auto_resume;
 }
 const launching=!s.running&&LAUNCHT&&Date.now()-LAUNCHT<240000;
 document.getElementById('runBusy').style.display=(s.running||launching)?'flex':'none';
 // 상태 머신: 실행 중=[중단] · 그 외=[실행] 하나 — 새 프로젝트=새 계산, 현재 프로젝트(미완)=이어서
 const resum=!s.completed&&!s.running&&s.resume_anchor!=null&&((+s.snap_count||0)>1||+s.resume_anchor>0);
 RESUM=resum;
 const pSel0=LASTPROJS.find(x=>x.rid===(PROJ||CURC));
 const selCur=(!PROJ||PROJ===CURC);
 const curResum=selCur&&resum;
 const projHas=projectHasProgress(pSel0);                         // 선택 프로젝트의 계산·변환 진행 데이터
 HASRUN=((!!s.running&&selCur)||curResum||projHas)&&!NEWMODE;
 if(!HASRUN)clearDash();
 if(!resum&&!s.running&&!projHas&&!pSel0)NEWMODE=true;    // 선택된 프로젝트도 없을 때만 새 프로젝트 상태
 document.getElementById('runIdle').style.display=(s.running||launching)?'none':'flex';
 const canResume=curResum;
 const go=document.getElementById('btnGo');
 if(go){go.disabled=false;                       // 항상 눌리게 — 불가한 상황이면 goRun이 이유·대안을 안내
  const gt=document.getElementById('btnGoTxt');if(gt)gt.textContent=(!NEWMODE&&(projHas||canResume))?'실행 재개':'실행';
  go.title=NEWMODE?'새 프로젝트로 계산 시작':(canResume?'중단 지점부터 이어서 계산'
   :(selCur?'완주된 프로젝트 — [새 프로젝트]로 새 계산':'보관된 프로젝트 — 누르면 안내가 표시됩니다 (재생은 Viewer)'));}
 const reset=document.getElementById('btnReset');
 if(reset)reset.style.display=(!s.running&&!launching&&!NEWMODE&&!!pSel0&&!pSel0.external&&(curResum||projHas))?'':'none';
 const dis=!!s.running||!NEWMODE;
 for(const id of [...Object.values(OUTIDS),'cfgPick'])document.getElementById(id).disabled=dis;
 const add=document.getElementById('cfgAdd');
 if(add){add.disabled=false;add.title='새 설정 만들기';}
 updateConfigDeleteButton();
}
function chartNote(txt){
 for(const id of ['spark','vchart']){const el=document.getElementById(id);
  if(el&&!el.innerHTML)el.innerHTML='<text x="50%" y="50%" fill="#6b6b66" font-size="12" text-anchor="middle">'+txt+'</text>';}}
async function openRawSnapshots(){
 const rid=PROJ||CURC;
 if(!rid){toast('Raw 데이터를 열 프로젝트를 선택하세요',true);return;}
 try{
  const r=await (await fetch('/api/open-raw',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rid})})).json();
  if(!r.ok)throw new Error(r.msg||'Raw 데이터 폴더를 열지 못했습니다');
 }catch(e){toast((e.message||e),true);}
}
function clearDash(){
 if(clearDash.done)return; clearDash.done=true;          // 상태 전환 시 1회만 (매 폴마다 재청소 불필요)
 document.getElementById('mTime').innerHTML='<span class="un" style="font-size:16px">실행 전 — 진행 데이터 없음</span>';
 document.getElementById('mPct').textContent='';
 document.getElementById('runBar').style.width='0%';
 for(const id of ['stEtaW','stVapW','stCoilW'])document.getElementById(id).innerHTML='';
 document.getElementById('dSnap').textContent='';document.getElementById('openRaw').style.display='none';
 document.getElementById('chartT').textContent='';document.getElementById('vchartT').textContent='';
 document.getElementById('spark').innerHTML='';document.getElementById('vchart').innerHTML='';
 for(const id of ['v1','v2','v3','v4','v5','v6'])document.getElementById(id).textContent='';
 document.getElementById('mLog').textContent='';
 HIST=[];HISTV=[];HISTC=[];LIVET5=null;LIVET6=null;      // 이전 실행 이력도 함께 리셋 → 라벨·차트 재유입 방지
 METR=[]; {const mc=document.getElementById('metCard'); if(mc)mc.style.display='none';}
}
function renderHardwareUsage(hw){
 const card=document.getElementById('sysCard'),row=document.getElementById('sysRow');if(!card||!row)return;
 const valid=v=>typeof v==='number'&&Number.isFinite(v),percent=v=>valid(v)?Math.max(0,Math.min(100,v)):null;
 const capacity=d=>valid(d?.total_bytes)&&d.total_bytes>0&&valid(d.free_bytes)?percent(100*(1-d.free_bytes/d.total_bytes)):null;
 const storageText=d=>{if(!valid(d.total_bytes)||d.total_bytes<=0)return '—';const total=(d.total_bytes/1e9).toFixed(1),used=valid(d.free_bytes)?(Math.max(0,d.total_bytes-d.free_bytes)/1e9).toFixed(1):'—';return used+' / '+total+' GB';};
 // nvidia-smi reports memory.used and memory.total in MiB.
 const vramText=g=>{const used=valid(g.mu)&&g.mu>=0?(g.mu/1024).toFixed(1):'—',total=valid(g.mt)&&g.mt>0?(g.mt/1024).toFixed(1):'—';return 'VRAM '+used+' / '+total+' GiB';};
 const fresh=sample=>!hw?.stale&&!sample?.stale&&valid(sample?.sampled_at)&&Date.now()/1000-sample.sampled_at<4;
 const drives=Array.isArray(hw?.drives)?hw.drives:[];
 const gpus=Array.isArray(hw?.gpus)?hw.gpus:[];
 const items=[['cpu','CPU',fresh({sampled_at:hw?.cpu_sampled_at??hw?.sampled_at})?percent(hw?.cpu):null,'컴퓨터 전체 CPU 사용률','cpu'],...drives.map(d=>['disk:'+d.drive,d.drive,fresh(hw)?capacity(d):null,'드라이브 저장공간 사용률','disk',storageText(d)]),...gpus.map(g=>['gpu:'+g.i,g.i==null?'GPU':'GPU '+g.i,fresh(g)?percent(g.u):null,'Windows GPU 엔진 사용률','gpu',fresh(g)?vramText(g):'VRAM — / — GiB'])];
 const icons={cpu:'M7 7h10v10H7ZM9 2v5m6-5v5M9 17v5m6-5v5M2 9h5m-5 6h5m10-6h5m-5 6h5',disk:'M5 4h14l2 11v5H3v-5ZM3 15h18M7 18h.01M11 18h.01',gpu:'M3 6h18v12H3ZM8 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6ZM16 10h2m-2 4h2M6 18v3m5-3v3'};
 const previous=new Map([...row.children].map(n=>[n.dataset.key,n]));
 for(const [key,label,value,tip,kind,capacityText='']of items){
  let item=previous.get(key);if(item)previous.delete(key);else{item=document.createElement('div');item.className='hw-item';item.dataset.key=key;const icon=document.createElementNS('http://www.w3.org/2000/svg','svg');icon.setAttribute('viewBox','0 0 24 24');icon.setAttribute('aria-hidden','true');const path=document.createElementNS(icon.namespaceURI,'path');path.setAttribute('d',icons[kind]);icon.append(path);const name=document.createElement('b'),output=document.createElement('output'),track=document.createElement('div'),fill=document.createElement('span');track.className='hw-track';fill.className='hw-fill';track.append(fill);const size=document.createElement('small');size.className='hw-capacity';size.title='사용 용량 / 전체 용량';item.append(icon,name,output,track,size);row.append(item);}
  const gpu=kind==='gpu'?gpus.find(g=>'gpu:'+g.i===key):null;item.title=tip+(gpu?.name?' · '+gpu.name:'')+(gpu?.engine?' · '+gpu.engine:'')+(gpu?.source?' · '+gpu.source:'')+(value===null?' · 측정값 없음':'');item.querySelector('b').textContent=label;item.querySelector('output').textContent=value===null?'—':value.toFixed(1)+'%';item.querySelector('.hw-fill').style.width=(value??0)+'%';item.setAttribute('aria-label',label+' '+item.querySelector('output').textContent);item.classList.toggle('hw-unavailable',value===null);item.querySelector('.hw-capacity').textContent=capacityText;item.setAttribute('aria-label',label+' '+item.querySelector('output').textContent+(capacityText?' · '+capacityText:''));
 }
 for(const obsolete of previous.values())obsolete.remove();
 // Keep CPU, drives and GPUs in the same order when devices appear or disappear.
 items.forEach(([key],i)=>{const child=[...row.children].find(n=>n.dataset.key===key);if(row.children[i]!==child)row.insertBefore(child,row.children[i]||null);});
 card.style.display='';card.dataset.stale=String(!hw||!!hw.stale||!!hw.sampled_at&&Date.now()/1000-hw.sampled_at>=4);
}
async function poll(){
 if(POLLING) return; POLLING = true;
 try{
  const s=await fetch('/api/status').then(r=>r.json());
  LASTST=s; setStatus(s); updateLiveProjectProgress(s);
  if(EXBUSY&&s.extract&&!s.extract.busy&&!isWatching(CURC)){SRVDIRTY=true;refreshSrvInfo();}  // 자동 동기화 변환 완료 → 준비 개수 갱신
  EXBUSY=!!(s.extract&&s.extract.busy);
  const launch2=!s.running&&LAUNCHT&&Date.now()-LAUNCHT<240000;
  if(launch2)document.getElementById('mTime').innerHTML='<span class="un" style="font-size:16px">시작 중 · 격자 생성·초기화 (콘솔 창에서 진행 확인)</span>';
  else if(s.running&&s.time==null)                                   // 솔버는 떴지만 첫 출력 전 — 문구가 멈춰 보이지 않게 매번 갱신
   document.getElementById('mTime').innerHTML='<span class="un" style="font-size:16px">솔버 실행 중 · 첫 출력 대기 (초기 몇 분 소요)</span>';
  if(HASRUN)clearDash.done=false;                        // 실행/재개 상태로 돌아오면 다음 정리를 허용
  // 표시 시간의 단일 기준: 실행 중 = 로그의 현재 시간 · 중지 = 재개 지점(마지막 스냅샷 앵커)
  const anchorT=(!s.running&&s.resume_anchor!=null)?+s.resume_anchor:null;
  const tShow=s.running?s.time:anchorT;
  const pSel=LASTPROJS.find(x=>x.rid===(PROJ||CURC));
  const axis=runAxis(RUNCFG||CFG,pSel);
  const maxSnap=+s.snap_max||0;
  const mism=!!s.running&&s.time!=null&&maxSnap>1&&s.time<maxSnap-1;
  const dw=document.getElementById('dashWarn');
  if(dw){dw.style.display=mism?'':'none';
   if(mism)dw.textContent='주의 — 저장된 진행(최대 '+maxSnap.toFixed(axis.digits)+axis.unit+')보다 낮은 '+s.time.toFixed(axis.digits)+axis.unit+'에서 계산 중입니다. 의도한 재개가 아니면 [중단] 후 다시 [실행]을 누르고 로그 첫머리의 [CFD Studio 재개] 줄을 확인하세요.';}
  const arch=!s.running&&pSel&&pSel.rid!==CURC;                       // 보관 프로젝트 선택 상태
  if(arch&&!HIST.length)chartNote('보관 프로젝트 — 차트 이력은 실행 당시에만 기록 · 재생은 Viewer');
  const endShow=s.running?s.endTime:((pSel&&pSel.end)||s.endTime);   // 표시는 프로젝트 고유 종료시각
  const tShow2=arch?pSel.tmax:tShow;
  if(HASRUN&&tShow2!=null){
   const pc=s.completed?100:Math.min(100,100*tShow2/endShow);
   const doneLabel=s.completed?(s.completion_reason==='converged'?' · 수렴 완료':s.completion_reason==='limit'?' · 수렴 미도달 · 반복 한도 종료':' · 계산 완료'):(arch?' · 보관됨':' · 중지됨 — 재개 지점');
   document.getElementById('mTime').innerHTML=axis.steady?
    ('재생 '+fmtPlaybackSeconds(playbackDuration(RUNCFG||CFG,pSel))+'초 <span class="un">('+tShow2.toFixed(0)+' / '+Number(endShow).toFixed(0)+'회)'+(s.running?'':doneLabel)+'</span>'):
    (tShow2.toFixed(axis.digits)+' <span class="un">/ '+endShow+' 시뮬레이션 초'+(s.running?'':doneLabel)+'</span>');
   document.getElementById('mPct').textContent=pc.toFixed(2)+'%';
   document.getElementById('runBar').style.width=pc+'%';
  }
  if(HASRUN){ // 보관 프로젝트를 보는 동안엔 현재 케이스의 실시간 수치를 섞지 않음 (프로젝트 독립 표시)
  document.getElementById('stEtaW').innerHTML=(!arch&&s.running&&s.eta_s!=null)?
   ('완주 예상 현실 <b>'+Number(s.eta_s).toLocaleString()+'초</b> · '+Number(s.eta_h).toLocaleString()+'시간'):'';
  document.getElementById('stVapW').innerHTML=(!arch&&s.vapor_mL!=null)?('TMC-49 증기 <b>'+s.vapor_mL+'</b> mL'):'';
  const coilW=(!arch&&s.coilT!=null)?coilPowerW(s.coilT,RUNCFG||CFG):null;
  document.getElementById('stCoilW').innerHTML=(!arch&&s.coilT!=null)?('코일 <b>'+s.coilT+'</b> °C'+(coilW!=null?' · 배출 <b>'+coilW.toFixed(0)+'</b> W':'')):'';
  }
  // 냉각회로 T5(입구=조건값)·T6(출구=T5+Q/ṁcp, 조건의 유량 필요)
  const cp2=(HASRUN&&!arch)?coilPars():null;
  const t5=cp2?cp2.t5:null, t6=(HASRUN&&!arch)?calcT6(s.coilT):null;
  LIVET5=t5;LIVET6=t6;
  if(!arch&&HASRUN&&s.coilT!=null&&s.time!=null&&(!HISTC.length||s.time>HISTC[HISTC.length-1][0]))HISTC.push([s.time,s.coilT]);
  document.getElementById('v5').textContent=t5!=null?t5.toFixed(1)+'°':'';
  document.getElementById('v6').textContent=t6!=null?('≈'+t6.toFixed(2)+'°'):'';
  // 뷰어 실시간 솔버 구획 (레이어 토글)
  const showLive=!isSiloConfig(VIZCFG||RUNCFG||CFG)&&HASRUN&&!arch&&LY('lyInfo')&&(s.time!=null||s.vapor_mL!=null||s.coilT!=null);
  document.getElementById('hLiveG').style.display=showLive?'':'none';
  if(showLive){
   document.getElementById('hLt').textContent=tShow!=null?tShow.toFixed(2):'—';
   document.getElementById('hLv').textContent=s.vapor_mL!=null?s.vapor_mL:'—';
   document.getElementById('hLc').textContent=s.coilT!=null?s.coilT:'—';
  }
  if(!arch&&HASRUN&&s.probes){const r=[s.probes.t,...s.probes.T];
   if(!HIST.length||r[0]>HIST[HIST.length-1][0]) {HIST.push(r); if(MODE==='cfd')drawSpark();}}
  if(!arch&&HASRUN&&s.vapor_mL!=null&&s.time!=null&&(!HISTV.length||s.time>HISTV[HISTV.length-1][0]+1e-9)){
   HISTV.push([s.time,s.vapor_mL]); if(MODE==='cfd')drawVap();}
 try{renderEnergy();}catch(_){ }          // 에너지 수지 — 매 폴링마다 갱신
  // 스냅샷 표기도 프로젝트 기준: 보관 프로젝트 = 그 프로젝트의 보관 프레임 수 · 현재 = 케이스 스냅샷 수
  METR=(!arch&&HASRUN&&s.met)?s.met:[];
  if(MODE==='cfd')drawMetrics(); else {const mc=document.getElementById('metCard'); if(mc)mc.style.display='none';}
  const snapText=arch?(pSel&&pSel.n?('보관 프레임 '+pSel.n+'개'):'')
   :((HASRUN&&+s.snap_count>0)?('저장 스냅샷 '+s.snap_count+'개'):'');
  document.getElementById('dSnap').textContent=snapText;
  document.getElementById('openRaw').style.display=snapText?'inline-flex':'none';
  {const el=document.getElementById('mLog');
   if(arch){el.innerHTML='<span style="color:#6b6b66">보관 프로젝트 — 솔버 로그·실시간 수치는 현재 실행 케이스에서만 표시됩니다. 저장된 결과는 Viewer 탭 [실행]으로 재생하세요.</span>';}
   else if(HASRUN&&s.log){el.innerHTML=s.log.split('\\n').slice(-30).map(l=>l.startsWith('Time =')?'<span class="hl">'+l+'</span>':l).join('\\n');
    el.scrollTop=el.scrollHeight;}
   else if(s.running){el.innerHTML='<span style="color:#8a8880">솔버가 실행 중입니다 · 첫 로그 출력까지 잠시 기다려 주세요 (격자·초기화 단계에서는 콘솔 창에 진행이 표시됩니다)</span>';}
   else if(!HASRUN&&s.case&&s.dbg&&!s.log&&!pSel){el.innerHTML='<span style="color:#fab219">[연결 진단 — 로그가 비어 있어 상태를 점검합니다]</span>\\n'+esc(s.dbg)
    +'\\n\\n해석: LOG=[]이면 케이스 폴더에 log 파일이 없는 것(솔버가 이 폴더에서 실행된 적 없음/정리됨), pp: 아래에 probesT가 없으면 계측 데이터가 없는 것입니다.';}}
  if(!isWatching(CURC)) showExtract(s.extract,CURC);
 }catch(_){ const d=document.getElementById('stDot');d.className='dot off';
  document.getElementById('stTxt').textContent='서버 응답 없음'; }
 finally{
  POLLT=Date.now();
  PTIMER=setTimeout(poll,3000);
  POLLING=false;
 }
}

let hardwareLast=null;
async function pollHardware(){
 const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),2000);
 try{const response=await fetch('/api/sys',{signal:controller.signal,cache:'no-store'});if(!response.ok)throw Error('Hardware unavailable');hardwareLast=await response.json();renderHardwareUsage(hardwareLast);}
 catch(_){renderHardwareUsage(hardwareLast?{...hardwareLast,stale:true}:null);}
 finally{clearTimeout(timeout);setTimeout(pollHardware,1000);}
}
renderHardwareUsage(null);pollHardware();
let POLLING=false;
let POLLT=Date.now();
setInterval(()=>{                                        // 15초 넘게 갱신이 없으면 폴링 체인 재기동
 if(!POLLING&&Date.now()-POLLT>15000){POLLT=Date.now();clearTimeout(PTIMER);poll();}
},5000);
poll();
setTimeout(drawSpark,300);
setTimeout(updateSlots,400);
document.getElementById('nmInput').addEventListener('keydown',e=>{
 if(e.key==='Enter')nmOk(); if(e.key==='Escape')nmClose();});

// ══════════════ 마지막 화면 상태 저장·복원 ══════════════
const UILY=['lyBub','lyPhase','lySlice','lyTvol','lyGeo','lyCoil','lyTank','lyBound','lyProbe','lyInfo','gcT','gcV','gcB','gcL'];
const UIOUT=Object.values(OUTIDS);
for(const id of ['lyBub','lyPhase','lySlice','lyTvol']){
 const el=document.getElementById(id);if(el)el.addEventListener('change',refreshViewerFields);
}
function collectUI(){
 const g=id=>document.getElementById(id);
 const currentLayers=Object.fromEntries(UILY.map(i=>[i,g(i).checked]));
 const layerMode=configureViewerFields.mode||(isSiloConfig(MODE==='viz'?(VIZCFG||CFG):CFG)?'grain_silo':'immersion');
 const layerModes={...VIEWLAYERSTATE,[layerMode]:currentLayers};
 return {mode:MODE, proj:PROJ, vproj:VPROJ, newmode:NEWMODE, speed:g('speed').value,
  layers:currentLayers,layer_modes:layerModes,
  cam:{th,ph,rad,tgt:[...tgt]},
  outputs:NEWMODE?Object.fromEntries(UIOUT.map(i=>[i,g(i).checked])):null};
}
let UILAST='';
async function saveUI(force){
 try{
  const st=collectUI(), j=JSON.stringify(st);
  if(!force&&j===UILAST)return; UILAST=j;
  await fetch('/api/uistate',{method:'POST',headers:{'Content-Type':'application/json'},body:j});
 }catch(_){}}
setInterval(()=>saveUI(false),3000);
setInterval(refreshProjectList,5000);                     // Project 폴더 추가·삭제를 재실행 없이 반영
addEventListener('beforeunload',()=>{try{navigator.sendBeacon('/api/uistate',JSON.stringify(collectUI()));}catch(_){}});
async function restoreUI(currentStatus){
 if(document.body.classList.contains('grouped'))return;
 try{
  const st=await (await fetch('/api/uistate')).json();
  if(!st||!st.mode)return;
  const g=id=>document.getElementById(id);
  if(st.layer_modes&&typeof st.layer_modes==='object')Object.assign(VIEWLAYERSTATE,st.layer_modes);
  else if(st.layers){const rid=(st.vproj!==undefined&&st.vproj!==null)?st.vproj:st.proj,p=LASTPROJS.find(x=>x.rid===(rid||CURC));
   VIEWLAYERSTATE[p&&p.analysis==='grain_silo'?'grain_silo':'immersion']=st.layers;}
  const currentMode=configureViewerFields.mode||(isSiloConfig(CFG)?'grain_silo':'immersion'),currentLayers=VIEWLAYERSTATE[currentMode];
  if(currentLayers)for(const k of UILY)if(g(k)&&currentLayers[k]!=null)g(k).checked=currentLayers[k];
  if(st.speed)g('speed').value=st.speed;
  if(st.cam){th=st.cam.th;ph=st.cam.ph;rad=st.cam.rad;}
  const ownsCurrent=!!(currentStatus&&(currentStatus.running||+currentStatus.time>0||
   (currentStatus.snap_times||[]).some(x=>+x>0)));
  if(st.proj&&st.proj!==(PROJ||'')&&!ownsCurrent&&!(st.newmode&&HASPEND)){await selectProj(st.proj,true);}
 if(st.vproj!==undefined&&st.vproj!==null)VPROJ=st.vproj;             // 뷰어 독립 선택 복원
 if(st.newmode&&HASPEND){NEWMODE=true;
   for(const id of UIOUT)if(g(id))g(id).disabled=false;
   if(st.outputs)for(const k in st.outputs)if(g(k))g(k).checked=!!st.outputs[k];
   const go=g('btnGo'); if(go)go.disabled=false;}
  if(st.mode==='viz'){setMode('viz');
   const p=LASTPROJS.find(x=>x.rid===(vzrid()||CURC));
   const d=p&&p.data||{};
   if(p&&(p.n>0||d.concentration>0||d.bubble>0||d.flow>0||d.therm>0||d.phase>0||d.pressure>0||d.turbulence>0)&&!FRAMES.length)loadFrames(); // 부분 데이터 프로젝트도 복원
  }
  UILAST=JSON.stringify(collectUI());
 }catch(_){}}
__TRACER_VIEWER__
(async()=>{
 try{
  const i=await (await fetch('/api/info')).json();
  if(i.config){
   if(i.config_source==='project'&&i.rid){const p0=(i.projects||[]).find(x=>x.rid===i.rid),cn=i.project_config_name||'config.json';CFGREF='proj:'+i.rid;CFGFILE=((p0&&p0.name)||i.rid)+' · '+cn;CFGSRC='현재 프로젝트 / '+cn;}
   else{CFGREF='';CFGFILE='config.json';CFGSRC='WSL 케이스 config.json (자동 로딩)';}
   setConfig(i.config);fillRunInputs(i.config);
  }
  fillConds(i.conditions||[]);
  if(i.env){document.getElementById('envPath').textContent='OpenFOAM · 코어 자동 감지';ENVINFO=i.env;}
  const st0=await (await fetch('/api/status')).json();
  const resum0=!!st0.running||(st0.snap_times||[]).some(x=>+x>0);
  if(resum0){                                            // 진행 상태가 있을 때만 이전 이력 표시 (없으면 깨끗한 대기 화면)
   const h=await (await fetch('/api/history')).json();
   if(h.probes&&h.probes.length){HIST=h.probes;drawSpark();}
   if(h.vapor&&h.vapor.length){HISTV=h.vapor;drawVap();}
   try{renderEnergy();}catch(_){}
   if(h.coil&&h.coil.length)HISTC=h.coil;
  }
  PROJ=i.rid||''; renderProjects(i);
  if(PROJ)applyProjSettings(PROJ);                       // 현재 프로젝트의 설정·현황 즉시 표시
  await restoreUI(st0);                                  // 계산 중/중단 현재 프로젝트가 과거 저장 선택보다 우선
  const studyProject=new URLSearchParams(location.search).get('study_project');
  if(studyProject&&LASTPROJS.some(p=>p.rid===studyProject)){VPROJ=studyProject;openProj(studyProject);}
  // 서버를 다시 열어도 마지막 프로젝트의 변환 결과는 즉시 준비한다. Raw 재변환이
  // 아니라 Project 폴더의 저장된 프레임만 읽으므로, Viewer를 열면 곧바로 재생할 수 있다.
  const restoreRid=vzrid()||PROJ, restoreProj=LASTPROJS.find(p=>p.rid===restoreRid);
  const restoreData=restoreProj&&restoreProj.data||{};
  if(!document.body.classList.contains('grouped')&&restoreProj&&(restoreProj.n>0||restoreData.concentration>0||restoreData.bubble>0||restoreData.flow>0||restoreData.therm>0||restoreData.phase>0)&&!FRAMES.length){
   SRVDIRTY=true;loadFrames();
  }
  if(i.saved_configs){SAVEDCFG=i.saved_configs;SAVEDCFGTYPES=i.saved_config_types||{};renderSettings();}
  srvFromInfo(i); if((SRV.bub&&SRV.hasC)||SRV.flow||SRV.therm||SRV.pressure||SRV.turbulence)SRVDIRTY=true; // [실행]으로 프로젝트 데이터 로딩
  updateSlots();
 }catch(_){}
})();
</script>
<script src="/warehouse_viewer.js"></script>
<script src="/input_validation.js"></script>
<script src="/spatial_editor.js"></script>
<script src="/config_editor.js"></script>
<script src="/form_config_editor.js"></script>
<script src="/form_wizard.js"></script>
<script src="/data_sheet_viewer.js"></script>
<script src="/execution_workspace.js"></script>
<script src="/i18n.js"></script>
<script src="/i18n_help.js"></script>
</body></html>
'''
INDEX_HTML = INDEX_HTML.replace("__APP_VER__", APP_VER)
with open(os.path.join(HERE, "internal", "tracer_viewer.js"), encoding="utf-8") as _tracer_js:
    INDEX_HTML = INDEX_HTML.replace("__TRACER_VIEWER__", _tracer_js.read())

def _merge_conditions():
    """설정 일원화 — conditions.csv를 config.json의 "conditions" 배열로 1회 통합.
    원본 csv는 conditions.csv.bak으로 보관. 기반 파일이 하나가 되어 관리·이동이 단순해짐."""
    src = os.path.abspath(os.path.join(HERE, "..", "tmc49_full_tank"))
    cj, cc = os.path.join(src, "config.json"), os.path.join(src, "conditions.csv")
    if not (os.path.exists(cj) and os.path.exists(cc)): return
    try:
        cfg = json.load(open(cj, encoding="utf-8"))
        if not isinstance(cfg.get("conditions"), list):        # 이미 통합됐으면 백업만
            import csv as _csv
            rows = []
            for r in _csv.DictReader(open(cc, encoding="utf-8-sig")):
                row = {}
                for k, v in r.items():
                    if k is None or v is None: continue
                    v = v.strip()
                    try: row[k.strip()] = float(v) if v and k.strip() not in ("name", "case", "note") else v
                    except ValueError: row[k.strip()] = v
                if row.get("name"): rows.append(row)
            cfg["conditions"] = rows
            tmp = cj + ".tmp"
            json.dump(cfg, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            os.replace(tmp, cj)
        os.replace(cc, cc + ".bak")
        print(f"[CFD Studio] conditions.csv → config.json 'conditions' 통합 완료 (원본은 conditions.csv.bak)")
    except Exception as e:
        print("[CFD Studio] 조건 통합 건너뜀:", e)

def sync_case_files():
    """Windows 폴더의 실행 도구만 WSL로 동기화한다.

    config.json은 프로젝트 상태이므로 여기서 다루지 않는다. 새 해석은
    /api/run이 선택 config를 적용하고, 재개는 해당 프로젝트 스냅샷만 쓴다.
    """
    _merge_conditions()
    src = os.path.abspath(os.path.join(HERE, "..", "tmc49_full_tank"))
    if not os.path.exists(os.path.join(src, "config.json")):
        return False, "Windows 케이스 폴더 없음"
    w = win2wsl(src)
    out_script = (
        "src='" + w + "'; "
        "mkdir -p tools; rm -rf tools/*; "
        "rm -f Allrun .sync_state; "
        "TOOL_OK=1; "
        "for f in \"$src/tools\"/*.py; do "
        "  [ -f \"$f\" ] || continue; "
        "  cp \"$f\" tools/ || TOOL_OK=0; "
        "done; "
        "[ -f \"$src/Allrun\" ] && cp \"$src/Allrun\" . && chmod +x Allrun 2>/dev/null; "
        "ALLRUN_OK=0; [ -f \"$src/Allrun\" ] && [ -f Allrun ] && ALLRUN_OK=1; "
        "[ \"$ALLRUN_OK\" -eq 0 ] && echo 'ERROR: Allrun copy failed'; "
        "if [ \"$ALLRUN_OK\" -eq 1 ] && [ \"$TOOL_OK\" -eq 1 ]; then "
        "  echo 'SYNC_STATUS=1'; else echo 'SYNC_STATUS=0'; fi"
    )
    ok, out = wsl(f"cd {WSL_CASE} || exit 1; {out_script}")
    txt = (out or "").strip()
    return ok and "SYNC_STATUS=1" in txt, (txt or "sync ok")

SYSSTAT = {}
STORAGESTAT = {}
RAW_ARCHIVE_STATE = {"busy": False, "msg": "", "archived_frames": 0,
                     "archived_bytes": 0, "last_time": None}
RAW_ARCHIVE_LK = threading.Lock()
RAW_ARCHIVE_WAKE = threading.Event()
_SYS_COLLECT_LK = threading.Lock()
_STORAGE_COLLECT_LK = threading.Lock()

def _raw_archive_index_path(root):
    return os.path.join(root, ".cfd_studio_archive.json")

def _raw_archive_load_index(root):
    obj = _read_json_file(_raw_archive_index_path(root)) or {}
    if not isinstance(obj.get("runs"), dict): obj["runs"] = {}
    obj.setdefault("version", 1)
    return obj

def _transfer_raw_archive_index(old_root, new_root, rid):
    """이동한 프로젝트의 집계 항목만 새 CFD Studio 인덱스로 합친다."""
    old_root, new_root, rid = str(old_root or "").strip(), str(new_root or "").strip(), str(rid or "")
    if not old_root or not new_root or not rid:
        return False
    if os.path.normcase(os.path.normpath(old_root)) == os.path.normcase(os.path.normpath(new_root)):
        return True
    old_path = _raw_archive_index_path(old_root)
    if not os.path.isfile(old_path):
        return False
    old_index = _raw_archive_load_index(old_root)
    old_run = (old_index.get("runs") or {}).get(rid)
    if not isinstance(old_run, dict):
        return False
    os.makedirs(new_root, exist_ok=True)
    new_index = _raw_archive_load_index(new_root)
    new_run = new_index["runs"].setdefault(rid, {"times": {}})
    new_run.setdefault("times", {}).update(old_run.get("times") or {})
    for field in ("updated_at", "source_case"):
        if old_run.get(field) is not None:
            new_run[field] = old_run[field]
    new_index.update(updated_at=time.time(), app_ver=APP_VER)
    meta_write(_raw_archive_index_path(new_root), new_index)
    old_index["runs"].pop(rid, None)
    old_index.update(updated_at=time.time(), app_ver=APP_VER)
    meta_write(old_path, old_index)
    return True

def _reconcile_raw_archive_index(root, rid, run_dir):
    """완료된 Raw 폴더와 집계 파일을 대조해 강제 종료 때의 인덱스 누락을 복구한다."""
    times_dir = os.path.join(str(run_dir or ""), "times")
    if not root or not rid or not os.path.isdir(times_dir):
        return False
    index = _raw_archive_load_index(root)
    run = index["runs"].setdefault(str(rid), {"times": {}})
    times = run.setdefault("times", {})
    changed = False
    try:
        names = os.listdir(times_dir)
    except OSError:
        return False
    for name in names:
        frame = os.path.join(times_dir, name)
        if name in times or not os.path.isfile(os.path.join(frame, ".cfd_complete")):
            continue
        size = 0
        try:
            for base, _, files in os.walk(frame):
                for filename in files:
                    if filename != ".cfd_complete":
                        size += os.path.getsize(os.path.join(base, filename))
        except OSError:
            continue
        times[name] = size
        changed = True
    if changed:
        run.update(updated_at=time.time(), source_case=str(WSL_CASE))
        index.update(updated_at=time.time(), app_ver=APP_VER)
        meta_write(_raw_archive_index_path(root), index)
    return True

def _raw_archive_index_totals(index):
    frames = total = 0
    for run in (index.get("runs") or {}).values():
        times = (run or {}).get("times") or {}
        frames += len(times)
        for value in times.values():
            try: total += max(0, int(value))
            except Exception: pass
    return frames, total

def _raw_archive_record(root, rid, sim_time, size):
    index = _raw_archive_load_index(root)
    run = index["runs"].setdefault(str(rid), {"times": {}})
    run.setdefault("times", {})[str(sim_time)] = int(size)
    run.update(updated_at=time.time(), source_case=str(WSL_CASE))
    index.update(updated_at=time.time(), app_ver=APP_VER)
    meta_write(_raw_archive_index_path(root), index)
    pd = proj_dir(rid)
    if os.path.isdir(pd):
        mp = os.path.join(pd, "meta.json")
        project_meta = _read_json_file(mp) or {}
        project_meta["raw_archive_root"] = root
        project_meta["raw_archive_run"] = _project_raw_run_path(rid, root)
        meta_write(mp, project_meta)
    frames, total = _raw_archive_index_totals(index)
    RAW_ARCHIVE_STATE.update(archived_frames=frames, archived_bytes=total,
                             last_time=str(sim_time), msg="보관 완료")

def _raw_archive_script(case_token, archive_wsl, run_wsl, rid, viz_wsl, required):
    """완전히 닫힌 고빈도 프레임 한 시각을 검증·이동하는 WSL 스크립트.

    p_rgh가 있는 전체 상태는 재개 앵커이므로 대상에서 제외한다. 최신 시각도
    기록 중일 수 있어 제외한다. 원본은 복사본 SHA-256 일치 후에만 링크로 교체한다.
    """
    template = r'''
set -u
cd __CASE__ 2>/dev/null || { echo 'ARCHIVE_ERROR=WSL 케이스 없음'; exit 0; }
CASE=$(pwd -P)
ROOT=__ROOT__
RUNROOT=__RUNROOT__
RID=__RID__
VIZROOT=__VIZROOT__
NEED_BUB=__NEED_BUB__
NEED_PHASE=__NEED_PHASE__
NEED_FLOW=__NEED_FLOW__
NEED_THERM=__NEED_THERM__
NEED_PRESSURE=__NEED_PRESSURE__
NEED_TURBULENCE=__NEED_TURBULENCE__
MARK=$(cat .cfd_studio_runid 2>/dev/null | tr -cd '0-9')
[ -n "$RID" ] && [ "$MARK" = "$RID" ] || { echo 'ARCHIVE_SKIP=프로젝트 표시 불일치'; exit 0; }
[ -d "$ROOT" ] && [ -w "$ROOT" ] || { echo 'ARCHIVE_ERROR=보관 폴더 접근 불가'; exit 0; }
renice 19 -p $$ >/dev/null 2>&1 || true
ionice -c3 -p $$ >/dev/null 2>&1 || true
PROCS=$(find . -mindepth 1 -maxdepth 1 -type d -printf '%f\n' 2>/dev/null | grep -E '^processor[0-9]+$' | sort)
[ -n "$PROCS" ] || { echo 'ARCHIVE_SKIP=processor 원본 없음'; exit 0; }
mkdir -p "$RUNROOT/times" || { echo 'ARCHIVE_ERROR=보관 폴더 생성 실패'; exit 0; }

# 이전 복사가 중단됐더라도 같은 시각의 최종본이 SHA-256 검증을
# 마친 상태면 남은 임시 복사는 중복 데이터이므로 안전하게 정리한다.
for STALE in "$RUNROOT"/.partial_*; do
  [ -d "$STALE" ] || continue
  PART=${STALE##*/.partial_}; PT=${PART%_*}
  [ -f "$RUNROOT/times/$PT/.cfd_complete" ] && rm -rf -- "$STALE"
done

# 전원 종료 등으로 링크 교체 중 끊겼다면, 검증 완료 표시가 있는 복사본으로만
# 남은 processor를 마저 연결한다. 모든 링크가 확인되기 전에는 백업을 지우지 않는다.
REC_TIMES=$(find processor* -mindepth 1 -maxdepth 1 -type d -name '.cfd_archive_backup_*' -printf '%f\n' 2>/dev/null | sed 's/^\.cfd_archive_backup_//' | sort -u)
for RT in $REC_TIMES; do
  FINAL="$RUNROOT/times/$RT"; ROK=1
  if [ -f "$FINAL/.cfd_complete" ]; then
    for P in $PROCS; do
      SRC="$P/$RT"; B="$P/.cfd_archive_backup_$RT"
      if [ -L "$SRC" ] && [ -d "$SRC" ]; then continue; fi
      if [ -d "$B" ] && [ ! -e "$SRC" ] && [ ! -L "$SRC" ]; then
        ln -s "$FINAL/$P" "$SRC" 2>/dev/null || ROK=0
      elif [ -d "$SRC" ] && [ ! -L "$SRC" ] && [ ! -e "$B" ]; then
        mv "$SRC" "$B" && ln -s "$FINAL/$P" "$SRC" 2>/dev/null || ROK=0
      else ROK=0; fi
    done
    if [ "$ROK" -eq 1 ]; then
      for P in $PROCS; do [ -L "$P/$RT" ] && [ -d "$P/$RT" ] || ROK=0; done
    fi
    if [ "$ROK" -eq 1 ]; then for P in $PROCS; do rm -rf -- "$P/.cfd_archive_backup_$RT"; done; fi
  else
    for P in $PROCS; do
      SRC="$P/$RT"; B="$P/.cfd_archive_backup_$RT"
      if [ -d "$B" ] && [ ! -e "$SRC" ] && [ ! -L "$SRC" ]; then mv "$B" "$SRC" 2>/dev/null || true; fi
    done
  fi
done

LATEST=$(for D in processor0/[0-9]*; do [ -e "$D" ] || [ -L "$D" ] || continue; basename "$D"; done | grep -E '^[0-9]+([.][0-9]+)?([eE][+-]?[0-9]+)?$' | sort -g | tail -1)
T=''
for CAND in $(find processor0 -mindepth 1 -maxdepth 1 -type d -printf '%f\n' 2>/dev/null | grep -E '^[0-9]+([.][0-9]+)?([eE][+-]?[0-9]+)?$' | sort -g); do
  [ "$CAND" != 0 ] || continue
  [ "$CAND" != "$LATEST" ] || continue
  # Raw를 느린 외부 드라이브로 옮기기 전에 선택된 시각화 변환이 끝났어야 한다.
  # 이 순서를 지켜야 reconstructPar가 /mnt/d 링크를 다시 읽는 병목을 피할 수 있다.
  READY=1
  if [ "$NEED_BUB" -eq 1 ]; then
    [ -f "$VIZROOT/bub_$CAND.bin" ] || [ -f "$VIZROOT/alpha.vapour_$CAND" ] || READY=0
  fi
  [ "$NEED_PHASE" -eq 0 ] || [ -f "$VIZROOT/phase_$CAND.bin" ] || READY=0
  [ "$NEED_FLOW" -eq 0 ] || [ -f "$VIZROOT/flow_$CAND.bin" ] || READY=0
  [ "$NEED_THERM" -eq 0 ] || [ -f "$VIZROOT/therm_$CAND.bin" ] || READY=0
  [ "$NEED_PRESSURE" -eq 0 ] || [ -f "$VIZROOT/pressure_$CAND.bin" ] || READY=0
  [ "$NEED_TURBULENCE" -eq 0 ] || [ -f "$VIZROOT/turbulence_$CAND.bin" ] || READY=0
  [ "$READY" -eq 1 ] || continue
  REF=$(find "processor0/$CAND" -maxdepth 1 -type f \( -name 'alpha.vapour' -o -name 'alpha.water' -o -name U -o -name T -o -name p -o -name k -o -name epsilon \) -size +0c -printf '%f\n' 2>/dev/null | sort)
  [ -n "$REF" ] || continue
  OK=1
  for P in $PROCS; do
    [ -d "$P/$CAND" ] && [ ! -L "$P/$CAND" ] || { OK=0; break; }
    [ ! -e "$P/$CAND/p_rgh" ] || { OK=0; break; }
    [ -z "$(find "$P/$CAND" -type f -newermt '-45 seconds' -print -quit 2>/dev/null)" ] || { OK=0; break; }
    CUR=$(find "$P/$CAND" -maxdepth 1 -type f \( -name 'alpha.vapour' -o -name 'alpha.water' -o -name U -o -name T -o -name p -o -name k -o -name epsilon \) -size +0c -printf '%f\n' 2>/dev/null | sort)
    [ "$CUR" = "$REF" ] || { OK=0; break; }
  done
  [ "$OK" -eq 1 ] && { T="$CAND"; break; }
done
[ -n "$T" ] || { echo 'ARCHIVE_SKIP=완료된 이동 대상 없음'; exit 0; }

FINAL="$RUNROOT/times/$T"
STAGE="$RUNROOT/.partial_${T}_$$"
SRC_MAN="$RUNROOT/.source_${T}_$$.sha256"
DST_MAN="$RUNROOT/.copy_${T}_$$.sha256"
make_source_manifest(){
  : > "$SRC_MAN"
  for P in $PROCS; do
    (cd "$P/$T" && find . -type f -print0 | sort -z | while IFS= read -r -d '' F; do
      H=$(sha256sum "$F" | awk '{print $1}'); S=$(stat -c %s "$F")
      printf '%s %s ./%s/%s\n' "$H" "$S" "$P" "${F#./}"
    done) >> "$SRC_MAN" || return 1
  done
}
make_copy_manifest(){
  (cd "$1" && find . -type f ! -name '.cfd_complete' -print0 | sort -z | while IFS= read -r -d '' F; do
    H=$(sha256sum "$F" | awk '{print $1}'); S=$(stat -c %s "$F")
    printf '%s %s %s\n' "$H" "$S" "$F"
  done) > "$DST_MAN"
}
make_source_manifest || { echo 'ARCHIVE_ERROR=원본 검증 목록 생성 실패'; exit 0; }
BYTES=$(awk '{s+=$2} END{printf "%.0f",s}' "$SRC_MAN")
if [ -f "$FINAL/.cfd_complete" ]; then
  make_copy_manifest "$FINAL" || { echo 'ARCHIVE_ERROR=기존 복사본 검증 실패'; exit 0; }
else
  FREE=$(df -Pk "$ROOT" 2>/dev/null | awk 'NR==2{printf "%.0f",$4*1024}')
  [ -n "$FREE" ] && [ "$FREE" -gt $((BYTES + 1073741824)) ] || { rm -f "$SRC_MAN"; echo 'ARCHIVE_ERROR=보관 공간 부족'; exit 0; }
  mkdir -p "$STAGE" || { rm -f "$SRC_MAN"; echo 'ARCHIVE_ERROR=임시 폴더 생성 실패'; exit 0; }
  for P in $PROCS; do cp -a "$P/$T" "$STAGE/$P" || { echo 'ARCHIVE_ERROR=복사 실패'; exit 0; }; done
  make_copy_manifest "$STAGE" || { echo 'ARCHIVE_ERROR=복사본 검증 목록 생성 실패'; exit 0; }
  cmp -s "$SRC_MAN" "$DST_MAN" || { echo 'ARCHIVE_ERROR=SHA-256 불일치'; exit 0; }
  [ ! -e "$FINAL" ] || { echo 'ARCHIVE_ERROR=보관 위치 충돌'; exit 0; }
  mv "$STAGE" "$FINAL" || { echo 'ARCHIVE_ERROR=복사본 확정 실패'; exit 0; }
  printf '%s\n' "$RID/$T" > "$FINAL/.cfd_complete"
fi
cmp -s "$SRC_MAN" "$DST_MAN" || { echo 'ARCHIVE_ERROR=기존 복사본 SHA-256 불일치'; exit 0; }
rm -f "$SRC_MAN" "$DST_MAN"

# 프로젝트가 바뀌었으면 복사본만 남기고 현재 케이스는 전혀 수정하지 않는다.
NOW=$(cat .cfd_studio_runid 2>/dev/null | tr -cd '0-9')
[ "$NOW" = "$RID" ] || { echo 'ARCHIVE_SKIP=프로젝트 전환 감지'; exit 0; }
LINKED=''
for P in $PROCS; do
  SRC="$P/$T"; B="$P/.cfd_archive_backup_$T"
  [ -d "$SRC" ] && [ ! -L "$SRC" ] && [ ! -e "$B" ] || { echo 'ARCHIVE_ERROR=원본 상태 변경'; exit 0; }
done
for P in $PROCS; do
  SRC="$P/$T"; B="$P/.cfd_archive_backup_$T"
  if ! mv "$SRC" "$B"; then
    for Q in $LINKED; do rm -f "$Q/$T"; mv "$Q/.cfd_archive_backup_$T" "$Q/$T" 2>/dev/null || true; done
    echo 'ARCHIVE_ERROR=원본 대기 이동 실패'; exit 0
  fi
  if ln -s "$FINAL/$P" "$SRC"; then LINKED="$LINKED $P"; else
    mv "$B" "$SRC" 2>/dev/null || true
    for Q in $LINKED; do rm -f "$Q/$T"; mv "$Q/.cfd_archive_backup_$T" "$Q/$T" 2>/dev/null || true; done
    echo 'ARCHIVE_ERROR=링크 생성 실패'; exit 0
  fi
done
for P in $PROCS; do [ -L "$P/$T" ] && [ -d "$P/$T" ] || { echo 'ARCHIVE_ERROR=링크 검증 실패'; exit 0; }; done
for P in $PROCS; do rm -rf -- "$P/.cfd_archive_backup_$T"; done
echo "ARCHIVED=$T"
echo "ARCHIVED_BYTES=$BYTES"
'''
    return (template.replace("__CASE__", case_token)
                    .replace("__ROOT__", _shq(archive_wsl))
                    .replace("__RUNROOT__", _shq(run_wsl))
                    .replace("__RID__", _shq(str(rid)))
                    .replace("__VIZROOT__", _shq(viz_wsl))
                    .replace("__NEED_BUB__", "1" if "bubble" in required else "0")
                    .replace("__NEED_PHASE__", "1" if "phase" in required else "0")
                    .replace("__NEED_FLOW__", "1" if "flow" in required else "0")
                    .replace("__NEED_THERM__", "1" if "therm" in required else "0")
                    .replace("__NEED_PRESSURE__", "1" if "pressure" in required else "0")
                    .replace("__NEED_TURBULENCE__", "1" if "turbulence" in required else "0"))

def _raw_archive_once(case_token=None, raw_dir=None, rid=None):
    """한 시각만 보관한다. 반환값은 archived/skip/error 중 하나다."""
    if not RAW_ARCHIVE_LK.acquire(blocking=False):
        return "skip", "이미 보관 중"
    io_lock = None
    io_acquired = False
    try:
        run_id = re.sub(r"[^0-9]", "", str(rid or _active_rid() or ""))
        if not run_id:
            RAW_ARCHIVE_STATE.update(busy=False, msg="실행 프로젝트 대기")
            return "skip", "실행 프로젝트 대기"
        io_lock = _raw_io_lock(run_id)
        io_acquired = io_lock.acquire(blocking=False)
        if not io_acquired:
            RAW_ARCHIVE_STATE.update(busy=False, msg="시각화 변환 완료 대기")
            return "skip", "시각화 변환 완료 대기"
        # 첫 보관 시 프로젝트에 루트를 고정한다. 전역 설정을 바꿔도 이미 시작된
        # 프로젝트의 원본이 여러 드라이브에 섞이지 않는다.
        root = _resolved_project_raw_root(run_id, raw_dir)
        ok, root, msg = _validate_raw_archive_dir(root)
        if not ok or not root:
            RAW_ARCHIVE_STATE.update(busy=False, msg=msg)
            return "error", msg
        RAW_ARCHIVE_STATE.update(busy=True, msg="원본 검증 중")
        pd = proj_dir(run_id)
        meta = _read_json_file(os.path.join(pd, "meta.json")) or {}
        run_dir = _project_raw_run_path(run_id, root)
        if not run_dir:
            RAW_ARCHIVE_STATE.update(busy=False, msg="프로젝트 Raw 보관 경로를 만들 수 없습니다")
            return "error", "프로젝트 Raw 보관 경로를 만들 수 없습니다"
        # 양쪽 CFD Studio에서 Project/<프로젝트명>/Raw_Data 구조를 동일하게 쓴다.
        # 기존 프로젝트의 meta.json 경로는 유지해 실행 중 링크가 바뀌지 않게 한다.
        if not meta.get("raw_archive_run"):
            meta["raw_archive_root"] = root
            meta["raw_archive_run"] = run_dir
            meta_write(os.path.join(pd, "meta.json"), meta)
        outputs = (meta.get("settings") or {}).get("output_fields")
        # 계산 중에는 닫힌 Raw를 선택 드라이브의 CFD Studio에 먼저 보관한다. 시각화는 계산 종료 후
        # 이 Raw를 읽어 생성해 솔버와 reconstructPar의 대량 읽기가 겹치지 않게 한다.
        solver_running = bool(get_status().get("running"))
        required = set() if solver_running else set(
            outputs if isinstance(outputs, list) else ("bubble", "phase", "flow", "therm"))
        script = _raw_archive_script(case_token or _wsl_case_token(), win2wsl(root), win2wsl(run_dir),
                                     run_id, win2wsl(pd), required)
        ok_w, out = wsl(script, timeout=900)
        m = re.search(r"(?m)^ARCHIVED=(.+)$", out or "")
        b = re.search(r"(?m)^ARCHIVED_BYTES=([0-9]+)$", out or "")
        if ok_w and m and b:
            sim_time, size = m.group(1).strip(), int(b.group(1))
            _raw_archive_record(root, run_id, sim_time, size)
            RAW_ARCHIVE_STATE.update(busy=False, msg="보관 완료")
            return "archived", sim_time
        err = re.search(r"(?m)^ARCHIVE_ERROR=(.+)$", out or "")
        skip = re.search(r"(?m)^ARCHIVE_SKIP=(.+)$", out or "")
        if err or not ok_w:
            msg = (err.group(1).strip() if err else (out or "WSL 보관 작업 실패")[-160:])
            RAW_ARCHIVE_STATE.update(busy=False, msg=msg)
            return "error", msg
        msg = skip.group(1).strip() if skip else "완료된 이동 대상 없음"
        RAW_ARCHIVE_STATE.update(busy=False, msg=msg)
        return "skip", msg
    finally:
        RAW_ARCHIVE_STATE["busy"] = False
        if io_acquired:
            io_lock.release()
        RAW_ARCHIVE_LK.release()

def raw_archive_loop():
    """설정된 PC에서만 과거 고빈도 원본을 한 시각씩 저우선순위 보관한다."""
    time.sleep(12)                              # 앱·WSL 기동 점검과 디스크 접근을 겹치지 않음
    loaded_root = None
    while True:
        active = _active_rid()
        root = _resolved_project_raw_root(active) if active else _raw_archive_dir()
        if root and root != loaded_root:
            ok, norm, msg = _validate_raw_archive_dir(root, require_writable=False)
            if ok:
                idx = _raw_archive_load_index(norm)
                frames, total = _raw_archive_index_totals(idx)
                RAW_ARCHIVE_STATE.update(archived_frames=frames, archived_bytes=total, msg="사용 가능")
                loaded_root = root
            else:
                RAW_ARCHIVE_STATE.update(msg=msg)
        active = _active_rid()
        active_meta = _read_json_file(os.path.join(proj_dir(active), "meta.json")) or {} if active else {}
        if root and active_meta.get("execution_project_id") and get_status().get("running") and not _extract_state(active).get("busy"):
            try: result, _ = _raw_archive_once()
            except Exception as e:
                RAW_ARCHIVE_STATE.update(busy=False, msg="보관 점검 실패: " + str(e)[:100])
                result = "error"
        else:
            result = "skip"
        RAW_ARCHIVE_WAKE.wait(timeout=60)
        RAW_ARCHIVE_WAKE.clear()

def _tree_bytes(root):
    """프로젝트·Trash의 실제 파일 크기 합. 링크는 따라가지 않아 중복 집계를 막는다."""
    total = 0
    stack = [root]
    while stack:
        p = stack.pop()
        try:
            with os.scandir(p) as it:
                for e in it:
                    try:
                        if e.is_symlink():
                            continue
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        elif e.is_file(follow_symlinks=False):
                            total += e.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass
        except OSError:
            pass
    return total

def _storage_collect():
    """CFD Studio 파생 데이터 + WSL 원본 + 외부 원본 보관량과 여유 공간.

    WSL du는 파일이 많을 수 있어 하드웨어 3초 폴링과 분리하고,
    낮은 CPU·I/O 우선순위로 실행한다.
    """
    d = {"windows_bytes": _tree_bytes(PROJECT_DIR) + _tree_bytes(TRASH_DIR)}
    try:
        du = shutil.disk_usage(HERE)
        d.update(disk_total_bytes=int(du.total), disk_free_bytes=int(du.free))
        drive = os.path.splitdrive(os.path.abspath(HERE))[0]
        if not drive:
            m = re.match(r"^/mnt/([A-Za-z])(?:/|$)", os.path.abspath(HERE))
            drive = (m.group(1).upper() + ":") if m else os.path.abspath(HERE)
        d["drive"] = drive
    except OSError:
        pass
    try:
        ok, out = wsl(f"ionice -c3 nice -n 19 du -sb {_wsl_case_token()} 2>/dev/null | awk '{{print $1; exit}}'", timeout=45)
        vals = re.findall(r"(?m)^([0-9]+)\s*$", out or "")
        if ok and vals:
            d["wsl_bytes"] = int(vals[-1])
    except Exception:
        pass
    root = _raw_archive_dir()
    if root:
        ok_a, norm, msg = _validate_raw_archive_dir(root, require_writable=False)
        d.update(archive_enabled=True, archive_path=norm or root, archive_available=bool(ok_a))
        if ok_a:
            try:
                idx = _raw_archive_load_index(norm)
                frames, archive_bytes = _raw_archive_index_totals(idx)
                embedded = _same_storage_volume(PROJECT_DIR, norm)
                d.update(archive_bytes=archive_bytes, archive_frames=frames,
                         archive_embedded=embedded)
                adu = shutil.disk_usage(norm)
                d.update(archive_disk_total_bytes=int(adu.total), archive_disk_free_bytes=int(adu.free))
                adrive = os.path.splitdrive(os.path.abspath(norm))[0]
                if not adrive:
                    am = re.match(r"^/mnt/([A-Za-z])(?:/|$)", os.path.abspath(norm))
                    adrive = (am.group(1).upper() + ":") if am else os.path.abspath(norm)
                d["archive_drive"] = adrive
            except OSError:
                d["archive_available"] = False
        else:
            d["archive_error"] = msg
    else:
        d["archive_enabled"] = False
    archive_extra = 0 if d.get("archive_embedded") else int(d.get("archive_bytes") or 0)
    d["total_bytes"] = int(d["windows_bytes"] + int(d.get("wsl_bytes") or 0) + archive_extra)
    d["sampled_at"] = time.time()
    return d

def _storage_refresh():
    if not _STORAGE_COLLECT_LK.acquire(blocking=False):
        return False
    try:
        d = _storage_collect()
        if d:
            STORAGESTAT.clear(); STORAGESTAT.update(d)
            return True
        return False
    finally:
        _STORAGE_COLLECT_LK.release()

def _drive_usage():
    """Read local fixed-volume capacity without launching a shell or scanning files."""
    if os.name != "nt":
        return []
    import ctypes
    kernel = ctypes.windll.kernel32
    kernel.GetLogicalDrives.restype = ctypes.c_ulong
    kernel.GetDriveTypeW.argtypes = [ctypes.c_wchar_p]
    kernel.GetDriveTypeW.restype = ctypes.c_uint
    mask = kernel.GetLogicalDrives()
    drives = []
    for index in range(26):
        if not mask & (1 << index):
            continue
        letter = chr(65 + index) + ":"
        root = letter + "\\"
        if kernel.GetDriveTypeW(root) != 3:  # Fixed local volumes only
            continue
        item = {"drive": letter}
        try:
            usage = shutil.disk_usage(root)
            item.update(total_bytes=int(usage.total), free_bytes=int(usage.free))
        except OSError:
            pass
        drives.append(item)
    return drives

_HARDWARE_MONITOR = None

def _sys_collect():
    global _HARDWARE_MONITOR
    if _HARDWARE_MONITOR is None:
        from cfd_studio.hardware_monitor import Monitor
        _HARDWARE_MONITOR = Monitor(smi=NVIDIA_SMI, drives=_drive_usage)
    return _HARDWARE_MONITOR.sample()

def _sys_refresh():
    """하드웨어 현재값을 한 번 갱신한다.

    WSL 상태 조회와 독립된 수집기를 사용한다. 장치 식별은 유지하되
    측정 실패는 None으로 전달하고 오래된 사용률을 현재 값으로 표시하지 않는다.
    """
    global SYSSTAT
    if not _SYS_COLLECT_LK.acquire(blocking=False):
        return False
    try:
        attempted_at = time.time()
        SYSSTAT["last_attempt_at"] = attempted_at
        d = _sys_collect()
        if d:
            SYSSTAT = {**d, "last_attempt_at": attempted_at}
            return bool(d.get("ok"))
        if SYSSTAT.get("sampled_at"):
            SYSSTAT.update(ok=True, stale=True)
        else:
            SYSSTAT.update(ok=False, stale=True)
        return False
    finally:
        _SYS_COLLECT_LK.release()

def sys_loop():
    while True:
        started = time.monotonic()
        try:
            _sys_refresh()
        except Exception:
            pass
        time.sleep(max(.1, 1 - (time.monotonic() - started)))

def storage_loop():
    while True:
        try:
            _storage_refresh()
        except Exception:
            pass
        time.sleep(120)

def autosync_loop():
    """자동 동기화 — 주기를 고정하지 않고, 스냅샷이 실제로 생기는 벽시계 속도를 실측해 맞춘다.
    새 스냅샷 n개를 변환할 때마다 (경과시간/n)으로 '스냅샷 1개당 생성 시간'을 추정(EMA)하고
    다음 확인 시점을 그 1.5배로 잡는다(스냅샷 1~2개 모일 때쯤 재방문).
    새 것이 없으면 주기를 점점 늘려(×1.5) 완주·정지 상태에서 부하를 줄인다. 범위 5초~5분."""
    period = 15.0          # 첫 견적 전 초기값
    ema = None             # 스냅샷 1개당 생성 시간(실측, EMA)
    last_wall = time.time()
    while True:
        AUTOSYNC_EV.wait(timeout=max(5.0, min(300.0, period)))
        AUTOSYNC_EV.clear()
        active = _active_rid()
        S = _extract_state(active)
        if not STATE.get("autosync") or S.get("busy"):
            continue
        S["sel"] = STATE.get("autosel") or {"alpha": True, "flow": True, "therm": True, "phase": True}
        try:
            extract_worker(active)
        except Exception:
            pass
        new = S.get("done", 0)
        now = time.time()
        if new > 0:
            elapsed = now - last_wall
            last_wall = now
            if elapsed > 2:                      # 켜자마자 밀린 것 일괄 변환한 경우는 견적에서 제외
                per = min(300.0, elapsed / new)
                ema = per if ema is None else 0.6 * ema + 0.4 * per
                period = max(5.0, min(300.0, ema * 1.5))
        else:
            period = min(300.0, period * 1.5)    # 새 스냅샷 없음 — 한동안 더 길게
        STATE["autosync_period"] = round(max(5.0, min(300.0, period)))

def _kill_previous():
    """포트를 잡고 있는 이전 CFD Studio 프로세스 종료 (업데이트 후 옛 화면이 계속 뜨는 문제 방지)"""
    try:
        out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10, creationflags=0x08000000 if os.name == "nt" else 0).stdout
    except Exception:
        return
    me = str(os.getpid())
    for line in out.splitlines():
        u = line.upper()
        if f":{PORT}" in line and "LISTEN" in u:
            pid = line.split()[-1]
            if pid.isdigit() and pid != me:
                print(f"이전 CFD Studio(PID {pid}) 자동 종료…")
                mine = False                           # CFD Studio임이 확인된 PID만 종료한다.
                try:                                       # 남의 프로세스를 무조건 taskkill 하던
                    import urllib.request as _u            # 동작은 다른 랩 PC에 넘길 수 없다
                    with _u.urlopen(f"http://127.0.0.1:{PORT}/api/info", timeout=3) as _r:
                        mine = b'"cfd-studio"' in _r.read(4000)
                except Exception:
                    old_pid, _ = _studio_pid_record()
                    mine = old_pid == int(pid)
                if mine:
                    subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True)
                else:
                    print(f"[CFD Studio] 포트 {PORT} 를 다른 프로그램이 쓰고 있습니다 (PID {pid}) — "
                          f"studio_config.json 의 port 를 바꾸세요.")
    time.sleep(1.2)

def _claim_studio_pid():
    """이전 Studio가 포트를 놓고 스레드만 남은 경우도 기록 PID로 종료한다."""
    me, started = os.getpid(), PROCESS_STARTED
    old, old_started = _studio_pid_record()
    if old and old != me and old_started and POWERSHELL_EXE:
        try:
            ps = (f"$p=Get-Process -Id {old} -ErrorAction SilentlyContinue; if($p){{"
                  "[Console]::Write(($p.StartTime.ToUniversalTime()-[datetime]'1970-01-01').TotalSeconds)}}")
            r = subprocess.run([POWERSHELL_EXE, "-NoProfile", "-Command", ps],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=8, creationflags=0x08000000 if os.name == "nt" else 0)
            actual = float((r.stdout or "0").strip() or 0)
            if abs(actual - old_started) < 30:
                subprocess.run(["taskkill", "/PID", str(old), "/F"], capture_output=True, creationflags=0x08000000 if os.name == "nt" else 0)
        except Exception:
            pass
    tmp = STUDIO_PIDF + ".tmp"
    with open(tmp, "w", encoding="ascii") as f:
        json.dump({"pid": me, "started": started}, f)
    os.replace(tmp, STUDIO_PIDF)

def _cleanup_orphan_extractors():
    """Studio 강제 교체 뒤 남은 임시 재조립만 정리하고 CFD 솔버는 건드리지 않는다."""
    script = r'''for C in /proc/[0-9]*/cwd; do
  D=$(readlink "$C" 2>/dev/null || true)
  case "$D" in
    /tmp/cfd_studio_reconstruct.*) P=${C#/proc/}; P=${P%/cwd}; kill -TERM "$P" 2>/dev/null || true;;
  esac
done
sleep 1
for D in /tmp/cfd_studio_reconstruct.*; do [ -d "$D" ] && rm -rf -- "$D"; done
'''
    wsl(script, timeout=20)

MIGRATE_LK = threading.Lock()

def _repair_root_markers():
    """과거 버전이 Project 루트에 잘못 둔 실행/대기 마커를 frames 관리영역으로 복귀."""
    for name in ("_runid.txt", "_pending.json"):
        src = os.path.join(PROJECT_DIR, name)
        dst = os.path.join(FRAME_DIR, name)
        if os.path.isfile(src) and not os.path.exists(dst):
            try: shutil.move(src, dst)
            except Exception: pass

def _migrate_project_dirs():
    """구버전 frames/Project와 frames/<rid>를 상위 Project/로 보존 이관.

    실행 숫자 ID는 meta.run_id에 유지하고 실제 폴더명은 화면 프로젝트
    이름으로 변환한다. 충돌 파일은 _runtime에 보존한다.
    """
    if not MIGRATE_LK.acquire(blocking=False):
        return
    try:
        def merge_dir(s, t, tag):
            if not os.path.isdir(s):
                return
            if not os.path.isdir(t):
                try: shutil.move(s, t); return
                except Exception: os.makedirs(t, exist_ok=True)
            conflict = ""
            for f in list(os.listdir(s)):
                ss, tt = os.path.join(s, f), os.path.join(t, f)
                if not os.path.exists(tt):
                    try: shutil.move(ss, tt)
                    except Exception: pass
                    continue
                if not conflict:
                    conflict = os.path.join(RUNTIME_DIR, "legacy_conflicts", tag + "_" + str(int(time.time())))
                    os.makedirs(conflict, exist_ok=True)
                try: shutil.move(ss, os.path.join(conflict, f))
                except Exception: pass

        # v39~v48: frames/Project/<id> → Project/<id>
        if os.path.isdir(LEGACY_PROJECT_DIR):
            for d in list(os.listdir(LEGACY_PROJECT_DIR)):
                s = os.path.join(LEGACY_PROJECT_DIR, d)
                if os.path.isdir(s) and _project_key(d):
                    merge_dir(s, os.path.join(PROJECT_DIR, d), "project_" + d)

        # v38 이전: frames/<rid> → Project/<rid>
        for d in os.listdir(FRAME_DIR):
            s = os.path.join(FRAME_DIR, d)
            if not (d.isdigit() and os.path.isdir(s)):
                continue
            t = os.path.join(PROJECT_DIR, d)
            merge_dir(s, t, d)

        # 숫자 폴더를 meta.name 기반 사람 가독 폴더명으로 1회 변환
        for d in list(os.listdir(PROJECT_DIR)):
            pd = os.path.join(PROJECT_DIR, d)
            if not os.path.isdir(pd) or not _project_key(d):
                continue
            _normalize_project_dir(pd, d)
            meta = _read_json_file(os.path.join(pd, "meta.json")) or {}
            if d.isdigit() and meta.get("run_id"):
                target = _unique_project_path(meta.get("name") or d, current=pd)
                if os.path.abspath(target) != os.path.abspath(pd):
                    try: shutil.move(pd, target)
                    except Exception: pass
    finally:
        MIGRATE_LK.release()

def _migrate_frames():
    rid = _active_rid()
    if not rid: return
    root_files = [f for f in os.listdir(FRAME_DIR)                       # "_" 파일은 앱 관리용
                  if os.path.isfile(os.path.join(FRAME_DIR, f)) and not f.startswith("_")]
    if not root_files: return
    pd = proj_dir(rid); os.makedirs(pd, exist_ok=True)
    for f in root_files:
        src, dst = os.path.join(FRAME_DIR, f), os.path.join(pd, f)
        try:
            if f == "meta.json" and os.path.exists(dst):
                # 구버전 공용 진행 meta는 프로젝트 식별자·이름·Raw 경로를 갖지 않는다.
                # 파일 자체를 덮어쓰면 재시작 때 활성 프로젝트가 외부 프로젝트로 바뀐다.
                root_meta = _read_json_file(src) or {}
                project_meta = _read_json_file(dst) or {}
                project_meta["last_time"] = max(float(project_meta.get("last_time") or 0),
                                                float(root_meta.get("last_time") or 0))
                if "completed" not in project_meta and root_meta.get("completed"):
                    project_meta["completed"] = True
                    project_meta["completion_reason"] = root_meta.get("completion_reason") or "end"
                meta_write(dst, project_meta)
                os.remove(src)
            elif os.path.exists(dst):
                conflict = os.path.join(RUNTIME_DIR, "legacy_conflicts", "frames_" + rid)
                os.makedirs(conflict, exist_ok=True)
                shutil.move(src, os.path.join(conflict, f + "_" + uuid.uuid4().hex[:8]))
            else:
                shutil.move(src, dst)
        except Exception:
            pass
    mp = os.path.join(pd, "meta.json")
    if not os.path.exists(mp):
        et = None
        ok, out = wsl(f"cd {WSL_CASE} && {of_bash()} >/dev/null 2>&1; foamDictionary -entry endTime -value system/controlDict 2>/dev/null")
        try: et = float(out.strip().splitlines()[-1])
        except Exception: pass
        try: json.dump({"end": et}, open(mp, "w"))
        except Exception: pass

def _repair_identity():
    """구버전(격자 시각 지문) 시절 끊긴 전환 1회 복구 — [새 프로젝트]로 시작한 실행이
    이전 프로젝트 ID를 물려받아 진행이 이전 프로젝트 위에 표시되던 상태 정리:
    케이스에 실행 마커가 없고 + 대기 중 새 프로젝트가 있고 + 그 생성 이후 계산
    로그가 생겼다면 → 지금 ID를 발급해 그 실행을 새 프로젝트로 올바르게 귀속"""
    try:
        if not os.path.exists(PENDF): return
        pj = json.load(open(PENDF))
        ok, mk = wsl(f"cd {WSL_CASE} && cat .cfd_studio_runid 2>/dev/null; echo ==LM==; "
                     f"stat -c %Y log.icoReactingMultiphaseInterFoam 2>/dev/null")
        if not ok: return
        a, _, b = mk.partition("==LM==")
        if re.sub(r"[^0-9]", "", a): return        # 마커 있음 = 신버전 발급 완료 — 복구 불필요
        try: logm = float(b.strip().splitlines()[-1])
        except Exception: return                   # 계산 로그 없음 = 아직 실행 전 — pending 유지
        if logm <= float(pj.get("created", 0)): return
        rid_new = str(int(time.time()))
        wsl(f"cd {WSL_CASE} && echo {rid_new} > .cfd_studio_runid")
        st = pj.get("settings") or {}
        meta = {"name": pj.get("name") or time.strftime("실행 %m/%d %H:%M"), "settings": st,
                "end": float(st.get("end_time_s") or (get_config() or {}).get("run", {}).get("end_time_s") or 30),
                "end_locked": True, "heal2": True}
        _create_run_project(rid_new, meta["name"], meta)
        with open(os.path.join(FRAME_DIR, "_runid.txt"), "w") as run_file: run_file.write(rid_new)
        os.remove(PENDF)
    except Exception:
        pass

def _startup_check():
    """환경 자가 진단 — 다른 컴퓨터에서 무엇이 빠졌는지 콘솔에 바로 알려 준다"""
    try:
        ok, out = wsl(
            "echo WSL_OK; "
            "if command -v taskset >/dev/null 2>&1; then echo TASKSET; fi; "
            "if command -v mpirun >/dev/null 2>&1; then echo MPI; fi; "
            "if [ -f \"$HOME/.of_gpu_env\" ]; then "
            "  source \"$HOME/.of_gpu_env\" >/dev/null 2>&1 || true; echo GPUENV; "
            "  if [ -f \"${FOAM_MODULE_LIBBIN:-/nonexistent}/libpetscFoam.so\" ] || "
            "     [ -f \"${FOAM_USER_LIBBIN:-/nonexistent}/libpetscFoam.so\" ]; then echo PETSCFOAM; fi; "
            "  if ls \"${PETSC_ARCH_PATH:-/nonexistent}/lib/libpetsc.so\"* >/dev/null 2>&1; then echo PETSCLIB; fi; "
            "  if ls \"${AMGX_DIR:-/nonexistent}/lib/libamgxsh.so\"* >/dev/null 2>&1; then echo AMGXLIB; fi; "
            "fi; "
            f"if grep -qE 'solver[[:space:]]+petsc' {_wsl_case_token()}/system/fvSolution 2>/dev/null; then echo GPUSOLVER; fi; "
            f"if [ -d {_wsl_case_token()} ]; then echo CASE; fi; "
            "if ls -d /usr/lib/openfoam/openfoam*/etc/bashrc >/dev/null 2>&1 || "
            "ls -d /opt/openfoam*/etc/bashrc >/dev/null 2>&1; then echo FOAM; fi"
        )
        if not ok or "WSL_OK" not in out:
            print(f"  [점검] WSL을 실행할 수 없습니다 ({WSL_EXE}) → 설치.bat을 한 번 실행하세요"); return
        miss = []
        if "CASE" not in out: miss.append(f"케이스 폴더({WSL_CASE}) — 설치.bat 실행")
        if "FOAM" not in out: miss.append("OpenFOAM — 설치.bat 실행")
        if "MPI" not in out: miss.append("mpirun(OpenMPI) — OpenFOAM 설치에 포함")
        if "TASKSET" not in out: miss.append("taskset(util-linux) — CPU 상한 기능만 비활성, 계산은 정상")
        print("  [점검] 실행 환경 정상 (WSL·OpenFOAM·케이스 확인됨)" if not miss
              else "  [점검] 확인 필요: " + " / ".join(miss))
        logical, physical = _cpu_topology()
        gi = gpu_index(); gn = (_ENV.get("gpu_info") or {}).get("name", "GPU")
        print(f"  [성능] 논리 CPU {logical}개 중 {cpu_slots()}개({cpu_pct()}% 상한) · 새 프로젝트 MPI {mpi_np()}개 · GPU {gi} {gn}")
        gpu_stack = all(x in out for x in ("GPUENV", "PETSCFOAM", "PETSCLIB", "AMGXLIB"))
        if _solver_mode() == "gpu_only":
            only = _gpu_only_status(refresh=True)
            print("  [GPU Only] " + str(only.get("message") or "전용 환경 확인 실패"))
        elif gpu_stack and "GPUSOLVER" in out:
            print("  [성능] AmgX/PETSc 압력 계산 활성")
        elif gpu_stack:
            print("  [성능] AmgX/PETSc 설치됨 · 현재 fvSolution은 CPU 압력 계산")
        else:
            print("  [성능] AmgX/PETSc 미설치 · CPU 압력 계산 (GPU 준비 파일은 보존됨)")
    except Exception:
        pass

def _safe(fn):
    try: return fn()
    except Exception: return None

class StudioHTTPServer(ThreadingHTTPServer):
    """한 포트에 Studio 인스턴스가 하나만 바인딩되도록 보장한다."""
    allow_reuse_address = False

    def server_bind(self):
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

def main():
    try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass
    _janitor()
    _merge_conditions()
    _repair_root_markers()
    _migrate_project_dirs()
    _migrate_frames()
    _repair_identity()
    _seed_saved_configs()
    try:
        srv = StudioHTTPServer(("127.0.0.1", PORT), H)
    except OSError:
        _kill_previous()
        try:
            srv = StudioHTTPServer(("127.0.0.1", PORT), H)
        except OSError:
            print(f"[CFD Studio] 포트 {PORT} 를 열 수 없습니다 — studio_config.json 의 port 를 바꾸고 다시 실행하세요.")
            try: input("Enter 를 누르면 종료합니다 ")
            except Exception: pass
            return
    _claim_studio_pid()
    from execution_adapters import install as install_execution_adapters
    install_execution_adapters(EXECUTION_WORKSPACE, globals())
    EXECUTION_WORKSPACE.start_queue_service()
    _cleanup_orphan_extractors()
    threading.Thread(target=autosync_loop, daemon=True).start()
    threading.Thread(target=sys_loop, name="cfd-sys", daemon=True).start()
    threading.Thread(target=storage_loop, name="cfd-storage", daemon=True).start()
    threading.Thread(target=raw_archive_loop, name="cfd-raw-archive", daemon=True).start()
    threading.Thread(target=resume_loop, daemon=True).start()
    threading.Thread(target=trash_loop, daemon=True).start()
    threading.Thread(target=_startup_check, daemon=True).start()
    # 시작 시 도구만 갱신한다. 현재 WSL config는 활성 프로젝트의 불변 상태다.
    threading.Thread(target=lambda: _safe(sync_case_files), daemon=True).start()
    print(f"CFD Studio {APP_VER} 실행됨 → http://127.0.0.1:{PORT}  (이 창을 닫으면 프로그램이 종료됩니다)")
    threading.Timer(0.8, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
        try:
            recorded, _ = _studio_pid_record()
            if recorded == os.getpid():
                os.remove(STUDIO_PIDF)
        except (OSError, ValueError):
            pass

if __name__ == "__main__":
    main()
