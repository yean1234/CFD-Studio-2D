"""실제 솔버를 사용하는 소규모 인수 시험. 운영 프로젝트와 독립적으로 실행한다."""
import argparse
import json
from pathlib import Path
from .contracts import candidates
from .service import Service
from . import packages
from .reproduce import reproduce


def smoke(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    store = Service(root/'study')
    study = store.create('Three-case tracer acceptance')
    design = {'variable': 'K_porous_m2_s', 'method': 'manual', 'values': [.001, .002, .004], 'seed': 42}
    rev = store.commit(study, design, candidates(design)['preview_hash'], None)
    ids = store.enqueue(rev['cases'], 'acceptance-request')
    assert store.enqueue(rev['cases'], 'acceptance-request') == ids
    store.drain()
    detail = store.detail(study)
    assert len(detail['attempts']) == 3
    assert all(a['quality'] == 'pass' for a in detail['attempts']), detail
    exported = packages.export(store, study)
    packages.import_package(store.root/'packages'/exported['filename'], root/'imported')
    reproduced = reproduce(root/'imported', root/'reproduced')
    assert reproduced['numerical_checks_pass'] and reproduced['field_comparison_pass']
    report = {'study': study, 'attempts': detail['attempts'], 'package': exported, 'reproduction': reproduced}
    (root/'acceptance.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('output', type=Path)
    args = parser.parse_args()
    print(json.dumps(smoke(args.output), ensure_ascii=False, indent=2))
