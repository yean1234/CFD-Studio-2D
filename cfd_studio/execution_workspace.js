/* Project containers do not own solver settings. Each launch takes a snapshot. */
(() => {
  const $ = id => document.getElementById(id);
  const selectedRuns=new Map();
  let data = {projects: []}, projectId = '', runId = '', generation = 0, detail = null;
  let pending=false, refreshing=false, projectSignature='',runSignature='',viewMode='cfd',nativeViewer=null,nativePromise=null,preferredTemplate='warehouse';
  const status = {complete:'완료', failed:'실패', running:'계산 중', queued:'준비 중', preparing:'준비 중', saved:'보관'};
  const model = {clo2_coupled_scenario:'저장고 연결', clo2_plan_scenario:'저장고 확산', normalized_gable_verification:'정규화 시험', gas_transport:'추적자 시험', immersion:'액침냉각', grain_silo:'단상 저장고'};
  const node = (tag, text, cls) => {const e=document.createElement(tag); if(text!=null)e.textContent=text; if(cls)e.className=cls; return e;};
  async function api(path, body) {
    const response = await fetch('/api/executions'+path, body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const value = await response.json();
    if(!response.ok||value.ok===false)throw Error(value.msg||'요청 실패');
    return value;
  }
  function currentProject(){return data.projects.find(p=>p.id===projectId);}
  function button(text, action, cls='btn') {const b=node('button',text,cls); b.type='button'; b.onclick=action; return b;}
  function message(text){$('ewMessage').textContent=text;}
  function showList(){viewMode='cfd';nativeViewer?.hide();setPlay(false,true);setMode('cfd');document.body.classList.remove('execution-viewer','warehouse-viewer');$('appContext').textContent='CFD Studio · '+(currentProject()?.name||'프로젝트');}
  function renderProjects() {
    const list=$('ewProjects');
    const signature=JSON.stringify([projectId,data.projects.map(p=>[p.id,p.name,p.runs.length])]);
    if(signature!==projectSignature){projectSignature=signature;list.replaceChildren();
    for(const p of data.projects){
      const b=button('',()=>selectProject(p.id),'ew-project'+(p.id===projectId?' selected':''));
      b.append(node('strong',p.name),node('span',`실행 ${p.runs.length}개`)); list.append(b);
    }
    }
    $('ewTitle').textContent=currentProject()?.name||'프로젝트';
    $('ewNewRun').disabled=pending;
    $('appContext').textContent='CFD Studio · '+(currentProject()?.name||'프로젝트');
    $('stTxt').textContent=data.busy?'계산 중':'실행 대기';$('stDot').className=data.busy?'dot run':'dot ok';
  }
  function renderRuns(){
    const rows=$('ewRows'), p=currentProject(), search=$('ewSearch').value.toLowerCase();
    const signature=JSON.stringify([projectId,runId,search,p?.runs]);
    if(signature===runSignature)return;runSignature=signature;
    rows.replaceChildren();
    const picker=$('ewRunPicker');picker.replaceChildren(new Option('실행 선택',''));for(const r of p?.runs||[])picker.append(new Option(r.name,r.id));picker.value=runId;picker.title=p?.runs.find(r=>r.id===runId)?.name||'실행 선택';
    for(const r of p?.runs||[]){
      if(!`${r.name} ${r.model}`.toLowerCase().includes(search))continue;
      const tr=node('tr');tr.classList.toggle('selected',r.id===runId);
      const td=node('td'); const b=button(r.name,()=>selectRun(r.id),'ew-run'); b.title=r.name; td.append(b);
      tr.append(td,node('td',model[r.model]||r.model||'미확인'),node('td',status[r.status]||r.status),node('td',r.end_s==null?'—':`${r.end_s} s`));rows.append(tr);
    }
    if(!rows.children.length){const tr=node('tr'), td=node('td',search?'검색 결과 없음':'실행 이력 없음');td.colSpan=4;tr.append(td);rows.append(tr);}
  }
  async function selectProject(id){
    projectId=id;runId='';detail=null;generation++;nativeViewer?.hide();setPlay(false,true);
    $('ewSearch').value='';renderProjects();renderRuns();
    try{localStorage.setItem('cfd-project',id);}catch(_){}
    const runs=currentProject()?.runs||[];
    const recent=runs.find(r=>r.id===selectedRuns.get(id))||runs.find(r=>r.status==='running')||runs.find(r=>r.has_results)||runs[0];
    if(recent)await selectRun(recent.id);else{clearDetail();showList();}
  }
  function clearDetail(){
    $('ewRunTitle').textContent='실행 선택';$('ewLog').textContent='목록에서 실행을 선택하세요.';
    $('ewSource').textContent='';$('ewConfigSummary').textContent='';$('ewFacts').textContent='';$('ewView').disabled=true;$('ewSettings').disabled=true;$('ewSidebarSettings').disabled=true;
  }
  function showDetail(value){
    detail=value;$('ewRunTitle').textContent=value.name;$('ewLog').textContent=value.log||'보존된 솔버 로그 없음';
    $('ewSource').textContent=value.log_source||'';
    $('ewConfigSummary').textContent=CFDSettings.summary(value.config);$('ewSettings').disabled=false;$('ewSidebarSettings').disabled=false;
    const checks=value.checks||{};
    $('ewFacts').textContent=`${model[value.model]||value.model||'모델 미확인'} · ${status[value.status]||value.status}`+
      (value.kind==='warehouse'?' · 수치 수렴 '+(checks.numerical_pass?'해당 시험 통과':'미완료')+' · 실험 검증 미완료':'')+
      (value.error?' · '+value.error:'');
    $('ewView').disabled=!value.has_results;
  }
  async function selectRun(id){
    const token=++generation;runId=id;selectedRuns.set(projectId,id);detail=null;renderRuns();nativeViewer?.hide();setPlay(false,true);
    clearDetail();$('ewRunTitle').textContent='불러오는 중';
    try{const value=await api('/detail?id='+encodeURIComponent(id));if(token!==generation)return;showDetail(value);message('');if(viewMode==='viewer')await viewResult();}
    catch(e){if(token===generation){clearDetail();message(e.message);}}
  }
  async function viewer(){
    if(!nativePromise)nativePromise=import('/warehouse_viewer.js').then(module=>nativeViewer=module.mountWarehouseViewer($('warehouseNative'),inspectSettings));
    return nativePromise;
  }
  async function viewResult(){
    if(!detail?.has_results){showList();message('선택한 실행의 결과가 아직 없습니다. 설정과 로그를 확인하세요.');return;}
    const selected=detail,token=generation;viewMode='viewer';setPlay(false,true);
    document.body.classList.add('execution-viewer');
    document.body.classList.toggle('warehouse-viewer',selected.kind==='warehouse');
    if(selected.kind!=='warehouse')VPROJ=selected.rid;
    setMode('viz');
    if(selected.kind==='warehouse'){
      const v=await viewer();if(token!==generation||viewMode!=='viewer')return;
      await v.load(selected.rid,selected.name);
    }else{nativeViewer?.hide();await selVz(selected.rid);}
  }
  function inspectSettings(){
    if(!detail)return;const snapshot=structuredClone(detail);
    CFDSettings.open({config:snapshot.config,readonly:true,title:'설정 보기 · '+snapshot.name,name:snapshot.name,onClone:config=>openRun(config)});
  }
  async function refresh(){
    if(refreshing)return;refreshing=true;
    try{
      const value=await api('');data=value;
      if(!projectId||!data.projects.some(p=>p.id===projectId)){
        let saved='';try{saved=localStorage.getItem('cfd-project')||'';}catch(_){}
        await selectProject(data.projects.find(p=>p.id===saved)?.id||data.projects[0]?.id);
      }else{renderProjects();renderRuns();}
      if(runId&&!pending){const token=generation;const v=await api('/detail?id='+encodeURIComponent(runId));if(token===generation)showDetail(v);}
    }catch(e){message(e.message);}finally{refreshing=false;}
  }
  async function openRun(source){
    if(pending)return;
    try{
      const targetProject=projectId,projectName=currentProject()?.name;
      const [presetData,result]=await Promise.all([api('/presets'),source?Promise.resolve({config:structuredClone(source)}):api('/template?id='+encodeURIComponent(preferredTemplate))]);
      const prepare=config=>{const c=structuredClone(config);if(CFDSettings.kind(c)==='immersion'&&!c.run.output_fields)c.run.output_fields=['bubble','phase','flow','therm'];return c;};
      CFDSettings.open({config:prepare(result.config),title:'새 CFD 실행 · '+projectName,presets:presetData.presets,
        onLoad:async id=>{const loaded=await api('/template?id='+encodeURIComponent(id));preferredTemplate=id;return prepare(loaded.config);},
        onSave:async(name,config)=>(await api('/preset',{name,config})).result,
        onRun:async(name,config)=>{
          pending=true;renderProjects();
          try{
            let key;
            if(CFDSettings.kind(config)==='warehouse')key=(await api('/start',{project_id:targetProject,name,config})).result.run_key;
            else{
              const response=await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:'fresh',config_ref:'inline',config,output_fields:config.run.output_fields,execution_project_id:targetProject,execution_name:name})});
              const result=await response.json();if(!response.ok||!result.ok)throw Error(result.msg||result.err||'계산 시작 실패');key='legacy:'+result.rid;
            }
            showList();await refresh();await selectProject(targetProject);await selectRun(key);message('계산 시작');
          }finally{pending=false;renderProjects();}
        }
      });
    }catch(e){message(e.message);}
  }
  async function createProject(){
    nameBox('프로젝트 이름','새 프로젝트',async name=>{try{const result=await api('/project',{name});await refresh();await selectProject(result.result.id);}catch(e){message(e.message);}});
  }
  async function renameProject(){
    const id=projectId, p=currentProject();if(!p)return;
    nameBox('프로젝트 이름',p.name,async name=>{try{await api('/rename',{id,name});await refresh();}catch(e){message(e.message);}});
  }
  function mount(){
    const style=node('style');style.textContent=`
body.grouped #secRun,body.grouped #secData{display:none!important}body.grouped.execution-viewer:not(.warehouse-viewer) #secData{display:block!important}body.grouped #projList2,body.grouped #secData>.fgroup,body.grouped #secData>button[onclick="newProj()"]{display:none!important}body.grouped.warehouse-viewer #viz{visibility:hidden}#ewRunPicker{width:100%;padding:8px;margin:10px 0;background:var(--surface);color:var(--ink);border:1px solid var(--line)}body.grouped #dash{display:flex!important}body.grouped.execution-viewer #dash{display:none!important}
body.grouped #dash>.dlog{flex:none;display:block;min-height:0}body.grouped #dash>:not(.dlog){display:none!important}body.grouped .dlog>pre,body.grouped .dlog>.dlab{display:none!important}
#ewSidebar{padding:16px}#ewSidebar h2{font-size:14px}#ewProjects{display:grid;gap:8px;margin:12px 0}.ew-project{width:100%;text-align:left;padding:12px;border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:8px;cursor:pointer}.ew-project strong,.ew-project span{display:block}.ew-project span{font-size:12px;color:var(--muted);margin-top:5px}.ew-project.selected{border-color:#3987e5}
#ewPanel{display:grid;gap:14px;min-width:0}#ewPanel h2,#ewPanel h3{margin:0;font-size:17px}.ew-bar{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.ew-bar h2,.ew-bar h3{flex:1}.ew-table{max-height:320px;overflow:auto;border:1px solid var(--line);border-radius:8px}#ewPanel table{width:100%;border-collapse:collapse}#ewPanel th,#ewPanel td{text-align:left;padding:10px;border-bottom:1px solid var(--line)}#ewPanel th{position:sticky;top:0;background:var(--surface)}#ewPanel tr.selected{background:rgba(57,135,229,.16)}.ew-run{color:var(--ink);background:none;border:0;text-align:left;cursor:pointer;overflow-wrap:anywhere}#ewRows td:first-child{width:56%}#ewSearch{max-width:320px;padding:8px;background:var(--surface);color:var(--ink);border:1px solid var(--line)}
#ewLog{max-height:280px!important;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;padding:12px;background:var(--page);border-radius:6px}#ewSource,#ewFacts,#ewMessage,#ewConfigSummary{font-size:12px;overflow-wrap:anywhere;color:var(--ink2)}#ewMessage{color:#e1b95d}@media(max-width:700px){#ewPanel th,#ewPanel td{padding:6px;font-size:12px}#ewRows td:first-child{width:auto}}
`;document.head.append(style);
    const sidebar=node('section',null);sidebar.id='ewSidebar';sidebar.append(node('h2','프로젝트'),button('새 프로젝트',createProject));
    const projects=node('div');projects.id='ewProjects';const picker=node('select');picker.id='ewRunPicker';picker.setAttribute('aria-label','실행 선택');picker.onchange=()=>{if(picker.value)selectRun(picker.value);};const settings=button('설정 보기',inspectSettings);settings.id='ewSidebarSettings';settings.disabled=true;sidebar.append(projects,picker,settings,button('실행 목록',showList));$('side').prepend(sidebar);
    const panel=node('section');panel.id='ewPanel';panel.innerHTML=`
<div class="ew-bar"><h2 id="ewTitle">프로젝트</h2><button id="ewRename" class="btn">이름 변경</button><button id="ewNewRun" class="btn pri">새 CFD 실행</button></div>
<p id="ewMessage" role="status"></p><div class="ew-bar"><h3>실행 목록</h3><input id="ewSearch" aria-label="실행 검색" placeholder="실행 검색"></div>
<div class="ew-table"><table><thead><tr><th>실행</th><th>모델</th><th>상태</th><th>계산 범위</th></tr></thead><tbody id="ewRows"></tbody></table></div>
<div class="ew-bar"><h3 id="ewRunTitle">실행 선택</h3><button id="ewView" class="btn" disabled>결과 보기</button></div><p id="ewFacts"></p>
<div class="ew-bar"><p id="ewConfigSummary"></p><button id="ewSettings" class="btn" disabled>설정 보기</button></div>
<h3>솔버 로그</h3><p id="ewSource"></p><pre id="ewLog"></pre>`;
    document.querySelector('#dash .dlog').append(panel);
    const native=node('section');native.id='warehouseNative';native.hidden=true;$('main').append(native);
    $('ewNewRun').onclick=()=>openRun();$('ewRename').onclick=renameProject;$('ewView').onclick=viewResult;$('ewSearch').oninput=renderRuns;$('ewSettings').onclick=inspectSettings;
    $('mCFD').onclick=showList;$('mViz').onclick=viewResult;
    document.body.classList.add('grouped');showList();
  }
  mount();refresh();setInterval(refresh,4000);
})();
