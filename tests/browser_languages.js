// Run on the isolated review server; no calculation or production writes.
async page=>{
 const checks=[],errors=[];const check=(value,label)=>{if(!value)throw Error(label);checks.push(label);};
 const onerror=e=>errors.push(e.message);page.on('pageerror',onerror);
 await page.route('**/api/settings?*',r=>r.fulfill({json:{ok:true,settings:{cpu_pct:60,cpu_logical:8,mpi_np:'auto',mpi_effective:4,gpu_index:'auto',pressure_solver_mode:'cpu',gpu_devices:[],gpu_only:{ready:false,message:'전용 실행 환경 확인 필요'}}}}));
 await page.goto('http://127.0.0.1:18760');await page.setViewportSize({width:1440,height:1000});
 await page.evaluate(()=>CFDI18n.setLanguage('ko'));
 const before=await (await page.request.get('http://127.0.0.1:18760/api/executions')).json();
 await page.getByRole('button',{name:'환경 설정',exact:true}).click();await page.locator('#languageToggle').click();
 for(const [lang,label,projectLabel] of [['en','Settings','New project'],['ja','環境設定','新規プロジェクト'],['ko','환경 설정','새 프로젝트']]){
  await page.locator('[data-language='+lang+']').click();await page.waitForFunction(l=>document.documentElement.lang===l,lang);
  check(await page.locator('[data-language='+lang+']').getAttribute('aria-pressed')==='true',lang+' selected indicator');
  check(await page.locator('#settingsBg h3').innerText().then(t=>t.includes(label)),lang+' settings heading');
  check(await page.locator('#ewCreateProject').innerText()===projectLabel,lang+' dynamic project action');
  check(await page.locator('#setCpu').inputValue()==='60',lang+' numeric settings preserved');
  if(lang!=='ko')await page.locator('#settingsBg .mbox').screenshot({path:'output/playwright/language-'+lang+'.png'});
 }
 await page.locator('[data-language=ja]').click();await page.reload();await page.waitForSelector('#ewCreateForm');
 check(await page.locator('html').getAttribute('lang')==='ja','language restored after reload');
 check(await page.locator('#ewCreateProject').innerText()==='新規プロジェクト','dynamically rebuilt controls translated');
 await page.locator('#ewCreateProject').click();const project=page.locator('dialog.ew-dialog');await project.waitFor();await project.locator('[name=name]').fill('저장');await project.locator('[name=description]').fill('온도 · 사용자 원문');
 await page.evaluate(()=>CFDI18n.setLanguage('en'));
 check(await project.locator('[name=name]').inputValue()==='저장','user name preserved');check(await project.locator('[name=description]').inputValue()==='온도 · 사용자 원문','user description preserved');
 await project.locator('[name=form_id]').selectOption('immersion');check(await project.locator('[name=form_id]').inputValue()==='immersion','Template value unchanged');
 await project.getByRole('button',{name:'Cancel',exact:true}).click();
 await page.locator('#ewCreateForm').click();const form=page.locator('.ew-form-dialog');await form.waitFor();await form.locator('[name=name]').fill('Language template');await form.locator('[name=solver]').selectOption('icoFoam');await form.locator('[data-wizard]').click();
 const wizard=page.locator('.fw-dialog');await wizard.waitFor();check(await wizard.innerText().then(t=>t.includes('Which fluid will be analyzed?')),'new questionnaire translated');
 await wizard.locator('input[name=medium][value=gas]').check();await page.evaluate(()=>CFDI18n.setLanguage('ja'));
 check(await wizard.locator('input[name=medium][value=gas]').isChecked(),'questionnaire selection survives language switch');check(await wizard.innerText().then(t=>t.includes('どの流体を解析しますか')),'questionnaire switches to Japanese');
 await wizard.getByRole('button',{name:'キャンセル',exact:true}).click();await form.getByRole('button',{name:'キャンセル',exact:true}).click();
 await page.getByRole('button',{name:'!',exact:true}).click();await page.locator('#ifT1').click();
 check(await page.locator('#ifB1').textContent().then(t=>t.includes('プロジェクトを探す')),'Japanese user guide');
 await page.evaluate(()=>CFDI18n.setLanguage('en'));check(await page.locator('#ifB1').textContent().then(t=>t.includes('Find project')),'English user guide');
 await page.evaluate(()=>CFDI18n.setLanguage('ko'));check(await page.locator('#ifB1').textContent().then(t=>t.includes('기존 프로젝트 등록')),'original Korean help restored');
 await page.locator('#infoBg').getByRole('button',{name:'닫기 ✕',exact:true}).click();
 // Synthetic DOM fixture verifies translator exclusion and late updates independently of result content.
 check(await page.evaluate(async()=>{
  const box=document.createElement('div');box.id='languageFixture';box.innerHTML='<span id="languageStatus">대기</span><pre>저장 · 온도</pre><span translate="no">온도</span><select><option>저장</option></select>';document.body.append(box);CFDI18n.setLanguage('en');await new Promise(r=>setTimeout(r,40));
  const ok=box.querySelector('pre').textContent==='저장 · 온도'&&box.querySelector('[translate=no]').textContent==='온도'&&box.querySelector('option').value==='저장'&&box.querySelector('option').textContent==='Save';
  box.querySelector('#languageStatus').textContent='완료';await new Promise(r=>setTimeout(r,40));const updated=box.querySelector('#languageStatus').textContent==='Completed';CFDI18n.setLanguage('ja');await new Promise(r=>setTimeout(r,40));const switched=box.querySelector('#languageStatus').textContent==='完了';box.remove();return ok&&updated&&switched;
 }),'logs, names and option values preserved; late status translated');
 // Opening language preferences during computation must not enable resource changes.
 await page.evaluate(()=>{window.languageOriginalBusy=runBusyNow;runBusyNow=()=>true;});
 await page.getByRole('button',{name:'環境設定',exact:true}).click();
 check(await page.locator('#setSave').isDisabled()&&await page.locator('#setCpu').isDisabled(),'compute settings locked while busy');
 await page.locator('#languageToggle').click();await page.locator('[data-language=en]').click();check(await page.locator('html').getAttribute('lang')==='en','language remains available while busy');
 await page.evaluate(()=>{runBusyNow=window.languageOriginalBusy;delete window.languageOriginalBusy;});
 await page.locator('#settingsBg').getByRole('button',{name:'Close ✕',exact:true}).click();
 const after=await (await page.request.get('http://127.0.0.1:18760/api/executions')).json();
 check(JSON.stringify(before.projects)===JSON.stringify(after.projects),'project, Case and Config records unchanged');check(JSON.stringify(before.queue)===JSON.stringify(after.queue),'queue unchanged');
 check(errors.length===0,'no browser runtime errors: '+errors.join('; '));page.off('pageerror',onerror);return {count:checks.length,checks};
}
