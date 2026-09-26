"""명시적 요청으로 대표 사례를 재계산한다. 패키지 가져오기는 실행과 분리한다."""
import argparse
import csv
import json
from pathlib import Path
import numpy as np
from .runner import run
from .service import file_hash
from .figures import comparison_svg


def reproduce(source, output, figures_only=False):
    source, output = Path(source), Path(output)
    manifest = json.loads((source/'manifest.json').read_text(encoding='utf-8'))
    for name, entry in manifest['files'].items():
        from .packages import safe_name
        safe_name(name)
        file = source/name
        if file.is_symlink() or file_hash(file) != entry['sha256']:
            raise ValueError('Imported package changed')
    output.mkdir(parents=True, exist_ok=False)
    comparison = json.loads((source/'figures/comparison.json').read_text(encoding='utf-8'))
    (output/'comparison.svg').write_bytes(comparison_svg(comparison))
    with (output/'comparison.csv').open('w', newline='') as stream:
        writer = csv.writer(stream); writer.writerow(['attempt_id', 'physical_time_s', 'mean_C_over_Cref'])
        for row in comparison['rows']:
            writer.writerows(zip([row['attempt']]*len(row['metrics']['times']), row['metrics']['times'], row['metrics']['mean_C']))
    if figures_only:
        return {'figures_only': True, 'cfd_recalculated': False}
    reference = source/'results'/manifest['representative']
    (output/'input.json').write_bytes((reference/'input.json').read_bytes())
    tolerances = json.loads((source/'checks/reproduction_tolerances.json').read_text(encoding='utf-8'))
    result = run(output)
    with np.load(reference/'raw/concentration.npz') as old, np.load(output/'raw/concentration.npz') as new:
        times_equal = np.array_equal(old['times'], new['times'])
        max_error = float(np.max(np.abs(old['concentration']-new['concentration'])))
        passed = times_equal and bool(np.allclose(old['concentration'], new['concentration'],
                       atol=tolerances['absolute_field'], rtol=tolerances['relative_field']))
    report = {'cfd_recalculated': True, 'numerical_checks_pass': result['pass'],
              'field_comparison_pass': passed, 'max_absolute_field_difference': max_error,
              'tolerances': tolerances}
    (output/'reproduction.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path); parser.add_argument('output', type=Path)
    parser.add_argument('--figures-only', action='store_true')
    args = parser.parse_args()
    print(json.dumps(reproduce(args.source, args.output, args.figures_only), indent=2))
