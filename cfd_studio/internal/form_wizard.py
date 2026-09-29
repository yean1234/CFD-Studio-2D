"""Solver-aware input scaffolds. No physical values or executable cases are inferred."""
import copy
from cfd_studio.solver_catalog import definition, CATALOG
from cfd_studio.solver_requirements import definition as input_definition

LABELS = {
    'medium': {'liquid':'액체', 'gas':'기체', 'liquid_gas':'액체 + 기체', 'liquid_liquid':'액체 + 액체', 'liquid_liquid_gas':'액체 2종 + 기체'},
    'purpose': {'flow':'유동', 'heat_flow':'열·부력 유동', 'conjugate_heat':'고체·유체 열전달', 'interface':'자유표면·계면', 'compressible_flow':'압축성 유동·에너지', 'thermal_multiphase':'다상 열전달', 'thermal_scalar':'열·유동·스칼라 수송'},
    'regime': {'laminar':'층류', 'RAS':'난류 RAS', 'LES':'난류 LES'},
    'domain': {'internal':'내부 유동', 'external':'외부 유동'},
    'mesh': {'import':'기존 격자', 'generate':'격자 생성'},
    'termination': {'convergence':'수렴 기준', 'physical_time':'물리시간', 'frames':'저장 프레임 수'}
}

def profile(solver):
    item=definition(solver)
    purposes={'buoyantSimpleFoam':'heat_flow','buoyantPimpleFoam':'heat_flow',
              'chtMultiRegionFoam':'conjugate_heat','interFoam':'interface','interIsoFoam':'interface',
              'rhoPimpleFoam':'compressible_flow','icoReactingMultiphaseInterFoam':'thermal_multiphase',
              'warehouseBuoyantFoam':'thermal_scalar'}
    purpose=purposes.get(solver,'flow')
    media=['liquid','gas']
    if purpose in ('interface','thermal_multiphase'):media=['liquid_gas','liquid_liquid']
    if purpose=='thermal_multiphase':media.append('liquid_liquid_gas')
    if solver=='warehouseBuoyantFoam':media=['gas']
    steady=item['time_mode']=='정상'
    options={'medium':media,'purpose':[purpose], 'regime':['laminar'] if solver=='icoFoam' else ['laminar','RAS','LES'],
             'domain':['internal','external'], 'mesh':['import','generate'],
             'termination':['convergence'] if steady else ['physical_time','convergence','frames']}
    # A stationary mean-flow template does not offer time-resolved LES.
    if steady:options['regime']=['laminar','RAS']
    return {'solver':solver,'time_mode':'steady' if steady else 'transient',
            'options':{k:[{'value':v,'label':LABELS[k][v]} for v in values] for k,values in options.items()},
            'note':item['limitation'] or item['summary'], 'requirements': input_definition(solver)}

def profiles():
    return [profile(item['id']) for item in CATALOG]

def quantity(unit):return {'value':None,'unit':unit}
def vector(unit):return {'x':None,'y':None,'z':None,'unit':unit}

def generate(solver,answers):
    p=profile(solver)
    if not isinstance(answers,dict) or set(answers)!=set(p['options']):raise ValueError('모든 양식 질문에 답해 주세요')
    for key,options in p['options'].items():
        if answers[key] not in [o['value'] for o in options]:raise ValueError('선택한 솔버에서 지원하지 않는 항목: '+key)
    a=copy.deepcopy(answers);purpose=a['purpose'];steady=p['time_mode']=='steady'
    thermal=purpose in ('heat_flow','conjugate_heat','compressible_flow','thermal_multiphase','thermal_scalar')
    multi=purpose in ('interface','thermal_multiphase')
    buoyant=purpose in ('heat_flow','conjugate_heat','thermal_scalar')
    kinematic=purpose in ('flow','thermal_scalar')
    field_units={'U':'m/s','p':'m^2/s^2' if kinematic else 'Pa'}
    if thermal:field_units['T']='K'
    if buoyant or multi:field_units['p_rgh']=field_units['p']
    states={'liquid':['liquid'],'gas':['gas'],'liquid_gas':['liquid','gas'],
            'liquid_liquid':['liquid','liquid'],'liquid_liquid_gas':['liquid','liquid','gas']}[a['medium']]
    fluids={}
    for i,state in enumerate(states):
        key='phase_'+str(i+1) if multi else 'fluid'
        fluid={'name':'','state':state,'density':quantity('kg/m^3'),'kinematic_viscosity':quantity('m^2/s')}
        if thermal:fluid.update(heat_capacity=quantity('J/(kg K)'),thermal_conductivity=quantity('W/(m K)'))
        if purpose in ('heat_flow','conjugate_heat','compressible_flow','thermal_multiphase'):
            fluid['thermodynamics']={'equation_of_state':'','transport_model':'','energy_variable':''}
        if purpose=='thermal_scalar':fluid.update(thermal_expansion=quantity('1/K'),reference_temperature=quantity('K'))
        fluids[key]=fluid
        if multi:field_units['alpha.'+key]='1'
    field_value=lambda key,unit:vector(unit) if key=='U' else quantity(unit)
    initial={key:field_value(key,unit) for key,unit in field_units.items()}
    boundaries={}
    for patch in (['inlet','outlet','wall'] if a['domain']=='internal' else ['far_field','body']):
        boundaries[patch]={'mesh_patch':'','fields':{key:{'type':'','value':field_value(key,unit)} for key,unit in field_units.items()}}
    mesh={'source':''} if a['mesh']=='import' else {'generator':'','cell_size':quantity('m'),'refinement_regions':[]}
    algorithm='SIMPLE' if steady else ('PISO' if solver in ('icoFoam','pisoFoam') else 'PIMPLE')
    numerics={'algorithm':algorithm,'schemes':{},'linear_solvers':{},'correctors':None}
    if not steady:numerics.update(time_step=quantity('s'),max_courant=None)
    stop={'mode':a['termination']}
    if a['termination']=='convergence':stop.update(residual_targets={},sustain_steps=None)
    if steady:stop['max_iterations']=None
    else:
        stop['max_time']=quantity('s')
        if a['termination']=='physical_time':stop['end_time']=quantity('s')
        if a['termination']=='frames':stop.update(saved_frames=None,include_initial_frame=False)
    config={'analysis':{'form_generator':'solver-questionnaire-v1','solver':solver,'time_mode':p['time_mode'],'choices':a},
            'geometry':{'source':'','fluid_regions':[]},'mesh':mesh,'materials':{'fluids':fluids},
            'physics':{'flow_regime':a['regime']},'initial_conditions':{'fields':initial},
            'boundary_conditions':boundaries,'numerics':numerics,'termination':stop,
            'outputs':{'fields':list(field_units),'write_interval':quantity('iterations' if steady else 's'),'probes':[]}}
    if a['regime']!='laminar':config['physics']['turbulence']={'model':'','coefficients':{},'initial_fields':{},'boundary_fields':{}}
    if buoyant or multi:config['physics']['gravity']=vector('m/s^2')
    if multi:
        config['physics']['interfaces']={'surface_tension':quantity('N/m'),'pairs':[]}
        config['numerics']['phase_fraction']={'subcycles':None,'max_courant':None}
    if purpose=='thermal_multiphase':config['physics']['phase_transfer']={'model':'','coefficients':{}}
    if purpose=='conjugate_heat':
        config['geometry'].update(solid_regions=[],interfaces=[])
        config['materials']['solid']={'name':'','density':quantity('kg/m^3'),'heat_capacity':quantity('J/(kg K)'), 'thermal_conductivity':quantity('W/(m K)')}
        config['initial_conditions']['solid_temperature']=quantity('K')
        config['boundary_conditions']['thermal_interfaces']=[]
    if purpose=='thermal_scalar':
        config['physics']['scalar_transport']={'field_name':'','unit':'','diffusivity':quantity('m^2/s'),'initial_value':None,'boundary_conditions':{}}
        config['physics']['porous_regions']=[]
    from cfd_studio.solver_requirements import refine,annotate
    config=refine(solver,config)
    schema=annotate(solver,config,make_schema(config))
    return {'config':config,'config_schema':schema,'sections':list(config),
            'summary':{'solver':solver,'choices':{key:LABELS[key][value] for key,value in a.items()},'fields':list(field_units)},
            'definition_only':True}

def make_schema(config):
    integers={'correctors','sustain_steps','max_iterations','saved_frames','subcycles'}
    def fields(obj):
        result=[]
        for key,value in obj.items():
            field={'key':key,'unit':obj.get('unit','') if key in ('value','x','y','z') else ''}
            if isinstance(value,dict):field.update(type='object',fields=fields(value))
            elif value is None:field.update(type='integer' if key in integers else 'number',nullable=True,value=None)
            elif isinstance(value,bool):field.update(type='boolean',value=value)
            elif isinstance(value,list):field.update(type='array',value=copy.deepcopy(value))
            else:field.update(type='string',value=value)
            result.append(field)
        return result
    return {'version':1,'fields':fields(config)}
