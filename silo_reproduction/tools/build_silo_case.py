#!/usr/bin/env python3
"""Build independent Chen et al. (2026) corn-silo OpenFOAM case folders.

Only published values are materialized. A solver cannot start before a reviewed
mesh contract supplies the CAD details and CV plane absent from the paper.
"""
import argparse
import csv
import json
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def write(path, content, executable=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    if executable:
        path.chmod(path.stat().st_mode | 0o111)


def safe_name(value):
    name = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", str(value or "")).strip().rstrip(". ")
    if not name or name in (".", "..") or len(name) > 80:
        raise ValueError("재현 묶음 이름은 1~80자의 안전한 폴더명이어야 합니다")
    return name


def foam_header(kind, location, obj):
    return """FoamFile
{
    version 2.0;
    format ascii;
    class %s;
    location \"%s\";
    object %s;
}
// ************************************************************************* //
""" % (kind, location, obj)


def case_files(case_dir, row, config):
    pub = config["published"]
    manifest = {
        "study": config["study"], "design": row, "published": pub,
        "published_numerics": config["published_numerics"],
        "openfoam_mapping": config["openfoam_mapping"],
        "unpublished_assumptions": config["assumptions"],
        "physics": {"solver": config["openfoam_mapping"]["solver"],
                    "turbulence": config["openfoam_mapping"]["turbulence"],
                    "flow": "3D steady single-phase incompressible isothermal forced ventilation",
                    "porous_zone": "isotropic Darcy-Forchheimer corn grainZone",
                    "excluded": ["heat", "humidity", "species", "grain respiration", "DEM"]},
        "run_status": "contracts_required",
        "run_blocker": "Reviewed mesh and solver contracts are required; unpublished values remain unset."
    }
    write(case_dir / "case_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    write(case_dir / "constant" / "transportProperties", foam_header("dictionary", "constant", "transportProperties") +
        "transportModel Newtonian;\nnu [0 2 -1 0 0 0 0] %.8g;\nrho [1 -3 0 0 0 0 0] %.8g;\n" % (pub["nu_m2_s"], pub["rho_kg_m3"]))
    write(case_dir / "constant" / "turbulenceProperties", foam_header("dictionary", "constant", "turbulenceProperties") +
        "simulationType RAS;\nRAS\n{\n    RASModel kEpsilon;\n    turbulence on;\n    printCoeffs on;\n}\n")
    fv_options = foam_header("dictionary", "constant", "fvOptions") + """cornPorous
    {
        type explicitPorositySource;
        active yes;
        explicitPorositySourceCoeffs
        {
            type DarcyForchheimer;
            selectionMode cellZone;
            cellZone grainZone;
            DarcyForchheimerCoeffs
            {
                d d [0 -2 0 0 0 0 0] (%(d).8g %(d).8g %(d).8g);
                f f [0 -1 0 0 0 0 0] (%(f).8g %(f).8g %(f).8g);
                coordinateSystem { origin (0 0 0); e1 (1 0 0); e2 (0 1 0); }
            }
        }
}
""" % {"d": pub["darcy_d_1_m2"], "f": pub["forchheimer_f_1_m"]}
    write(case_dir / "constant" / "fvOptions", fv_options)
    unresolved = {
        "inlet_velocity_direction": None, "turbulence_inlet_k": None,
        "turbulence_inlet_epsilon": None, "wall_function_mesh_basis": None,
        "convergence_criteria": None, "relaxation_factors": None,
        "reviewed_second_order_openfoam_scheme": None, "parallel_subdomains": None,
        "cv_sampling_plane": None
    }
    write(case_dir / "system" / "UNRESOLVED.json", json.dumps(unresolved, ensure_ascii=False, indent=2) + "\n")
    write(case_dir / "0" / "README.md", "U, p, k, epsilon, and nut are intentionally absent. Their direction, turbulence boundary values, wall functions, and patch mapping require reviewed mesh and solver contracts.\n")
    write(case_dir / "system" / "README.md", "controlDict, fvSchemes, fvSolution, and decomposeParDict are intentionally absent. The paper publishes second-order upwind, but not the reviewed OpenFOAM equivalent, convergence thresholds, relaxation factors, or parallel settings.\n")
    write(case_dir / "README.md", "# %s\n\nPublished design: A=%s mm, B=%s layers, C=%s mm, D=%s.\n\n`Allrun` remains blocked until reviewed mesh and solver contracts resolve every item in `system/UNRESOLVED.json`.\n" % (row["case_id"], row["A_mm"], row["B_layers"], row["C_mm"], row["D_count"]))


PREFLIGHT = r'''#!/usr/bin/env python3
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path
case = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
def fail(message): raise SystemExit("CONTRACT_REQUIRED: " + message)
def text(relative):
    path = case / relative
    if not path.is_file(): fail("reviewed file is missing: " + relative)
    return path.read_text(encoding="utf-8", errors="replace")
def names(value):
    if isinstance(value, str): return [value]
    if isinstance(value, list) and all(isinstance(item, str) for item in value): return value
    return []
def foam_value(relative, entry):
    try:
        run = subprocess.run(["foamDictionary", str(case / relative), "-entry", entry, "-value"], capture_output=True, text=True, timeout=15)
    except Exception as exc: fail("foamDictionary check failed: " + str(exc))
    if run.returncode: fail("invalid OpenFOAM dictionary entry " + relative + ":" + entry)
    return run.stdout.strip()
version = os.environ.get("WM_PROJECT_VERSION", "").strip()
if not re.search(r"(?:^|[-v])2312(?:\D|$)", version): fail("this mapping requires a sourced OpenFOAM v2312 environment")
path = case / "system" / "mesh_contract.json"
if not path.is_file(): fail("system/mesh_contract.json is missing")
try: data = json.loads(path.read_text(encoding="utf-8"))
except Exception as exc: fail("invalid mesh contract: " + str(exc))
required = ("reviewed", "mesh_source", "grain_zone", "patches", "cv_plane")
missing = [key for key in required if not data.get(key)]
if data.get("reviewed") is not True or missing: fail("incomplete reviewed mesh contract: " + ", ".join(missing))
if data.get("grain_zone") != "grainZone": fail("grain_zone must be grainZone")
patches = data.get("patches") or {}
if any(not names(patches.get(key)) for key in ("inlet", "outlet", "walls")): fail("patches must define inlet, outlet, walls")
for name in ("boundary", "cellZones"):
    if not (case / "constant" / "polyMesh" / name).is_file(): fail("constant/polyMesh/" + name + " is missing")
zones = text("constant/polyMesh/cellZones")
zone = re.search(r"(?ms)(?:^|[\s(])grainZone\s*\{.*?cellLabels\s+(?:List<label>\s+)?(\d+)\s*\(", zones)
if not zone or int(zone.group(1)) < 1: fail("grainZone is missing or empty")
boundary = text("constant/polyMesh/boundary")
for patch in sum((names(patches[key]) for key in ("inlet", "outlet", "walls")), []):
    found = re.search(r"(?ms)^\s*" + re.escape(patch) + r"\s*\{.*?\bnFaces\s+(\d+)\s*;", boundary)
    if not found or int(found.group(1)) < 1: fail("boundary patch is missing or empty: " + patch)
solver_path = case / "system" / "solver_contract.json"
if not solver_path.is_file(): fail("system/solver_contract.json is missing")
try: solver = json.loads(solver_path.read_text(encoding="utf-8"))
except Exception as exc: fail("invalid solver contract: " + str(exc))
solver_required = ("reviewed", "solver", "inlet_velocity_vector_m_s", "turbulence_inlet", "convergence_criteria", "numerical_schemes", "parallel_subdomains")
solver_missing = [key for key in solver_required if not solver.get(key)]
if solver.get("reviewed") is not True or solver_missing: fail("incomplete reviewed solver contract: " + ", ".join(solver_missing))
if solver.get("solver") != "simpleFoam": fail("solver must be simpleFoam for this single-phase steady reproduction")
velocity = solver.get("inlet_velocity_vector_m_s")
if not isinstance(velocity, list) or len(velocity) != 3 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in velocity): fail("inlet_velocity_vector_m_s must be a finite 3-vector")
if abs(math.sqrt(sum(v*v for v in velocity)) - 3.0) > 3e-3: fail("inlet velocity magnitude must be the published 3 m/s")
turbulence = solver.get("turbulence_inlet") or {}
if not all(isinstance(turbulence.get(k), (int, float)) and turbulence[k] > 0 for k in ("k", "epsilon")): fail("turbulence_inlet must contain positive k and epsilon")
convergence = solver.get("convergence_criteria") or {}
if not all(isinstance(convergence.get(k), (int, float)) and 0 < convergence[k] < 1 for k in ("p", "U", "k", "epsilon")): fail("convergence_criteria must contain p/U/k/epsilon values between 0 and 1")
schemes = solver.get("numerical_schemes") or {}
if schemes.get("steady_state") is not True or schemes.get("reviewed_second_order_openfoam_equivalent") is not True: fail("numerical_schemes must confirm steady state and reviewed second-order OpenFOAM equivalence")
for relative in ("0/U", "0/p", "0/k", "0/epsilon", "0/nut", "constant/fvOptions", "system/controlDict", "system/fvSchemes", "system/fvSolution", "system/decomposeParDict"):
    text(relative)
if foam_value("constant/fvOptions", "cornPorous/explicitPorositySourceCoeffs/selectionMode") != "cellZone": fail("cornPorous selectionMode must be cellZone inside explicitPorositySourceCoeffs")
if foam_value("constant/fvOptions", "cornPorous/explicitPorositySourceCoeffs/cellZone") != "grainZone": fail("cornPorous cellZone must be grainZone")
if not re.search(r"(?m)^\s*dimensions\s+\[0\s+1\s+-1\s+0\s+0\s+0\s+0\]\s*;", text("0/U")): fail("0/U must use velocity dimensions [0 1 -1 0 0 0 0]")
if not re.search(r"(?m)^\s*dimensions\s+\[0\s+2\s+-2\s+0\s+0\s+0\s+0\]\s*;", text("0/p")): fail("simpleFoam p must be kinematic pressure [0 2 -2 0 0 0 0]")
control = text("system/controlDict")
if not re.search(r"(?m)^\s*application\s+simpleFoam\s*;", control): fail("controlDict application must be simpleFoam")
fv_schemes = text("system/fvSchemes")
if not re.search(r"(?ms)ddtSchemes\s*\{.*?default\s+steadyState\s*;", fv_schemes): fail("fvSchemes must use steadyState")
u_div = re.search(r"(?m)^\s*div\(phi,U\)\s+([^;]+);", fv_schemes)
if not u_div or not re.search(r"\b(linearUpwind|LUST|limitedLinear|QUICK)\b", u_div.group(1)): fail("div(phi,U) must use the reviewed second-order OpenFOAM equivalent")
decompose = text("system/decomposeParDict")
match = re.search(r"(?m)^\s*numberOfSubdomains\s+(\d+)\s*;", decompose)
runtime_np = int(sys.argv[2]) if len(sys.argv) > 2 else 0
if not match or runtime_np < 1: fail("decomposeParDict must contain a positive numberOfSubdomains")
if "--prepare" not in sys.argv and int(match.group(1)) != runtime_np: fail("decomposeParDict numberOfSubdomains must match runtime MPI count")
print("[silo] reviewed mesh and solver contracts accepted")
'''


CV_SCRIPT = r'''#!/usr/bin/env python3
import argparse
import csv
import json
import math
from pathlib import Path
parser = argparse.ArgumentParser(); parser.add_argument("--input", required=True); parser.add_argument("--output", default="results/cv.json")
args = parser.parse_args(); values = []
with open(args.input, encoding="utf-8", newline="") as handle:
    for row in csv.DictReader(handle):
        try: values.append(float(row["U_mag"]))
        except (KeyError, TypeError, ValueError): pass
if len(values) < 2: raise SystemExit("CV requires at least two numeric U_mag samples")
mean = sum(values) / len(values)
if mean <= 0: raise SystemExit("CV requires a positive mean U_mag")
std = math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))
cv = std / mean
result = {"sample_count": len(values), "standard_deviation_basis": "sample_n_minus_1", "mean_velocity_m_s": mean, "std_velocity_m_s": std, "CV": cv, "CV_percent": 100 * cv, "one_minus_CV": 1 - cv, "input": str(Path(args.input))}
out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, ensure_ascii=False))
'''


PRESSURE_SCRIPT = r'''#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path
parser = argparse.ArgumentParser(); parser.add_argument("--input", required=True); parser.add_argument("--output", default="results/pressure_drop.json")
args = parser.parse_args(); case = Path(__file__).resolve().parents[1]
manifest = json.loads((case / "case_manifest.json").read_text(encoding="utf-8")); rho = float(manifest["published"]["rho_kg_m3"])
sums = {"inlet": [0.0, 0.0], "outlet": [0.0, 0.0]}
with open(args.input, encoding="utf-8", newline="") as handle:
    for row in csv.DictReader(handle):
        patch = str(row.get("patch") or "").strip().lower()
        if patch not in sums: continue
        try: p = float(row["p_kinematic_m2_s2"]); area = float(row["area_m2"])
        except (KeyError, TypeError, ValueError): continue
        if area > 0: sums[patch][0] += p * area; sums[patch][1] += area
if any(sums[name][1] <= 0 for name in sums): raise SystemExit("pressure drop requires positive-area inlet and outlet samples")
pin = sums["inlet"][0] / sums["inlet"][1]; pout = sums["outlet"][0] / sums["outlet"][1]
result = {"rho_kg_m3": rho, "inlet_p_kinematic_m2_s2": pin, "outlet_p_kinematic_m2_s2": pout, "pressure_drop_kinematic_m2_s2": pin - pout, "pressure_drop_Pa": rho * (pin - pout), "averaging": "face-area-weighted", "input": str(Path(args.input))}
out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, ensure_ascii=False))
'''


RUNTIME_PLAN = r'''#!/usr/bin/env python3
import argparse
import json
import math
import os
from pathlib import Path
parser = argparse.ArgumentParser(); parser.add_argument("--field", choices=("np", "json"), default="json")
args = parser.parse_args()
case = Path(__file__).resolve().parents[1]
try: contract = json.loads((case / "system" / "solver_contract.json").read_text(encoding="utf-8"))
except Exception: contract = {}
logical = max(1, os.cpu_count() or 1)
try: affinity = max(1, len(os.sched_getaffinity(0)))
except (AttributeError, OSError): affinity = logical
try: pct = int(float(str(os.environ.get("CFD_STUDIO_CPU_PCT", "60")).replace("%", "")))
except ValueError: pct = 60
pct = min(80, max(1, pct))
budget = affinity if affinity < logical else max(1, math.floor(logical * pct / 100))
requested = os.environ.get("CFD_STUDIO_MPI_NP") or os.environ.get("NP") or contract.get("parallel_subdomains") or "auto"
try: requested_np = int(requested)
except (TypeError, ValueError): requested_np = budget
np = min(budget, max(1, requested_np))
result = {"logical_cpus": logical, "affinity_cpus": affinity, "cpu_pct_limit": pct, "available_slots": budget, "requested": requested, "np": np, "oversubscribe": False}
print(np if args.field == "np" else json.dumps(result, ensure_ascii=False))
'''


ALLRUN = '''#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
NP="$(python3 "$HERE/tools/runtime_plan.py" --field np)"
python3 "$HERE/tools/preflight.py" "$HERE" "$NP" --prepare
foamDictionary system/decomposeParDict -entry numberOfSubdomains -set "$NP" >/dev/null
python3 "$HERE/tools/preflight.py" "$HERE" "$NP"
checkMesh -allGeometry -allTopology
python3 "$HERE/tools/runtime_plan.py"
if [ "$NP" -gt 1 ]; then
    decomposePar -force
    mpirun -np "$NP" simpleFoam -parallel | tee log.simpleFoam
    reconstructPar -latestTime
else
    simpleFoam | tee log.simpleFoam
fi
echo "[silo] Supply the documented CV-plane U_mag CSV for tools/calc_cv.py and area-weighted kinematic-pressure CSV for tools/calc_pressure_drop.py."
'''


def source_rows(root, kind):
    if kind in ("l9", "box_behnken"):
        with open(root / "design" / ("l9.csv" if kind == "l9" else "box_behnken.csv"), encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    if kind == "reference": return [{"run": "reference", "A_mm": 20, "B_layers": 12, "C_mm": 5, "D_count": 6, "paper_one_minus_CV": 0.5254, "paper_CV": 0.4746}]
    if kind == "final": return [{"run": "final", "A_mm": 20, "B_layers": 13, "C_mm": 6, "D_count": 7, "paper_one_minus_CV": 0.5307, "paper_CV": 0.4693}]
    return []


def normalize(rows, kind, config):
    out = []
    domains = config["design_domains"]
    allowed = {key: set(domains[key]) for key in ("A_mm", "B_layers", "C_mm", "D_count")}
    for index, raw in enumerate(rows, 1):
        row = {"case_id": "%02d_%s" % (index, str(raw.get("run", index)).zfill(2))}
        for key in ("A_mm", "B_layers", "C_mm", "D_count"):
            row[key] = int(float(raw[key]))
        for key in ("paper_one_minus_CV", "paper_CV"):
            if raw.get(key, "") not in (None, ""): row[key] = float(raw[key])
        if kind == "custom" and any(row[key] not in allowed[key] for key in allowed):
            raise ValueError("직접 입력은 논문 단일요인 이산 수준만 사용할 수 있습니다: A=10/15/20/25/30, B=10~14, C=4~8, D=4~8")
        out.append(row)
    return out


def build(root, name, kind, custom):
    config = read_json(root / "config.json")
    rows = normalize([{"run": "custom", **custom}] if kind == "custom" else source_rows(root, kind), kind, config)
    target = root / "studies" / safe_name(name)
    if target.exists(): raise ValueError("같은 이름의 재현 묶음이 이미 있습니다")
    target.mkdir(parents=True)
    try:
        frozen = {"study": config["study"], "kind": kind, "design_count": len(rows), "execution": "blocked_until_reviewed_mesh_contract", "published": config["published"], "published_numerics": config["published_numerics"], "openfoam_mapping": config["openfoam_mapping"], "mesh": config["mesh"], "design_domains": config["design_domains"], "unpublished_assumptions": config["assumptions"]}
        write(target / "study.json", json.dumps(frozen, ensure_ascii=False, indent=2) + "\n")
        shutil.copy2(root / "ASSUMPTIONS.md", target / "ASSUMPTIONS.md")
        with open(target / "design.csv", "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["case_id", "A_mm", "B_layers", "C_mm", "D_count", "paper_one_minus_CV", "paper_CV"], extrasaction="ignore")
            writer.writeheader(); writer.writerows(rows)
        lines = ["case_id,A_mm,B_layers,C_mm,D_count,paper_CV,computed_mean_velocity_m_s,computed_CV,pressure_drop_Pa,status\n"]
        for row in rows: lines.append("%s,%s,%s,%s,%s,%s,,,,contracts_required\n" % (row["case_id"], row["A_mm"], row["B_layers"], row["C_mm"], row["D_count"], row.get("paper_CV", "")))
        write(target / "results" / "summary.csv", "".join(lines))
        write(target / "README.md", "# Chen et al. (2026) independent reproduction\n\nThis study contains published values and explicit unset assumptions only. It does not claim author-package reproduction.\n\nExecution is blocked until a reviewed mesh contract supplies CAD, `grainZone`, patch names, and the CV plane.\n")
        for row in rows:
            case = target / "cases" / row["case_id"]
            case_files(case, row, config)
            write(case / "tools" / "preflight.py", PREFLIGHT, True)
            write(case / "tools" / "calc_cv.py", CV_SCRIPT, True)
            write(case / "tools" / "calc_pressure_drop.py", PRESSURE_SCRIPT, True)
            write(case / "tools" / "runtime_plan.py", RUNTIME_PLAN, True)
            write(case / "Allrun", ALLRUN, True)
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise
    return {"ok": True, "study": target.name, "folder": str(target), "case_count": len(rows), "execution": "contracts_required"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT)); parser.add_argument("--name", required=True)
    parser.add_argument("--kind", required=True, choices=("reference", "l9", "box_behnken", "final", "custom"))
    parser.add_argument("--A", type=int); parser.add_argument("--B", type=int); parser.add_argument("--C", type=int); parser.add_argument("--D", type=int)
    args = parser.parse_args(); custom = {"A_mm": args.A, "B_layers": args.B, "C_mm": args.C, "D_count": args.D}
    if args.kind == "custom" and any(value is None for value in custom.values()): raise SystemExit("custom 재현은 A/B/C/D를 모두 입력해야 합니다")
    try: print(json.dumps(build(Path(args.root).resolve(), args.name, args.kind, custom), ensure_ascii=False))
    except Exception as exc: print(json.dumps({"ok": False, "msg": str(exc)}, ensure_ascii=False)); return 2
    return 0


if __name__ == "__main__": sys.exit(main())
