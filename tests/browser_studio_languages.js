// Reads live data but replaces comparison payloads in this browser only; no save or run requests.
async page=>{
 const checks=[],errors=[];const check=(ok,label)=>{if(!ok)throw Error(label);checks.push(label);};
 const onerror=e=>errors.push(e.message);page.on('pageerror',onerror);let comparison='missing';
 await page.route('**/api/executions/detail?*',async route=>{
  const response=await route.fetch(),data=await response.json();
  // /detail responds with the Case directly. Keep identifiers, files and solver data intact.
  data.differences=comparison==='missing'?null:comparison==='equal'?[]:[{path:'user.note',before:'저장',after:'온도'}];data.preset_id=comparison==='changed'?'translation-check':null;
  await route.fulfill({response,json:data});
 });
 try{
 const scan=async(label,root='body')=>{await page.waitForTimeout(200);const missing=await page.locator(root).evaluate(e=>{const out=new Set(),walker=document.createTreeWalker(e,NodeFilter.SHOW_TEXT);let n;while(n=walker.nextNode()){const p=n.parentElement;if(!p.checkVisibility()||p.closest('script,style,textarea,pre:not([data-i18n-text]),code,output,[translate=no],.ew-project strong,.ew-run-top strong,.ew-case-name,.ew-form-row strong,#ewTitle,#ewDescription,#ewGoals,#ewFacts,#dsName,#appContext'))continue;if(/[가-힣]/.test(n.nodeValue))out.add(n.nodeValue.trim());}return [...out];});check(!missing.length,label+': '+missing.join('; '));};
 await page.setViewportSize({width:1920,height:1000});await page.reload();await page.evaluate(()=>CFDI18n.setLanguage('ja'));await page.waitForSelector('#ewRows .ew-run-card');
 await page.waitForFunction(()=>document.getElementById('ewDifferences').textContent.includes('比較基準が保存'));
 check((await page.locator('#envPath').innerText()).includes('コアを自動検出'),'core auto-detection translated');
 await scan('CFD Japanese');
 for(const mode of ['equal','changed']){
  comparison=mode;await page.locator('#ewRows .ew-run-card').first().click();
  await page.waitForFunction(changed=>document.getElementById('ewDifferences').textContent.includes(changed?'Case作成時のプリセット':'基準設定との差分なし'),mode==='changed');
  check(true,mode+' baseline description translated');
 }
 const raw=page.locator('#ewDifferences [translate=no]');check(await raw.innerText()==='\n\nuser.note: "저장" → "온도"','comparison keys and user values preserved');
 for(const locale of ['en','ja','ko','ja']){await page.evaluate(l=>CFDI18n.setLanguage(l),locale);await page.waitForTimeout(50);check(await raw.innerText()==='\n\nuser.note: "저장" → "온도"','raw comparison preserved '+locale);}
 for(const locale of ['ja','en']){
  await page.evaluate(l=>CFDI18n.setLanguage(l),locale);
  await page.getByRole('button',{name:locale==='ja'?'環境設定':'Settings',exact:true}).click();await scan('resource settings '+locale,'#settingsBg');await page.locator('#settingsBg').getByRole('button',{name:locale==='ja'?'閉じる ✕':'Close ✕',exact:true}).click();
  await page.locator('#ewCreateProject').click();await scan('project creation '+locale,'dialog.ew-dialog');await page.locator('dialog.ew-dialog').getByRole('button',{name:locale==='ja'?'キャンセル':'Cancel',exact:true}).click();
  await page.getByRole('button',{name:'Viewer',exact:true}).click();await page.waitForTimeout(700);await scan('3D Viewer '+locale);
  await page.getByRole('button',{name:'Data Sheet',exact:true}).click();await scan('Data Sheet '+locale);
  await page.getByRole('button',{name:'CFD',exact:true}).click();
 }
 // Mixed labels keep a user name verbatim while translating the program-generated suffix.
 await page.evaluate(()=>{const host=document.createElement('div');host.id='localeFixture';const select=document.createElement('select'),option=new Option('저장 · 실행 연결 필요','unchanged');option.setAttribute('translate','no');option.dataset.i18nName='저장';option.dataset.i18nSuffix='실행 연결 필요';select.append(option);const input=document.createElement('input');input.id='localeInvalid';input.value='9';input.min='0';input.max='2';host.append(select,input);document.body.append(host);CFDInput.bind(input,{type:'number'});CFDInput.check(input);CFDI18n.setLanguage('ja');});
 await page.waitForTimeout(80);check(await page.locator('#localeFixture option').innerText()==='저장 · 実行アダプターが必要','user Template name preserved with translated status');
 check(await page.locator('#localeInvalid').evaluate(e=>e.validationMessage.includes('0～2')),'native validation message translated');
 await page.evaluate(()=>CFDI18n.setLanguage('en'));await page.waitForTimeout(80);check(await page.locator('#localeInvalid').evaluate(e=>e.validationMessage==='Enter a value between 0 and 2'),'invalid input message follows language switch');
 check(await page.locator('#localeInvalid').inputValue()==='9'&&await page.locator('#localeFixture select').inputValue()==='unchanged','validation and localization do not change input data');
 await page.evaluate(()=>document.getElementById('localeFixture').remove());
 // Empty Viewer guidance is UI, even though populated headings contain user names.
 await page.evaluate(()=>{DataSheetViewer.setSelection({id:'language-empty',name:'사용자 프로젝트'},[]);DataSheetViewer.setMode('data');CFDI18n.setLanguage('ja');});
 await page.waitForTimeout(80);check(await page.locator('#dsSelection').innerText()==='左側でCaseを選択してください','empty Viewer guidance translated');check(await page.locator('#dsName').innerText()==='사용자 프로젝트','Viewer project name preserved');
 check(errors.length===0,'no browser runtime errors: '+errors.join('; '));return {count:checks.length,checks};
 }finally{await page.unrouteAll({behavior:'ignoreErrors'});page.off('pageerror',onerror);await page.evaluate(()=>document.getElementById('localeFixture')?.remove());}
}
