"""용량·경로를 검사하고 코드를 실행하지 않은 채 새 폴더에 압축을 푼다."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import zipfile

from .contracts import canonical
from .service import file_hash, uid, verify_snapshot
from .figures import comparison_svg

MAX_BYTES = 256*1024*1024
MAX_FILES = 12000


def safe_name(name):
    if not isinstance(name, str):
        raise ValueError('패키지 경로는 문자열이어야 합니다')
    path = PurePosixPath(name)
    if (not name or '\\' in name or ':' in name or path.is_absolute() or '..' in path.parts
            or any(p in ('', '.') for p in name.split('/')) or '\x00' in name):
        raise ValueError('패키지 경로가 안전하지 않습니다')
    reserved = {'CON', 'PRN', 'AUX', 'NUL'} | {f'{p}{n}' for p in ('COM', 'LPT') for n in range(1, 10)}
    if any(p.endswith((' ', '.')) or p.split('.')[0].upper() in reserved
           or any(ord(c) < 32 or c in '<>"|?*' for c in p) for p in path.parts):
        raise ValueError('Windows에서 안전하지 않은 패키지 경로입니다')
    return path


def export(service, study):
    detail = service.detail(study)
    comparison = service.comparison(study, detail=detail)
    if not comparison['rows']:
        raise ValueError('품질 검사를 통과한 결과가 없습니다')
    revision = next(r for r in detail['revisions'] if r['id'] == detail['current_revision'])
    package_id = uid()
    folder = service.root/'packages'
    folder.mkdir(exist_ok=True)
    path = folder/(package_id+'.zip')
    files = {}
    code = service.root/'revisions'/revision['id']/'code'
    verify_snapshot(code, revision['code_hash'])
    for file in code.rglob('*'):
        if file.is_file() and not file.is_symlink() and '__pycache__' not in file.parts:
            files['code/'+file.relative_to(code).as_posix()] = file
    for row in comparison['rows']:
        attempt = service.root/'attempts'/row['attempt']
        for file in attempt.rglob('*'):
            if file.is_file() and not file.is_symlink():
                files['results/'+row['attempt']+'/'+file.relative_to(attempt).as_posix()] = file
    # 연구계획서 원문과 협력기관 제공 자료는 재현 패키지에 배포하지 않는다.
    generated = {'inputs/study.json': canonical(detail).encode(), 'figures/comparison.json': canonical(comparison).encode(),
                 'figures/comparison.svg': comparison_svg(comparison),
                 'checks/reproduction_tolerances.json': canonical({'absolute_field': 1e-10, 'relative_field': 1e-8,
                     'scope': 'same OpenFOAM build and normalized small benchmark only'}).encode(),
                 'README.txt': ('CFD Studio numerical tracer package, level B. Not validated ClO2.\n'
                     'Import only verifies files and never executes code.\n'
                     'To reproduce explicitly: source OpenFOAM, install compatible numpy,\n'
                     'review code/, build code/tracer_transport/solver with wmake in an isolated FOAM_USER_APPBIN,\n'
                     'then run: python -m study_platform.reproduce IMPORTED_FOLDER NEW_OUTPUT\n'
                     'Run that command from the reviewed code/ directory. Use --figures-only for CSV only.\n'
                     'A requires Python/NPZ and Studio viewer; B also requires OpenFOAM v2312, wmake, C++ compiler.\n'
                     'Full warehouse research reproduction (level C) is not provided.\n').encode()}
    if (len(files)+len(generated)+1 > MAX_FILES
            or sum(p.stat().st_size for p in files.values())+sum(map(len, generated.values())) > MAX_BYTES):
        raise ValueError('대표 예제 패키지 크기 제한을 초과했습니다')
    manifest = {'schema_version': 1, 'level': 'B', 'package_id': package_id,
                'representative': comparison['rows'][0]['attempt'], 'files': {}}
    with zipfile.ZipFile(path, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, source in files.items():
            safe_name(name)
            if source.name.startswith('log.') or source.name == 'execution.log':
                data = source.read_text(encoding='utf-8', errors='replace').replace(str(service.root), '<STUDY_ROOT>').encode()
                manifest['files'][name] = {'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data), 'local_root_redacted': True}
                archive.writestr(name, data)
            else:
                manifest['files'][name] = {'sha256': file_hash(source), 'size': source.stat().st_size}
                archive.write(source, name)
        for name, data in generated.items():
            manifest['files'][name] = {'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)}
            archive.writestr(name, data)
        archive.writestr('manifest.json', canonical(manifest))
    return {'id': package_id, 'filename': path.name, 'bytes': path.stat().st_size, 'level': 'B'}


def inspect(path):
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_FILES or sum(x.file_size for x in entries) > MAX_BYTES:
            raise ValueError('패키지 크기 또는 파일 수 제한 초과')
        names = [x.filename for x in entries]
        folded = {n.casefold() for n in names}
        if len(folded) != len(names) or 'manifest.json' not in names:
            raise ValueError('중복 경로 또는 manifest 누락')
        for entry in entries:
            safe_name(entry.filename)
            if any('/'.join(entry.filename.split('/')[:i]).casefold() in folded
                   for i in range(1, len(entry.filename.split('/')))):
                raise ValueError('파일과 디렉터리 경로가 충돌합니다')
            if entry.is_dir() or stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError('링크 또는 명시적 디렉터리 항목은 허용하지 않습니다')
        if archive.getinfo('manifest.json').file_size > 4*1024*1024:
            raise ValueError('Manifest 크기 제한 초과')
        manifest = json.loads(archive.read('manifest.json'))
        if (not isinstance(manifest, dict) or type(manifest.get('schema_version')) is not int
                or manifest['schema_version'] != 1 or manifest.get('level') not in ('A', 'B')):
            raise ValueError('미지원 패키지 스키마')
        if not isinstance(manifest.get('files'), dict) or set(manifest['files']) != set(names)-{'manifest.json'}:
            raise ValueError('누락되거나 등록되지 않은 파일')
        if 'representative' in manifest:
            representative = safe_name(manifest['representative'])
            if len(representative.parts) != 1 or 'results/'+str(representative)+'/input.json' not in manifest['files']:
                raise ValueError('대표 실행 경로가 올바르지 않습니다')
        for name, item in manifest['files'].items():
            if (not isinstance(item, dict) or type(item.get('size')) is not int or item['size'] < 0
                    or not isinstance(item.get('sha256'), str) or not re.fullmatch(r'[a-f0-9]{64}', item['sha256'])
                    or archive.getinfo(name).file_size != item['size']):
                raise ValueError('파일 메타데이터가 올바르지 않습니다: '+name)
            data = archive.read(name)
            if len(data) != item['size'] or hashlib.sha256(data).hexdigest() != item['sha256']:
                raise ValueError('파일 크기 또는 해시 불일치: '+name)
    return manifest


def import_package(path, destination):
    manifest = inspect(path)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    # 검증된 경로만 새 폴더에 쓴다. 설치기·셸·동봉 스크립트는 실행하지 않는다.
    try:
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                target = destination.joinpath(*safe_name(name).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('xb') as out:
                    out.write(archive.read(name))
    except Exception:
        shutil.rmtree(destination)
        raise
    return manifest
