async page=>{
 page=await page.context().newPage();await page.goto('http://127.0.0.1:8712');await page.waitForFunction(()=>window.CFDSettings);await page.evaluate(()=>CFDI18n.setLanguage('ko'));
 const checks=[],check=(v,label)=>{if(!v)throw Error(label);checks.push(label);};
 const forms=(await (await page.request.get('http://127.0.0.1:8712/api/executions/forms')).json()).forms;
 for(const model of ['immersion','warehouse']){
  const f=forms.find(f=>f.model===model);if(!f?.config)throw Error('Missing '+model+' fixture');
  await page.evaluate(f=>{window.source=structuredClone(f.config);window.caseEditor=CFDSettings.open({config:f.config,form:f,managed:true,name:'UI check',onRun:async(name,c)=>window.caseSaved=c});},f);
  const d=page.locator('.fc-dialog[open]'),root=model==='immersion'?'run':'numerics',end=model==='immersion'?'end_time_s':'end_s';
  await d.locator('.fc-nav>button[title="'+root+'"]').click();
  check(await d.locator('[data-config-path="'+root+'.'+end+'"]').count()===0,model+' has no duplicate end input');
  check(await d.locator('[data-config-path="'+root+'.write_interval_s"]').count()===1,model+' keeps storage interval');
  check(await d.locator('[data-config-path="'+root+'.'+(model==='immersion'?'max_dt_s':'dt_s')+'"]').count()===1,model+' keeps solver time step');
  await d.getByText('전체 항목',{exact:true}).click();await d.locator('.fc-nav>button[title="'+root+'"]').click();
  check(await d.locator('[data-config-path="'+root+'.'+end+'"]').count()===0,model+' show all does not reveal duplicate');
  await d.locator('.fc-nav>input').fill('종료');check(await d.getByLabel('목표 물리시간 (s)',{exact:true}).count()===1,model+' search points to termination section');
  check(await d.locator('[data-config-path="'+root+'.'+end+'"]').count()===0,model+' search excludes duplicate');
  await d.locator('.fc-nav>input').fill('');await d.locator('.fc-nav>button').filter({hasText:'종료 조건·목표'}).click();
  const target=f.config[root][end]+f.config[root].write_interval_s;await d.getByLabel('목표 물리시간 (s)',{exact:true}).fill(String(target));
  await d.locator('.fc-editor-card>.fc-actions').getByRole('button',{name:'Config 저장',exact:true}).click();
  const stored=await page.evaluate(()=>caseSaved);check(stored[root][end]===target&&stored._studio.termination.time_s===target,model+' saves target to solver input');
  check(stored[root].write_interval_s===f.config[root].write_interval_s,model+' output interval unchanged');
 }
 const f=forms.find(f=>f.model==='immersion');
 await page.evaluate(f=>{caseEditor=CFDSettings.open({config:f.config,form:f,managed:true,name:'Frames',onRun:async(name,c)=>window.frameSaved=c});},f);
 const d=page.locator('.fc-dialog[open]');await d.getByLabel('종료 방식',{exact:true}).selectOption('frames');await d.getByLabel('목표 저장 프레임 수',{exact:true}).fill('121');await d.getByLabel('0초 초기 프레임 포함',{exact:true}).check();
 await d.locator('.fc-editor-card>.fc-actions').getByRole('button',{name:'Config 저장',exact:true}).click();
 check(await page.evaluate(()=>frameSaved.run.end_time_s===120*(frameSaved.run.viz_interval_s??frameSaved.run.write_interval_s)),'frame target derives end from visualization interval');
 await page.evaluate(()=>{caseEditor=CFDSettings.open({config:frameSaved,managed:false,name:'Existing termination',onSave:async(name,c)=>window.updatedSaved=c});});
 await d.getByLabel('목표 저장 프레임 수',{exact:true}).fill('122');await d.locator('.fc-editor-card>.fc-actions').getByRole('button',{name:'Config 저장',exact:true}).click();
 check(await page.evaluate(()=>updatedSaved.run.end_time_s===121*updatedSaved.run.viz_interval_s),'existing termination remains authoritative without managed flag');
 await page.evaluate(()=>{caseEditor=CFDSettings.open({config:updatedSaved,managed:true,readonly:true});});await d.locator('.fc-nav>button[title="run"]').click();check(await d.locator('[data-config-path="run.end_time_s"]').count()===0,'snapshot avoids duplicate controls');await page.evaluate(()=>caseEditor.close());
 await page.evaluate(f=>{caseEditor=CFDFormConfig.open({config:f.config,valuesOnly:true,onSave:()=>{}});},f);await d.locator('.fc-nav>button[title="run"]').click();check(await d.locator('[data-config-path="run.end_time_s"]').count()===1,'standalone template inputs remain available');await page.evaluate(()=>caseEditor.close());
 await page.close();return {passed:checks.length,checks};
}
