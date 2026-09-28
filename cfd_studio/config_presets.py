"""공통 수치 입력 검사와 새 프리셋 보관. 솔버 실행이나 물성 추천은 하지 않는다."""
import json
import math
import os
import uuid
from pathlib import Path
import re
import threading

_SAVE_LOCK = threading.Lock()


def finite_number(value, label, *, integer=False):
    if isinstance(value, bool) or value is None or isinstance(value, (dict, list)):
        raise ValueError(label+'은 숫자로 입력해 주세요')
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(label+'은 숫자로 입력해 주세요') from None
    if not math.isfinite(result):
        raise ValueError(label+'은 유한한 숫자로 입력해 주세요')
    if integer and not result.is_integer():
        raise ValueError(label+'은 정수로 입력해 주세요')
    return int(result) if integer else result


def validate_numerics(config):
    """저장 전 기본 정의역을 확인하며 사용자가 지정한 값은 변경하지 않는다."""
    run, mesh = config.get('run'), config.get('mesh')
    if not isinstance(run, dict) or not isinstance(mesh, dict):
        raise ValueError('계산·격자 설정을 확인해 주세요')
    kind = config.get('_해석유형', 'immersion')
    steady = kind == 'grain_silo' and config.get('openfoam_mapping', {}).get('solver') == 'simpleFoam'
    end_key, write_key = ('max_iterations', 'write_interval_iterations') if steady else ('end_time_s', 'write_interval_s')
    end = finite_number(run.get(end_key), '계산 종료값', integer=steady)
    write = finite_number(run.get(write_key), '저장 간격', integer=steady)
    if end <= 0 or not 0 < write <= end:
        raise ValueError('계산 종료값은 양수이고 저장 간격은 0보다 크며 종료값 이하여야 합니다')
    if 'viz_interval_s' in run:
        viz = finite_number(run['viz_interval_s'], '시각화 저장 간격', integer=steady)
        if not 0 < viz <= end:
            raise ValueError('시각화 저장 간격은 0보다 크며 계산 종료값 이하여야 합니다')
    if not steady:
        dt = finite_number(run.get('time_step_s', run.get('max_dt_s')), '계산 시간간격')
        if dt <= 0:
            raise ValueError('계산 시간간격은 0보다 커야 합니다')
    if kind == 'immersion':
        if run.get('time_step_mode', 'adaptive') not in ('adaptive', 'fixed'):
            raise ValueError('시간 간격 방식은 자동 안정 또는 고정이어야 합니다')
        if finite_number(mesh.get('dx_mm'), '격자 간격') <= 0:
            raise ValueError('격자 간격은 0보다 커야 합니다')
        for key, label in (('maxCo', '최대 Courant'), ('maxAlphaCo', '최대 계면 Courant')):
            if key in run and finite_number(run[key], label) <= 0:
                raise ValueError(label+'는 0보다 커야 합니다')
    elif kind == 'grain_silo':
        if finite_number(mesh.get('target_cells'), '목표 격자 수', integer=True) <= 0:
            raise ValueError('목표 격자 수는 양의 정수여야 합니다')


def save_new_preset(folder, name, config):
    """동일 이름을 덮어쓰지 않는다. JSON 직렬화 실패 시 파일도 만들지 않는다."""
    if (not isinstance(name, str) or not name or name != name.strip().rstrip('.')
            or re.search(r'[\\/:*?"<>|\x00-\x1f]', name)
            or re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', name, re.I)):
        raise ValueError('Windows에서 사용할 수 없는 설정 이름입니다')
    data = json.dumps(config, ensure_ascii=False, indent=2, allow_nan=False)
    folder = Path(folder)
    with _SAVE_LOCK:
        folder.mkdir(parents=True, exist_ok=True)
        target = folder/(name+'.json')
        # Linux에서 저장해도 Windows로 옮겼을 때 파일명이 충돌하지 않게 한다.
        if any(p.name.casefold() == target.name.casefold() for p in folder.iterdir()):
            raise FileExistsError('같은 이름의 설정이 있습니다. 새 이름을 입력해 주세요')
        temporary = folder/('.preset-'+uuid.uuid4().hex+'.tmp')
        try:
            with temporary.open('x', encoding='utf-8') as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            # Publish the complete file without overwriting a concurrent creator.
            os.link(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    return target
