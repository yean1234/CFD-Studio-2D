/* Config schema editor. Field keys and units are user-owned, never translated. */
(() => {
  const types=['string','number','integer','boolean','object','array','null'];
  const forbidden=new Set(['__proto__','prototype','constructor']);
  const clone=x=>structuredClone(x);
  const spatialAPI=()=>globalThis.CFDSpatial||(typeof require==='function'?require('./spatial_editor.js'):null);
  const spatialPath=path=>!!spatialAPI()?.isGeometryPath(path);
  const kind=value=>value===null?'null':Array.isArray(value)?'array':typeof value==='object'?'object':typeof value==='number'?(Number.isInteger(value)?'integer':'number'):typeof value;
  function fromConfig(config,previous=null){
    if(!config||typeof config!=='object'||Array.isArray(config))throw Error('Config must be a JSON object');
    function fields(object,prior=[],depth=0){
      if(depth>16)throw Error('Config nesting exceeds 16 levels');
      return Object.entries(object).map(([key,value])=>{const old=prior.find(f=>f.key===key),actual=kind(value),type=old?.nullable&&actual==='null'?old.type:(actual==='null'&&((key==='value'&&typeof object.unit==='string')||Object.hasOwn(parameterUnits,key)))?'number':actual==='integer'?(old?.type==='integer'?'integer':'number'):actual;return {key,type,...(actual==='null'&&type!=='null'?{nullable:true}:{}),unit:['value','x','y','z'].includes(key)&&typeof object.unit==='string'?object.unit:(old?.unit||''),...(old?.nullable?{nullable:true}:{}),...(old?.readonly?{readonly:true}:{}),...(Array.isArray(old?.enum)?{enum:clone(old.enum)}:{}),...Object.fromEntries(['label','description'].filter(k=>typeof old?.[k]==='string').map(k=>[k,old[k]])),...(typeof old?.required==='boolean'?{required:old.required}:{}),...(type==='object'?{fields:fields(value,old?.fields,depth+1)}:{value:clone(value)})};});
    }
    const schema={version:1,spatial_version:1,fields:fields(config,previous?.fields)};toConfig(schema);return schema;
  }
  function toConfig(schema){
    if(schema?.version!==1)throw Error('Config schema version must be 1');let count=0;
    function checkJSON(v,depth){if(v===undefined||typeof v==='function'||typeof v==='symbol')throw Error('Config requires JSON values');if(depth>16)throw Error('Config nesting exceeds 16 levels');if(typeof v==='number'&&!Number.isFinite(v))throw Error('Config numbers must be finite');if(Array.isArray(v)){if(v.length>10000)throw Error('Config array is too large');for(const x of v)checkJSON(x,depth+1);}else if(v&&typeof v==='object')for(const [k,x] of Object.entries(v)){if(forbidden.has(k))throw Error('Reserved Config Key: '+k);checkJSON(x,depth+1);}}
    function group(fields,depth){
      if(depth>16||!Array.isArray(fields))throw Error('Invalid Config group');const result={};
      for(const f of fields){
        if(++count>512||!f||typeof f!=='object')throw Error('Config supports up to 512 fields');
        if(typeof f.key!=='string'||!f.key.trim()||f.key.length>80||forbidden.has(f.key))throw Error('Config Key must contain 1–80 characters and not be reserved');
        if(Object.hasOwn(result,f.key))throw Error('Duplicate Config Key: '+f.key);
        if(!types.includes(f.type))throw Error('Unsupported Config Type');
        if(typeof (f.unit??'')!=='string'||(f.unit||'').length>64)throw Error('Config Unit is too long');
        let value;
        if(f.type==='object')value=group(f.fields,depth+1);
        else{value=f.value;const actual=kind(value);if(actual!==f.type&&!(f.type==='number'&&actual==='integer')&&!(f.nullable===true&&value===null))throw Error('Config Value does not match Type: '+f.key);checkJSON(value,depth+1);value=clone(value);}
        result[f.key]=value;
      }return result;
    }return group(schema.fields,0);
  }
  function newField(fields){let n=1;while(fields.some(f=>f.key==='field_'+n))n++;return {key:'field_'+n,type:'number',unit:'',nullable:true,value:null};}
  const labels={components:'물리 컴포넌트',vapour:'증기 물성',vapor:'증기 물성',phase_change:'상변화',T_K:'절대온도 (K)',cp:'정압비열 (질량당 열용량)',rho:'밀도',mu:'점성계수 (흐름 저항)',kappa:'열전도율',evap_C:'증발 완화계수',cond_C:'응축 완화계수',Tsat_C:'포화온도 (끓는점)',h_fg_J_kg:'기화잠열 (상변화 열량)',values:'표본 값',property_tables:'물성 표',material_state:'물질 상태',init_T_dielectric_C:'초기 온도',init_T_water_C:'초기 온도',init_T_dielectric_top_C:'상부 초기 온도',init_T_water_top_C:'상부 초기 온도',power:'발열량',voltage:'전압',electric_potential:'전위',conductivity:'전기전도도',shape:'기하 형상',min:'최소 좌표',max:'최대 좌표',min_m:'최소 좌표',max_m:'최대 좌표',center:'중심 좌표',radius:'반지름',height:'높이',axis:'중심축',role:'영역 역할',config_bindings:'물리 설정 연결',heater:'열원',total_W:'총 발열량',geometry_spec:'공간 형상',loading:'적재 배치',tank:'계산 영역',board:'고체 영역',coil:'열교환 영역',silo:'사일로 형상',analysis:'해석 정보',geometry:'공간 형상',mesh:'격자',materials:'재료 물성',physics:'물리 모델',initial_conditions:'초기 조건',boundary_conditions:'경계조건',numerics:'계산 방법',termination:'종료 조건',outputs:'결과 저장',fluids:'유체',fluid:'유체',solid:'고체',fields:'물리량',source:'파일 경로',fluid_regions:'유체 영역',solid_regions:'고체 영역',regions:'영역',interfaces:'계면',generator:'격자 생성기',cell_size:'격자 크기',refinement_regions:'국부 세분화 영역',name:'이름',state:'상태',density:'밀도',kinematic_viscosity:'동점성계수',heat_capacity:'비열',thermal_conductivity:'열전도율',thermal_expansion:'열팽창계수',reference_temperature:'기준 온도',transport_model:'수송 모델',thermophysical_properties:'열물성 모델',thermoType:'열물성 구성',mixture:'혼합물',transport:'수송 특성',thermo:'열역학 모델',equationOfState:'상태방정식',specie:'성분',energy:'에너지',U:'속도',p:'압력',p_rgh:'중력 보정 압력',T:'온도',inlet:'유입 경계',outlet:'유출 경계',wall:'벽면 경계',far_field:'원방 경계',body:'물체 표면',mesh_patch:'격자 경계 이름',type:'종류',value:'값',unit:'단위',x:'X',y:'Y',z:'Z',algorithm:'계산 알고리즘',schemes:'이산화 방법',linear_solvers:'선형 방정식 풀이',controls:'반복 계산',time_step:'계산 시간간격',max_time_step:'최대 시간간격',max_courant:'최대 Courant 수',adjust_time_step:'시간간격 자동 조절',pressure_reference:'압력 기준',cell:'기준 셀 번호',nCorrectors:'압력 보정 횟수',nOuterCorrectors:'외부 반복 횟수',nNonOrthogonalCorrectors:'비직교 보정 횟수',nAlphaCorr:'상분율 보정 횟수',nAlphaSubCycles:'상분율 세부 계산 횟수',subcycles:'세부 계산 횟수',phase_fraction:'상분율 계산',method:'계산 기법',coefficients:'추가 계수',model:'모델',motion:'격자 움직임',radiation:'복사',sources:'추가 소스항',gravity:'중력 가속도',surface_tension:'표면장력',pairs:'상 연결',phase_transfer:'상간 전달',flow_regime:'유동 모델',turbulence:'난류',initial_fields:'난류 초기값',boundary_fields:'난류 경계조건',delta:'필터 폭 모델',model_options:'모델 선택지',mode:'종료 방식',end_time:'종료 물리시간',max_time:'최대 계산 시간',max_iterations:'최대 반복 횟수',sustain_steps:'기준 유지 횟수',residual_targets:'잔차 수렴 기준',saved_frames:'저장 프레임 수',include_initial_frame:'초기 프레임 포함',write_interval:'결과 저장 간격',probes:'관측 위치',thermal_interfaces:'열전달 접합면',solid_temperature:'고체 초기 온도',scalar_transport:'스칼라 수송',field_name:'물리량 이름',diffusivity:'확산계수',initial_value:'초기값',porous_regions:'다공성 영역',solver:'솔버',time_mode:'시간 방식',choices:'설문 응답',form_generator:'양식 생성 방식',ddtSchemes:'시간 이산화',gradSchemes:'기울기 이산화',divSchemes:'대류항 이산화',laplacianSchemes:'확산항 이산화',interpolationSchemes:'보간 방법',snGradSchemes:'면 법선 기울기',Pr:'Prandtl 수',Prt:'난류 Prandtl 수',k:'난류 운동에너지',epsilon:'난류 소산율',omega:'비소산율'};
  const typeLabels={string:'문자',number:'숫자',integer:'정수',boolean:'사용 여부',object:'항목 묶음',array:'목록',null:'값 없음'};
  function fieldLabel(field,path=[]){if(!field.label&&field.key==='type'){if(path[0]==='boundary_conditions')return '경계조건 종류';if(path.includes('thermoType'))return '열물성 구성 방식';}return field.label||labels[field.key]||(/^phase_\d+$/.test(field.key)?'유체 '+field.key.split('_')[1]:/^alpha\.phase_\d+$/.test(field.key)?'상분율 '+field.key.split('_')[1]:(globalThis.CFDSettings?.fieldInfo?.([field.key],{})?.title||field.key));}
  function fieldExample(field,path=[]){
    const key=field.key,p=path.join('.');
    if(key==='type'&&path[0]==='boundary_conditions')return 'ex) fixedValue';
    if(key==='mesh_patch')return 'ex) '+(path[0]==='boundary_conditions'&&path[1]?path[1]:'inlet');
    if(key==='source')return 'ex) constant/polyMesh';
    if(key==='name')return 'ex) fluid_1';
    if(key==='field_name')return 'ex) C';
    if(key==='transport_model')return 'ex) Newtonian';
    if(field.type==='integer')return 'ex) 10';
    if(field.type==='number')return /\.(x|y|z)$/.test(p)?'ex) 0.0':'ex) 0.5';
    if(field.type==='array')return key==='fields'?'ex) ["U", "p"]':'ex) []';
    if(field.type==='object')return 'ex) {}';
    return 'ex) ABC';
  }
  // Conditional inputs stay visible until the selected model rules them out.
  function fieldStatus(field,path=[]){
    if(field.type==='object'){
      const states=field.fields.map(f=>fieldStatus(f,[...path,field.key]));
      if(states.includes('required'))return 'required';
      if(states.includes('conditional'))return 'conditional';
      if(states.length&&states.every(x=>x==='fixed'))return 'fixed';
    }
    if(field.readonly)return 'fixed';
    if(field.required===true)return 'required';
    if(field.required===undefined)return 'conditional';
    const p=[...path,field.key].join('.');
    if(/^(geometry\.|geometry_spec\.|boundary_conditions\.|physics\.turbulence\.|numerics\.max_(time_step|courant))/.test(p))return 'conditional';
    return 'optional';
  }
  function validateValueEdits(before,after,path=[]){
    if(before!==null&&after!==null&&typeof before!==typeof after)throw Error(path.join('.')+' 입력 형식을 확인하세요');
    if(Array.isArray(before)!==Array.isArray(after)&&before!==null)throw Error(path.join('.')+' 배열 형식을 유지하세요');
    if(Array.isArray(before)&&Array.isArray(after))for(let i=0;i<Math.min(before.length,after.length);i++)validateValueEdits(before[i],after[i],[...path,i]);
    if(before&&typeof before==='object'&&!Array.isArray(before)&&after&&typeof after==='object')for(const [key,value]of Object.entries(before)){if(Object.hasOwn(after,key))validateValueEdits(value,after[key],[...path,key]);}
    fromConfig({value:after});
  }
  // Inspector recommendations are definitions, not an executable solver adapter.
  const materialCatalog=[
    ['density','밀도','kg/m³','all'],['kinematic_viscosity','동점성계수','m²/s','fluid'],['viscosity','점성계수','Pa·s','fluid'],
    ['heat_capacity','비열','J/(kg·K)','thermal'],['thermal_conductivity','열전도율','W/(m·K)','thermal'],['initial_temperature','초기 온도','K','thermal'],
    ['thermal_expansion','열팽창계수','1/K','thermal'],['reference_temperature','기준 온도','K','thermal'],['power','발열량','W','thermal'],
    ['volumetric_heat_source','체적 발열량','W/m³','thermal'],['emissivity','방사율','','thermal'],['heat_transfer_coefficient','열전달계수','W/(m²·K)','thermal'],
    ['contact_resistance','접촉 열저항','m²·K/W','solidThermal'],['porosity','공극률','','solid'],['permeability','투과도','m²','solid'],
    ['surface_roughness','표면 거칠기','m','solid'],['voltage','전압','V','solid'],['electric_conductivity','전기전도도','S/m','solid'],
    ['surface_tension','표면장력','N/m','interface'],['contact_angle','접촉각','°','interface'],['initial_phase_fraction','초기 상분율','','interface'],
    ['molecular_weight','분자량','kg/kmol','gas'],['latent_heat','잠열','J/kg','phase'],['transition_temperature','상변화 온도','K','phase'],
    ['temperature_samples','온도 표본','K','thermal','array']
  ].map(([key,label,unit,scope,type='number'])=>({key,label,unit,scope,type}));
  function materialProfile(config,part,path=[],form=null){
    const solver=config.analysis?.solver||form?.solver?.id||form?.solver||config.openfoam_mapping?.solver||'';
    const known=['icoFoam','simpleFoam','pimpleFoam','pisoFoam','buoyantSimpleFoam','buoyantPimpleFoam','chtMultiRegionFoam','interFoam','interIsoFoam','rhoPimpleFoam','icoReactingMultiphaseInterFoam','warehouseBuoyantFoam'].includes(solver);
    const state=part.material_state||(['solid','liquid','gas'].includes(part.state)?part.state:'')||(['water','dielectric_fluid'].includes(path[0])?'liquid':path.includes('solid_regions')||['board','coil'].includes(path[0])||path[0]==='heater'?'solid':'');
    const thermal=!known||['buoyantSimpleFoam','buoyantPimpleFoam','chtMultiRegionFoam','rhoPimpleFoam','icoReactingMultiphaseInterFoam','warehouseBuoyantFoam'].includes(solver);
    const solid=state==='solid',fluid=['liquid','gas'].includes(state),interfaceFlow=['interFoam','interIsoFoam','icoReactingMultiphaseInterFoam'].includes(solver);
    const phaseSupported=fluid&&solver==='icoReactingMultiphaseInterFoam';
    const phaseEnabled=part.properties?.phase_change?.value===true;
    const allowed={all:!!state,fluid,solid,thermal:thermal&&!!state,solidThermal:solid&&thermal,gas:state==='gas',interface:fluid&&interfaceFlow,phase:phaseSupported&&phaseEnabled};
    const catalog=materialCatalog.filter(f=>allowed[f.scope]);
    const basic=state?[...(solid||!known||interfaceFlow?['density']:[]),...(fluid?['kinematic_viscosity']:[]),...(thermal?['heat_capacity','thermal_conductivity','initial_temperature']:[])]:[];
    // Compressible density can be derived from the selected equation of state.
    return {solver,known,state,thermal,phaseSupported,phaseEnabled,catalog,basic,solidUnsupported:solid&&known&&solver!=='chtMultiRegionFoam'};
  }
  const parameterUnits={T_K:'K',T_C:'°C',rho:'kg/m³',cp:'J/(kg·K)',mu:'Pa·s',nu:'m²/s',kappa:'W/(m·K)',evap_C:'1/s',cond_C:'1/s',Tsat_C:'°C',h_fg_J_kg:'J/kg',dx_mm:'mm',dt_s:'s',max_dt_s:'s',write_interval_s:'s',viz_interval_s:'s'};
  function importedSchema(payload,previous=null){
    if(!payload||typeof payload!=='object'||Array.isArray(payload))throw Error('Config must be a JSON object');
    if(payload.version===1&&Array.isArray(payload.fields)){toConfig(payload);return fromConfig(toConfig(payload),payload);}
    if(payload.config&&typeof payload.config==='object'&&(payload.config_schema||payload.input_schema)){
      const definition=payload.config_schema||payload.input_schema;toConfig(definition);return fromConfig(payload.config,definition);
    }
    return fromConfig(payload,previous);
  }
  function tableColumns(fields){
    const temperature=fields.find(f=>f.key==='T_K'&&f.type==='array');if(!temperature)return [];
    const numeric=f=>f.type==='array'&&Array.isArray(f.value)&&f.value.every(v=>v===null||typeof v==='number');
    if(!numeric(temperature))return [];
    const values=fields.filter(f=>['values','rho','cp','mu','kappa','nu'].includes(f.key)&&numeric(f));return values.length?[temperature,...values]:[];
  }
  function validateTables(config){
    const visit=(v,path=[])=>{if(!v||typeof v!=='object')return;if(!Array.isArray(v)&&Array.isArray(v.T_K)){
      const columns=['values','rho','cp','mu','kappa','nu'].filter(k=>Array.isArray(v[k]));
      if(columns.some(k=>v[k].length!==v.T_K.length))throw Error('온도와 물성값의 행 수를 맞추세요: '+path.join('.'));
    }for(const [k,x]of Object.entries(v))visit(x,[...path,k]);};visit(config);
  }
  function open({config={},schema=null,onSave,onValidate=null,title='Config',schemaOnly=false,valuesOnly=false,readonly=false,submitLabel='저장',customSections=[],onMount=null,onClone=null,form=null}){
    let searchQuery='';
    let draft=schemaOnly&&schema?clone(schema):fromConfig(config,schema),mode='fields',structure=false,showOptional=false,selected='';
    const rawValues=new WeakMap();toConfig(draft);
    const el=(tag,text,cls)=>{const x=document.createElement(tag);if(text!=null)x.textContent=text;if(cls)x.className=cls;return x;};
    const button=(text,fn)=>{const x=el('button',text,'btn');x.type='button';x.onclick=fn;if(text==='취소')x.classList.add('fc-cancel');return x;};
    if(!document.getElementById('formConfigStyle')){const style=el('style');style.id='formConfigStyle';style.textContent=`
.fc-dialog{width:min(1120px,96vw);max-width:1120px;height:min(850px,92vh);max-height:92vh;padding:22px;border:1px solid var(--line);border-radius:14px;background:var(--card,var(--page));color:var(--text);box-sizing:border-box}.fc-dialog [hidden]{display:none!important}.fc-dialog[open]{display:flex;flex-direction:column;gap:12px}.fc-dialog::backdrop{background:#000a}.fc-header,.fc-actions,.fc-toolbar,.fc-modes,.fc-tools{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.fc-header h2{font-size:18px;margin:0}.fc-toolbar{justify-content:space-between}.fc-tools{margin-left:auto}.fc-body{flex:1;min-height:0;overflow:auto}.fc-layout{display:grid;grid-template-columns:180px minmax(0,1fr);height:100%;min-height:0}.fc-nav{overflow:auto;padding-right:12px;border-right:1px solid var(--line)}.fc-nav .btn{box-sizing:border-box;min-height:38px;height:38px;width:100%;text-align:left;margin-bottom:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.fc-nav [aria-current=true],.fc-toolbar [aria-pressed=true]{border-color:var(--accent,#579eff);background:#3987e51a}.fc-main{overflow:auto;padding:0 14px;min-width:0}.fc-main h3{font-size:15px;margin:0 0 12px}.fc-note,.fc-hint{color:var(--muted);font-size:12px;line-height:1.5;margin:0}.fc-filter{margin-bottom:12px;display:flex;align-items:center;gap:6px;font-size:12px}.fc-field{padding:10px 0;border-bottom:1px solid var(--line);min-width:0}.fc-row{display:grid;grid-template-columns:180px minmax(180px,1fr);gap:12px;align-items:center}.fc-caption{font-size:13px;min-width:0}.fc-caption small{display:block;font-size:11px;color:var(--muted);margin-top:4px}.fc-badge{font-size:10px;color:var(--red,#ef8989);margin-left:7px}.fc-control{display:flex;gap:8px;align-items:center;min-width:0}.fc-unit{font-size:11px;color:var(--muted);white-space:nowrap}.fc-field input,.fc-field select,.fc-field textarea,.fc-part-properties input,.fc-part-properties select,.fc-part-properties textarea,.fc-json,.fc-add input,.fc-add select{box-sizing:border-box;width:100%;min-width:0;background:var(--page);color:var(--text);border:1px solid var(--line);border-radius:7px;padding:8px;font:inherit;font-size:13px;min-height:34px}.fc-field textarea,.fc-json{font:12px Consolas,monospace;resize:vertical}.fc-field output{overflow-wrap:anywhere;font-size:12px}.fc-array{width:100%;min-width:0}.fc-object-control{width:100%;min-width:0}.fc-table-scroll{overflow-x:auto}.fc-property-table table{border-collapse:separate;border-spacing:5px;width:100%;table-layout:fixed;min-width:300px}.fc-property-table th{font-size:11px;text-align:left;font-weight:400;color:var(--muted)}.fc-property-table th small{display:block;margin-top:4px}.fc-property-table th:last-child:empty{width:28px}.fc-property-table .btn{min-width:28px;height:28px;padding:0 7px}.fc-array-head{display:flex;gap:8px;align-items:center;margin-bottom:8px}.fc-array-head>.btn:first-of-type{margin-left:auto}.fc-array .btn{width:28px;height:28px;min-width:28px;padding:0;display:inline-flex;justify-content:center;align-items:center;font-size:19px;line-height:1;border-radius:7px}.fc-array-row{display:flex;align-items:flex-start;gap:7px;margin-bottom:6px}.fc-array-index{min-width:20px;font-size:11px;color:var(--muted);padding-top:9px}.fc-array-value{flex:1;min-width:0}.fc-role+.fc-role{margin-top:12px}.fc-vector{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;flex:1}.fc-vector label{display:flex;align-items:center;gap:4px;font-size:11px}.fc-section{margin:14px 0 0;border:1px solid var(--line);border-radius:10px;padding:0 12px 10px;min-width:0}.fc-section legend{font-size:12px;padding:0 6px;color:var(--muted)}.fc-section>.fc-field:last-child{border-bottom:0}.fc-structure-row{display:grid;grid-template-columns:1fr 1fr 130px 90px auto;gap:8px;align-items:end}.fc-structure-row label{font-size:11px;color:var(--muted);display:flex;flex-direction:column;gap:5px}.fc-json{height:100%;min-height:260px;box-sizing:border-box;width:100%;background:var(--page);color:var(--text);border:1px solid var(--line);border-radius:10px;padding:14px}.fc-error{color:var(--red,#ef8989);font-size:12px;margin:0;white-space:pre-wrap}.fc-error:empty{display:none}.fc-actions{justify-content:flex-end}.fc-actions>.fc-cancel{order:-1;margin-inline-end:auto}.fc-validation{max-height:90px;overflow:auto;font-size:12px;border-top:1px solid var(--line);padding-top:8px}.fc-validation p{margin:4px 0}.fc-add{padding:12px;border:1px solid var(--accent,#579eff);border-radius:10px;margin-bottom:12px}.fc-add-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.fc-add label{font-size:12px;display:flex;flex-direction:column;gap:5px}.fc-add .fc-actions{margin-top:10px}.fc-empty{padding:25px;color:var(--muted);font-size:13px}.fc-main .fc-titlebar{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}.fc-main .fc-titlebar h3{margin:0}@media(max-width:760px){.fc-layout{grid-template-columns:135px minmax(0,1fr)}.fc-row{grid-template-columns:1fr;gap:6px}.fc-structure-row{grid-template-columns:1fr 1fr}.fc-dialog{padding:14px}.fc-main{padding-right:0}.fc-add-grid{grid-template-columns:1fr}}

.fc-dialog{width:min(1640px,97vw);max-width:1640px}.fc-workspace{display:grid;grid-template-columns:minmax(570px,1.35fr) minmax(310px,1fr);gap:16px;flex:1;min-height:0}.fc-layout{grid-template-columns:160px minmax(0,1fr)}.fc-row{grid-template-columns:minmax(100px,135px) minmax(100px,1fr);gap:10px}.fc-body{height:100%}.fc-preview{min-height:0;min-width:0;border:1px solid var(--line);border-radius:12px;overflow:hidden;display:flex;flex-direction:column;background:#111315}.fc-preview-header{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:12px;border-bottom:1px solid var(--line);font-size:13px}.fc-preview-host{position:relative;flex:1;min-height:180px;overflow:hidden}.fc-preview-host canvas{display:block;width:100%;height:100%}.fc-preview-note{margin:0;padding:10px;font-size:11px;color:var(--muted);max-height:68px;overflow:auto}.fc-element-list{box-sizing:border-box;width:100%;border:0;border-bottom:1px solid var(--line);margin:0 0 12px;padding:0 0 12px}.fc-element-list h4{font-size:12px;margin:0 0 10px;color:var(--muted)}.fc-section>select{width:100%;padding:8px;background:var(--page);color:var(--ink);border:1px solid var(--line);border-radius:7px;margin:10px 0}.sp-tags{position:absolute;inset:0;pointer-events:none;overflow:hidden}.sp-leaders{position:absolute;inset:0;width:100%;height:100%;overflow:hidden;pointer-events:none}.sp-leaders polyline{stroke:currentColor;stroke-width:1;opacity:.7;vector-effect:non-scaling-stroke}.sp-leaders circle{fill:currentColor;opacity:.9}.sp-leaders .selected polyline{stroke:#9dc5ff;stroke-width:1.5;opacity:1}.sp-leaders .selected circle{fill:#bcd8ff}.sp-tag{position:absolute;transform:translate(-50%,-50%);pointer-events:auto;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;background:#191d23e8;color:#fff;border:1px solid #677487;border-radius:6px;padding:5px 8px;font-family:inherit;font-size:11px;cursor:pointer}.sp-tag[aria-pressed=true]{border-color:#73adff;background:#193e69;z-index:2}@media(max-width:980px){.fc-workspace{grid-template-columns:minmax(430px,1fr) minmax(240px,.75fr)}.fc-layout{grid-template-columns:130px minmax(0,1fr)}.fc-row{grid-template-columns:1fr}.fc-dialog{padding:14px}}@media(max-width:740px){.fc-workspace{grid-template-columns:1fr;grid-template-rows:minmax(220px,1fr) 240px;overflow:auto}.fc-main{padding-right:4px}}


/* Config, geometry and JSON are independent cards; opening JSON only moves them. */
.fc-dialog{--editor-width:clamp(560px,35vw,700px);--preview-width:clamp(460px,34vw,680px);--json-width:clamp(440px,27vw,540px);--pair-width:calc(var(--editor-width) + var(--preview-width) + 18px);--panel-offset:max(0px,calc((min(98vw,calc(var(--pair-width) + var(--json-width) + 18px)) - var(--pair-width)) / 2));width:min(98vw,calc(var(--pair-width) + var(--json-width) + 18px));max-width:none;padding:0;border:0;border-radius:0;background:transparent;box-shadow:none;overflow:auto;transition:none;color:var(--ink)}
.fc-dialog[open]{display:block}
.fc-editor-card,.fc-dialog>.fc-preview{position:absolute;top:0;bottom:0;box-sizing:border-box;border:1px solid var(--line);border-radius:14px;display:flex;flex-direction:column;overflow:hidden;transform:translateX(var(--panel-offset));transition:transform .42s cubic-bezier(.22,1,.36,1)}
.fc-editor-card{left:0;width:var(--editor-width);padding:20px;gap:12px;background:var(--surface,var(--page))}
.fc-dialog>.fc-preview{left:calc(var(--editor-width) + 18px);width:var(--preview-width);margin:0;background:#111315}
.fc-dialog>.fc-preview .fc-preview-header{padding:18px;flex:none}
.fc-dialog>.fc-preview .fc-preview-host{min-height:0}
.fc-json-open .fc-editor-card,.fc-json-open>.fc-preview{transform:translateX(0)}
.fc-editor-card .fc-workspace{display:flex;flex:1;min-height:0;overflow:hidden}.fc-editor-card .fc-body{width:100%;height:100%}.fc-nav{min-width:0}.fc-editor-card .fc-layout{grid-template-columns:145px minmax(0,1fr)}.fc-editor-card .fc-row{grid-template-columns:1fr;gap:5px}
.fc-json-pane{position:absolute;left:0;top:0;bottom:0;width:var(--json-width);box-sizing:border-box;min-width:0;overflow:hidden;display:flex;flex-direction:column;gap:14px;padding:18px;border:1px solid var(--line);border-radius:14px;background:var(--surface,var(--page));box-shadow:0 16px 48px #0005;opacity:0;visibility:hidden;transform:translateX(28px);transition:transform .42s cubic-bezier(.22,1,.36,1),opacity .24s ease,visibility .42s}
.fc-json-open .fc-json-pane{left:calc(var(--pair-width) + 18px);opacity:1;visibility:visible;transform:translateX(0)}.fc-json-pane .fc-preview-header{padding:0 0 14px}.fc-json-pane .fc-preview-header select{max-width:150px;padding:7px;border:1px solid var(--line);border-radius:7px;background:var(--page);color:var(--ink)}.fc-json-pane .fc-json{flex:1;min-height:160px;height:auto;resize:none;line-height:1.65;padding:16px}.fc-json-pane .fc-actions{flex-shrink:0}.fc-json-pane textarea{user-select:text}
@media(max-width:1050px){.fc-dialog{--editor-width:520px;--preview-width:460px;--json-width:440px}.fc-editor-card{padding:16px}.fc-editor-card .fc-layout{grid-template-columns:145px minmax(0,1fr)}}
@media(prefers-reduced-motion:reduce){.fc-editor-card,.fc-dialog>.fc-preview,.fc-json-pane{transition:none}}
.fc-dialog .btn{white-space:nowrap;flex-shrink:0}.fc-section legend{max-width:100%;box-sizing:border-box;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.fc-element-list h4{white-space:nowrap;overflow:visible;text-overflow:clip}.fc-main h3{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.fc-titlebar h3{min-width:0;flex:1}.fc-titlebar{gap:8px}.fc-caption>span:first-child{display:inline-block;max-width:100%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;vertical-align:middle}.fc-part-properties{margin-top:18px}.fc-property-head{display:flex;align-items:center;gap:8px;margin:12px 0}.fc-property-head strong{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.fc-property-head .btn{padding:4px 8px}.fc-property-add{margin-top:12px}.fc-part-properties>.fc-section{padding-bottom:12px}.fc-part-properties>.fc-section>.fc-control{margin-top:8px}.fc-part-properties .fc-control>input,.fc-part-properties .fc-control>select{flex:1}.fc-property-remove{width:28px;height:28px;min-width:28px;padding:0!important;font-size:19px;display:inline-flex;align-items:center;justify-content:center}.fc-role{display:grid;gap:8px}.fc-case-controls{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.fc-preset-load{display:flex;align-items:center;gap:8px;width:340px;min-width:0}.fc-preset-load>button{flex:none}.fc-preset-load>select{flex:1;width:auto!important}.fc-preset-load>div{flex:1;min-width:0}.fc-output-options{display:flex;flex-wrap:wrap;gap:10px}.fc-output-options label{display:flex;align-items:center;gap:5px}.fc-output-options input{width:auto;min-height:0}.fc-nav>input{padding:8px;border-radius:7px;border:1px solid var(--line);background:var(--page);color:var(--ink)}.fc-section legend .btn{margin-left:8px;padding:3px 7px;font-size:10px}.fc-case-controls label{display:flex;align-items:center;gap:6px;font-size:12px}.fc-case-controls input:not([type=checkbox]),.fc-case-controls select,.fc-custom input,.fc-custom textarea,.fc-custom select{padding:8px;border:1px solid var(--line);border-radius:7px;background:var(--page);color:var(--ink);font:inherit;min-width:0}.fc-custom{font-size:13px}.fc-custom label{display:grid;gap:7px;margin:16px 0}.fc-custom p{font-size:12px;color:var(--muted);line-height:1.6}.fc-custom textarea{width:100%;box-sizing:border-box}.fc-json-pane textarea{user-select:text}`;document.head.append(style);}
    const dialog=el('dialog',null,'fc-dialog'+(schemaOnly?' fc-schema-only':'')),header=el('div',null,'fc-header');header.append(el('h2',title));
    const toolbar=el('div',null,'fc-toolbar'),body=el('div',null,'fc-body'),error=el('p',null,'fc-error'),actions=el('div',null,'fc-actions');error.setAttribute('role','alert');
    let saving=false,jsonPath=null,jsonSpatial=false,jsonPrimitive=false,jsonDirty=false,jsonBase='',jsonArea,adding=null,elementId=null,elementDraft=null,elementPath=null,propertyAdding=false,cleanPreview=null,previewTimer=null,previewVersion=0,closed=false,cameraState=null,lastScene='';
    const commitJSON=()=>{if(jsonDirty)throw Error('JSON 저장 또는 취소를 선택하세요');globalThis.CFDInput?.assertValid(body);flushElement();toConfig(draft);};
    const guarded=fn=>{try{error.textContent='';fn();}catch(e){error.textContent=e.message;}};
    const jsonButton=button('전체 JSON',()=>openJSON(null));
    const structureButton=button('구조 편집',()=>guarded(()=>{if(valuesOnly)return;commitJSON();structure=!structure;mode='fields';render();}));structureButton.hidden=valuesOnly||readonly;
    const spatial=button('JSON',()=>openJSON(null,true));spatial.setAttribute('aria-label','전체 공간 형상 JSON');
    const upload=el('input');upload.type='file';upload.accept='.json,application/json';upload.hidden=true;
    upload.onchange=async()=>{const file=upload.files[0];if(!file)return;try{if(file.size>1000000)throw Error('JSON file must be under 1 MB');if(jsonDirty)throw Error('JSON 저장 또는 취소를 선택하세요');const parsed=JSON.parse((await file.text()).replace(/^\uFEFF/,'')),next=importedSchema(parsed,draft);toConfig(next);draft=next;elementId=null;elementDraft=null;elementPath=null;selected='';mode='fields';error.textContent='';render();if(dialog.classList.contains('fc-json-open')){jsonPrimitive=false;jsonSpatial=false;jsonPath=null;loadJSON();}}catch(e){error.textContent=e.message;}upload.value='';};
    const modes=el('div',null,'fc-modes'),tools=el('div',null,'fc-tools');const importButton=button('JSON 가져오기',()=>upload.click());importButton.hidden=readonly;tools.append(structureButton,jsonButton,importButton,button('JSON 내보내기',()=>guarded(()=>{commitJSON();const a=el('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(schemaOnly?blankDefinition(draft):toConfig(draft),null,2)],{type:'application/json'}));a.download=schemaOnly?'cfd-template.json':'cfd-config.json';a.click();render();setTimeout(()=>URL.revokeObjectURL(a.href),1000);})),upload);toolbar.append(modes,tools);
    const hint=el('p',readonly?'실행 시점의 입력 기록 · 변경하려면 이 Config로 새 Case 선택':schemaOnly?'초기 형상과 입력 양식 정의 · 물성 및 운전값은 프로젝트에서 입력':'필수 항목을 먼저 입력하세요','fc-note');
    const workspace=el('div',null,'fc-workspace'),preview=el('aside',null,'fc-preview'),previewHeader=el('div',null,'fc-preview-header'),previewHost=el('div',null,'fc-preview-host'),previewNote=el('p',null,'fc-preview-note');
    previewHeader.append(el('strong','3D 형상'),spatial);preview.append(previewHeader,previewHost,previewNote);workspace.append(body);
    const jsonPane=el('aside',null,'fc-json-pane'),jsonHeader=el('div',null,'fc-preview-header'),jsonTitle=el('strong','JSON'),jsonActions=el('div',null,'fc-actions');
    const primitiveExample=el('select');primitiveExample.setAttribute('aria-label','기본 형상 예시');primitiveExample.hidden=true;primitiveExample.append(new Option('기본 형상 예시',''),new Option('직육면체','box'),new Option('구','sphere'),new Option('원기둥','cylinder'));
    primitiveExample.onchange=()=>{if(!primitiveExample.value)return;const old=sp.primitiveDefinition(currentConfig(),jsonPath)||{},shape=primitiveExample.value;const value={name:old.name||'region',shape,unit:old.unit||'m',...(shape==='box'?{min:[0,0,0],max:[null,null,null]}:{center:[0,0,0],radius:null,...(shape==='cylinder'?{height:null,axis:'z'}:{})})};jsonArea.value=JSON.stringify(value,null,2);jsonArea.dispatchEvent(new Event('input'));primitiveExample.value='';};
    jsonArea=el('textarea',null,'fc-json');jsonArea.spellcheck=false;jsonArea.setAttribute('aria-label','선택 항목 JSON');jsonArea.readOnly=readonly;jsonArea.oninput=()=>{jsonDirty=jsonArea.value!==jsonBase;jsonSave.disabled=!jsonDirty;body.inert=jsonDirty;};
    const jsonSave=button('JSON 저장',()=>guarded(()=>{
      const parsed=JSON.parse(jsonArea.value);flushElement();
      if(jsonPrimitive){draft=fromConfig(sp.applyPrimitive(toConfig(draft),jsonPath,parsed),draft);}
      else if(jsonSpatial){const before=toConfig(draft),next=sp.mergeDocument(before,parsed);validateValueEdits(before,next);draft=fromConfig(next,draft);}
      else if(schemaOnly){const next=jsonPath?clone(draft):parsed;if(jsonPath){const field=next.fields.find(f=>f.key===jsonPath[0]);if(!field)throw Error('JSON 항목을 찾을 수 없습니다');if(parsed.key!==field.key)throw Error('선택한 항목의 JSON 키는 유지하세요');next.fields[next.fields.indexOf(field)]=parsed;}toConfig(next);draft=next;}
      else{const next=toConfig(draft);if(jsonPath)writePath(next,jsonPath,parsed);else {fromConfig(parsed);for(const key of Object.keys(next))delete next[key];Object.assign(next,parsed);}validateValueEdits(toConfig(draft),next);draft=fromConfig(next,draft);}
      jsonDirty=false;body.inert=false;jsonBase=jsonArea.value;jsonSave.disabled=true;render();loadJSON();schedulePreview();
    }));jsonSave.classList.add('pri');jsonSave.hidden=readonly;jsonSave.disabled=true;
    const dismissJSON=()=>{jsonButton.focus({preventScroll:true});jsonDirty=false;body.inert=false;dialog.classList.remove('fc-json-open');dialog.scrollLeft=0;jsonPane.inert=true;jsonPane.setAttribute('aria-hidden','true');render();};
    jsonActions.append(button(readonly?'닫기':'취소',dismissJSON),jsonSave);jsonHeader.append(jsonTitle,primitiveExample);jsonPane.append(jsonHeader,jsonArea,jsonActions);jsonPane.inert=true;jsonPane.setAttribute('aria-hidden','true');dialog.append(jsonPane);
    function loadJSON(){const value=jsonPrimitive?sp.primitiveDefinition(toConfig(draft),jsonPath):jsonSpatial?sp.document(toConfig(draft)):schemaOnly?(jsonPath?draft.fields.find(f=>f.key===jsonPath[0]):draft):(jsonPath?sp.at(toConfig(draft),jsonPath):toConfig(draft));jsonBase=JSON.stringify(value,null,2);jsonArea.value=jsonBase;jsonDirty=false;jsonSave.disabled=true;primitiveExample.hidden=!jsonPrimitive||readonly;}
    function openJSON(path,spatialScope=false){guarded(()=>{commitJSON();jsonPrimitive=spatialScope==='primitive';jsonSpatial=spatialScope===true;jsonPath=schemaOnly&&path&&!jsonPrimitive?[path[0]]:path;jsonTitle.textContent=jsonPrimitive?'형상 JSON':jsonSpatial?'전체 공간 형상 JSON':(jsonPath?jsonPath.map(key=>fieldLabel({key})).join(' / '):'전체 Config')+' JSON';render();loadJSON();dialog.classList.add('fc-json-open');jsonPane.inert=false;jsonPane.setAttribute('aria-hidden','false');jsonArea.focus({preventScroll:true});});}

    const editorCard=el('div',null,'fc-editor-card');editorCard.append(header,toolbar,hint,workspace,error,actions);dialog.prepend(editorCard,preview);hint.title='선택 항목의 기존값은 유지됩니다 · 전체 항목에서 확인';
    if(onValidate){const report=el('section',null,'fc-validation');report.setAttribute('aria-live','polite');report.textContent='입력 검사로 누락 항목을 확인할 수 있습니다';workspace.after(report);const check=button('입력 검사',async()=>{check.disabled=true;try{commitJSON();render();validateTables(toConfig(draft));const result=await onValidate(toConfig(draft));report.replaceChildren(el('strong',result.missing_count?'필수 입력 '+result.missing_count+'개 확인 필요':'정의된 필수 입력 작성 완료'));const list=el('ul');for(const issue of result.issues){const item=el('li'),link=button(issue.path.map(key=>fieldLabel({key})).join(' / '),()=>{selected=issue.path[0];showOptional=true;mode='fields';render();const target=[...body.querySelectorAll('[data-field-path]')].find(n=>n.dataset.fieldPath===issue.path.join('.'));target?.scrollIntoView({block:'center'});target?.querySelector('input,select,textarea')?.focus();});link.title=issue.path.join('.');item.append(link,' · ',issue.message);list.append(item);}for(const note of result.model_review||[])list.append(el('li',note));report.append(list);}catch(e){report.textContent=e.message;}finally{check.disabled=false;}});actions.append(check);}
    const sp=spatialAPI();
    function writePath(obj,path,value){const parent=sp.at(obj,path.slice(0,-1));if(!parent)throw Error('선택한 요소를 찾을 수 없습니다');parent[path.at(-1)]=value;}
    function currentConfig(){let value=toConfig(draft);if(elementDraft&&elementPath)writePath(value,elementPath,toConfig(elementDraft));for(const entry of readonly?[]:sp.elements(value)){if(entry.value.shape&&(['tank','board','coil'].includes(entry.path[0])||entry.path[0]==='loading')){const reference=entry.value._transform_reference;value=sp.applyPrimitive(value,entry.path,sp.primitiveDefinition(value,entry.path));if(reference)sp.at(value,entry.path)._transform_reference=reference;}}return value;}
    function flushElement(){if(!elementDraft)return;draft=fromConfig(currentConfig(),draft);elementDraft=null;elementPath=null;}
    function selectElement(id){guarded(()=>{commitJSON();elementId=id;propertyAdding=false;cleanPreview?.select(id);mode='fields';structure=false;render();});}
    function schedulePreview(){clearTimeout(previewTimer);previewTimer=setTimeout(updatePreview,180);}
    async function updatePreview(){
      if(closed)return;
      try{
        const config=currentConfig(),model=sp.shapes(config),signature=JSON.stringify(model);
        if(signature===lastScene&&cleanPreview){cleanPreview.select(elementId);return;}
        const generation=++previewVersion;cameraState=cleanPreview?.cameraState()||cameraState;cleanPreview?.();cleanPreview=null;previewHost.replaceChildren();lastScene=signature;
        previewNote.textContent=model.notes.join(' · ');
        if(!model.items.length){previewHost.append(el('p','형상과 치수를 입력하세요','fc-empty'));return;}
        const clean=await sp.viewer(previewHost,model,{onSelect:selectElement,selected:elementId,cameraState});
        if(closed||generation!==previewVersion){clean();return;}cleanPreview=clean;
      }catch(e){lastScene='';++previewVersion;cleanPreview?.();cleanPreview=null;previewHost.replaceChildren(el('p','형상 입력을 확인하세요','fc-empty'));previewNote.textContent=e.message;}
    }
    const syncInputs=()=>{schedulePreview();if(dialog.classList.contains('fc-json-open')&&!jsonDirty){try{const value=currentConfig(),definition=schemaOnly?fromConfig(value,draft):null;const part=jsonPrimitive?sp.primitiveDefinition(value,jsonPath):jsonSpatial?sp.document(value):schemaOnly?(jsonPath?definition.fields.find(f=>f.key===jsonPath[0]):definition):(jsonPath?sp.at(value,jsonPath):value);jsonBase=JSON.stringify(part,null,2);jsonArea.value=jsonBase;}catch(_){}}};body.addEventListener('input',syncInputs);body.addEventListener('change',syncInputs);
    function schemaAt(path){let field,fields=draft.fields;for(const key of path){field=fields?.find(f=>f.key===key);fields=field?.fields;}return field;}
    function renderElement(main,entry){
      if(!elementDraft||JSON.stringify(elementPath)!==JSON.stringify(entry.path))elementDraft=fromConfig(entry.value);elementPath=entry.path;entry={...entry,value:toConfig(elementDraft)};for(const f of elementDraft.fields)if(['radius','height'].includes(f.key)&&f.type==='null'){f.type='number';f.nullable=true;}if(!readonly&&!elementDraft.fields.some(f=>f.key==='name'))elementDraft.fields.unshift({key:'name',type:'string',value:entry.label});const heading=el('div',null,'fc-titlebar'),title=el('h3',entry.label);title.setAttribute('translate','no');heading.append(title);
      const primitive=sp.primitiveDefinition(currentConfig(),entry.path);const geometryJSON=button('JSON',()=>openJSON(entry.path,primitive?'primitive':false));if(primitive)geometryJSON.setAttribute('aria-label','형상 JSON');heading.append(geometryJSON);if(!readonly)heading.append(button('요소 삭제',()=>guarded(()=>{commitJSON();const value=toConfig(draft),parent=sp.at(value,entry.path.slice(0,-1)),key=entry.path.at(-1);if(Array.isArray(parent))parent.splice(key,1);else delete parent[key];draft=fromConfig(value,draft);elementId=null;render();})));main.append(heading);
      const settings=el('div',null,'fc-field'),roleLabel=el('label','영역 역할','fc-role'),role=el('input');role.setAttribute('aria-label','영역 역할');role.placeholder='ex) fluid, solid, heat_source';role.readOnly=readonly;role.value=entry.value.role||'';role.oninput=()=>{let field=elementDraft.fields.find(f=>f.key==='role');if(!field){field={key:'role',type:'string',value:''};elementDraft.fields.push(field);}field.value=role.value;};roleLabel.append(role);settings.append(roleLabel);main.append(settings);
      const profile=materialProfile(currentConfig(),entry.value,entry.path,form);
      const stateLabel=el('label','물질 상태','fc-role'),state=el('select');state.setAttribute('aria-label','물질 상태');state.disabled=readonly;
      state.append(new Option('선택',''),new Option('고체','solid'),new Option('액체','liquid'),new Option('기체','gas'));state.value=profile.state;
      state.onchange=()=>guarded(()=>{const value=state.value;commitJSON();const c=toConfig(draft),part=sp.at(c,entry.path);part.material_state=value;draft=fromConfig(c,draft);render();});
      stateLabel.append(state);settings.append(stateLabel);
      renderTransform(main,entry);
      const geometryKeys=new Set(['name','shape','type','unit','min','max','min_m','max_m','center','radius','height','axis','width_mm','depth_mm','liquid_height_mm','x0','x1','y0','y1','z0','z1','length_m','width_m','eaves_m','roof_rise_m']);
      const legacyGeometry=primitive&&!entry.value.shape;const oldDimensions=new Set(['width_mm','depth_mm','liquid_height_mm','x0','x1','y0','y1','z0','z1','min_m','max_m']);
      const geometryFields=legacyGeometry?fromConfig(primitive).fields.map(f=>({...f,readonly:true})):elementDraft.fields.filter(f=>geometryKeys.has(f.key)&&!(primitive&&oldDimensions.has(f.key)));
      const physicalFields=elementDraft.fields.filter(f=>!geometryKeys.has(f.key)&&!['role','material_state','state','config_bindings','properties','_transform_reference'].includes(f.key));
      const geometryGroup=el('fieldset',null,'fc-section');geometryGroup.append(el('legend','공간 형상'));if(geometryFields.length){main.append(geometryGroup);renderFields(geometryFields,geometryGroup,entry.path);if(legacyGeometry)geometryGroup.append(el('p','기존 치수에서 변환한 형상입니다 · JSON에서 종류·좌표·치수 편집','fc-note'));}
      if(['dielectric_fluid','water'].includes(entry.path[0])&&currentConfig().tank&&currentConfig().layers){
        const c=currentConfig(),group=geometryGroup;if(!group.isConnected)main.append(group);
        const row=el('label','영역 높이','fc-field fc-role'),height=el('input');height.type='number';height.step='any';height.required=true;height.min='0';height.max=String(c.tank.liquid_height_mm);height.value=String(entry.path[0]==='water'?c.tank.liquid_height_mm-c.layers.dielectric_mm:c.layers.dielectric_mm);height.readOnly=readonly;height.setAttribute('aria-label','영역 높이');height.oninput=()=>{if(height.value!==''&&height.validity.valid)schemaAt(['layers','dielectric_mm']).value=entry.path[0]==='water'?c.tank.liquid_height_mm-Number(height.value):Number(height.value);};row.append(height,el('span','mm','fc-unit'));group.append(row);
      }
      const automatic=sp.partBindings(currentConfig(),entry.path).filter(p=>p.join('.')!=='layers.dielectric_mm');
      if(automatic.length){for(const path of automatic){const field=schemaAt(path);if(field){const group=el('fieldset',null,'fc-section');group.dataset.componentPath=path.join('.');group.append(el('legend',path.length===1?fieldLabel(field,path):'초기 조건 및 열원'));main.append(group);renderFields(path.length===1&&field.type==='object'?field.fields:[field],group,path.length===1&&field.type==='object'?path:path.slice(0,-1));}}}
      renderProperties(main,entry);
      if(physicalFields.some(f=>!f.key.startsWith('_'))){const group=el('fieldset',null,'fc-section');group.append(el('legend','물리 속성'));main.append(group);renderFields(physicalFields,group,entry.path);}
      const bindings=Array.isArray(entry.value.config_bindings)?entry.value.config_bindings:[];
      for(const path of bindings){if(!Array.isArray(path)||automatic.some(p=>JSON.stringify(p)===JSON.stringify(path)))continue;const field=schemaAt(path);if(field){const group=el('fieldset',null,'fc-section');group.append(el('legend',fieldLabel(field,path)));main.append(group);renderFields([field],group,path.slice(0,-1));}}
    }

    function renderTransform(main,entry){
      const info=sp.transformInfo(currentConfig(),entry.path);if(!info)return;
      const group=el('fieldset',null,'fc-section');group.append(el('legend','변환'));main.append(group);
      for(const [key,label]of [['position','위치'],['scale','Scale']]){
        const row=el('div',null,'fc-field'),caption=el('div',label,'fc-caption'),vector=el('div',null,'fc-vector');row.append(caption,vector);group.append(row);
        for(let i=0;i<3;i++){const wrap=el('label','XYZ'[i]),input=el('input');input.type='number';input.step='any';input.value=String(Number(info[key][i].toPrecision(12)));input.setAttribute('aria-label',label+' '+'XYZ'[i]);input.readOnly=readonly||(key==='position'?(info.lockedPosition===true||info.lockedPosition?.[i]):info.lockedScale[i]);if(key==='scale')input.min='0.000000001';
          input.onchange=()=>guarded(()=>{if(input.value===''||!input.checkValidity())throw Error('위치와 Scale 값을 확인하세요');const next=sp.transform(currentConfig(),entry.path,key,i,Number(input.value));elementDraft=null;elementPath=null;draft=fromConfig(next,draft);render();});wrap.append(input);vector.append(wrap);
        }if(key==='position')row.append(el('span',info.unit,'fc-unit'));
      }
      if(info.lockedPosition)group.append(el('p','상위 형상에서 정의하는 좌표입니다','fc-note'));
      if(['sphere','cylinder'].includes(info.kind))group.append(el('p','곡면의 반지름 방향 Scale은 함께 변경됩니다','fc-note'));
    }
    function renderProperties(main,entry){
      const profile=materialProfile(currentConfig(),entry.value,entry.path,form);
      const section=el('section',null,'fc-part-properties'),head=el('div',null,'fc-property-head');head.append(el('strong','물성 및 초기 조건'));section.append(head);main.append(section);
      const propertyRoot=()=>{let root=elementDraft.fields.find(f=>f.key==='properties');if(!root){root={key:'properties',type:'object',fields:[]};elementDraft.fields.push(root);}if(root.type!=='object')throw Error('properties는 객체 형식이어야 합니다');return root;};
      const root=elementDraft.fields.find(f=>f.key==='properties');
      if(root&&root.type!=='object'){renderFields([root],section,entry.path);return;}
      const aliases={density:['density','rho'],kinematic_viscosity:['kinematic_viscosity','nu','mu','viscosity'],heat_capacity:['heat_capacity','cp','Cp'],thermal_conductivity:['thermal_conductivity','kappa'],initial_temperature:['initial_temperature','T','Ta_C']};
      const present=key=>(aliases[key]||[key]).some(k=>Object.hasOwn(entry.value,k)||Object.hasOwn(entry.value.property_tables||{},k))||(key==='initial_temperature'&&sp.partBindings(currentConfig(),entry.path).some(p=>String(p.at(-1)).startsWith('init_T_')));
      function drawProperty(property,virtual=false,required=false){
        const fields=property.fields||[],read=k=>fields.find(f=>f.key===k)?.value,value=fields.find(f=>f.key==='value'),type=read('type');
        if(!value||!types.includes(type)||['object','null'].includes(type)){renderFields([property],section,[...entry.path,'properties']);return;}
        const builtin=read('catalog_key')===property.key;
        value.type=type;value.nullable=true;value.label=builtin?(materialCatalog.find(p=>p.key===property.key)?.label||read('name')):read('name')||property.key;value.unit=read('unit')||'';
        const card=el('fieldset',null,'fc-section'),legend=el('legend',value.label);if(!builtin&&!virtual)legend.setAttribute('translate','no');legend.title=property.key;card.append(legend);section.append(card);
        if(required)legend.append(el('span','필수','fc-badge'));
        const widget=control(value,[...entry.path,'properties',property.key,'value']);card.append(widget);if(value.unit)widget.append(el('span',value.unit,'fc-unit'));
        if(virtual){let inserted=false;const persist=()=>{if(!inserted){propertyRoot().fields.push(property);inserted=true;}};widget.addEventListener('input',persist);widget.addEventListener('change',persist);}
        if(!readonly&&!virtual&&!required){const remove=button('−',()=>guarded(()=>{root.fields.splice(root.fields.indexOf(property),1);commitJSON();render();}));remove.classList.add('fc-property-remove');remove.setAttribute('aria-label','속성 삭제');remove.title='속성 삭제';widget.append(remove);}
      }
      // Existing tables stay canonical. Never add a competing constant for an existing property table.
      if(!readonly)for(const key of profile.basic){if(root?.fields.some(f=>f.key===key)||present(key))continue;const item=materialCatalog.find(p=>p.key===key),record={name:item.label,catalog_key:key,type:item.type,unit:item.unit,value:null};drawProperty(fromConfig({[key]:record}).fields[0],true,true);}
      for(const property of root?.fields||[])if(property.key!=='phase_change')drawProperty(property,false,profile.basic.includes(property.key));
      const actualPhase=entry.value.phase_change||entry.value.components?.phase_change||sp.partBindings(currentConfig(),entry.path).some(p=>p[0]==='phase_change');
      if(profile.state&&!actualPhase){
        const row=el('label','상변화','fc-field fc-role'),toggle=el('select');toggle.setAttribute('aria-label','상변화');toggle.append(new Option('선택',''),new Option('사용 안 함','false'),new Option('사용','true'));toggle.value=entry.value.properties?.phase_change?.value==null?'':String(entry.value.properties.phase_change.value);toggle.disabled=readonly||schemaOnly||!profile.phaseSupported;
        toggle.onchange=()=>guarded(()=>{const root=propertyRoot(),record=fromConfig({phase_change:{name:'상변화',catalog_key:'phase_change',type:'boolean',unit:'',value:toggle.value===''?null:toggle.value==='true'}}).fields[0],index=root.fields.findIndex(f=>f.key==='phase_change');if(index>=0)root.fields[index]=record;else root.fields.push(record);commitJSON();render();});row.append(toggle);section.append(row);
        if(!profile.phaseSupported)section.append(el('p','현재 솔버 양식에는 이 상태의 상변화 모델이 정의되어 있지 않습니다','fc-note'));
        else section.append(el('p','상변화 사용 시 상간 전달 모델·계수·상 연결을 별도로 정의하세요','fc-note'));
      }
      if(profile.solidUnsupported)section.append(el('p','이 솔버는 고체 내부 열전도를 직접 계산하지 않습니다','fc-note'));
      section.append(el('p','추가 속성은 Config에 저장됩니다 · 솔버 적용에는 실행 연결이 필요합니다','fc-note'));
      if(readonly)return;
      head.append(button('+ 속성',()=>{propertyAdding=!propertyAdding;section.querySelector('.fc-property-add')?.remove();if(propertyAdding)showAdd();}));
      function showAdd(){
        const panel=el('section',null,'fc-add fc-property-add'),grid=el('div',null,'fc-add-grid');panel.append(grid);section.append(panel);
        const input=(label,node)=>{const wrap=el('label',label);node.setAttribute('aria-label',label);wrap.append(node);grid.append(wrap);return node;};
        const choice=input('속성 종류',el('select')),name=input('속성 이름',el('input')),key=input('속성 키',el('input')),type=input('입력할 내용',el('select')),unit=input('단위',el('input'));
        const catalog=[{key:'custom',label:'직접 정의',unit:'',type:'number'},...profile.catalog.filter(p=>!root?.fields.some(f=>f.key===p.key)&&!present(p.key))];
        for(const item of catalog)choice.append(new Option(item.label,item.key));for(const id of ['number','integer','string','boolean','array'])type.append(new Option(typeLabels[id],id));
        name.placeholder='ex) '+(globalThis.CFDI18n?.translate('밀도')||'밀도');key.placeholder='ex) density';unit.placeholder='ex) kg/m³';
        choice.onchange=()=>{const item=catalog.find(x=>x.key===choice.value);name.value=item.key==='custom'?'':(globalThis.CFDI18n?.translate(item.label)||item.label);key.value=item.key==='custom'?'':item.key;unit.value=item.unit;type.value=item.type;};
        const buttons=el('div',null,'fc-actions');buttons.append(button('취소',()=>{propertyAdding=false;panel.remove();}),button('속성 추가',()=>guarded(()=>{
          if(!name.value.trim())throw Error('표시 이름을 입력하세요');const root=propertyRoot();const record={name:name.value.trim(),type:type.value,unit:unit.value.trim(),value:type.value==='array'?[]:type.value==='string'?'':null};const item=catalog.find(x=>x.key===choice.value);if(item?.key!=='custom'&&key.value.trim()===item.key&&name.value.trim()===(globalThis.CFDI18n?.translate(item.label)||item.label))record.catalog_key=item.key;
          const field=fromConfig({[key.value.trim()]:record}).fields[0];toConfig({version:1,fields:[...root.fields,field]});root.fields.push(field);propertyAdding=false;commitJSON();render();
        })));panel.append(buttons);
      }
      if(propertyAdding)showAdd();
    }
    function addElement(){guarded(()=>{commitJSON();const value=toConfig(draft);value.geometry??={};const root=value.geometry.shape||value.geometry.type?['regions']:['geometry','regions'];if(root.length===1)value.regions??=[];else value.geometry.regions??=[];const regions=sp.at(value,root);
      let n=1;const occupied=sp.elements(value).map(x=>x.label);while(occupied.includes('region_'+n))n++;const name='region_'+n;
      const element={name,role:'',material_state:'',shape:'box',unit:'m',min:[0,0,0],max:[null,null,null],config_bindings:[]};
      let path;if(Array.isArray(regions)){path=[...root,regions.length];regions.push(element);}else{let key=name;while(Object.hasOwn(regions,key))key+='_';regions[key]=element;path=[...root,key];}
      draft=fromConfig(value,draft);elementId=sp.pathId(path);mode='fields';structure=false;render();
    });}
    function arrayControl(field,path){
      const list=el('div',null,'fc-array'),disabled=readonly||(schemaOnly&&!spatialPath(path))||field.readonly;
      const values=Array.isArray(field.value)?field.value:[];let page=0,itemType=kind(values.find(v=>v!==null)??0);if(itemType==='integer')itemType='number';
      const redraw=()=>{list.replaceChildren();const head=el('div',null,'fc-array-head'),count=el('span',String(values.length));count.setAttribute('translate','no');head.append(count);list.append(head);
        if(!disabled){const add=button('+',()=>{if(values.length>=10000)return;const sample=values.find(v=>kind(v)===itemType||(itemType==='number'&&typeof v==='number'));const blank=v=>Array.isArray(v)?v.map(blank):v&&typeof v==='object'?Object.fromEntries(Object.entries(v).map(([k,x])=>[k,blank(x)])):typeof v==='string'?'':null;values.push(itemType==='object'?blank(sample||{}):itemType==='array'?[]:itemType==='string'?'':null);field.value=values;page=Math.floor((values.length-1)/40);redraw();list.dispatchEvent(new Event('input',{bubbles:true}));});add.setAttribute('aria-label','목록 항목 추가');head.append(add);
          if(!values.length){const type=el('select');type.setAttribute('aria-label','목록 항목 형식');for(const t of ['number','string','boolean','object','array'])type.append(new Option(typeLabels[t],t));type.value=itemType;type.onchange=()=>itemType=type.value;head.prepend(type);}
        }
        if(values.length>40){head.append(button('‹',()=>{page=Math.max(0,page-1);redraw();}),el('span',(page+1)+' / '+Math.ceil(values.length/40)),button('›',()=>{page=Math.min(Math.ceil(values.length/40)-1,page+1);redraw();}));}
        for(let i=page*40;i<Math.min(values.length,(page+1)*40);i++){
          const value=values[i],type=value===null?itemType:(typeof value==='number'?'number':kind(value)),fieldItem={key:String(i),type,nullable:true,readonly:disabled,unit:'',label:fieldLabel(field,path)+' '+(i+1),...(type==='object'?{fields:fromConfig(value||{}).fields}:{value})};
          const row=el('div',null,'fc-array-row'),number=el('span',String(i+1),'fc-array-index');number.setAttribute('translate','no');row.append(number);list.append(row);
          const cell=el('div',null,'fc-array-value');row.append(cell);if(type==='object')renderFields(fieldItem.fields,cell,[...path,i]);else cell.append(control(fieldItem,[...path,i]));
          const update=()=>{try{values[i]=type==='object'?toConfig({version:1,fields:fieldItem.fields}):fieldItem.value;field.value=values;}catch(_){values[i]=undefined;}};cell.addEventListener('input',update);cell.addEventListener('change',update);
          if(!disabled){const remove=button('−',()=>{values.splice(i,1);field.value=values;page=Math.min(page,Math.max(0,Math.ceil(values.length/40)-1));redraw();list.dispatchEvent(new Event('input',{bubbles:true}));});remove.setAttribute('aria-label','목록 항목 삭제');row.append(remove);}
        }
      };redraw();return list;
    }
    function coordinateField(field,path){
      return field.type==='array'&&field.value?.length===3&&field.value.every(x=>x===null||typeof x==='number')&&(
        ['position','coordinates','origin','U','gravity'].includes(field.key)||
        (spatialPath(path)&&['min','max','center','min_m','max_m'].includes(field.key))||
        (typeof path.at(-1)==='number'&&['probes','probes_mm'].includes(path[0])));
    }
    function propertyTable(columns,fields,host,path){
      const box=el('section',null,'fc-property-table fc-field'),head=el('div',null,'fc-array-head'),viewport=el('div',null,'fc-table-scroll');box.dataset.tablePath=path.join('.');box.append(head,viewport);host.append(box);let page=0;
      const disabled=readonly||(schemaOnly&&!spatialPath(path))||columns.some(f=>f.readonly);
      const rows=()=>Math.max(0,...columns.map(f=>f.value.length));
      const redraw=()=>{head.replaceChildren();viewport.replaceChildren();head.append(el('span','온도별 물성'));
        if(!disabled){const add=button('+',()=>{const n=rows();if(n>=10000)return;for(const f of columns){while(f.value.length<n)f.value.push(null);f.value.push(null);}page=Math.floor(n/40);redraw();box.dispatchEvent(new Event('input',{bubbles:true}));});add.setAttribute('aria-label','물성 행 추가');head.append(add);}
        if(rows()>40)head.append(button('‹',()=>{page=Math.max(0,page-1);redraw();}),el('span',(page+1)+' / '+Math.ceil(rows()/40)),button('›',()=>{page=Math.min(Math.ceil(rows()/40)-1,page+1);redraw();}));
        const table=el('table'),thead=el('thead'),labelsRow=el('tr'),tbody=el('tbody');table.style.minWidth=(columns.length*145+(disabled?0:40))+'px';thead.append(labelsRow);table.append(thead,tbody);viewport.append(table);
        const unitField=fields.find(f=>f.key==='unit');
        for(const f of columns){const th=el('th',f.key==='values'?fieldLabel({key:path.at(-1)}):fieldLabel(f));const unit=f.unit||(f.key==='values'?unitField?.value:parameterUnits[f.key]);if(unit&&f.key!=='T_K')th.append(el('small',unit));th.title=[...path,f.key].join('.');labelsRow.append(th);}if(!disabled)labelsRow.append(el('th'));
        for(let i=page*40;i<Math.min(rows(),(page+1)*40);i++){const tr=el('tr');tbody.append(tr);for(const f of columns){const td=el('td'),input=el('input');input.type='number';input.step='any';input.value=f.value[i]??'';input.readOnly=disabled;input.placeholder='ex) 0.5';input.setAttribute('aria-label',fieldLabel(f)+' '+(i+1));input.dataset.configPath=[...path,f.key,i].join('.');globalThis.CFDInput?.bind(input,{type:'number',nullable:true});input.oninput=()=>{try{const value=globalThis.CFDInput?CFDInput.parseValue(input.value,'number',{nullable:true}):(input.value===''?null:Number(input.value));while(f.value.length<=i)f.value.push(null);f.value[i]=value;}catch(_){f.value[i]=undefined;}};td.append(input);tr.append(td);}
          if(!disabled){const td=el('td'),remove=button('−',()=>{for(const f of columns)f.value.splice(i,1);page=Math.min(page,Math.max(0,Math.ceil(rows()/40)-1));redraw();box.dispatchEvent(new Event('input',{bubbles:true}));});remove.setAttribute('aria-label','물성 행 삭제');td.append(remove);tr.append(td);}}
      };redraw();
    }
    function control(field,path,choicesOverride=null){
      const container=el('div',null,'fc-control'),name=path.join('.');
      const bind=node=>{node.setAttribute('aria-label',fieldLabel(field,path));node.dataset.configPath=name;container.append(node);return node;};
      if(field.type==='array'&&field.key!=='output_fields'&&!coordinateField(field,path)){container.append(arrayControl(field,path));return container;}
      if(field.type==='object'){
        const group=el('div',null,'fc-object-control');container.append(group);renderFields(field.fields,group,path);if(!readonly&&!field.readonly)group.append(button('항목 추가',()=>{adding={fields:field.fields,path};render();}));return container;
      }
      if(coordinateField(field,path)){
        const axes=el('div',null,'fc-vector');container.append(axes);for(let i=0;i<3;i++){const label=el('label','XYZ'[i]),v=el('input');v.type='number';v.step='any';v.value=field.value[i]??'';v.readOnly=readonly||(schemaOnly&&!spatialPath(path))||field.readonly;v.placeholder='ex) 0.0';v.setAttribute('aria-label',fieldLabel(field,path)+' '+'XYZ'[i]);v.dataset.configPath=name+'.'+i;globalThis.CFDInput?.bind(v,{type:'number',nullable:true});v.oninput=()=>{try{field.value[i]=CFDInput.parseValue(v.value,'number',{nullable:true});}catch(_){field.value[i]=undefined;}};label.append(v);axes.append(label);}return container;
      }
      if(readonly||(schemaOnly&&!spatialPath(path))||field.readonly){
        const value=field.type==='object'?toConfig({version:1,fields:field.fields}):field.value;
        const out=bind(el(['array','object'].includes(field.type)?'textarea':'input'));out.readOnly=true;
        out.value=readonly||field.readonly?(typeof value==='object'&&value!==null?JSON.stringify(value):String(value??'')):'';
        out.placeholder=field.type==='boolean'?'ex) true / false':fieldExample(field,path);out.setAttribute('translate','no');
        if(out.tagName==='TEXTAREA')out.rows=2;
      }
      else if(field.key==='output_fields'&&field.type==='array'){
        const choices=globalThis.CFDSettings?.outputChoices(field.value,form)||field.value,group=el('div',null,'fc-output-options');container.append(group);
        for(const value of choices){const label=el('label'),input=el('input');input.type='checkbox';input.checked=field.value.includes(value);input.onchange=()=>{field.value=choices.filter((_,i)=>group.querySelectorAll('input')[i].checked);};label.append(input,el('span',({flow:'유속',therm:'온도',phase:'상분율',bubble:'기포',pressure:'압력',turbulence:'난류'})[value]||value));group.append(label);}
      }
      else if((choicesOverride||field.enum)?.length){const v=bind(el('select')),choices=clone(choicesOverride||field.enum);if(!choices.some(x=>Object.is(x,field.value)))choices.unshift(field.value);choices.forEach((x,i)=>v.append(new Option(String(x??'선택'),String(i))));v.value=String(choices.findIndex(x=>Object.is(x,field.value)));v.onchange=()=>{field.value=choices[Number(v.value)];if(field.type==='null'&&field.value!==null){field.type=kind(field.value);field.nullable=true;}};}
      else if(globalThis.CFDSettings?.choicesFor(field.key).length&&['string','number','integer'].includes(field.type)){
        const select=bind(el('select')),choices=globalThis.CFDSettings.choicesFor(field.key);if(!choices.some(o=>o.value===field.value))choices.push({value:field.value,label:String(field.value??'선택')});for(const choice of choices)select.append(new Option(choice.label,String(choice.value)));select.value=String(field.value);select.onchange=()=>field.value=choices.find(c=>String(c.value)===select.value).value;
      }
      else if(spatialPath(path)&&['shape','axis','unit'].includes(field.key)&&field.type==='string'){
        const v=bind(el('select')),choices=field.key==='shape'?['box','sphere','cylinder']:field.key==='axis'?['x','y','z']:['m','cm','mm'];if(field.value&&!choices.includes(field.value))choices.unshift(field.value);v.append(new Option('선택',''));for(const choice of choices)v.append(new Option(({box:'직육면체',sphere:'구',cylinder:'원기둥'})[choice]||choice,choice));v.value=field.value||'';
        v.onchange=()=>{field.value=v.value;if(field.key==='shape'&&elementDraft){const add=(key,value)=>{if(!elementDraft.fields.some(f=>f.key===key))elementDraft.fields.push(value===null?{key,type:'number',nullable:true,value:null}:fromConfig({[key]:value}).fields[0]);};if(v.value==='box'){add('min',[0,0,0]);add('max',[null,null,null]);}else{add('center',[0,0,0]);add('radius',null);if(v.value==='cylinder'){add('height',null);add('axis','z');}}commitJSON();render();}};
      }
      else if(field.type==='boolean'){const v=bind(el('select'));if(field.nullable)v.append(new Option('선택',''));v.append(new Option('사용','true'),new Option('사용 안 함','false'));v.value=field.value===null?'':String(field.value);v.onchange=()=>field.value=v.value===''?null:v.value==='true';}
      else if(field.type==='null'){const v=bind(el('select'));v.append(new Option('입력 형식 선택',''));for(const t of ['number','string','boolean','object','array'])v.append(new Option(typeLabels[t],t));v.onchange=()=>{if(!v.value)return;field.type=v.value;field.nullable=true;if(v.value==='object'){delete field.value;field.fields=[];}else field.value={number:null,string:'',boolean:null,array:[]}[v.value];render();};}
      else if(field.type==='array'||field.type==='object'){
        const v=bind(el('textarea'));v.rows=2;v.value=rawValues.get(field)??JSON.stringify(field.type==='object'?toConfig({version:1,fields:field.fields}):field.value,null,2);v.placeholder=fieldExample(field,path);v.setAttribute('translate','no');globalThis.CFDInput?.bind(v,{type:field.type});
        v.oninput=()=>{rawValues.set(field,v.value);try{const value=globalThis.CFDInput?CFDInput.parseValue(v.value,field.type):JSON.parse(v.value);if(field.type==='object')field.fields=fromConfig(value,{fields:field.fields}).fields;else field.value=value;}catch(_){if(field.type!=='object')field.value=undefined;}};
      }else{
        const v=bind(el('input'));v.type=['number','integer'].includes(field.type)?'number':'text';v.step=field.type==='integer'?'1':'any';v.value=rawValues.get(field)??field.value??'';v.placeholder=fieldExample(field,path);globalThis.CFDInput?.bind(v,{type:field.type,nullable:field.nullable===true});
        if(rawValues.has(field))v.value=rawValues.get(field);
        v.oninput=()=>{rawValues.set(field,v.value);try{field.value=globalThis.CFDInput?CFDInput.parseValue(v.value,field.type,{nullable:field.nullable===true}):v.value;}catch(_){field.value=undefined;}};
      }
      if(rawValues.has(field))queueMicrotask(()=>{for(const v of container.querySelectorAll('input,textarea'))globalThis.CFDInput?.check(v);});
      return container;
    }
    function visible(field,path){if(searchQuery){const text=[fieldLabel(field,path),[...path,field.key].join('.'),field.description||''].join(' ');if(!(globalThis.CFDSettings?.matchesSearch?CFDSettings.matchesSearch(searchQuery,text,field.unit||'',field.type==='object'?'':JSON.stringify(field.value)):text.toLowerCase().includes(searchQuery.toLowerCase()))&&!(field.type==='object'&&field.fields.some(f=>visible(f,[...path,field.key]))))return false;return true;}return !!elementDraft||spatialPath([...path,field.key])||structure||showOptional||['required','conditional'].includes(fieldStatus(field,path));}
    function rowFor(field,path,host,display=field){
      const box=el('div',null,'fc-field'),row=el('div',null,'fc-row'),caption=el('div',null,'fc-caption'),status=fieldStatus(display,path.slice(0,-1));box.dataset.fieldPath=path.join('.');caption.title=path.join('.');const title=el('span',fieldLabel(display,path));if(display.label)title.setAttribute('translate','no');caption.append(title);
      if(status==='required')caption.append(el('span','필수','fc-badge'));if(display.description)caption.append(el('small',display.description));else if(display.key==='type'&&path[0]==='boundary_conditions')caption.append(el('small','경계에서 값을 지정하는 방식 · fixedValue는 지정값 사용'));
      row.append(caption);box.append(row);host.append(box);return {box,row};
    }
    function renderFields(fields,host,path=[]){
      const modelOptions=fields.find(f=>f.key==='model_options'&&f.type==='array'&&f.value?.length&&f.value.every(v=>typeof v==='string'))?.value;const columns=!structure?tableColumns(fields):[];if(columns.length&&columns.some(f=>visible(f,path)))propertyTable(columns,fields,host,path);
      for(const field of fields){
        if(columns.includes(field)||(!structure&&modelOptions&&field.key==='model_options'&&fields.some(f=>f.key==='model')))continue;if(!structure&&field.key.startsWith('_'))continue;if(!visible(field,path))continue;if(path[0]==='geometry'&&field.key==='source'&&!field.value)continue;const p=[...path,field.key];
        if(structure){
          const box=el('div',null,'fc-field'),row=el('div',null,'fc-structure-row');box.dataset.fieldPath=p.join('.');box.append(row);host.append(box);
          const entry=(caption,node)=>{const label=el('label',caption);node.setAttribute('aria-label',p.join('.')+' '+caption);label.append(node);row.append(label);return node;};
          const name=entry('표시 이름',el('input'));name.maxLength=160;name.value=field.label||fieldLabel(field);name.oninput=()=>field.label=name.value;
          const key=entry('JSON 키',el('input'));key.value=field.key;key.required=true;key.maxLength=80;key.disabled=field.readonly===true;key.oninput=()=>field.key=key.value;
          const type=entry('입력 형식',el('select'));for(const t of types)type.append(new Option(typeLabels[t],t));type.value=field.type;type.disabled=field.readonly===true;type.onchange=()=>{field.type=type.value;rawValues.delete(field);delete field.fields;delete field.value;field.nullable=true;if(field.type==='object')field.fields=[];else field.value={string:'',number:null,integer:null,boolean:null,array:[],null:null}[field.type];render();};
          const unit=entry('단위',el('input'));unit.value=field.unit||'';unit.disabled=field.readonly===true;unit.oninput=()=>field.unit=unit.value;
          const remove=button('삭제',()=>{fields.splice(fields.indexOf(field),1);render();});remove.disabled=field.readonly===true;row.append(remove);
          if(field.type==='object'){renderFields(field.fields,box,p);box.append(button('항목 추가',()=>{adding={fields,path:p};render();}));}
          else if(!schemaOnly)box.append(control(field,p));continue;
        }
        const valueField=field.type==='object'&&field.fields.every(f=>['value','unit','label','description'].includes(f.key))&&field.fields.find(f=>f.key==='value'),unitField=field.type==='object'&&field.fields.find(f=>f.key==='unit'),vector=field.type==='object'&&['x','y','z'].every(k=>field.fields.some(f=>f.key===k));
        if(field.type==='object'&&!valueField&&!vector){if(field.fields.length===1&&field.fields[0].type==='object'&&fieldLabel(field.fields[0])===fieldLabel(field)){renderFields(field.fields,host,p);continue;}const group=el('fieldset',null,'fc-section');const legend=el('legend',fieldLabel(field));legend.append(button('JSON',()=>openJSON(p)));group.append(legend);host.append(group);renderFields(field.fields,group,p);if(!readonly&&!field.readonly)group.append(button('항목 추가',()=>{adding={fields:field.fields,path:p};render();}));continue;}
        const {row}=rowFor(field,p,host);const unit=unitField?.value||field.unit||globalThis.CFDSettings?.fieldInfo?.(p,config)?.unit||parameterUnits[field.key]||'';
        if(vector){const controls=el('div',null,'fc-control'),group=el('div',null,'fc-vector');for(const axis of ['x','y','z']){const f=field.fields.find(x=>x.key===axis),label=el('label',axis.toUpperCase());label.append(control(f,[...p,axis]));group.append(label);}controls.append(group);if(unit)controls.append(el('span',unit,'fc-unit'));row.append(controls);}
        else {const controls=control(valueField||field,valueField?[...p,'value']:p,field.key==='model'?modelOptions:null);if(unit)controls.append(el('span',unit,'fc-unit'));row.append(controls);}
      }
    }
    function renderAdd(host){
      if(!adding)return;const panel=el('section',null,'fc-add'),grid=el('div',null,'fc-add-grid');panel.append(el('h3','항목 추가'),grid);
      const entry=(text,node)=>{const label=el('label',text);node.setAttribute('aria-label',text);label.append(node);grid.append(label);return node;};
      const name=entry('표시 이름',el('input')),key=entry('JSON 키',el('input')),type=entry('입력할 내용',el('select'));key.value=newField(adding.fields).key;
      for(const [value,label]of Object.entries(typeLabels).filter(([k])=>k!=='null'))type.append(new Option(label,value));type.value='number';
      const unit=entry('단위',el('input'));unit.placeholder='m, s, kg 등';const help=el('p',null,'fc-hint'),examples={number:'소수를 포함한 수치 · 예: 0.5',integer:'개수와 횟수 · 예: 10',string:'이름이나 경로 · 예: fluid',boolean:'기능 사용 또는 사용 안 함',object:'여러 항목을 하나로 묶는 그룹',array:'여러 값의 목록 · + 버튼으로 항목 추가'};const refresh=()=>help.textContent=examples[type.value];type.onchange=refresh;refresh();panel.append(help);
      const buttons=el('div',null,'fc-actions');buttons.append(button('취소',()=>{adding=null;render();}),button('추가',()=>guarded(()=>{if(!name.value.trim())throw Error('표시 이름을 입력하세요');const field={key:key.value.trim(),label:name.value.trim(),type:type.value,unit:unit.value.trim(),nullable:true,...(type.value==='object'?{fields:[]}:{value:{number:null,integer:null,string:'',boolean:null,array:[]}[type.value]})};toConfig({version:1,fields:[...adding.fields,field]});adding.fields.push(field);selected=adding.path[0]||field.key;showOptional=true;adding=null;render();})));panel.append(buttons);host.prepend(panel);
    }
    function render(){
      const priorNav=body.querySelector('.fc-nav'),navScroll=priorNav?.scrollTop||0;
      const priorMain=body.querySelector('.fc-main'),mainScroll=priorMain?.scrollTop||0,viewKey=elementId||selected;
      const keepMain=body.dataset.viewKey===viewKey;
      try{
      body.replaceChildren();jsonButton.setAttribute('aria-pressed',String(dialog.classList.contains('fc-json-open')));structureButton.setAttribute('aria-pressed',String(structure));

      const layout=el('div',null,'fc-layout'),nav=el('nav',null,'fc-nav'),main=el('main',null,'fc-main');nav.setAttribute('aria-label','Config 분류');layout.append(nav,main);body.append(layout);
      const search=el('input');search.placeholder='Config 검색';search.setAttribute('aria-label','Config 검색');search.value=searchQuery;search.style.cssText='width:100%;box-sizing:border-box;margin-bottom:10px';search.oninput=()=>guarded(()=>{commitJSON();searchQuery=search.value;const focus=search.selectionStart;render();const next=body.querySelector('[aria-label="Config 검색"]');next.focus({preventScroll:true});next.setSelectionRange(focus,focus);});nav.append(search);
      const groups=draft.fields.filter(f=>!f.key.startsWith('_')&&!['schema','schema_version'].includes(f.key));if(!groups.some(f=>f.key===selected)&&!customSections.some(f=>f.key===selected))selected=customSections[0]?.key||groups[0]?.key||'';
      for(const entry of customSections){const b=button(entry.title,()=>guarded(()=>{commitJSON();elementId=null;selected=entry.key;render();}));b.setAttribute('aria-current',String(!elementId&&selected===entry.key));nav.append(b);}
      const partEntries=sp.elements(toConfig(draft)),ownedRoots=new Set(partEntries.filter(e=>e.path.length===1).map(e=>e.path[0]));
      if(partEntries.some(e=>e.path[0]==='tank')&&partEntries.some(e=>e.path[0]==='dielectric_fluid')&&partEntries.some(e=>e.path[0]==='water'))ownedRoots.add('layers');
      if(partEntries.some(e=>e.path[0]==='heater'&&e.path[1]==='cpus'))ownedRoots.add('heater');
      const componentOwners=new Map(),commonRoots=new Set(['run','numerics','mesh','termination','outputs','probes','probes_mm','conditions']);
      for(const entry of partEntries)for(const path of [...sp.partBindings(toConfig(draft),entry.path),...(Array.isArray(entry.value.config_bindings)?entry.value.config_bindings:[])])if(Array.isArray(path)&&path.length===1&&!commonRoots.has(path[0])&&draft.fields.some(f=>f.key===path[0])){ownedRoots.add(path[0]);if(!componentOwners.has(path[0]))componentOwners.set(path[0],entry.id);}
      if(!elementId&&ownedRoots.has(selected))elementId=componentOwners.get(selected)||partEntries.find(x=>x.path[0]===selected)?.id||partEntries[0]?.id;
      for(const field of groups.filter(f=>!ownedRoots.has(f.key))){const b=button(fieldLabel(field),()=>guarded(()=>{commitJSON();elementId=null;selected=field.key;adding=null;render();}));b.setAttribute('aria-current',String(!elementId&&selected===field.key));b.title=field.key;if(field.label)b.setAttribute('translate','no');nav.append(b);}
      const sceneList=el('section',null,'fc-element-list');sceneList.append(el('h4','형상 및 계산 영역'));
      const entries=sp.elements(toConfig(draft));for(const entry of entries){const b=button(entry.label,()=>selectElement(entry.id));b.title=entry.label;b.dataset.elementId=entry.id;b.setAttribute('translate','no');b.setAttribute('aria-current',String(elementId===entry.id));sceneList.append(b);}if(!readonly)sceneList.append(button('+ 요소',addElement));nav.prepend(sceneList);
      if(elementId&&!entries.some(x=>x.id===elementId)){elementId=null;elementDraft=null;elementPath=null;}
      const optional=el('label',null,'fc-filter'),toggle=el('input');toggle.type='checkbox';toggle.checked=showOptional;toggle.onchange=()=>guarded(()=>{commitJSON();showOptional=toggle.checked;selected='';render();});optional.append(toggle,el('span','전체 항목'));nav.append(optional);
      if(!valuesOnly&&!readonly)nav.append(button('항목 추가',()=>guarded(()=>{commitJSON();adding={fields:draft.fields,path:[]};render();})));
      if(searchQuery){elementDraft=null;elementPath=null;for(const custom of customSections)if(custom.matches?.(searchQuery,currentConfig()))custom.render(main,controller);for(const field of groups)renderFields([field],main);schedulePreview();return;}
      const custom=!elementId&&customSections.find(s=>s.key===selected);if(custom){custom.render(main,controller);schedulePreview();return;}
      const entry=entries.find(x=>x.id===elementId);if(entry){renderElement(main,entry);renderAdd(main);schedulePreview();return;}
      const field=draft.fields.find(f=>f.key===selected);if(field){const heading=el('div',null,'fc-titlebar');heading.append(el('h3',fieldLabel(field)));if(!readonly&&field.type==='object'&&(!valuesOnly||!field.fields.length))heading.append(button('항목 추가',()=>guarded(()=>{commitJSON();adding={fields:field.fields,path:[field.key]};render();})));heading.append(button('JSON',()=>openJSON([field.key])));main.append(heading);if(field.type==='object')renderFields(field.fields,main,[field.key]);else renderFields([field],main);}
      if(!field)main.append(el('p','표시할 입력 항목이 없습니다 · 전체 항목을 확인하세요','fc-empty'));
      renderAdd(main);schedulePreview();
      }finally{const nav=body.querySelector('.fc-nav'),main=body.querySelector('.fc-main');if(nav)nav.scrollTop=navScroll;if(main&&keepMain)main.scrollTop=mainScroll;body.dataset.viewKey=elementId||selected;}
    }
    const controller={dialog,toolbar,actions,body,getConfig:()=>{if(jsonDirty)throw Error('JSON 저장 또는 취소를 선택하세요');globalThis.CFDInput?.assertValid(body);const value=currentConfig();validateTables(value);return value;},setConfig:value=>{commitJSON();draft=fromConfig(value,draft);elementId=null;render();if(dialog.classList.contains('fc-json-open'))loadJSON();},mutate:fn=>{commitJSON();const value=toConfig(draft);fn(value);draft=fromConfig(value,draft);schedulePreview();},render,openJSON,close:()=>dialog.close()};
    if(onMount)onMount(controller);
    const save=button(submitLabel,async()=>{if(saving)return;save.disabled=true;let locks=[];try{commitJSON();if(schemaOnly)draft=blankDefinition(draft);const value=toConfig(draft);validateTables(value);if(!schemaOnly&&!form?.definition_only){const issue=sp.runnerGeometryIssue(value);if(issue)throw Error(issue);}saving=true;locks=[...dialog.children].map(node=>[node,node.inert]);for(const [node]of locks)node.inert=true;await onSave(value,clone(draft));dialog.close();}catch(e){error.textContent=e.message;if(elementId&&!elementDraft)render();}finally{saving=false;for(const [node,locked]of locks)node.inert=locked;save.disabled=false;}});save.classList.add('pri');
    actions.append(button(readonly?'닫기':'취소',()=>dialog.close()));if(!readonly)actions.append(save);else if(onClone)actions.append(button('이 Config로 새 Case',()=>{const value=toConfig(draft);dialog.close();onClone(value);}));
    dialog.oncancel=event=>{if(saving)event.preventDefault();};dialog.onclose=()=>{closed=true;previewVersion++;clearTimeout(previewTimer);cleanPreview?.();dialog.remove();};render();document.body.append(dialog);dialog.showModal();schedulePreview();return controller;

  }
  function blankComponents(value){
    if(Array.isArray(value))return [];
    if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([key,item])=>[key,['name','label','description','unit','type','model','method','model_options'].includes(key)||key.startsWith('_')?clone(item):blankComponents(item)]));
    return typeof value==='string'?'':null;
  }
  function blankDefinition(schema){const copy=clone(schema);copy.spatial_version=1;const visit=(fields,path=[])=>{for(const field of fields){const p=[...path,field.key];if(field.key==='properties'&&field.type==='object'&&field.fields.every(f=>f.type==='object'&&f.fields.some(v=>v.key==='type')&&f.fields.some(v=>v.key==='value')))continue;if(spatialPath(p))continue;if(field.type==='object')visit(field.fields,p);else if(!field.readonly){field.nullable=true;field.value=field.type==='array'?[]:field.type==='string'?'':null;}}};visit(copy.fields);const config=toConfig(copy);for(const entry of spatialAPI().elements(config)){if(entry.value.components)entry.value.components=blankComponents(entry.value.components);for(const property of Object.values(entry.value.properties||{}))if(property&&typeof property==='object'&&Object.hasOwn(property,'value')&&typeof property.type==='string')property.value=property.type==='array'?[]:property.type==='string'?'':null;}return fromConfig(config,copy);}

  const api={importedSchema,tableColumns,validateTables,materialProfile,materialCatalog,validateValueEdits,fromConfig,toConfig,newField,blankDefinition,fieldLabel,fieldStatus,open};if(typeof module!=='undefined'&&module.exports)module.exports=api;else window.CFDFormConfig=api;
})();
