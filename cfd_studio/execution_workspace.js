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
  function badge(text,state){const b=node('span',text,'ew-badge');b.dataset.state=state||'';return b;}
  function numericalText(r){return {passed:'통과',incomplete:'미완료',unchecked:'미검사'}[r.numerical_status]||'미검사';}
  function renderRuns(){
    const rows=$('ewRows'), p=currentProject(), search=$('ewSearch').value.toLowerCase();
    const signature=JSON.stringify([projectId,runId,search,p?.runs]);
    if(signature===runSignature)return;runSignature=signature;
    rows.replaceChildren();
    const picker=$('ewRunPicker');picker.replaceChildren(new Option('실행 선택',''));for(const r of p?.runs||[])picker.append(new Option(r.name,r.id));picker.value=runId;picker.title=p?.runs.find(r=>r.id===runId)?.name||'실행 선택';
    for(const r of p?.runs||[]){
      if(!`${r.name} ${r.model}`.toLowerCase().includes(search))continue;
      const row=button('',()=>selectRun(r.id),'ew-run-card');row.classList.toggle('selected',r.id===runId);row.setAttribute('aria-pressed',String(r.id===runId));
      const top=node('div',null,'ew-run-top'),name=node('strong',r.name);name.title=r.name;top.append(name,badge(stateText(r)+(r.status==='draft'?' · 초안':''),r.status));
      const meta=node('div',null,'ew-run-meta');meta.append(node('span',model[r.model]||r.model||'미확인'),node('span',stopText(r.termination,r.end_s)));
      const bottom=node('div',null,'ew-run-meta');bottom.append(node('span',r.differences?.length?`설정 ${r.differences.length}개 변경`:'설정 동일'),node('span',resultText(r)));row.append(top,meta,bottom);
      row.title=`${r.name}
마지막 저장 ${r.last_saved==null?'—':r.last_saved+' '+(r.time_unit||'s')} · 수치 검사 ${numericalText(r)}`;rows.append(row);
    }
    $('ewRunCount').textContent=String(p?.runs.length||0);
    if(!rows.children.length)rows.append(node('div',search?'검색 결과 없음':'아직 실행이 없습니다.','ew-empty'));
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
    $('ewStatus').replaceChildren();$('ewStats').replaceChildren();$('ewProgress').hidden=true;$('ewRunError').textContent='';$('ewStopLabel').textContent='—';$('ewDifferenceCount').textContent='';$('ewConfigSummary').textContent='';$('ewFacts').textContent='';$('ewView').disabled=true;$('ewSettings').disabled=true;$('ewSidebarSettings').disabled=true;$('ewEnqueue').disabled=true;$('ewFolder').disabled=true;$('ewStop').hidden=true;$('ewDifferences').textContent='';$('ewGoals').textContent='';
  }
  function showDetail(value){
    detail=value;const row=currentProject()?.runs.find(r=>r.id===value.id);if(row){for(const k of ['result_status','last_saved','numerical_status','has_results','frame_counts'])if(k in value)row[k]=value[k];renderRuns();}$('ewRunTitle').textContent=value.name;$('ewLog').textContent=value.log||'보존된 솔버 로그 없음';
    $('ewStatus').replaceChildren(badge(stateText(value),value.status));
    $('ewConfigSummary').textContent=CFDSettings.summary(value.config);$('ewSettings').disabled=false;$('ewSidebarSettings').disabled=false;
    const checks=value.checks||{};
    $('ewFacts').textContent=model[value.model]||value.model||'모델 미확인';
    $('ewStats').replaceChildren();
    for(const [label,text,state] of [['마지막 저장',value.last_saved==null?'—':value.last_saved+' '+(value.time_unit||'s'),''],['수치 검사',numericalText(value),value.numerical_status],['시각화',resultText(value),value.result_status]]){const card=node('div',null,'ew-stat');card.append(node('span',label),badge(text,state));$('ewStats').append(card);}
    $('ewRunError').textContent=value.error||'';
    const progress=value.end_s>0&&value.last_saved!=null; $('ewProgress').hidden=!progress;
    if(progress){const pct=Math.min(100,Math.max(0,100*value.last_saved/value.end_s));$('ewProgressFill').style.width=pct+'%';$('ewProgressLabel').textContent='저장 진행';$('ewProgressValue').textContent=Math.round(pct)+'%';}
    $('ewStopLabel').textContent=stopText(value.termination,value.end_s);
    $('ewView').textContent=value.result_status==='update'?'업데이트':value.has_results?'열기':'생성';$('ewView').disabled=!value.has_results&&!value.can_generate;
    $('ewSettings').lastChild.textContent=value.editable?'설정 편집':'설정 보기';$('ewSidebarSettings').textContent=value.editable?'설정 편집':'설정 보기';
    $('ewEnqueue').disabled=value.status!=='draft';$('ewEnqueue').hidden=!value.editable;$('ewStop').hidden=value.status!=='running';$('ewFolder').disabled=!value.path;
    $('ewDifferences').textContent=(value.differences||[]).map(x=>x.path+': '+JSON.stringify(x.before)+' → '+JSON.stringify(x.after)).join('\n')||'기준 설정과 차이 없음';
    $('ewGoals').textContent=value.goals||'';$('ewDifferenceCount').textContent=value.differences?.length?value.differences.length+'개 변경':'변경 없음';
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
  function renderQueue(){const q=data.queue||{},box=$('ewQueue');box.replaceChildren();$('ewQueueCard').hidden=!q.active&&!q.order?.length&&!q.failure&&!q.service_error;const all=data.projects.flatMap(p=>p.runs);$('ewQueueState').textContent=q.failure?'실패 확인 필요':q.paused?(q.active?'현재 실행 후 일시정지':'일시정지'):q.active||q.order?.length?'순차 실행':'대기열 완료';
    for(const [i,id] of (q.order||[]).entries()){const r=all.find(r=>r.id===id),row=node('div',null,'ew-bar ew-queue-row');row.append(node('span',(i+1)+'. '+(data.projects.find(p=>p.id===r?.project_id)?.name||'프로젝트')+' / '+(r?.name||id)));const move=delta=>{const order=[...q.order],j=i+delta;if(j<0||j>=order.length)return;[order[i],order[j]]=[order[j],order[i]];queueAction('reorder',{ids:order});};const up=button('↑',()=>move(-1)),down=button('↓',()=>move(1));up.title='실행 순서 위로';down.title='실행 순서 아래로';up.disabled=i===0;down.disabled=i===q.order.length-1;row.append(up,down,button('제외',()=>queueAction('remove',{id})));box.append(row);}
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
body.grouped #side>section{flex:0 0 auto;min-height:auto}body.grouped #secRun,body.grouped #secData{display:none!important}body.grouped.execution-viewer #secData{display:block!important}body.grouped #projList2,body.grouped #secData>.fgroup,body.grouped #secData>button[onclick="newProj()"]{display:none!important}
body.grouped #dash{display:block!important;padding:20px}body.grouped.execution-viewer #dash{display:none!important}body.grouped #dash>.dlog{padding:0;border:0;background:none;border-radius:0;display:block}body.grouped #dash>:not(.dlog),body.grouped .dlog>pre,body.grouped .dlog>.dlab{display:none!important}
#ewSidebar{padding:16px}#ewSidebar h2{font-size:11px;color:var(--muted);font-weight:600;margin:0 0 12px}#ewProjects{display:grid;gap:6px;margin:12px 0 18px;max-height:32vh;overflow:auto}.ew-project{width:100%;text-align:left;padding:12px;border:1px solid var(--line);background:transparent;color:var(--ink);border-radius:8px;cursor:pointer}.ew-project strong,.ew-project span{display:block}.ew-project strong{font-size:13px}.ew-project span{font-size:11px;color:var(--muted);margin-top:5px}.ew-project.selected{border-color:var(--s1);background:rgba(57,135,229,.07)}
#ewRunPicker{width:100%;margin:0 0 8px}body.grouped:not(.execution-viewer) #ewRunPicker,body.grouped:not(.execution-viewer) #ewSidebarSettings,body.grouped:not(.execution-viewer) #ewBack{display:none}#ewSidebarSettings,#ewBack{width:100%;margin-bottom:6px}#ewPresets{border:0;border-top:1px solid var(--line);margin-top:20px;padding:18px 0 0}#ewPresets .ew-bar{display:grid;grid-template-columns:1fr 1fr;gap:7px}#ewPresetPicker{margin-bottom:10px}
#ewPanel{padding:0;border:0;min-width:0}#ewPanel [hidden],#ewSidebar [hidden]{display:none!important}#ewPanel h2,#ewPanel h3,#ewPanel p{margin:0}#ewPanel h2{font-size:21px;letter-spacing:-.5px}#ewPanel h3{font-size:13px}#ewPanel p:empty{display:none}.ew-bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.ew-bar h2,.ew-bar h3{flex:1;min-width:0}.ew-heading{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:18px}.ew-heading .ew-bar{flex-shrink:0}#ewDescription{font-size:12px;color:var(--ink2);margin-top:7px!important;white-space:pre-wrap}#ewDefault{font-size:11px;color:var(--muted);margin-top:8px!important}
.ew-layout{display:grid;grid-template-columns:minmax(260px,.8fr) minmax(340px,1.25fr);gap:14px;align-items:start}.ew-list-panel,.ew-detail-panel,.ew-queue-card{background:var(--surface);border:1px solid var(--line);border-radius:12px;overflow:hidden;min-width:0}.ew-list-heading{padding:16px 16px 12px}.ew-list-heading .ew-bar{margin-bottom:12px}#ewRunCount{font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums}#ewSearch{width:100%;height:34px;padding:0 11px;border:1px solid var(--line);border-radius:7px;color:var(--ink);background:var(--page);font:inherit;font-size:12px}#ewRows{grid-template-columns:minmax(0,1fr);max-height:calc(100vh - 290px);min-height:180px;overflow-y:auto;padding:0 8px 8px;display:grid;gap:5px}.ew-run-card{min-width:0;display:block;width:100%;padding:12px;text-align:left;background:transparent;border:1px solid transparent;border-radius:8px;color:var(--ink);cursor:pointer;font:inherit}.ew-run-card:hover{background:var(--surface2)}.ew-run-card.selected{background:rgba(57,135,229,.09);border-color:rgba(57,135,229,.6)}.ew-run-top{display:flex;align-items:center;gap:8px;margin-bottom:9px}.ew-run-top strong{min-width:0;font-size:12px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1}.ew-run-meta{display:flex;justify-content:space-between;gap:8px;font-size:10.5px;color:var(--muted);margin-top:5px}.ew-run-meta span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ew-badge{display:inline-flex;align-items:center;gap:5px;font-size:11px;white-space:nowrap;color:var(--ink2)}.ew-badge::before{content:'';width:5px;height:5px;border-radius:50%;background:var(--muted)}.ew-badge[data-state=complete],.ew-badge[data-state=ready],.ew-badge[data-state=passed]{color:#70ce9d}.ew-badge[data-state=complete]::before,.ew-badge[data-state=ready]::before,.ew-badge[data-state=passed]::before{background:#70ce9d}.ew-badge[data-state=failed]{color:#ed9288}.ew-badge[data-state=failed]::before{background:#ed9288}.ew-badge[data-state=running],.ew-badge[data-state=queued]{color:#88bafd}.ew-badge[data-state=running]::before,.ew-badge[data-state=queued]::before{background:#88bafd}
.ew-detail-head{padding:20px;border-bottom:1px solid var(--line)}#ewRunTitle{font-size:16px!important;line-height:1.5;overflow-wrap:anywhere;margin:10px 0 14px!important}#ewFacts{font-size:11px;color:var(--muted)}.ew-detail-head>.ew-bar:first-child{justify-content:space-between}.ew-detail-actions{display:flex;gap:8px;flex-wrap:wrap}.ew-detail-actions .pri{margin-left:auto}#ewStats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:0;margin:18px 0 0}.ew-stat{display:grid;gap:8px;padding:0 12px;border-left:1px solid var(--line);min-width:0}.ew-stat:first-child{padding-left:0;border:0}.ew-stat>span:first-child{font-size:10px;color:var(--muted)}.ew-stat .ew-badge{font-size:13px}.ew-stat .ew-badge[data-state='']::before{display:none}#ewProgress{margin-top:18px}#ewProgress .ew-bar{justify-content:space-between;margin-bottom:7px;color:var(--muted);font-size:10px}#ewProgress .pbar{height:5px}
.ew-detail-body{padding:16px 20px}.ew-setting-line{display:flex;justify-content:space-between;gap:12px;font-size:11px;color:var(--muted);margin-bottom:12px}#ewStopLabel{color:var(--ink2)}#ewGoals{font-size:12px;line-height:1.6;color:var(--ink2);white-space:pre-wrap;margin-bottom:12px!important}#ewConfigSummary{font-size:11px;color:var(--muted);line-height:1.5;margin-bottom:12px!important}#ewDifferenceBox{border-top:1px solid var(--line);padding:12px 0 0;font-size:11px;color:var(--muted)}#ewDifferenceCount{float:right}#ewDifferences{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px;max-height:180px;overflow:auto}#ewLogBox{border-top:1px solid var(--line);padding:14px 20px}#ewLogBox summary{font-size:11px;color:var(--ink2)}#ewLog{height:180px;max-height:35vh;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;font:10px/1.6 monospace;color:var(--muted);padding:12px;background:var(--page);border-radius:6px;margin:12px 0 0}
#ewMessage,#ewRunError,#ewQueueError{font-size:12px;color:#e0ac77;line-height:1.6;overflow-wrap:anywhere}#ewMessage:not(:empty){margin-bottom:14px!important}#ewRunError:not(:empty){margin-top:12px!important}.ew-queue-card{margin-top:14px;padding:14px 18px}.ew-queue-card>summary{list-style:none}.ew-queue-card>summary::-webkit-details-marker{display:none}.ew-queue-card>summary h3:before{content:'▸';color:var(--muted);margin-right:8px}.ew-queue-card[open]>summary h3:before{content:'▾'}#ewQueueState{font-size:11px;color:var(--muted)}.ew-queue-actions{margin:14px 0 8px}#ewQueue .ew-bar span{flex:1;font-size:12px}.ew-queue-row{border-top:1px solid var(--line);padding:9px 0}.ew-queue-row .btn{height:28px;padding:0 9px;font-size:11px}.ew-empty{padding:26px 12px;text-align:center;color:var(--muted);font-size:12px}
.ew-dialog{width:min(500px,90vw);background:var(--surface);color:var(--ink);border:1px solid var(--line);border-radius:12px;padding:22px}.ew-dialog::backdrop{background:#000a}.ew-dialog label{display:grid;gap:6px;margin:14px 0;font-size:12px}.ew-dialog input,.ew-dialog textarea,.ew-dialog select{width:100%;box-sizing:border-box;background:var(--page);color:var(--ink);border:1px solid var(--line);padding:8px;border-radius:7px}.ew-dialog .ew-bar{justify-content:flex-end}
@media(max-width:1100px){.ew-layout{grid-template-columns:1fr}#ewRows{grid-template-columns:minmax(0,1fr);max-height:250px;min-height:100px}.ew-heading{align-items:flex-start}body.grouped #dash{padding:14px}}@media(max-width:720px){.ew-heading{display:block}.ew-heading>.ew-bar{margin-top:12px}#ewStats{grid-template-columns:1fr;gap:12px}.ew-stat{border:0;padding:0}}
`;document.head.append(style);
    const sidebar=node('section',null);sidebar.id='ewSidebar';sidebar.append(node('h2','프로젝트'),button('새 프로젝트',createProject));
    const projects=node('div');projects.id='ewProjects';const picker=node('select');picker.id='ewRunPicker';picker.setAttribute('aria-label','실행 선택');picker.onchange=()=>{if(picker.value)selectRun(picker.value);};const settings=button('설정 보기',inspectSettings);settings.id='ewSidebarSettings';settings.disabled=true;const back=button('실행 목록',showList);back.id='ewBack';sidebar.append(projects,picker,settings,back);const presetBox=node('section');presetBox.id='ewPresets';presetBox.append(node('h2','설정 프리셋'));const presetSelect=node('select');presetSelect.id='ewPresetPicker';presetSelect.setAttribute('aria-label','설정 프리셋');presetBox.append(presetSelect);const actions=node('div',null,'ew-bar');actions.append(button('새로 만들기',()=>presetEditor('new')),button('열기',()=>presetEditor('view')),button('복제',()=>presetEditor('copy')),button('이름 변경',()=>presetEditor('rename')));presetBox.append(actions);sidebar.append(presetBox);$('side').prepend(sidebar);
    const panel=node('section');panel.id='ewPanel';panel.innerHTML=`
<header class="ew-heading"><div><h2 id="ewTitle">프로젝트</h2><p id="ewDescription"></p><p id="ewDefault"></p></div><div class="ew-bar"><button id="ewRename" class="btn">프로젝트 설정</button><button id="ewNewRun" class="btn pri">CFD 실행 추가</button></div></header>
<p id="ewMessage" role="status"></p>
<div class="ew-layout"><div class="ew-list-panel"><div class="ew-list-heading"><div class="ew-bar"><h3>실행 목록</h3><span id="ewRunCount"></span></div><input id="ewSearch" aria-label="실행 검색" placeholder="실행 검색"></div><div id="ewRows" role="group" aria-label="CFD 실행 목록"></div></div>
<div class="ew-detail-panel"><div class="ew-detail-head"><div class="ew-bar"><p id="ewFacts"></p><div id="ewStatus"></div></div><h3 id="ewRunTitle">실행 선택</h3><div class="ew-detail-actions"><button id="ewSettings" class="btn" disabled>설정 보기</button><button id="ewFolder" class="btn" disabled>결과 폴더</button><button id="ewView" class="btn pri" disabled>열기</button><button id="ewEnqueue" class="btn" disabled>대기열에 추가</button><button id="ewStop" class="btn dng" hidden>실행 중단</button></div><div id="ewStats"></div><div id="ewProgress" hidden><div class="ew-bar"><span id="ewProgressLabel"></span><span id="ewProgressValue"></span></div><div class="pbar"><div id="ewProgressFill"></div></div></div><p id="ewRunError" role="alert"></p></div>
<div class="ew-detail-body"><div class="ew-setting-line"><span>종료 조건</span><span id="ewStopLabel">—</span></div><p id="ewConfigSummary"></p><p id="ewGoals"></p><details id="ewDifferenceBox"><summary>설정 차이 <span id="ewDifferenceCount"></span></summary><pre id="ewDifferences"></pre></details></div><details id="ewLogBox"><summary>솔버 로그</summary><pre id="ewLog"></pre></details></div></div>
<details id="ewQueueCard" class="ew-queue-card" open><summary class="ew-bar"><h3>대기열</h3><span id="ewQueueState"></span></summary><div class="ew-bar ew-queue-actions"><button id="ewQueueStart" class="btn pri">대기열 시작</button><button id="ewQueuePause" class="btn">다음 실행부터 일시정지</button></div><div id="ewQueue"></div><p id="ewQueueError"></p><div id="ewFailures" class="ew-bar" hidden><button id="ewRetry" class="btn" hidden>재시도</button><button id="ewSkip" class="btn" hidden>건너뛰기</button></div></details>`;
    document.querySelector('#dash .dlog').append(panel);
    const icons={add:'M12 5v14M5 12h14',settings:'M4 7h16M4 17h16M8 4v6M16 14v6',folder:'M3 7V5h7l2 2h9v13H3Z',play:'m8 5 11 7-11 7Z'};
    for(const [id,key] of [['ewNewRun','add'],['ewRename','settings'],['ewSettings','settings'],['ewFolder','folder'],['ewQueueStart','play']]){const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('width','14');svg.setAttribute('height','14');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('fill','none');svg.setAttribute('stroke','currentColor');svg.setAttribute('stroke-width','1.6');svg.setAttribute('stroke-linecap','round');svg.setAttribute('stroke-linejoin','round');svg.setAttribute('aria-hidden','true');const path=document.createElementNS(svg.namespaceURI,'path');path.setAttribute('d',icons[key]);svg.append(path);$(id).prepend(svg);}
    $('ewNewRun').onclick=()=>openRun();$('ewRename').onclick=renameProject;$('ewView').onclick=viewResult;$('ewSearch').oninput=renderRuns;$('ewSettings').onclick=inspectSettings;
    $('ewEnqueue').onclick=()=>queueAction('enqueue',{ids:[runId]});$('ewQueueStart').onclick=()=>queueAction('resume');$('ewQueuePause').onclick=()=>queueAction('pause');$('ewRetry').onclick=()=>queueAction('retry',{id:data.queue.failure});$('ewSkip').onclick=()=>queueAction('skip',{id:data.queue.failure});$('ewStop').onclick=()=>queueAction('stop',{id:runId});$('ewFolder').onclick=async()=>{try{await api('/folder',{id:runId});}catch(e){message(e.message);}};
    $('mCFD').onclick=showList;$('mViz').onclick=viewResult;
    document.body.classList.add('grouped');showList();
  }
  mount();refresh();setInterval(refresh,4000);
})();
