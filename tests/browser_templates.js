// Review server only, no CFD execution. Input fixture: output/template-review/ico-inputs.json
async page=>{
 const checks=[],errors=[];const check=(v,m)=>{if(!v)throw Error(m);checks.push(m);};const onerror=e=>errors.push(e.message);page.on('pageerror',onerror);
 const api=async(path,body)=>{const r=body?await page.request.post('http://127.0.0.1:18760/api/executions'+path,{data:body}):await page.request.get('http://127.0.0.1:18760/api/executions'+path);const d=await r.json();if(d.ok===false)throw Error(d.msg);return d;};
 const suffix=Date.now(),templateName='UI Template '+suffix,projectName='UI Project '+suffix;
 try{
 await page.goto('http://127.0.0.1:18760');await page.setViewportSize({width:1440,height:1100});await page.evaluate(()=>CFDI18n.setLanguage('ko'));await page.locator('#ewCreateForm').click();
 const wizard=page.locator('.fw-recommend-dialog');await wizard.waitFor();
 for(const values of [{medium:'liquid',purpose:'flow'},{regime:'laminar',time_mode:'transient'},{domain:'internal',mesh:'import',termination:'physical_time'}]){for(const [k,v] of Object.entries(values))await wizard.locator(`input[name=${k}][value=${v}]`).check();await wizard.getByRole('button',{name:values.domain?'솔버 추천':'다음',exact:true}).click();}
 await wizard.locator('input[name=recommended_solver][value=icoFoam]').check();await wizard.getByRole('button',{name:'양식 생성',exact:true}).click();await wizard.waitFor({state:'detached'});
 let dialog=page.locator('dialog.ew-form-dialog');await dialog.locator('[name=name]').fill(templateName);
 check(await dialog.locator('[name=model]').count()===0,'Config Template selector removed');
 check(await dialog.locator('[name=description]').evaluate(n=>n.closest('label').previousElementSibling.querySelector('[name=name]')!==null),'description immediately follows Template name');
 check(await dialog.locator('[data-authors] a').count()>0,'selected solver has author/source text links');
 await dialog.locator('[data-config]').click();const editor=page.locator('.fc-dialog');
 check(await editor.locator('input[aria-label$=" Value"]').count()===0,'Template definition editor has no value inputs');
 await editor.getByRole('button',{name:'구조 편집',exact:true}).click();check(await editor.locator('select[aria-label$=" 입력 형식"]').count()>0,'Template definition retains advanced data type controls');
 await page.screenshot({path:'output/playwright/template-definition.png'});await editor.getByRole('button',{name:'적용',exact:true}).click();
 await page.screenshot({path:'output/playwright/template-dialog.png'});
 await dialog.getByRole('button',{name:'Template 저장',exact:true}).click();await dialog.waitFor({state:'detached'});
 const saved=(await api('/forms')).forms.find(f=>f.name===templateName);check(!!saved,'Template saves and appears in list');check(saved.blank_config.initial_conditions.fields.p.value===null,'Template physical inputs remain blank');const before=JSON.stringify(saved);
 await page.locator('#ewCreateProject').click();dialog=page.locator('dialog.ew-dialog');await dialog.locator('[name=name]').fill(projectName);await dialog.locator('[name=form_id]').selectOption(saved.id);
 check(!(await dialog.locator('[name=form_id] option:checked').isDisabled()),'custom Template can be selected for project');check(await dialog.locator('[name=preset]').inputValue()==='','new project starts with direct input');check(!(await dialog.getByRole('checkbox').isChecked()),'save as preset defaults off');
 await dialog.getByRole('button',{name:'Config 입력',exact:true}).click();
 await page.locator('.fc-nav').getByRole('button',{name:'초기 조건',exact:true}).click();check(await page.locator('input[data-config-path="initial_conditions.fields.p.value"]').inputValue()==='','project input starts blank');
 await page.locator('.fc-dialog').getByRole('button',{name:'JSON 가져오기',exact:true}).click({trial:true});
 await page.locator('.fc-dialog input[type=file]').setInputFiles('output/template-review/ico-inputs.json');
 await page.locator('.fc-dialog').getByRole('button',{name:'적용',exact:true}).click();await page.locator('.fc-dialog').waitFor({state:'detached'});
 await dialog.getByRole('checkbox').check();await dialog.getByRole('textbox',{name:'새 프리셋 이름',exact:true}).fill('Inputs '+suffix);
 await page.screenshot({path:'output/playwright/template-project.png'});await dialog.getByRole('button',{name:'저장',exact:true}).click();await dialog.waitFor({state:'detached'});
 let snapshot=await api('');const project=snapshot.projects.find(p=>p.name===projectName);check(!!project?.initial_config,'project stores its own input snapshot');
 const preset=(await api('/presets')).presets.find(p=>p.name==='Inputs '+suffix);check(preset.form_id===saved.id,'new input preset is scoped to Template');check(JSON.stringify((await api('/forms')).forms.find(f=>f.id===saved.id))===before,'project values do not change Template');
 await page.reload();await page.waitForSelector('#ewCreateProject');check((await api('')).projects.some(p=>p.id===project.id&&p.initial_config),'project Config survives page reload');
 // Connected project remains usable, no calculation started
 await page.locator('#ewCreateProject').click();dialog=page.locator('dialog.ew-dialog');await dialog.locator('[name=name]').fill('Connected '+suffix);await dialog.locator('[name=form_id]').selectOption('immersion');
 check(await dialog.locator('[name=preset] option[value="'+preset.id+'"]').count()===0,'another Template does not show custom input preset');
 await dialog.locator('[name=preset]').selectOption('form:immersion');await dialog.getByRole('button',{name:'저장',exact:true}).click();await dialog.waitFor({state:'detached'});
 snapshot=await api('');const connected=snapshot.projects.find(p=>p.name==='Connected '+suffix);const caseResult=await api('/case',{project_id:connected.id,name:'UI Case',config:connected.initial_config});
 await page.reload();await page.waitForSelector('#ewCreateProject');await page.locator('#ewProjects button').filter({hasText:'Connected '+suffix}).click();await page.locator('#ewRows button').filter({hasText:'UI Case'}).click();
 check(await page.locator('#ewDifferenceBox').evaluate(n=>n.tagName==='SECTION')&&await page.locator('#ewDifferences').isVisible(),'Config differences are always visible');
 check(await page.locator('#ewLogBox').evaluate(n=>n.tagName==='SECTION')&&await page.locator('#ewLog').isVisible(),'solver log is always visible');
 check(await page.locator('#ewDifferenceBox summary,#ewLogBox summary').count()===0,'difference and log have no collapse control');
 await page.screenshot({path:'output/playwright/template-case.png'});
 check(errors.length===0,'no browser errors: '+errors.join('; '));return {checks,project:project.id,preset:preset.id};
 }finally{page.off('pageerror',onerror);}
}
