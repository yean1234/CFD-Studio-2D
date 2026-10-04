"""Check development references and the tracked-file inventory without running Studio"""
import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs/development'
REQUIRED = ('README.md', 'README.en.md', 'README.ja.md', 'ONBOARDING.md',
            'ARCHITECTURE.md', 'DATA-CONTRACTS.md', 'RUNTIME-API.md',
            'REQUIREMENTS.md', 'VERIFICATION.md', 'OPERATIONS.md',
            'MAINTENANCE.md', 'BACKLOG.md', 'MESH-ROADMAP.md',
            'GLOSSARY.md', 'REFERENCES.md', 'UI-CONTRACT.md', 'INVENTORY.md', 'decisions/README.md',
            'templates/RFC.md', 'templates/HANDOFF.md', 'templates/TEST-REPORT.md',
            'DOCUMENTATION-REVIEW.md')


def tracked_files():
    raw = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT)
    return sorted(set(raw.decode('utf-8').split('\0')) - {''})


def inventory(files):
    excluded = ('cfd_studio/Setup/', 'cfd_studio/vendor/', 'study_platform/vendor/')
    own = [p for p in files if not p.startswith(excluded) and '/vendor/' not in p]
    groups = {
        '기술·사용자 문서': [p for p in own if p.endswith('.md')],
        '자체 소스·정의·실행 파일': [p for p in own if p.startswith(
            ('cfd_studio/', 'tracer_transport/', 'silo_reproduction/',
             'tmc49_full_tank/', 'study_platform/', 'tools/'))
            and (Path(p).suffix in ('.py', '.js', '.html', '.css', '.json', '.C', '.H', '.sh', '.bat')
                 or Path(p).name in ('Allrun', 'Allclean', 'files', 'options'))],
        '검사 코드': [p for p in own if p.startswith('tests/')
                     and Path(p).suffix in ('.py', '.js')],
    }
    lines = ['# 저장소 목록', '', '- `python tools/check_development_docs.py --write-inventory`로 갱신',
             '- Git 추적/스테이징 파일 기준 · 설치 런타임·외부 vendor·사용자 미추적 자료 제외',
             '- 목록 포함은 코드 검증 완료를 의미하지 않음 · 날짜 문서는 해당 시점의 기록',
             '- 새 문서를 추가하면 먼저 해당 파일을 스테이징한 뒤 목록 갱신', '']
    for title, paths in groups.items():
        lines += [f'## {title}', '', f'- {len(paths)}개', '']
        for path in paths:
            # Encode spaces for Markdown destinations without changing disk paths
            link = '../../' + path.replace(' ', '%20')
            lines.append(f'- [{path}]({link})')
        lines.append('')
    return '\n'.join(lines)


def check():
    from urllib.parse import unquote
    errors = []
    for name in REQUIRED:
        if not (DOCS / name).is_file():
            errors.append('missing document: ' + name)
    data = json.loads((DOCS / 'capabilities.json').read_text(encoding='utf-8'))
    ids = set()
    states = {'implemented', 'partial', 'not_implemented', 'unverified', 'excluded'}
    requirements = (DOCS / 'REQUIREMENTS.md').read_text(encoding='utf-8')
    for item in data['items']:
        ident = item['id']
        if ident in ids or not re.fullmatch(r'REQ-\d{3}', ident):
            errors.append('invalid/duplicate requirement: ' + ident)
        ids.add(ident)
        if item['status'] not in states or not item.get('acceptance'):
            errors.append('invalid state/acceptance: ' + ident)
        if ident not in requirements:
            errors.append('requirement absent from table: ' + ident)
        for path in item['sources'] + item['tests'] + [item['document']]:
            resolved = (ROOT / path).resolve()
            if not resolved.is_relative_to(ROOT) or not resolved.is_file():
                errors.append(f'{ident}: invalid reference {path}')
    table_ids = set(re.findall(r'^\| (REQ-\d{3}) \|', requirements, re.M))
    if table_ids != ids:
        errors.append('requirement table/catalog IDs differ')
    paths = list(DOCS.rglob('*.md'))
    for path in paths:
        body = re.sub(r'```.*?```', '', path.read_text(encoding='utf-8'), flags=re.S)
        for target in re.findall(r'\]\(([^)]+)\)', body):
            if re.match(r'[A-Za-z][A-Za-z0-9+.-]*:', target):
                continue
            target = unquote(target.split('#')[0])
            if target and not (path.parent / target).exists():
                errors.append(f'{path.relative_to(ROOT)}: broken link {target}')
    expected = inventory(tracked_files())
    actual = (DOCS / 'INVENTORY.md').read_text(encoding='utf-8') if (DOCS / 'INVENTORY.md').exists() else ''
    if actual != expected:
        errors.append('inventory is stale; stage intended new files, then use --write-inventory')
    return errors, len(paths), len(ids)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-inventory', action='store_true')
    args = parser.parse_args()
    if args.write_inventory:
        (DOCS / 'INVENTORY.md').write_text(inventory(tracked_files()), encoding='utf-8')
    errors, documents, requirements = check()
    print(f'Development documents: {documents}; requirements: {requirements}; errors: {len(errors)}')
    for error in errors:
        print(error)
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
