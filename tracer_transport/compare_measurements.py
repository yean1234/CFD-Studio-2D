"""Compare an unvalidated ClO2 case with independent sensor observations.

Comparison does not itself certify the physical model. Sensor provenance,
alignment limits and calibration/validation split remain explicit inputs.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import numpy as np


REQUIRED = {'sensor_id', 'x_m', 'y_m', 'z_m', 'time_s',
            'concentration_mg_m3', 'uncertainty_mg_m3', 'split'}


def compare(case, observations_csv, output, source, max_cell_distance_m):
    case, observations_csv, output = map(Path, (case, observations_csv, output))
    if output.exists():
        raise FileExistsError(f'Refusing to replace {output}')
    if not isinstance(source, str) or not source.strip():
        raise ValueError('Observation provenance is required')
    if (isinstance(max_cell_distance_m, bool) or not isinstance(max_cell_distance_m, (int, float))
            or not math.isfinite(max_cell_distance_m) or max_cell_distance_m <= 0):
        raise ValueError('A positive, finite maximum centre distance is required')
    model = json.loads((case/'model_contract.json').read_text())
    geometry = json.loads((case/'transport_input.json').read_text())['geometry_spec']['geometry']
    if model['kind'] != 'clo2_gas_in_air':
        raise ValueError('Measured ClO2 values cannot be compared to normalized tracer values')
    with np.load(case/'concentration.npz', allow_pickle=False) as archive:
        times = archive['times_s']
        fields = archive['concentration']
        centres = archive['cell_centres_m']
        unit = str(archive['concentration_unit'])
    if unit != 'kg/m3' or fields.shape != (len(times), len(centres)) or not np.isfinite(fields).all():
        raise ValueError('Incompatible or invalid calculated concentration field')
    with observations_csv.open(newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream)
        if set(reader.fieldnames or []) != REQUIRED:
            raise ValueError('Observation CSV columns do not match the contract')
        rows = list(reader)
    if not rows:
        raise ValueError('Observation CSV is empty')
    compared = []
    for row in rows:
        if not row['sensor_id'].strip() or row['split'] not in ('calibration', 'validation'):
            raise ValueError('Sensor ID and calibration/validation split are required')
        values = [float(row[key]) for key in ('x_m', 'y_m', 'z_m', 'time_s',
                                             'concentration_mg_m3', 'uncertainty_mg_m3')]
        if not np.isfinite(values).all() or values[4] < 0 or values[5] <= 0:
            raise ValueError('Invalid observation or uncertainty')
        xyz, time = np.array(values[:3]), values[3]
        length, width = geometry['length_m'], geometry['width_m']
        roof_height = geometry['eaves_m'] + geometry['roof_rise_m']*(1-abs(2*xyz[1]/width-1))
        if not (0 <= xyz[0] <= length and 0 <= xyz[1] <= width and 0 <= xyz[2] <= roof_height):
            raise ValueError('Sensor is outside the gabled storage domain')
        if time < times[0] or time > times[-1]:
            raise ValueError('Observation time is outside saved frames')
        distances = np.linalg.norm(centres - xyz, axis=1)
        cell = int(np.argmin(distances))
        if distances[cell] > max_cell_distance_m:
            raise ValueError('Sensor is too far from a calculated cell centre')
        predicted = float(np.interp(time, times, fields[:, cell])*1e6)
        compared.append({'sensor_id': row['sensor_id'], 'split': row['split'],
                         'time_s': time, 'x_m': xyz[0], 'y_m': xyz[1], 'z_m': xyz[2],
                         'cell_index': cell, 'cell_centre_distance_m': float(distances[cell]),
                         'measured_mg_m3': values[4], 'uncertainty_mg_m3': values[5],
                         'calculated_mg_m3': predicted, 'residual_mg_m3': predicted-values[4]})
    if not any(row['split'] == 'validation' for row in compared):
        raise ValueError('Independent validation rows are required')
    metrics = {}
    for split in ('calibration', 'validation'):
        subset = [row for row in compared if row['split'] == split]
        if not subset:
            continue
        residuals = np.array([row['residual_mg_m3'] for row in subset])
        uncertainty = np.array([row['uncertainty_mg_m3'] for row in subset])
        metrics[split] = {'count': len(subset), 'mae_mg_m3': float(np.mean(abs(residuals))),
                          'rmse_mg_m3': float(np.sqrt(np.mean(residuals**2))),
                          'bias_mg_m3': float(np.mean(residuals)),
                          'within_reported_uncertainty_fraction': float(np.mean(abs(residuals) <= uncertainty))}
    report = {'comparison_status': 'computed_not_certified', 'model_validation': model['model_validation'],
              'observation_source': source, 'observation_sha256': hashlib.sha256(observations_csv.read_bytes()).hexdigest(),
              'max_cell_distance_m': max_cell_distance_m, 'sampling': 'nearest_cell_linear_time',
              'metrics': metrics, 'rows': len(compared)}
    output.mkdir(parents=True)
    with (output/'comparison_rows.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(compared[0]))
        writer.writeheader()
        writer.writerows(compared)
    (output/'comparison.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', type=Path, required=True)
    parser.add_argument('--observations', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--max-cell-distance-m', type=float, required=True)
    args = parser.parse_args()
    print(json.dumps(compare(args.case, args.observations, args.output,
                             args.source, args.max_cell_distance_m), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
