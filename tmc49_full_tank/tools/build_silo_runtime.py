#!/usr/bin/env python3
"""Build the grain-silo case in CFD Studio's normal active-case directory."""
import json
import math
import os
import shutil

if __package__:
    from .silo_contract import original_design, validate_runtime
    from .mesh_refinement import refinement_boxes, collect_refinements
else:
    from silo_contract import original_design, validate_runtime
    from mesh_refinement import refinement_boxes, collect_refinements


def header(cls, location, obj):
    return f"""FoamFile
{{
    version 2.0;
    format ascii;
    class {cls};
    location \"{location}\";
    object {obj};
}}
// ************************************************************************* //
"""


def field_header(cls, obj):
    return header(cls, "0", obj)


def boundary_text(inlet, outlet, wall, extra_inlets=()):
    lines = ["boundaryField", "{", f"    inlet {{ {inlet} }}"]
    lines.extend(f"    {name} {{ {spec} }}" for name, spec in extra_inlets)
    lines.extend((f"    outlet {{ {outlet} }}", f"    walls {{ {wall} }}",
                  f"    bottomWall {{ {wall} }}", "}", ""))
    return "\n".join(lines)


def design_geometry(cfg, plan):
    """Return the explicit, documented surrogate geometry for design comparison."""
    assumptions = validate_runtime(cfg)
    silo = cfg["silo"]
    model = str(silo.get("geometry_model") or "").strip()
    if model != "equivalent_boundary_ports_v1":
        raise ValueError("지원하지 않는 저장고 형상 모델입니다")

    kind = silo["kind"]
    design = original_design(silo) if kind == "original" else silo["design"]
    A = float(design.get("A", 0)) / 1000.0
    B = int(design.get("B", 0))
    C = float(design.get("C", 0) or 0) / 1000.0
    D = int(design.get("D", 0) or 0)
    ports_per_layer = int(assumptions["ports_per_layer"])
    if A <= 0 or B < 1 or ports_per_layer < 1:
        raise ValueError("등가 형상에는 A, B, 층당 포트 수가 필요합니다")

    grain = plan["grain"]
    z_min = float(assumptions["layer_z_min_m"])
    z_max = float(assumptions["layer_z_max_m"])
    bottom_enabled = assumptions["bottom_outlets_enabled"]
    if not (0 < z_min <= z_max < grain):
        raise ValueError("순환 포트 높이 범위는 곡물층 내부여야 합니다")
    if bottom_enabled and (C <= 0 or D < 1):
        raise ValueError("하부 포트를 사용하려면 C와 D가 양수여야 합니다")

    if B == 1:
        heights = [(z_min + z_max) / 2.0]
    else:
        heights = [z_min + (z_max - z_min) * i / (B - 1) for i in range(B)]
    radius = plan["radius"]
    side_centres = []
    for z in heights:
        for i in range(ports_per_layer):
            angle = 2.0 * math.pi * i / ports_per_layer
            side_centres.append((radius * math.cos(angle), radius * math.sin(angle), z))

    bottom_ring_radius = float(assumptions["bottom_ring_radius_m"]) if bottom_enabled else 0.0
    if bottom_enabled and not (0 < bottom_ring_radius < radius):
        raise ValueError("하부 포트 링 반경은 저장고 반경보다 작아야 합니다")
    bottom_centres = []
    if bottom_enabled:
        for i in range(D):
            angle = 2.0 * math.pi * i / D
            bottom_centres.append((bottom_ring_radius * math.cos(angle),
                                   bottom_ring_radius * math.sin(angle), 0.0))

    equivalent_spacing = plan["equivalent_spacing_mm"] / 1000.0
    # The paper's 6-10 mm apertures are near the selected mesh spacing.  The
    # selection sphere therefore needs to reach the nearest boundary-face
    # centre; flowRateInletVelocity still enforces the nominal aperture flow.
    side_pick_radius = max(0.525 * A, 0.95 * equivalent_spacing)
    bottom_pick_radius = max(0.525 * C, 0.95 * equivalent_spacing) if bottom_centres else 0.0
    return {
        "model": model, "kind": kind, "A_m": A, "B": B, "C_m": C, "D": D,
        "ports_per_layer": ports_per_layer, "layer_heights_m": heights,
        "side_centres": side_centres, "bottom_centres": bottom_centres,
        "side_pick_radius_m": side_pick_radius,
        "bottom_pick_radius_m": bottom_pick_radius,
        "bottom_ring_radius_m": bottom_ring_radius,
        "assumption_source": assumptions.get("source", ""),
    }


def mesh_plan(cfg):
    """Choose an O-grid layout close to the target with balanced cell spacing."""
    p = cfg["published"]
    radius = float(p["storage_diameter_m"]) / 2.0
    height = float(p["total_height_m"])
    grain = float(p["grain_height_m"])
    duct_d = float(p["bottom_central_duct_diameter_m"])
    target = int(cfg["mesh"]["target_cells"])
    inlet_half = math.sqrt(math.pi * (duct_d / 2.0) ** 2) / 2.0
    inlet_half = min(radius * 0.72, max(radius * 0.08, inlet_half))
    outer = radius / math.sqrt(2.0)

    best = None
    for ncore in range(8, 401):
        inner_spacing = 2.0 * inlet_half / ncore
        nradial = max(3, round((outer - inlet_half) / inner_spacing))
        horizontal = ncore * ncore + 4 * ncore * nradial
        nz = max(4, round(target / horizontal))
        actual = horizontal * nz
        spacings = (
            inner_spacing,
            (outer - inlet_half) / nradial,
            2.0 * outer / ncore,
            height / nz,
        )
        aspect = max(spacings) / min(spacings)
        target_error = abs(math.log(actual / target))
        candidate = (20.0 * target_error + math.log(aspect), ncore,
                     nradial, nz, actual, spacings, aspect)
        if best is None or candidate < best:
            best = candidate

    _, ncore, nradial, nz, actual, spacings, aspect = best
    nz_grain = max(2, round(nz * grain / height))
    nz_air = max(2, nz - nz_grain)
    nz = nz_grain + nz_air
    actual = (ncore * ncore + 4 * ncore * nradial) * nz
    equivalent = (math.pi * radius * radius * height / actual) ** (1.0 / 3.0)
    plan = {
        "radius": radius, "height": height, "grain": grain,
        "inlet_half": inlet_half, "outer": outer,
        "ncore": ncore, "nradial": nradial,
        "nz_grain": nz_grain, "nz_air": nz_air,
        "actual_cells": actual,
        "equivalent_spacing_mm": equivalent * 1000.0,
        "estimated_min_spacing_mm": min(spacings) * 1000.0,
        "estimated_max_spacing_mm": max(spacings) * 1000.0,
        "estimated_max_aspect_ratio": aspect,
    }

    return refine_plan(cfg, plan)


def refine_plan(cfg, plan):
    """Keep matching O-grid faces; XY refinement propagates across all layers."""
    mesh=cfg['mesh'];regions=collect_refinements(cfg,mesh)
    if not isinstance(regions,list):raise ValueError('[MESH-R003] refinement_regions must be a list')
    if not regions:return plan
    radius,height,grain=(plan[k] for k in ('radius','height','grain'))
    base=(math.pi*radius**2*height/mesh['target_cells'])**(1/3)
    boxes=refinement_boxes({'dx_mm':base*1000,'refinement_regions':mesh.get('refinement_regions',[])},
                           [radius*1000,radius*1000,height*1000],cfg,
                           [-radius*1000,-radius*1000,0])
    boxes=[([v/1000 for v in lo],[v/1000 for v in hi],size/1000) for lo,hi,size in boxes]
    for lo,hi,_ in boxes:
        closest=[max(lo[i],min(0,hi[i])) for i in range(2)]
        if math.hypot(*closest)>=radius:
            raise ValueError('[MESH-R004] Refinement does not intersect the cylindrical domain')
    spacing=min(size for _,_,size in boxes)
    limit=mesh.get('maximum_cells',20000000)
    if type(limit) is not int or not 1<=limit<=20000000:
        raise ValueError('[MESH-R005] maximum_cells must be an integer from 1 to 20000000')
    # Reject excessive subdivision before converting ratios to cell counts
    if max(radius,height)/spacing>limit:
        raise ValueError('[MESH-R005] Refinement spacing exceeds the cell budget')
    ncore=max(plan['ncore'],math.ceil(max(2*plan['inlet_half'],math.pi*radius/2)/spacing))
    nradial=max(plan['nradial'],math.ceil((radius-plan['inlet_half'])/spacing))
    levels=sorted({0.,grain,height,*[p[2] for lo,hi,_ in boxes for p in (lo,hi)]})
    counts=[]
    for a,b in zip(levels,levels[1:]):
        original=grain/plan['nz_grain'] if b<=grain else (height-grain)/plan['nz_air']
        local=min([original]+[size for lo,hi,size in boxes if a<hi[2] and b>lo[2]])
        counts.append(max(1,math.ceil((b-a)/local)))
    cells=(ncore*ncore+4*ncore*nradial)*sum(counts)
    if cells>limit:raise ValueError(f'[MESH-R005] Refinement needs {cells} cells; limit is {limit}')
    spacings=[2*plan['inlet_half']/ncore,(plan['outer']-plan['inlet_half'])/nradial,
              math.pi*radius/(2*ncore),*[(b-a)/n for a,b,n in zip(levels,levels[1:],counts)]]
    plan.update(ncore=ncore,nradial=nradial,z_levels=levels,z_counts=counts,
                nz_grain=sum(n for b,n in zip(levels[1:],counts) if b<=grain),
                nz_air=sum(n for a,n in zip(levels,counts) if a>=grain),actual_cells=cells,
                equivalent_spacing_mm=(math.pi*radius**2*height/cells)**(1/3)*1000,
                estimated_min_spacing_mm=min(spacings)*1000,
                estimated_max_spacing_mm=max(spacings)*1000,
                estimated_max_aspect_ratio=max(spacings)/min(spacings),
                refinement={'strategy':'conformal_ogrid_xy_global_z_local',
                            'base_reference_spacing_m':base,'resolved_boxes_m':boxes,
                            'requested_regions':regions})
    return plan


def block_mesh(cfg):
    plan = mesh_plan(cfg)
    radius, height, grain = plan["radius"], plan["height"], plan["grain"]
    inlet_half, outer = plan["inlet_half"], plan["outer"]
    ncore, nradial = plan["ncore"], plan["nradial"]
    nz_grain, nz_air = plan["nz_grain"], plan["nz_air"]

    xy = [(-inlet_half, -inlet_half), (inlet_half, -inlet_half),
          (inlet_half, inlet_half), (-inlet_half, inlet_half),
          (-outer, -outer), (outer, -outer), (outer, outer), (-outer, outer)]
    levels = plan.get("z_levels", [0.0, grain, height])
    vertices = [(x, y, z) for z in levels for x, y in xy]
    def v(level, point): return level * 8 + point
    shapes = [(0, 1, 2, 3), (4, 5, 1, 0), (5, 6, 2, 1),
              (3, 2, 6, 7), (4, 0, 3, 7)]
    lines = [header("dictionary", "system", "blockMeshDict"), "scale 1;", "vertices\n("]
    lines.extend(f"    ({x:.12g} {y:.12g} {z:.12g})" for x, y, z in vertices)
    lines.extend([");", "blocks\n("])
    for layer, zcells in enumerate(plan.get("z_counts", (nz_grain, nz_air))):
        for index, shape in enumerate(shapes):
            lower = [v(layer, point) for point in shape]
            upper = [v(layer + 1, point) for point in shape]
            if index == 0:
                nx, ny = ncore, ncore
            elif index == 4:
                nx, ny = nradial, ncore
            else:
                nx, ny = ncore, nradial
            lines.append("    hex (%s) (%d %d %d) simpleGrading (1 1 1)" %
                         (" ".join(map(str, lower + upper)), nx, ny, zcells))
    lines.extend([");", "edges\n("])
    arc_mid = [((4, 5), (0, -radius)), ((5, 6), (radius, 0)),
               ((6, 7), (0, radius)), ((7, 4), (-radius, 0))]
    for level, z in enumerate(levels):
        for (a, b), (mx, my) in arc_mid:
            lines.append(f"    arc {v(level, a)} {v(level, b)} ({mx:.12g} {my:.12g} {z:.12g})")
    lines.extend([");", "boundary\n(", "    inlet\n    {\n        type patch;\n        faces\n        ("])
    lines.append("            (%s)" % " ".join(map(str, [v(0, 0), v(0, 3), v(0, 2), v(0, 1)])))
    lines.extend(["        );\n    }", "    bottomWall\n    {\n        type wall;\n        faces\n        ("])
    for shape in shapes[1:]:
        lines.append("            (%s)" % " ".join(map(str, [v(0, shape[0]), v(0, shape[3]), v(0, shape[2]), v(0, shape[1])])))
    lines.extend(["        );\n    }", "    outlet\n    {\n        type patch;\n        faces\n        ("])
    for shape in shapes:
        lines.append("            (%s)" % " ".join(map(str, [v(len(levels)-1, point) for point in shape])))
    lines.extend(["        );\n    }", "    walls\n    {\n        type wall;\n        faces\n        ("])
    outer_edges = [(4, 5), (5, 6), (6, 7), (7, 4)]
    for layer in range(len(levels)-1):
        for a, b in outer_edges:
            lines.append("            (%s)" % " ".join(map(str, [v(layer, a), v(layer, b), v(layer + 1, b), v(layer + 1, a)])))
    lines.extend(["        );\n    }", ");", "mergePatchPairs ();", ""])
    return "\n".join(lines), plan


def topo_set(cfg, plan):
    p = cfg["published"]
    radius = float(p["storage_diameter_m"]) / 2.0
    grain = float(p["grain_height_m"])
    actions = f"""
    {{
        name grainCells;
        type cellSet;
        action new;
        source cylinderToCell;
        sourceInfo
        {{
            p1 (0 0 {-1e-6:.12g});
            p2 (0 0 {grain + 1e-6:.12g});
            radius {radius + 1e-6:.12g};
        }}
    }}
    {{
        name grainZone;
        type cellZoneSet;
        action new;
        source setToCellZone;
        set grainCells;
    }}
"""
    geometry = design_geometry(cfg, plan)
    if geometry:
        actions += """
    {
        name sideWallFaces;
        type faceSet;
        action new;
        source patchToFace;
        patch walls;
    }
"""
        for index, centre in enumerate(geometry["side_centres"]):
            action = "new" if index == 0 else "add"
            actions += f"""
    {{
        name sideInletFaces;
        type faceSet;
        action {action};
        source sphereToFace;
        origin ({centre[0]:.12g} {centre[1]:.12g} {centre[2]:.12g});
        radius {geometry['side_pick_radius_m']:.12g};
    }}
"""
        actions += """
    {
        name sideInletFaces;
        type faceSet;
        action subset;
        source faceToFace;
        set sideWallFaces;
    }
"""
        if geometry["bottom_centres"]:
            actions += """
    {
        name bottomWallFaces;
        type faceSet;
        action new;
        source patchToFace;
        patch bottomWall;
    }
"""
            for index, centre in enumerate(geometry["bottom_centres"]):
                action = "new" if index == 0 else "add"
                actions += f"""
    {{
        name bottomInletFaces;
        type faceSet;
        action {action};
        source sphereToFace;
        origin ({centre[0]:.12g} {centre[1]:.12g} {centre[2]:.12g});
        radius {geometry['bottom_pick_radius_m']:.12g};
    }}
"""
            actions += """
    {
        name bottomInletFaces;
        type faceSet;
        action subset;
        source faceToFace;
        set bottomWallFaces;
    }
"""
    return header("dictionary", "system", "topoSetDict") + "actions\n(\n" + actions + ");\n"


def create_patch(cfg, plan):
    geometry = design_geometry(cfg, plan)
    if not geometry:
        return None
    entries = ["""
    {
        name sideInlets;
        patchInfo { type patch; }
        constructFrom set;
        set sideInletFaces;
    }
"""]
    if geometry["bottom_centres"]:
        entries.append("""
    {
        name bottomInlets;
        patchInfo { type patch; }
        constructFrom set;
        set bottomInletFaces;
    }
""")
    return (header("dictionary", "system", "createPatchDict")
            + "pointSync false;\npatches\n(\n" + "".join(entries) + ");\n")


def dictionaries(cfg, plan):
    p = cfg["published"]
    om = cfg["openfoam_mapping"]
    controls = cfg["solver_controls"]
    run = cfg["run"]
    solver = om["solver"]
    transient = solver == "pimpleFoam"
    turbulence = om["turbulence"]
    speed = float(p["inlet_speed_m_s"])
    intensity = float(controls["turbulence_intensity"])
    length = float(controls["turbulence_length_scale_m"])
    k0 = 1.5 * (speed * intensity) ** 2
    epsilon0 = 0.09 ** 0.75 * k0 ** 1.5 / length
    tolerance = float(controls["convergence_tolerance"])
    geometry = design_geometry(cfg, plan)
    stop_mode = str(run.get("stop_mode", "fixed")).strip().lower()
    ddt = "Euler" if transient else "steadyState"
    algorithm = "PIMPLE" if transient else "SIMPLE"
    algorithm_body = "nOuterCorrectors 2; nCorrectors 2; nNonOrthogonalCorrectors 0;" if transient else "nNonOrthogonalCorrectors 0;"
    if transient:
        residual_control = f"""residualControl
    {{
        p {{ tolerance {tolerance:.12g}; relTol 0; }}
        U {{ tolerance {tolerance:.12g}; relTol 0; }}
        k {{ tolerance {tolerance:.12g}; relTol 0; }}
        epsilon {{ tolerance {tolerance:.12g}; relTol 0; }}
    }}"""
    else:
        # In convergence mode endTime remains a hard safety cap. SIMPLE stops
        # earlier only after every selected equation satisfies this threshold.
        residual_control = f"""residualControl
    {{
        p {tolerance:.12g};
        U {tolerance:.12g};
        k {tolerance:.12g};
        epsilon {tolerance:.12g};
    }}""" if stop_mode == "converged" else ""
    write_control = "adjustableRunTime" if transient else "timeStep"
    if transient:
        end_value = float(run["end_time_s"])
        write_value = float(run["write_interval_s"])
        delta_t = float(run.get("time_step_s", run.get("max_dt_s", 0.01)))
    else:
        end_value = int(run.get("max_iterations", run["end_time_s"]))
        write_value = int(run.get("write_interval_iterations", run["write_interval_s"]))
        delta_t = 1

    transport = header("dictionary", "constant", "transportProperties") + (
        "transportModel Newtonian;\n"
        f"nu [0 2 -1 0 0 0 0] {float(p['nu_m2_s']):.12g};\n"
        f"rho [1 -3 0 0 0 0 0] {float(p['rho_kg_m3']):.12g};\n")
    turbulence_props = header("dictionary", "constant", "turbulenceProperties") + f"""simulationType RAS;
RAS
{{
    RASModel {turbulence};
    turbulence on;
    printCoeffs on;
}}
"""
    fv_options = header("dictionary", "constant", "fvOptions") + f"""cornPorous
{{
    type explicitPorositySource;
    active yes;
    explicitPorositySourceCoeffs
    {{
        type DarcyForchheimer;
        selectionMode cellZone;
        cellZone grainZone;
        DarcyForchheimerCoeffs
        {{
            d d [0 -2 0 0 0 0 0] ({float(p['darcy_d_1_m2']):.12g} {float(p['darcy_d_1_m2']):.12g} {float(p['darcy_d_1_m2']):.12g});
            f f [0 -1 0 0 0 0 0] ({float(p['forchheimer_f_1_m']):.12g} {float(p['forchheimer_f_1_m']):.12g} {float(p['forchheimer_f_1_m']):.12g});
            coordinateSystem {{ origin (0 0 0); e1 (1 0 0); e2 (0 1 0); }}
        }}
    }}
}}
"""
    control = header("dictionary", "system", "controlDict") + f"""application {solver};
startFrom startTime;
startTime 0;
stopAt endTime;
endTime {end_value:.12g};
deltaT {delta_t:.12g};
writeControl {write_control};
writeInterval {write_value:.12g};
purgeWrite 0;
writeFormat binary;
writePrecision 8;
writeCompression off;
timeFormat general;
timePrecision 8;
runTimeModifiable true;
"""
    schemes = header("dictionary", "system", "fvSchemes") + f"""ddtSchemes {{ default {ddt}; }}
gradSchemes {{ default cellLimited Gauss linear 1; }}
divSchemes
{{
    default none;
    div(phi,U) bounded Gauss linearUpwind grad(U);
    div(phi,k) bounded Gauss limitedLinear 1;
    div(phi,epsilon) bounded Gauss limitedLinear 1;
    div((nuEff*dev2(T(grad(U))))) Gauss linear;
}}
laplacianSchemes {{ default Gauss linear limited 0.5; }}
interpolationSchemes {{ default linear; }}
snGradSchemes {{ default limited 0.5; }}
wallDist {{ method meshWave; }}
"""
    solution = header("dictionary", "system", "fvSolution") + f"""solvers
{{
    p {{ solver GAMG; tolerance {tolerance:.12g}; relTol 0.05; smoother GaussSeidel; }}
    pFinal {{ $p; relTol 0; }}
    \"(U|k|epsilon)\" {{ solver smoothSolver; smoother symGaussSeidel; tolerance {tolerance:.12g}; relTol 0.1; }}
    \"(U|k|epsilon)Final\" {{ $U; relTol 0; }}
}}
{algorithm}
{{
    {algorithm_body}
    {residual_control}
}}
relaxationFactors
{{
    fields {{ p 0.2; }}
    equations {{ U 0.3; k 0.3; epsilon 0.3; }}
}}
"""
    decompose = header("dictionary", "system", "decomposeParDict") + "numberOfSubdomains 1;\nmethod scotch;\n"
    extra_u = []
    extra_p = []
    extra_k = []
    extra_epsilon = []
    extra_nut = []
    if geometry:
        central_area = math.pi * (float(p["bottom_central_duct_diameter_m"]) / 2.0) ** 2
        side_area = len(geometry["side_centres"]) * math.pi * (geometry["A_m"] / 2.0) ** 2
        bottom_area = len(geometry["bottom_centres"]) * math.pi * (geometry["C_m"] / 2.0) ** 2
        total_area = central_area + side_area + bottom_area
        total_flow = speed * central_area
        q_central = total_flow * central_area / total_area
        q_side = total_flow * side_area / total_area
        q_bottom = total_flow * bottom_area / total_area if bottom_area else 0.0
        inlet_u = f"type flowRateInletVelocity; volumetricFlowRate constant {q_central:.12g}; value uniform (0 0 {speed:.12g});"
        extra_u.append(("sideInlets", f"type flowRateInletVelocity; volumetricFlowRate constant {q_side:.12g}; value uniform (0 0 0);"))
        if geometry["bottom_centres"]:
            extra_u.append(("bottomInlets", f"type flowRateInletVelocity; volumetricFlowRate constant {q_bottom:.12g}; value uniform (0 0 {speed:.12g});"))
        for name, _ in extra_u:
            extra_p.append((name, "type zeroGradient;"))
            extra_k.append((name, f"type fixedValue; value uniform {k0:.12g};"))
            extra_epsilon.append((name, f"type fixedValue; value uniform {epsilon0:.12g};"))
            extra_nut.append((name, "type calculated; value uniform 0;"))
        plan["inlet_flow_m3_s"] = {
            "total": total_flow, "central": q_central, "side": q_side,
            "bottom": q_bottom, "nominal_total_open_area_m2": total_area,
        }
    else:
        inlet_u = f"type fixedValue; value uniform (0 0 {speed:.12g});"

    U = field_header("volVectorField", "U") + f"""dimensions [0 1 -1 0 0 0 0];
internalField uniform (0 0 0);
""" + boundary_text(inlet_u,
                       "type inletOutlet; inletValue uniform (0 0 0); value uniform (0 0 0);",
                       "type noSlip;", extra_u)
    pressure = field_header("volScalarField", "p") + "dimensions [0 2 -2 0 0 0 0];\ninternalField uniform 0;\n" + boundary_text(
        "type zeroGradient;", "type fixedValue; value uniform 0;", "type zeroGradient;", extra_p)
    kval = field_header("volScalarField", "k") + f"dimensions [0 2 -2 0 0 0 0];\ninternalField uniform {k0:.12g};\n" + boundary_text(
        f"type fixedValue; value uniform {k0:.12g};",
        f"type inletOutlet; inletValue uniform {k0:.12g}; value uniform {k0:.12g};",
        f"type kqRWallFunction; value uniform {k0:.12g};", extra_k)
    epsilon = field_header("volScalarField", "epsilon") + f"dimensions [0 2 -3 0 0 0 0];\ninternalField uniform {epsilon0:.12g};\n" + boundary_text(
        f"type fixedValue; value uniform {epsilon0:.12g};",
        f"type inletOutlet; inletValue uniform {epsilon0:.12g}; value uniform {epsilon0:.12g};",
        f"type epsilonWallFunction; value uniform {epsilon0:.12g};", extra_epsilon)
    nut = field_header("volScalarField", "nut") + "dimensions [0 2 -1 0 0 0 0];\ninternalField uniform 0;\n" + boundary_text(
        "type calculated; value uniform 0;", "type calculated; value uniform 0;",
        "type nutkWallFunction; value uniform 0;", extra_nut)
    return {
        "constant/transportProperties": transport,
        "constant/turbulenceProperties": turbulence_props,
        "constant/fvOptions": fv_options,
        "system/controlDict": control, "system/fvSchemes": schemes,
        "system/fvSolution": solution, "system/decomposeParDict": decompose,
        "0.orig/U": U, "0.orig/p": pressure, "0.orig/k": kval,
        "0.orig/epsilon": epsilon, "0.orig/nut": nut,
    }


def build(root, cfg, check=False):
    validate_runtime(cfg)
    om = cfg.get("openfoam_mapping") or {}
    if om.get("solver") not in ("simpleFoam", "pimpleFoam"):
        raise ValueError("저장고 솔버는 simpleFoam 또는 pimpleFoam이어야 합니다")
    if om.get("turbulence") not in ("kEpsilon", "realizableKE", "RNGkEpsilon"):
        raise ValueError("지원하지 않는 난류 모델입니다")
    mesh, plan = block_mesh(cfg)
    files = dictionaries(cfg, plan)
    files["system/blockMeshDict"] = mesh
    files["system/topoSetDict"] = topo_set(cfg, plan)
    patch_dict = create_patch(cfg, plan)
    if patch_dict:
        files["system/createPatchDict"] = patch_dict
    if check:
        print(f"[build_case] 식량 저장고 설정 검증 통과 · 예상 격자 {plan['actual_cells']:,}")
        return
    for rel in ("0.orig",):
        shutil.rmtree(os.path.join(root, rel), ignore_errors=True)
    for rel, content in files.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
    geometry = design_geometry(cfg, plan)
    manifest = {"analysis_type": "grain_silo", "solver": om["solver"],
                "turbulence": om["turbulence"], "design": (cfg.get("silo") or {}).get("design") or {},
                "target_cells": cfg["mesh"]["target_cells"],
                "generated_cells": plan["actual_cells"],
                "mesh_plan": {key: plan[key] for key in (
                    "ncore", "nradial", "nz_grain", "nz_air",
                    "equivalent_spacing_mm", "estimated_min_spacing_mm",
                    "estimated_max_spacing_mm", "estimated_max_aspect_ratio")},
                "spatial_discretization": "bounded second-order",
                "output_fields": cfg["run"].get("output_fields") or [],
                "reproduction_status": "reviewed_surrogate_not_paper_geometry",
                "geometry_assumptions": dict(cfg["silo"]["geometry_assumptions"])}
    if "refinement" in plan:
        manifest["mesh_plan"].update({key: plan[key] for key in ("refinement", "z_levels", "z_counts")})
    if geometry:
        manifest["geometry_model"] = {
            key: geometry[key] for key in (
                "model", "kind", "A_m", "B", "C_m", "D",
                "ports_per_layer", "layer_heights_m", "bottom_ring_radius_m",
                "assumption_source")
        }
        manifest["inlet_flow_m3_s"] = plan.get("inlet_flow_m3_s")
    with open(os.path.join(root, "case_manifest.json"), "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"[build_case] 식량 저장고 케이스 생성 · {om['solver']} · 격자 {plan['actual_cells']:,} · 등가 간격 {plan['equivalent_spacing_mm']:.2f} mm")
