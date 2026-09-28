/* Project containers do not own solver settings. Each launch takes a snapshot. */
(() => {
  const $ = id => document.getElementById(id);
  let data = {projects: []}, projectId = '', runId = '', generation = 0, detail = null;
  let draft = null, pending = false, refreshing = false, resultId = '', projectSignature = '', runSignature = '';
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
  function showList(){setMode('cfd'); document.body.classList.remove('execution-viewer');$('appContext').textContent='CFD Studio · '+(currentProject()?.name||'프로젝트');}
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
    $('ewNewRun').disabled=pending||data.busy;
    $('appContext').textContent='CFD Studio · '+(currentProject()?.name||'프로젝트');
    $('stTxt').textContent=data.busy?'계산 중':'실행 대기';$('stDot').className=data.busy?'dot run':'dot ok';
  }
  function renderRuns(){
    const rows=$('ewRows'), p=currentProject(), search=$('ewSearch').value.toLowerCase();
    const signature=JSON.stringify([projectId,runId,search,p?.runs]);
    if(signature===runSignature)return;runSignature=signature;
    rows.replaceChildren();
    for(const r of p?.runs||[]){
      if(!`${r.name} ${r.model}`.toLowerCase().includes(search))continue;
      const tr=node('tr');tr.classList.toggle('selected',r.id===runId);
      const td=node('td'); const b=button(r.name,()=>selectRun(r.id),'ew-run'); b.title=r.name; td.append(b);
      tr.append(td,node('td',model[r.model]||r.model||'미확인'),node('td',status[r.status]||r.status),node('td',r.end_s==null?'—':`${r.end_s} s`));rows.append(tr);
    }
    if(!rows.children.length){const tr=node('tr'), td=node('td',search?'검색 결과 없음':'실행 이력 없음');td.colSpan=4;tr.append(td);rows.append(tr);}
  }
  async function selectProject(id){
    projectId=id;runId='';detail=null;resultId='';generation++;
    $('ewResult').hidden=true;$('ewResult').removeAttribute('src');
    $('ewSearch').value='';showList();renderProjects();renderRuns();
    try{localStorage.setItem('cfd-project',id);}catch(_){}
    const runs=currentProject()?.runs||[];
    const recent=runs.find(r=>r.status==='running')||runs.find(r=>r.has_results)||runs[0];
    if(recent)await selectRun(recent.id);else clearDetail();
  }
  function clearDetail(){
    $('ewRunTitle').textContent='실행 선택';$('ewLog').textContent='목록에서 실행을 선택하세요.';
    $('ewSource').textContent='';$('ewConfig').textContent='';$('ewFacts').textContent='';$('ewView').disabled=true;
  }
  function showDetail(value){
    detail=value;$('ewRunTitle').textContent=value.name;$('ewLog').textContent=value.log||'보존된 솔버 로그 없음';
    $('ewSource').textContent=value.log_source||'';
    $('ewConfig').textContent=JSON.stringify(value.config,null,2);
    const checks=value.checks||{};
    $('ewFacts').textContent=`${model[value.model]||value.model||'모델 미확인'} · ${status[value.status]||value.status}`+
      (value.kind==='warehouse'?' · 수치 수렴 '+(checks.numerical_pass?'해당 시험 통과':'미완료')+' · 실험 검증 미완료':'')+
      (value.error?' · '+value.error:'');
    $('ewView').disabled=!value.has_results;
  }
  async function selectRun(id){
    const token=++generation;runId=id;detail=null;resultId='';renderRuns();
    $('ewResult').hidden=true;$('ewResult').removeAttribute('src');
    clearDetail();$('ewRunTitle').textContent='불러오는 중';
    try{const value=await api('/detail?id='+encodeURIComponent(id));if(token!==generation)return;showDetail(value);message('');}
    catch(e){if(token===generation){clearDetail();message(e.message);}}
  }
  async function viewResult(){
    if(!detail?.has_results)return;
    if(detail.kind==='warehouse'){
      if(resultId!==detail.id){$('ewResult').src='/warehouse/results?id='+encodeURIComponent(detail.rid)+'&embedded=1';resultId=detail.id;}
      $('ewResult').hidden=false;$('ewResult').scrollIntoView({behavior:'smooth',block:'start'});
    }else{
      await selVz(detail.rid);setMode('viz');document.body.classList.add('execution-viewer');
    }
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
  function numberInput(id){const raw=$(id).value.trim();if(!raw||!Number.isFinite(Number(raw)))throw Error('입력값을 확인해 주세요');return Number(raw);}
  async function openRun(){
    if(data.busy||pending)return;
    try{
      const result=await api('/template');draft=result.config;
      $('ewName').value='실행 '+new Date().toLocaleString('ko-KR');
      $('ewEnd').value=draft.numerics.end_s;$('ewDt').value=draft.numerics.dt_s;
      $('ewWrite').value=draft.numerics.write_interval_s;$('ewRefinement').value=draft.porous_mesh.refinement;
      $('ewTemperature').value=draft.coupled.initial_temperature_C;$('ewProcesses').value=draft.coupled.processes;
      $('ewAdvanced').value=JSON.stringify(draft,null,2);$('ewAdvancedBox').open=false;
      $('ewFormError').textContent='';$('ewDialog').showModal();
    }catch(e){message(e.message);}
  }
  function configFromForm(){
    const config=structuredClone(draft);
    config.numerics.end_s=numberInput('ewEnd');config.numerics.dt_s=numberInput('ewDt');config.numerics.write_interval_s=numberInput('ewWrite');
    config.porous_mesh.refinement=numberInput('ewRefinement');config.coupled.initial_temperature_C=numberInput('ewTemperature');config.coupled.processes=numberInput('ewProcesses');
    return config;
  }
  function lockForm(value){pending=value;for(const e of $('ewForm').querySelectorAll('input,select,textarea,button'))e.disabled=value;}
  async function startRun(event){
    event.preventDefault();if(pending)return;
    const targetProject=projectId;
    try{
      const config=configFromForm();lockForm(true);$('ewFormError').textContent='';
      const result=await api('/start',{project_id:targetProject,name:$('ewName').value,config});
      $('ewDialog').close();await refresh();await selectProject(targetProject);await selectRun(result.result.run_key);message('계산 시작');
    }catch(e){$('ewFormError').textContent=e.message;}
    finally{lockForm(false);renderProjects();}
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
body.grouped #secRun,body.grouped #secData{display:none!important}body.grouped #dash{display:flex!important}body.grouped.execution-viewer #dash{display:none!important}
body.grouped #dash>.dlog{flex:none;display:block;min-height:0}body.grouped #dash>:not(.dlog){display:none!important}body.grouped .dlog>pre,body.grouped .dlog>.dlab{display:none!important}
#ewSidebar{padding:16px}#ewSidebar h2{font-size:14px}#ewProjects{display:grid;gap:8px;margin:12px 0}.ew-project{width:100%;text-align:left;padding:12px;border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:8px;cursor:pointer}.ew-project strong,.ew-project span{display:block}.ew-project span{font-size:12px;color:var(--muted);margin-top:5px}.ew-project.selected{border-color:#3987e5}
#ewPanel{display:grid;gap:14px;min-width:0}#ewPanel h2,#ewPanel h3{margin:0;font-size:17px}.ew-bar{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.ew-bar h2,.ew-bar h3{flex:1}.ew-table{max-height:320px;overflow:auto;border:1px solid var(--line);border-radius:8px}#ewPanel table{width:100%;border-collapse:collapse}#ewPanel th,#ewPanel td{text-align:left;padding:10px;border-bottom:1px solid var(--line)}#ewPanel th{position:sticky;top:0;background:var(--surface)}#ewPanel tr.selected{background:rgba(57,135,229,.16)}.ew-run{color:var(--ink);background:none;border:0;text-align:left;cursor:pointer;overflow-wrap:anywhere}#ewRows td:first-child{width:56%}#ewSearch{max-width:320px;padding:8px;background:var(--surface);color:var(--ink);border:1px solid var(--line)}
#ewLog,#ewConfig{max-height:280px!important;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;padding:12px;background:var(--page);border-radius:6px}#ewSource,#ewFacts,#ewMessage{font-size:12px;overflow-wrap:anywhere;color:var(--ink2)}#ewMessage{color:#e1b95d}#ewResult{width:100%;height:850px;border:0;background:white;border-radius:8px}#ewResult[hidden]{display:none}#ewDialog{width:min(650px,95vw);max-height:90vh;overflow:auto;border:1px solid var(--line);border-radius:12px;background:var(--surface);color:var(--ink);padding:22px}#ewDialog::backdrop{background:#0009}#ewForm{display:grid;gap:14px}.ew-inputs{display:grid;grid-template-columns:1fr 1fr;gap:12px}#ewForm label{display:grid;gap:5px}#ewForm input,#ewForm select,#ewForm textarea{font:inherit;padding:9px;background:var(--page);color:var(--ink);border:1px solid var(--line);width:100%;box-sizing:border-box}#ewAdvanced{height:240px;font:12px monospace!important}#ewFormError{color:#ff9c8a}#ewForm ul{padding-left:20px;color:var(--ink2);font-size:12px}@media(max-width:700px){.ew-inputs{grid-template-columns:1fr}#ewPanel th,#ewPanel td{padding:6px;font-size:12px}#ewRows td:first-child{width:auto}}
`;document.head.append(style);
    const sidebar=node('section',null);sidebar.id='ewSidebar';sidebar.append(node('h2','프로젝트'),button('새 프로젝트',createProject));
    const projects=node('div');projects.id='ewProjects';sidebar.append(projects,button('실행 목록',showList));$('side').prepend(sidebar);
    const panel=node('section');panel.id='ewPanel';panel.innerHTML=`
<div class="ew-bar"><h2 id="ewTitle">프로젝트</h2><button id="ewRename" class="btn">이름 변경</button><button id="ewNewRun" class="btn pri">새 CFD 실행</button></div>
<p id="ewMessage" role="status"></p><div class="ew-bar"><h3>실행 목록</h3><input id="ewSearch" aria-label="실행 검색" placeholder="실행 검색"></div>
<div class="ew-table"><table><thead><tr><th>실행</th><th>모델</th><th>상태</th><th>계산 범위</th></tr></thead><tbody id="ewRows"></tbody></table></div>
<div class="ew-bar"><h3 id="ewRunTitle">실행 선택</h3><button id="ewView" class="btn" disabled>결과 보기</button></div><p id="ewFacts"></p>
<details><summary>실행 설정</summary><pre id="ewConfig"></pre></details>
<h3>솔버 로그</h3><p id="ewSource"></p><pre id="ewLog"></pre><iframe id="ewResult" title="선택한 실행 결과" hidden></iframe>`;
    document.querySelector('#dash .dlog').append(panel);
    const dialog=node('dialog');dialog.id='ewDialog';dialog.innerHTML=`<form id="ewForm"><h2>새 CFD 실행</h2>
<label>실행 이름<input id="ewName" required maxlength="80"></label><div class="ew-inputs">
<label>종료시간 (s)<input id="ewEnd" type="number" min="0.001" step="any" required></label><label>저장 간격 (s)<input id="ewWrite" type="number" min="0.001" step="any" required></label>
<label>계산 간격 (s)<input id="ewDt" type="number" min="0.000001" step="any" required></label><label>격자 세분화<select id="ewRefinement"><option value="1">1단계 · 1,860셀</option><option value="2">2단계 · 14,880셀</option><option value="4">3단계 · 119,040셀</option></select></label>
<label>초기 실내 온도 (°C)<input id="ewTemperature" type="number" min="5" max="40" step="any" required></label><label>CPU 프로세스 수<input id="ewProcesses" type="number" min="1" max="8" step="1" required></label></div>
<ul><li>모델: 저장고 유속·온도·ClO₂ 농도 연결</li><li>누출 제외, 균질 다공성 곡물, 미보정 물성</li><li>외기온: 문헌 시간변화 입력</li><li>실행마다 설정과 결과를 별도 보관</li><li>프로젝트에 고정 설정 없음</li></ul>
<details id="ewAdvancedBox"><summary>전체 설정</summary><textarea id="ewAdvanced" aria-label="전체 설정"></textarea><button id="ewApply" type="button" class="btn">설정 적용</button></details>
<p id="ewFormError" role="alert"></p><div class="ew-bar"><button id="ewCancel" type="button" class="btn">취소</button><button type="submit" class="btn pri">계산 시작</button></div></form>`;document.body.append(dialog);
    $('ewNewRun').onclick=openRun;$('ewRename').onclick=renameProject;$('ewView').onclick=viewResult;$('ewSearch').oninput=renderRuns;
    $('ewCancel').onclick=()=>dialog.close();dialog.addEventListener('cancel',e=>{if(pending)e.preventDefault();});$('ewForm').onsubmit=startRun;
    $('ewApply').onclick=()=>{try{const v=JSON.parse($('ewAdvanced').value);if(!v.numerics||!v.coupled||!v.porous_mesh)throw Error('저장고 연결 설정이 필요합니다');draft=v;
      $('ewEnd').value=v.numerics.end_s;$('ewDt').value=v.numerics.dt_s;$('ewWrite').value=v.numerics.write_interval_s;$('ewRefinement').value=v.porous_mesh.refinement;$('ewTemperature').value=v.coupled.initial_temperature_C;$('ewProcesses').value=v.coupled.processes;$('ewFormError').textContent='설정 적용 완료';}catch(e){$('ewFormError').textContent=e.message;}};
    $('mCFD').onclick=showList;$('mViz').onclick=viewResult;
    document.body.classList.add('grouped');showList();
  }
  mount();refresh();setInterval(refresh,4000);
})();
