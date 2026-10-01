/* Shared execution settings editor and immutable snapshot inspector. */
(() => {
  const names = {
    numerics:'계산 시간',run:'계산·출력',geometry_spec:'공간 형상',geometry:'공간 형상',tank:'수조',layers:'층 구성·초기 온도',board:'보드',heater:'발열',coil:'냉각 코일',
    loading:'영역 공통 속성',porous_mesh:'격자',coupled:'유동·열전달',initial:'초기 농도',temperature:'외기온 기록',dielectric_fluid:'하단 액체 물성',water:'상단 액체 물성',vapour:'증기 물성',phase_change:'상변화',mesh:'격자',probes_mm:'측정 위치',conditions:'실험 조건',provenance:'출처',assumptions:'가정',boundary_policy:'경계조건',published:'형상·물성',silo:'저장고·덕트',solver_controls:'솔버 제어',openfoam_mapping:'해석 모델',
    end_s:'종료시간',dt_s:'계산 간격',write_interval_s:'저장 간격',end_time_s:'종료시간',viz_interval_s:'화면 데이터 간격',max_dt_s:'최대 계산 간격',time_step_s:'계산 간격',time_step_mode:'시간 간격 방식',time_mode:'시간 간격 방식',processes:'CPU 프로세스 수',refinement:'격자 세분화',maximum_cells:'최대 셀 수',base_max_spacing_m:'기본 최대 격자 간격',length_m:'길이',width_m:'폭',eaves_m:'처마 높이',roof_rise_m:'지붕 높이',initial_temperature_C:'초기 실내 온도',porosity:'공극률',tortuosity:'굴곡도',blocks:'적재 블록',min_m:'최소 좌표',max_m:'최대 좌표',centre_m:'중심 좌표',sigma_m:'분포 폭',background_mg_m3:'배경 농도',gaussian_peak_mg_m3:'분포 최댓값',times_s:'시간',values_C:'외기온',permeability_m2:'투과도',solid_rhoCp_J_m3_K:'곡물 체적 열용량',bulk_conductivity_W_m_K:'유효 열전도도',envelope_h_W_m2_K:'외피 열전달계수',nu_m2_s:'동점성계수',rho_kg_m3:'밀도',cp_J_kg_K:'비열',cp_J_kgK:'비열',mu_Pa_s:'점성계수',kappa_W_mK:'열전도도',beta_1_K:'체적팽창계수',T_ref_C:'기준 온도',initial_k_m2_s2:'초기 난류 운동에너지',initial_epsilon_m2_s3:'초기 난류 소산율',Pr:'Prandtl 수',Prt:'난류 Prandtl 수',Sct:'난류 Schmidt 수',max_Co:'최대 Courant 수',turbulence:'난류 모델',advection_scheme:'이류 계산 방식',output_fields:'출력 항목',width_mm:'폭',depth_mm:'깊이',liquid_height_mm:'액체 높이',dielectric_mm:'하단 액체 높이',air_mm:'상단 공기층',init_T_dielectric_C:'하단 초기 온도',init_T_water_C:'상단 초기 온도',init_T_dielectric_top_C:'하단 액체 상부 온도',init_T_water_top_C:'상단 액체 상부 온도',total_W:'총 발열',flow_LPM:'냉각수 유량',Ta_C:'냉각수 입구 온도',UA_target_W_K:'목표 UA',h_W_m2K:'열전달계수',Tsat_C:'기화점',h_fg_J_kg:'잠열',molWeight:'분자량',evap_C:'증발 계수',cond_C:'응축 계수',dx_mm:'격자 간격',maxCo:'최대 Courant 수',maxAlphaCo:'최대 계면 Courant 수',cpus:'CPU 위치',manual_properties:'대표 물성',T_C:'온도',name:'이름',basis:'근거',evidence:'근거',unresolved:'미확정 항목',coordinate_basis:'좌표 기준',representation:'표현 방식',kind:'모델',id:'이름',model:'물성 모델',table:'물성표',properties:'물성',gas_boundary:'가스 경계',leakage:'누출',nx:'길이 방향 셀 수',ny_per_half:'반폭 셀 수',nz:'높이 방향 셀 수'
  };
  const enums = {time_mode:['fixed','adaptive'],time_step_mode:['fixed','adaptive'],advection_scheme:['upwind','bounded_high_order'],refinement:[1,2,4],turbulence:['kEpsilon'],output_fields:['bubble','phase','flow','therm','pressure','turbulence'],stop_mode:['fixed','converged']};
  const choices = {fixed:'고정',adaptive:'자동 안정',upwind:'1차 상류',bounded_high_order:'유계 고차',bubble:'기포',phase:'상분율',flow:'유속',therm:'온도',pressure:'압력',turbulence:'난류',converged:'수렴 도달'};
  const clone = value => structuredClone(value);
  const isReferenceKey = key => /(^|_)(provenance|source|sources|reference|references|citation|citations|evidence|basis|sha256)($|_)/i.test(String(key));
  function references(value,path=[]){
    if(!value||typeof value!=='object')return [];
    return Object.entries(value).flatMap(([key,item])=>{const p=[...path,Array.isArray(value)?Number(key):key];return isReferenceKey(key)?[{path:p,value:item}]:references(item,p);});
  }

  function kind(c){return c?.coupled&&c?.numerics?'warehouse':c?._해석유형==='grain_silo'?'grain_silo':c?.tank&&c?.dielectric_fluid?'immersion':'unsupported';}
  function parse(text){const c=JSON.parse(text);if(!c||Array.isArray(c)||typeof c!=='object')throw Error('설정 JSON 객체가 필요합니다');
    const check=v=>{if(v&&typeof v==='object')for(const [k,x] of Object.entries(v)){if(['__proto__','prototype','constructor'].includes(k))throw Error('허용되지 않는 설정 키');check(x);}};check(c);return c;}
  function validate(c){
    if(kind(c)==='unsupported')throw Error('이 설정은 조회만 지원합니다. 실행 가능한 기본 설정을 선택하세요.');
    const check=(v,path='')=>{if(v===null)throw Error(path+' 값을 입력하세요');if(typeof v==='number'&&!Number.isFinite(v))throw Error(path+' 숫자를 확인하세요');if(v&&typeof v==='object')for(const [k,x] of Object.entries(v)){if(isReferenceKey(k)||['unresolved','assumptions','study','solver_options','published_numerics'].includes(k))continue;check(x,path?path+'.'+k:k);}};check(c);
    const n=kind(c)==='warehouse'?c.numerics:c.run;
    const positive=(v,label)=>{if(typeof v!=='number'||!Number.isFinite(v)||v<=0)throw Error(label+'을 양수로 입력하세요');};
    if(!n)throw Error('계산 설정이 없습니다');
    const steady=kind(c)==='grain_silo'&&c.openfoam_mapping?.solver==='simpleFoam';
    const end=n.end_s??(steady?n.max_iterations:n.end_time_s),write=steady?n.write_interval_iterations:n.write_interval_s;
    positive(end,'종료값');positive(write,'저장 간격');const output=kind(c)==='immersion'?(n.viz_interval_s??write):write;positive(output,'결과 프레임 저장 간격');if(output>end)throw Error('결과 프레임 저장 간격은 종료값 이하여야 합니다');
    if(!steady)positive(n.dt_s??n.time_step_s??n.max_dt_s,'계산 간격');
    if(kind(c)==='warehouse'){
      if(n.dt_s>write)throw Error('계산 간격은 저장 간격 이하여야 합니다');
      if(Math.abs(end/write-Math.round(end/write))>1e-8)throw Error('종료시간은 저장 간격의 배수여야 합니다');
      if(!Number.isInteger(c.coupled.processes)||c.coupled.processes<1||c.coupled.processes>8)throw Error('CPU 프로세스 수는 1~8의 정수여야 합니다');
    }
    if(kind(c)==='immersion'){
      positive(c.mesh?.dx_mm,'격자 간격');
      if(!Array.isArray(n.output_fields)||!n.output_fields.length)throw Error('출력 항목을 하나 이상 선택하세요');
    }
    return c;
  }
  function terminationPaths(config){
    const model=kind(config),steady=model==='grain_silo'&&config.openfoam_mapping?.solver==='simpleFoam';
    if(model==='warehouse')return [['numerics','end_s']];
    if(['immersion','grain_silo'].includes(model))return [['run',steady?'max_iterations':'end_time_s'],['run','stop_mode']];
    return [];
  }
  function applyTermination(input){
    const c=clone(input),k=kind(c),n=c.numerics||c.run,steady=k==='grain_silo'&&c.openfoam_mapping?.solver==='simpleFoam';
    const stop=c._studio?.termination;if(!stop)return c;
    if(stop.mode==='convergence')throw Error('수렴 기준의 연속 유지 구간을 확인하는 실행기 연결이 없습니다');
    if(steady&&stop.mode==='time')throw Error('정상 해석에 물리시간 종료를 적용할 수 없습니다');
    if(!['time','frames'].includes(stop.mode))throw Error('종료 방식을 선택하세요');
    if(stop.mode==='frames'&&(!Number.isInteger(stop.frames)||stop.frames<1))throw Error('저장 프레임 수는 양의 정수여야 합니다');
    const value=stop.mode==='time'?stop.time_s:(steady?n.write_interval_iterations:k==='immersion'?(n.viz_interval_s??n.write_interval_s):n.write_interval_s)*(stop.frames-(stop.include_initial?1:0));
    if(!(value>0))throw Error('목표값을 확인하세요. 초기 프레임 포함 시 최소 2개가 필요합니다');
    n[k==='warehouse'?'end_s':steady?'max_iterations':'end_time_s']=value;if(k!=='warehouse')n.stop_mode='fixed';
    c._studio.termination=stop.mode==='time'?{mode:'time',time_s:stop.time_s}:{mode:'frames',frames:stop.frames,include_initial:!!stop.include_initial};return c;
  }
  function fieldInfo(path,config){const key=path.at(-1), full=path.join('.');let title=names[key]||String(key),unit='';
    if(typeof CBDEF!=='undefined')for(const [group,,,fields] of CBDEF)for(const [k,label,u] of fields)if(full===group+'.'+k){title=label;unit=u||'';}
    if(!unit){for(const [suffix,u] of [['_mg_m3','mg/m³'],['_kg_m3','kg/m³'],['_J_kg_K','J/(kg·K)'],['_J_kgK','J/(kg·K)'],['_J_m3_K','J/(m³·K)'],['_W_m2_K','W/(m²·K)'],['_W_m_K','W/(m·K)'],['_m2_s3','m²/s³'],['_m2_s2','m²/s²'],['_m2_s','m²/s'],['_m2','m²'],['_mm','mm'],['_m','m'],['_C','°C'],['_s','s']])if(String(key).endsWith(suffix)){unit=u;break;}}
    if(['x0','x1','y0','y1','z0','z1'].includes(key)){title=key[0].toUpperCase()+(key[1]==='0'?' 최소':' 최대');unit='mm';}
    if(kind(config)==='immersion'&&key==='write_interval_s')title='복구 데이터 저장 간격';
    if(key==='viz_interval_s')title='결과 프레임 저장 간격';
    return {title,unit};
  }
  const normalizeSearch = value => String(value).normalize('NFKC').toLowerCase().replace(/\s+/g,'');
  function matchesSearch(query,...terms){const translated=terms.map(x=>globalThis.CFDI18n?.translate(String(x))||x);const text=normalizeSearch([...terms,...translated].join(' '));return text.includes(normalizeSearch(query))||String(query).trim().split(/\s+/).every(word=>text.includes(normalizeSearch(word)));}
  function searchFields(config,query,{managed=false,readonly=false,sections={}}={}){
    const found=[];
    const visit=(value,path)=>{
      if(path.some(k=>isReferenceKey(k)||String(k).startsWith('_'))||path[0]==='schema')return;
      const key=path.at(-1),output=key==='output_fields'&&Array.isArray(value);
      if(!output&&value!==null&&typeof value==='object'){
        for(const [k,v] of Object.entries(value))visit(v,[...path,Array.isArray(value)?Number(k):k]);return;
      }
      if(managed&&!readonly&&['end_s','end_time_s','max_iterations','stop_mode'].includes(key))return;
      const info=fieldInfo(path,config),parents=path.map((_,i)=>fieldInfo(path.slice(0,i+1),config).title);
      const labels=(enums[key]||[]).map(v=>choices[v]||v);
      if(matchesSearch(query,sections[path[0]]||'',path.join('.'),...parents,info.unit,...labels,choices[value]||'',JSON.stringify(value)))found.push({path,value});
    };
    visit(config,[]);return found;
  }
  function searchTermination(config,query){
    const stop=config._studio?.termination,steady=kind(config)==='grain_silo'&&config.openfoam_mapping?.solver==='simpleFoam';
    const mode=stop?.mode||(steady?'frames':'time');
    return matchesSearch(query,'종료 조건 목표 종료 방식 수렴 기준 특정 물리시간 저장 프레임 수 목표값 비교 목적',config._studio?.goals||'',
      mode==='frames'?'목표 저장 프레임 수 0초 초기 프레임 포함 frames include_initial':'목표 물리시간 종료시간 time_s end_s end_time_s');
  }
  function summary(c,form){if(!c)return '';const n=c.numerics||c.run||{},iterations=n.time_basis==='iterations',end=iterations?n.max_iterations:n.end_s??n.end_time_s;return [form?.name,form?.solver||c.openfoam_mapping?.solver||c.analysis?.solver,end==null?null:`${end} ${iterations?'회':'s'}`].filter(Boolean).join(' · ')||'보관된 Case Config';}
  function prepareConfig(config,form){const c=clone(config),defaults=form?.capabilities?.default_output_fields;if(defaults){c.run??={};c.run.output_fields??=clone(defaults);}return c;}
  function outputChoices(value,form){return [...new Set([...(form?.capabilities?.output_fields||enums.output_fields),...value])];}
  function configParts(config){
    const groups=[
      {title:'형상·격자',keys:['tank','layers','board','coil','geometry_spec','geometry','loading','silo','mesh','porous_mesh']},
      {title:'물성·경계조건',keys:['dielectric_fluid','water','vapour','phase_change','heater','published','coupled','initial','temperature','boundary_policy']},
      {title:'솔버·계산',keys:['openfoam_mapping','solver_controls','numerics','run']},
      {title:'관측·비교',keys:['probes_mm','conditions','assumptions']}
    ];
    const keys=Object.keys(config).filter(k=>!k.startsWith('_')&&!['schema','schema_version'].includes(k)&&!isReferenceKey(k));
    const used=new Set(groups.flatMap(g=>g.keys));groups.push({title:'고급',keys:keys.filter(k=>!used.has(k))});
    return groups.map(g=>({...g,keys:g.keys.filter(k=>keys.includes(k))})).filter(g=>g.keys.length);
  }
  function download(config,name){const url=URL.createObjectURL(new Blob([JSON.stringify(config,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=(name||'Case Config')+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  let dialog;
  function legacyOpen(options){
    if(dialog?.open)throw Error('열려 있는 설정 창을 먼저 닫아 주세요');
    if(!dialog){dialog=document.createElement('dialog');dialog.id='settingsDialog';document.body.append(dialog);const style=document.createElement('style');style.textContent=`
#settingsDialog{width:min(1100px,96vw);height:min(850px,92vh);padding:0;border:1px solid var(--line);border-radius:12px;background:var(--surface);color:var(--ink)}#settingsDialog::backdrop{background:#000a}#settingsDialog[open]{display:flex;flex-direction:column}#settingsDialog header,#settingsDialog footer{padding:16px 20px;border-bottom:1px solid var(--line);display:flex;gap:10px;align-items:center;flex-wrap:wrap}#settingsDialog h2{font-size:18px;margin:0;flex:1}#settingsDialog p{margin:4px 0;font-size:12px;color:var(--ink2)}#settingsDialog input,#settingsDialog select,#settingsDialog textarea{background:var(--page);color:var(--ink);border:1px solid var(--line);border-radius:5px;padding:8px;font:inherit;box-sizing:border-box;min-width:0}#settingsDialog button{cursor:pointer}#settingsDialog input:disabled,#settingsDialog textarea:disabled,#settingsDialog select:disabled{opacity:.85}#settingsDialog .settings-body{flex:1;min-height:0;display:grid;grid-template-columns:205px minmax(0,1fr)}#settingsDialog nav{overflow:auto;padding:12px;border-right:1px solid var(--line)}#settingsDialog nav button{display:block;width:100%;padding:10px;text-align:left;margin-bottom:4px;border:0;border-radius:5px;background:transparent;color:var(--ink)}#settingsDialog nav details{margin:8px 0;border-color:var(--line)}#settingsDialog nav details>div{margin:4px!important;padding:2px}#settingsDialog nav details>summary{font-size:12px}#settingsDialog .settings-part-title{font-size:10px;letter-spacing:.4px;color:var(--muted);padding:16px 10px 6px;margin:0;border-top:1px solid var(--line)}#settingsDialog .settings-part-title:first-of-type{border-top:0}#settingsDialog nav button[aria-current=true]{background:#3987e530;color:#80baff}#settingsDialog main{overflow:auto;padding:18px;min-width:0}#settingsDialog .settings-row{display:grid;grid-template-columns:180px minmax(100px,1fr) 70px;gap:12px;align-items:center;padding:8px 0;border-bottom:1px solid var(--line);font-size:13px}#settingsDialog .settings-row input,#settingsDialog .settings-row textarea,#settingsDialog .settings-row select{width:100%}#settingsDialog .settings-row output{white-space:pre-wrap;overflow-wrap:anywhere}#settingsDialog fieldset{border:1px solid var(--line);border-radius:6px;margin:12px 0;padding:12px;min-width:0}#settingsDialog legend{padding:0 6px;font-size:13px}#settingsDialog .settings-note{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;color:var(--ink2);margin:8px 0}#settingsDialog footer{border-top:1px solid var(--line);border-bottom:0;flex-shrink:0}#settingsError{color:#ff9c8a!important;flex-basis:100%;white-space:pre-wrap}#settingsSearch{width:100%;margin-bottom:10px}#settingsJson{width:100%;height:100%;min-height:320px;font:12px monospace!important}#settingsDialog .settings-top{padding:12px 20px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}#settingsDialog .settings-top>select{width:auto;max-width:55%;flex:1}#settingsDialog .settings-top>p{flex-basis:100%}#settingsDialog .settings-top label{display:flex;align-items:center;gap:8px;font-size:13px}#settingsDialog .settings-fluid{display:flex;gap:8px;margin:10px 0}#settingsDialog .settings-output{display:flex;gap:12px;flex-wrap:wrap}#settingsDialog .settings-output label{display:flex;align-items:center;gap:4px}#settingsDialog .settings-output input{width:auto}@media(max-width:700px){#settingsDialog .settings-body{grid-template-columns:130px minmax(0,1fr)}#settingsDialog .settings-row{grid-template-columns:1fr;gap:4px}#settingsDialog header,#settingsDialog main{padding:12px}}
`;document.head.append(style);}
    let config=clone(options.config),readonly=!!options.readonly,section=options.managed?'termination':config.numerics?'numerics':config.run?'run':Object.keys(config)[0],locked=false,version=0,jsonText=null;const invalidNumbers=new Map();
    const el=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
    const button=(text,fn)=>{const b=el('button',text);b.type='button';b.className='btn';b.onclick=()=>act(fn);return b;};
    const error=message=>{document.getElementById('settingsError').textContent=message;};
    const act=async fn=>{try{error('');await fn();}catch(e){error(e.message);}};
    const current=()=>{if(!readonly){globalThis.CFDInput?.assertValid(dialog);if(invalidNumbers.size)throw Error([...invalidNumbers.keys()][0]+' 입력값을 숫자로 수정하세요.');}const c=jsonText!==null?parse(jsonText):clone(config);if(!readonly&&options.form){if(kind(c)!==kind(options.config))throw Error('CFD Template의 해석 대상을 변경할 수 없습니다');if(kind(c)==='grain_silo'&&c.openfoam_mapping?.solver!==options.form.solver)throw Error('솔버는 CFD Template에서 지정합니다');}return !readonly&&options.managed?applyTermination(c):c;};
    const close=()=>{if(!locked){version++;dialog.close();}};
    const busy=value=>{locked=value;for(const n of dialog.querySelectorAll('button,input,textarea,select'))n.disabled=value;};
    dialog.replaceChildren();const header=el('header');header.append(el('h2',options.title||(readonly?'Case Config':'새 Case Config')),button('닫기',close));dialog.append(header);
    const spatialButton=()=>button('공간 JSON',()=>CFDSpatial.open({config:current(),readonly,onApply:next=>{config=next;jsonText=null;invalidNumbers.clear();renderNav();render();}}));
    const top=el('div');top.className='settings-top';const name=el('input');name.id='settingsName';name.value=options.name||'실행 '+new Date().toLocaleString(({ko:'ko-KR',en:'en-US',ja:'ja-JP'})[globalThis.CFDI18n?.language]||'ko-KR');name.style.width='min(400px,55vw)';name.maxLength=80;name.setAttribute('aria-label',options.purpose==='preset'?'프리셋 이름':'실행 이름');
    if(!readonly&&options.purpose!=='form'){const l=el('label',options.purpose==='preset'?'프리셋 이름':'Case 이름');l.append(name);top.append(l);}
    const savePreset=el('input');savePreset.type='checkbox';savePreset.id='savePresetCheck';savePreset.checked=false;const presetName=el('input');presetName.id='newPresetName';presetName.placeholder='새 프리셋 이름';presetName.setAttribute('aria-label','새 프리셋 이름');presetName.hidden=true;
    if(!readonly&&options.managed&&options.purpose!=='preset'){const l=el('label');l.append(savePreset,el('span','프리셋에 저장'));top.append(l,presetName);savePreset.onchange=()=>{presetName.hidden=!savePreset.checked;};}
    const subtitle=el('p',readonly?'실행에 사용한 설정입니다. 조회·내보내기만 가능합니다.':'설정은 이번 실행에만 적용됩니다. 프로젝트에는 고정되지 않습니다.');top.append(subtitle);dialog.append(top);
    if(!readonly&&options.presets){const select=el('select');select.id='settingsPreset';select.setAttribute('aria-label','프리셋');select.append(new Option('프리셋 불러오기',''));for(const p of options.presets){const option=new Option(p.name,p.id);option.setAttribute('translate','no');select.append(option);}top.append(select,button('불러오기',async()=>{if(!select.value)throw Error('불러올 설정을 선택하세요');const token=++version;busy(true);try{const c=await options.onLoad(select.value);if(token!==version)return;config=clone(c);invalidNumbers.clear();section=options.managed?'termination':config.numerics?'numerics':'run';jsonText=null;renderNav();render();}finally{busy(false);}}));}
    const body=el('div');body.className='settings-body';const nav=el('nav');nav.setAttribute('aria-label','Config 항목');const search=el('input');search.id='settingsSearch';search.placeholder='Config 검색';search.setAttribute('aria-label','Config 검색');const navList=el('div');nav.append(search,navList);const main=el('main');body.append(nav,main);dialog.append(body);
    const footer=el('footer');const err=el('p');err.id='settingsError';err.setAttribute('role','alert');footer.append(err,button('JSON 내보내기',()=>download(current(),readonly?options.name:name.value)));
    const importFile=el('input');importFile.type='file';importFile.accept='.json,application/json';importFile.hidden=true;importFile.id='settingsImport';importFile.onchange=()=>act(async()=>{const file=importFile.files[0];if(!file)return;if(file.size>65536)throw Error('설정 파일은 64 KiB 이하여야 합니다');const token=++version;const c=parse(await file.text());if(token!==version||!dialog.open)return;config=c;invalidNumbers.clear();jsonText=null;section=options.managed?'termination':config.numerics?'numerics':config.run?'run':Object.keys(config)[0];renderNav();render();importFile.value='';});dialog.append(importFile);
    if(!readonly){footer.append(button('JSON 가져오기',()=>importFile.click()));
      if(options.onSave&&!options.managed)footer.append(button('Config 저장',async()=>{const c=current();validate(c);busy(true);try{const saved=await options.onSave(name.value,c);error('Config 저장 완료: '+saved.name);}finally{busy(false);}}));
      const start=button(options.submitLabel||'계산 시작',async()=>{const c=current();validate(c);if(!name.value.trim())throw Error('실행 이름을 입력하세요');if(savePreset.checked&&!presetName.value.trim())throw Error('새 프리셋 이름을 입력하세요');busy(true);try{await options.onRun(name.value,clone(c),{preset_name:savePreset.checked?presetName.value.trim():null});dialog.close();}finally{busy(false);}});start.id='settingsStart';start.classList.add('pri');footer.append(start);
    }else if(options.onClone){footer.append(button('Config 재사용',()=>{const c=current();if(kind(c)==='unsupported')throw Error('이 모델은 보관 설정 조회만 지원합니다');close();options.onClone(c);}));}
    footer.append(button(readonly?'닫기':'취소',close));dialog.append(footer);dialog.oncancel=e=>{if(locked)e.preventDefault();else version++;};
    function renderNav(){
      navList.replaceChildren();
      const add=(key,title,host=navList)=>{const b=button(title,()=>{if(section==='json'&&!readonly){config=current();jsonText=null;}section=key;search.value='';renderNav();render();});b.setAttribute('aria-current',String(section===key));host.append(b);};
      if(options.managed||config._studio?.termination)add('termination','종료 조건·목표');
      for(const part of configParts(config)){const group=el('details'),content=el('div');group.open=part.keys.includes(section);group.append(el('summary',part.title),content);navList.append(group);for(const key of part.keys)add(key,options.form?.sections?.[key]||names[key]||key,content);}
      const advanced=el('h4','파일');advanced.className='settings-part-title';navList.append(advanced);add('json','전체 JSON');
      if(references(config).length){const title=el('h4','참고 자료');title.className='settings-part-title';navList.append(title);add('references','출처');}
    }
    function set(path,value){let obj=config;for(const k of path.slice(0,-1))obj=obj[k];obj[path.at(-1)]=value;subtitle.textContent=[options.form?.name,options.form?.solver,readonly?'실행 시점 Config':options.purpose==='form'?'새 Case의 기본값':options.purpose==='preset'?'프리셋 Config':'이 Case에 적용'].filter(Boolean).join(' · ');}
    function draw(value,path,host){if(section!=='references'&&path.some(isReferenceKey))return;const key=path.at(-1),info=fieldInfo(path,config);
      if(key==='output_fields'&&Array.isArray(value)){const box=el('div'),available=outputChoices(value,options.form);box.className='settings-output';for(const field of available){const l=el('label'),input=el('input');input.type='checkbox';input.checked=value.includes(field);input.disabled=readonly;input.onchange=()=>{const selected=available.filter((_,i)=>box.querySelectorAll('input')[i].checked);set(path,selected);};l.append(input,el('span',choices[field]||field));box.append(l);}host.append(box);return;}
      if(value!==null&&typeof value==='object'){
        const box=el('fieldset');box.append(el('legend',info.title));host.append(box);
        for(const [k,v] of Object.entries(value)){
          if(k.startsWith('_')){if(isReferenceKey(k))continue;const note=el('div',typeof v==='string'?v:JSON.stringify(v));note.className='settings-note';box.append(note);continue;}
          const entry=Array.isArray(value)?el('fieldset'):box;if(entry!==box){entry.append(el('legend',String(Number(k)+1)));box.append(entry);if(!readonly)entry.append(button('행 삭제',()=>{const removed=Number(k),prefix=path.join('.')+'.';
            const drafts=[...invalidNumbers];for(const [name] of drafts)if(name.startsWith(prefix))invalidNumbers.delete(name);
            for(const [name,raw] of drafts)if(name.startsWith(prefix)){const parts=name.slice(prefix.length).split('.'),index=Number(parts[0]);if(index===removed)continue;parts[0]=String(index>removed?index-1:index);invalidNumbers.set(prefix+parts.join('.'),raw);}
            value.splice(removed,1);render();}));}
          draw(v,[...path,Array.isArray(value)?Number(k):k],entry);
        }
        if(Array.isArray(value)&&!readonly)box.append(button('행 추가',()=>{value.push(value.length?clone(value.at(-1)):0);render();}));return;
      }
      if(options.managed&&!readonly&&['end_s','end_time_s','max_iterations','stop_mode'].includes(key))return;
      const row=el('label');row.className='settings-row';row.title=path.join('.');row.dataset.settingPath=path.join('.');row.append(el('span',info.title));
      if(readonly||(options.form&&path.join('.')==='openfoam_mapping.solver')){row.append(el('output',value===null?'미지정':typeof value==='boolean'?(value?'사용':'미사용'):String(value)));}
      else{
        let input;const options=enums[key];
        if(options&&!Array.isArray(value)){input=el('select');for(const v of [...new Set([...options,value])])input.append(new Option(choices[v]||String(v),String(v)));input.value=String(value);}
        else if(typeof value==='boolean'){input=el('input');input.type='checkbox';input.checked=value;}
        else{input=el(typeof value==='string'&&value.length>90?'textarea':'input');if(input.tagName==='INPUT'){input.type=typeof value==='number'?'number':'text';input.step='any';}input.value=value===null?'null':String(value);}
        input.setAttribute('aria-label',info.title+(info.unit?' ('+info.unit+')':''));input.dataset.path=path.join('.');
        if(typeof value==='number'&&input.tagName==='INPUT'){
          const fieldPath=path.join('.');globalThis.CFDInput?.bind(input,{type:'number'});
          if(invalidNumbers.has(fieldPath)){input.value=invalidNumbers.get(fieldPath);queueMicrotask(()=>globalThis.CFDInput?.check(input));}
        }
        input.oninput=()=>{if(typeof value==='number'){try{const n=globalThis.CFDInput?CFDInput.parseValue(input.value,'number'):Number(input.value);if(!input.value.trim()||!Number.isFinite(n))throw Error('숫자를 입력하세요');input.setCustomValidity('');invalidNumbers.delete(path.join('.'));set(path,n);}catch(e){invalidNumbers.set(path.join('.'),input.value);input.setCustomValidity(e.message);}}else set(path,typeof value==='boolean'?input.checked:value===null?(input.value==='null'?null:input.value):input.value);};
        if(input.tagName==='SELECT')input.onchange=input.oninput;row.append(input);
      }
      row.append(el('span',info.unit));host.append(row);
    }
    function renderTermination(){
      main.append(el('h3','종료 조건·목표'));const steady=kind(config)==='grain_silo'&&config.openfoam_mapping?.solver==='simpleFoam',n=config.numerics||config.run||{};
      const saved=config._studio?.termination;
      const stop=saved?clone(saved):{mode:steady?'frames':'time',time_s:n.end_s??n.end_time_s??300,frames:Math.max(1,Math.ceil((n.max_iterations||300)/(n.write_interval_iterations||100))),include_initial:false};
      if(!readonly)config._studio={...config._studio,termination:stop};
      const mode=el('select');mode.setAttribute('aria-label','종료 방식');
      for(const [value,text,disabled] of [['convergence','수렴 기준',true],['time','특정 물리시간',steady],['frames','저장 프레임 수',false]]){const o=new Option(text,value);o.disabled=disabled;mode.append(o);}mode.value=stop.mode;mode.disabled=readonly;mode.onchange=()=>{stop.mode=mode.value;invalidNumbers.delete('_studio.termination.time_s');invalidNumbers.delete('_studio.termination.frames');stop.time_s??=n.end_s??n.end_time_s??300;stop.frames??=3;stop.include_initial??=false;config._studio.termination=stop;render();};main.append(mode);
      const note=el('p','수렴 기준: 연속 유지 구간을 확인하는 실행기 연결이 없어 현재 선택할 수 없습니다.'+(steady?' 정상 해석의 반복 횟수는 물리시간이 아닙니다.':''));main.append(note);
      const field=(label,key,value)=>{const row=el('label');row.className='settings-row';const input=el('input');input.type='number';input.step=key==='frames'?'1':'any';input.value=invalidNumbers.get('_studio.termination.'+key)??value??'';input.disabled=readonly;input.required=true;input.min=key==='frames'?'1':'0';input.setAttribute('aria-label',label);globalThis.CFDInput?.bind(input,{type:key==='frames'?'integer':'number'});if(invalidNumbers.has('_studio.termination.'+key))input.value=invalidNumbers.get('_studio.termination.'+key);input.oninput=()=>{try{const v=globalThis.CFDInput?CFDInput.parseValue(input.value,key==='frames'?'integer':'number'):Number(input.value);if(!input.checkValidity())throw Error(input.validationMessage);stop[key]=v;invalidNumbers.delete('_studio.termination.'+key);}catch(_){invalidNumbers.set('_studio.termination.'+key,input.value);}};if(invalidNumbers.has('_studio.termination.'+key))queueMicrotask(()=>globalThis.CFDInput?.check(input));row.append(el('span',label),input);main.append(row);};
      if(stop.mode==='time')field('목표 물리시간 (s)','time_s',stop.time_s);
      if(stop.mode==='frames'){field('목표 저장 프레임 수','frames',stop.frames);const l=el('label'),b=el('input');b.type='checkbox';b.checked=!!stop.include_initial;b.disabled=readonly||steady;b.onchange=()=>{stop.include_initial=b.checked;};l.append(b,el('span','0초 초기 프레임 포함'));main.append(l,el('p','선택한 출력 항목이 모두 저장된 시점만 1프레임으로 셉니다.'));}
      const label=el('label','목표값·비교 목적'),goals=el('textarea');goals.setAttribute('aria-label','목표값·비교 목적');goals.value=config._studio?.goals||'';goals.disabled=readonly;goals.maxLength=4000;goals.style.width='100%';goals.oninput=()=>{config._studio.goals=goals.value;};label.append(goals);main.append(label);
      main.append(el('p','솔버 시간간격: 계산 단계 · 결과 저장 간격: 파일 출력 주기 · 재생 속도: Viewer 표시 배속'));
    }
    function render(){main.replaceChildren();subtitle.textContent=[options.form?.name,options.form?.solver,readonly?'실행 시점 Config':options.purpose==='form'?'새 Case의 기본값':options.purpose==='preset'?'프리셋 Config':'이 Case에 적용'].filter(Boolean).join(' · ');
      const query=search.value.trim();
      if(query){
        if((options.managed||config._studio?.termination)&&searchTermination(config,query))renderTermination();
        const groups=new Map();
        for(const {path,value} of searchFields(config,query,{managed:options.managed,readonly,sections:options.form?.sections||{}})){
          const parent=path.slice(0,-1).map((_,i)=>fieldInfo(path.slice(0,i+1),config).title).join(' · ')||'설정';
          if(!groups.has(parent)){const box=el('fieldset');box.append(el('legend',parent));main.append(box);groups.set(parent,box);}
          draw(value,path,groups.get(parent));
        }
        if(!main.children.length)main.append(el('p','검색 결과가 없습니다.'));
        return;
      }
      if(section==='termination'){renderTermination();return;}
      if(section==='references'){main.append(el('h3','출처'));for(const ref of references(config)){const group=el('fieldset'),parent=ref.path.slice(0,-1).map(k=>names[k]||k).join(' · ');group.append(el('legend',parent||'설정'));draw(ref.value,ref.path,group);main.append(group);}return;}

      if(section==='json'){const area=el('textarea');area.id='settingsJson';area.setAttribute('aria-label','전체 JSON');area.readOnly=readonly;globalThis.CFDInput?.bind(area,{type:'object'});area.value=jsonText??JSON.stringify(config,null,2);area.oninput=()=>{jsonText=area.value;};main.append(area);return;}
      const sectionHeading=el('div');sectionHeading.style.cssText='display:flex;align-items:center;gap:12px;margin-bottom:12px';const sectionTitle=el('h3',options.form?.sections?.[section]||names[section]||section);sectionTitle.style.margin='0';sectionHeading.append(sectionTitle);if(['geometry_spec','geometry','tank','loading','board','coil','silo'].includes(section))sectionHeading.append(spatialButton());main.append(sectionHeading);
      if(!readonly&&['water','dielectric_fluid'].includes(section)&&typeof fluidRef==='function'){
        const bar=el('div');bar.className='settings-fluid';bar.append(button('대표 물성 입력',()=>{const q=fluidRef(section==='water'?'upper':'lower',config);config[section].manual_properties={model:'linear_density',T_ref_C:q.T,rho_kg_m3:q.rho,cp_J_kgK:q.cp,mu_Pa_s:q.mu,kappa_W_mK:q.k,beta_1_K:q.beta};render();}),button('원래 물성표 사용',()=>{delete config[section].manual_properties;render();}));main.append(bar);
      }
      const v=config[section];if(v&&typeof v==='object'&&!Array.isArray(v))for(const [k,x] of Object.entries(v)){if(k.startsWith('_')){if(isReferenceKey(k))continue;const note=el('div',String(x));note.className='settings-note';main.append(note);}else draw(x,[section,k],main);}else draw(v,[section],main);
    }
    search.oninput=()=>act(()=>{if(section==='json'){config=jsonText!==null?parse(jsonText):config;jsonText=null;section=config.numerics?'numerics':config.run?'run':Object.keys(config)[0];renderNav();}render();});renderNav();render();dialog.showModal();return {close,current};
  }
  function open(options){
    if(!globalThis.CFDFormConfig)return legacyOpen(options);
    const readonly=!!options.readonly,initial=clone(options.config),managed=!!options.managed;
    let caseName=options.name||'Case '+new Date().toLocaleString(({ko:'ko-KR',en:'en-US',ja:'ja-JP'})[globalThis.CFDI18n?.language]||'ko-KR'),presetEnabled=false,presetName='',loading=false;
    const el=(tag,text)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;return node;};
    const named=(tag,label)=>{const node=el(tag);node.setAttribute('aria-label',label);return node;};
    const configNow=value=>{
      if(options.form){if(kind(value)!==kind(initial))throw Error('CFD Template의 해석 대상을 변경할 수 없습니다');if(kind(value)==='grain_silo'&&value.openfoam_mapping?.solver!==options.form.solver)throw Error('솔버는 CFD Template에서 지정합니다');}
      return managed||value._studio?.termination?applyTermination(value):value;
    };
    if(managed&&!readonly){const n=initial.numerics||initial.run||{},steady=kind(initial)==='grain_silo'&&initial.openfoam_mapping?.solver==='simpleFoam';initial._studio??={};initial._studio.termination??=steady?{mode:'frames',frames:Math.max(1,Math.ceil((n.max_iterations||300)/(n.write_interval_iterations||100))),include_initial:false}:{mode:'time',time_s:n.end_s??n.end_time_s??300};}
    const sections=managed||initial._studio?.termination?[{key:'case_termination',title:'종료 조건·목표',ownsPaths:terminationPaths(initial),matches:(query,value)=>searchTermination(value,query),render:(host,editor)=>{
      host.classList.add('fc-custom');const value=editor.getConfig(),n=value.numerics||value.run||{},steady=kind(value)==='grain_silo'&&value.openfoam_mapping?.solver==='simpleFoam',stop=value._studio?.termination||(steady?{mode:'frames',frames:Math.max(1,Math.ceil((n.max_iterations||300)/(n.write_interval_iterations||100))),include_initial:false}:{mode:'time',time_s:n.end_s??n.end_time_s??300});
      if(!readonly&&!value._studio?.termination)editor.mutate(c=>{c._studio??={};c._studio.termination=clone(stop);});
      const heading=el('div');heading.className='fc-titlebar';heading.append(el('h3','종료 조건·목표'));const json=el('button','JSON');json.type='button';json.className='btn fc-json-action';json.onclick=()=>editor.openJSON(['_studio']);heading.append(json);host.append(heading);
      const mode=named('select','종료 방식');for(const [key,label,disabled]of [['convergence','수렴 기준',true],['time','특정 물리시간',steady],['frames','저장 프레임 수',false]]){const o=new Option(label,key);o.disabled=disabled;mode.append(o);}mode.value=stop.mode||'time';mode.disabled=readonly;host.append(mode);
      mode.onchange=()=>{editor.mutate(c=>{c._studio??={};c._studio.termination={...stop,mode:mode.value,time_s:stop.time_s??n.end_s??n.end_time_s??300,frames:stop.frames??3,include_initial:!!stop.include_initial};});editor.render();};
      host.append(el('p','수렴 기준은 실행기 연결이 필요하므로 현재 선택할 수 없음'));
      const key=stop.mode==='frames'?'frames':'time_s',caption=key==='frames'?'목표 저장 프레임 수':'목표 물리시간 (s)',label=el('label',caption),input=named('input',caption);input.type='number';input.step=key==='frames'?'1':'any';input.min=key==='frames'?'1':'0';input.required=true;input.value=stop[key]??'';input.readOnly=readonly;globalThis.CFDInput?.bind(input,{type:key==='frames'?'integer':'number'});input.oninput=()=>{if(input.value!==''&&input.checkValidity())editor.mutate(c=>c._studio.termination[key]=Number(input.value));};label.append(input);host.append(label);
      if(key==='frames'){const label=el('label'),check=named('input','0초 초기 프레임 포함');check.type='checkbox';check.checked=!!stop.include_initial;check.disabled=readonly||steady;check.onchange=()=>editor.mutate(c=>c._studio.termination.include_initial=check.checked);label.append(check,el('span','0초 초기 프레임 포함'));host.append(label,el('p','선택한 출력 항목이 모두 저장된 시점만 1프레임으로 계산'));}
      const goalsLabel=el('label','목표값·비교 목적'),goals=named('textarea','목표값·비교 목적');goals.value=value._studio?.goals||'';goals.readOnly=readonly;goals.maxLength=4000;goals.oninput=()=>editor.mutate(c=>{c._studio??={};c._studio.goals=goals.value;});goalsLabel.append(goals);host.append(goalsLabel,el('p','솔버 시간간격 · 결과 저장 간격 · Viewer 재생 속도는 개별 항목'));
    }}]:[];
    return CFDFormConfig.open({config:initial,schema:CFDFormConfig.fromConfig(initial,options.form?.input_schema),valuesOnly:true,readonly,title:options.title||'Case Config',customSections:sections,submitLabel:options.submitLabel||'Config 저장',form:options.form,onClone:options.onClone,
      onMount:editor=>{
        const top=el('div');top.className='fc-case-controls';editor.toolbar.before(top);
        if(readonly){top.append(el('span','실행 시점 Config'));return;}
        const nameLabel=el('label',options.purpose==='preset'?'프리셋 이름':'Case 이름'),name=named('input','실행 이름');name.value=caseName;name.maxLength=80;name.oninput=()=>caseName=name.value;nameLabel.append(name);top.append(nameLabel);
        if(managed){const label=el('label'),check=named('input','프리셋에 저장'),text=named('input','새 프리셋 이름');check.type='checkbox';check.checked=false;text.hidden=true;text.placeholder='새 프리셋 이름';text.oninput=()=>presetName=text.value;check.onchange=()=>{presetEnabled=check.checked;text.hidden=!check.checked;};label.append(check,el('span','프리셋에 저장'));top.append(label,text);}
        if(options.presets?.length){const select=named('select','프리셋');select.append(new Option('프리셋 불러오기',''));for(const p of options.presets){const option=new Option(p.name,p.id);option.setAttribute('translate','no');select.append(option);}const load=el('button','불러오기');load.type='button';load.className='btn';load.onclick=async()=>{if(!select.value||loading)return;const error=editor.dialog.querySelector('.fc-error');loading=true;load.disabled=true;try{editor.getConfig();const value=await options.onLoad(select.value);if(editor.dialog.open)editor.setConfig(value);error.textContent='';}catch(e){error.textContent=e.message;}finally{loading=false;load.disabled=false;}};const presetLoad=el('div');presetLoad.className='fc-preset-load';presetLoad.append(select,load);top.append(presetLoad);}
      },onSave:async value=>{
        if(loading)throw Error('프리셋을 불러오는 중입니다');if(!caseName.trim())throw Error('이름을 입력하세요');if(presetEnabled&&!presetName.trim())throw Error('새 프리셋 이름을 입력하세요');const result=configNow(value);validate(result);
        if(options.onRun)await options.onRun(caseName,result,{preset_name:presetEnabled?presetName.trim():null});else if(options.onSave)await options.onSave(caseName,result);
      }});
  }
  globalThis.CFDSettings={open,kind,matchesSearch,choicesFor:key=>(enums[key]||[]).map(value=>({value,label:choices[value]||String(value)})),parse,validate,fieldInfo,summary,prepareConfig,outputChoices,applyTermination,terminationPaths,references,searchFields,searchTermination,configParts};
  if(typeof module!=='undefined')module.exports=globalThis.CFDSettings;
})();
