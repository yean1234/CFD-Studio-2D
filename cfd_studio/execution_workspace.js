/* Project containers do not own solver settings. Each launch takes a snapshot. */
(() => {
  const $ = id => document.getElementById(id);
  const selectedRuns=new Map();
  let data = {projects: []}, projectId = '', runId = '', generation = 0, detail = null;
  let queuePending=false;let pending=false, refreshing=false, projectSignature='',runSignature='',viewMode='cfd',preferredTemplate='warehouse',presets=[];
  const status = {complete:'완료', failed:'실패', running:'계산 중', queued:'대기', draft:'대기', stopped:'중단', preparing:'준비 중', saved:'보관'};
  const stateText=r=>(status[r.status]||r.status)+(r.completion_reason==='limit'?' · 한계 도달':'');
  const model = {warehouse:'저장고 연결',clo2_coupled_scenario:'저장고 연결', clo2_plan_scenario:'저장고 확산', normalized_gable_verification:'정규화 시험', gas_transport:'추적자 시험', immersion:'액침냉각', grain_silo:'단상 저장고'};
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
  function showList(){viewMode='cfd';suspendWarehouseViewer();setPlay(false,true);setMode('cfd');document.body.classList.remove('execution-viewer','warehouse-viewer');$('appContext').textContent='CFD Studio · '+(currentProject()?.name||'프로젝트');}
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
    $('ewDescription').textContent=currentProject()?.description||'';
    $('ewDefault').textContent='기본 프리셋: '+(presets.find(p=>p.id===currentProject()?.default_preset)?.name||'미지정');
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
      const diff=node('td',r.differences?.length?`${r.differences.length}개 변경`:'—');diff.title=(r.differences||[]).map(x=>x.path+': '+JSON.stringify(x.before)+' → '+JSON.stringify(x.after)).join('\n');
      tr.append(td,node('td',model[r.model]||r.model||'미확인'),diff,node('td',stopText(r.termination,r.end_s)),node('td',stateText(r)+(r.status==='draft'?' · 미등록':'')),node('td',r.last_saved==null?'—':r.last_saved+' '+(r.time_unit||'s')),node('td',{passed:'통과',incomplete:'미완료',unchecked:'미검사'}[r.numerical_status]||'미검사'),node('td',resultText(r)));rows.append(tr);
    }
    if(!rows.children.length){const tr=node('tr'), td=node('td',search?'검색 결과 없음':'실행 이력 없음');td.colSpan=8;tr.append(td);rows.append(tr);}
  }
  async function selectProject(id){
    projectId=id;runId='';detail=null;generation++;suspendWarehouseViewer();setPlay(false,true);
    $('ewSearch').value='';renderProjects();renderRuns();
    try{localStorage.setItem('cfd-project',id);}catch(_){}
    const runs=currentProject()?.runs||[];
    const recent=runs.find(r=>r.id===selectedRuns.get(id))||runs.find(r=>r.status==='running')||runs.find(r=>r.has_results)||runs[0];
    if(recent)await selectRun(recent.id);else{clearDetail();showList();}
  }
  function clearDetail(){
    $('ewRunTitle').textContent='실행 선택';$('ewLog').textContent='목록에서 실행을 선택하세요.';
    $('ewSource').textContent='';$('ewConfigSummary').textContent='';$('ewFacts').textContent='';$('ewView').disabled=true;$('ewSettings').disabled=true;$('ewSidebarSettings').disabled=true;$('ewEnqueue').disabled=true;$('ewFolder').disabled=true;$('ewStop').hidden=true;$('ewDifferences').textContent='';$('ewGoals').textContent='';
  }
  function showDetail(value){
    detail=value;const row=currentProject()?.runs.find(r=>r.id===value.id);if(row){for(const k of ['result_status','last_saved','numerical_status','has_results','frame_counts'])if(k in value)row[k]=value[k];renderRuns();}$('ewRunTitle').textContent=value.name;$('ewLog').textContent=value.log||'보존된 솔버 로그 없음';
    $('ewSource').textContent=value.log_source||'';
    $('ewConfigSummary').textContent=CFDSettings.summary(value.config);$('ewSettings').disabled=false;$('ewSidebarSettings').disabled=false;
    const checks=value.checks||{};
    $('ewFacts').textContent=`${model[value.model]||value.model||'모델 미확인'} · ${stateText(value)}`+
      (value.kind==='warehouse'?' · 수치 수렴 '+(checks.numerical_pass?'해당 시험 통과':'미완료')+' · 실험 검증 미완료':'')+
      (value.frames!=null?' · 저장 '+value.frames+'프레임':'')+(value.error?' · '+value.error:'');
    $('ewView').textContent=value.result_status==='update'?'업데이트':value.has_results?'열기':'생성';$('ewView').disabled=!value.has_results&&!value.can_generate;
    $('ewSettings').textContent=value.editable?'설정 편집':'설정 보기';$('ewSidebarSettings').textContent=value.editable?'설정 편집':'설정 보기';
    $('ewEnqueue').disabled=value.status!=='draft';$('ewStop').hidden=value.status!=='running';$('ewFolder').disabled=!value.path;
    $('ewDifferences').textContent=(value.differences||[]).map(x=>x.path+': '+JSON.stringify(x.before)+' → '+JSON.stringify(x.after)).join('\n')||'기준 설정과 차이 없음';
    $('ewGoals').textContent=value.goals||'';
  }
  async function selectRun(id){
    const token=++generation;runId=id;selectedRuns.set(projectId,id);detail=null;renderRuns();suspendWarehouseViewer();setPlay(false,true);
    clearDetail();$('ewRunTitle').textContent='불러오는 중';
    try{const value=await api('/detail?id='+encodeURIComponent(id));if(token!==generation)return;showDetail(value);message('');if(viewMode==='viewer')await viewResult();}
    catch(e){if(token===generation){clearDetail();message(e.message);}}
  }
  async function viewResult(){
    if(!detail){viewMode='viewer';message('실행 정보를 불러오는 중입니다.');return;}
    if(detail.can_generate&&(!detail.has_results||detail.result_status==='update')){await prepareResult();return;}
    if(!detail.has_results){showList();message('선택한 실행의 결과가 아직 없습니다. 설정과 로그를 확인하세요.');return;}
    const selected=detail,token=generation;viewMode='viewer';setPlay(false,true);
    document.body.classList.add('execution-viewer');
    document.body.classList.toggle('warehouse-viewer',selected.kind==='warehouse');
    cancelViewerLoad();
    if(selected.kind!=='warehouse'){restoreWarehouseUI();VIZCFG=selected.config||null;VPROJ=selected.rid;}
    setMode('viz');
    if(selected.kind==='warehouse'){
      if(token!==generation||viewMode!=='viewer')return;
      await loadWarehouseResult(selected.rid,selected.name);
    }else{await selVz(selected.rid);}
  }
  function inspectSettings(){
    if(!detail)return;if(detail.editable){openRun(detail.config,detail);return;}const snapshot=structuredClone(detail);
    CFDSettings.open({config:snapshot.config,managed:!!snapshot.termination,readonly:true,title:'설정 보기 · '+snapshot.name,name:snapshot.name,onClone:config=>openRun(config)});
  }
  async function refresh(){
    if(refreshing){await new Promise(resolve=>setTimeout(resolve,50));return refresh();}refreshing=true;
    try{
      const [value,presetData]=await Promise.all([api(''),api('/presets')]);data=value;presets=presetData.presets;renderPresets();renderQueue();
      if(!projectId||!data.projects.some(p=>p.id===projectId)){
        let saved='';try{saved=localStorage.getItem('cfd-project')||'';}catch(_){}
        await selectProject(data.projects.find(p=>p.id===saved)?.id||data.projects[0]?.id);
      }else{renderProjects();renderRuns();}
      if(runId&&!pending){const token=generation;const v=await api('/detail?id='+encodeURIComponent(runId));if(token===generation)showDetail(v);}
    }catch(e){message(e.message);}finally{refreshing=false;}
  }
  function stopText(t,end){if(!t)return end==null?'—':end+' s';return t.mode==='frames'?t.frames+' 프레임 · 초기 '+(t.include_initial?'포함':'제외'):t.mode==='time'?t.time_s+' s':'수렴 기준';}
  function resultText(r){return {ready:'준비됨',update:'새 데이터',preparing:'변환 중',none:'없음'}[r.result_status]||'없음';}
  function renderPresets(){const select=$('ewPresetPicker'),value=select.value,signature=JSON.stringify(presets);if(select.dataset.signature===signature)return;select.dataset.signature=signature;select.replaceChildren(new Option('프리셋 선택',''));for(const p of presets)select.append(new Option(p.name,p.id));select.value=presets.some(p=>p.id===value)?value:'';}
  function renderQueue(){const q=data.queue||{},box=$('ewQueue');box.replaceChildren();const all=data.projects.flatMap(p=>p.runs);$('ewQueueState').textContent=q.failure?'실패 확인 필요':q.paused?(q.active?'현재 실행 후 일시정지':'일시정지'):q.active||q.order?.length?'순차 실행':'대기열 완료';
    for(const [i,id] of (q.order||[]).entries()){const r=all.find(r=>r.id===id),row=node('div',null,'ew-bar');row.append(node('span',(i+1)+'. '+(data.projects.find(p=>p.id===r?.project_id)?.name||'프로젝트')+' / '+(r?.name||id)));const move=delta=>{const order=[...q.order],j=i+delta;if(j<0||j>=order.length)return;[order[i],order[j]]=[order[j],order[i]];queueAction('reorder',{ids:order});};const up=button('↑',()=>move(-1)),down=button('↓',()=>move(1));up.title='실행 순서 위로';down.title='실행 순서 아래로';up.disabled=i===0;down.disabled=i===q.order.length-1;row.append(up,down,button('제외',()=>queueAction('remove',{id})));box.append(row);}
    $('ewQueueStart').disabled=!!q.failure||(!q.order?.length&&!q.active);$('ewQueuePause').disabled=!!q.paused||(!q.active&&!q.order?.length);$('ewFailures').hidden=!q.failure;$('ewRetry').hidden=!q.failure;$('ewSkip').hidden=!q.failure;
    if(queuePending)for(const b of document.querySelectorAll('#ewQueue button,#ewQueueStart,#ewQueuePause,#ewRetry,#ewSkip,#ewEnqueue,#ewStop'))b.disabled=true;
    $('ewQueueError').textContent=q.failure?(all.find(r=>r.id===q.failure)?.error||'중단한 실행을 확인하세요'):q.service_error||'';
  }
  async function queueAction(action,extra={}){if(queuePending)return;queuePending=true;renderQueue();try{await api('/queue',{action,...extra});await refresh();}catch(e){message(e.message);}finally{queuePending=false;renderQueue();if(detail)showDetail(detail);}}
  async function openRun(source,editing=null){
    if(pending)return;
    try{
      const targetProject=projectId,projectName=currentProject()?.name;
      let sourceId=editing?.preset_id||currentProject()?.default_preset||preferredTemplate;
      const [presetData,result]=await Promise.all([api('/presets'),source?Promise.resolve({config:structuredClone(source)}):api('/template?id='+encodeURIComponent(sourceId))]);
      const prepare=config=>{const c=structuredClone(config);if(CFDSettings.kind(c)==='immersion'&&!c.run.output_fields)c.run.output_fields=['bubble','phase','flow','therm'];return c;};
      CFDSettings.open({config:prepare(result.config),managed:true,submitLabel:'실행 저장',name:editing?.name,title:editing?'실행 설정':'CFD 실행 추가 · '+projectName,presets:presetData.presets,
        onLoad:async id=>{sourceId=id;return prepare((await api('/template?id='+encodeURIComponent(id))).config);},
        onRun:async(name,config,extra)=>{
          pending=true;renderProjects();try{
            const saved=await api('/case',{project_id:targetProject,name,config,id:editing?.id,revision:editing?.revision,preset_id:sourceId,...extra});
            showList();await refresh();if(saved.result.preset)$('ewPresetPicker').value=saved.result.preset.id;await selectProject(targetProject);await selectRun(saved.result.run_key);message('실행 저장 완료');
          }finally{pending=false;renderProjects();}
        }
      });
    }catch(e){message(e.message);}
  }
  async function projectDialog(edit=false){
    try{const ps=(await api('/presets')).presets,p=edit?currentProject():null,d=node('dialog');d.className='ew-dialog';d.innerHTML='<form><h2></h2><label>프로젝트 이름<input name="name" required maxlength="80"></label><label>프로젝트 설명<textarea name="description" maxlength="4000" rows="3"></textarea></label><label>기본 설정 프리셋<select name="preset"><option value="">미지정</option></select></label><p role="alert"></p><div class="ew-bar"><button class="btn pri" type="submit">저장</button><button class="btn" type="button">취소</button></div></form>';d.querySelector('h2').textContent=edit?'프로젝트 설정':'새 프로젝트';const f=d.querySelector('form');f.elements.name.value=p?.name||'';f.elements.description.value=p?.description||'';for(const item of ps)f.elements.preset.append(new Option(item.name,item.id));f.elements.preset.value=p?.default_preset||'';f.querySelector('[type=button]').onclick=()=>d.close();d.onclose=()=>d.remove();f.onsubmit=async e=>{e.preventDefault();if(pending)return;pending=true;renderProjects();f.querySelector('[type=submit]').disabled=true;try{const result=await api(edit?'/project-edit':'/project',{id:p?.id,name:f.elements.name.value,description:f.elements.description.value,default_preset:f.elements.preset.value||null});await refresh();await selectProject(result.result.id);d.close();}catch(err){f.querySelector('[role=alert]').textContent=err.message;}finally{pending=false;renderProjects();f.querySelector('[type=submit]').disabled=false;}};document.body.append(d);d.showModal();}catch(e){message(e.message);}
  }
  const createProject=()=>projectDialog(false),renameProject=()=>projectDialog(true);
  async function presetEditor(mode){try{const id=$('ewPresetPicker').value||'warehouse',result=await api('/template?id='+encodeURIComponent(id));if(mode==='rename'){nameBox('프리셋 이름',presets.find(p=>p.id===id)?.name||'',async name=>{try{await api('/preset-rename',{id,name});await refresh();}catch(e){message(e.message);}});return;}
    const editable=mode!=='view';CFDSettings.open({config:result.config,managed:true,purpose:'preset',name:editable?'':presets.find(p=>p.id===id)?.name,title:editable?'새 설정 프리셋':'설정 프리셋',readonly:!editable,submitLabel:'프리셋 저장',onClone:c=>presetEditor('copy'),onRun:async(name,config)=>{await api('/preset',{name,config});await refresh();}});
  }catch(e){message(e.message);}}
  async function prepareResult(){const selected=detail;if(!selected)return;try{await api('/result',{id:selected.id});message('누락된 결과 확인 중');await refresh();}catch(e){message(e.message);}}
  function mount(){
    const style=node('style');style.textContent=`
body.grouped #side>section{flex:0 0 auto;min-height:auto}body.grouped #secRun,body.grouped #secData{display:none!important}body.grouped.execution-viewer #secData{display:block!important}body.grouped #projList2,body.grouped #secData>.fgroup,body.grouped #secData>button[onclick="newProj()"]{display:none!important}#ewRunPicker{width:100%;padding:8px;margin:10px 0;background:var(--surface);color:var(--ink);border:1px solid var(--line)}body.grouped #dash{display:flex!important}body.grouped.execution-viewer #dash{display:none!important}
body.grouped #dash>.dlog{flex:none;display:block;min-height:0}body.grouped #dash>:not(.dlog){display:none!important}body.grouped .dlog>pre,body.grouped .dlog>.dlab{display:none!important}
#ewSidebar{padding:16px}#ewSidebar h2{font-size:14px}#ewProjects{display:grid;gap:8px;margin:12px 0}.ew-project{width:100%;text-align:left;padding:12px;border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:8px;cursor:pointer}.ew-project strong,.ew-project span{display:block}.ew-project span{font-size:12px;color:var(--muted);margin-top:5px}.ew-project.selected{border-color:#3987e5}
#ewPanel{display:grid;gap:10px;min-width:0}#ewPanel h2,#ewPanel h3{margin:0;font-size:17px}.ew-bar{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.ew-bar h2,.ew-bar h3{flex:1}.ew-table{max-height:320px;overflow:auto;border:1px solid var(--line);border-radius:8px}#ewPanel table{width:100%;border-collapse:collapse}#ewPanel th,#ewPanel td{text-align:left;padding:10px;border-bottom:1px solid var(--line)}#ewPanel th{position:sticky;top:0;background:var(--surface)}#ewPanel tr.selected{background:rgba(57,135,229,.16)}.ew-run{color:var(--ink);background:none;border:0;text-align:left;cursor:pointer;overflow-wrap:anywhere}#ewRows td:first-child{min-width:170px;max-width:300px}#ewRows td{font-size:12px}#ewQueue .ew-bar span{flex:1}#ewSearch{max-width:320px;padding:8px;background:var(--surface);color:var(--ink);border:1px solid var(--line)}
#ewLog{max-height:280px!important;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;padding:12px;background:var(--page);border-radius:6px}#ewSource,#ewFacts,#ewMessage,#ewConfigSummary{font-size:12px;overflow-wrap:anywhere;color:var(--ink2)}#ewMessage{color:#e1b95d}@media(max-width:700px){#ewPanel th,#ewPanel td{padding:6px;font-size:12px}#ewRows td:first-child{width:auto}}

#ewPanel [hidden],#ewSidebar [hidden]{display:none!important}#ewPanel p{margin:0;line-height:1.5}#ewPanel p:empty{display:none}#ewDescription,#ewGoals{white-space:pre-wrap}#ewPanel details{margin:0}.ew-dialog{width:min(500px,90vw);background:var(--surface);color:var(--ink);border:1px solid var(--line);border-radius:10px;padding:20px}.ew-dialog::backdrop{background:#000a}.ew-dialog label{display:grid;gap:6px;margin:14px 0}.ew-dialog input,.ew-dialog textarea,.ew-dialog select,#ewPresetPicker{width:100%;background:var(--page);color:var(--ink);border:1px solid var(--line);padding:8px;border-radius:5px}#ewDescription,#ewDefault,#ewGoals,#ewQueueState,#ewQueueError{font-size:12px;color:var(--ink2)}#ewDifferences{white-space:pre-wrap;font-size:11px;max-height:180px;overflow:auto}#ewPresets{border-top:1px solid var(--line);margin-top:16px;padding-top:12px}#ewPresets .ew-bar{gap:5px;margin:8px 0}
`;document.head.append(style);
    const sidebar=node('section',null);sidebar.id='ewSidebar';sidebar.append(node('h2','프로젝트'),button('새 프로젝트',createProject));
    const projects=node('div');projects.id='ewProjects';const picker=node('select');picker.id='ewRunPicker';picker.setAttribute('aria-label','실행 선택');picker.onchange=()=>{if(picker.value)selectRun(picker.value);};const settings=button('설정 보기',inspectSettings);settings.id='ewSidebarSettings';settings.disabled=true;sidebar.append(projects,picker,settings,button('실행 목록',showList));const presetBox=node('section');presetBox.id='ewPresets';presetBox.append(node('h2','설정 프리셋'));const presetSelect=node('select');presetSelect.id='ewPresetPicker';presetSelect.setAttribute('aria-label','설정 프리셋');presetBox.append(presetSelect);const actions=node('div',null,'ew-bar');actions.append(button('새로 만들기',()=>presetEditor('new')),button('열기',()=>presetEditor('view')),button('복제',()=>presetEditor('copy')),button('이름 변경',()=>presetEditor('rename')));presetBox.append(actions);sidebar.append(presetBox);$('side').prepend(sidebar);
    const panel=node('section');panel.id='ewPanel';panel.innerHTML=`
<div class="ew-bar"><h2 id="ewTitle">프로젝트</h2><button id="ewRename" class="btn">프로젝트 설정</button><button id="ewNewRun" class="btn pri">CFD 실행 추가</button></div>
<p id="ewDescription"></p><p id="ewDefault"></p><p id="ewMessage" role="status"></p><div class="ew-bar"><h3>실행 목록</h3><input id="ewSearch" aria-label="실행 검색" placeholder="실행 검색"></div>
<div class="ew-table"><table><thead><tr><th>실행</th><th>모델</th><th>설정 차이</th><th>종료 조건</th><th>실행 상태</th><th>마지막 저장</th><th>수치 검사</th><th>시각화</th></tr></thead><tbody id="ewRows"></tbody></table></div>
<div class="ew-bar"><h3>대기열</h3><span id="ewQueueState"></span><button id="ewQueueStart" class="btn">대기열 시작</button><button id="ewQueuePause" class="btn">다음 실행부터 일시정지</button></div><div id="ewQueue"></div><p id="ewQueueError"></p><div id="ewFailures" class="ew-bar" hidden><button id="ewRetry" class="btn" hidden>재시도</button><button id="ewSkip" class="btn" hidden>건너뛰기</button></div>
<div class="ew-bar"><h3 id="ewRunTitle">실행 선택</h3><button id="ewView" class="btn" disabled>결과 보기</button></div><p id="ewFacts"></p><p id="ewGoals"></p><div class="ew-bar"><button id="ewEnqueue" class="btn" disabled>대기열에 추가</button><button id="ewStop" class="btn" hidden>실행 중단</button><button id="ewFolder" class="btn" disabled>결과 폴더</button></div><details><summary>설정 차이</summary><pre id="ewDifferences"></pre></details>
<div class="ew-bar"><p id="ewConfigSummary"></p><button id="ewSettings" class="btn" disabled>설정 보기</button></div>
<h3>솔버 로그</h3><p id="ewSource"></p><pre id="ewLog"></pre>`;
    document.querySelector('#dash .dlog').append(panel);
    $('ewNewRun').onclick=()=>openRun();$('ewRename').onclick=renameProject;$('ewView').onclick=viewResult;$('ewSearch').oninput=renderRuns;$('ewSettings').onclick=inspectSettings;
    $('ewEnqueue').onclick=()=>queueAction('enqueue',{ids:[runId]});$('ewQueueStart').onclick=()=>queueAction('resume');$('ewQueuePause').onclick=()=>queueAction('pause');$('ewRetry').onclick=()=>queueAction('retry',{id:data.queue.failure});$('ewSkip').onclick=()=>queueAction('skip',{id:data.queue.failure});$('ewStop').onclick=()=>queueAction('stop',{id:runId});$('ewFolder').onclick=async()=>{try{await api('/folder',{id:runId});}catch(e){message(e.message);}};
    $('mCFD').onclick=showList;$('mViz').onclick=viewResult;
    document.body.classList.add('grouped');showList();
  }
  mount();refresh();setInterval(refresh,4000);
})();
