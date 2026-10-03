"""Validate explicit silo surrogate choices before any solver files are changed."""
import math

MODEL = 'equivalent_boundary_ports_v1'
CHOICES = {
    'domain_model': 'cylinder_full_height',
    'central_inlet_model': 'equal_area_square',
    'flow_distribution': 'nominal_area_proportional',
}


def fail(code, detail):
    raise ValueError(f'[{code}] {detail}')


def original_design(silo):
    """Keep the published original separate from optimization-only bottom ports."""
    design = silo.get('design', {})
    if not isinstance(design, dict):
        fail('CFG-G003', 'silo.design must be an object')
    expected = {'A': 10, 'B': 7, 'C': 0, 'D': 0}
    for key, value in expected.items():
        supplied = design.get(key, value)
        if isinstance(supplied, bool) or not isinstance(supplied, (int, float)) or supplied != value:
            fail('CFG-G003', f'original requires {key}={value}; C/D=0 means no optimization-only bottom ports')
    return expected


def validate_runtime(config):
    """Require reviewed surrogate assumptions; this does not certify paper fidelity."""
    silo = config.get('silo') or {}
    if not isinstance(silo, dict):
        fail('CFG-G004', 'silo must be an object')
    if config.get('mesh', {}).get('require_external_mesh') is not False:
        fail('CFG-G004', 'The connected surrogate generates an O-grid; external mesh import is not connected')
    if silo.get('geometry_model') != MODEL:
        fail('CFG-G004', 'Select an explicit geometry model; the full paper duct geometry is not connected')
    kind = silo.get('kind')
    if kind not in ('original', 'custom', 'optimized'):
        fail('CFG-G003', 'silo.kind must be original, custom or optimized')
    design = original_design(silo) if kind == 'original' else silo.get('design')
    if not isinstance(design, dict):
        fail('CFG-G003', 'silo.design must be an object')
    for key in ('A', 'B', 'C', 'D'):
        value = design.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            fail('CFG-G003', f'silo.design.{key} must be finite and nonnegative')
    if design['A'] <= 0 or not 1 <= design['B'] <= 64 or int(design['B']) != design['B'] or int(design['D']) != design['D']:
        fail('CFG-G003', 'A must be positive; B must be an integer in 1..64; D must be an integer')
    a = silo.get('geometry_assumptions')
    if not isinstance(a, dict) or a.get('reviewed') is not True:
        fail('CFG-G005', 'Review silo.geometry_assumptions before starting a new calculation')
    for key, value in CHOICES.items():
        if a.get(key) != value:
            fail('CFG-G005', f'Explicit assumption required: {key}={value}')
    if not isinstance(a.get('source'), str) or not a['source'].strip():
        fail('CFG-G005', 'Record the rationale in geometry_assumptions.source')
    for key in ('ports_per_layer', 'layer_z_min_m', 'layer_z_max_m'):
        value = a.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            fail('CFG-G005', f'Explicit finite value required: {key}')
    if int(a['ports_per_layer']) != a['ports_per_layer'] or not 1 <= a['ports_per_layer'] <= 64:
        fail('CFG-G005', 'ports_per_layer must be an integer in 1..64')
    grain = config.get('published', {}).get('grain_height_m')
    if isinstance(grain, bool) or not isinstance(grain, (int, float)) or not math.isfinite(grain) or not 0 < a['layer_z_min_m'] <= a['layer_z_max_m'] < grain:
        fail('CFG-G005', 'Layer heights must lie inside the grain zone')
    if design['B'] > 1 and a['layer_z_min_m'] == a['layer_z_max_m']:
        fail('CFG-G005', 'Multiple layers must have distinct heights')
    if not isinstance(a.get('bottom_outlets_enabled'), bool):
        fail('CFG-G005', 'Specify bottom_outlets_enabled explicitly')
    if kind == 'original' and a['bottom_outlets_enabled']:
        fail('CFG-G003', 'Original geometry has no optimization-only bottom ports')
    if a['bottom_outlets_enabled']:
        radius = a.get('bottom_ring_radius_m')
        if isinstance(radius, bool) or not isinstance(radius, (int, float)) or not math.isfinite(radius) or not 0 < radius < config['published']['storage_diameter_m'] / 2:
            fail('CFG-G005', 'Specify a bottom ring radius inside the storage radius')
        if design['C'] <= 0 or not 1 <= design['D'] <= 64:
            fail('CFG-G003', 'Enabled bottom ports require C>0 and D in 1..64')
    return a
