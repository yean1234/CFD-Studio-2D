"""Explicit Y-midplane reduction for the sealed, uniformly heated warehouse model"""
import math

MODES = ('full', 'symmetry_y_min', 'symmetry_y_max')
PATCH = 'symmetryPlane'


def domain_mode(spec):
    mode = spec.get('porous_mesh', {}).get('domain_mode', 'full')
    if mode not in MODES:
        raise ValueError('[MESH-S001] Unsupported computational domain mode')
    return mode


def symmetry_domain(spec):
    """Check represented physical inputs, not just the building outline"""
    mode = domain_mode(spec)
    if mode == 'full':
        return None
    if spec.get('porous_mesh', {}).get('kind') != 'aligned_grain_blocks' or not spec.get('coupled'):
        raise ValueError('[MESH-S001] Symmetry requires the aligned coupled warehouse adapter')
    g = spec['geometry_spec']['geometry']
    width = g['width_m']
    blocks = spec['loading']['blocks']
    def coordinates(block):
        return list(block['min_m']) + list(block['max_m'])
    for block in blocks:
        mirrored = coordinates(block)
        mirrored[1], mirrored[4] = width-mirrored[4], width-mirrored[1]
        if not any(all(math.isclose(a,b,rel_tol=0,abs_tol=1e-8)
                       for a,b in zip(mirrored,coordinates(other))) for other in blocks):
            raise ValueError('[MESH-S002] Loading geometry is not symmetric about Y=width/2')
    initial = spec['initial']
    if initial['gaussian_peak_mg_m3'] != 0 and not math.isclose(initial['centre_m'][1], width/2, abs_tol=1e-8, rel_tol=0):
        raise ValueError('[MESH-S003] Initial concentration is not symmetric about Y=width/2')
    lower, upper = (0., width/2) if mode == 'symmetry_y_min' else (width/2, width)
    return {'mode':mode, 'axis':'y', 'plane_m':width/2, 'volume_fraction':.5,
            'bounds_m':[[0.,g['length_m']],[lower,upper],[0.,g['eaves_m']+g['roof_rise_m']]],
            'boundary_patch':PATCH, 'mirrored_results':False,
            'basis':'Symmetric loading, uniform porous coefficients, symmetric initial Gaussian, uniform initial temperature and zero velocity; common exterior heat boundary',
            'limitation':'Excludes cross-plane flow and asymmetric solutions; numerical symmetry is not physical validation'}


def patch_names(spec, original):
    return (*original,PATCH) if symmetry_domain(spec) else original


def clipped_blocks(spec):
    domain = symmetry_domain(spec)
    result = []
    for block in spec['loading']['blocks']:
        item = dict(block, min_m=list(block['min_m']), max_m=list(block['max_m']))
        if domain:
            item['min_m'][1] = max(item['min_m'][1],domain['bounds_m'][1][0])
            item['max_m'][1] = min(item['max_m'][1],domain['bounds_m'][1][1])
        if all(a<b for a,b in zip(item['min_m'],item['max_m'])):
            result.append(item)
    return result


def apply_field_boundaries(folder):
    """Convert the newly generated symmetry patch in every initial field"""
    import re
    for path in folder.iterdir():
        if not path.is_file():
            continue
        text = path.read_text()
        text, count = re.subn(r'\bsymmetryPlane\s*\{[^{}]*\}', 'symmetryPlane { type symmetryPlane; }', text)
        if count != 1:
            raise ValueError('[MESH-S004] Missing symmetry boundary in '+path.name)
        path.write_text(text)
