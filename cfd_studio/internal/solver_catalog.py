"""Solver capabilities are independent of executables and Studio adapters.

Descriptions checked against OpenCFD v2312 application sources. Executable
discovery never launches a solver and does not certify runtime compatibility.
"""
import copy
import os
import shlex
import shutil
import subprocess
import time


def entry(name, category, mode, summary, outputs, inputs, models=(), limitation='', dedicated=False, coupling=None):
    return dict(id=name, category=category, time_mode=mode, summary=summary,
                outputs=outputs, inputs=inputs, models=list(models), limitation=limitation,
                dedicated=dedicated, coupling=coupling, integration='connected' if models else 'definition_only')


CATALOG = (
    entry('icoFoam','단상 유동','비정상','비압축성 뉴턴 유체의 층류',
          ['유속','운동학적 압력 p/ρ'],['유체 격자','동점성계수','초기 U·p','속도·압력 경계조건'],limitation='열전달·다상·난류 모델 없음'),
    entry('simpleFoam','단상 유동','정상','비압축성 정상 유동과 난류',
          ['유속','운동학적 압력 p/ρ','선택한 난류장'],['유체 격자','점성·난류 모델','초기 U·p','경계조건'],('grain_silo',),'Studio 연결 범위: 기존 사일로 형상·Config',coupling='SIMPLE'),
    entry('pimpleFoam','단상 유동','비정상','비압축성 비정상 유동, PIMPLE 알고리즘',
          ['유속','운동학적 압력 p/ρ','선택한 난류장'],['유체 격자','점성·난류 모델','초기 U·p','경계조건'],('grain_silo',),'Studio 연결 범위: 기존 사일로 형상·Config',coupling='PIMPLE'),
    entry('pisoFoam','단상 유동','비정상','비압축성 비정상 유동, PISO 알고리즘',
          ['유속','운동학적 압력 p/ρ','선택한 난류장'],['유체 격자','점성·난류 모델','초기 U·p','경계조건'],limitation='기본 솔버에 온도 계산 없음'),
    entry('buoyantSimpleFoam','열·부력','정상','압축성 유체의 정상 부력·열전달, 복사 모델 지원',
          ['유속','압력','온도','밀도'],['유체 격자','열물성','중력','열·유동 경계조건']),
    entry('buoyantPimpleFoam','열·부력','비정상','압축성 유체의 비정상 부력·열전달',
          ['유속','압력','온도','밀도'],['유체 격자','열물성','중력','열·유동 경계조건']),
    entry('chtMultiRegionFoam','복합 열전달','비정상','유체 유동과 고체 열전도를 영역 사이에서 연계',
          ['영역별 온도','유체 유속','유체 압력'],['유체·고체 영역 격자','영역별 열물성','접합면','열·유동 경계조건']),
    entry('interFoam','다상 유동','비정상','섞이지 않는 두 비압축성 유체의 등온 자유표면, VOF',
          ['유속','압력','상분율'],['두 상의 물성','초기 상분율','표면장력','중력·경계조건'],limitation='기본 솔버에 열전달·비등 계산 없음'),
    entry('interIsoFoam','다상 유동','비정상','두 비압축성 유체의 등온 자유표면, isoAdvector 계면 이송',
          ['유속','압력','상분율'],['두 상의 물성','초기 상분율','표면장력','중력·경계조건'],limitation='기본 솔버에 열전달·비등 계산 없음'),
    entry('rhoPimpleFoam','압축성 유동','비정상','압축성 유체의 비정상 유동과 에너지 계산',
          ['유속','압력','온도','밀도'],['유체 격자','상태방정식·열물성','초기장','경계조건']),
    entry('icoReactingMultiphaseInterFoam','이중액침냉각','비정상','Studio의 다상·상변화·열전달 액침냉각 구성',
          ['유속','온도','상분율','기포 지표'],['수조·보드·코일','각 상 물성','발열·상변화','격자·시간'],('immersion',),'기존 액침냉각 Config와 결과 변환에 연결',True),
    entry('warehouseBuoyantFoam','식량 저장고','비정상','Studio의 부력 유동·온도·스칼라 수송과 다공성 적재 구성',
          ['유속','온도','농도'],['저장고 형상·적재','열·수송 물성','초기장','경계조건·시간'],('warehouse',),'전용 빌드 필요. 기존 모델의 미보정 가정·검증 제한 유지',True),
)


def definition(solver):
    item=next((x for x in CATALOG if x['id']==solver),None)
    if item is None:
        raise ValueError('등록된 솔버를 선택하세요')
    return copy.deepcopy(item)


def config_solver(config):
    for section in ('openfoam_mapping', 'analysis'):
        solver = config.get(section, {}).get('solver')
        if isinstance(solver, str) and solver:
            return solver
    return config.get('solver') if isinstance(config.get('solver'), str) else None


def result_axis(config):
    """Display basis only; never enables an adapter or changes solver inputs."""
    solver = config_solver(config)
    known = next((x for x in CATALOG if x['id'] == solver), None)
    if known:
        return 'iteration' if known['time_mode'] == '정상' else 'time'
    basis = config.get('run', {}).get('time_basis')
    if basis is None:
        basis = config.get('analysis', {}).get('time_mode')
    return 'iteration' if basis in ('iterations', 'steady') else 'time'


def draft_config(solver):
    definition(solver)
    return {'_해석유형':'solver_definition','solver':solver,
            'requirements':{'geometry':'','materials':'','boundaries':'','initial_fields':''}}


def validate_draft(config, solver):
    expected=draft_config(solver)
    if not isinstance(config,dict) or set(config)!=set(expected) or config.get('_해석유형')!='solver_definition' or config.get('solver')!=solver:
        raise ValueError('솔버 FORM 초안 형식이 일치하지 않습니다')
    notes=config.get('requirements')
    if not isinstance(notes,dict) or set(notes)!=set(expected['requirements']) or any(not isinstance(x,str) or len(x)>4000 for x in notes.values()):
        raise ValueError('입력 계획은 항목별 4,000자 이내로 입력하세요')


def probe(settings):
    """One explicit, bounded executable check in the configured CPU environment."""
    source=settings.get('openfoam_bashrc')
    if source and source!='auto':
        setup='source '+shlex.quote(str(source))+' >/dev/null 2>&1 || exit 3'
    else:
        setup='CFD_CATALOG_RC=""; for f in /usr/lib/openfoam/openfoam*/etc/bashrc /opt/openfoam*/etc/bashrc; do [ ! -f "$f" ] || CFD_CATALOG_RC="$f"; done; [ -n "$CFD_CATALOG_RC" ] || exit 3; source "$CFD_CATALOG_RC" >/dev/null 2>&1 || exit 3'
    script=setup+'\nprintf "VERSION\\t%s\\n" "$WM_PROJECT_VERSION"\n'
    for item in CATALOG:
        name=item['id']
        script+=f'if type -P {name} >/dev/null; then printf "{name}\\tfound\\n"; else printf "{name}\\tmissing\\n"; fi\n'
    argv=['bash','-s']
    if os.name=='nt':
        exe=shutil.which('wsl.exe') or os.path.join(os.environ.get('SystemRoot',r'C:\Windows'),'System32','wsl.exe')
        argv=[exe]+(['-d',str(settings['wsl_distro'])] if settings.get('wsl_distro') else [])+['bash','-ls']
    try:
        # Binary stdin preserves LF when Windows passes this script into WSL bash.
        result=subprocess.run(argv,input=script.encode('utf-8'),capture_output=True,timeout=15,creationflags=0x08000000 if os.name=='nt' else 0)
        if result.returncode:
            raise OSError('OpenFOAM 환경 확인 실패')
        stdout=result.stdout.decode('utf-8',errors='replace')
        lines=dict(line.split('\t',1) for line in stdout.splitlines() if '\t' in line)
        if any(lines.get(x['id']) not in ('found','missing') for x in CATALOG):
            raise OSError('설치 확인 응답 누락')
        return {'checked_at':time.time(),'version':lines.get('VERSION',''),'status':'checked',
                'solvers':{x['id']:lines[x['id']] for x in CATALOG},
                'note':'설정된 CPU OpenFOAM 환경의 실행 파일 존재 여부. 실행·라이브러리 호환성·GPU 지원 검증은 별도.'}
    except (OSError,subprocess.TimeoutExpired):
        return {'checked_at':time.time(),'version':'','status':'unavailable','solvers':{},
                'note':'OpenFOAM 환경을 확인하지 못했습니다. 미설치로 확정하지 않습니다.'}


def catalog(installation=None):
    from cfd_studio.solver_requirements import definition as requirements
    installation=installation or {}
    return [{**copy.deepcopy(x),'installation':installation.get('solvers',{}).get(x['id'],'unchecked'),
             'draft_config':draft_config(x['id']),'requirements':requirements(x['id'])} for x in CATALOG]
