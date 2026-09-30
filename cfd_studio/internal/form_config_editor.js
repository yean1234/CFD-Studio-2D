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
      return Object.entries(object).map(([key,value])=>{const old=prior.find(f=>f.key===key),actual=kind(value),type=old?.nullable&&actual==='null'?old.type:old?.type==='number'&&actual==='integer'?'number':actual;return {key,type,unit:['value','x','y','z'].includes(key)&&typeof object.unit==='string'?object.unit:(old?.unit||''),...(old?.nullable?{nullable:true}:{}),...(old?.readonly?{readonly:true}:{}),...Object.fromEntries(['label','description'].filter(k=>typeof old?.[k]==='string').map(k=>[k,old[k]])),...(typeof old?.required==='boolean'?{required:old.required}:{}),...(type==='object'?{fields:fields(value,old?.fields,depth+1)}:{value:clone(value)})};});
    }
    const schema={version:1,spatial_version:1,fields:fields(config,previous?.fields)};toConfig(schema);return schema;
  }
  function toConfig(schema){
    if(schema?.version!==1)throw Error('Config schema version must be 1');let count=0;
    function checkJSON(v,depth){if(depth>16)throw Error('Config nesting exceeds 16 levels');if(typeof v==='number'&&!Number.isFinite(v))throw Error('Config numbers must be finite');if(Array.isArray(v)){if(v.length>10000)throw Error('Config array is too large');for(const x of v)checkJSON(x,depth+1);}else if(v&&typeof v==='object')for(const [k,x] of Object.entries(v)){if(forbidden.has(k))throw Error('Reserved Config Key: '+k);checkJSON(x,depth+1);}}
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
  const labels={power:'발열량',voltage:'전압',electric_potential:'전위',conductivity:'전기전도도',shape:'기하 형상',min:'최소 좌표',max:'최대 좌표',min_m:'최소 좌표',max_m:'최대 좌표',center:'중심 좌표',radius:'반지름',height:'높이',axis:'중심축',role:'영역 역할',config_bindings:'물리 설정 연결',heater:'열원',total_W:'총 발열량',geometry_spec:'저장고 형상',loading:'적재 배치',tank:'수조 형상',board:'보드 형상',coil:'코일 형상',silo:'사일로 형상',analysis:'해석 정보',geometry:'형상',mesh:'격자',materials:'재료 물성',physics:'물리 모델',initial_conditions:'초기 조건',boundary_conditions:'경계조건',numerics:'계산 방법',termination:'종료 조건',outputs:'결과 저장',fluids:'유체',fluid:'유체',solid:'고체',fields:'물리량',source:'파일 경로',fluid_regions:'유체 영역',solid_regions:'고체 영역',regions:'영역',interfaces:'계면',generator:'격자 생성기',cell_size:'격자 크기',refinement_regions:'국부 세분화 영역',name:'이름',state:'상태',density:'밀도',kinematic_viscosity:'동점성계수',heat_capacity:'비열',thermal_conductivity:'열전도율',thermal_expansion:'열팽창계수',reference_temperature:'기준 온도',transport_model:'수송 모델',thermophysical_properties:'열물성 모델',thermoType:'열물성 구성',mixture:'혼합물',transport:'수송 특성',thermo:'열역학 모델',equationOfState:'상태방정식',specie:'성분',energy:'에너지',U:'속도',p:'압력',p_rgh:'중력 보정 압력',T:'온도',inlet:'유입 경계',outlet:'유출 경계',wall:'벽면 경계',far_field:'원방 경계',body:'물체 표면',mesh_patch:'격자 경계 이름',type:'종류',value:'값',unit:'단위',x:'X',y:'Y',z:'Z',algorithm:'계산 알고리즘',schemes:'이산화 방법',linear_solvers:'선형 방정식 풀이',controls:'반복 계산',time_step:'계산 시간간격',max_time_step:'최대 시간간격',max_courant:'최대 Courant 수',adjust_time_step:'시간간격 자동 조절',pressure_reference:'압력 기준',cell:'기준 셀 번호',nCorrectors:'압력 보정 횟수',nOuterCorrectors:'외부 반복 횟수',nNonOrthogonalCorrectors:'비직교 보정 횟수',nAlphaCorr:'상분율 보정 횟수',nAlphaSubCycles:'상분율 세부 계산 횟수',subcycles:'세부 계산 횟수',phase_fraction:'상분율 계산',method:'계산 기법',coefficients:'추가 계수',model:'모델',motion:'격자 움직임',radiation:'복사',sources:'추가 소스항',gravity:'중력 가속도',surface_tension:'표면장력',pairs:'상 연결',phase_transfer:'상간 전달',flow_regime:'유동 모델',turbulence:'난류',initial_fields:'난류 초기값',boundary_fields:'난류 경계조건',delta:'필터 폭 모델',model_options:'모델 선택지',mode:'종료 방식',end_time:'종료 물리시간',max_time:'최대 계산 시간',max_iterations:'최대 반복 횟수',sustain_steps:'기준 유지 횟수',residual_targets:'잔차 수렴 기준',saved_frames:'저장 프레임 수',include_initial_frame:'초기 프레임 포함',write_interval:'결과 저장 간격',probes:'관측 위치',thermal_interfaces:'열전달 접합면',solid_temperature:'고체 초기 온도',scalar_transport:'스칼라 수송',field_name:'물리량 이름',diffusivity:'확산계수',initial_value:'초기값',porous_regions:'다공성 영역',solver:'솔버',time_mode:'시간 방식',choices:'설문 응답',form_generator:'양식 생성 방식',ddtSchemes:'시간 이산화',gradSchemes:'기울기 이산화',divSchemes:'대류항 이산화',laplacianSchemes:'확산항 이산화',interpolationSchemes:'보간 방법',snGradSchemes:'면 법선 기울기',Pr:'Prandtl 수',Prt:'난류 Prandtl 수',k:'난류 운동에너지',epsilon:'난류 소산율',omega:'비소산율'};
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
  function open({config={},schema=null,onSave,onValidate=null,title='Config',schemaOnly=false,valuesOnly=false,readonly=false,submitLabel='저장',customSections=[],onMount=null,onClone=null,form=null}){
    let searchQuery='';
    let draft=schemaOnly&&schema?clone(schema):fromConfig(config,schema),mode='fields',structure=false,showOptional=false,selected='';
    const rawValues=new WeakMap();toConfig(draft);
    const el=(tag,text,cls)=>{const x=document.createElement(tag);if(text!=null)x.textContent=text;if(cls)x.className=cls;return x;};
    const button=(text,fn)=>{const x=el('button',text,'btn');x.type='button';x.onclick=fn;return x;};
    if(!document.getElementById('formConfigStyle')){const style=el('style');style.id='formConfigStyle';style.textContent=`
.fc-dialog{width:min(1120px,96vw);max-width:1120px;height:min(850px,92vh);max-height:92vh;padding:22px;border:1px solid var(--line);border-radius:14px;background:var(--card,var(--page));color:var(--text);box-sizing:border-box}.fc-dialog [hidden]{display:none!important}.fc-dialog[open]{display:flex;flex-direction:column;gap:12px}.fc-dialog::backdrop{background:#000a}.fc-header,.fc-actions,.fc-toolbar,.fc-modes,.fc-tools{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.fc-header h2{font-size:18px;margin:0}.fc-toolbar{justify-content:space-between}.fc-tools{margin-left:auto}.fc-body{flex:1;min-height:0;overflow:auto}.fc-layout{display:grid;grid-template-columns:180px minmax(0,1fr);height:100%;min-height:0}.fc-nav{overflow:auto;padding-right:12px;border-right:1px solid var(--line)}.fc-nav .btn{width:100%;text-align:left;margin-bottom:6px;white-space:normal}.fc-nav [aria-current=true],.fc-toolbar [aria-pressed=true]{border-color:var(--accent,#579eff);background:#3987e51a}.fc-main{overflow:auto;padding:0 14px;min-width:0}.fc-main h3{font-size:15px;margin:0 0 12px}.fc-note,.fc-hint{color:var(--muted);font-size:12px;line-height:1.5;margin:0}.fc-filter{margin-bottom:12px;display:flex;align-items:center;gap:6px;font-size:12px}.fc-field{padding:10px 0;border-bottom:1px solid var(--line);min-width:0}.fc-row{display:grid;grid-template-columns:180px minmax(180px,1fr);gap:12px;align-items:center}.fc-caption{font-size:13px;min-width:0}.fc-caption small{display:block;font-size:11px;color:var(--muted);margin-top:4px}.fc-badge{font-size:10px;color:var(--accent,#579eff);margin-left:7px}.fc-control{display:flex;gap:8px;align-items:center;min-width:0}.fc-unit{font-size:11px;color:var(--muted);white-space:nowrap}.fc-field input,.fc-field select,.fc-field textarea,.fc-json,.fc-add input,.fc-add select{box-sizing:border-box;width:100%;min-width:0;background:var(--page);color:var(--text);border:1px solid var(--line);border-radius:7px;padding:8px;font:inherit;font-size:13px;min-height:34px}.fc-field textarea,.fc-json{font:12px Consolas,monospace;resize:vertical}.fc-field output{overflow-wrap:anywhere;font-size:12px}.fc-vector{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;flex:1}.fc-vector label{display:flex;align-items:center;gap:4px;font-size:11px}.fc-section{margin:14px 0 0;border:1px solid var(--line);border-radius:10px;padding:0 12px 10px;min-width:0}.fc-section legend{font-size:12px;padding:0 6px;color:var(--muted)}.fc-section>.fc-field:last-child{border-bottom:0}.fc-structure-row{display:grid;grid-template-columns:1fr 1fr 130px 90px auto;gap:8px;align-items:end}.fc-structure-row label{font-size:11px;color:var(--muted);display:flex;flex-direction:column;gap:5px}.fc-json{height:100%;min-height:260px;box-sizing:border-box;width:100%;background:var(--page);color:var(--text);border:1px solid var(--line);border-radius:10px;padding:14px}.fc-error{color:var(--red,#ef8989);font-size:12px;margin:0;white-space:pre-wrap}.fc-error:empty{display:none}.fc-actions{justify-content:flex-end}.fc-validation{max-height:90px;overflow:auto;font-size:12px;border-top:1px solid var(--line);padding-top:8px}.fc-validation p{margin:4px 0}.fc-add{padding:12px;border:1px solid var(--accent,#579eff);border-radius:10px;margin-bottom:12px}.fc-add-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.fc-add label{font-size:12px;display:flex;flex-direction:column;gap:5px}.fc-add .fc-actions{margin-top:10px}.fc-empty{padding:25px;color:var(--muted);font-size:13px}.fc-main .fc-titlebar{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}.fc-main .fc-titlebar h3{margin:0}@media(max-width:760px){.fc-layout{grid-template-columns:135px minmax(0,1fr)}.fc-row{grid-template-columns:1fr;gap:6px}.fc-structure-row{grid-template-columns:1fr 1fr}.fc-dialog{padding:14px}.fc-main{padding-right:0}.fc-add-grid{grid-template-columns:1fr}}

.fc-dialog{width:min(1640px,97vw);max-width:1640px}.fc-workspace{display:grid;grid-template-columns:minmax(570px,1.35fr) minmax(310px,1fr);gap:16px;flex:1;min-height:0}.fc-layout{grid-template-columns:160px minmax(0,1fr)}.fc-row{grid-template-columns:minmax(100px,135px) minmax(100px,1fr);gap:10px}.fc-body{height:100%}.fc-preview{min-height:0;min-width:0;border:1px solid var(--line);border-radius:12px;overflow:hidden;display:flex;flex-direction:column;background:#111315}.fc-preview-header{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:12px;border-bottom:1px solid var(--line);font-size:13px}.fc-preview-host{position:relative;flex:1;min-height:180px;overflow:hidden}.fc-preview-host canvas{display:block;width:100%;height:100%}.fc-preview-note{margin:0;padding:10px;font-size:11px;color:var(--muted);max-height:68px;overflow:auto}.fc-element-list{border-bottom:1px solid var(--line);margin-bottom:12px;padding-bottom:8px}.fc-element-list h4{font-size:12px;margin:0 0 10px;color:var(--muted)}.fc-section>select{width:100%;padding:8px;background:var(--page);color:var(--ink);border:1px solid var(--line);border-radius:7px;margin:10px 0}.sp-tags{position:absolute;inset:0;pointer-events:none;overflow:hidden}.sp-tag{position:absolute;transform:translate(-50%,-50%);pointer-events:auto;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;background:#191d23e8;color:#fff;border:1px solid #677487;border-radius:6px;padding:5px 8px;font-family:inherit;font-size:11px;cursor:pointer}.sp-tag[aria-pressed=true]{border-color:#73adff;background:#193e69;z-index:2}@media(max-width:980px){.fc-workspace{grid-template-columns:minmax(430px,1fr) minmax(240px,.75fr)}.fc-layout{grid-template-columns:130px minmax(0,1fr)}.fc-row{grid-template-columns:1fr}.fc-dialog{padding:14px}}@media(max-width:740px){.fc-workspace{grid-template-columns:1fr;grid-template-rows:minmax(220px,1fr) 240px;overflow:auto}.fc-main{padding-right:4px}}

.fc-dialog{width:min(1240px,96vw);max-width:1800px;transition:width .28s ease,transform .28s ease}.fc-dialog.fc-json-open{width:min(1800px,98vw)}.fc-workspace{grid-template-columns:minmax(0,1.3fr) minmax(0,1fr) minmax(0,0fr);gap:0;transition:grid-template-columns .28s ease}.fc-preview{margin-left:14px}.fc-json-open .fc-workspace{grid-template-columns:minmax(0,1.35fr) minmax(0,1fr) minmax(0,1fr)}.fc-json-pane{min-width:0;overflow:hidden;display:flex;flex-direction:column;gap:10px;opacity:0;transform:translateX(25px);transition:opacity .28s,transform .28s;margin-left:0}.fc-json-open .fc-json-pane{margin-left:14px;opacity:1;transform:translateX(0);border:1px solid var(--line);border-radius:12px;padding:0 10px 10px}.fc-json-pane .fc-json{flex:1;min-height:160px;resize:none}.fc-json-open .fc-row{grid-template-columns:1fr;gap:5px}.fc-nav{min-width:0}.fc-json-open .fc-layout{grid-template-columns:125px minmax(0,1fr)}.fc-case-controls{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.fc-preset-load{display:flex;align-items:center;gap:8px;width:340px;min-width:0}.fc-preset-load>button{flex:none}.fc-preset-load>select{flex:1;width:auto!important}.fc-preset-load>div{flex:1;min-width:0}.fc-output-options{display:flex;flex-wrap:wrap;gap:10px}.fc-output-options label{display:flex;align-items:center;gap:5px}.fc-output-options input{width:auto;min-height:0}.fc-nav>input{padding:8px;border-radius:7px;border:1px solid var(--line);background:var(--page);color:var(--ink)}.fc-section legend .btn{margin-left:8px;padding:3px 7px;font-size:10px}.fc-case-controls label{display:flex;align-items:center;gap:6px;font-size:12px}.fc-case-controls input:not([type=checkbox]),.fc-case-controls select,.fc-custom input,.fc-custom textarea,.fc-custom select{padding:8px;border:1px solid var(--line);border-radius:7px;background:var(--page);color:var(--ink);font:inherit;min-width:0}.fc-custom{font-size:13px}.fc-custom label{display:grid;gap:7px;margin:16px 0}.fc-custom p{font-size:12px;color:var(--muted);line-height:1.6}.fc-custom textarea{width:100%;box-sizing:border-box}.fc-json-pane textarea{user-select:text}@media(max-width:740px){.fc-workspace,.fc-json-open .fc-workspace{display:flex;flex-direction:column;overflow:auto}.fc-body{min-height:300px}.fc-preview{min-height:240px;margin:12px 0}.fc-json-pane{display:none}.fc-json-open .fc-json-pane{display:flex;min-height:300px;margin:0}.fc-dialog{transition:none}}@media(prefers-reduced-motion:reduce){.fc-dialog,.fc-workspace,.fc-json-pane{transition:none;transform:none}}
`;document.head.append(style);}
    const dialog=el('dialog',null,'fc-dialog'+(schemaOnly?' fc-schema-only':'')),header=el('div',null,'fc-header');header.append(el('h2',title));
    const toolbar=el('div',null,'fc-toolbar'),body=el('div',null,'fc-body'),error=el('p',null,'fc-error'),actions=el('div',null,'fc-actions');error.setAttribute('role','alert');
    let saving=false,jsonPath=null,jsonDirty=false,jsonBase='',jsonArea,adding=null,elementId=null,elementDraft=null,elementPath=null,cleanPreview=null,previewTimer=null,previewVersion=0,closed=false,cameraState=null,lastScene='';
    const commitJSON=()=>{if(jsonDirty)throw Error('JSON 저장 또는 취소를 선택하세요');globalThis.CFDInput?.assertValid(body);flushElement();toConfig(draft);};
    const guarded=fn=>{try{error.textContent='';fn();}catch(e){error.textContent=e.message;}};
    const jsonButton=button('전체 JSON',()=>openJSON(null));
    const structureButton=button('구조 편집',()=>guarded(()=>{if(valuesOnly)return;commitJSON();structure=!structure;mode='fields';render();}));structureButton.hidden=valuesOnly||readonly;
    const spatial=button('JSON',()=>openJSON(['geometry'].filter(k=>draft.fields.some(f=>f.key===k)).length?['geometry']:null));
    const upload=el('input');upload.type='file';upload.accept='.json,application/json';upload.hidden=true;
    upload.onchange=async()=>{const file=upload.files[0];if(!file)return;try{if(file.size>1000000)throw Error('JSON file must be under 1 MB');const parsed=JSON.parse(await file.text()),next=schemaOnly?parsed:fromConfig(parsed,draft);toConfig(next);draft=next;mode='fields';error.textContent='';render();}catch(e){error.textContent=e.message;}upload.value='';};
    const modes=el('div',null,'fc-modes'),tools=el('div',null,'fc-tools');const importButton=button('JSON 가져오기',()=>upload.click());importButton.hidden=readonly;tools.append(structureButton,jsonButton,importButton,button('JSON 내보내기',()=>guarded(()=>{commitJSON();const a=el('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(schemaOnly?blankDefinition(draft):toConfig(draft),null,2)],{type:'application/json'}));a.download=schemaOnly?'cfd-template.json':'cfd-config.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);})),upload);toolbar.append(modes,tools);
    const hint=el('p',readonly?'실행 시점의 입력 기록 · 변경하려면 이 Config로 새 Case 선택':schemaOnly?'초기 형상과 입력 양식 정의 · 물성 및 운전값은 프로젝트에서 입력':'필수 항목과 조건부 항목을 먼저 입력하세요','fc-note');
    const workspace=el('div',null,'fc-workspace'),preview=el('aside',null,'fc-preview'),previewHeader=el('div',null,'fc-preview-header'),previewHost=el('div',null,'fc-preview-host'),previewNote=el('p',null,'fc-preview-note');
    previewHeader.append(el('strong','3D 형상'),spatial);preview.append(previewHeader,previewHost,previewNote);workspace.append(body,preview);
    const jsonPane=el('aside',null,'fc-json-pane'),jsonHeader=el('div',null,'fc-preview-header'),jsonTitle=el('strong','JSON'),jsonActions=el('div',null,'fc-actions');
    jsonArea=el('textarea',null,'fc-json');jsonArea.spellcheck=false;jsonArea.setAttribute('aria-label','선택 항목 JSON');jsonArea.readOnly=readonly;jsonArea.oninput=()=>{jsonDirty=jsonArea.value!==jsonBase;jsonSave.disabled=!jsonDirty;body.inert=jsonDirty;};
    const jsonSave=button('JSON 저장',()=>guarded(()=>{
      const parsed=JSON.parse(jsonArea.value);flushElement();
      if(schemaOnly){const next=jsonPath?clone(draft):parsed;if(jsonPath){const field=next.fields.find(f=>f.key===jsonPath[0]);if(!field)throw Error('JSON 항목을 찾을 수 없습니다');if(parsed.key!==field.key)throw Error('선택한 항목의 JSON 키는 유지하세요');next.fields[next.fields.indexOf(field)]=parsed;}toConfig(next);draft=next;}
      else{const next=toConfig(draft);if(jsonPath)writePath(next,jsonPath,parsed);else {fromConfig(parsed);for(const key of Object.keys(next))delete next[key];Object.assign(next,parsed);}validateValueEdits(toConfig(draft),next);draft=fromConfig(next,draft);}
      jsonDirty=false;body.inert=false;jsonBase=jsonArea.value;jsonSave.disabled=true;render();loadJSON();schedulePreview();
    }));jsonSave.classList.add('pri');jsonSave.hidden=readonly;jsonSave.disabled=true;
    const dismissJSON=()=>{jsonButton.focus({preventScroll:true});jsonDirty=false;body.inert=false;dialog.classList.remove('fc-json-open');jsonPane.inert=true;jsonPane.setAttribute('aria-hidden','true');};
    jsonActions.append(button(readonly?'닫기':'취소',dismissJSON),jsonSave);jsonHeader.append(jsonTitle);jsonPane.append(jsonHeader,jsonArea,jsonActions);jsonPane.inert=true;jsonPane.setAttribute('aria-hidden','true');workspace.append(jsonPane);
    function loadJSON(){const value=schemaOnly?(jsonPath?draft.fields.find(f=>f.key===jsonPath[0]):draft):(jsonPath?sp.at(toConfig(draft),jsonPath):toConfig(draft));jsonBase=JSON.stringify(value,null,2);jsonArea.value=jsonBase;jsonDirty=false;jsonSave.disabled=true;}
    function openJSON(path){guarded(()=>{commitJSON();jsonPath=schemaOnly&&path?[path[0]]:path;jsonTitle.textContent=(jsonPath?jsonPath.map(key=>fieldLabel({key})).join(' / '):'전체 Config')+' JSON';loadJSON();dialog.classList.add('fc-json-open');jsonPane.inert=false;jsonPane.setAttribute('aria-hidden','false');jsonArea.focus({preventScroll:true});});}

    dialog.append(header,toolbar,hint,workspace,error,actions);hint.title='선택 항목의 기존값은 유지됩니다 · 전체 항목에서 확인';
    if(onValidate){const report=el('section',null,'fc-validation');report.setAttribute('aria-live','polite');report.textContent='입력 검사로 누락 항목을 확인할 수 있습니다';workspace.after(report);const check=button('입력 검사',async()=>{check.disabled=true;try{commitJSON();const result=await onValidate(toConfig(draft));report.replaceChildren(el('strong',result.missing_count?'필수 입력 '+result.missing_count+'개 확인 필요':'정의된 필수 입력 작성 완료'));const list=el('ul');for(const issue of result.issues){const item=el('li'),link=button(issue.path.map(key=>fieldLabel({key})).join(' / '),()=>{selected=issue.path[0];showOptional=true;mode='fields';render();const target=[...body.querySelectorAll('[data-field-path]')].find(n=>n.dataset.fieldPath===issue.path.join('.'));target?.scrollIntoView({block:'center'});target?.querySelector('input,select,textarea')?.focus();});link.title=issue.path.join('.');item.append(link,' · ',issue.message);list.append(item);}for(const note of result.model_review||[])list.append(el('li',note));report.append(list);}catch(e){report.textContent=e.message;}finally{check.disabled=false;}});actions.append(check);}
    const sp=spatialAPI();
    function writePath(obj,path,value){const parent=sp.at(obj,path.slice(0,-1));if(!parent)throw Error('선택한 요소를 찾을 수 없습니다');parent[path.at(-1)]=value;}
    function currentConfig(){const value=toConfig(draft);if(elementDraft&&elementPath)writePath(value,elementPath,toConfig(elementDraft));return value;}
    function flushElement(){if(!elementDraft)return;draft=fromConfig(currentConfig(),draft);elementDraft=null;elementPath=null;}
    function selectElement(id){guarded(()=>{commitJSON();elementId=id;cleanPreview?.select(id);mode='fields';structure=false;render();});}
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
    const syncInputs=()=>{schedulePreview();if(dialog.classList.contains('fc-json-open')&&!jsonDirty){try{const value=currentConfig(),definition=schemaOnly?fromConfig(value,draft):null;const part=schemaOnly?(jsonPath?definition.fields.find(f=>f.key===jsonPath[0]):definition):(jsonPath?sp.at(value,jsonPath):value);jsonBase=JSON.stringify(part,null,2);jsonArea.value=jsonBase;}catch(_){}}};body.addEventListener('input',syncInputs);body.addEventListener('change',syncInputs);
    function schemaAt(path){let field,fields=draft.fields;for(const key of path){field=fields?.find(f=>f.key===key);fields=field?.fields;}return field;}
    function bindingOptions(){
      const out=[];const walk=(fields,path=[])=>{for(const field of fields){const p=[...path,field.key];if(field.key.startsWith('_'))continue;if(field.type==='object'){out.push({path:p,label:p.map(key=>fieldLabel({key})).join(' / ')});if(p.length<4)walk(field.fields,p);}}};
      for(const f of draft.fields)if(['materials','initial_conditions','boundary_conditions','physics','heater','dielectric_fluid','water','air','solid'].includes(f.key))walk([f]);
      return out;
    }
    function renderElement(main,entry){
      elementPath=entry.path;elementDraft=fromConfig(entry.value);for(const f of elementDraft.fields)if(['radius','height'].includes(f.key)&&f.type==='null'){f.type='number';f.nullable=true;}if(!readonly&&!elementDraft.fields.some(f=>f.key==='name'))elementDraft.fields.unshift({key:'name',type:'string',value:entry.label});const heading=el('div',null,'fc-titlebar'),title=el('h3',entry.label);title.setAttribute('translate','no');heading.append(title);
      heading.append(button('JSON',()=>openJSON(entry.path)));if(!readonly)heading.append(button('요소 삭제',()=>guarded(()=>{commitJSON();const value=toConfig(draft),parent=sp.at(value,entry.path.slice(0,-1)),key=entry.path.at(-1);if(Array.isArray(parent))parent.splice(key,1);else delete parent[key];draft=fromConfig(value,draft);elementId=null;render();})));main.append(heading);
      const settings=el('div',null,'fc-field'),roleLabel=el('label','영역 역할'),role=el('select');role.setAttribute('aria-label','영역 역할');
      for(const [key,label]of [['','미지정'],['fluid','유체 영역'],['solid','고체 영역'],['boundary','경계면'],['heat_source','발열체']])role.append(new Option(label,key));
      role.disabled=readonly;role.value=entry.value.role||'';role.onchange=()=>{let field=elementDraft.fields.find(f=>f.key==='role');if(!field){field={key:'role',type:'string',value:''};elementDraft.fields.push(field);}field.value=role.value;};roleLabel.append(role);settings.append(roleLabel);main.append(settings);
      renderFields(elementDraft.fields.filter(f=>!['role','config_bindings'].includes(f.key)),main,entry.path);
      const bindingBox=el('section',null,'fc-section');bindingBox.append(el('h3','물리 설정 연결'));main.append(bindingBox);
      const options=bindingOptions(),bindings=Array.isArray(entry.value.config_bindings)?clone(entry.value.config_bindings):(entry.path[0]==='heater'&&schemaAt(['heater','total_W'])?[['heater','total_W']]:[]);
      const storeBindings=()=>{let f=elementDraft.fields.find(f=>f.key==='config_bindings');if(!f){f={key:'config_bindings',type:'array',value:[]};elementDraft.fields.push(f);}f.value=clone(bindings);};
      for(const path of bindings){const field=Array.isArray(path)?schemaAt(path):null,group=el('fieldset',null,'fc-section');group.append(el('legend',Array.isArray(path)?path.map(key=>fieldLabel({key})).join(' / '):'연결 오류'));bindingBox.append(group);
        if(!readonly)group.append(button('연결 해제',()=>guarded(()=>{bindings.splice(bindings.indexOf(path),1);storeBindings();commitJSON();render();})));
        if(field){renderFields([field],group,path.slice(0,-1));}else group.append(el('p','연결된 Config 항목이 없습니다','fc-error'));
      }
      const select=el('select');select.setAttribute('aria-label','연결할 Config 항목');select.append(new Option('Config 항목 선택',''));for(const option of options){const id=JSON.stringify(option.path);if(!bindings.some(p=>JSON.stringify(p)===id))select.append(new Option(option.label,id));}
      select.onchange=()=>guarded(()=>{if(!select.value)return;bindings.push(JSON.parse(select.value));storeBindings();commitJSON();render();});if(!readonly)bindingBox.append(select);
      bindingBox.append(el('p','연결한 Config 원본 항목을 편집 · 영역 역할만으로 솔버 설정이 자동 생성되지는 않음','fc-note'));
    }
    function addElement(){guarded(()=>{commitJSON();const value=toConfig(draft);value.geometry??={};value.geometry.regions??=[];const regions=value.geometry.regions;
      let n=1;const occupied=sp.elements(value).map(x=>x.label);while(occupied.includes('region_'+n))n++;const name='region_'+n;
      const element={name,role:'',shape:'box',unit:'m',min:[0,0,0],max:[null,null,null],config_bindings:[]};
      let path;if(Array.isArray(regions)){path=['geometry','regions',regions.length];regions.push(element);}else{let key=name;while(Object.hasOwn(regions,key))key+='_';regions[key]=element;path=['geometry','regions',key];}
      draft=fromConfig(value,draft);elementId=sp.pathId(path);mode='fields';structure=false;render();
    });}
    function control(field,path){
      const container=el('div',null,'fc-control'),name=path.join('.');
      const bind=node=>{node.setAttribute('aria-label',fieldLabel(field,path));node.dataset.configPath=name;container.append(node);return node;};
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
      else if(globalThis.CFDSettings?.choicesFor(field.key).length&&['string','number','integer'].includes(field.type)){
        const select=bind(el('select')),choices=globalThis.CFDSettings.choicesFor(field.key);if(!choices.some(o=>o.value===field.value))choices.push({value:field.value,label:String(field.value??'선택')});for(const choice of choices)select.append(new Option(choice.label,String(choice.value)));select.value=String(field.value);select.onchange=()=>field.value=choices.find(c=>String(c.value)===select.value).value;
      }
      else if(spatialPath(path)&&['shape','axis','unit'].includes(field.key)&&field.type==='string'){
        const v=bind(el('select')),choices=field.key==='shape'?['box','sphere','cylinder']:field.key==='axis'?['x','y','z']:['m','cm','mm'];if(field.value&&!choices.includes(field.value))choices.unshift(field.value);v.append(new Option('선택',''));for(const choice of choices)v.append(new Option(({box:'직육면체',sphere:'구',cylinder:'원기둥'})[choice]||choice,choice));v.value=field.value||'';
        v.onchange=()=>{field.value=v.value;if(field.key==='shape'&&elementDraft){const add=(key,value)=>{if(!elementDraft.fields.some(f=>f.key===key))elementDraft.fields.push(value===null?{key,type:'number',nullable:true,value:null}:fromConfig({[key]:value}).fields[0]);};if(v.value==='box'){add('min',[0,0,0]);add('max',[null,null,null]);}else{add('center',[0,0,0]);add('radius',null);if(v.value==='cylinder'){add('height',null);add('axis','z');}}commitJSON();render();}};
      }
      else if(spatialPath(path)&&field.type==='array'&&['min','max','center','min_m','max_m'].includes(field.key)&&field.value?.length===3){
        const axes=el('div',null,'fc-vector');container.append(axes);for(let i=0;i<3;i++){const label=el('label','XYZ'[i]),v=el('input');v.type='number';v.step='any';v.value=field.value[i]??'';v.placeholder='ex) 0.0';v.setAttribute('aria-label',fieldLabel(field,path)+' '+'XYZ'[i]);v.dataset.configPath=name+'.'+i;globalThis.CFDInput?.bind(v,{type:'number',nullable:true});v.oninput=()=>{try{field.value[i]=CFDInput.parseValue(v.value,'number',{nullable:true});}catch(_){field.value[i]=undefined;}};label.append(v);axes.append(label);}
      }
      else if(field.type==='boolean'){const v=bind(el('select'));if(field.nullable)v.append(new Option('선택',''));v.append(new Option('사용','true'),new Option('사용 안 함','false'));v.value=field.value===null?'':String(field.value);v.onchange=()=>field.value=v.value===''?null:v.value==='true';}
      else if(field.type==='null')bind(el('output','미지정'));
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
      const badge={required:'필수',conditional:'조건부',optional:'선택 항목',fixed:'자동 설정'}[status];caption.append(el('span',badge,'fc-badge'));if(display.description)caption.append(el('small',display.description));else if(display.key==='type'&&path[0]==='boundary_conditions')caption.append(el('small','경계에서 값을 지정하는 방식 · fixedValue는 지정값 사용'));
      row.append(caption);box.append(row);host.append(box);return {box,row};
    }
    function renderFields(fields,host,path=[]){
      for(const field of fields){
        if(!structure&&field.key.startsWith('_'))continue;if(!visible(field,path))continue;if(path[0]==='geometry'&&field.key==='source'&&!field.value)continue;const p=[...path,field.key];
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
        const valueField=field.type==='object'&&field.fields.every(f=>['value','unit'].includes(f.key))&&field.fields.find(f=>f.key==='value'),unitField=field.type==='object'&&field.fields.find(f=>f.key==='unit'),vector=field.type==='object'&&['x','y','z'].every(k=>field.fields.some(f=>f.key===k));
        if(field.type==='object'&&field.fields.length&&!valueField&&!vector){if(field.fields.length===1&&field.fields[0].type==='object'&&fieldLabel(field.fields[0])===fieldLabel(field)){renderFields(field.fields,host,p);continue;}const group=el('fieldset',null,'fc-section');const legend=el('legend',fieldLabel(field));legend.append(button('JSON',()=>openJSON(p)));group.append(legend);host.append(group);renderFields(field.fields,group,p);continue;}
        const {row}=rowFor(field,p,host);const unit=unitField?.value||field.unit||globalThis.CFDSettings?.fieldInfo?.(p,config)?.unit||'';
        if(vector){const controls=el('div',null,'fc-control'),group=el('div',null,'fc-vector');for(const axis of ['x','y','z']){const f=field.fields.find(x=>x.key===axis),label=el('label',axis.toUpperCase());label.append(control(f,[...p,axis]));group.append(label);}controls.append(group);if(unit)controls.append(el('span',unit,'fc-unit'));row.append(controls);}
        else {const controls=control(valueField||field,valueField?[...p,'value']:p);if(unit)controls.append(el('span',unit,'fc-unit'));row.append(controls);}
      }
    }
    function renderAdd(host){
      if(!adding)return;const panel=el('section',null,'fc-add'),grid=el('div',null,'fc-add-grid');panel.append(el('h3','항목 추가'),grid);
      const entry=(text,node)=>{const label=el('label',text);node.setAttribute('aria-label',text);label.append(node);grid.append(label);return node;};
      const name=entry('표시 이름',el('input')),key=entry('JSON 키',el('input')),type=entry('입력할 내용',el('select'));key.value=newField(adding.fields).key;
      for(const [value,label]of Object.entries(typeLabels).filter(([k])=>k!=='null'))type.append(new Option(label,value));type.value='number';
      const unit=entry('단위',el('input'));unit.placeholder='m, s, kg 등';const help=el('p',null,'fc-hint'),examples={number:'소수를 포함한 수치 · 예: 0.5',integer:'개수와 횟수 · 예: 10',string:'이름이나 경로 · 예: fluid',boolean:'기능 사용 또는 사용 안 함',object:'여러 항목을 하나로 묶는 그룹',array:'여러 값의 목록 · JSON 배열로 입력'};const refresh=()=>help.textContent=examples[type.value];type.onchange=refresh;refresh();panel.append(help);
      const buttons=el('div',null,'fc-actions');buttons.append(button('취소',()=>{adding=null;render();}),button('추가',()=>guarded(()=>{if(!name.value.trim())throw Error('표시 이름을 입력하세요');const field={key:key.value.trim(),label:name.value.trim(),type:type.value,unit:unit.value.trim(),nullable:true,...(type.value==='object'?{fields:[]}:{value:{number:null,integer:null,string:'',boolean:null,array:[]}[type.value]})};toConfig({version:1,fields:[...adding.fields,field]});adding.fields.push(field);selected=adding.path[0]||field.key;showOptional=true;adding=null;render();})));panel.append(buttons);host.prepend(panel);
    }
    function render(){
      body.replaceChildren();jsonButton.setAttribute('aria-pressed',String(dialog.classList.contains('fc-json-open')));structureButton.setAttribute('aria-pressed',String(structure));

      const layout=el('div',null,'fc-layout'),nav=el('nav',null,'fc-nav'),main=el('main',null,'fc-main');nav.setAttribute('aria-label','Config 분류');layout.append(nav,main);body.append(layout);
      const search=el('input');search.placeholder='Config 검색';search.setAttribute('aria-label','Config 검색');search.value=searchQuery;search.style.cssText='width:100%;box-sizing:border-box;margin-bottom:10px';search.oninput=()=>guarded(()=>{commitJSON();searchQuery=search.value;const focus=search.selectionStart;render();const next=body.querySelector('[aria-label="Config 검색"]');next.focus();next.setSelectionRange(focus,focus);});nav.append(search);
      const groups=draft.fields.filter(f=>!f.key.startsWith('_')&&!['schema','schema_version'].includes(f.key));if(!groups.some(f=>f.key===selected)&&!customSections.some(f=>f.key===selected))selected=customSections[0]?.key||groups[0]?.key||'';
      for(const entry of customSections){const b=button(entry.title,()=>guarded(()=>{commitJSON();elementId=null;selected=entry.key;render();}));b.setAttribute('aria-current',String(!elementId&&selected===entry.key));nav.append(b);}
      for(const field of groups){const b=button(fieldLabel(field),()=>guarded(()=>{commitJSON();elementId=null;selected=field.key;adding=null;render();}));b.setAttribute('aria-current',String(!elementId&&selected===field.key));b.title=field.key;if(field.label)b.setAttribute('translate','no');nav.append(b);}
      const sceneList=el('section',null,'fc-element-list');sceneList.append(el('h4','형상 및 계산 영역'));
      const entries=sp.elements(toConfig(draft));for(const entry of entries){const b=button(entry.label,()=>selectElement(entry.id));b.dataset.elementId=entry.id;b.setAttribute('translate','no');b.setAttribute('aria-current',String(elementId===entry.id));sceneList.append(b);}if(!readonly)sceneList.append(button('+ 요소',addElement));nav.prepend(sceneList);
      if(elementId&&!entries.some(x=>x.id===elementId)){elementId=null;elementDraft=null;elementPath=null;}
      const optional=el('label',null,'fc-filter'),toggle=el('input');toggle.type='checkbox';toggle.checked=showOptional;toggle.onchange=()=>guarded(()=>{commitJSON();showOptional=toggle.checked;selected='';render();});optional.append(toggle,el('span','전체 항목'));nav.append(optional);
      if(!valuesOnly&&!readonly)nav.append(button('항목 추가',()=>guarded(()=>{commitJSON();adding={fields:draft.fields,path:[]};render();})));
      if(searchQuery){elementDraft=null;elementPath=null;for(const custom of customSections)if(custom.matches?.(searchQuery,currentConfig()))custom.render(main,controller);for(const field of groups)renderFields([field],main);schedulePreview();return;}
      const custom=!elementId&&customSections.find(s=>s.key===selected);if(custom){custom.render(main,controller);schedulePreview();return;}
      const entry=entries.find(x=>x.id===elementId);if(entry){renderElement(main,entry);schedulePreview();return;}
      const field=draft.fields.find(f=>f.key===selected);if(field){const heading=el('div',null,'fc-titlebar');heading.append(el('h3',fieldLabel(field)));if(!valuesOnly&&!readonly&&field.type==='object')heading.append(button('항목 추가',()=>guarded(()=>{commitJSON();adding={fields:field.fields,path:[field.key]};render();})));heading.append(button('JSON',()=>openJSON([field.key])));main.append(heading);if(field.type==='object')renderFields(field.fields,main,[field.key]);else renderFields([field],main);}
      if(!field)main.append(el('p','표시할 입력 항목이 없습니다 · 전체 항목을 확인하세요','fc-empty'));
      renderAdd(main);schedulePreview();
    }
    const controller={dialog,toolbar,actions,body,getConfig:()=>{commitJSON();return toConfig(draft);},setConfig:value=>{commitJSON();draft=fromConfig(value,draft);elementId=null;render();if(dialog.classList.contains('fc-json-open'))loadJSON();},mutate:fn=>{commitJSON();const value=toConfig(draft);fn(value);draft=fromConfig(value,draft);schedulePreview();},render,openJSON,close:()=>dialog.close()};
    if(onMount)onMount(controller);
    const save=button(submitLabel,async()=>{if(saving)return;save.disabled=true;let locks=[];try{commitJSON();if(schemaOnly)draft=blankDefinition(draft);const value=toConfig(draft);saving=true;locks=[...dialog.children].map(node=>[node,node.inert]);for(const [node]of locks)node.inert=true;await onSave(value,clone(draft));dialog.close();}catch(e){error.textContent=e.message;}finally{saving=false;for(const [node,locked]of locks)node.inert=locked;save.disabled=false;}});save.classList.add('pri');
    actions.append(button(readonly?'닫기':'취소',()=>dialog.close()));if(!readonly)actions.append(save);else if(onClone)actions.append(button('이 Config로 새 Case',()=>{const value=toConfig(draft);dialog.close();onClone(value);}));
    dialog.oncancel=event=>{if(saving)event.preventDefault();};dialog.onclose=()=>{closed=true;previewVersion++;clearTimeout(previewTimer);cleanPreview?.();dialog.remove();};render();document.body.append(dialog);dialog.showModal();schedulePreview();return controller;

  }
  function blankDefinition(schema){const copy=clone(schema);copy.spatial_version=1;const visit=(fields,path=[])=>{for(const field of fields){const p=[...path,field.key];if(spatialPath(p))continue;if(field.type==='object')visit(field.fields,p);else if(!field.readonly){field.nullable=true;field.value=field.type==='array'?[]:field.type==='string'?'':null;}}};visit(copy.fields);toConfig(copy);return copy;}

  const api={validateValueEdits,fromConfig,toConfig,newField,blankDefinition,fieldLabel,fieldStatus,open};if(typeof module!=='undefined'&&module.exports)module.exports=api;else window.CFDFormConfig=api;
})();
