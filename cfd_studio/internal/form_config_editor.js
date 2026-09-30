/* Config schema editor. Field keys and units are user-owned, never translated. */
(() => {
  const types=['string','number','integer','boolean','object','array','null'];
  const forbidden=new Set(['__proto__','prototype','constructor']);
  const clone=x=>structuredClone(x);
  const kind=value=>value===null?'null':Array.isArray(value)?'array':typeof value==='object'?'object':typeof value==='number'?(Number.isInteger(value)?'integer':'number'):typeof value;
  function fromConfig(config,previous=null){
    if(!config||typeof config!=='object'||Array.isArray(config))throw Error('Config must be a JSON object');
    function fields(object,prior=[],depth=0){
      if(depth>16)throw Error('Config nesting exceeds 16 levels');
      return Object.entries(object).map(([key,value])=>{const old=prior.find(f=>f.key===key),actual=kind(value),type=old?.nullable&&actual==='null'?old.type:old?.type==='number'&&actual==='integer'?'number':actual;return {key,type,unit:['value','x','y','z'].includes(key)&&typeof object.unit==='string'?object.unit:(old?.unit||''),...(old?.nullable?{nullable:true}:{}),...(old?.readonly?{readonly:true}:{}),...Object.fromEntries(['label','description'].filter(k=>typeof old?.[k]==='string').map(k=>[k,old[k]])),...(typeof old?.required==='boolean'?{required:old.required}:{}),...(type==='object'?{fields:fields(value,old?.fields,depth+1)}:{value:clone(value)})};});
    }
    const schema={version:1,fields:fields(config,previous?.fields)};toConfig(schema);return schema;
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
  const labels={geometry_spec:'저장고 형상',loading:'적재 배치',tank:'수조 형상',board:'보드 형상',coil:'코일 형상',silo:'사일로 형상',analysis:'해석 정보',geometry:'형상',mesh:'격자',materials:'재료 물성',physics:'물리 모델',initial_conditions:'초기 조건',boundary_conditions:'경계조건',numerics:'계산 방법',termination:'종료 조건',outputs:'결과 저장',fluids:'유체',fluid:'유체',solid:'고체',fields:'물리량',source:'파일 경로',fluid_regions:'유체 영역',solid_regions:'고체 영역',regions:'영역',interfaces:'계면',generator:'격자 생성기',cell_size:'격자 크기',refinement_regions:'국부 세분화 영역',name:'이름',state:'상태',density:'밀도',kinematic_viscosity:'동점성계수',heat_capacity:'비열',thermal_conductivity:'열전도율',thermal_expansion:'열팽창계수',reference_temperature:'기준 온도',transport_model:'수송 모델',thermophysical_properties:'열물성 모델',thermoType:'열물성 구성',mixture:'혼합물',transport:'수송 특성',thermo:'열역학 모델',equationOfState:'상태방정식',specie:'성분',energy:'에너지',U:'속도',p:'압력',p_rgh:'중력 보정 압력',T:'온도',inlet:'유입 경계',outlet:'유출 경계',wall:'벽면 경계',far_field:'원방 경계',body:'물체 표면',mesh_patch:'격자 경계 이름',type:'모델 종류',value:'값',unit:'단위',x:'X',y:'Y',z:'Z',algorithm:'계산 알고리즘',schemes:'이산화 방법',linear_solvers:'선형 방정식 풀이',controls:'반복 계산',time_step:'계산 시간간격',max_time_step:'최대 시간간격',max_courant:'최대 Courant 수',adjust_time_step:'시간간격 자동 조절',pressure_reference:'압력 기준',cell:'기준 셀 번호',nCorrectors:'압력 보정 횟수',nOuterCorrectors:'외부 반복 횟수',nNonOrthogonalCorrectors:'비직교 보정 횟수',nAlphaCorr:'상분율 보정 횟수',nAlphaSubCycles:'상분율 세부 계산 횟수',subcycles:'세부 계산 횟수',phase_fraction:'상분율 계산',method:'계산 기법',coefficients:'추가 계수',model:'모델',motion:'격자 움직임',radiation:'복사',sources:'추가 소스항',gravity:'중력 가속도',surface_tension:'표면장력',pairs:'상 연결',phase_transfer:'상간 전달',flow_regime:'유동 모델',turbulence:'난류',initial_fields:'난류 초기값',boundary_fields:'난류 경계조건',delta:'필터 폭 모델',model_options:'모델 선택지',mode:'종료 방식',end_time:'종료 물리시간',max_time:'최대 계산 시간',max_iterations:'최대 반복 횟수',sustain_steps:'기준 유지 횟수',residual_targets:'잔차 수렴 기준',saved_frames:'저장 프레임 수',include_initial_frame:'초기 프레임 포함',write_interval:'결과 저장 간격',probes:'관측 위치',thermal_interfaces:'열전달 접합면',solid_temperature:'고체 초기 온도',scalar_transport:'스칼라 수송',field_name:'물리량 이름',diffusivity:'확산계수',initial_value:'초기값',porous_regions:'다공성 영역',solver:'솔버',time_mode:'시간 방식',choices:'설문 응답',form_generator:'양식 생성 방식',ddtSchemes:'시간 이산화',gradSchemes:'기울기 이산화',divSchemes:'대류항 이산화',laplacianSchemes:'확산항 이산화',interpolationSchemes:'보간 방법',snGradSchemes:'면 법선 기울기',Pr:'Prandtl 수',Prt:'난류 Prandtl 수',k:'난류 운동에너지',epsilon:'난류 소산율',omega:'비소산율'};
  const typeLabels={string:'문자',number:'숫자',integer:'정수',boolean:'사용 여부',object:'항목 묶음',array:'목록',null:'값 없음'};
  function fieldLabel(field){return field.label||labels[field.key]||(/^phase_\d+$/.test(field.key)?'유체 '+field.key.split('_')[1]:/^alpha\.phase_\d+$/.test(field.key)?'상분율 '+field.key.split('_')[1]:(globalThis.CFDSettings?.fieldInfo?.([field.key],{})?.title||field.key));}
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
  function open({config={},schema=null,onSave,onValidate=null,title='Config',schemaOnly=false,valuesOnly=false}){
    let draft=schema?clone(schema):fromConfig(config),mode='fields',structure=false,showOptional=false,selected='';
    const rawValues=new WeakMap();toConfig(draft);
    const el=(tag,text,cls)=>{const x=document.createElement(tag);if(text!=null)x.textContent=text;if(cls)x.className=cls;return x;};
    const button=(text,fn)=>{const x=el('button',text,'btn');x.type='button';x.onclick=fn;return x;};
    if(!document.getElementById('formConfigStyle')){const style=el('style');style.id='formConfigStyle';style.textContent=`
.fc-dialog{width:min(1120px,96vw);max-width:1120px;height:min(850px,92vh);max-height:92vh;padding:22px;border:1px solid var(--line);border-radius:14px;background:var(--card,var(--page));color:var(--text);box-sizing:border-box}.fc-dialog [hidden]{display:none!important}.fc-dialog[open]{display:flex;flex-direction:column;gap:12px}.fc-dialog::backdrop{background:#000a}.fc-header,.fc-actions,.fc-toolbar,.fc-modes,.fc-tools{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.fc-header h2{font-size:18px;margin:0}.fc-toolbar{justify-content:space-between}.fc-tools{margin-left:auto}.fc-body{flex:1;min-height:0;overflow:auto}.fc-layout{display:grid;grid-template-columns:180px minmax(0,1fr);height:100%;min-height:0}.fc-nav{overflow:auto;padding-right:12px;border-right:1px solid var(--line)}.fc-nav .btn{width:100%;text-align:left;margin-bottom:6px;white-space:normal}.fc-nav [aria-current=true],.fc-toolbar [aria-pressed=true]{border-color:var(--accent,#579eff);background:#3987e51a}.fc-main{overflow:auto;padding:0 14px;min-width:0}.fc-main h3{font-size:15px;margin:0 0 12px}.fc-note,.fc-hint{color:var(--muted);font-size:12px;line-height:1.5;margin:0}.fc-filter{display:flex;align-items:center;gap:6px;font-size:12px}.fc-field{padding:10px 0;border-bottom:1px solid var(--line);min-width:0}.fc-row{display:grid;grid-template-columns:180px minmax(180px,1fr);gap:12px;align-items:center}.fc-caption{font-size:13px;min-width:0}.fc-caption small{display:block;font-size:11px;color:var(--muted);margin-top:4px}.fc-badge{font-size:10px;color:var(--accent,#579eff);margin-left:7px}.fc-control{display:flex;gap:8px;align-items:center;min-width:0}.fc-unit{font-size:11px;color:var(--muted);white-space:nowrap}.fc-field input,.fc-field select,.fc-field textarea,.fc-json,.fc-add input,.fc-add select{box-sizing:border-box;width:100%;min-width:0;background:var(--page);color:var(--text);border:1px solid var(--line);border-radius:7px;padding:8px;font:inherit;font-size:13px;min-height:34px}.fc-field textarea,.fc-json{font:12px Consolas,monospace;resize:vertical}.fc-field output{overflow-wrap:anywhere;font-size:12px}.fc-vector{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;flex:1}.fc-vector label{display:flex;align-items:center;gap:4px;font-size:11px}.fc-section{margin:14px 0 0;border:1px solid var(--line);border-radius:10px;padding:0 12px 10px;min-width:0}.fc-section legend{font-size:12px;padding:0 6px;color:var(--muted)}.fc-section>.fc-field:last-child{border-bottom:0}.fc-structure-row{display:grid;grid-template-columns:1fr 1fr 130px 90px auto;gap:8px;align-items:end}.fc-structure-row label{font-size:11px;color:var(--muted);display:flex;flex-direction:column;gap:5px}.fc-json{height:100%;min-height:260px;box-sizing:border-box;width:100%;background:var(--page);color:var(--text);border:1px solid var(--line);border-radius:10px;padding:14px}.fc-error{color:var(--red,#ef8989);font-size:12px;margin:0;white-space:pre-wrap}.fc-error:empty{display:none}.fc-actions{justify-content:flex-end}.fc-validation{max-height:90px;overflow:auto;font-size:12px;border-top:1px solid var(--line);padding-top:8px}.fc-validation p{margin:4px 0}.fc-add{padding:12px;border:1px solid var(--accent,#579eff);border-radius:10px;margin-bottom:12px}.fc-add-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.fc-add label{font-size:12px;display:flex;flex-direction:column;gap:5px}.fc-add .fc-actions{margin-top:10px}.fc-empty{padding:25px;color:var(--muted);font-size:13px}.fc-main .fc-titlebar{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}.fc-main .fc-titlebar h3{margin:0}@media(max-width:760px){.fc-layout{grid-template-columns:135px minmax(0,1fr)}.fc-row{grid-template-columns:1fr;gap:6px}.fc-structure-row{grid-template-columns:1fr 1fr}.fc-dialog{padding:14px}.fc-main{padding-right:0}.fc-add-grid{grid-template-columns:1fr}}
`;document.head.append(style);}
    const dialog=el('dialog',null,'fc-dialog'+(schemaOnly?' fc-schema-only':'')),header=el('div',null,'fc-header');header.append(el('h2',title));
    const toolbar=el('div',null,'fc-toolbar'),body=el('div',null,'fc-body'),error=el('p',null,'fc-error'),actions=el('div',null,'fc-actions');error.setAttribute('role','alert');
    let jsonArea,adding=null;
    const commitJSON=()=>{globalThis.CFDInput?.assertValid(body);if(mode==='json'){const next=schemaOnly?JSON.parse(jsonArea.value):fromConfig(JSON.parse(jsonArea.value),draft);toConfig(next);draft=next;}else toConfig(draft);};
    const guarded=fn=>{try{error.textContent='';fn();}catch(e){error.textContent=e.message;}};
    const fieldsButton=button(schemaOnly?'입력 양식':'입력값',()=>guarded(()=>{commitJSON();mode='fields';render();}));
    const jsonButton=button('JSON',()=>guarded(()=>{commitJSON();mode='json';render();}));
    const structureButton=button('구조 편집',()=>guarded(()=>{if(valuesOnly)return;commitJSON();structure=!structure;mode='fields';render();}));structureButton.hidden=valuesOnly;
    const spatial=button('공간 JSON',()=>guarded(()=>{commitJSON();CFDSpatial.open({config:toConfig(draft),schema:draft,schemaOnly,onApply:(value,definition)=>{draft=definition||fromConfig(value,draft);mode='fields';render();}});}));
    const upload=el('input');upload.type='file';upload.accept='.json,application/json';upload.hidden=true;
    upload.onchange=async()=>{const file=upload.files[0];if(!file)return;try{if(file.size>1000000)throw Error('JSON file must be under 1 MB');const parsed=JSON.parse(await file.text()),next=schemaOnly?parsed:fromConfig(parsed,draft);toConfig(next);draft=next;mode='fields';error.textContent='';render();}catch(e){error.textContent=e.message;}upload.value='';};
    const modes=el('div',null,'fc-modes'),tools=el('div',null,'fc-tools');modes.append(fieldsButton);tools.append(structureButton,jsonButton,button('JSON 가져오기',()=>upload.click()),button('JSON 내보내기',()=>guarded(()=>{commitJSON();const a=el('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(schemaOnly?blankDefinition(draft):toConfig(draft),null,2)],{type:'application/json'}));a.download=schemaOnly?'cfd-template.json':'cfd-config.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);})),upload);toolbar.append(modes,tools);
    const hint=el('p',schemaOnly?'필수 입력 중심의 양식 · 실제 값은 프로젝트에서 입력':'필수 항목과 조건부 항목을 먼저 입력하세요','fc-note');
    dialog.append(header,toolbar,hint,body,error,actions);hint.title='선택 항목의 기존값은 유지됩니다 · 전체 항목에서 확인';
    if(onValidate){const report=el('section',null,'fc-validation');report.setAttribute('aria-live','polite');report.textContent='입력 검사로 누락 항목을 확인할 수 있습니다';body.after(report);const check=button('입력 검사',async()=>{check.disabled=true;try{commitJSON();const result=await onValidate(toConfig(draft));report.replaceChildren(el('strong',result.missing_count?'필수 입력 '+result.missing_count+'개 확인 필요':'정의된 필수 입력 작성 완료'));const list=el('ul');for(const issue of result.issues){const item=el('li'),link=button(issue.path.map(key=>fieldLabel({key})).join(' / '),()=>{selected=issue.path[0];showOptional=true;mode='fields';render();const target=[...body.querySelectorAll('[data-field-path]')].find(n=>n.dataset.fieldPath===issue.path.join('.'));target?.scrollIntoView({block:'center'});target?.querySelector('input,select,textarea')?.focus();});link.title=issue.path.join('.');item.append(link,' · ',issue.message);list.append(item);}for(const note of result.model_review||[])list.append(el('li',note));report.append(list);}catch(e){report.textContent=e.message;}finally{check.disabled=false;}});actions.append(check);}
    function control(field,path){
      const container=el('div',null,'fc-control'),name=path.join('.');
      const bind=node=>{node.setAttribute('aria-label',fieldLabel(field));node.dataset.configPath=name;container.append(node);return node;};
      if(field.readonly){const out=bind(el('output',typeof field.value==='object'?JSON.stringify(field.value):String(field.value??'')));out.setAttribute('translate','no');}
      else if(field.type==='boolean'){const v=bind(el('select'));if(field.nullable)v.append(new Option('선택',''));v.append(new Option('사용','true'),new Option('사용 안 함','false'));v.value=field.value===null?'':String(field.value);v.onchange=()=>field.value=v.value===''?null:v.value==='true';}
      else if(field.type==='null')bind(el('output','미지정'));
      else if(field.type==='array'||field.type==='object'){
        const v=bind(el('textarea'));v.rows=2;v.value=rawValues.get(field)??JSON.stringify(field.type==='object'?toConfig({version:1,fields:field.fields}):field.value,null,2);v.setAttribute('translate','no');globalThis.CFDInput?.bind(v,{type:field.type});
        v.oninput=()=>{rawValues.set(field,v.value);try{const value=globalThis.CFDInput?CFDInput.parseValue(v.value,field.type):JSON.parse(v.value);if(field.type==='object')field.fields=fromConfig(value,{fields:field.fields}).fields;else field.value=value;}catch(_){if(field.type!=='object')field.value=undefined;}};
      }else{
        const v=bind(el('input'));v.type=['number','integer'].includes(field.type)?'number':'text';v.step=field.type==='integer'?'1':'any';v.value=rawValues.get(field)??field.value??'';v.placeholder=field.type==='integer'?'정수 입력':field.type==='number'?'숫자 입력':'입력';globalThis.CFDInput?.bind(v,{type:field.type,nullable:field.nullable===true});
        if(rawValues.has(field))v.value=rawValues.get(field);
        v.oninput=()=>{rawValues.set(field,v.value);try{field.value=globalThis.CFDInput?CFDInput.parseValue(v.value,field.type,{nullable:field.nullable===true}):v.value;}catch(_){field.value=undefined;}};
      }
      if(rawValues.has(field))queueMicrotask(()=>{for(const v of container.querySelectorAll('input,textarea'))globalThis.CFDInput?.check(v);});
      return container;
    }
    function visible(field,path){return structure||showOptional||['required','conditional'].includes(fieldStatus(field,path));}
    function rowFor(field,path,host,display=field){
      const box=el('div',null,'fc-field'),row=el('div',null,'fc-row'),caption=el('div',null,'fc-caption'),status=fieldStatus(display,path.slice(0,-1));box.dataset.fieldPath=path.join('.');caption.title=path.join('.');const title=el('span',fieldLabel(display));if(display.label)title.setAttribute('translate','no');caption.append(title);
      const badge={required:'필수',conditional:'조건부',optional:'선택 항목',fixed:'자동 설정'}[status];caption.append(el('span',badge,'fc-badge'));if(display.description)caption.append(el('small',display.description));
      row.append(caption);box.append(row);host.append(box);return {box,row};
    }
    function renderFields(fields,host,path=[]){
      for(const field of fields){
        if(!visible(field,path))continue;const p=[...path,field.key];
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
        if(field.type==='object'&&field.fields.length&&!valueField&&!vector){if(field.fields.length===1&&field.fields[0].type==='object'&&fieldLabel(field.fields[0])===fieldLabel(field)){renderFields(field.fields,host,p);continue;}const group=el('fieldset',null,'fc-section');group.append(el('legend',fieldLabel(field)));host.append(group);renderFields(field.fields,group,p);continue;}
        const {row}=rowFor(field,p,host);const unit=unitField?.value||field.unit||globalThis.CFDSettings?.fieldInfo?.(p,config)?.unit||'';
        if(schemaOnly){const summary=el('div',null,'fc-control');summary.append(el('span',vector?'3축 숫자':typeLabels[valueField?.type||field.type]));if(unit)summary.append(el('span',unit,'fc-unit'));if(field.readonly)summary.append(control(field,p));row.append(summary);}
        else if(vector){const controls=el('div',null,'fc-control'),group=el('div',null,'fc-vector');for(const axis of ['x','y','z']){const f=field.fields.find(x=>x.key===axis),label=el('label',axis.toUpperCase());label.append(control(f,[...p,axis]));group.append(label);}controls.append(group);if(unit)controls.append(el('span',unit,'fc-unit'));row.append(controls);}
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
      body.replaceChildren();fieldsButton.setAttribute('aria-pressed',String(mode==='fields'));jsonButton.setAttribute('aria-pressed',String(mode==='json'));structureButton.setAttribute('aria-pressed',String(structure));
      if(mode==='json'){jsonArea=el('textarea',null,'fc-json');jsonArea.setAttribute('aria-label','Config JSON');jsonArea.spellcheck=false;globalThis.CFDInput?.bind(jsonArea,{type:'object'});jsonArea.value=JSON.stringify(schemaOnly?blankDefinition(draft):toConfig(draft),null,2);body.append(jsonArea);return;}
      const layout=el('div',null,'fc-layout'),nav=el('nav',null,'fc-nav'),main=el('main',null,'fc-main');nav.setAttribute('aria-label','Config 분류');layout.append(nav,main);body.append(layout);
      const groups=draft.fields.filter(f=>visible(f,[])||f.key===selected);if(!groups.some(f=>f.key===selected))selected=groups[0]?.key||'';
      for(const field of groups){const b=button(fieldLabel(field),()=>guarded(()=>{commitJSON();selected=field.key;adding=null;render();}));b.setAttribute('aria-current',String(selected===field.key));b.title=field.key;if(field.label)b.setAttribute('translate','no');nav.append(b);}
      const optional=el('label',null,'fc-filter'),toggle=el('input');toggle.type='checkbox';toggle.checked=showOptional;toggle.onchange=()=>guarded(()=>{commitJSON();showOptional=toggle.checked;selected='';render();});optional.append(toggle,el('span','전체 항목'));nav.append(optional);
      if(!valuesOnly)nav.append(button('항목 추가',()=>guarded(()=>{commitJSON();adding={fields:draft.fields,path:[]};render();})));
      const field=draft.fields.find(f=>f.key===selected);if(field){const heading=el('div',null,'fc-titlebar');heading.append(el('h3',fieldLabel(field)));if(['geometry','geometry_spec','tank','loading','board','coil','silo'].includes(field.key))heading.append(spatial);if(!valuesOnly&&field.type==='object')heading.append(button('항목 추가',()=>guarded(()=>{commitJSON();adding={fields:field.fields,path:[field.key]};render();})));main.append(heading);if(field.type==='object')renderFields(field.fields,main,[field.key]);else renderFields([field],main);}
      if(!field)main.append(el('p','표시할 입력 항목이 없습니다 · 전체 항목을 확인하세요','fc-empty'));
      renderAdd(main);
    }
    const save=button('적용',async()=>{save.disabled=true;try{commitJSON();if(schemaOnly)draft=blankDefinition(draft);const value=toConfig(draft);await onSave(value,clone(draft));dialog.close();}catch(e){error.textContent=e.message;}finally{save.disabled=false;}});save.classList.add('pri');actions.append(button('취소',()=>dialog.close()),save);
    dialog.onclose=()=>dialog.remove();render();document.body.append(dialog);dialog.showModal();
  }
  function blankDefinition(schema){const copy=clone(schema);const visit=fields=>{for(const field of fields){if(field.type==='object')visit(field.fields);else if(!field.readonly){field.nullable=true;field.value=field.type==='array'?[]:field.type==='string'?'':null;}}};visit(copy.fields);toConfig(copy);return copy;}
  const api={fromConfig,toConfig,newField,blankDefinition,fieldLabel,fieldStatus,open};if(typeof module!=='undefined'&&module.exports)module.exports=api;else window.CFDFormConfig=api;
})();
