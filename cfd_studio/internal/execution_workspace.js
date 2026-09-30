/* Project containers do not own solver settings. Each launch takes a snapshot. */
(() => {
  const $ = id => document.getElementById(id);
  const selectedRuns=new Map(),caseProgress=new Map();
  let progressProject=null,progressBusy=false,reloadBusy=false;
  let data = {projects: []}, projectId = '', runId = '', generation = 0, detail = null;
  const csvPending=new Set();let queuePending=false;let pending=false, refreshing=false, projectSignature='',runSignature='',viewMode='cfd',presets=[],forms=[];
  const status = {complete:'완료', failed:'실패', running:'계산 중', queued:'대기', draft:'대기', stopped:'중단', preparing:'준비 중', saved:'보관'};
  const stateText=r=>(status[r.status]||r.status)+(r.completion_reason==='limit'?' · 한계 도달':'');
  const modelName = run => run.form_snapshot?.name || forms.find(f=>f.id===run.form_id)?.name || forms.find(f=>f.model===run.model)?.name || run.model || '모델 미확인';
  const node = (tag, text, cls) => {const e=document.createElement(tag); if(text!=null)e.textContent=text; if(cls)e.className=cls; return e;};
  async function api(path, body) {
    const response = await fetch('/api/executions'+path, body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const value = await response.json();
    if(!response.ok||value.ok===false)throw Error(value.msg||'요청 실패');
    return value;
  }
  function currentProject(){return data.projects.find(p=>p.id===projectId);}
  function renderViewerCases(){
    const p=currentProject(),list=$('ewViewerCaseList');if(!list)return;
    const changedProject=!!p&&progressProject!==projectId;
    if(changedProject){progressProject=projectId;caseProgress.clear();}
    for(const run of p?.runs||[]){if(!caseProgress.has(run.id))caseProgress.set(run.id,{percent:run.result_status==='ready'?100:null,label:run.result_status==='ready'?'준비됨':'확인 중',active:run.result_status!=='ready'});}
    const signature=JSON.stringify([projectId,runId,p?.runs.map(r=>[r.id,r.name,r.has_results])]);
    if(list.dataset.signature!==signature){list.dataset.signature=signature;list.replaceChildren();
      for(const r of p?.runs||[]){const row=node('div',null,'ew-viewer-case'),view=button('',()=>selectRun(r.id));row.dataset.runId=r.id;const fill=node('span',null,'ew-case-fill'),name=node('span',r.name,'ew-case-name'),amount=node('span',null,'ew-case-amount');fill.setAttribute('role','progressbar');fill.setAttribute('aria-label',r.name+' 시각화 준비');fill.setAttribute('aria-valuemin','0');fill.setAttribute('aria-valuemax','100');view.append(fill,name,amount);view.setAttribute('aria-label',r.name);view.disabled=!r.has_results;view.classList.toggle('selected',runId===r.id);view.title=r.name;view.setAttribute('aria-pressed',String(runId===r.id));row.append(view);list.append(row);}
    }
    renderCaseProgress();
    if(changedProject)checkCaseProgress();
    DataSheetViewer.setSelection(p,(p?.runs||[]).filter(r=>r.id===runId&&r.has_results));
  }
  function renderCaseProgress(){
    for(const row of $('ewViewerCaseList')?.children||[]){
      const value=progressProject===projectId?caseProgress.get(row.dataset.runId):null;
      const button=row.querySelector('button'),fill=row.querySelector('.ew-case-fill'),amount=row.querySelector('.ew-case-amount');
      fill.hidden=!value;amount.hidden=!value;if(!value)continue;
      const percent=value.percent;
      fill.style.width=(percent??0)+'%';fill.style.transitionDuration=percent===100?'350ms':'1100ms';
      fill.classList.toggle('indeterminate',percent==null&&value.active);
      if(percent==null)fill.removeAttribute('aria-valuenow');else fill.setAttribute('aria-valuenow',String(percent));
      fill.setAttribute('aria-valuetext',value.label+(percent==null?'':' '+percent+'%'));
      amount.textContent=percent==null||value.error?value.label:percent+'%';
      row.classList.toggle('progress-error',!!value.error);
      button.title=(currentProject()?.runs.find(r=>r.id===row.dataset.runId)?.name||'')+' · 시각화 '+value.label+(value.error?' · '+value.error:'');
    }
  }
  async function checkCaseProgress(){
    if(progressBusy||progressProject!==projectId)return;
    const target=projectId;progressBusy=true;
    try{const reply=await api('/result-progress?project_id='+encodeURIComponent(target));
      if(target!==projectId||target!==progressProject)return;
      for(const value of reply.runs)caseProgress.set(value.id,value);
    }catch(e){if(target===progressProject){for(const [id,value] of caseProgress)caseProgress.set(id,{...value,active:false,percent:null,label:'확인 실패',error:e.message});}}
    finally{progressBusy=false;renderCaseProgress();if(target!==projectId&&progressProject===projectId)checkCaseProgress();}
  }
  async function reloadViewerCases(){
    if(reloadBusy||progressBusy||!currentProject())return;
    const target=projectId,id=runId;reloadBusy=true;progressProject=target;caseProgress.clear();
    for(const run of currentProject().runs)caseProgress.set(run.id,{percent:null,label:'확인 중',active:true});
    renderCaseProgress();
    // Paint the empty gauges before applying the inspected values.
    await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
    try{await checkCaseProgress();if(target===projectId&&id===runId&&id){await selectRun(id);if(target===projectId&&id===runId)DataSheetViewer.reload();}}
    finally{reloadBusy=false;}
  }
  function renderSidebarAction(){
    const first=$('ewFindProject'),second=$('ewCreateProject');if(!first||!second)return;
    const viewer=document.body.classList.contains('execution-viewer');
    const actions=$('ewSidebarActions');actions.classList.toggle('viewer',viewer);actions.dataset.viewerMode=DataSheetViewer.mode;
    for(const [control,label,action,selected] of viewer
      ? [[first,'3D Virtual',()=>selectViewerMode('3d'),DataSheetViewer.mode==='3d'],[second,'Data Sheet',()=>selectViewerMode('data'),DataSheetViewer.mode==='data']]
      : [[first,'프로젝트 찾기',findProject,false],[second,'새 프로젝트',createProject,false]]){
      control.textContent=label;control.title=label;control.setAttribute('aria-label',label);
      control.classList.toggle('selected',selected);control.onclick=action;control.disabled=!viewer&&pending;
      if(viewer)control.setAttribute('aria-pressed',String(selected));else control.removeAttribute('aria-pressed');
    }
  }
  function selectViewerMode(mode){DataSheetViewer.setMode(mode);renderSidebarAction();}
  function button(text, action, cls='btn') {const b=node('button',text,cls); b.type='button'; b.onclick=action; return b;}
  function message(text){$('ewMessage').textContent=text;}
  function showList(){DataSheetViewer.suspend();viewMode='cfd';suspendWarehouseViewer();setPlay(false,true);setMode('cfd');document.body.classList.remove('execution-viewer','warehouse-viewer');renderSidebarAction();$('appContext').textContent='CFD Studio · '+(currentProject()?.name||'프로젝트');}
  function renderProjects() {
    renderForms();
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
    $('ewDefault').replaceChildren();for(const [text,raw] of [[forms.find(f=>f.id===currentProject()?.form_id)?.name||'CFD Template 미지정',true],[' · 기본 프리셋: ',false],[presets.find(p=>p.id===currentProject()?.default_preset)?.name||(currentProject()?'직접 입력':'미지정'),!!currentProject()?.default_preset]]){const part=node('span',text);if(raw)part.setAttribute('translate','no');$('ewDefault').append(part);}
    $('ewRename').disabled=!currentProject();$('ewNewRun').disabled=!currentProject()||pending||currentProject()?.storage_available===false;const path=$('ewStorage');if(path){path.textContent=currentProject()?.storage_available===false?'프로젝트 폴더 연결 필요':'';path.title='';path.classList.toggle('offline',currentProject()?.storage_available===false);}renderSidebarAction();
    $('appContext').textContent='CFD Studio · '+(currentProject()?.name||'프로젝트');renderViewerCases();
    $('stTxt').textContent=data.busy?'계산 중':'실행 대기';$('stDot').className=data.busy?'dot run':'dot ok';
  }
  function badge(text,state){const b=node('span',text,'ew-badge');b.dataset.state=state||'';return b;}
  function numericalText(r){return {passed:'통과',incomplete:'미완료',unchecked:'미검사'}[r.numerical_status]||'미검사';}
  function renderRuns(){
    const rows=$('ewRows'), p=currentProject(), search=$('ewSearch').value.toLowerCase();
    const signature=JSON.stringify([projectId,runId,search,p?.runs]);
    if(signature===runSignature)return;runSignature=signature;
    rows.replaceChildren();
    for(const r of p?.runs||[]){
      if(!`${r.name} ${r.model} ${modelName(r)}`.toLowerCase().includes(search))continue;
      const row=button('',()=>selectRun(r.id),'ew-run-card');row.classList.toggle('selected',r.id===runId);row.setAttribute('aria-pressed',String(r.id===runId));
      const top=node('div',null,'ew-run-top'),name=node('strong',r.name);name.title=r.name;top.append(name,badge(stateText(r)+(r.status==='draft'?' · 초안':''),r.status));
      const meta=node('div',null,'ew-run-meta');meta.append(node('span',modelName(r)),node('span',stopText(r.termination,r.end_s)));
      const bottom=node('div',null,'ew-run-meta');bottom.append(node('span',r.differences?.length?`Config ${r.differences.length}개 변경`:Array.isArray(r.differences)?'Config 동일':'비교 기준 없음'),node('span',resultText(r)));row.append(top,meta,bottom);
      row.title=`${r.name}
마지막 저장 ${r.last_saved==null?'—':r.last_saved+' '+(r.time_unit||'s')} · 수치 검사 ${numericalText(r)}`;rows.append(row);
    }
    $('ewRunCount').textContent=String(p?.runs.length||0);
    if(!rows.children.length)rows.append(node('div',search?'검색 결과 없음':'아직 실행이 없습니다','ew-empty'));
  }

  async function selectProject(id){
    projectId=id;runId='';detail=null;generation++;suspendWarehouseViewer();setPlay(false,true);
    $('ewSearch').value='';renderProjects();renderRuns();
    try{localStorage.setItem('cfd-project',id);}catch(_){}
    const runs=currentProject()?.runs||[];
    const recent=runs.find(r=>r.id===selectedRuns.get(id))||runs.find(r=>r.status==='running')||runs.find(r=>r.has_results)||runs[0];
    if(recent)await selectRun(recent.id);else{clearDetail();if(viewMode==='viewer')showEmptyViewer('아직 CFD Case가 없습니다');else showList();}
  }
  function clearDetail(){
    $('ewRunTitle').removeAttribute('translate');$('ewRunTitle').textContent='실행 선택';$('ewLog').setAttribute('data-i18n-text','');$('ewLog').textContent='목록에서 실행을 선택하세요';
    $('ewStatus').replaceChildren();$('ewStats').replaceChildren();$('ewProgress').hidden=true;$('ewRunError').textContent='';$('ewStopLabel').textContent='—';$('ewDifferenceCount').textContent='';$('ewConfigSummary').textContent='';$('ewFacts').textContent='';$('ewView').disabled=true;$('ewSettings').disabled=true;$('ewEnqueue').disabled=true;$('ewFolder').disabled=true;$('ewCSV').disabled=true;$('ewStop').hidden=true;$('ewRecovery').hidden=true;$('ewDifferences').textContent='';$('ewGoals').textContent='';
  }
  function showDetail(value){
    detail=value;const row=currentProject()?.runs.find(r=>r.id===value.id);if(row){for(const k of ['result_status','last_saved','numerical_status','has_results','frame_counts'])if(k in value)row[k]=value[k];renderRuns();renderSidebarAction();}$('ewRunTitle').setAttribute('translate','no');$('ewRunTitle').textContent=value.name;if(value.log)$('ewLog').removeAttribute('data-i18n-text');else $('ewLog').setAttribute('data-i18n-text','');$('ewLog').textContent=value.log||'보존된 솔버 로그 없음';
    $('ewStatus').replaceChildren(badge(stateText(value),value.status));
    $('ewConfigSummary').textContent=CFDSettings.summary(value.config,value.form_snapshot||forms.find(f=>f.id===value.form_id));$('ewSettings').disabled=false;
    const checks=value.checks||{};
    $('ewFacts').textContent=modelName(value);
    $('ewStats').replaceChildren();
    for(const [label,text,state] of [['마지막 저장',value.last_saved==null?'—':value.last_saved+' '+(value.time_unit||'s'),''],['수치 검사',numericalText(value),value.numerical_status],['시각화',resultText(value),value.result_status]]){const card=node('div',null,'ew-stat');card.append(node('span',label),badge(text,state));$('ewStats').append(card);}
    $('ewRunError').textContent=value.recovery?.reason||value.error||'';
    const recovery=value.recovery;$('ewRecovery').hidden=!recovery;$('ewRecovery').textContent=value.status==='stopped'?'이어하기':recovery?.retry?'다시하기':'실패 사유';$('ewRecovery').disabled=queuePending;

    const progress=value.end_s>0&&value.last_saved!=null; $('ewProgress').hidden=!progress;
    if(progress){const pct=Math.min(100,Math.max(0,100*value.last_saved/value.end_s));$('ewProgressFill').style.width=pct+'%';$('ewProgressLabel').textContent='저장 진행';$('ewProgressValue').textContent=Math.round(pct)+'%';}
    $('ewStopLabel').textContent=stopText(value.termination,value.end_s);
    $('ewView').textContent=value.result_status==='update'?'업데이트':value.has_results?'열기':'생성';$('ewView').disabled=!value.has_results&&!value.can_generate;
    $('ewSettings').lastChild.textContent=value.editable?'Config 편집':'Config 보기';
    $('ewEnqueue').disabled=value.status!=='draft';$('ewEnqueue').hidden=!value.editable;$('ewStop').hidden=value.status!=='running';$('ewFolder').disabled=!value.path;
    $('ewCSV').disabled=!value.path||csvPending.has(value.id);$('ewCSV').textContent=csvPending.has(value.id)?'CSV 생성 중…':'전체 CSV';
    const comparison=differenceView(value);$('ewDifferences').textContent=comparison.text;
    $('ewGoals').textContent=value.goals||'';$('ewDifferenceCount').textContent=comparison.label;
  }
  async function selectRun(id){
    const token=++generation;runId=id;selectedRuns.set(projectId,id);detail=null;DataSheetViewer.begin(null);cancelViewerLoad();renderRuns();renderViewerCases();suspendWarehouseViewer();setPlay(false,true);
    clearDetail();$('ewRunTitle').removeAttribute('translate');$('ewRunTitle').textContent='불러오는 중';
    try{const value=await api('/detail?id='+encodeURIComponent(id));if(token!==generation)return;showDetail(value);renderViewerCases();message('');if(viewMode==='viewer')await viewResult();}
    catch(e){if(token===generation){clearDetail();message(e.message);if(viewMode==='viewer')showEmptyViewer('결과를 불러오지 못했습니다');}}
  }
  async function viewResult(){
    if(!detail){if(runId){viewMode='viewer';message('실행 정보를 불러오는 중입니다');}else showEmptyViewer('표시할 CFD Case가 없습니다');return;}
    if(detail.can_generate&&(!detail.has_results||detail.result_status==='update')){await prepareResult();return;}
    if(!detail.has_results){showEmptyViewer('선택한 Case의 결과가 아직 없습니다');return;}
    const selected=detail,token=generation;viewMode='viewer';setPlay(false,true);document.body.classList.remove('case-empty');$('controls').inert=false;
    DataSheetViewer.begin(selected);DataSheetViewer.resume();document.body.classList.add('execution-viewer');renderSidebarAction();
    document.body.classList.toggle('warehouse-viewer',selected.kind==='warehouse');
    cancelViewerLoad();
    if(selected.kind!=='warehouse'){restoreWarehouseUI();VIZCFG=selected.config||null;VPROJ=selected.rid;}
    setMode('viz');
    if(selected.kind==='warehouse'){
      if(token!==generation||viewMode!=='viewer')return;
      await loadWarehouseResult(selected.rid,selected.name);
    }else{await selVz(selected.rid);}
    if(token===generation&&viewMode==='viewer')DataSheetViewer.loaded();
  }
  function showEmptyViewer(text){
    viewMode='viewer';suspendWarehouseViewer();cancelViewerLoad();setPlay(false,true);
    DataSheetViewer.begin(null);DataSheetViewer.resume();
    document.body.classList.add('execution-viewer','case-empty');$('controls').inert=true;
    $('ewViewerEmpty').textContent=text;setMode('viz');renderSidebarAction();
  }
  function inspectSettings(){
    if(!detail)return;if(detail.editable){openRun(detail.config,detail);return;}const snapshot=structuredClone(detail);
    CFDSettings.open({config:snapshot.config,managed:!!snapshot.termination,readonly:true,form:snapshot.form_snapshot||forms.find(f=>f.id===currentProject()?.form_id),title:'Config · '+snapshot.name,name:snapshot.name,onClone:config=>openRun(config)});
  }
  async function refresh(){
    if(refreshing){await new Promise(resolve=>setTimeout(resolve,50));return refresh();}refreshing=true;
    try{
      const [value,presetData,formData]=await Promise.all([api(''),api('/presets'),api('/forms')]);data=value;presets=presetData.presets;forms=formData.forms;renderQueue();
      if(!projectId||!data.projects.some(p=>p.id===projectId)){
        let saved='';try{saved=localStorage.getItem('cfd-project')||'';}catch(_){}
        await selectProject(data.projects.find(p=>p.id===saved)?.id||data.projects[0]?.id);
      }else{renderProjects();renderRuns();}
      if(runId&&!pending){const token=generation;const v=await api('/detail?id='+encodeURIComponent(runId));if(token===generation)showDetail(v);}
    }catch(e){message(e.message);}finally{refreshing=false;}
  }
  function stopText(t,end){if(!t)return end==null?'—':end+' s';return t.mode==='frames'?t.frames+' 프레임 · 초기 '+(t.include_initial?'포함':'제외'):t.mode==='time'?t.time_s+' s':'수렴 기준';}
  function differenceView(value){
    if(!Array.isArray(value.differences))return {label:'기준 없음',text:'비교 기준이 저장되지 않은 기존 결과입니다'};
    const basis=value.preset_id?'Case 생성 당시 프리셋':'Case 최초 저장 설정';
    const rows=value.differences.map(x=>x.path+': '+JSON.stringify(x.before)+' → '+JSON.stringify(x.after));
    return {label:rows.length?rows.length+'개 변경':'변경 없음',text:'기준: '+basis+'\n\n'+(rows.join('\n')||'기준 설정과 차이 없음')};
  }
  function resultText(r){return {ready:'준비됨',update:'새 데이터',preparing:'변환 중',none:'없음'}[r.result_status]||'없음';}
  function renderForms(){
    const list=$('ewFormList'),activeId=currentProject()?.form_id;
    const signature=JSON.stringify([projectId,activeId,forms]);
    if(list.dataset.signature===signature)return;
    const changedProject=list.dataset.projectId!==(projectId||''),scrollTop=list.scrollTop;
    list.dataset.signature=signature;list.dataset.projectId=projectId||'';list.replaceChildren();
    const ordered=[...forms.filter(f=>f.id===activeId),...forms.filter(f=>f.id!==activeId)];
    for(const form of ordered){
      const active=form.id===activeId,row=node('div',null,'ew-form-row'+(active?' selected':'')),text=node('div');
      row.dataset.formId=form.id;if(active){row.setAttribute('aria-current','true');row.title='선택한 프로젝트의 CFD Template';}
      text.append(node('strong',form.name),node('small',form.solver+(form.definition_only?' · 실행 연결 필요':'')));
      const edit=button('수정',()=>formEditor(form.id));edit.setAttribute('aria-label',form.name+' 수정');row.append(text,edit);list.append(row);
    }
    list.scrollTop=changedProject?0:scrollTop;
  }
  async function formEditor(id=null,prepared=null,flow=null){
    try{
      const [reply,catalogReply,surveyReply]=await Promise.all([api('/forms'),api('/solvers'),api('/form-survey')]);
      if(flow&&!flow.active)return;
      const existing=reply.forms.find(f=>f.id===id),connected=existing&&!existing.definition_only;
      const survey=(settings,onApply,root=false)=>CFDFormWizard.recommend({options:surveyReply.options,...settings,onOpen:flow?.attach,onDismiss:root?flow?.finish:null,loadRecommendations:async answers=>(await api('/form-recommend',{answers})).result,generate:async(solver,answers)=>(await api('/form-from-survey',{solver,answers})).result,onApply});
      if(!existing&&!prepared){survey({},selection=>formEditor(null,selection,flow),true);return;}
      let solvers=catalogReply.solvers,installation=catalogReply.installation;
      let config=structuredClone(prepared?.result.config||existing?.blank_config||{}),schema=prepared?.result.config_schema|| (existing?.input_schema?structuredClone(existing.input_schema):CFDFormConfig.fromConfig({})),configured=!!(existing||prepared);
      const d=node('dialog');d.className='ew-dialog ew-form-dialog';
      d.innerHTML='<form data-validation="submit"><h2></h2><label>CFD Template 이름<input name="name" required maxlength="80"></label><label>설명<textarea name="description" rows="2" maxlength="4000"></textarea></label><label>솔버<select name="solver"></select></label><section class="ew-solver-card" aria-label="솔버 기능"><div class="ew-solver-heading"><strong data-solver-title></strong><button type="button" class="btn" data-check>설치 확인</button></div><div data-install-result role="status" aria-live="polite"></div><p data-summary></p><p data-authors></p><div class="ew-solver-tags"></div><dl data-features></dl><p data-connection></p><p data-uses></p><details><summary>필수 Config</summary><ul data-required></ul></details><details><summary>선택·조건부 Config</summary><ul data-optional></ul></details><details><summary>계산 범위</summary><p data-inputs></p></details></section><div class="ew-form-config"><div><strong>Config 양식</strong><p data-config-count></p></div><div class="ew-bar"><button type="button" class="btn pri" data-wizard>양식 구성</button><button type="button" class="btn" data-config>양식 편집</button></div></div><p role="alert"></p><div class="ew-bar"><button type="button" class="btn" data-cancel>취소</button><button type="submit" class="btn pri">Template 저장</button></div></form>';
      const f=d.querySelector('form');f.querySelector('h2').textContent=existing?'CFD Template 수정':'양식 확인';
      for(const dedicated of [false,true]){const group=node('optgroup');group.label=dedicated?'Studio 연결 솔버':'OpenFOAM 솔버';for(const solver of solvers.filter(x=>x.dedicated===dedicated))group.append(new Option(solver.id,solver.id));f.elements.solver.append(group);}
      f.elements.name.value=existing?.name||'';f.elements.description.value=existing?.description||'';f.elements.solver.value=existing?.solver||prepared.solver;f.elements.solver.disabled=true;
      const solver=()=>solvers.find(x=>x.id===f.elements.solver.value);
      const draw=()=>{
        const item=solver();f.querySelector('[data-solver-title]').textContent=item.id;f.querySelector('[data-summary]').textContent=item.summary;
        const authors=f.querySelector('[data-authors]');authors.replaceChildren();for(const link of item.upstream||[]){if(authors.children.length)authors.append(' · ');const a=node('a',link.label);a.href=link.url;a.target='_blank';a.rel='noopener noreferrer';authors.append(a);}
        f.querySelector('[data-install-result]').textContent=installation?.status==='unavailable'?'확인 실패 · '+installation.note:item.installation==='found'?'설치 확인됨 · '+(installation?.version||'OpenFOAM'):item.installation==='missing'?'실행 파일 없음':'설치 미확인';
        const tags=f.querySelector('.ew-solver-tags');tags.replaceChildren(...[item.category,item.time_mode,connected?'실행 연결됨':'실행 연결 필요'].map(x=>node('span',x)));
        f.querySelector('[data-features]').replaceChildren(node('dt','주요 결과'),node('dd',item.outputs.join(' · ')));
        f.querySelector('[data-inputs]').textContent=item.requirements.limit;f.querySelector('[data-uses]').textContent='주요 용도 · '+item.requirements.uses.join(' / ');
        for(const [selector,key] of [['[data-required]','required'],['[data-optional]','optional']])f.querySelector(selector).replaceChildren(...item.requirements[key].map(x=>node('li',x)));
        f.querySelector('[data-connection]').textContent=connected?'연결된 실행 양식 · 입력값은 프로젝트와 프리셋에서 관리':'양식·프로젝트·프리셋 저장 가능 · 계산은 실행기 연결 후 사용';
        f.querySelector('[data-wizard]').hidden=!!connected;f.querySelector('[data-wizard]').textContent='설문 수정';f.querySelector('[data-config]').disabled=!configured;
        const count=fields=>fields.reduce((n,x)=>n+1+(x.type==='object'?count(x.fields):0),0);f.querySelector('[data-config-count]').textContent=configured?count(schema.fields)+' fields · Key / Type / Unit':'해석 조건을 선택해 빈 입력 양식 구성';
      };

      f.querySelector('[data-check]').onclick=async()=>{const check=f.querySelector('[data-check]');check.disabled=true;f.querySelector('[data-install-result]').textContent='설치 확인 중';try{const r=await api('/solver-check',{});if(!d.isConnected)return;solvers=r.result.solvers;installation=r.result.installation;draw();}catch(e){f.querySelector('[data-install-result]').textContent=e.message;}finally{check.disabled=false;}};
      f.querySelector('[data-config]').onclick=()=>CFDFormConfig.open({config,schema,schemaOnly:true,title:'Config 양식',onSave:async(value,definition)=>{config=value;schema=definition;draw();}});
      f.querySelector('[data-wizard]').onclick=()=>survey({answers:{...config?.analysis?.choices,time_mode:config?.analysis?.time_mode},selected:solver().id,fixedSolver:existing?.solver||null,replace:configured},async selection=>{config=selection.result.config;schema=selection.result.config_schema;f.elements.solver.value=selection.solver;configured=true;draw();});
      f.querySelector('[data-cancel]').onclick=()=>d.close();d.onclose=()=>{d.remove();flow?.finish();};d.oncancel=e=>{if(f.querySelector('[type=submit]').disabled)e.preventDefault();};
      f.onsubmit=async e=>{e.preventDefault();const submit=f.querySelector('[type=submit]');submit.disabled=true;f.querySelector('[data-cancel]').disabled=true;try{if(!configured)throw Error('설문을 완료하고 솔버를 선택하세요');const saved=await api('/form',{id,revision:existing?.revision,name:f.elements.name.value,model:existing?.model||'solver_definition',solver:solver().id,description:f.elements.description.value,config:connected?existing.config:config,sections:existing?.sections||{},input_schema:schema});await flow?.onSaved(saved.result);d.close();await refresh();}catch(e){f.querySelector('[role=alert]').textContent=e.message;}finally{submit.disabled=false;f.querySelector('[data-cancel]').disabled=false;}};
      draw();document.body.append(d);if(flow?.attach(d)===false){d.remove();return;}d.showModal();
    }catch(e){if(flow){flow.error(e.message);flow.finish();}else message(e.message);}
  }
  function renderQueue(){const q=data.queue||{},box=$('ewQueue');box.replaceChildren();$('ewQueueCard').hidden=!q.active&&!q.order?.length&&!q.failure&&!q.service_error;const all=data.projects.flatMap(p=>p.runs);$('ewQueueState').textContent=q.failure?'실패 확인 필요':q.paused?(q.active?'현재 실행 후 일시정지':'일시정지'):q.active||q.order?.length?'순차 실행':'대기열 완료';
    for(const [i,id] of (q.order||[]).entries()){const r=all.find(r=>r.id===id),row=node('div',null,'ew-bar ew-queue-row');row.append(node('span',(i+1)+'. '+(data.projects.find(p=>p.id===r?.project_id)?.name||'프로젝트')+' / '+(r?.name||id)));const move=delta=>{const order=[...q.order],j=i+delta;if(j<0||j>=order.length)return;[order[i],order[j]]=[order[j],order[i]];queueAction('reorder',{ids:order});};const up=button('↑',()=>move(-1)),down=button('↓',()=>move(1));up.title='실행 순서 위로';down.title='실행 순서 아래로';up.disabled=i===0;down.disabled=i===q.order.length-1;row.append(up,down,button('제외',()=>queueAction('remove',{id})));box.append(row);}
    $('ewQueueStart').disabled=!!q.failure||(!q.order?.length&&!q.active);$('ewQueuePause').disabled=!!q.paused||(!q.active&&!q.order?.length);$('ewFailures').hidden=!q.failure;$('ewRetry').hidden=!q.failure;$('ewSkip').hidden=!q.failure;
    if(queuePending)for(const b of document.querySelectorAll('#ewQueue button,#ewQueueStart,#ewQueuePause,#ewRetry,#ewSkip,#ewEnqueue,#ewStop'))b.disabled=true;
    $('ewQueueError').textContent=q.failure?(all.find(r=>r.id===q.failure)?.error||'중단한 실행을 확인하세요'):q.service_error||'';
  }
  async function exportCaseCSV(){
    const id=runId;if(!id||csvPending.has(id))return;
    csvPending.add(id);if(detail)showDetail(detail);
    try{const response=await api('/export-csv',{id});const a=node('a');a.href='/api/executions/export-csv-download?token='+encodeURIComponent(response.result.token);a.download='';document.body.append(a);a.click();a.remove();if(runId===id)message('전체 CSV 다운로드를 시작했습니다');}
    catch(e){if(runId===id)message('CSV 내보내기 실패: '+e.message);}
    finally{csvPending.delete(id);if(detail)showDetail(detail);}
  }
  async function recoveryDialog(id){
    if(!id||queuePending)return;
    try{
      const value=await api('/detail?id='+encodeURIComponent(id)),r=value.recovery;
      if(!r)throw Error('실패하거나 중단된 Case를 선택하세요');
      const d=node('dialog',null,'ew-dialog'),content=node('div',null,'ew-recovery-body');
      content.append(node('h2',value.status==='stopped'?'중단 Case':'실패 사유'),node('h3',value.name),node('p',r.reason));
      if(r.evidence){const evidence=node('details');evidence.append(node('summary','오류 기록'),node('pre',r.evidence));content.append(evidence);}
      content.append(node('p',r.action));
      if(r.resume)content.append(node('p',r.resume_reason));
      const actions=node('div',null,'ew-bar');
      const recover=async action=>{for(const b of actions.querySelectorAll('button'))b.disabled=true;try{const response=await api('/recover',{id,action});d.close();await refresh();await selectRun(response.result.id);message('대기열에 추가했습니다. 대기열 시작을 누르면 계산합니다');}catch(e){error.textContent=e.message;}finally{for(const b of actions.querySelectorAll('button'))b.disabled=b.dataset.recoveryAction==='resume'&&!r.resume;}};
      if(value.status==='stopped'){const resume=button('이어하기',()=>recover('continue_case'));resume.dataset.recoveryAction='resume';resume.disabled=!r.resume;resume.title=r.resume_reason||'';actions.append(resume);}
      if(r.retry)actions.append(button('다시하기',()=>recover('retry')));
      if(r.retry)content.append(node('p','다시하기는 기존 기록을 보존하고 처음부터 계산합니다'));
      const error=node('p');error.setAttribute('role','alert');actions.append(button('닫기',()=>d.close()));content.append(error,actions);d.append(content);d.onclose=()=>d.remove();document.body.append(d);d.showModal();
    }catch(e){message(e.message);}
  }
  async function queueAction(action,extra={}){if(queuePending)return;queuePending=true;renderQueue();try{await api('/queue',{action,...extra});await refresh();}catch(e){message(e.message);}finally{queuePending=false;renderQueue();if(detail)showDetail(detail);}}
  async function openRun(source,editing=null){
    if(pending)return;
    try{
      const targetProject=projectId,projectName=currentProject()?.name;
      const form=forms.find(f=>f.id===currentProject()?.form_id);if(!form)throw Error('프로젝트에서 CFD Template을 선택하세요');
      if(form.definition_only)throw Error('이 Template은 Config 저장만 지원합니다 · Case 계산에는 실행기 연결 필요');
      let sourceId=editing?editing.preset_id:currentProject()?.default_preset||(currentProject()?.initial_config?null:'form:'+form.id);
      const [presetData,result]=await Promise.all([api('/presets'),source?Promise.resolve({config:structuredClone(source)}):currentProject()?.initial_config&&!editing?Promise.resolve({config:structuredClone(currentProject().initial_config)}):api('/template?id='+encodeURIComponent(sourceId))]);
      const activeForm={...form,...editing?.form_snapshot,capabilities:editing?.form_snapshot?.capabilities||form.capabilities};
      const prepare=config=>CFDSettings.prepareConfig(config,activeForm);
      CFDSettings.open({config:prepare(result.config),managed:true,submitLabel:'실행 저장',name:editing?.name,title:editing?'Case Config':'CFD Case · '+projectName,form:activeForm,presets:presetData.presets.filter(p=>p.form_id===form.id),
        onLoad:async id=>{sourceId=id;return prepare((await api('/template?id='+encodeURIComponent(id))).config);},
        onRun:async(name,config,extra)=>{
          pending=true;renderProjects();try{
            const saved=await api('/case',{project_id:targetProject,name,config,id:editing?.id,revision:editing?.revision,preset_id:sourceId,...extra});
            showList();await refresh();await selectProject(targetProject);await selectRun(saved.result.run_key);message('실행 저장 완료');
          }finally{pending=false;renderProjects();}
        }
      });
    }catch(e){message(e.message);}
  }
  async function findProject(){
    const d=node('dialog');d.className='ew-dialog';
    d.innerHTML='<form data-validation="submit"><h2>프로젝트 찾기</h2><label>프로젝트 폴더<div class="ew-path"><input name="storage_path" required spellcheck="false" placeholder="D:\\CFD Projects\\프로젝트 이름"><button class="btn" type="button" data-pick>찾기</button></div></label><p class="ew-path-note">CFD Studio에서 생성한 프로젝트 폴더를 선택하세요. 파일 형식과 실행 목록을 검증한 후 등록합니다</p><p role="status" aria-live="polite"></p><div class="ew-bar"><button class="btn pri" type="submit">추가</button><button class="btn" type="button" data-cancel>취소</button></div></form>';
    const f=d.querySelector('form'),path=f.elements.storage_path,pick=f.querySelector('[data-pick]'),submit=f.querySelector('[type=submit]'),cancel=f.querySelector('[data-cancel]'),notice=f.querySelector('[role=status]');
    let working=false;
    const busy=value=>{working=value;path.disabled=value;pick.disabled=value;submit.disabled=value;cancel.disabled=value;};
    pick.onclick=async()=>{globalThis.CFDInput?.reset(path);busy(true);notice.textContent='폴더 선택 창에서 폴더를 선택하거나 취소하세요';try{const reply=await api('/project-pick',{path:path.value});if(!reply.result.cancelled)path.value=reply.result.path;notice.textContent='';}catch(e){notice.textContent=e.message;}finally{busy(false);}};
    cancel.onclick=()=>d.close();d.oncancel=e=>{if(working)e.preventDefault();};d.onclose=()=>d.remove();
    f.onsubmit=async e=>{e.preventDefault();if(working||pending)return;const location=path.value;busy(true);pending=true;renderSidebarAction();notice.textContent='프로젝트 검증 중…';
      try{const reply=await api('/project-open',{storage_path:location});showList();await refresh();await selectProject(reply.result.id);message('프로젝트 등록 완료');d.close();}
      catch(error){notice.textContent=error.message;}finally{pending=false;busy(false);renderSidebarAction();}
    };
    document.body.append(d);d.showModal();path.focus();
  }
  async function projectDialog(edit=false){
    try {
      const [presetReply,defaults]=await Promise.all([api('/presets'),api('/storage-defaults')]);
      const p=edit?currentProject():null,d=node('dialog');d.className='ew-dialog ew-project-dialog';
      d.innerHTML='<form data-validation="submit"><h2></h2><label>프로젝트 이름<input name="name" required maxlength="80"></label><label>프로젝트 폴더<div class="ew-path"><input name="storage_path" required spellcheck="false" placeholder="D:\\CFD Projects\\프로젝트 이름"><button class="btn" type="button" data-pick>찾기</button></div></label><p class="ew-path-note"></p><label>프로젝트 설명<textarea name="description" maxlength="4000" rows="3"></textarea></label><div class="ew-form-choice"><label>CFD Template<div class="ew-template-select"><select name="form_id" required><option value="">해석 대상 선택</option></select><button type="button" class="btn ew-template-add" data-new-template aria-label="새 CFD Template" title="새 CFD Template">+</button></div></label><label>기본 프리셋<select name="preset" disabled><option value="">FORM 선택 후 선택</option></select></label></div><p role="alert"></p><div class="ew-bar"><button class="btn pri" type="submit">저장</button><button class="btn" type="button" data-cancel>취소</button></div></form>';
      d.querySelector('h2').textContent=edit?'프로젝트 관리':'새 프로젝트';
      const f=d.querySelector('form'),path=f.elements.storage_path;
      f.elements.name.value=p?.name||'';f.elements.description.value=p?.description||'';
      path.value=p?.storage_path||'';
      let customPath=edit;
      path.oninput=()=>{customPath=true;};
      f.elements.name.oninput=()=>{if(!customPath){const name=f.elements.name.value.trim().replace(/[\\/:*?"<>|]/g,'_');path.value=name?defaults.base_path.replace(/[\\/]$/,'')+(defaults.base_path.includes('\\')?'\\':'/')+name:'';}};
      f.querySelector('.ew-path-note').textContent=edit?'위치 변경 시 기존 데이터를 복사·검증합니다. 원본은 보존됩니다':'이 폴더에 설정·Case·원본·시각화 데이터를 저장합니다';
      for(const item of forms){const option=new Option(item.name+(item.definition_only?' · 실행 연결 필요':''),item.id);option.setAttribute('translate','no');f.elements.form_id.append(option);}
      let projectConfig=null,configEpoch=0;
      const configArea=node('div',null,'ew-form-config'),configStatus=node('p','Config 입력 필요'),configButton=button('Config 입력',async()=>{
        try{const selected=forms.find(x=>x.id===f.elements.form_id.value);if(!selected)throw Error('CFD Template을 선택하세요');const token=++configEpoch;
          const value=projectConfig|| (f.elements.preset.value?(await api('/template?id='+encodeURIComponent(f.elements.preset.value))).config:selected.blank_config);
          if(token!==configEpoch||!d.isConnected)return;
          const editorSchema=CFDFormConfig.fromConfig(value,selected.input_schema);
          CFDFormConfig.open({config:value,schema:editorSchema,valuesOnly:true,title:'프로젝트 Config',onValidate:selected.definition_only?async c=>(await api('/form-inspect',{solver:selected.solver,config:c})).result:null,onSave:async c=>{
            await api('/project-config-check',{form_id:selected.id,config:c});if(token!==configEpoch||f.elements.form_id.value!==selected.id)return;projectConfig=structuredClone(c);configStatus.textContent='Config 입력 완료';configButton.textContent='Config 편집';
          }});
        }catch(e){f.querySelector('[role=alert]').textContent=e.message;}
      });configArea.append(configStatus,configButton);
      const presetSave=node('label'),presetCheck=node('input'),presetName=node('input');presetSave.className='ew-preset-save';presetCheck.type='checkbox';presetCheck.checked=false;presetName.placeholder='새 프리셋 이름';presetName.setAttribute('aria-label','새 프리셋 이름');presetName.hidden=true;presetCheck.onchange=()=>{presetName.hidden=!presetCheck.checked;};presetSave.append(presetCheck,node('span','프리셋에 저장'));
      if(!edit)f.querySelector('.ew-form-choice').after(configArea,presetSave,presetName);
      const filterPresets=()=>{f.elements.preset.replaceChildren(new Option('직접 입력',''));projectConfig=null;configButton.disabled=!f.elements.form_id.value;configStatus.textContent='Config 입력 필요';for(const item of presetReply.presets.filter(x=>x.form_id===f.elements.form_id.value)){const option=new Option(item.name,item.id);option.setAttribute('translate','no');f.elements.preset.append(option);}f.elements.preset.disabled=!f.elements.form_id.value;};
      f.elements.form_id.value=p?.form_id||'';f.elements.form_id.disabled=edit;filterPresets();f.elements.preset.value=p?.default_preset||(p?'form:'+p.form_id:'');f.elements.form_id.onchange=()=>{configEpoch++;filterPresets();};f.elements.preset.onchange=()=>{configEpoch++;projectConfig=null;configStatus.textContent=f.elements.preset.value?'선택한 프리셋 적용':'Config 입력 필요';configButton.textContent='Config 입력';};
      const addTemplate=f.querySelector('[data-new-template]');addTemplate.hidden=edit;
      addTemplate.onclick=()=>{
        if(addTemplate.disabled)return;addTemplate.disabled=true;f.querySelector('[role=alert]').textContent='';
        const flow={active:true,
          attach:child=>{if(!flow.active||!d.open)return false;d.classList.add('ew-project-attached');child.classList.add('ew-template-attached');},
          error:text=>{if(d.isConnected)f.querySelector('[role=alert]').textContent=text;},
          finish:()=>{if(!flow.active)return;flow.active=false;d.classList.remove('ew-project-attached');addTemplate.disabled=false;if(d.open)addTemplate.focus({preventScroll:true});},
          onSaved:async saved=>{
            try{
              const [latest,latestPresets]=await Promise.all([api('/forms'),api('/presets')]);
              if(!flow.active||!d.open)return;
              forms=latest.forms;presetReply.presets=latestPresets.presets;
              f.elements.form_id.replaceChildren(new Option('해석 대상 선택',''));
              for(const item of forms){const option=new Option(item.name+(item.definition_only?' · 실행 연결 필요':''),item.id);option.setAttribute('translate','no');f.elements.form_id.append(option);}
              f.elements.form_id.value=saved.id;configEpoch++;filterPresets();configButton.textContent='Config 입력';
            }catch(e){flow.error('Template 저장 완료 · '+e.message);}
          }
        };
        formEditor(null,null,flow);
      };
      const pick=f.querySelector('[data-pick]');pick.onclick=async()=>{pick.disabled=true;f.querySelector('[role=alert]').textContent='폴더 선택 창에서 폴더를 선택하거나 취소하세요';try{const r=await api('/project-pick',{path:path.value||defaults.base_path});if(!r.result.cancelled){path.value=r.result.path;customPath=true;}f.querySelector('[role=alert]').textContent='';}catch(e){f.querySelector('[role=alert]').textContent=e.message;}finally{pick.disabled=false;}};
      f.querySelector('[data-cancel]').onclick=()=>d.close();d.onclose=()=>d.remove();
      f.onsubmit=async e=>{e.preventDefault();if(pending)return;pending=true;renderProjects();
        const submit=f.querySelector('[type=submit]');submit.disabled=true;pick.disabled=true;
        f.querySelector('[role=alert]').textContent=edit&&path.value!==p.storage_path?'프로젝트 복사·검증 중…':'';
        try{if(!edit&&!projectConfig){if(!f.elements.preset.value)throw Error('Config 입력을 완료하세요');projectConfig=(await api('/template?id='+encodeURIComponent(f.elements.preset.value))).config;}if(!edit&&presetCheck.checked&&!presetName.value.trim())throw Error('새 프리셋 이름을 입력하세요');const result=await api(edit?'/project-edit':'/project',{id:p?.id,name:f.elements.name.value,description:f.elements.description.value,default_preset:f.elements.preset.value||null,form_id:f.elements.form_id.value,storage_path:path.value,...(!edit?{initial_config:projectConfig,preset_name:presetCheck.checked?presetName.value.trim():null}:{})});await refresh();await selectProject(result.result.id);d.close();}
        catch(err){f.querySelector('[role=alert]').textContent=err.message;}
        finally{pending=false;renderProjects();submit.disabled=false;pick.disabled=false;}
      };
      document.body.append(d);d.showModal();
    }catch(e){message(e.message);}
  }
  const createProject=()=>projectDialog(false),renameProject=()=>projectDialog(true);
  async function prepareResult(){const selected=detail;if(!selected)return;try{await api('/result',{id:selected.id});message('누락된 결과 확인 중');await refresh();}catch(e){message(e.message);}}
  function mount(){
    const style=node('style');style.textContent=`
body.grouped #side>section{flex:0 0 auto;min-height:auto}body.grouped #secRun,body.grouped #secData{display:none!important}body.grouped.execution-viewer #ewPresets{display:none!important}body.grouped #projList2,body.grouped #secData>.fgroup,body.grouped #secData>button[onclick="newProj()"]{display:none!important}
#ewViewerEmpty{display:none;position:absolute;inset:0 0 84px;align-items:center;justify-content:center;color:var(--muted);font-size:13px;pointer-events:none}body.case-empty:not(.data-sheet-viewer) #ewViewerEmpty{display:flex}body.case-empty #gl,body.case-empty #rcol,body.case-empty #gcol,body.case-empty #plabels,body.case-empty #empty{visibility:hidden!important}body.case-empty #controls{opacity:.45}body.grouped #dash{display:block!important;padding:20px}body.grouped.execution-viewer #dash{display:none!important}body.grouped #dash>.dlog{padding:0;border:0;background:none;border-radius:0;display:block}body.grouped #dash>:not(.dlog),body.grouped .dlog>pre,body.grouped .dlog>.dlab{display:none!important}
.ew-path{display:flex;gap:8px;align-items:center}.ew-path input{flex:1;min-width:0}.ew-path-note{font-size:11px;color:var(--muted);line-height:1.6}.ew-project-heading{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}.ew-project-heading h2{margin:0!important}#ewStorage{font-size:11px;color:var(--muted);margin-top:6px!important;max-width:46vw;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}#ewStorage.offline{color:var(--s3)}#ewSidebar{--case-list-height:310px;--heading-action-size:28px;padding:16px}#ewSidebar h2{font-size:11px;color:var(--muted);font-weight:600;margin:0 0 12px}#ewProjects,#ewFormList{display:grid;align-content:start;gap:6px;margin:12px 0 0;height:clamp(240px,38vh,400px);overflow-y:scroll;overflow-x:hidden;overscroll-behavior:contain;scrollbar-gutter:stable;padding:7px;background:var(--page);border:1px solid var(--line);border-radius:9px}#ewProjects::-webkit-scrollbar,#ewFormList::-webkit-scrollbar{width:9px}#ewProjects::-webkit-scrollbar-track,#ewFormList::-webkit-scrollbar-track{background:#151514;border-radius:8px}#ewProjects::-webkit-scrollbar-thumb,#ewFormList::-webkit-scrollbar-thumb{background:#464642;border:2px solid #151514;border-radius:8px}.ew-project{width:100%;text-align:left;padding:12px;border:1px solid var(--line);background:transparent;color:var(--ink);border-radius:8px;cursor:pointer}.ew-project strong,.ew-project span{display:block}.ew-project strong{font-size:13px}.ew-project span{font-size:11px;color:var(--muted);margin-top:5px}.ew-project.selected{border-color:var(--s1);background:rgba(57,135,229,.07)}
#ewViewerCases{display:none;padding-top:18px}body.execution-viewer #ewViewerCases{display:block}#ewViewerCaseList{height:var(--case-list-height);min-height:var(--case-list-height);overflow-y:scroll;overflow-x:hidden;scrollbar-gutter:stable;overscroll-behavior:contain;display:grid;align-content:start;grid-template-columns:minmax(0,1fr);gap:5px}.ew-viewer-case{display:flex;min-width:0;align-items:center;gap:9px}#ewSidebar .ew-project-heading .ew-heading-action{box-sizing:border-box;width:var(--heading-action-size);height:var(--heading-action-size);padding:0;border-radius:7px;font-size:11px;flex:none;display:grid;place-items:center;gap:0;line-height:0}#ewSidebar .ew-heading-action svg{display:block}#ewSidebar #btnRunTxt{display:none}#ewViewerCaseList .ew-viewer-case button{display:block;flex:1;min-width:0;text-align:left;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;padding:8px;font-size:11px;border-color:transparent}#ewViewerCaseList .ew-viewer-case button.selected{border-color:var(--s1);box-shadow:inset 0 0 0 1px var(--s1);background:#3987e51a}
#ewViewerCaseList .ew-viewer-case button{position:relative;display:flex;align-items:center;gap:8px;isolation:isolate}.ew-case-name{position:relative;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;min-width:0}.ew-case-amount{position:relative;flex:none;font-size:10px;color:var(--muted)}.ew-case-fill{position:absolute;inset:0 auto 0 0;width:0;z-index:-1;background:rgba(57,135,229,.18);transition:width 1100ms ease-out;pointer-events:none}.ew-case-fill.indeterminate{width:28%!important;animation:ew-case-check 1.6s ease-in-out infinite}.ew-viewer-case.progress-error .ew-case-amount{color:var(--s3)}.ew-case-fill[hidden],.ew-case-amount[hidden]{display:none!important}@keyframes ew-case-check{from{transform:translateX(-100%)}to{transform:translateX(360%)}}@media(prefers-reduced-motion:reduce){.ew-case-fill{transition:none!important}.ew-case-fill.indeterminate{animation:none}}
#ewPresets{border:0;border-top:1px solid var(--line);margin-top:12px;padding:18px 0 0}#ewPresets .ew-bar{display:grid;grid-template-columns:1fr 1fr;gap:7px}.ew-form-row{display:flex;align-items:center;gap:8px;padding:11px 5px;border:1px solid transparent;border-radius:8px}.ew-form-row.selected{border-color:var(--s1);background:rgba(57,135,229,.07)}.ew-form-row>div{flex:1;min-width:0}.ew-form-row strong{display:block;font-size:12px;overflow-wrap:anywhere}.ew-form-row small{display:block;font-size:9px;color:var(--muted);margin-top:5px;overflow-wrap:anywhere}.ew-form-row .btn{padding:0 8px;height:28px;font-size:11px}.ew-dialog.ew-form-dialog{max-height:85vh;max-width:700px;overflow:auto;width:min(700px,94vw)}.ew-form-dialog [hidden]{display:none!important}.ew-solver-card{background:var(--page);border:1px solid var(--line);border-radius:12px;padding:16px;margin:8px 0 18px}.ew-solver-heading{display:flex;align-items:center;justify-content:space-between;gap:10px}.ew-solver-heading strong{overflow-wrap:anywhere}.ew-solver-card p{font-size:12px;line-height:1.6;margin:10px 0}.ew-solver-card small{display:block;color:var(--muted);font-size:10px;line-height:1.5;margin-top:12px}.ew-solver-tags{display:flex;flex-wrap:wrap;gap:6px}.ew-solver-tags span{border:1px solid var(--line);border-radius:14px;padding:4px 8px;font-size:10px}.ew-solver-card dl{display:grid;grid-template-columns:65px 1fr;gap:6px;font-size:11px;line-height:1.6}.ew-solver-card dt{color:var(--muted)}.ew-solver-card dd{margin:0}.ew-draft-notes{border-top:1px solid var(--line);padding-top:12px}.ew-draft-notes h3{font-size:13px}.ew-form-columns{display:grid;grid-template-columns:1fr 1fr;gap:14px}.ew-form-config{display:flex;align-items:center;justify-content:space-between;border-top:1px solid var(--line);padding-top:14px;margin-top:16px}.ew-form-config p{font-size:11px;color:var(--muted)}.ew-form-outputs{margin-top:14px}.ew-form-outputs p{font-size:11px;color:var(--muted)}.ew-form-sections{max-height:230px;overflow:auto;padding:0 12px;background:var(--page);border-radius:8px}.ew-form-sections label{grid-template-columns:1fr 1fr;align-items:center}.ew-form-choice{border-top:1px solid var(--line);padding-top:4px;margin-top:18px}
#ewPanel{padding:0;border:0;min-width:0}#ewPanel [hidden],#ewSidebar [hidden]{display:none!important}#ewPanel h2,#ewPanel h3,#ewPanel p{margin:0}#ewTitle{color:var(--ink)!important}#ewPanel h2{font-size:21px;letter-spacing:-.5px}#ewPanel h3{font-size:13px}#ewPanel p:empty{display:none}.ew-bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.ew-bar h2,.ew-bar h3{flex:1;min-width:0}.ew-heading{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:18px}.ew-heading .ew-bar{flex-shrink:0}#ewNewRun{display:inline-flex;align-items:center;justify-content:center;gap:8px}#ewNewRun .ew-case-plus{display:inline-flex;align-items:center;justify-content:center;font-size:23px;font-weight:500;line-height:16px;width:16px;height:16px}#ewDescription{font-size:12px;color:var(--ink2);margin-top:7px!important;white-space:pre-wrap}#ewDefault{font-size:11px;color:var(--muted);margin-top:8px!important}
#ewPanel #sysCard{margin:0 0 14px;padding:12px 16px!important;border-radius:12px}#ewPanel #sysRow{display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px!important}#sysRow .hw-item{min-width:0;display:grid;grid-template-columns:auto 1fr auto;gap:10px;align-items:center}#sysRow .hw-item b{font-size:11px;font-weight:500;white-space:nowrap}#sysRow .hw-item output{font-size:12px;font-variant-numeric:tabular-nums;min-width:42px;text-align:right}#sysRow .hw-track{height:5px;border-radius:8px;background:var(--line);overflow:hidden}#sysRow .hw-fill{display:block;height:100%;width:0;background:var(--s1);border-radius:8px;transition:width .3s}#sysCard[data-stale=true]{opacity:.65}@media(max-width:720px){#ewPanel #sysRow{grid-template-columns:1fr;gap:12px!important}}.ew-layout{display:grid;grid-template-columns:minmax(260px,.8fr) minmax(340px,1.25fr);gap:14px;align-items:stretch;height:clamp(380px,calc(100vh - 310px),780px)}.ew-list-panel,.ew-detail-panel,.ew-queue-card{background:var(--surface);border:1px solid var(--line);border-radius:12px;overflow:hidden;min-width:0}.ew-list-panel,.ew-detail-panel{min-height:0}.ew-list-panel{display:flex;flex-direction:column}.ew-detail-panel{overflow-y:auto;overscroll-behavior:contain;scrollbar-gutter:stable}.ew-list-heading{flex-shrink:0;padding:16px 16px 12px}.ew-list-heading .ew-bar{margin-bottom:12px}#ewRunCount{font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums}#ewSearch{width:100%;height:34px;padding:0 11px;border:1px solid var(--line);border-radius:7px;color:var(--ink);background:var(--page);font:inherit;font-size:12px}#ewRows{grid-template-columns:minmax(0,1fr);grid-auto-rows:max-content;align-content:start;box-sizing:border-box;flex:1;min-height:0;overflow-y:scroll;overflow-x:hidden;scrollbar-gutter:stable;overscroll-behavior:contain;padding:0 8px 8px;display:grid;gap:5px}.ew-run-card{min-width:0;display:block;width:100%;padding:12px;text-align:left;background:transparent;border:1px solid transparent;border-radius:8px;color:var(--ink);cursor:pointer;font:inherit}.ew-run-card:hover{background:var(--surface2)}.ew-run-card.selected{background:rgba(57,135,229,.09);border-color:rgba(57,135,229,.6)}.ew-run-top{display:flex;align-items:center;gap:8px;margin-bottom:9px}.ew-run-top strong{min-width:0;font-size:12px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1}.ew-run-meta{display:flex;justify-content:space-between;gap:8px;font-size:10.5px;color:var(--muted);margin-top:5px}.ew-run-meta span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ew-badge{display:inline-flex;align-items:center;gap:5px;font-size:11px;white-space:nowrap;color:var(--ink2)}.ew-badge::before{content:'';width:5px;height:5px;border-radius:50%;background:var(--muted)}.ew-badge[data-state=complete],.ew-badge[data-state=ready],.ew-badge[data-state=passed]{color:#70ce9d}.ew-badge[data-state=complete]::before,.ew-badge[data-state=ready]::before,.ew-badge[data-state=passed]::before{background:#70ce9d}.ew-badge[data-state=failed]{color:#ed9288}.ew-badge[data-state=failed]::before{background:#ed9288}.ew-badge[data-state=running],.ew-badge[data-state=queued]{color:#88bafd}.ew-badge[data-state=running]::before,.ew-badge[data-state=queued]::before{background:#88bafd}
.ew-detail-head{padding:20px;border-bottom:1px solid var(--line)}#ewRunTitle{font-size:16px!important;line-height:1.5;overflow-wrap:anywhere;margin:10px 0 14px!important}#ewFacts{font-size:11px;color:var(--muted)}.ew-detail-head>.ew-bar:first-child{justify-content:space-between}.ew-detail-actions{display:flex;gap:8px;flex-wrap:wrap}.ew-detail-actions .pri{margin-left:auto}#ewStats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:0;margin:18px 0 0}.ew-stat{display:grid;gap:8px;padding:0 12px;border-left:1px solid var(--line);min-width:0}.ew-stat:first-child{padding-left:0;border:0}.ew-stat>span:first-child{font-size:10px;color:var(--muted)}.ew-stat .ew-badge{font-size:13px}.ew-stat .ew-badge[data-state='']::before{display:none}#ewProgress{margin-top:18px}#ewProgress .ew-bar{justify-content:space-between;margin-bottom:7px;color:var(--muted);font-size:10px}#ewProgress .pbar{height:5px}
.ew-detail-body{padding:16px 20px}.ew-setting-line{display:flex;justify-content:space-between;gap:12px;font-size:11px;color:var(--muted);margin-bottom:12px}#ewStopLabel{color:var(--ink2)}#ewGoals{font-size:12px;line-height:1.6;color:var(--ink2);white-space:pre-wrap;margin-bottom:12px!important}#ewConfigSummary{font-size:11px;color:var(--muted);line-height:1.5;margin-bottom:12px!important}#ewDifferenceBox{border-top:1px solid var(--line);padding:12px 0 0;font-size:11px;color:var(--muted)}#ewDifferenceCount{float:right}#ewPanel #ewDifferences{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px;line-height:1.8;min-height:96px;max-height:320px;overflow:auto;margin:0;padding:16px;box-sizing:border-box}#ewLogBox{border-top:1px solid var(--line);padding:14px 20px}#ewDifferenceBox h3,#ewLogBox h3{display:flex;align-items:center;margin:0;padding:12px;background:var(--surface2);font-weight:500;font-size:11px;color:var(--ink2)}#ewLog{height:180px;max-height:35vh;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;font:10px/1.6 monospace;color:var(--muted);padding:12px;background:var(--page);border-radius:6px;margin:12px 0 0}
.ew-recovery-body{padding:24px;max-width:560px}.ew-recovery-body p{line-height:1.6;margin:14px 0!important}.ew-recovery-body pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:240px;overflow:auto}.ew-recovery-body .ew-bar{margin-top:20px}#ewMessage,#ewRunError,#ewQueueError{font-size:12px;color:#e0ac77;line-height:1.6;overflow-wrap:anywhere}#ewMessage:not(:empty){margin-bottom:14px!important}#ewRunError:not(:empty){margin-top:12px!important}.ew-queue-card{margin-top:14px;padding:14px 18px}.ew-queue-card>summary{list-style:none}.ew-queue-card>summary::-webkit-details-marker{display:none}#ewQueueState{font-size:11px;color:var(--muted)}.ew-queue-actions{margin:14px 0 8px}#ewQueue .ew-bar span{flex:1;font-size:12px}.ew-queue-row{border-top:1px solid var(--line);padding:9px 0}.ew-queue-row .btn{height:28px;padding:0 9px;font-size:11px}.ew-empty{padding:26px 12px;text-align:center;color:var(--muted);font-size:12px}
.ew-dialog{max-height:90vh;overflow:auto;box-sizing:border-box;width:min(500px,90vw);background:var(--surface);color:var(--ink);border:1px solid var(--line);border-radius:12px;padding:22px}.ew-dialog::backdrop{background:#000a}.ew-dialog label{display:grid;gap:6px;margin:14px 0;font-size:12px}.ew-dialog input,.ew-dialog textarea,.ew-dialog select{width:100%;box-sizing:border-box;background:var(--page);color:var(--ink);border:1px solid var(--line);padding:8px;border-radius:7px}.ew-dialog .ew-bar{justify-content:flex-end}.ew-dialog label.ew-preset-save{display:flex;align-items:center;gap:8px}.ew-dialog .ew-preset-save input{width:16px;margin:0}.ew-solver-card a{color:var(--s1);text-underline-offset:3px}
@media(max-width:1100px){.ew-layout{grid-template-columns:1fr;height:auto}#ewRows{height:250px;flex:none}.ew-heading{align-items:flex-start}body.grouped #dash{padding:14px}}@media(max-width:720px){.ew-heading{display:block}.ew-heading>.ew-bar{margin-top:12px}#ewStats{grid-template-columns:1fr;gap:12px}.ew-stat{border:0;padding:0}}

#ewRunCount{margin-left:6px}
/* Shared disclosure surface: right chevron and a continuous rounded panel. */
body.grouped details>summary,#ewPanel details>summary{position:relative;display:flex;align-items:center;gap:10px;list-style:none;padding:11px 36px 11px 12px!important;min-height:36px;box-sizing:border-box;border:0;border-radius:9px;background:var(--surface2);color:var(--ink2);letter-spacing:0}
body.grouped details>summary::-webkit-details-marker,#ewPanel details>summary::-webkit-details-marker{display:none}
body.grouped details>summary::before,#ewPanel details>summary::before{display:none!important}
body.grouped details>summary::after,#ewPanel details>summary::after{content:'';position:absolute;right:14px;top:50%;width:6px;height:6px;border-right:1.5px solid var(--muted);border-bottom:1.5px solid var(--muted);transform:translateY(-65%) rotate(45deg);transition:transform .15s}
body.grouped details[open]>summary::after,#ewPanel details[open]>summary::after{transform:translateY(-20%) rotate(225deg)}
body.grouped details>summary:hover,#ewPanel details>summary:hover{background:#2c2c29;color:var(--ink)}
body.grouped details>summary:focus-visible,#ewPanel details>summary:focus-visible{outline:2px solid var(--s1);outline-offset:-2px}
#ewPanel .ew-disclosure-state{display:none}#ewDifferenceCount{float:none;font-size:10px;margin-left:auto}
body.grouped details,#ewPanel #ewDifferenceBox,#ewPanel #ewLogBox,#ewPanel #ewQueueCard{border:1px solid var(--line);border-radius:10px;background:var(--surface);padding:0;overflow:hidden}
body.grouped details[open]>summary,#ewPanel details[open]>summary{border-radius:9px 9px 0 0;box-shadow:0 1px 0 var(--line);position:relative;z-index:1}
body.grouped details> :not(summary){margin-left:12px;margin-right:12px}
#ewPanel #ewLogBox{margin:0 20px 16px}#ewPanel #ewLog{margin:12px;height:180px}#ewPanel #ewDifferenceBox{margin-top:12px}#ewPanel #ewQueueCard{margin-top:14px}#ewPanel #ewQueueCard>.ew-queue-actions{margin:12px}
body.grouped #warehouseDetails details{margin-top:8px}body.grouped #warehouseDetails details>summary{font-size:11px}body.grouped #warehouseDetails details>form{margin-top:12px}body.grouped #warehouseDetails details>p{margin-top:12px;margin-bottom:12px}
/* Keep native select keyboard, focus and disabled-option behavior. */
@supports (appearance:base-select){
 body.grouped select:not([multiple]),body.grouped select:not([multiple])::picker(select){appearance:base-select}
 body.grouped select:not([multiple]){anchor-name:--studio-select;anchor-scope:--studio-select;background-image:none!important;display:inline-flex;align-items:center;gap:12px;padding-right:12px!important;border-radius:8px;transition:border-color .15s}
 body.grouped select:not([multiple])::picker-icon{content:'';width:6px;height:6px;flex:none;border-right:1.5px solid var(--muted);border-bottom:1.5px solid var(--muted);transform:rotate(45deg);margin-left:auto;margin-right:2px;transition:transform .15s}
 body.grouped select:not([multiple]):open{border-radius:8px 8px 0 0;border-color:rgba(255,255,255,.28)}
 body.grouped select:not([multiple]):open::picker-icon{transform:rotate(225deg)}
 body.grouped select:not([multiple])::picker(select){position-anchor:--studio-select;position-try-order:normal;position-area:none;inset:auto;top:anchor(bottom);left:anchor(left);width:anchor-size(width);box-sizing:border-box;position-try-fallbacks:flip-block;border:1px solid rgba(255,255,255,.28);border-top:0;border-radius:0 0 10px 10px;background:var(--surface2);color:var(--ink);padding:6px;margin:0;max-height:min(320px,45vh);overflow-y:auto;box-shadow:0 12px 24px #0005;font:inherit;font-size:12px}
 body.grouped select:not([multiple]) option{border-radius:6px;padding:9px 10px;cursor:pointer;white-space:normal;overflow-wrap:anywhere}
 body.grouped select:not([multiple]) option:checked{background:rgba(57,135,229,.18);color:#8fc3ff}body.grouped select:not([multiple]) option:hover{background:rgba(255,255,255,.08)}body.grouped select:not([multiple]) option:disabled{color:var(--muted);opacity:.6;cursor:default}
 body.grouped select:not([multiple]) option::checkmark{color:#8fc3ff}
}


#ewSidebarActions{position:relative;isolation:isolate;display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:8px;width:100%}
#ewSidebarActions>.btn{display:flex;align-items:center;justify-content:center;width:100%;height:38px;min-height:38px;box-sizing:border-box;padding:0 6px;white-space:nowrap}
#ewSidebarActions>.btn{transition:background-color .25s,color .25s}#ewSidebarActions>.btn.selected{background:rgba(57,135,229,.12);color:#8fc3ff}
#ewSidebarActions::after{content:'';position:absolute;inset:0 auto 0 0;width:calc((100% - 8px)/2);box-sizing:border-box;border:1px solid var(--s1);border-radius:8px;box-shadow:inset 0 0 0 1px var(--s1);pointer-events:none;opacity:0;transition:transform .28s cubic-bezier(.2,.8,.2,1),opacity .15s}
#ewSidebarActions.viewer::after{opacity:1}#ewSidebarActions.viewer[data-viewer-mode=data]::after{transform:translateX(calc(100% + 8px))}
.ew-template-select{display:flex;align-items:center;gap:8px}.ew-dialog .ew-template-select select{flex:1;min-width:0;margin:0;height:36px}.ew-template-select .ew-template-add{width:36px;height:36px;flex:none;padding:0;display:grid;place-items:center;font-size:24px;line-height:1;border-radius:8px}.ew-template-add[hidden]{display:none}
.ew-project-dialog{transition:transform .28s cubic-bezier(.2,.8,.2,1),width .28s,height .28s}
.ew-project-attached{width:min(420px,36vw);height:min(820px,90vh);transform:translateX(calc((min(700px,56vw) + 16px)/-2))}
dialog.ew-template-attached[class]{box-sizing:border-box;width:min(700px,56vw);max-width:none;height:min(820px,90vh);max-height:90vh;transform:translateX(calc((min(420px,36vw) + 16px)/2));animation:ew-template-enter .28s cubic-bezier(.2,.8,.2,1)}
dialog.ew-template-attached::backdrop{background:transparent}
@keyframes ew-template-enter{from{opacity:0;translate:20px 0}to{opacity:1;translate:0 0}}
@media(max-width:1100px){.ew-project-attached{width:min(500px,90vw);height:auto;transform:none}dialog.ew-template-attached[class]{width:94vw;height:auto;transform:none}dialog.ew-template-attached::backdrop{background:#0009}}
@media(prefers-reduced-motion:reduce){.ew-project-dialog,#ewSidebarActions::after,#ewSidebarActions>.btn{transition:none}dialog.ew-template-attached[class]{animation:none}}

`;document.head.append(style);
    const sidebar=node('section',null);sidebar.id='ewSidebar';const create=button('새 프로젝트',createProject);create.id='ewCreateProject';const find=button('프로젝트 찾기',findProject);find.id='ewFindProject';const actions=node('div');actions.id='ewSidebarActions';actions.append(find,create);const projectHeading=node('div',null,'ew-project-heading');projectHeading.append(node('h2','프로젝트'));sidebar.append(projectHeading,actions);
    const projects=node('div');projects.id='ewProjects';projects.setAttribute('aria-label','프로젝트 목록');projects.tabIndex=0;sidebar.append(projects);const presetBox=node('section');presetBox.id='ewPresets';const heading=node('div',null,'ew-project-heading');heading.append(node('h2','CFD Template 리스트'),button('',()=>formEditor(),'btn ew-heading-action'));heading.lastChild.id='ewCreateForm';heading.lastChild.setAttribute('aria-label','새 CFD Template');heading.lastChild.title='새 CFD Template';const formList=node('div');formList.id='ewFormList';formList.setAttribute('aria-label','CFD Template 목록');formList.tabIndex=0;presetBox.append(heading,formList);sidebar.append(presetBox);const viewerCases=node('section');viewerCases.id='ewViewerCases';const caseHeading=node('div',null,'ew-project-heading'),reload=$('btnRun');reload.className='btn ew-heading-action';reload.removeAttribute('style');reload.title='다시 읽기';reload.setAttribute('aria-label','다시 읽기');$('btnRunTxt').textContent='다시 읽기';caseHeading.append(node('h2','CFD Case'),reload);viewerCases.append(caseHeading);const caseList=node('div');caseList.id='ewViewerCaseList';caseList.setAttribute('aria-label','CFD Case 목록');caseList.tabIndex=0;viewerCases.append(caseList);sidebar.append(viewerCases);$('side').prepend(sidebar);
    const emptyViewer=node('div');emptyViewer.id='ewViewerEmpty';emptyViewer.setAttribute('role','status');$('viz').append(emptyViewer);
    const panel=node('section');panel.id='ewPanel';panel.innerHTML=`
<header class="ew-heading"><div><h2 id="ewTitle">프로젝트</h2><p id="ewDescription"></p><p id="ewDefault"></p><p id="ewStorage"></p></div><div class="ew-bar"><button id="ewRename" class="btn">프로젝트 관리</button><button id="ewNewRun" class="btn pri" aria-label="+ CFD Case"><span class="ew-case-plus" aria-hidden="true">+</span> <span>CFD Case</span></button></div></header>
<p id="ewMessage" role="status"></p>
<div class="ew-layout"><div class="ew-list-panel"><div class="ew-list-heading"><div class="ew-bar"><h3>실행 목록 <span id="ewRunCount"></span></h3></div><input id="ewSearch" aria-label="실행 검색" placeholder="실행 검색"></div><div id="ewRows" role="group" aria-label="CFD 실행 목록"></div></div>
<div class="ew-detail-panel"><div class="ew-detail-head"><div class="ew-bar"><p id="ewFacts"></p><div id="ewStatus"></div></div><h3 id="ewRunTitle">실행 선택</h3><div class="ew-detail-actions"><button id="ewSettings" class="btn" disabled>Config 보기</button><button id="ewFolder" class="btn" disabled>결과 폴더</button><button id="ewCSV" class="btn" disabled title="전체 시계열·저장 공간 데이터를 CSV 묶음으로 내보내기">전체 CSV</button><button id="ewView" class="btn pri" disabled>열기</button><button id="ewEnqueue" class="btn" disabled>대기열에 추가</button><button id="ewRecovery" class="btn" hidden>다시하기</button><button id="ewStop" class="btn dng" hidden>실행 중단</button></div><div id="ewStats"></div><div id="ewProgress" hidden><div class="ew-bar"><span id="ewProgressLabel"></span><span id="ewProgressValue"></span></div><div class="pbar"><div id="ewProgressFill"></div></div></div><p id="ewRunError" role="alert"></p></div>
<div class="ew-detail-body"><div class="ew-setting-line"><span>종료 조건</span><span id="ewStopLabel">—</span></div><p id="ewConfigSummary"></p><p id="ewGoals"></p><section id="ewDifferenceBox"><h3>Config 차이 <span id="ewDifferenceCount"></span></h3><pre id="ewDifferences"></pre></section></div><section id="ewLogBox"><h3>솔버 로그</h3><pre id="ewLog"></pre></section></div></div>
<details id="ewQueueCard" class="ew-queue-card" open><summary class="ew-bar"><h3>대기열</h3><span id="ewQueueState"></span></summary><div class="ew-bar ew-queue-actions"><button id="ewQueueStart" class="btn pri">대기열 시작</button><button id="ewQueuePause" class="btn">다음 실행부터 일시정지</button></div><div id="ewQueue"></div><p id="ewQueueError"></p><div id="ewFailures" class="ew-bar" hidden><button id="ewRetry" class="btn" hidden>실패 사유 및 복구</button><button id="ewSkip" class="btn" hidden>건너뛰기</button></div></details>`;
    const hardware=$('sysCard');if(hardware){panel.insertBefore(hardware,panel.querySelector('.ew-layout'));hardware.style.display='';}
    document.querySelector('#dash .dlog').append(panel);
    for(const group of panel.querySelectorAll('details')){const summary=group.querySelector('summary'),hint=node('span',null,'ew-disclosure-state');summary.append(hint);const sync=()=>{hint.textContent=group.open?'접기':'펼치기';summary.setAttribute('aria-expanded',String(group.open));};group.addEventListener('toggle',sync);sync();}

    const icons={reload:'M3 10a9 9 0 1 1 2.6 8.4M3 4v6h6',add:'M12 4v16M4 12h16',settings:'M4 7h16M4 17h16M8 4v6M16 14v6',folder:'M3 7V5h7l2 2h9v13H3Z',play:'m8 5 11 7-11 7Z'};
    for(const [id,key] of [['ewRename','settings'],['ewSettings','settings'],['ewFolder','folder'],['ewQueueStart','play'],['btnRun','reload'],['ewCreateForm','add']]){const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('width',key==='add'?'22':key==='reload'?'18':'14');svg.setAttribute('height',key==='add'?'22':key==='reload'?'18':'14');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('fill','none');svg.setAttribute('stroke','currentColor');svg.setAttribute('stroke-width','1.6');svg.setAttribute('stroke-linecap','round');svg.setAttribute('stroke-linejoin','round');svg.setAttribute('aria-hidden','true');const path=document.createElementNS(svg.namespaceURI,'path');path.setAttribute('d',icons[key]);svg.append(path);$(id).prepend(svg);}
    $('ewNewRun').onclick=()=>openRun();$('ewRename').onclick=renameProject;$('ewView').onclick=viewResult;$('ewSearch').oninput=renderRuns;$('ewSettings').onclick=inspectSettings;
    $('ewCSV').onclick=exportCaseCSV;
    $('ewEnqueue').onclick=()=>queueAction('enqueue',{ids:[runId]});$('ewQueueStart').onclick=()=>queueAction('resume');$('ewQueuePause').onclick=()=>queueAction('pause');$('ewRetry').onclick=()=>recoveryDialog(data.queue.failure);$('ewRecovery').onclick=()=>recoveryDialog(runId);$('ewSkip').onclick=()=>queueAction('skip',{id:data.queue.failure});$('ewStop').onclick=()=>queueAction('stop',{id:runId});$('ewFolder').onclick=async()=>{try{await api('/folder',{id:runId});}catch(e){message(e.message);}};
    $('mCFD').onclick=showList;$('mViz').onclick=viewResult;$('btnRun').onclick=reloadViewerCases;
    document.body.classList.add('grouped');showList();
  }
  mount();refresh();setInterval(()=>{refresh();if(progressProject===projectId&&viewMode==='viewer')checkCaseProgress();},4000);
})();
