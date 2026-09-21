# -*- coding: utf-8 -*-
"""config.json(형상·설정 + conditions 조건 배열) → OpenFOAM 케이스 전체 생성기.

사용:
  python3 tools/build_case.py                       # config.json 기본값으로 생성
  python3 tools/build_case.py --condition C3_T20    # config.json conditions 행의 h/Ta 적용
  python3 tools/build_case.py --check               # 생성 없이 검증만

생성 대상: system/{blockMeshDict,setFieldsDict,controlDict},
          0.orig/{T,U,p,p_rgh,alpha.liquid,alpha.vapour,alpha.water},
          constant/{phaseProperties,thermophysicalProperties.{liquid,vapour,water}}
정적 유지: system/{fvSchemes,fvSolution,decomposeParDict}, constant/{g,turbulenceProperties}

0.orig 전체를 생성하는 이유: CFD Studio의 sync_case_files()는 config.json·tools·Allrun만
WSL 케이스로 옮기므로, 경계조건을 바꾸려면 생성기가 직접 써야 반영된다.
"""
import json, csv, math, argparse, os, sys

R_GAS, P_ATM = 8.314462618, 101325.0
RAW = {}             # 조건 적용 전 config 원본
OVERRIDDEN = {}      # CFD Studio '직접 입력'으로 덮인 키 — 사용자 입력을 자동 재산정이 덮지 않도록

# ---------------------------------------------------------------- 설정 읽기
def load(root, condition=None):
    cfg = json.load(open(os.path.join(root, 'config.json')))
    RAW.update(json.loads(json.dumps(cfg)))       # 조건 적용 전 원본 (오버라이드 비교 기준)
    if condition:
        rows = {str(r.get('name')): r for r in (cfg.get('conditions') or []) if isinstance(r, dict)}
        if not rows:                       # 구버전 케이스 호환 (conditions.csv)
            try: rows = {r['name']: r for r in csv.DictReader(open(os.path.join(root, 'conditions.csv')))}
            except OSError: rows = {}
        if condition not in rows:
            sys.exit(f"[오류] config.json conditions에 '{condition}' 없음. 보유: {', '.join(rows)}")
        r = rows[condition]
        cfg['coil']['h_W_m2K'] = float(r['h_model_W_m2K'])
        cfg['coil']['Ta_C'] = float(r['Ta_C'])
        cfg['_condition'] = condition
        # 조건별 냉각 성능은 실측 막계수 h_meas 에 비례한다고 보고 UA_target 을 배율로 옮긴다.
        # (h_model 열은 면적 환산 자리값이라 기준으로 쓰지 않음 — 검토서 A2)
        # 조건별 UA 는 실측 R_DI→HX 의 역수(UA_meas_W_K). 없으면 기본 UA_target 유지.
        try:
            um = float(r.get('UA_meas_W_K') or 0)
            if um > 0: cfg['coil']['UA_target_W_K'] = um
        except Exception:
            pass
    return cfg

# ---------------------------------------------------------------- 검증
def validate(c):
    W, D, H = c['tank']['width_mm'], c['tank']['depth_mm'], c['tank']['liquid_height_mm']
    err = []
    def inbox(b, name, zfree=False):
        if not (0 <= b['x0'] < b['x1'] <= W and 0 <= b['y0'] < b['y1'] <= H):
            err.append(f"{name}: x/y 범위가 수조({W}x{H})를 벗어남")
        if not zfree and not (0 <= b['z0'] < b['z1'] <= D):
            err.append(f"{name}: z 범위가 깊이({D})를 벗어남")
    inbox(c['board'], 'board'); inbox(c['coil'], 'coil')
    if not (0 < c['layers']['dielectric_mm'] < H):
        err.append("layers.dielectric_mm 은 0~liquid_height 사이여야 함")
    b = c['board']
    for i, u in enumerate(c['heater']['cpus']):
        if not (b['x0'] <= u['x0'] < u['x1'] <= b['x1'] and b['y0'] <= u['y0'] < u['y1'] <= b['y1']):
            err.append(f"cpus[{i}] 가 board footprint 밖")
    if not (c['coil']['y0'] >= c['board']['y1'] or c['coil']['y1'] <= c['board']['y0']):
        err.append("coil 과 board 상자가 y에서 겹침")
    if c['phase_change']['evap_C'] <= 0 or c['phase_change']['cond_C'] >= 0:
        err.append("phase_change: evap_C>0, cond_C<0 이어야 함")
    if float(c['coil'].get('h_W_m2K') or 0) <= 0:
        err.append("coil.h_W_m2K 는 0보다 커야 함")
    if float(c['dielectric_fluid'].get('molWeight') or 0) <= 0:
        err.append("하단 비전도 액체 molWeight 는 0보다 커야 함")
    if float(c.get('water', {}).get('molWeight') or 18.01528) <= 0:
        err.append("상단 액체 molWeight 는 0보다 커야 함")
    run = c.get('run') or {}
    time_step_mode = str(run.get('time_step_mode') or 'adaptive').strip().lower()
    if time_step_mode not in ('adaptive', 'fixed'):
        err.append("run.time_step_mode 는 adaptive(자동 안정) 또는 fixed(고정) 여야 함")
    try:
        if float(run.get('max_dt_s') or 0) <= 0:
            err.append("run.max_dt_s 는 0보다 커야 함")
    except (TypeError, ValueError):
        err.append("run.max_dt_s 는 숫자여야 함")
    for prop in ('cp', 'mu', 'kappa'):
        if float(c.get('vapour', {}).get(prop) or 0) <= 0:
            err.append(f"하단 액체 증기 vapour.{prop} 는 0보다 커야 함")
    # 제조사/문헌 원표는 다항식으로 숨기지 않고 property_tables에 그대로 둔다.
    # 각 물성은 독립적인 시험 온도를 가질 수 있으므로 표마다 T_K를 검증한다.
    pt = (c.get('dielectric_fluid') or {}).get('property_tables')
    if pt:
        for prop in ('rho', 'cp', 'mu', 'kappa'):
            table = pt.get(prop) or {}
            xs, ys = table.get('T_K') or [], table.get('values') or []
            if len(xs) < 2 or len(xs) != len(ys):
                err.append(f"dielectric_fluid.property_tables.{prop}: T_K와 values 길이가 같은 2점 이상 표여야 함")
                continue
            try:
                xvals, yvals = [float(x) for x in xs], [float(y) for y in ys]
            except (TypeError, ValueError):
                err.append(f"dielectric_fluid.property_tables.{prop}: 숫자만 허용됨")
                continue
            if any(b <= a for a, b in zip(xvals, xvals[1:])):
                err.append(f"dielectric_fluid.property_tables.{prop}.T_K 는 엄격한 오름차순이어야 함")
            if any(y <= 0 for y in yvals):
                err.append(f"dielectric_fluid.property_tables.{prop}.values 는 모두 0보다 커야 함")
    # CFD Studio의 유체 물성 입력은 단순 표시값이 아니라 아래 검증을 거쳐
    # thermophysicalProperties의 tabulated 물성으로 직접 생성된다.
    for key, label in (('dielectric_fluid', '하단 비전도 액체'), ('water', '상단 액체')):
        f = c.get(key) or {}
        mp = f.get('manual_properties')
        if not mp:
            continue
        for prop in ('T_ref_C', 'rho_kg_m3', 'cp_J_kgK', 'mu_Pa_s', 'kappa_W_mK', 'beta_1_K'):
            try: v = float(mp[prop])
            except (KeyError, TypeError, ValueError):
                err.append(f"{label} manual_properties.{prop} 값이 필요함"); continue
            if prop == 'T_ref_C':
                if not (-100 <= v <= 500): err.append(f"{label} 기준 온도는 -100~500 °C 범위여야 함")
            elif prop == 'beta_1_K':
                if not (0 <= v <= 0.02): err.append(f"{label} 체적팽창계수는 0~0.02 1/K 범위여야 함")
            elif v <= 0:
                err.append(f"{label} {prop} 는 0보다 커야 함")
    if not c['heater'].get('cpus'):
        err.append("heater.cpus 가 비어 있음 — 발열면이 없음")
    Tsat = float(c['dielectric_fluid']['Tsat_C'])
    for k2 in ('init_T_dielectric_C', 'init_T_dielectric_top_C'):
        v2 = c['layers'].get(k2)
        if v2 is not None and float(v2) >= Tsat:
            err.append(f"layers.{k2}({v2}) 가 기화점 {Tsat} 이상 — 시작과 동시에 전 영역이 비등함")
    for p in c['probes_mm']['points']:
        x, y, z = p
        if not (0 < x < W and 0 < y < H and 0 < z < D):
            err.append(f"프로브 {p} 가 도메인 밖")
        if b['x0'] < x < b['x1'] and b['y0'] < y < b['y1'] and b['z0'] < z < b['z1']:
            err.append(f"프로브 {p} 가 보드 내부")
        k = c['coil']
        if k['x0'] < x < k['x1'] and k['y0'] < y < k['y1'] and k['z0'] < z < k['z1']:
            err.append(f"프로브 {p} 가 코일 내부")
    if err:
        sys.exit("[검증 실패]\n  - " + "\n  - ".join(err))

def report_evidence_status(c):
    """Keep preliminary model assumptions visible at every build/run."""
    status = c.get('_검증상태') or {}
    if status.get('정량검증완료') is False:
        print("[build_case] 근거 상태: research_preliminary — 실험 보정 전 정량 확정용이 아님", file=sys.stderr)
    unresolved = []
    for key, value in ((c.get('vapour') or {}).get('_evidence') or {}).items():
        if value in ('unresolved', 'calibration_required', 'analogous'):
            unresolved.append(f"vapour.{key}={value}")
    for key, value in ((c.get('phase_change') or {}).get('_evidence') or {}).items():
        if value in ('unresolved', 'calibration_required'):
            unresolved.append(f"phase_change.{key}={value}")
    sigma = (c.get('dielectric_fluid') or {}).get('_sigma_evidence') or {}
    for key, value in sigma.items():
        if value != 'direct':
            unresolved.append(f"dielectric_fluid.{key}={value}")
    for key, item in (c.get('_모델가정') or {}).items():
        value = item.get('evidence') if isinstance(item, dict) else 'untracked'
        if value not in ('direct', 'derived'):
            unresolved.append(f"model.{key}={value}")
    if unresolved:
        print("[build_case] 보정/교체 필요: " + ", ".join(unresolved), file=sys.stderr)

# ---------------------------------------------------------------- 격자
def breakpoints(vals, lo, hi):
    s = sorted(set([lo, hi] + [v for v in vals if lo < v < hi]))
    return s

def build_mesh(c):
    W, D, H = c['tank']['width_mm'], c['tank']['depth_mm'], c['tank']['liquid_height_mm']
    b, k, dx = c['board'], c['coil'], c['mesh']['dx_mm']
    cpus = c['heater']['cpus']
    XS = breakpoints([b['x0'], b['x1'], k['x0'], k['x1']] + [v for u in cpus for v in (u['x0'], u['x1'])], 0, W)
    YS = breakpoints([b['y0'], b['y1'], k['y0'], k['y1'], c['layers']['dielectric_mm']]
                     + [v for u in cpus for v in (u['y0'], u['y1'])], 0, H)
    ZS = breakpoints([b['z0'], b['z1'], k['z0'], k['z1']], 0, D)
    NC, NR, NZ = len(XS)-1, len(YS)-1, len(ZS)-1
    nx = [max(2, round((XS[i+1]-XS[i])/dx)) for i in range(NC)]
    ny = [max(2, round((YS[j+1]-YS[j])/dx)) for j in range(NR)]
    nz = [max(2, round((ZS[kk+1]-ZS[kk])/dx)) for kk in range(NZ)]

    def spans(lines, a0, a1):
        return [i for i in range(len(lines)-1) if lines[i] >= a0-1e-9 and lines[i+1] <= a1+1e-9]
    HOLES = {}
    for i in spans(XS, b['x0'], b['x1']):
        for j in spans(YS, b['y0'], b['y1']):
            for kk in spans(ZS, b['z0'], b['z1']): HOLES[(i, j, kk)] = 'board'
    for i in spans(XS, k['x0'], k['x1']):
        for j in spans(YS, k['y0'], k['y1']):
            for kk in spans(ZS, k['z0'], k['z1']): HOLES[(i, j, kk)] = 'coil'

    cpu_cols = [(spans(XS, u['x0'], u['x1']), spans(YS, u['y0'], u['y1'])) for u in cpus]
    def is_cpu(i, j): return any(i in cs and j in rs for cs, rs in cpu_cols)

    def vid(i, j, kk): return kk*(NC+1)*(NR+1) + j*(NC+1) + i
    L = ['/*--------------------------------*- C++ -*----------------------------------*/',
         'FoamFile { version 2.0; format ascii; class dictionary; object blockMeshDict; }',
         f'// config.json 자동 생성 (dx={dx}mm) — tools/build_case.py', 'scale 0.001;', 'vertices (']
    for kk in range(NZ+1):
        for j in range(NR+1):
            for i in range(NC+1):
                L.append(f'    ({XS[i]} {YS[j]} {ZS[kk]})')
    L += [');', 'blocks (']
    cells = 0
    for kk in range(NZ):
        for j in range(NR):
            for i in range(NC):
                if (i, j, kk) in HOLES: continue
                cells += nx[i]*ny[j]*nz[kk]
                h8 = [vid(i,j,kk), vid(i+1,j,kk), vid(i+1,j+1,kk), vid(i,j+1,kk),
                      vid(i,j,kk+1), vid(i+1,j,kk+1), vid(i+1,j+1,kk+1), vid(i,j+1,kk+1)]
                L.append(f'    hex ({" ".join(map(str,h8))}) ({nx[i]} {ny[j]} {nz[kk]}) simpleGrading (1 1 1)')
    L.append(');')

    def face(i, j, kk, side):
        if side == 'W': return (vid(i,j,kk), vid(i,j,kk+1), vid(i,j+1,kk+1), vid(i,j+1,kk))
        if side == 'E': return (vid(i+1,j,kk), vid(i+1,j+1,kk), vid(i+1,j+1,kk+1), vid(i+1,j,kk+1))
        if side == 'S': return (vid(i,j,kk), vid(i+1,j,kk), vid(i+1,j,kk+1), vid(i,j,kk+1))
        if side == 'N': return (vid(i,j+1,kk), vid(i,j+1,kk+1), vid(i+1,j+1,kk+1), vid(i+1,j+1,kk))
        if side == 'B': return (vid(i,j,kk), vid(i,j+1,kk), vid(i+1,j+1,kk), vid(i+1,j,kk))
        return (vid(i,j,kk+1), vid(i+1,j,kk+1), vid(i+1,j+1,kk+1), vid(i,j+1,kk+1))

    open_top = bool((c.get('run') or {}).get('open_top', True))
    groups = {'cpu': [], 'board': [], 'coil': [], 'outerWalls': [], 'top': []}
    NBR = {'W': (-1,0,0), 'E': (1,0,0), 'S': (0,-1,0), 'N': (0,1,0), 'B': (0,0,-1), 'F': (0,0,1)}
    cpu_area = 0.0
    for kk in range(NZ):
        for j in range(NR):
            for i in range(NC):
                if (i, j, kk) in HOLES: continue
                for side, (di, dj, dk) in NBR.items():
                    ii, jj, kx = i+di, j+dj, kk+dk
                    outside = not (0 <= ii < NC and 0 <= jj < NR and 0 <= kx < NZ)
                    hole = HOLES.get((ii, jj, kx))
                    if not outside and hole is None: continue
                    f = face(i, j, kk, side)
                    if hole == 'board' and side == 'B' and is_cpu(i, j):
                        groups['cpu'].append(f); cpu_area += (XS[i+1]-XS[i])*(YS[j+1]-YS[j])
                    elif hole: groups[hole].append(f)
                    elif open_top and side == 'N' and jj >= NR:
                        groups['top'].append(f)      # 상단 개방면 — 상변화 체적 배출구
                    else: groups['outerWalls'].append(f)
    L.append('boundary (')
    for name in ('cpu', 'board', 'coil', 'outerWalls', 'top'):
        if not groups[name]: continue
        L.append(f'    {name} {{ type {"patch" if name == "top" else "wall"}; faces (')
        for f in groups[name]: L.append(f'        ({f[0]} {f[1]} {f[2]} {f[3]})')
        L.append('    ); }')
    L.append(');')

    kx = k
    coil_area_m2 = 2*((kx['x1']-kx['x0'])*(kx['y1']-kx['y0']) + (kx['x1']-kx['x0'])*(kx['z1']-kx['z0'])
                      + (kx['y1']-kx['y0'])*(kx['z1']-kx['z0']))*1e-6

    # 코일 각 면의 인접 셀 크기 → 격자측 열저항 δ/κ 산출용.
    # externalWallHeatFluxTemperature 의 h 는 이 저항과 '직렬'로 걸리므로
    # 모델이 낼 수 있는 UA 에는 Σ(A·κ/δ) 라는 격자 상한이 존재한다 (검토서 A2).
    def cellsz(S):
        return [(S[i+1]-S[i])/max(2, round((S[i+1]-S[i])/dx)) for i in range(len(S)-1)]
    def adj(S, sz, val, up):
        for i in range(len(S)-1):
            if up and abs(S[i]-val) < 1e-9: return sz[i]
            if not up and abs(S[i+1]-val) < 1e-9: return sz[i]
        return dx
    cx, cy, cz = cellsz(XS), cellsz(YS), cellsz(ZS)
    ax = (k['x1']-k['x0'])*(k['y1']-k['y0'])   # z 법선 면
    ay = (k['x1']-k['x0'])*(k['z1']-k['z0'])   # y 법선 면
    az = (k['y1']-k['y0'])*(k['z1']-k['z0'])   # x 법선 면
    coil_faces = [                              # (면적 m², 반셀 거리 m)
        (ay*1e-6, adj(YS, cy, k['y0'], False)/2000.0),
        (ay*1e-6, adj(YS, cy, k['y1'], True)/2000.0),
        (ax*1e-6, adj(ZS, cz, k['z0'], False)/2000.0),
        (ax*1e-6, adj(ZS, cz, k['z1'], True)/2000.0),
        (az*1e-6, adj(XS, cx, k['x0'], False)/2000.0),
        (az*1e-6, adj(XS, cx, k['x1'], True)/2000.0),
    ]
    return '\n'.join(L), cells, cpu_area, coil_area_m2, coil_faces

# ---------------------------------------------------------------- 코일 전도도
def coil_UA(faces, h, kw):
    """실효 UA [W/K] = Σ A_i /(1/h + δ_i/κ). h→∞ 극한이 격자 상한."""
    return sum(a/(1.0/h + d/kw) for a, d in faces)

def coil_UA_cap(faces, kw):
    return sum(a*kw/d for a, d in faces)

def coil_h_for(faces, UA_t, kw):
    """목표 UA 를 내는 h 를 이분법으로 역산. 상한 초과면 None."""
    if UA_t >= coil_UA_cap(faces, kw): return None
    lo, hi = 1.0e-3, 1.0e7
    if UA_t <= coil_UA(faces, lo, kw): return None
    for _ in range(200):
        mid = (lo+hi)/2
        if coil_UA(faces, mid, kw) < UA_t: lo = mid
        else: hi = mid
    return (lo+hi)/2

# ---------------------------------------------------------------- 물성 표
def poly(cs, T): return sum(a*T**i for i, a in enumerate(cs))

def source_property_table(table):
    """출처 원표를 OpenFOAM tabulated 형식으로 변환한다.

    원표 내부는 선형보간하고, 시험 범위 밖은 가장 가까운 실측값으로 고정한다.
    임의 외삽으로 물성을 새로 만들지 않기 위해 250/460 K 경계점도 끝값을 쓴다.
    """
    xs = [float(x) for x in table['T_K']]
    ys = [float(y) for y in table['values']]
    rows = list(zip(xs, ys))
    if xs[0] > 250.0: rows.insert(0, (250.0, ys[0]))
    if xs[-1] < 460.0: rows.append((460.0, ys[-1]))
    return '(\n' + '\n'.join(f'        ({t:.2f} {v:.8g})' for t, v in rows) + '\n    )'

def table_value(table, T):
    """출처 표 선형보간. 범위 밖은 끝값 고정."""
    xs = [float(x) for x in table['T_K']]
    ys = [float(y) for y in table['values']]
    if T <= xs[0]: return ys[0]
    if T >= xs[-1]: return ys[-1]
    for i in range(1, len(xs)):
        if T <= xs[i]:
            q = (T-xs[i-1])/(xs[i]-xs[i-1])
            return ys[i-1] + q*(ys[i]-ys[i-1])
    return ys[-1]

def manual_property_table(f, fallback_name):
    """사용자 대표 물성을 OpenFOAM icoTabulated 표로 변환한다.

    rho(T)=rho_ref*[1-beta*(T-Tref)]의 선형 열팽창 모델을 사용하고 cp, mu,
    kappa는 입력 대표값으로 유지한다. UI에 표시한 값이 생성 사전에 그대로
    들어가며, manual_properties가 없으면 기존 다항식/표를 한 글자도 바꾸지 않는다.
    """
    mp = (f or {}).get('manual_properties')
    if not mp: return None
    tref = float(mp['T_ref_C']) + 273.15
    rho0 = float(mp['rho_kg_m3']); beta = float(mp['beta_1_K'])
    cp = float(mp['cp_J_kgK']); mu = float(mp['mu_Pa_s']); kappa = float(mp['kappa_W_mK'])
    Ts = [250.0] + [273.15 + 5*i for i in range(21)] + [400.0, 460.0]
    def rho(T): return max(1.0e-6, rho0*(1.0-beta*(T-tref)))
    def tab(fn):
        return '(\n' + '\n'.join(f'        ({T:.2f} {fn(T):.8g})' for T in Ts) + '\n    )'
    return {
        'name': str((f or {}).get('name') or fallback_name),
        'Tref': tref, 'rho0': rho0, 'cp': cp, 'mu': mu, 'kappa': kappa, 'beta': beta,
        'rho_tab': tab(rho), 'cp_tab': tab(lambda _T: cp),
        'mu_tab': tab(lambda _T: mu), 'kappa_tab': tab(lambda _T: kappa),
    }

def thermo_files(c):
    d = c['dielectric_fluid']
    Tref = d['Tsat_C'] + 273.15
    dm = manual_property_table(d, '하단 비전도 액체')
    if dm:
        liq = f'''/*--------------------------------*- C++ -*----------------------------------*/
FoamFile {{ version 2.0; format ascii; class dictionary; object thermophysicalProperties.liquid; }}
// config.json 자동 생성 — {dm['name']} (사용자 입력 물성, rho 선형 열팽창 + 나머지 대표값)
thermoType
{{
    type heRhoThermo; mixture pureMixture; transport tabulated;
    thermo hTabulated; equationOfState icoTabulated; specie specie; energy sensibleEnthalpy;
}}
mixture
{{
    specie {{ molWeight {d['molWeight']}; }}
    equationOfState {{ rho {dm['rho_tab']}; }}
    thermodynamics {{ Hf 0; Sf 0; Cp {dm['cp_tab']}; }}
    transport {{ mu {dm['mu_tab']}; kappa {dm['kappa_tab']}; }}
}}
'''
    elif d.get('property_tables'):
        pts = d['property_tables']
        ref = {key: table_value(pts[key], Tref) for key in ('rho', 'cp', 'mu', 'kappa')}
        liq = f'''/*--------------------------------*- C++ -*----------------------------------*/
FoamFile {{ version 2.0; format ascii; class dictionary; object thermophysicalProperties.liquid; }}
// config.json 자동 생성 — {d['name']} 제조사 시험표 (표 내부 선형보간, 범위 밖 끝값 고정)
thermoType
{{
    type heRhoThermo; mixture pureMixture; transport tabulated;
    thermo hTabulated; equationOfState icoTabulated; specie specie; energy sensibleEnthalpy;
}}
mixture
{{
    specie {{ molWeight {d['molWeight']}; }}
    equationOfState {{ // {Tref:.2f}K에서 rho={ref['rho']:.2f} kg/m3
        rho {source_property_table(pts['rho'])};
    }}
    thermodynamics {{ // Cp({Tref:.2f}K)={ref['cp']:.2f} J/kgK | Hf 0
        Hf 0; Sf 0;
        Cp {source_property_table(pts['cp'])};
    }}
    transport {{ // mu({Tref:.2f}K)={ref['mu']:.8g} Pa.s | kappa={ref['kappa']:.8g} W/mK
        mu {source_property_table(pts['mu'])};
        kappa {source_property_table(pts['kappa'])};
    }}
}}
'''
    else:
        # 과거 프로젝트 스냅샷 호환. 신규 설정은 출처 원표(property_tables)를 사용한다.
        lo, hi = d['poly_range_K']
        Ts = [250.0] + [lo + 2*i for i in range(int((hi-lo)/2)+1)] + [400.0, 460.0]
        cl = lambda T: min(max(T, lo), hi)
        def tab(f):
            return '(\n' + '\n'.join(f'        ({T:.2f} {f(cl(T)):.6g})' for T in Ts) + '\n    )'
        liq = f'''/*--------------------------------*- C++ -*----------------------------------*/
FoamFile {{ version 2.0; format ascii; class dictionary; object thermophysicalProperties.liquid; }}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //
// config.json 자동 생성 — {d['name']} 액체 (다항식→2K 표, 범위 밖 경계값 고정)
thermoType
{{
    type heRhoThermo; mixture pureMixture; transport tabulated;
    thermo hTabulated; equationOfState icoTabulated; specie specie; energy sensibleEnthalpy;
}}
mixture
{{
    specie {{ molWeight {d['molWeight']}; }}
    equationOfState {{ // {Tref:.2f}K에서 rho={poly(d['rho_poly'],Tref):.1f}
        rho {tab(lambda T: poly(d['rho_poly'],T))};
    }}
    thermodynamics {{ // Cp({Tref:.2f}K)={poly(d['cp_poly'],Tref):.1f} | Hf 0 (잠열=증기 Hf와의 차)
        Hf 0; Sf 0;
        Cp {tab(lambda T: poly(d['cp_poly'],T))};
    }}
    transport {{ // mu({Tref:.2f}K)={poly(d['mu_poly'],Tref):.4g} | kappa={poly(d['kappa_poly'],Tref):.4g}
        mu {tab(lambda T: poly(d['mu_poly'],T))};
        kappa {tab(lambda T: poly(d['kappa_poly'],T))};
    }}
}}
'''
    # 증기 밀도 표에 사용할 온도축. 액체 표 스키마와 무관하게 고정 범위를 쓴다.
    Ts = [250.0] + [273.15 + 2*i for i in range(46)] + [400.0, 460.0]
    v = c['vapour']
    rho_rows = '\n'.join(f'        ({T:.2f} {P_ATM*d["molWeight"]*1e-3/R_GAS/T:.6g})' for T in Ts)
    vap = f'''/*--------------------------------*- C++ -*----------------------------------*/
FoamFile {{ version 2.0; format ascii; class dictionary; object thermophysicalProperties.vapour; }}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //
// config.json 자동 생성 — {d['name']} 증기 (1atm 이상기체 rho(T) 표)
// cp/mu/kappa evidence: {(v.get('_evidence') or {}).get('cp', 'untracked')} — C6F14 유사값, TMC-49 직접 증기 물성 확보 시 교체
thermoType
{{
    type heRhoThermo; mixture pureMixture; transport tabulated;
    thermo hTabulated; equationOfState icoTabulated; specie specie; energy sensibleEnthalpy;
}}
mixture
{{
    specie {{ molWeight {d['molWeight']}; }}
    equationOfState {{
        rho (
{rho_rows}
    );
    }}
    thermodynamics {{
        Hf {d['h_fg_J_kg']};    // 잠열 h_fg [J/kg] — 액체 Hf 0과의 차이 (config.json 출처 메타데이터 참조)
        Sf 0;
        Cp ( (250 {v['cp']}) (460 {v['cp']}) );
    }}
    transport {{
        mu    ( (250 {v['mu']}) (460 {v['mu']}) );
        kappa ( (250 {v['kappa']}) (460 {v['kappa']}) );
    }}
}}
'''
    w = dict(c['water'])
    for a, b in (('rho', 'rho_30C'), ('cp', 'cp_30C'), ('mu', 'mu_30C')):
        if a not in w and b in w: w[a] = w[b]          # 구버전 분기 호환
    if 'Pr' not in w and w.get('mu_30C') and w.get('kappa_30C'):
        w['Pr'] = w['mu_30C']*w['cp_30C']/w['kappa_30C']
    wm = manual_property_table(w, '상단 액체')
    if wm:
        wat = f'''/*--------------------------------*- C++ -*----------------------------------*/
FoamFile {{ version 2.0; format ascii; class dictionary; object thermophysicalProperties.water; }}
// config.json 자동 생성 — {wm['name']} (상단 액체 사용자 입력 물성; water는 기존 프로젝트 호환용 내부 상 이름)
thermoType
{{
    type heRhoThermo; mixture pureMixture; transport tabulated;
    thermo hTabulated; equationOfState icoTabulated; specie specie; energy sensibleEnthalpy;
}}
mixture
{{
    specie {{ molWeight {w.get('molWeight', 18.01528)}; }}
    equationOfState {{ rho {wm['rho_tab']}; }}
    thermodynamics {{ Hf 0; Sf 0; Cp {wm['cp_tab']}; }}
    transport {{ mu {wm['mu_tab']}; kappa {wm['kappa_tab']}; }}
}}
'''
    elif w.get('T_K'):
        # 온도 의존 물성 — rho(T)가 있어야 상단 액체층에 부력이 생겨 자연대류가 성립한다.
        # thermoType 은 유전체와 동일한 tabulated/hTabulated/icoTabulated 조합을 쓴다
        # (rhoThermos.C 에 컴파일되어 있는 조합. const+icoPolynomial 은 존재하지 않음)
        TW = list(w['T_K'])
        def wtab(key):
            v = list(w[key])
            rows = [(250.0, v[0])] + list(zip(TW, v)) + [(460.0, v[-1])]
            return '(\n' + '\n'.join(f'        ({t:.2f} {x:.6g})' for t, x in rows) + '\n    )'
        wat = f'''/*--------------------------------*- C++ -*----------------------------------*/
FoamFile {{ version 2.0; format ascii; class dictionary; object thermophysicalProperties.water; }}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //
// config.json 자동 생성 — {w.get('name', 'DI수')} (온도 의존, 범위 밖 경계값 고정)
// rho(T) 필수: 상수 밀도는 부력항을 0으로 만들어 상단 액체가 정지 전도층이 된다
thermoType
{{
    type heRhoThermo; mixture pureMixture; transport tabulated;
    thermo hTabulated; equationOfState icoTabulated; specie specie; energy sensibleEnthalpy;
}}
mixture
{{
    specie {{ molWeight {w.get('molWeight', 18.01528)}; }}
    equationOfState {{
        rho {wtab('rho')};
    }}
    thermodynamics {{
        Hf 0; Sf 0;
        Cp {wtab('cp')};
    }}
    transport {{
        mu {wtab('mu')};
        kappa {wtab('kappa')};
    }}
}}
'''
    else:                                  # 구버전 config 호환 (상수 물성)
        wat = f'''/*--------------------------------*- C++ -*----------------------------------*/
FoamFile {{ version 2.0; format ascii; class dictionary; object thermophysicalProperties.water; }}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //
// config.json 자동 생성 — {w.get('name', '상단 액체')} 상수 물성 (★부력 없음 — T_K 표 또는 manual_properties 권장)
thermoType
{{
    type heRhoThermo; mixture pureMixture; transport const; thermo hConst;
    equationOfState rhoConst; specie specie; energy sensibleEnthalpy;
}}
mixture
{{
    specie          {{ molWeight {w.get('molWeight', 18.01528)}; }}
    equationOfState {{ rho {w['rho']}; }}
    thermodynamics  {{ Cp {w['cp']}; Hf 0; }}
    transport       {{ mu {w['mu']}; Pr {w['Pr']}; }}
}}
'''
    return liq, vap, wat

# ---------------------------------------------------------------- 사전들
def phase_properties(c):
    d, pc = c['dielectric_fluid'], c['phase_change']
    Tsat = d['Tsat_C'] + 273.15
    sigma_evidence = d.get('_sigma_evidence') or {}
    lv_src = sigma_evidence.get('sigma_lv', 'untracked')
    lw_src = sigma_evidence.get('sigma_lw', 'untracked')
    vw_src = sigma_evidence.get('sigma_vw', 'untracked')
    return f'''/*--------------------------------*- C++ -*----------------------------------*/
FoamFile {{ version 2.0; format ascii; class dictionary; object phaseProperties; }}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //
// config.json 자동 생성 — 3상(하단 비전도 액체/그 증기/상단 액체) + Lee 상변화
// liquid/vapour/water는 기존 프로젝트·Viewer 호환을 위한 OpenFOAM 내부 상 이름
type    massTransferMultiphaseSystem;
phases  (liquid vapour water);

liquid  {{ type pureMovingPhaseModel; }}
vapour  {{ type pureMovingPhaseModel; }}
water   {{ type pureMovingPhaseModel; }}

surfaceTension
(
    (liquid and vapour) {{ type constant; sigma {d['sigma_lv']}; }}   // evidence: {lv_src}
    (liquid and water)  {{ type constant; sigma {d['sigma_lw']}; }}   // evidence: {lw_src}
    (vapour and water)  {{ type constant; sigma {d['sigma_vw']}; }}   // evidence: {vw_src}
);

massTransferModel
(
    (liquid to vapour)
    {{
        type            Lee;
        C               {pc['evap_C']};       // ★UDF 원값 수령 시 교체
        Tactivate       {Tsat:.2f};
    }}
    (vapour to liquid)
    {{
        type            Lee;
        C               {pc['cond_C']};       // 실측 정성 기준 역산 보정 — UDF 원값 수령 시 교체
        Tactivate       {Tsat:.2f};
    }}
);
'''

def zero_T(c, coil_area_m2, cpu_area_mm2, open_top=True, Tw=305.15):
    h, Ta = c['coil']['h_W_m2K'], c['coil']['Ta_C'] + 273.15
    Q = c['heater']['total_W']
    flux = Q/(cpu_area_mm2*1e-6)/1000
    top = (f'    top         {{ type inletOutlet; inletValue uniform {Tw:.2f}; '
           f'value uniform {Tw:.2f}; }}\n') if open_top else ''
    return f'''/*--------------------------------*- C++ -*----------------------------------*/
FoamFile {{ version 2.0; format ascii; class volScalarField; object T; }}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //
// config.json 자동 생성
dimensions [0 0 0 1 0 0 0];
internalField uniform 305;      // setFields가 층별 초기 온도 설정

boundaryField
{{
    cpu         // CPU 발열면 — 총 {Q} W (면적 {cpu_area_mm2:,.0f} mm² ⇒ {flux:.1f} kW/m²)
    {{
        type            externalWallHeatFluxTemperature;
        mode            power;
        Q               {Q};
        kappaMethod     fluidThermo;
        value           uniform 320;
    }}
    board       {{ type zeroGradient; }}     // 기판 단열 근사 ★발열 분배 확인
    coil        // 냉각 코일 — h(T-Ta). 조건 교체는 config.json의 conditions 배열
    {{
        type            externalWallHeatFluxTemperature;
        mode            coefficient;
        h               uniform {h};         // ★핀 사양 수령 시 확정 (hA 보존 환산값)
        Ta              constant {Ta:.2f};
        kappaMethod     fluidThermo;
        value           uniform 300;
    }}
    outerWalls  {{ type zeroGradient; }}     // 외벽 단열 근사
{top}}}
'''

ZERO_HDR = """/*--------------------------------*- C++ -*----------------------------------*/
FoamFile {{ version 2.0; format ascii; class {cls}; object {obj}; }}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //
// config.json 자동 생성 — 직접 수정 금지 (build_case.py가 매 실행 덮어씀)
dimensions {dim};
internalField uniform {init};

boundaryField
{{
{walls}{top}}}
"""

def zero_fields(c, open_top):
    """0.orig/{U,p,p_rgh,alpha.*} 생성.

    상단 개방(top)이 필요한 이유 — 이 솔버의 pEqn 에는 압축성 항이 없고
    (상변화 체적은 fluid.volTransfer 로만 들어감) 세 상 모두 비압축성이다.
    밀폐 강체 도메인에서는 증발이 만드는 체적(액체→증기 약 134배)을 흡수할
    곳이 없어 압력식이 적합조건을 잃는다. 잠열이 열을 나르려면 정상상태에서도
    수백 mL 의 증기 재고가 상시 존재해야 하므로 밀폐로는 성립하지 않는다.
    """
    K = 273.15
    Tw = float(c['layers'].get('init_T_water_top_C', c['layers']['init_T_water_C'])) + K
    W = ('cpu', 'board', 'coil', 'outerWalls')
    def blk(spec, topspec):
        walls = ''.join('    %-12s { %s }\n' % (n, spec) for n in W)
        top = ('    %-12s { %s }\n' % ('top', topspec)) if open_top else ''
        return walls, top
    out = {}
    for name, init in (('alpha.liquid', 0), ('alpha.vapour', 0), ('alpha.water', 1)):
        inlet = 1 if name == 'alpha.water' else 0
        w, t = blk('type zeroGradient;',
                   'type inletOutlet; inletValue uniform %d; value uniform %d;' % (inlet, inlet))
        out['0.orig/' + name] = ZERO_HDR.format(cls='volScalarField', obj=name,
            dim='[0 0 0 0 0 0 0]', init=init, walls=w, top=t)
    w, t = blk('type noSlip;', 'type pressureInletOutletVelocity; value uniform (0 0 0);')
    out['0.orig/U'] = ZERO_HDR.format(cls='volVectorField', obj='U',
        dim='[0 1 -1 0 0 0 0]', init='(0 0 0)', walls=w, top=t)
    w, t = blk('type calculated; value uniform 101325;',
               'type calculated; value uniform 101325;')
    out['0.orig/p'] = ZERO_HDR.format(cls='volScalarField', obj='p',
        dim='[1 -1 -2 0 0 0 0]', init=101325, walls=w, top=t)
    w, t = blk('type fixedFluxPressure; value uniform 101325;',
               'type prghTotalPressure; p0 uniform 101325; value uniform 101325;')
    out['0.orig/p_rgh'] = ZERO_HDR.format(cls='volScalarField', obj='p_rgh',
        dim='[1 -1 -2 0 0 0 0]', init=101325, walls=w, top=t)
    return out, Tw

def set_fields(c):
    """층 초기화 — 상·하단 온도가 다르면 얇은 상자를 쌓아 선형 성층(stratification)을 만든다.
    (균일 초기장은 실제 수조와 달라 '전 층이 같은 온도'로 보이는 문제가 있음.
     top 값이 없거나 bottom과 같으면 기존처럼 균일 초기화)"""
    L = c['layers']
    Hd = L['dielectric_mm']/1000.0
    Hl = c['tank']['liquid_height_mm']/1000.0
    K = 273.15
    dB = L['init_T_dielectric_C'] + K                       # 유전체 하단(기준값)
    dT = L.get('init_T_dielectric_top_C', L['init_T_dielectric_C']) + K
    wB = L['init_T_water_C'] + K                            # 상단 액체층 하단(계면 쪽)
    wT = L.get('init_T_water_top_C', L['init_T_water_C']) + K
    n  = max(1, int(L.get('init_profile_steps', 12)))

    def layer(y0, y1, Tb, Tt, water):
        """[y0,y1] 구간을 n등분해 선형 온도 상자 생성 (아래→위 순서, 뒤 상자가 앞을 덮음)"""
        out = []
        for k in range(n):
            a, b = y0 + (y1-y0)*k/n, y0 + (y1-y0)*(k+1)/n
            if k == 0 and y0 <= 1e-9: a = -1.0        # 바닥·천장은 경계 밖까지 덮어 반올림 누락 방지
            if k == n-1 and abs(y1-Hl) < 1e-9: b = 9.0
            f = (k + 0.5)/n
            T = Tb + (Tt-Tb)*f
            phase = ("            volScalarFieldValue alpha.water   0\n"
                     "            volScalarFieldValue alpha.liquid  1\n") if not water else ""
            out.append(f"""    boxToCell
    {{
        box (-1 {a:.4f} -1) (1 {b:.4f} 1);
        fieldValues
        (
{phase}            volScalarFieldValue T             {T:.2f}
        );
    }}""")
        return "\n".join(out)

    # 안정성 강제 — 아래가 위보다 뜨거운 초기 성층은 Rayleigh-Bénard 불안정이라
    # 계산 시작과 동시에 인공 전복 과도를 만든다(Ra≈5e10, 임계 1708). 그런 조합은
    # 하단 값으로 등온화하고 경고를 남긴다. 위가 더 따뜻한(안정) 성층만 그대로 둔다.
    if dT < dB - 1e-6:
        m = 0.5*(dB+dT)
        print(f"[build_case] 경고: 유전체 초기 성층이 불안정(하단 {dB-K:.2f} > 상단 {dT-K:.2f} °C) "
              f"→ 평균 {m-K:.2f} °C 등온으로 강제", file=sys.stderr)
        dB = dT = m
    if wT < wB - 1e-6:
        m = 0.5*(wB+wT)
        print(f"[build_case] 경고: 물 초기 성층이 불안정(하단 {wB-K:.2f} > 상단 {wT-K:.2f} °C) "
              f"→ 평균 {m-K:.2f} °C 등온으로 강제", file=sys.stderr)
        wB = wT = m

    uniform_d = abs(dT-dB) < 1e-6
    uniform_w = abs(wT-wB) < 1e-6
    if uniform_d and uniform_w:
        regions = f"""    boxToCell
    {{
        box (-1 -1 -1) (1 {Hd} 1);
        fieldValues
        (
            volScalarFieldValue alpha.water   0
            volScalarFieldValue alpha.liquid  1
            volScalarFieldValue T             {dB:.2f}
        );
    }}"""
        note = "균일 초기장"
    else:
        regions = (layer(0.0, Hd, dB, dT, water=False) + "\n"
                   + layer(Hd, Hl, wB, wT, water=True))
        note = (f"성층 초기장 — 유전체 {dB-K:.2f}→{dT-K:.2f} °C, "
                f"물 {wB-K:.2f}→{wT-K:.2f} °C (각 층 {n}단)")
    return f'''/*--------------------------------*- C++ -*----------------------------------*/
FoamFile {{ version 2.0; format ascii; class dictionary; object setFieldsDict; }}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //
// config.json 자동 생성 — 층 초기화 (유전체 {c['layers']['dielectric_mm']} mm / 물 {c['tank']['liquid_height_mm']-c['layers']['dielectric_mm']} mm)
// {note}
defaultFieldValues
(
    volScalarFieldValue alpha.water   1
    volScalarFieldValue alpha.liquid  0
    volScalarFieldValue alpha.vapour  0
    volScalarFieldValue T             {wB:.2f}
);
regions
(
{regions}
);
'''

def control_dict(c, coil_area_m2):
    r = c['run']
    h, TaC = c['coil']['h_W_m2K'], c['coil']['Ta_C']
    hA = h*coil_area_m2
    probes = '\n'.join(f'            ({p[0]/1000} {p[1]/1000} {p[2]/1000})' for p in c['probes_mm']['points'])
    # 솔버는 물리 연성을 위해 모든 필드를 계산하지만, 고빈도 저장은
    # 사용자가 선택한 시각화 자료만 남긴다. 저빈도 전체 write는 재시작 앵커로 유지.
    allowed = ('bubble', 'phase', 'flow', 'therm')
    raw_outputs = r.get('output_fields', list(allowed))
    if not isinstance(raw_outputs, list):
        raw_outputs = list(allowed)
    outputs = [x for x in allowed if x in raw_outputs]
    if not outputs:
        raise SystemExit("[\uAC80\uC99D \uC2E4\uD328]\n  - run.output_fields\uB294 1\uAC1C \uC774\uC0C1 \uC120\uD0DD\uD574\uC57C \uD568")
    objects = []
    if 'bubble' in outputs or 'phase' in outputs: objects.append('alpha.vapour')
    if 'phase' in outputs: objects.append('alpha.water')
    if 'flow' in outputs: objects.append('U')
    if 'therm' in outputs: objects.append('T')
    object_text = ' '.join(objects)
    output_text = '·'.join({'bubble':'기포', 'phase':'액체 상분율',
                            'flow':'유동', 'therm':'온도'}[x] for x in outputs)
    viz = ''
    vi = r.get('viz_interval_s')
    if vi and float(vi) < float(r['write_interval_s']):
        viz = f'''    vizFields  // 시각화 전용 고빈도 저장({output_text}, {vi}s) — 전체 상태 저장({r['write_interval_s']}s)은 재시작 앵커로 유지
    {{
        type            writeObjects;
        libs            (utilityFunctionObjects);
        objects         ({object_text});
        writeControl    adjustableRunTime;
        writeInterval   {vi};
    }}
'''
    time_step_mode = str(r.get('time_step_mode') or 'adaptive').strip().lower()
    fixed_time_step = time_step_mode == 'fixed'
    target_dt = float(r['max_dt_s'])
    initial_dt = target_dt if fixed_time_step else min(1e-5, target_dt)
    adjust_time_step = 'no' if fixed_time_step else 'yes'
    time_step_note = ('fixed: deltaT를 입력값으로 유지'
                      if fixed_time_step else
                      'adaptive: maxDeltaT는 상한이며 Courant 조건에 따라 실제 deltaT는 더 작아짐')
    return f'''/*--------------------------------*- C++ -*----------------------------------*/
FoamFile {{ version 2.0; format ascii; class dictionary; object controlDict; }}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //
// config.json 자동 생성
// time step mode: {time_step_note}
application     icoReactingMultiphaseInterFoam;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         {r['end_time_s']};
deltaT          {initial_dt:.12g};
adjustTimeStep  {adjust_time_step};
maxCo           {r['maxCo']};
maxAlphaCo      {r['maxAlphaCo']};
maxDeltaT       {target_dt:.12g};
writeControl    adjustableRunTime;
writeInterval   {r['write_interval_s']};
purgeWrite      0;
writeFormat     binary;
writePrecision  8;
timeFormat      general;
timePrecision   6;
runTimeModifiable yes;

functions
{{
{viz}    vaporVol
    {{
        type            volFieldValue;
        libs            (fieldFunctionObjects);
        operation       volIntegrate;
        fields          (alpha.vapour);
        regionType      all;
        writeFields     false;
        writeControl    timeStep;
        writeInterval   20;
        log             false;
    }}
    Tpeak      // 원격자 기준 최고·최저 온도 — 벽 과열도 진단용
    {{         // (시각화용 therm_*.bin 은 10 mm 평균이라 첨두를 놓침)
        type            volFieldValue;
        libs            (fieldFunctionObjects);
        operation       max;
        fields          (T);
        regionType      all;
        writeFields     false;
        writeControl    timeStep;
        writeInterval   50;
        log             false;
    }}
    TcpuWall   // CPU 벽면 최고 온도 — volFieldValue 는 내부장만 보므로 패치로 따로 잰다
    {{
        type            surfaceFieldValue;
        libs            (fieldFunctionObjects);
        regionType      patch;
        name            cpu;
        operation       max;
        fields          (T);
        writeFields     false;
        writeControl    timeStep;
        writeInterval   50;
        log             false;
    }}
    Tfloor
    {{
        type            volFieldValue;
        libs            (fieldFunctionObjects);
        operation       min;
        fields          (T);
        regionType      all;
        writeFields     false;
        writeControl    timeStep;
        writeInterval   50;
        log             false;
    }}
    coilT      // 에너지 감사: Q_coil = hA(T-Ta) = {hA:.2f} x (T평균 - {TaC+273.15:.2f}) W ↔ 입력 {c['heater']['total_W']} W
    {{
        type            surfaceFieldValue;
        libs            (fieldFunctionObjects);
        regionType      patch;
        name            coil;
        operation       areaAverage;
        fields          (T);
        writeFields     false;
        writeControl    timeStep;
        writeInterval   200;
        log             false;
    }}
    probesT    // 가상 열전대 (config.json probes_mm) ★정확 좌표 수령 시 교체
    {{
        type            probes;
        libs            (sampling);
        fields          (T);
        probeLocations
        (
{probes}
        );
        writeControl    timeStep;
        writeInterval   50;
    }}
}}
'''

# ---------------------------------------------------------------- 메인
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--condition', default=None)
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    c = load(root, a.condition)
    if c.get('_해석유형') == 'grain_silo':
        from build_silo_runtime import build as build_silo
        build_silo(root, c, check=a.check)
        return
    # CFD Studio '직접 입력' 오버라이드 (run_overrides.json) — config.json 위에 얹어 적용
    ovp = os.path.join(root, 'run_overrides.json')
    if os.path.exists(ovp):
        try:
            ov = json.load(open(ovp, encoding='utf-8'))
            for grp in ('run', 'heater', 'phase_change', 'coil', 'layers', 'mesh'):
                for k, v in (ov.get(grp) or {}).items():
                    if grp not in c or k not in c[grp]:
                        print(f"[build_case] 경고: 오버라이드 '{grp}.{k}' 는 config 에 없는 키 — 무시함",
                              file=sys.stderr); continue
                    # 값이 config 원본과 같으면 '직접 입력'으로 보지 않고 건드리지도 않는다.
                    # CFD Studio 는 입력칸을 config 값으로 미리 채우므로, 손대지 않은 칸까지
                    # 오버라이드로 되돌아온다. 비교 기준은 --condition 적용 '전' 원본이어야 한다.
                    ref = (RAW.get(grp) or {}).get(k)
                    try: same = abs(float(v) - float(ref)) <= 1e-9*max(1.0, abs(float(v)))
                    except Exception: same = (v == ref)
                    if same: continue
                    try: c[grp][k] = float(v) if isinstance(ref, (int, float)) else v
                    except Exception: c[grp][k] = v
                    OVERRIDDEN[(grp, k)] = True
            print(f"[build_case] 직접 입력(run_overrides.json) 적용: {ov}", file=sys.stderr)
        except Exception as e:
            print(f"[build_case] run_overrides.json 무시(파싱 실패): {e}", file=sys.stderr)
    validate(c)
    report_evidence_status(c)
    run = c.get('run') or {}
    time_step_mode = str(run.get('time_step_mode') or 'adaptive').strip().lower()
    target_dt = float(run['max_dt_s'])
    if time_step_mode == 'fixed':
        print(f"[build_case] 시간 간격: 고정 {target_dt:g} s · Courant 초과 시 자동 축소 안 함", file=sys.stderr)
    else:
        print(f"[build_case] 시간 간격: 자동 안정 · {target_dt:g} s는 상한(실제 Δt는 Courant 조건에 따라 더 작아짐)", file=sys.stderr)
    bmd, cells, cpu_area, coil_area, coil_faces = build_mesh(c)
    msg = (f"[build_case] 셀 {cells:,} | CPU 면적 {cpu_area:,.0f} mm² → {c['heater']['total_W']} W ⇒ "
           f"{c['heater']['total_W']/(cpu_area*1e-6)/1000:.1f} kW/m² | 코일 면적 {coil_area:.4f} m²"
           + (f" | 조건 {a.condition}" if a.condition else ""))
    print(msg, file=sys.stderr)

    # ---- 코일 열전달 감사 -------------------------------------------------
    # h 는 격자측 저항 δ/κ 와 직렬이므로 실효 UA < hA 이고, h→∞ 극한에도 Σ(A·κ/δ) 를 못 넘는다.
    upper = c['water']
    ump = upper.get('manual_properties') or {}
    kw = float(ump.get('kappa_W_mK') or upper.get('kappa_30C') or 0.615)
    upper_name = str(upper.get('name') or '상단 액체')
    cap = coil_UA_cap(coil_faces, kw)
    UA_t = c['coil'].get('UA_target_W_K')
    h_cfg = float(c['coil']['h_W_m2K'])
    scale = 1.0
    if UA_t and not OVERRIDDEN.get(('coil', 'h_W_m2K')):
        UA_t = float(UA_t)*scale
        UA_use = min(UA_t, 0.90*cap)
        h_new = coil_h_for(coil_faces, UA_use, kw)
        if h_new:
            h_new = round(h_new, 1)
            if abs(h_new - h_cfg)/max(h_cfg, 1) > 0.02:
                print(f"[build_case] 코일 h 재산정: {h_cfg:.0f} → {h_new:.0f} W/m²K "
                      f"(UA_target {UA_t:.2f} W/K" + (f", 조건 배율 {scale:.3f}" if scale != 1.0 else "") + ")",
                      file=sys.stderr)
            c['coil']['h_W_m2K'] = h_new
    h = float(c['coil']['h_W_m2K'])
    UA = coil_UA(coil_faces, h, kw)
    Q, Ta = c['heater']['total_W'], c['coil']['Ta_C']
    print(f"[build_case] 코일: h {h:,.0f} W/m²K → 실효 UA {UA:.2f} W/K "
          f"(격자 상한 {cap:.2f} · hA {h*coil_area:.1f}) | {Q} W 배출 시 평형 {upper_name} 벌크 "
          f"{Ta + Q/UA:.1f} °C (냉각수 {Ta:.0f} °C)", file=sys.stderr)
    if UA_t and float(UA_t) > cap:
        print(f"[build_case] ★경고: UA_target {float(UA_t):.2f} W/K 는 이 격자의 상한 {cap:.2f} W/K 초과 "
              f"— h 를 아무리 올려도 도달 불가(상한의 90 %로 클램프). "
              f"해소하려면 mesh.dx_mm 를 낮추거나 코일 면적을 늘려야 함", file=sys.stderr)
    Tw0 = c['layers'].get('init_T_water_C')
    if Tw0 is not None and abs(float(Tw0) - (Ta + Q/UA)) > 3.0:
        print(f"[build_case] 참고: 상단 액체 초기온도 {Tw0} °C 가 평형 근사값 {Ta + Q/UA:.1f} °C 와 "
              f"{abs(float(Tw0)-(Ta+Q/UA)):.1f} K 차이 — 초기 과도가 길어집니다.", file=sys.stderr)
    if a.check:
        print("[--check] 생성 생략, 검증만 통과", file=sys.stderr); return
    liq, vap, wat = thermo_files(c)
    open_top = bool(c['run'].get('open_top', True))
    zf, Tw = zero_fields(c, open_top)
    print(f"[build_case] 상단 경계: {'개방(top = prghTotalPressure 배출구)' if open_top else '★밀폐 — 상변화 체적을 흡수할 수 없음'}",
          file=sys.stderr)
    out = {
        'system/blockMeshDict': bmd + '\n',
        'system/setFieldsDict': set_fields(c),
        'system/controlDict': control_dict(c, coil_area),
        '0.orig/T': zero_T(c, coil_area, cpu_area, open_top, Tw),
        **zf,
        'constant/phaseProperties': phase_properties(c),
        'constant/thermophysicalProperties.liquid': liq,
        'constant/thermophysicalProperties.vapour': vap,
        'constant/thermophysicalProperties.water': wat,
    }
    for rel, txt in out.items():
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, 'w').write(txt)
    print(f"[build_case] {len(out)}개 파일 생성 완료", file=sys.stderr)

if __name__ == '__main__':
    main()
