"""Explicit Studio input contracts for OpenCFD v2312 baseline solver forms.

These contracts check definition completeness, not executable OpenFOAM dictionaries.
Optional run-time models require their own model-specific coefficients.
"""
import copy

DEFINITIONS = {
 'icoFoam': dict(uses=['층류 채널·관내 유동','공동 유동·수치 검증'], fields=['U','p'], material='nu', algorithm='PISO', required=['transportProperties: nu','0/U·0/p 및 경계조건','fvSchemes·fvSolution/PISO·controlDict'], optional=['밀도: 힘·차원 압력 환산에 사용할 때'], limit='비압축성 뉴턴 유체·층류. 온도·난류·상분율 방정식 없음'),
 'simpleFoam': dict(uses=['정상 관로·덕트 압력손실','정상 외부 유동·공력'], fields=['U','p'], material='nu', algorithm='SIMPLE', required=['transportProperties: 점성 모델·nu','0/U·0/p, turbulenceProperties','fvSolution/SIMPLE·정상 수렴 조건'], optional=['RAS 모델별 k·epsilon 또는 k·omega','MRF·다공성 저항·소스항'], limit='정상 비압축성 유동. 온도 계산은 기본 구성에 포함되지 않음'),
 'pimpleFoam': dict(uses=['비정상 관내·외부 유동','이동 격자·시간에 따른 와류'], fields=['U','p'], material='nu', algorithm='PIMPLE', required=['transportProperties·turbulenceProperties','0/U·0/p','fvSolution/PIMPLE·deltaT·저장 간격'], optional=['RAS·LES 모델별 입력','dynamicMeshDict: 이동 격자 사용 시'], limit='비압축성 비정상 유동. 압력·속도 외부 반복 사용'),
 'pisoFoam': dict(uses=['비정상 내부 유동','시간에 따른 비압축성 유동'], fields=['U','p'], material='nu', algorithm='PISO', required=['transportProperties·turbulenceProperties','0/U·0/p','fvSolution/PISO·deltaT'], optional=['RAS·LES 모델별 입력','MRF·소스항'], limit='PISO 기반 비압축성 비정상 유동. 기본 온도 방정식 없음'),
 'buoyantSimpleFoam': dict(uses=['정상 자연대류·환기','정상 열전달·열손실'], fields=['U','p','p_rgh','T'], material='thermo', algorithm='SIMPLE', required=['thermophysicalProperties: thermoType·mixture','U·p·p_rgh·T 및 열 경계조건','중력 g·SIMPLE·정상 수렴 조건'], optional=['복사 모델·흡수/방사 계수','난류·열원'], limit='밀도 변화와 부력을 포함하는 정상 열유동. 압력 단위 Pa.'),
 'buoyantPimpleFoam': dict(uses=['가열·냉각 과도 응답','부력·환기 유동의 시간 변화'], fields=['U','p','p_rgh','T'], material='thermo', algorithm='PIMPLE', required=['thermophysicalProperties: thermoType·mixture','U·p·p_rgh·T·중력 g','PIMPLE·deltaT·열 경계조건'], optional=['복사·열원','이동 격자·RAS·LES'], limit='부력·열전달 비정상 유동. 열역학·수송 모델을 선택해야 함'),
 'chtMultiRegionFoam': dict(uses=['유체 냉각과 고체 전도','열교환기·전자부품 열관리'], fields=['U','p','p_rgh','T'], material='thermo', algorithm='PIMPLE', required=['regionProperties: fluid·solid 영역','영역별 thermophysicalProperties·fvSchemes·fvSolution','유체 초기장·고체 T·열 접합 경계조건'], optional=['영역별 복사·열원','접촉 열저항·이방성 전도 모델'], limit='유체·고체 영역마다 격자·물성·초기장·수치 설정을 작성해야 함'),
 'interFoam': dict(uses=['자유표면·액면 운동','충전·댐 붕괴·두 비혼합 유체'], fields=['U','p_rgh','alpha.phase_1'], material='two_phase', algorithm='PIMPLE', required=['두 상의 rho·nu·상 이름','U·p_rgh·alpha.phase_1·중력·표면장력','MULES 상분율 이송·PIMPLE·deltaT'], optional=['접촉각·벽 젖음 조건','이동 격자·난류'], limit='등온 비혼합 2상. p와 두 번째 상분율은 유도값이며 기본 온도·비등 계산 없음'),
 'interIsoFoam': dict(uses=['자유표면·계면 형상 추적','날카로운 계면 이송'], fields=['U','p_rgh','alpha.phase_1'], material='two_phase', algorithm='PIMPLE', required=['두 상의 rho·nu·상 이름','U·p_rgh·alpha.phase_1·중력·표면장력','isoAdvector 상분율 이송·PIMPLE·deltaT'], optional=['isoFaceTol·surfCellTol·bounding 설정','접촉각·이동 격자·난류'], limit='등온 2상 isoAdvector 계면 이송. interFoam의 MULES 설정과 구분'),
 'rhoPimpleFoam': dict(uses=['압축성 과도 유동','압력·밀도·온도가 변하는 유동'], fields=['U','p','T'], material='thermo', algorithm='PIMPLE', required=['thermophysicalProperties: 상태방정식·에너지·수송 모델','U·p·T 및 경계조건','PIMPLE·deltaT·압축성 수치 기법'], optional=['난류·열원','이동 격자'], limit='p는 Pa. rho·에너지는 열역학 모델에 연결되며 연소 반응 솔버가 아님'),
 'icoReactingMultiphaseInterFoam': dict(uses=['다상 열전달·상변화','비혼합 유체의 가열·냉각'], fields=['U','p_rgh','T'], material='phase_thermo', algorithm='PIMPLE', required=['phaseProperties·상별 thermophysicalProperties','각 상분율·U·p_rgh·T','중력·계면 모델·PIMPLE·상분율 이송'], optional=['질량·열 전달 모델별 계수','복사·난류·성분별 모델 입력'], limit='N상 열유동. 상변화 활성 시 전달 모델·계수 및 상 연결을 별도로 입력'),
 'warehouseBuoyantFoam': dict(uses=['전용 저장고 열·유동 모델','수동 스칼라 수송 연구'], fields=['U','p_rgh','T'], material='boussinesq', algorithm='PIMPLE', required=['전용 transportProperties·Boussinesq 열물성','U·p_rgh·T·스칼라 정의·확산계수','중력·PIMPLE·전용 격자·경계 연결'], optional=['다공성 영역별 저항','스칼라 경계·소스의 사용자 정의'], limit='저장소 전용 솔버. 범용 OpenFOAM 표준 솔버가 아니며 물성·검증 범위 확인 필요')
}

def definition(solver):
    if solver not in DEFINITIONS:raise ValueError('솔버 입력 정의가 없습니다')
    result=copy.deepcopy(DEFINITIONS[solver]);result['limit']=result['limit'].rstrip('.')
    return result

def refine(solver,c):
    """Refine the generic scaffold into an explicit solver input structure."""
    d=definition(solver)
    if solver in ('interFoam','interIsoFoam','icoReactingMultiphaseInterFoam','warehouseBuoyantFoam'):
        c['initial_conditions']['fields'].pop('p',None)
        for patch in c['boundary_conditions'].values():
            if isinstance(patch,dict):patch.get('fields',{}).pop('p',None)
    if d['material']=='two_phase':
        c['initial_conditions']['fields'].pop('alpha.phase_2',None)
        for patch in c['boundary_conditions'].values():
            if isinstance(patch,dict):patch.get('fields',{}).pop('alpha.phase_2',None)
        c['numerics']['phase_fraction']['method']='isoAdvector' if solver=='interIsoFoam' else 'MULES'
        c['numerics']['phase_fraction']['coefficients']={} # Optional overrides; OpenFOAM defaults may apply.
    for fluid in c['materials']['fluids'].values():
        if d['material'] in ('thermo','phase_thermo'):
            fluid.pop('thermodynamics',None)
            fluid['thermophysical_properties']={'thermoType':{k:'' for k in ('type','mixture','transport','thermo','equationOfState','specie','energy')},'mixture':{}}
    if d['material']=='boussinesq':
        c['materials']['fluids']['fluid'].update(Pr=None,Prt=None)
    c['numerics']['schemes']={k:{} for k in ('ddtSchemes','gradSchemes','divSchemes','laplacianSchemes','interpolationSchemes','snGradSchemes')}
    c['numerics']['linear_solvers']={k:{} for k in ('U','p_rgh' if 'p_rgh' in d['fields'] else 'p')}
    if 'T' in d['fields']:c['numerics']['linear_solvers']['energy']={}
    controls={'nNonOrthogonalCorrectors':None}
    if d['algorithm'] in ('PISO','PIMPLE'):controls['nCorrectors']=None
    if d['algorithm']=='PIMPLE':controls['nOuterCorrectors']=None
    c['numerics'].pop('correctors',None)
    c['numerics']['controls']={d['algorithm']:controls}
    pressure='p_rgh' if 'p_rgh' in c['initial_conditions']['fields'] else 'p'
    c['numerics']['pressure_reference']={'cell':None,'value':{'value':None,'unit':c['initial_conditions']['fields'][pressure]['unit']}}
    if 'time_step' in c['numerics']:
        c['numerics']['adjust_time_step']=None
        c['numerics']['max_time_step']={'value':None,'unit':'s'}
    if d['material']=='nu' and solver!='icoFoam':
        c['materials']['fluids']['fluid']['transport_model']=''
    if solver in ('pimpleFoam','buoyantPimpleFoam','rhoPimpleFoam','interFoam','interIsoFoam'):
        c['mesh']['motion']={'model':'','coefficients':{}}
    if 'T' in d['fields']:
        c['physics']['radiation']={'model':'','coefficients':{}}
    c['physics']['sources']={}
    if 'phase_fraction' in c['numerics']:
        c['numerics']['phase_fraction'].update(nAlphaCorr=None,nAlphaSubCycles=None)
    if d['material']=='phase_thermo':
        c['physics']['phase_transfer']['pairs']=[]
    if solver=='chtMultiRegionFoam':
        c['materials']['solid']['thermophysical_properties']={'thermoType':{},'mixture':{}}
    if solver=='chtMultiRegionFoam':c['numerics']['regions']={}
    if c['physics'].get('turbulence') is not None:
        turbulence=c['physics']['turbulence']
        turbulence['model_options']=['kEpsilon','kOmegaSST'] if c['analysis']['choices']['regime']=='RAS' else ['Smagorinsky','WALE']
        if c['analysis']['choices']['regime']=='RAS':
            turbulence['initial_fields']={key:None for key in ('k','epsilon','omega')}
            turbulence['boundary_fields']={key:{} for key in ('k','epsilon','omega')}
        else:turbulence['delta']=''
    return c

def rules(solver,baseline,actual):
    """Canonical required paths; optional coefficient dictionaries are excluded."""
    d=definition(solver);a=baseline['analysis']['choices'];out=[]
    def add(path,kind='filled',unit=None,note=''):
        if kind=='filled':
            expected=read(baseline,path)
            kind='mapping' if isinstance(expected,dict) else 'sequence' if isinstance(expected,list) else kind
        out.append({'path':path,'kind':kind,'unit':unit,'note':note})
    def q(path,positive=False):
        value=baseline
        for key in path:value=value[key]
        add(path+['value'],'positive' if positive else 'number',value['unit'])
        add(path+['unit'],'unit',value['unit'])
    def vec(path):
        expected=read(baseline,path)
        if isinstance(expected,dict) and 'unit' in expected:add(path+['unit'],'unit',expected['unit'])
        for key in ('x','y','z'):add(path+[key],'number')
    if a['mesh']=='import':add(['mesh','source'],'text')
    else:
        # A generated domain is defined inline; it does not require a file path.
        geometry=actual.get('geometry',{})
        if geometry.get('source'):add(['geometry','source'],'text')  # Preserve imported legacy definitions.
        elif geometry.get('shape'):add(['geometry'],'mapping')
        else:
            region_key='regions' if geometry.get('regions') else 'fluid_regions'
            add(['geometry',region_key],'mapping' if isinstance(geometry.get(region_key),dict) else 'sequence')
        add(['mesh','generator'],'text');q(['mesh','cell_size'],True)
    for name in baseline['materials']['fluids']:
        path=['materials','fluids',name]
        if d['material'] in ('nu','two_phase','boussinesq'):q(path+['kinematic_viscosity'],True)
        if d['material']=='two_phase':q(path+['density'],True);add(path+['name'],'text')
        if d['material']=='phase_thermo':add(path+['name'],'text')
        if d['material']=='nu' and solver!='icoFoam':add(path+['transport_model'],'text')
        if d['material'] in ('thermo','phase_thermo'):
            for key in ('type','mixture','transport','thermo','equationOfState','specie','energy'):add(path+['thermophysical_properties','thermoType',key],'text')
            add(path+['thermophysical_properties','mixture'],'filled',note='상태방정식·열·수송 모델에 필요한 계수')
        if d['material']=='boussinesq':
            q(path+['thermal_expansion']);q(path+['reference_temperature'],True);add(path+['Pr'],'positive');add(path+['Prt'],'positive')
    initial=baseline['initial_conditions']['fields']
    for key,value in initial.items():
        path=['initial_conditions','fields',key]
        if key=='U':vec(path)
        else:q(path)
    for patch,body in baseline['boundary_conditions'].items():
        if not isinstance(body,dict) or 'fields' not in body:continue
        path=['boundary_conditions',patch];add(path+['mesh_patch'],'text')
        for field in body['fields']:
            fp=path+['fields',field];add(fp+['type'],'text')
            entry=read(actual,fp)
            if isinstance(entry,dict) and entry.get('type')=='fixedValue':
                if field=='U':vec(fp+['value'])
                else:q(fp+['value'])
    add(['numerics','algorithm'],'choice',d['algorithm'])
    add(['numerics','controls',d['algorithm']],'object')
    for key in baseline['numerics']['controls'][d['algorithm']]:add(['numerics','controls',d['algorithm'],key],'nonnegative_integer' if key=='nNonOrthogonalCorrectors' else 'integer')
    ref=read(actual,['numerics','pressure_reference'])
    if isinstance(ref,dict) and (ref.get('cell') is not None or isinstance(ref.get('value'),dict) and ref['value'].get('value') is not None):
        add(['numerics','pressure_reference','cell'],'nonnegative_integer');q(['numerics','pressure_reference','value'])
    if 'phase_fraction' in baseline['numerics']:
        for key in ('nAlphaCorr','nAlphaSubCycles'):add(['numerics','phase_fraction',key],'integer')
    if 'adjust_time_step' in baseline['numerics']:
        add(['numerics','adjust_time_step'],'boolean')
        if read(actual,['numerics','adjust_time_step']) is True:
            add(['numerics','max_courant'],'positive');q(['numerics','max_time_step'],True)
    for path in (['mesh','motion'],['physics','radiation']):
        model=read(actual,path)
        if isinstance(model,dict) and model.get('model') not in ('',None,'none'):add(path+['coefficients'],'mapping')
    for section in baseline['numerics']['schemes']:add(['numerics','schemes',section],'filled')
    for field in baseline['numerics']['linear_solvers']:add(['numerics','linear_solvers',field],'filled')
    if 'time_step' in baseline['numerics']:q(['numerics','time_step'],True)
    for key,value in baseline['termination'].items():
        if key=='mode':continue
        if isinstance(value,dict) and 'unit' in value:q(['termination',key],True)
        elif key=='include_initial_frame':add(['termination',key],'boolean')
        elif key=='residual_targets':add(['termination',key],'filled')
        else:add(['termination',key],'integer')
    q(['outputs','write_interval'],True);add(['outputs','fields'],'filled')
    if 'gravity' in baseline['physics']:vec(['physics','gravity'])
    if 'interfaces' in baseline['physics']:q(['physics','interfaces','surface_tension'])
    if solver=='chtMultiRegionFoam':
        for key in ('fluid_regions','solid_regions','interfaces'):add(['geometry',key],'filled')
        add(['numerics','regions'],'filled');add(['boundary_conditions','thermal_interfaces'],'filled')
        for key in ('density','heat_capacity','thermal_conductivity'):q(['materials','solid',key],True)
        q(['initial_conditions','solid_temperature'],True)
    if a['regime']!='laminar':
        path=['physics','turbulence'];add(path+['model'],'text')
        model=read(actual,path+['model']);models={'kEpsilon':['k','epsilon'],'kOmegaSST':['k','omega'],'Smagorinsky':[],'WALE':[]}
        if model in models:
            for field in models[model]:
                add(path+['initial_fields',field],'number');add(path+['boundary_fields',field],'filled')
        if a['regime']=='LES':add(path+['delta'],'text')
    transfer=read(actual,['physics','phase_transfer'])
    if isinstance(transfer,dict) and transfer.get('model') not in ('',None,'none'):
        add(['physics','phase_transfer','coefficients'],'filled');add(['physics','phase_transfer','pairs'],'sequence')
    if solver=='warehouseBuoyantFoam':
        path=['physics','scalar_transport'];add(path+['field_name'],'text');add(path+['unit'],'text');q(path+['diffusivity']);add(path+['initial_value'],'number');add(path+['boundary_conditions'],'filled')
    return out

_MISSING=object()
def read(obj,path):
    for key in path:
        if not isinstance(obj,dict) or key not in obj:return _MISSING
        obj=obj[key]
    return obj

def inspect_config(solver,config):
    from cfd_studio.form_wizard import generate
    import math
    if not isinstance(config,dict):raise ValueError('Config는 JSON object여야 합니다')
    analysis=config.get('analysis',{})
    if not isinstance(analysis,dict) or analysis.get('solver')!=solver:raise ValueError('Template과 Config 솔버가 다릅니다')
    baseline=generate(solver,analysis.get('choices'))['config']
    checks=rules(solver,baseline,config);issues=[]
    for rule in checks:
        value=read(config,rule['path']);kind=rule['kind'];missing=value is _MISSING or value is None or value=='' or value=={} or value==[]
        numeric=type(value) in (int,float) and math.isfinite(value)
        valid=(not missing or (kind=='object' and isinstance(value,dict))) and {'number':numeric,'positive':numeric and value>0,'integer':type(value) is int and value>0,'nonnegative_integer':type(value) is int and value>=0,'boolean':type(value) is bool,'text':isinstance(value,str) and bool(value.strip()),'unit':value==rule['unit'],'object':isinstance(value,dict),'choice':value==rule['unit'],'mapping':isinstance(value,dict) and bool(value),'sequence':isinstance(value,list) and bool(value),'filled':not missing}.get(kind,False)
        if not valid:issues.append({'path':rule['path'],'message':'필수 입력 누락' if missing else ('단위 확인: '+str(rule['unit']) if kind=='unit' else '입력 형식·범위 확인')})
    # Explicitly expose conditional fields beyond the supported turbulence presets.
    physics=config.get('physics',{})
    if not isinstance(physics,dict):physics={}
    turbulence=physics.get('turbulence',{})
    if not isinstance(turbulence,dict):turbulence={}
    unresolved=['선택한 경계조건·열물성 모델의 세부 계수 및 메시 패치 대응은 별도 검토']
    if turbulence.get('model') not in ('',None,'kEpsilon','kOmegaSST','Smagorinsky','WALE'):unresolved.append('사용자 난류 모델의 추가 장·계수 확인 필요')
    transfer=physics.get('phase_transfer',{})
    if not isinstance(transfer,dict):transfer={}
    if transfer.get('model') not in ('',None,'none'):unresolved.append('상변화 전달 모델의 계수·상 연결 검토 필요')
    initial=read(config,['initial_conditions','fields'])
    if not isinstance(initial,dict):initial={}
    for field,value in initial.items():
        v=value.get('value') if isinstance(value,dict) else None
        if field.startswith('alpha.') and type(v) in (int,float) and not 0<=v<=1:issues.append({'path':['initial_conditions','fields',field,'value'],'message':'상분율은 0~1 범위'})
    alphas=[v.get('value') for k,v in initial.items() if k.startswith('alpha.') and isinstance(v,dict)]
    if solver=='icoReactingMultiphaseInterFoam' and alphas and all(type(v) in (int,float) for v in alphas) and not math.isclose(sum(alphas),1,abs_tol=1e-8):
        issues.append({'path':['initial_conditions','fields'],'message':'초기 상분율의 합은 1이어야 합니다'})
    if a_mode:=read(config,['termination','mode']):
        if a_mode=='physical_time':
            end=read(config,['termination','end_time','value']);maximum=read(config,['termination','max_time','value'])
            if type(end) in (int,float) and type(maximum) in (int,float) and end>maximum:issues.append({'path':['termination','max_time','value'],'message':'최대 시간은 종료 시간 이상이어야 합니다'})
    return {'status':'incomplete' if issues else 'specified', 'required_count':len(checks),'missing_count':len(issues), 'issues':issues,'model_review':unresolved,'physical_validation':False,'executable':False}

def annotate(solver,config,schema):
    required={tuple(r['path']) for r in rules(solver,config,config)}
    def visit(fields,path=()):
        for field in fields:
            p=path+(field['key'],);field['required']=p in required
            if field['type']=='object':visit(field['fields'],p)
    visit(schema['fields']);return schema
