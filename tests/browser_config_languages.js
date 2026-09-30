// UI-only drafts; reads Template fixtures but never saves projects or runs a solver.
async page=>{
 const checks=[],errors=[];const check=(ok,label)=>{if(!ok)throw Error(label);checks.push(label);};
 page.on('pageerror',e=>errors.push(e.message));await page.reload();await page.setViewportSize({width:1920,height:1000});
 const origin=new URL(page.url()).origin,forms=(await (await page.request.get(origin+'/api/executions/forms')).json()).forms;
 const untranslated=async d=>{await page.waitForTimeout(30);return d.evaluate(e=>{const values=new Set(),walker=document.createTreeWalker(e,NodeFilter.SHOW_TEXT);let node;while(node=walker.nextNode()){const parent=node.parentElement;if(parent.closest('[translate=no],textarea,pre,code,output')||!parent.checkVisibility())continue;if(/[가-힣]/.test(node.nodeValue))values.add(node.nodeValue.trim());}return [...values];});};
 for(const locale of ['ja','en'])for(const root of ['geometry_spec','tank']){
  const fixture=forms.find(f=>f.config?.[root]);if(!fixture)throw Error('Missing fixture '+root);
  await page.evaluate(({fixture,locale})=>{
   CFDI18n.setLanguage(locale);const config=structuredClone(fixture.config);config._studio={...config._studio,goals:'사용자 입력 · 번역하지 않음'};
   window.languageInspector=CFDSettings.open({config,form:fixture,managed:true,title:'Case Config',presets:[{id:'personal',name:'저장'}],onLoad:async()=>config,onRun:()=>{}});
   window.languageBefore=JSON.stringify(languageInspector.getConfig());
  },{fixture,locale});
  const d=page.locator('.fc-dialog');await d.locator('.fc-preview canvas').waitFor();
  let missing=await untranslated(d);check(!missing.length,locale+'/'+root+' termination: '+missing.join('; '));
  check(!/[가-힣]/.test(await d.locator('.fc-case-controls input').first().inputValue()),locale+' generated Case timestamp');
  check(await d.locator('.fc-preset-load option[value=personal]').textContent()==='저장',locale+' user preset name preserved');
  check(await d.locator('.fc-custom textarea').inputValue()==='사용자 입력 · 번역하지 않음',locale+' goal input preserved');
  check(!/[가-힣]/.test(await d.locator('.fc-custom textarea').getAttribute('aria-label')),locale+' textarea accessibility label translated');
  await d.locator('.fc-custom select').selectOption('frames');missing=await untranslated(d);check(!missing.length,locale+'/'+root+' frame guidance: '+missing.join('; '));
  const fields=await d.locator('.fc-nav>button[title]').evaluateAll(xs=>xs.map(x=>x.title));
  for(const field of fields){await d.locator('.fc-nav>button').evaluateAll((xs,key)=>xs.find(x=>x.title===key).click(),field);missing=await untranslated(d);if(missing.length)throw Error(locale+'/'+root+'/'+field+': '+missing.join('; '));}
  check(true,locale+'/'+root+' all Config sections translated');
  await d.locator('.fc-preview-header button').click();missing=await untranslated(d);check(!missing.length,locale+'/'+root+' spatial JSON controls: '+missing.join('; '));
  const area=d.locator('.fc-json-pane textarea'),before=await area.inputValue();
  await page.evaluate(()=>CFDI18n.setLanguage('ko'));await page.waitForTimeout(30);check(await area.inputValue()===before,locale+' spatial JSON unchanged by language switch');
  await page.evaluate(l=>CFDI18n.setLanguage(l),locale);await page.waitForTimeout(30);
  await d.locator('.fc-json-pane .fc-actions button').first().click();
  await d.locator('.fc-tools button').filter({hasText:locale==='ja'?'JSON全体':'Full JSON'}).click();
  const full=JSON.parse(await area.inputValue());check(full._studio.goals==='사용자 입력 · 번역하지 않음',locale+' full JSON preserves user text');
  // After changing termination mode, language switching alone must leave the whole draft intact.
  const snapshot=await page.evaluate(()=>JSON.stringify(languageInspector.getConfig()));
  for(const language of ['ko','en','ja']){await page.evaluate(l=>CFDI18n.setLanguage(l),language);await page.waitForTimeout(30);check(await page.evaluate(()=>JSON.stringify(languageInspector.getConfig()))===snapshot,locale+'/'+root+' Config preserved when switching to '+language);}
  if(locale==='ja'&&root==='geometry_spec'){await d.locator('.fc-json-pane .fc-actions button').first().click();await d.locator('.fc-nav>button').first().click();await d.screenshot({path:'output/playwright/config-ja-fixed.png'});}
  await d.locator('.fc-editor-card > .fc-actions button').first().click();
 }
 // Late-rendered status, labels and JSON keys stay independent.
 await page.evaluate(()=>{window.languageInspector=CFDFormConfig.open({config:{geometry:{regions:[{shape:'box',unit:'m',min:[0,0,0],max:[1,2,3]}]},materials:{phase_1:{density:1},phase_2:{density:2}},outputs:{fields:['U','alpha.phase_1']}},title:'Config',onSave:()=>{}});CFDI18n.setLanguage('ja');});
 const d=page.locator('.fc-dialog');await d.locator('.fc-nav>button[title=materials]').click();check(!(await untranslated(d)).length,'numbered phase labels translated');
 await d.locator('.fc-preview-header button').click();const area=d.locator('.fc-json-pane textarea'),doc=JSON.parse(await area.inputValue());doc.sections.geometry.geometry.regions[0].max[0]='invalid';await area.fill(JSON.stringify(doc));await d.locator('.fc-json-pane .fc-actions button').last().click();await page.waitForTimeout(30);
 const error=await d.locator('.fc-error').innerText();check(error.includes('geometry.regions.0.max.0')&&!/[가-힣]/.test(error),'dynamic validation error translated with original JSON path');
 await d.locator('.fc-json-pane .fc-actions button').first().click();await d.locator('.fc-editor-card > .fc-actions button').first().click();
 await page.reload();check(await page.locator('html').getAttribute('lang')==='ja','Japanese preference restored after reload');
 check(errors.length===0,'no browser runtime errors: '+errors.join('; '));return {count:checks.length,checks};
}
