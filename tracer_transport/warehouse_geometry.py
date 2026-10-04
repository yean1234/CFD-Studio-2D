"""Parametric gabled-domain mesh preflight, independent of gas chemistry.

This builds geometry only. It does not turn unmeasured transport properties
into a runnable or experimentally validated fumigation case.
"""
import argparse
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import time


def positive(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f'{name} must be finite and positive')
    return value


def validate(spec):
    if set(spec) != {'schema', 'geometry', 'mesh', 'evidence', 'unresolved'} or spec['schema'] != 1:
        raise ValueError('Unknown geometry specification schema or fields')
    g = spec['geometry']
    if set(g) != {'length_m', 'width_m', 'eaves_m', 'roof_rise_m', 'coordinate_basis'}:
        raise ValueError('Geometry requires explicit dimensions and coordinate basis')
    for key in ('length_m', 'width_m', 'eaves_m', 'roof_rise_m'):
        positive(g[key], key)
    if g['coordinate_basis'] not in ('nominal_drawing_envelope', 'confirmed_internal_clearance'):
        raise ValueError('Unknown coordinate basis')
    if not isinstance(spec['evidence'], str) or not spec['evidence'].strip():
        raise ValueError('Geometry provenance is required')
    if not isinstance(spec['unresolved'], list) or not all(isinstance(x, str) and x.strip() for x in spec['unresolved']):
        raise ValueError('Unresolved conditions must be an explicit list')
    m = spec['mesh']
    if set(m) != {'nx', 'ny_per_half', 'nz', 'maximum_cells'}:
        raise ValueError('Unknown mesh fields')
    if any(isinstance(v, bool) or not isinstance(v, int) or v < 1 for v in m.values()):
        raise ValueError('Mesh counts must be positive integers')
    cells = 2 * m['nx'] * m['ny_per_half'] * m['nz']
    if cells > m['maximum_cells']:
        raise ValueError('Requested mesh exceeds the explicit cell budget')
    return {'cells': cells, 'volume_m3': g['length_m'] * g['width_m'] * (g['eaves_m'] + g['roof_rise_m']/2),
            'mesh_only': True, 'transport_ready': False,
            'coordinate_system': 'metres; x length, y width, z above floor; origin at storage corner',
            'coordinate_basis': g['coordinate_basis'], 'unresolved': spec['unresolved']}


def header(name):
    return f'FoamFile {{ version 2.0; format ascii; class dictionary; object {name}; }}\n'


def mesh_dictionary(spec):
    validate(spec)
    g, m = spec['geometry'], spec['mesh']
    length, width = g['length_m'], g['width_m']
    eaves, ridge = g['eaves_m'], g['eaves_m'] + g['roof_rise_m']
    vertices = [(x, y, z) for zlevel in (0, 1) for y, height in ((0, eaves), (width/2, ridge), (width, eaves))
                for x in (0, length) for z in (height if zlevel else 0,)]
    vertex_text = '\n'.join('(%g %g %g)' % v for v in vertices)
    count = f"({m['nx']} {m['ny_per_half']} {m['nz']})"
    # Both halves share the ridge plane; no internal wall is inserted there.
    return header('blockMeshDict') + f'''convertToMeters 1;
vertices ({vertex_text});
blocks (
    hex (0 1 3 2 6 7 9 8) {count} simpleGrading (1 1 1)
    hex (2 3 5 4 8 9 11 10) {count} simpleGrading (1 1 1)
);
edges ();
boundary (
    floor {{ type wall; faces ((0 2 3 1) (2 4 5 3)); }}
    roof {{ type wall; faces ((6 7 9 8) (8 9 11 10)); }}
    sideWalls {{ type wall; faces ((0 1 7 6) (4 10 11 5)); }}
    endWall {{ type wall; faces ((0 6 8 2) (2 8 10 4)); }}
    annexInterface {{ type wall; faces ((1 3 9 7) (3 5 11 9)); }}
);
mergePatchPairs ();
'''


def checked_mesh_quality(log_text, expected_cells, expected_volume_m3, extra_patches=()):
    """Read independent checkMesh measurements, failing closed on missing data."""
    if 'Mesh OK.' not in log_text:
        raise RuntimeError('checkMesh did not report Mesh OK; inspect preserved logs')
    number = r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)'

    def metric(pattern, name, convert=float):
        found = re.search(pattern, log_text, re.MULTILINE)
        if not found:
            raise RuntimeError(f'checkMesh did not report {name}; inspect preserved logs')
        value = convert(found.group(1))
        if not math.isfinite(value):
            raise RuntimeError(f'checkMesh reported invalid {name}')
        return value

    cells = metric(r'^\s*cells:\s*(\d+)\s*$', 'cell count', int)
    volume = metric(r'\bTotal volume\s*=\s*'+number, 'total volume')
    regions = metric(r'\bNumber of regions:\s*(\d+)', 'region count', int)
    nonorthogonality = metric(r'\bMesh non-orthogonality Max:\s*'+number, 'non-orthogonality')
    skewness = metric(r'\bMax skewness\s*=\s*'+number, 'skewness')
    patches = {}
    for name in ('floor', 'roof', 'sideWalls', 'endWall', 'annexInterface') + tuple(extra_patches):
        patches[name] = metric(r'^\s*'+name+r'\s+(\d+)\s+', name+' patch', int)
    if cells != expected_cells or regions != 1 or any(count < 1 for count in patches.values()):
        raise RuntimeError('checkMesh topology disagrees with the requested domain')
    if volume <= 0 or not math.isclose(volume, expected_volume_m3, rel_tol=1e-4, abs_tol=1e-6):
        raise RuntimeError('checkMesh volume disagrees with the requested geometry')
    return {'checked_cells': cells, 'checked_volume_m3': volume, 'connected_regions': regions,
            'max_nonorthogonality_deg': nonorthogonality, 'max_skewness': skewness,
            'boundary_faces': patches}


def build(spec, destination, check=False):
    report = validate(spec)
    destination = Path(destination)
    if check and any(shutil.which(tool) is None for tool in ('blockMesh', 'checkMesh')):
        raise RuntimeError('Load the OpenFOAM environment before --check-mesh')
    destination.mkdir(parents=True, exist_ok=False)
    (destination/'system').mkdir()
    (destination/'constant').mkdir()
    (destination/'geometry.json').write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding='utf-8')
    (destination/'system/blockMeshDict').write_text(mesh_dictionary(spec), encoding='ascii')
    (destination/'system/controlDict').write_text(header('controlDict') +
        'application blockMesh; startFrom startTime; startTime 0; stopAt endTime; endTime 0;\n'
        'deltaT 1; writeControl timeStep; writeInterval 1;\n', encoding='ascii')
    (destination/'system/fvSchemes').write_text(header('fvSchemes') +
        'ddtSchemes { default Euler; } gradSchemes { default Gauss linear; }\n'
        'divSchemes { default none; } laplacianSchemes { default Gauss linear corrected; }\n'
        'interpolationSchemes { default linear; } snGradSchemes { default corrected; }\n', encoding='ascii')
    (destination/'system/fvSolution').write_text(header('fvSolution') + 'solvers {}\n', encoding='ascii')
    report['status'] = 'generated_not_checked'
    started = time.monotonic()
    try:
        if check:
            for tool in ('blockMesh', 'checkMesh'):
                args = [tool, '-case', str(destination.resolve())]
                if tool == 'checkMesh':
                    args += ['-allTopology', '-allGeometry']
                with (destination/f'log.{tool}').open('w') as log:
                    subprocess.run(args, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=300)
            report['mesh_quality'] = checked_mesh_quality(
                (destination/'log.checkMesh').read_text(), report['cells'], report['volume_m3'])
            report['status'] = 'mesh_checked'
    except (subprocess.SubprocessError, OSError, RuntimeError) as exc:
        report.update(status='failed', error=str(exc))
        raise
    finally:
        report['mesh_build_wall_seconds'] = time.monotonic() - started
        (destination/'geometry_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--check-mesh', action='store_true')
    args = parser.parse_args()
    print(json.dumps(build(json.loads(args.config.read_text(encoding='utf-8')), args.output, args.check_mesh), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
