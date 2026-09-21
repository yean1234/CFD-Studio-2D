# -*- coding: utf-8 -*-
"""BubbleML 규격(HDF5) 데이터셋 내보내기 — WSL에서 실행.

  python3 tools/export_bubbleml.py --out /mnt/c/.../bubbleml.h5 [--stride 1] [--batch 12]

BubbleML(HPCForge, NeurIPS) 관례를 3D·SI 단위로 확장:
  HDF5 datasets:  temperature(K), velx/vely/velz(m/s), alpha_vapour(0~1)  — shape (N, nz, ny, nx)
                  mask(유체=1)  — (nz, ny, nx),  time(s) — (N,)
  attrs: 격자·유체 물성·가열/냉각 조건 + 무차원화 상수(l0, t0, u0)
  이어쓰기 지원: 같은 --out 재실행 시 완료된 프레임은 건너뜀.
"""
import argparse, json, os, re, shutil, subprocess, sys
import numpy as np

try:
    import h5py
except ImportError:
    sys.exit("[오류] h5py 없음 — WSL에서: sudo apt-get install -y python3-h5py  (설치.bat이 자동 설치함)")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)


def sh(cmd, timeout=3600):
    return subprocess.run(["bash", "-c", cmd], capture_output=True, timeout=timeout)


def parse_foam(path, ncomp):
    b = open(path, "rb").read()
    i0 = b.find(b"internalField")
    m = re.search(rb"List<(?:scalar|vector)>\s*\n(\d+)\s*\n\(", b[i0:i0 + 240])
    if not m:
        raise ValueError(f"binary 필드 아님: {path}")
    n = int(m.group(1)); off = i0 + m.start() + len(m.group(0))
    return np.frombuffer(b, dtype="<f8", count=n * ncomp, offset=off).reshape(n, ncomp)


def openfoam_env():
    r = sh("ls -d /usr/lib/openfoam/openfoam*/etc/bashrc /opt/openfoam*/etc/bashrc 2>/dev/null | sort | tail -1")
    p = r.stdout.decode().strip().splitlines()
    return f"source {p[-1]}; " if p else ""


def cell_centres():
    """셀 중심좌표 (1회 생성 후 C_cache.npy 재사용)"""
    cache = "C_cache.npy"
    if os.path.exists(cache):
        return np.load(cache)
    times = sorted([d for d in os.listdir("processor0") if re.match(r"^[0-9]", d) and d != "0"], key=float)
    if not times:
        sys.exit("[오류] processor0에 스냅샷 없음")
    t = times[0]
    env = openfoam_env()
    sh(f"{env} reconstructPar -time {t} -fields '(alpha.vapour)' >/dev/null 2>&1; "
       f"postProcess -func writeCellCentres -time {t} >/dev/null 2>&1")
    C = parse_foam(os.path.join(t, "C"), 3)
    np.save(cache, C)
    shutil.rmtree(t, ignore_errors=True)
    return C


def build_grid(C, dx):
    x0, y0, z0 = C.min(axis=0); x1, y1, z1 = C.max(axis=0)
    nx = max(2, int(round((x1 - x0) / dx)) + 1)
    ny = max(2, int(round((y1 - y0) / dx)) + 1)
    nz = max(2, int(round((z1 - z0) / dx)) + 1)
    ix = np.clip(np.rint((C[:, 0] - x0) / dx).astype(np.int64), 0, nx - 1)
    iy = np.clip(np.rint((C[:, 1] - y0) / dx).astype(np.int64), 0, ny - 1)
    iz = np.clip(np.rint((C[:, 2] - z0) / dx).astype(np.int64), 0, nz - 1)
    flat = (iz * ny + iy) * nx + ix
    cnt = np.bincount(flat, minlength=nx * ny * nz).astype(np.float32)
    mask = (cnt > 0).reshape(nz, ny, nx)
    return flat, cnt, (nx, ny, nz), (x0, y0, z0, x1, y1, z1), mask


def scatter(flat, cnt, shape, vals):
    nx, ny, nz = shape
    acc = np.bincount(flat, weights=vals, minlength=nx * ny * nz).astype(np.float32)
    out = np.divide(acc, cnt, out=np.zeros_like(acc), where=cnt > 0)
    return out.reshape(nz, ny, nx)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="export_bubbleml.h5")
    ap.add_argument("--stride", type=int, default=1)
    ap.add_argument("--batch", type=int, default=12)
    ap.add_argument("--assume-reconstructed", action="store_true", help="(테스트) 재조립 생략")
    a = ap.parse_args()

    cfg = json.load(open("config.json", encoding="utf-8"))
    dx = cfg["mesh"]["dx_mm"] / 1000.0
    d = cfg["dielectric_fluid"]
    Tsat = d["Tsat_C"] + 273.15
    rho_l = sum(c * Tsat ** i for i, c in enumerate(d["rho_poly"]))
    rho_v = 101325.0 * d["molWeight"] / 1000.0 / (8.314462618 * Tsat)
    sigma = d["sigma_lv"]; g = 9.81
    l0 = (sigma / (g * max(rho_l - rho_v, 1.0))) ** 0.5
    t0 = (l0 / g) ** 0.5

    times = sorted([t for t in os.listdir("processor0") if re.match(r"^[0-9]", t) and t != "0"], key=float)
    times = times[::a.stride]
    if not times:
        sys.exit("[오류] 내보낼 스냅샷 없음")
    print(f"[export] 스냅샷 {len(times)}개 (stride {a.stride}) → {a.out}")

    C = cell_centres()
    flat, cnt, shape, bbox, mask = build_grid(C, dx)
    nx, ny, nz = shape
    print(f"[export] 균일 격자 {nx}x{ny}x{nz} (dx={dx*1000:g}mm) · 셀 {len(C):,}")

    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    new = not os.path.exists(a.out)
    f = h5py.File(a.out, "a")
    N = len(times)
    if new:
        for name in ("temperature", "velx", "vely", "velz", "alpha_vapour"):
            f.create_dataset(name, shape=(N, nz, ny, nx), dtype="f4",
                             chunks=(1, nz, ny, nx), compression="gzip", compression_opts=4)
        f.create_dataset("time", shape=(N,), dtype="f8")
        f.create_dataset("mask", data=mask.astype("u1"))
        at = f.attrs
        at["format"] = "BubbleML-style v1 (3D, SI units)"
        at["fluid"] = d.get("name", "TMC-49"); at["Tsat_K"] = Tsat
        at["rho_liquid"] = rho_l; at["rho_vapour"] = rho_v
        at["sigma_lv"] = sigma; at["h_fg_J_kg"] = d["h_fg_J_kg"]
        at["dx_m"] = dx; at["domain_bbox_m"] = bbox
        at["heater_W"] = cfg["heater"]["total_W"]
        at["coil_h_W_m2K"] = cfg["coil"]["h_W_m2K"]; at["coil_Ta_C"] = cfg["coil"]["Ta_C"]
        at["nondim_l0_m"] = l0; at["nondim_t0_s"] = t0; at["nondim_u0_m_s"] = l0 / t0
        at["frames_done"] = 0
        at["note"] = ("axes: (frame, z, y, x), y=height. mask=1 fluid cell. "
                      "alpha_vapour: TMC-49 vapour fraction. nondimensionalize t/=t0, x/=l0, u/=u0.")
    done = int(f.attrs.get("frames_done", 0))
    if f["temperature"].shape[0] != N:
        sys.exit(f"[오류] 기존 파일 프레임 수({f['temperature'].shape[0]}) ≠ 현재({N}) — --out 새 경로 사용")
    env = openfoam_env()
    for b0 in range(done, N, a.batch):
        chunk = times[b0:b0 + a.batch]
        if not a.assume_reconstructed:
            print(f"[export] 재조립 {b0+1}~{b0+len(chunk)}/{N}", flush=True)
            sh(f"{env} reconstructPar -time '{','.join(chunk)}' -fields '(T U alpha.vapour)' >/dev/null 2>&1")
        for j, t in enumerate(chunk):
            i = b0 + j
            T = parse_foam(os.path.join(t, "T"), 1)[:, 0]
            U = parse_foam(os.path.join(t, "U"), 3)
            AL = parse_foam(os.path.join(t, "alpha.vapour"), 1)[:, 0]
            f["temperature"][i] = scatter(flat, cnt, shape, T)
            f["velx"][i] = scatter(flat, cnt, shape, U[:, 0])
            f["vely"][i] = scatter(flat, cnt, shape, U[:, 1])
            f["velz"][i] = scatter(flat, cnt, shape, U[:, 2])
            f["alpha_vapour"][i] = scatter(flat, cnt, shape, AL)
            f["time"][i] = float(t)
            f.attrs["frames_done"] = i + 1
            if not a.assume_reconstructed:
                shutil.rmtree(t, ignore_errors=True)
            print(f"[export] {i+1}/{N} (t={t}s)", flush=True)
        f.flush()
    f.close()
    print(f"[export] 완료 — {a.out}")


if __name__ == "__main__":
    main()
