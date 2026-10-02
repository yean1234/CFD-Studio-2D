// Temporary Config drafts only; no project, preset, result or CFD process is changed.
async page=>{
 page=await page.context().newPage();const checks=[],errors=[],check=(v,n)=>{if(!v)throw Error(n);checks.push(n);};page.on('pageerror',e=>errors.push(e.message));
 try{
 await page.goto('http://127.0.0.1:8712');await page.waitForFunction(()=>window.CFDFormConfig);await page.evaluate(()=>CFDI18n.setLanguage('ko'));await page.setViewportSize({width:1800,height:1050});
 await page.evaluate(()=>{window.inputSource={control:{refinement:3,turbulence:'custom_model',output_fields:['custom_output']}};window.inputDefinition=CFDFormConfig.fromConfig(inputSource);inputDefinition.fields[0].label='Common controls';window.inputEditor=CFDFormConfig.open({config:inputSource,schema:inputDefinition,valuesOnly:true,onSave:v=>window.inputSaved=v});});
 const d=page.locator('.fc-dialog[open]'),json=d.locator('.fc-json-pane textarea'),closeJSON=()=>d.locator('.fc-json-pane').getByRole('button',{name:'취소',exact:true}).click();
 check(await d.locator('[data-config-path="control.refinement"]').evaluate(n=>n.tagName==='INPUT'&&n.inputMode==='decimal'),'arbitrary refinement uses numeric input without hardcoded choices');
 check(await d.locator('[data-config-path="control.turbulence"]').evaluate(n=>n.tagName==='INPUT'),'arbitrary turbulence is not forced into a solver menu');
 check(await d.locator('.fc-output-options').count()===0,'output_fields without a definition stays a normal list');
 check(await d.locator('.fc-caption button').count()===0,'basic fields have no definition edit buttons');
 await d.locator('[data-config-path="control.refinement"]').fill('7');
 await page.evaluate(()=>inputEditor.openJSON(null));
 const payload=await page.evaluate(()=>{const c={control:{refinement:6,enabled:true,outputs:['A']}},schema=CFDFormConfig.fromConfig(c);schema.fields[0].label='Defined controls';schema.fields[0].fields[0].enum=[3,6,9];schema.fields[0].fields[2].item_enum=['A','B'];return {config:c,config_schema:schema};});
 await json.fill(JSON.stringify(payload));await d.getByRole('button',{name:'JSON 저장',exact:true}).click();await closeJSON();
 check(await d.locator('.fc-nav>button[title=control]').innerText()==='Defined controls','JSON schema label updates navigation');
 check(await d.locator('[data-config-path="control.refinement"] option').allTextContents().then(x=>x.join(',')==='3,6,9'),'JSON schema options replace the input control');
 check(await d.locator('[data-config-path="control.enabled"]').evaluate(n=>n.tagName==='SELECT'),'added Boolean appears in the UI');
 check(await d.locator('[data-field-path="control.turbulence"]').count()===0,'removed JSON field disappears');
 check(await d.locator('.fc-output-options input[type=checkbox]').count()===2,'declared array choices render independently of field name');
 await page.evaluate(()=>inputEditor.openJSON(null));await json.fill('{invalid');await d.getByRole('button',{name:'JSON 저장',exact:true}).click();check(await d.locator('.fc-error').innerText().then(Boolean),'invalid JSON shows an error');await closeJSON();
 check(await d.locator('[data-config-path="control.refinement"] option').count()===3,'invalid JSON leaves previous controls intact');
 await d.locator('.fc-main>.fc-titlebar').getByRole('button',{name:'항목 추가',exact:true}).count().then(n=>check(n===0,'Case input does not expose top-level schema editor'));
 await page.evaluate(()=>inputEditor.close());
 // A new custom field owns its definition; default fields remain locked.
 await page.evaluate(()=>{inputEditor=CFDFormConfig.open({config:{control:{basic:1}},onSave:v=>window.inputSaved=v});});
 await d.locator('.fc-main>.fc-titlebar').getByRole('button',{name:'항목 추가',exact:true}).click();const add=d.locator('.fc-add');await add.getByLabel('표시 이름',{exact:true}).fill('User setting');await add.getByLabel('JSON 키',{exact:true}).fill('user_setting');await add.getByRole('button',{name:'추가',exact:true}).click();
 check(await d.locator('.fc-rename-label').filter({hasText:'User setting'}).count()===1,'new user field can rename its label');
 check(await d.locator('[data-field-path="control.basic"] .fc-caption button').count()===0,'basic field still has no edit button');
 await d.locator('[data-config-path="control.user_setting"]').fill('2.5');await d.locator('.fc-editor-card>.fc-actions').getByRole('button',{name:'저장',exact:true}).click();
 await page.evaluate(()=>{inputEditor=CFDFormConfig.open({config:inputSaved,valuesOnly:true});});check(await d.locator('.fc-rename-label').filter({hasText:'User setting'}).count()===1,'custom field ownership and label survive reopen');check(await d.locator('[data-config-path="control.user_setting"]').inputValue()==='2.5','custom value survives reopen');await page.evaluate(()=>inputEditor.close());
 check(await page.evaluate(()=>inputSource.control.refinement===3),'source Config is preserved');check(!errors.length,'no browser errors');return {checks};
 }finally{await page.close();}
}
