async page=>{
 page=await page.context().newPage();await page.goto('http://127.0.0.1:8712/');
 const results=[];const check=(name,value)=>{if(!value)throw Error(name);results.push(name);};
 await page.route('**/agent_controls.js',route=>route.fulfill({path:'cfd_studio/internal/agent_controls.js',contentType:'text/javascript'}));
 await page.addScriptTag({url:'/agent_controls.js'});
 await page.waitForFunction(()=>window.CFDWorkspaceState?.().projects.length>0);
 const initial=await page.evaluate(()=>CFDAgent.state());check('workspace discoverable',initial.workspace.projects.length>0);check('commands discoverable',await page.evaluate(()=>CFDAgent.describe().commands.includes('queue.start')));
 const project=initial.workspace.projects[0];
 const selected=await page.evaluate(async id=>CFDAgent.run('project.select',{id}),project.id);
 check('project selection uses visible UI',selected.status==='dispatched'&&selected.state.workspace.project_id===project.id);
 await page.waitForTimeout(650);
 if(project.runs.length){
  const r=await page.evaluate(async id=>CFDAgent.run('case.select',{id}),project.runs[0].id);check('Case selection visible',r.state.workspace.case_id===project.runs[0].id);
 }
 check('no case by guessed ID', (await page.evaluate(()=>CFDAgent.run('case.select',{id:'missing'}))).error==='CASE_NOT_FOUND');
 const creation=await page.evaluate(()=>CFDAgent.run('project.new'));await page.waitForSelector('.ew-project-dialog[open]');check('new project opens existing dialog',creation.status==='dispatched');check('active banner visible',await page.locator('#agentBannerText').textContent()==='에이전트 조작 중');
 let s=await page.evaluate(()=>CFDAgent.state());const name=s.controls.find(c=>c.label==='프로젝트 이름');check('form labels and fields discovered',!!name);
 const fill=await page.evaluate(target=>CFDAgent.run('ui.fill',{target,value:'Agent UI draft'}),name.target);check('draft input works',fill.status==='dispatched');
 check('background cannot be activated through modal',(await page.evaluate(()=>CFDAgent.run('cfd.open'))).error==='CONTROL_NOT_VISIBLE');
 s=await page.evaluate(()=>CFDAgent.state());await page.evaluate(target=>CFDAgent.run('ui.click',{target}),s.controls.find(c=>c.label==='취소').target);
 check('cancel leaves project unsaved',!(await page.evaluate(()=>CFDAgent.state())).workspace.projects.some(p=>p.name==='Agent UI draft'));
 const fixture=await page.evaluate(()=>{
  const d=document.createElement('dialog');d.id='agent-test-dialog';d.style.cssText='padding:24px;background:#202020;color:white';
  d.innerHTML='<h2>Agent input checks</h2><form><label>Count<input id="agentTestNumber" type="number" min="1" max="10" required value="2"></label><label>Choice<select><option value="a">Alpha</option><option value="b">Beta</option><option value="c" disabled>Blocked</option></select></label><label>Flag<input type="checkbox"></label><input aria-label="Readonly" readonly value="snapshot"><button type="button" disabled>Disabled</button><button type="submit">Save fixture</button></form>';
  d.querySelector('form').onsubmit=e=>{e.preventDefault();d.dataset.saved='true';};document.body.append(d);d.showModal();CFDInput.bind(d.querySelector('input'),{type:'integer'});return CFDAgent.state();
 });
 const n=fixture.controls.find(c=>c.label==='Count'),option=fixture.controls.find(c=>c.tag==='select'),flag=fixture.controls.find(c=>c.type==='checkbox'),readonly=fixture.controls.find(c=>c.label==='Readonly'),save=fixture.controls.find(c=>c.label==='Save fixture');
 check('only active dialog controls returned',fixture.controls.every(c=>!['ewNewRun','mCFD'].includes(c.target))&&fixture.dialog==='Agent input checks');
 check('wrong numeric type rejected',(await page.evaluate(target=>CFDAgent.run('ui.fill',{target,value:'bad'}),n.target)).error==='INVALID_INPUT');
 check('invalid edit preserves value',await page.locator('#agentTestNumber').inputValue()==='2');
 check('range error reported',(await page.evaluate(target=>CFDAgent.run('ui.fill',{target,value:'12'}),n.target)).error==='INPUT_INVALID');
 const corrected=await page.evaluate(target=>CFDAgent.run('ui.fill',{target,value:'5'}),n.target);check('corrected numeric accepted',corrected.status==='dispatched');
 check('disabled option rejected',(await page.evaluate(target=>CFDAgent.run('ui.select',{target,value:'c'}),option.target)).error==='OPTION_UNAVAILABLE');
 check('select fires same UI changes',(await page.evaluate(target=>CFDAgent.run('ui.select',{target,value:'b'}),option.target)).state.controls.find(c=>c.target===option.target).value==='b');
 check('checkbox uses native click',(await page.evaluate(target=>CFDAgent.run('ui.check',{target,checked:true}),flag.target)).state.controls.find(c=>c.target===flag.target).checked===true);
 check('readonly cannot change',(await page.evaluate(target=>CFDAgent.run('ui.fill',{target,value:'bad'}),readonly.target)).error==='NOT_EDITABLE');
 check('disabled button rejected',(await page.evaluate(target=>CFDAgent.run('ui.click',{target}),fixture.controls.find(c=>c.label==='Disabled').target)).error==='CONTROL_DISABLED');
 const simultaneous=await page.evaluate(async target=>{const first=CFDAgent.run('ui.fill',{target,value:'6'});const invalid=await CFDAgent.run('unknown');const second=await CFDAgent.run('ui.fill',{target,value:'7'});return {first:await first,second,invalid};},n.target);
 check('concurrent commands cannot unlock each other',simultaneous.first.status==='dispatched'&&simultaneous.second.error==='BUSY');
 await page.evaluate(target=>CFDAgent.run('ui.click',{target}),save.target);check('native form submit reached',await page.locator('#agent-test-dialog').getAttribute('data-saved')==='true');
 await page.evaluate(()=>{window.agentSignals=[];window.addEventListener('cfd-agent-pause',e=>agentSignals.push(e.detail));window.addEventListener('cfd-agent-resume',e=>agentSignals.push(e.detail));});
 await page.locator('#agentBannerStop').click();check('pause remains usable above dialog',(await page.evaluate(()=>CFDAgent.run('ui.fill',{target:CFDAgent.state().controls[0].target,value:'8'}))).error==='PAUSED');
 check('pause signal delivered',await page.evaluate(()=>agentSignals.at(-1).type==='pause'&&CFDAgent.state().paused));
 await page.evaluate(()=>{window.agentWaitResult=null;CFDAgent.waitForResume({timeoutMs:30000}).then(r=>window.agentWaitResult=r);});
 await page.waitForTimeout(150);check('agent wait stays pending',await page.evaluate(()=>agentWaitResult===null));
 check('finish cannot clear user pause',await page.evaluate(()=>CFDAgent.finish().status==='paused'&&CFDAgent.state().paused));
 await page.locator('#agentBannerStop').click();await page.waitForFunction(()=>window.agentWaitResult?.status==='resumed');
 check('resume signal releases waiting agent',await page.evaluate(()=>agentSignals.at(-1).type==='resume'&&!CFDAgent.state().paused));
 await page.evaluate(()=>document.getElementById('agent-test-dialog').remove());
 check('detached target rejected',(await page.evaluate(target=>CFDAgent.run('ui.fill',{target,value:'3'}),n.target)).error==='CONTROL_NOT_VISIBLE');
 // The user's pause control remains reachable above modal dialogs via popover.
 await page.locator('#agentPause').click();check('pause blocks future commands',(await page.evaluate(()=>CFDAgent.run('cfd.open'))).error==='PAUSED');await page.locator('#agentPause').click();
 const events=await page.evaluate(()=>CFDAgent.history());check('activity excludes entered values',!JSON.stringify(events).includes('Agent UI draft'));check('receipts never claim calculation completion',events.every(e=>['dispatched','rejected'].includes(e.status)));
 await page.keyboard.press('Alt+Shift+A');check('hotkey opens guide',await page.locator('#agentPanel').isVisible());
 await page.locator('#agentPromptToggle').click();check('prompt available without clipboard permissions',(await page.locator('#agentPrompt').inputValue()).includes('CFDAgent.state()'));
 await page.locator('#agentDock').screenshot({path:'output/playwright/agent-controls.png'});
 await page.keyboard.press('Alt+Shift+A');
 const sess=await page.evaluate(()=>CFDAgent.session);await page.reload();await page.addScriptTag({url:'/agent_controls.js'});check('reload resets ephemeral session and activity',await page.evaluate(old=>CFDAgent.session!==old&&CFDAgent.history().length===0,sess));
 await page.evaluate(()=>CFDI18n.setLanguage('ja'));await page.keyboard.press('Alt+Shift+A');
 check('Japanese agent guide localized',await page.locator('#agentCopy').textContent()==='案内プロンプトをコピー');
 await page.evaluate(()=>CFDI18n.setLanguage('en'));check('English agent guide localized',await page.locator('#agentCopy').textContent()==='Copy agent prompt');
 await page.evaluate(()=>CFDI18n.setLanguage('ko'));
 await page.evaluate(()=>CFDAgent.run('cfd.open'));
 await page.locator('#agentDock').screenshot({path:'output/playwright/agent-guide.png'});
 await page.locator('#agentBanner').screenshot({path:'output/playwright/agent-banner.png'});
 await page.evaluate(()=>CFDAgent.finish());check('finished task hides activity banner',!await page.locator('#agentBanner').isVisible());
 await page.close();
 return {passed:results.length,results};
}
