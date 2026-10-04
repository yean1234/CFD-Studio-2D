"""Static size transitions between conformal axis intervals, without cell allocation"""
import math


def transition_ratio(mesh):
    value = mesh.get('max_axis_spacing_ratio')
    enabled = mesh.get('mesh_transition_enabled', value is not None)
    if type(enabled) is not bool:
        raise ValueError('[MESH-R010] mesh_transition_enabled must be a boolean')
    # An explicit off state retains the saved ratio without applying it
    if not enabled:
        return None
    if type(value) not in (float, int) or not math.isfinite(value) or value <= 1:
        raise ValueError('[MESH-R010] max_axis_spacing_ratio must be finite and greater than 1')
    return value


def interval_ratio(lengths, counts):
    sizes = [length/count for length, count in zip(lengths, counts)]
    return max((max(a/b, b/a) for a, b in zip(sizes, sizes[1:])), default=1.)


def smooth_counts(lengths, counts, ratio):
    """Refine the coarser neighbor only; preserve interval endpoints and symmetry"""
    values = list(map(int, counts))
    if ratio is None:
        return values
    for _ in range(512):
        sizes = [length/count for length, count in zip(lengths, values)]
        updated = list(values)
        # Simultaneous updates avoid directional bias in a symmetric domain
        for i, length in enumerate(lengths):
            neighbors = sizes[max(0, i-1):i] + sizes[i+1:i+2]
            if neighbors:
                allowed = min(neighbors)*ratio
                if sizes[i] > allowed*(1+1e-12):
                    updated[i] = max(values[i], math.ceil(length/allowed))
        if updated == values:
            return values
        values = updated
    raise ValueError('[MESH-R011] Axis transition did not settle within 512 passes; relax the ratio')


def apply_transition(mesh, lengths, counts):
    ratio = transition_ratio(mesh)
    return tuple(smooth_counts(axis, values, ratio) for axis, values in zip(lengths, counts))


def transition_report(mesh, lengths, counts):
    ratio = transition_ratio(mesh)
    measured = [interval_ratio(axis, values) for axis, values in zip(lengths, counts)]
    return {
        'enabled': ratio is not None,
        'requested_maximum': ratio,
        'axis_reference_ratios': measured,
        'requirement_met': None if ratio is None else max(measured) <= ratio*(1+1e-12),
        'method': 'static_uniform_block_count_transition',
        'basis': 'Adjacent reference-axis cell spacings; roof Z uses maximum layer height',
        'limitations': 'Not boundary-layer inflation, per-cell 3D growth control, yPlus control or adaptive mesh refinement',
        'research_reference': 'https://doi.org/10.1038/s41598-024-76385-y',
        'relationship': 'Inspired by smooth size transitions; independent implementation, not the paper mesh generator',
    }
