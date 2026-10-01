/* Versioned, browser-local agent interface. All mutations go through visible UI controls. */
(function(root){
'use strict';
const VERSION='1.1';
const shortcuts={
 'cfd.open':'mCFD','viewer.open':'mViz','project.find':'ewFindProject','project.new':'ewCreateProject',
 'project.manage':'ewRename','case.new':'ewNewRun','config.open':'ewSettings','result.open':'ewView',
 'result.refresh':'btnRun','result.csv':'ewCSV','template.new':'ewCreateForm',
 'queue.add':'ewEnqueue','queue.start':'ewQueueStart','queue.pause':'ewQueuePause','case.stop':'ewStop',
 'case.recovery':'ewRecovery','queue.skip':'ewSkip','settings.open':'settingsBtn'
};
const commands=[...Object.keys(shortcuts),'project.select','case.select','viewer.mode','ui.click','ui.fill','ui.select','ui.check','config.json.open','config.json.fill','config.json.apply'];
function validate(command,args={}){
 if(!commands.includes(command))throw Error('UNKNOWN_COMMAND');
 if(!args||typeof args!=='object'||Array.isArray(args))throw Error('INVALID_ARGUMENTS');
 const required=command.endsWith('.select')&&command!=='ui.select'?'id':command==='viewer.mode'?'mode':command.startsWith('ui.')?'target':null;
 if(required&&(typeof args[required]!=='string'||!args[required]))throw Error('MISSING_'+required.toUpperCase());
 if(command==='viewer.mode'&&!['3d','data'].includes(args.mode))throw Error('INVALID_MODE');
 if(['ui.fill','ui.select'].includes(command)&&typeof args.value!=='string')throw Error('VALUE_MUST_BE_STRING');
 if(command==='config.json.open'&&!['config','geometry'].includes(args.scope))throw Error('INVALID_JSON_SCOPE');
 if(command==='config.json.fill'){if(typeof args.value!=='string')throw Error('VALUE_MUST_BE_STRING');if(new TextEncoder().encode(args.value).length>1000000)throw Error('JSON_TOO_LARGE');try{JSON.parse(args.value);}catch(_){throw Error('INVALID_JSON');}}
 if(command==='ui.check'&&typeof args.checked!=='boolean')throw Error('CHECKED_MUST_BE_BOOLEAN');
 return args;
}
function prompt(){return `CFD Studio agent interface v${VERSION}
Operate CFD Studio in the user's visible browser tab using window.CFDAgent. Do not modify source files, invoke private APIs, edit project files, or start a second hidden browser session to operate this workspace.
Preparation: the user starts CFD Studio (Windows: cfd_studio/실행.bat). Connect your browser automation tool to that existing visible tab. A browser tool capable of evaluating JavaScript in that tab is required for these commands; without it, use the same visible buttons with a computer-use tool. This interface does not install or connect an LLM, enable browser remote debugging, or expose an HTTP/MCP command endpoint.
1. Read CFDAgent.describe(), then CFDAgent.state(). Check version, session, project, Case, dialogs, enabled controls, queue, and notices. If CFDAgent is absent, reload only when unsaved edits can be preserved, or ask the user to restart an idle Studio. Never stop a running solver or close the user's browser.
2. Use await CFDAgent.run(command, args). Each command operates the visible UI and returns a receipt plus a fresh state. Observe between commands. Read element tokens from state().controls; tokens are specific to this page session and become invalid when a control is replaced. Never guess IDs or reuse stale tokens.
3. Select project and Case by IDs returned by state().workspace. Use project.select {id}, case.select {id}. For ui.fill use {target, value:"..."}; ui.select uses an option value, ui.check uses {target, checked:true|false}, ui.click uses {target}. Edits trigger the existing UI validation. Read-only snapshots remain read-only. ui.fill does not upload files; use a browser file-upload tool for an observed file input.
4. Guided workflow: explain the target project, Template/solver and intended task first. Prepare geometry and Config through the JSON commands below, not field-by-field entry. Show the draft and ask the user to verify what each setting means, units, shape/region assignments, initial/boundary conditions, termination and output intervals. Wait for their confirmation before final saving. Saving is separate from queueing and calculation. After saving, explain the queue contents and ask for confirmation before queue.add or queue.start; stop/retry likewise require the user's requested scope. Do not interpret a request to prepare Config as permission to run CFD. Guide one stage at a time and report the result before the next stage. These confirmations are a guided agent procedure, not a server-enforced approval system.
4a. JSON entry: first open Config for the intended draft (or a new Case copy of a readonly snapshot). Call config.json.open {scope:"geometry"} for the complete spatial document, or {scope:"config"} for the complete Config/Template schema. Read state().json (scope,title,value,readonly,dirty), parse its value and preserve the actual schema, identifiers, units, metadata and unrelated fields. A Template schema with version/fields is NOT a Config value object; a spatial document is NOT a bare geometry object. Never replace one format with another or infer missing values. Use config.json.fill {value:JSON.stringify(document,null,2)} to populate the JSON buffer, then config.json.apply to validate/apply the draft and update the preview. Inspect state().notices and reread state().json; dispatched alone is not acceptance. On errors, correct the same draft, never bypass validators. JSON apply does not save the project/Case or run CFD. Keep the draft and 3D preview visible for user review. Ask the user to check the settings before the final Save button. The existing JSON pane is the visible bulk-entry channel; no direct file or hidden HTTP writes are needed.
4b. New project: cfd.open, project.new, observe and fill visible inputs, choose Template and optional preset, complete Config through JSON, obtain user confirmation, then click the visible Save control. Case: case.new, prepare Config/termination/name, explain and obtain user confirmation, then click Save. Use displayed units and solver-supported fields. Do not invent geometry, physical properties or boundary conditions. Draft changes are not saved until the same Save button is used.
5. Only start/stop/retry calculations when the user requested that action. queue.add adds the selected draft; queue.start resumes the entire displayed queue, possibly across projects. Check every queued Case before starting. case.recovery opens the existing recovery dialog; read its reason. Do not automatically retry failed/completed jobs or bypass validation.
6. Viewer: viewer.open, viewer.mode {mode:"3d"|"data"}, select Case, result.refresh. Use observed controls for quantities, coordinates, playback and export. Select one Case at a time. Data Sheet: left panel switches between whole-domain mean and point time series (up to three quantities); right panel samples a line at a saved frame using nearest saved cells. Observe the actual field, frame, coordinate and sample-count controls; do not describe this sampling as interpolation. 100% visualization readiness is not physical validation. Distinguish saved frames, solver progress and completed CFD.
7. A receipt with status "dispatched" means the UI action was delivered, NOT that a save/export/CFD run succeeded. Poll state() at reasonable intervals and inspect notices, dialogs, queue, Case status and log. If an error, blocked control, changed selection or concurrent user edit appears, stop that sequence and inspect again. Do not automatically resend a timed-out action. Report actual saved/run results only.
8. While operating, the top-center banner blinks and the user can press the top-right Agent stop button. This immediately blocks subsequent commands, updates state().paused and state().signal, and emits the window event 'cfd-agent-pause'. Your controller MUST enter a waiting state on that event or a PAUSED receipt. Use await CFDAgent.waitForResume({timeoutMs:30000}); if status remains 'paused', keep waiting without actions until the user presses Resume. The resume event is 'cfd-agent-resume'. Read state() before every new action to avoid missing an event. Do not bypass the pause by reloading, opening another tab, calling UI functions directly or simulating user Resume. Studio cannot suspend your LLM provider process; your controller must honor this signal. Pausing does not stop an in-flight command or solver. Call CFDAgent.finish() when your requested work is done to clear the active banner; finish does not clear a user pause. Respect PAUSED/BUSY responses. Reconnect explicitly after a page reload; session IDs change. Agent activity contains action labels, not Config values, and is kept in memory only.
Commands: ${commands.join(', ')}
Read methods: CFDAgent.describe(), CFDAgent.state(), CFDAgent.prompt(), CFDAgent.history(), CFDAgent.waitForResume({timeoutMs:30000}), CFDAgent.finish()
Example: await CFDAgent.run('config.open'); then inspect CFDAgent.state().controls before editing.
Report in the user's language. User-defined names and Config values must not be translated.`;}
if(typeof module!=='undefined')module.exports={VERSION,commands,validate,prompt};
if(!root.document||root.CFDAgent)return;
const doc=root.document,$=id=>doc.getElementById(id),tokens=new WeakMap(),elements=new Map(),history=[];
const session=root.crypto.randomUUID();let sequence=0,busy=false,paused=false,active=false,panel,indicator,banner,dockShown=false,lastAction='',signalSequence=0,lastSignal=null;
const tr=s=>root.CFDI18n?.translate(s)||s;
function visible(e){return !!e?.isConnected&&!e.closest('[hidden],[inert]')&&!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden'&&getComputedStyle(e).display!=='none';}
function scope(){
 const modal=[...doc.querySelectorAll('dialog:modal')].filter(visible).at(-1);if(modal)return modal;
 return [...doc.querySelectorAll('.mbg,#modalBg')].filter(visible).at(-1)||doc.body;
}
function label(e){
 const label=e.getAttribute('aria-label')||[...e.labels||[]].map(x=>[...x.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent).join(' ')).join(' ').trim();
 return (label||e.title||e.closest('.fc-field')?.querySelector('.fc-caption')?.textContent||e.textContent||e.name||e.id||e.placeholder||e.type||e.tagName).trim().slice(0,180);
}
function token(e){if(!tokens.has(e)){const id='ui-'+(++sequence);tokens.set(e,id);elements.set(id,e);}return tokens.get(e);}
function disabled(e){return e.matches(':disabled')||e.getAttribute('aria-disabled')==='true';}
function controls(){
 for(const [id,e] of elements)if(!e.isConnected)elements.delete(id);
 return [...scope().querySelectorAll('button,input:not([type=hidden]),textarea,select,summary,[role=button]')].filter(e=>visible(e)&&!e.closest('[data-agent-ui]')).map(e=>({
  target:token(e),label:label(e),tag:e.tagName.toLowerCase(),type:e.type||null,disabled:disabled(e),readonly:!!e.readOnly,
  ...(e.matches('input:not([type=password]):not([type=file]),textarea,select')?{value:e.value}:{}),
  ...(e.matches('input[type=checkbox],input[type=radio]')?{checked:e.checked}:{}),
  ...(e.matches('select')?{options:[...e.options].map(o=>({value:o.value,label:o.text,disabled:o.disabled||o.parentElement.disabled}))}:{}),
  ...(e.getAttribute('min')!==null?{min:e.getAttribute('min')}:{}),...(e.getAttribute('max')!==null?{max:e.getAttribute('max')}:{}),
  ...(e.placeholder?{placeholder:e.placeholder}:{}),...(e.required?{required:true}:{}),...(e.getAttribute('aria-invalid')==='true'?{invalid:true}:{}),
  ...(e.getAttribute('data-config-path')?{path:e.getAttribute('data-config-path')}:{}),
  ...(e.hasAttribute('aria-pressed')?{pressed:e.getAttribute('aria-pressed')==='true'}:{})
 }));
}
function state(){return {version:VERSION,session,busy,paused,active,signal:lastSignal?{...lastSignal}:null,lastAction,workspace:root.CFDWorkspaceState?.()||null,
 screen:doc.body.classList.contains('execution-viewer')?(doc.body.classList.contains('data-sheet-viewer')?'data':'3d'):'cfd',
 dialog:scope()===doc.body?null:scope().querySelector('h2,h3')?.textContent?.trim()||scope().id,
 json:jsonState(),controls:controls(),notices:[...doc.querySelectorAll('[role=alert],[role=status],.fc-error,.input-feedback,.toast,#ewRunError,#ewQueueError')].filter(e=>visible(e)&&!e.closest('[data-agent-ui]')).map(e=>e.textContent.trim()).filter(Boolean).slice(-25),
 log:$('ewLog')?.textContent?.slice(-8000)||''};}
function jsonState(){const pane=scope().querySelector('.fc-json-pane'),area=pane?.querySelector('textarea');return area&&visible(area)?{scope:pane.dataset.jsonScope||'section',title:pane.querySelector('strong')?.textContent||'',value:area.value,readonly:area.readOnly,dirty:area.dataset.jsonDirty==='true'}:null;}
function fail(code){throw Error(code);}
function find(command,args){
 if(command.startsWith('config.json.')){const selector=command==='config.json.open'?'[data-agent-json-open="'+args.scope+'"]':command==='config.json.fill'?'.fc-json-pane textarea':'[data-agent-json-apply]';return scope().querySelector(selector)||fail('JSON_EDITOR_NOT_OPEN');}
 if(command.startsWith('ui.'))return elements.get(args.target)||fail('STALE_TARGET');
 if(command==='project.select')return [...doc.querySelectorAll('#ewProjects [data-project-id]')].find(e=>e.dataset.projectId===args.id)||fail('PROJECT_NOT_FOUND');
 if(command==='case.select'){
  const selector=doc.body.classList.contains('execution-viewer')?'#ewViewerCaseList [data-run-id] button':'#ewRows [data-run-id]';
  return [...doc.querySelectorAll(selector)].find(e=>(e.dataset.runId||e.closest('[data-run-id]')?.dataset.runId)===args.id)||fail('CASE_NOT_FOUND');
 }
 const viewer=doc.body.classList.contains('execution-viewer');
 if(['project.find','project.new'].includes(command)&&viewer)fail('OPEN_CFD_FIRST');
 if(command==='viewer.mode'&&!viewer)fail('OPEN_VIEWER_FIRST');
 return $(command==='viewer.mode'?(args.mode==='3d'?'ewFindProject':'ewCreateProject'):shortcuts[command])||fail('CONTROL_NOT_FOUND');
}
function available(e){if(!visible(e)||!scope().contains(e))fail('CONTROL_NOT_VISIBLE');if(disabled(e))fail('CONTROL_DISABLED');}
function emitInput(e){e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));}
// HTMLElement.click preserves native submission and listener behavior. Awaiting arbitrary
// onclick callbacks would bypass browser activation; receipts intentionally mean dispatched.
function operate(command,args,e){
 available(e);e.scrollIntoView({block:'nearest',inline:'nearest',behavior:'smooth'});e.focus({preventScroll:true});
 e.classList.add('agent-focus');setTimeout(()=>e.classList.remove('agent-focus'),1300);
 if(command==='ui.fill'||command==='config.json.fill'){
  if(!e.matches('input,textarea')||e.readOnly||['checkbox','radio','file','password','button','submit','reset','hidden'].includes(e.type))fail('NOT_EDITABLE');
  const original=e.value;
  if(e.selectionStart!==null){e.select();const event=new InputEvent('beforeinput',{bubbles:true,cancelable:true,inputType:'insertText',data:args.value});if(!e.dispatchEvent(event))fail('INVALID_INPUT');}
  e.value=args.value;
  if(e.value!==args.value){e.value=original;fail('INVALID_INPUT');}
  emitInput(e);
  if(e.value!==args.value)fail('INPUT_REJECTED');
  if(root.CFDInput&&!root.CFDInput.check(e))fail('INPUT_INVALID');
 }else if(command==='ui.select'){
  if(!e.matches('select')||e.multiple)fail('NOT_SINGLE_SELECT');
  const option=[...e.options].find(o=>o.value===args.value);if(!option||option.disabled||option.parentElement.disabled)fail('OPTION_UNAVAILABLE');
  e.value=args.value;emitInput(e);
 }else if(command==='ui.check'){
  if(!e.matches('input[type=checkbox],input[type=radio]'))fail('NOT_CHECKABLE');
  if(e.type==='radio'&&!args.checked)fail('SELECT_ANOTHER_RADIO');
  if(e.checked!==args.checked)e.click();
 }else{
  if(!e.matches('button,summary,[role=button],input[type=button],input[type=submit],input[type=checkbox],input[type=radio]'))fail('NOT_CLICKABLE');
  e.click();
 }
}
function paint(){
 if(!indicator)return;
 $('agentBannerText').textContent=tr(paused?'에이전트 일시정지':'에이전트 조작 중');
 $('agentBannerStop').textContent=tr(paused?'에이전트 조작 재개':'에이전트 조작 중단');
 banner.classList.toggle('agent-paused',paused);syncFloating();
 $('agentStatus').textContent=tr(paused?'에이전트 일시정지':busy?'명령 전달 중':'에이전트 준비');
 $('agentLast').textContent=lastAction;
 $('agentPause').textContent=tr(paused?'명령 허용':'명령 일시정지');
 $('agentPause').setAttribute('aria-pressed',String(paused));
 $('agentHistory').textContent=history.slice(-10).map(x=>`${new Date(x.time).toLocaleTimeString()}  ${x.command}  ${tr(x.status==='dispatched'?'전달됨':'전달 실패')}${x.error?' · '+x.error:''}`).join('\n');
}
function syncFloating(){
 const host=[...doc.querySelectorAll('dialog:modal')].filter(visible).at(-1)||doc.body;
 for(const [element,shown] of [[indicator,dockShown],[banner,active||paused]]){
  if(!element)continue;
  // A popover outside a modal dialog is inert even when visually in the top layer.
  if(element.parentElement!==host)host.append(element);
  if(shown&&!element.matches(':popover-open'))element.showPopover();
  if(!shown&&element.matches(':popover-open'))element.hidePopover();
 }
}
function showIndicator(){dockShown=true;paint();}
function setPaused(value){
 paused=value;if(value)active=true;
 lastSignal={type:value?'pause':'resume',sequence:++signalSequence,time:new Date().toISOString(),session};
 paint();root.dispatchEvent(new CustomEvent('cfd-agent-'+lastSignal.type,{detail:{...lastSignal}}));
}
function waitForResume({timeoutMs=30000}={}){
 if(!Number.isFinite(timeoutMs)||timeoutMs<0||timeoutMs>60000)return Promise.reject(Error('INVALID_TIMEOUT'));
 const reply=()=>({status:paused?'paused':'resumed',session,signal:lastSignal?{...lastSignal}:null});
 if(!paused)return Promise.resolve(reply());
 return new Promise(resolve=>{
  const finish=()=>{clearTimeout(timer);root.removeEventListener('cfd-agent-resume',finish);resolve(reply());};
  const timer=setTimeout(finish,timeoutMs);root.addEventListener('cfd-agent-resume',finish,{once:true});
 });
}
function finish(){if(busy)return {status:'rejected',error:'BUSY'};active=false;paint();return {status:paused?'paused':'idle',session};}

async function run(command,args={}){
 let ownsLock=false;
 const receipt={id:root.crypto.randomUUID(),time:new Date().toISOString(),command,status:'rejected',session};
 try{
  validate(command,args);if(paused)fail('PAUSED');if(busy)fail('BUSY');
  busy=true;ownsLock=true;const e=find(command,args);available(e);lastAction=command+' · '+label(e);receipt.target=token(e);active=true;showIndicator();
  operate(command,args,e);
  // Give event handlers and screen updates a chance to render, without waiting for a solver.
  await new Promise(resolve=>setTimeout(resolve,120));receipt.status='dispatched';
 }catch(error){receipt.error=error.message;}finally{
  // A rejected concurrent request must not unlock the command already in flight.
  if(ownsLock)busy=false;
 }
 history.push(receipt);if(history.length>100)history.shift();if(receipt.target)showIndicator();else paint();
 root.dispatchEvent(new CustomEvent('cfd-agent-action',{detail:{...receipt}}));
 return {...receipt,state:state()};
}
function open(){panel.hidden=!panel.hidden;showIndicator();}
function mount(){
 const style=doc.createElement('style');style.textContent=`.agent-focus{outline:2px solid #79b7ff!important;outline-offset:3px!important}#agentDock{position:fixed;inset:auto 18px 18px auto;margin:0;width:330px;max-width:calc(100vw - 36px);padding:12px;border:1px solid var(--line,#424242);border-radius:12px;background:var(--surface,#191919);color:var(--ink,#eee);font:12px system-ui;box-shadow:0 8px 32px #0006}#agentDock .agent-row{display:flex;align-items:center;gap:8px}#agentStatus{flex:1}#agentLast{display:block;color:var(--muted,#aaa);font-size:11px;margin-top:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}#agentPanel{margin-top:12px}#agentPanel[hidden]{display:none}#agentPanel textarea{box-sizing:border-box;width:100%;min-height:84px;resize:vertical;background:var(--page,#111);color:inherit;border:1px solid var(--line,#444);border-radius:7px;padding:8px;font:12px Consolas,monospace;user-select:text}#agentPanel p{line-height:1.5;color:var(--muted,#bbb)}#agentHistory{max-height:140px;overflow:auto;white-space:pre-wrap;font:10px Consolas,monospace;user-select:text}#agentDock button{font:inherit}#agentDock .agent-row button{flex:none}#agentSettingsRow{margin:12px 0}#agentPrompt{max-height:220px}#agentBanner{position:fixed;inset:10px 16px auto 16px;margin:0;padding:0;border:0;background:transparent;color:#fff;overflow:visible;width:auto;pointer-events:none;font:13px system-ui}#agentBanner .agent-banner-row{display:flex;align-items:center;justify-content:center;min-height:36px}#agentBannerText{padding:8px 16px;border:1px solid #77baff70;border-radius:20px;background:#13233bf2;box-shadow:0 2px 12px #0006;animation:agentBlink 1.5s ease-in-out infinite}#agentBannerStop{position:absolute;right:0;top:0;pointer-events:auto;min-height:36px;padding:8px 14px;border:1px solid #c5666690;border-radius:8px;background:#3b1d1df5;color:#ffd9d9;font:inherit;cursor:pointer}#agentBanner.agent-paused #agentBannerText{animation:none;border-color:#a49567;background:#302b1df5}@keyframes agentBlink{0%,100%{opacity:1}50%{opacity:.4}}@media(prefers-reduced-motion:reduce){#agentBannerText{animation:none}}@media(max-width:640px){#agentBanner .agent-banner-row{justify-content:flex-start}#agentBannerText{font-size:11px;padding:8px}#agentBannerStop{font-size:11px}}`;doc.head.append(style);
 indicator=doc.createElement('aside');indicator.id='agentDock';indicator.dataset.agentUi='';indicator.setAttribute('popover','manual');indicator.setAttribute('aria-label','Agent');
 indicator.innerHTML='<div class="agent-row"><strong id="agentStatus" role="status"></strong><button type="button" class="btn" id="agentPause"></button><button type="button" class="btn" id="agentExpand" aria-label="에이전트 안내">?</button><button type="button" class="btn" id="agentHide" aria-label="닫기">×</button></div><span id="agentLast" translate="no"></span><section id="agentPanel" hidden><p>같은 브라우저 탭의 버튼과 입력창을 명령으로 조작합니다</p><div class="agent-row"><button type="button" class="btn" id="agentCopy">안내 프롬프트 복사</button><button type="button" class="btn" id="agentPromptToggle">안내 보기</button></div><textarea id="agentPrompt" aria-label="에이전트 안내 프롬프트" readonly hidden translate="no"></textarea><p>명령 입력</p><textarea id="agentCommand" aria-label="에이전트 명령" spellcheck="false" translate="no" placeholder=\'{"command":"config.open","args":{}}\'></textarea><button type="button" class="btn" id="agentExecute">명령 실행</button><p id="agentReply" role="status" translate="no"></p><pre id="agentHistory" translate="no"></pre><p>Alt + Shift + A · 안내 열기</p></section>';
 doc.body.append(indicator);
 banner=doc.createElement('aside');banner.id='agentBanner';banner.dataset.agentUi='';banner.setAttribute('popover','manual');
 banner.innerHTML='<div class="agent-banner-row"><strong id="agentBannerText" role="status"></strong><button type="button" id="agentBannerStop"></button></div>';
 doc.body.append(banner);$('agentBannerStop').onclick=()=>setPaused(!paused);
 panel=$('agentPanel');$('agentPrompt').value=prompt();
 $('agentExpand').onclick=open;$('agentHide').onclick=()=>{dockShown=false;syncFloating();};$('agentPause').onclick=()=>setPaused(!paused);
 $('agentCopy').onclick=async()=>{try{await navigator.clipboard.writeText(prompt());$('agentReply').textContent=tr('안내 복사 완료');}catch(_){$('agentPrompt').hidden=false;$('agentPrompt').select();$('agentReply').textContent=tr('안내를 선택하여 복사하세요');}};
 $('agentPromptToggle').onclick=()=>{$('agentPrompt').hidden=!$('agentPrompt').hidden;};
 $('agentExecute').onclick=async()=>{try{const value=JSON.parse($('agentCommand').value),reply=await run(value.command,value.args||{});$('agentReply').textContent=reply.status+(reply.error?' · '+reply.error:'');}catch(_){$('agentReply').textContent=tr('올바른 JSON 명령을 입력하세요');}};
 const row=doc.createElement('div');row.id='agentSettingsRow';row.className='language-row';const title=doc.createElement('span');title.textContent='LLM 에이전트';const b=doc.createElement('button');b.type='button';b.className='btn';b.textContent='에이전트 안내';b.onclick=()=>{panel.hidden=false;showIndicator();};row.append(title,b);$('languageOptions')?.after(row);
 doc.addEventListener('keydown',e=>{if(e.altKey&&e.shiftKey&&e.code==='KeyA'&&!e.repeat){e.preventDefault();open();}});
 root.addEventListener('cfd-language-change',paint);
 new MutationObserver(syncFloating).observe(doc.body,{subtree:true,childList:true,attributes:true,attributeFilter:['open']});
}
root.CFDAgent=Object.freeze({version:VERSION,session,describe:()=>({version:VERSION,session,transport:'current-browser-tab',commands:[...commands],prompt:prompt(),receipt:'dispatched does not mean saved or completed'}),state,run,prompt,waitForResume,finish,history:()=>history.map(x=>({...x}))});
mount();
})(globalThis);
