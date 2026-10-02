// Local drafts only: custom display names, fixed base definitions and read-only snapshots.
async page=>{
 page=await page.context().newPage();const checks=[],errors=[],check=(v,n)=>{if(!v)throw Error(n);checks.push(n);};page.on('pageerror',e=>errors.push(e.message));
 try{
 await page.goto('http://127.0.0.1:8712');await page.waitForFunction(()=>window.CFDFormConfig);await page.evaluate(()=>CFDI18n.setLanguage('ko'));await page.setViewportSize({width:1800,height:1100});
 const config={analysis:{solver:'chtMultiRegionFoam'},geometry:{regions:[{name:'Tank',shape:'box',unit:'m',min:[0,0,0],max:[1,1,1],material_state:'solid',properties:{density:{name:'밀도',catalog_key:'density',type:'number',unit:'kg/m³',value:7800},gas:{name:'기체층',type:'number',unit:'mm',value:200}}}]}};
 await page.evaluate(c=>{window.propertyOriginal=structuredClone(c);window.propertyEditor=CFDFormConfig.open({config:c,valuesOnly:true,onSave:v=>window.propertySaved=v});},config);
 const d=page.locator('.fc-dialog[open]');await d.locator('[data-element-id]').first().click();
 check(await d.getByRole('button',{name:/수정/}).count()===0,'no edit buttons in Config');
 check(await d.locator('.fc-part-properties legend').filter({hasText:'밀도'}).locator('.fc-rename-label').count()===0,'base property name is fixed');
 await d.getByLabel('밀도',{exact:true}).fill('7900');check(await d.getByLabel('밀도',{exact:true}).inputValue()==='7900','base calculation value remains directly editable');
 const name=()=>d.locator('.fc-rename-label').filter({hasText:'기체층'});
 await name().dblclick();let input=d.locator('.fc-inline-name');await input.fill('취소할 이름');await input.press('Escape');check(await name().count()===1,'Escape cancels name change');
 await name().dblclick();input=d.locator('.fc-inline-name');await input.fill('');await input.press('Enter');check(await input.count()===1&&await input.evaluate(n=>!n.checkValidity()),'blank name does not replace existing definition');
 await input.fill('상부 공간');await input.press('Enter');check(await d.getByLabel('상부 공간',{exact:true}).inputValue()==='200','double-click changes display name only');
 await d.getByLabel('상부 공간',{exact:true}).fill('210');
 await d.locator('.fc-rename-label').filter({hasText:'상부 공간'}).dblclick();await d.locator('.fc-inline-name').fill('추가 공간');
 await d.locator('.fc-editor-card>.fc-actions').getByRole('button',{name:'저장',exact:true}).click();
 const saved=await page.evaluate(()=>propertySaved);check(saved.geometry.regions[0].properties.gas.name==='추가 공간','blur commits name before Save');
 check(saved.geometry.regions[0].properties.gas.value===210&&saved.geometry.regions[0].properties.gas.type==='number'&&saved.geometry.regions[0].properties.gas.unit==='mm','key, type and unit are unchanged by rename');check(saved.geometry.regions[0].properties.density.value===7900,'base value saves normally');
 check(await page.evaluate(()=>propertyOriginal.geometry.regions[0].properties.gas.name==='기체층'&&propertyOriginal.geometry.regions[0].properties.density.value===7800),'original Config unchanged');
 await page.evaluate(c=>{propertyEditor=CFDFormConfig.open({config:c,valuesOnly:true});},saved);await d.locator('[data-element-id]').first().click();check(await d.locator('.fc-rename-label').filter({hasText:'추가 공간'}).count()===1,'custom name is editable after reopen');await page.evaluate(()=>propertyEditor.close());
 await page.evaluate(c=>{propertyEditor=CFDFormConfig.open({config:c,readonly:true});},saved);await d.locator('[data-element-id]').first().click();check(await d.locator('.fc-rename-label').count()===0,'snapshot has no rename interactions');check(!await d.getByLabel('추가 공간',{exact:true}).isEditable(),'snapshot values readonly');await page.evaluate(()=>propertyEditor.close());
 const forms=(await (await page.request.get('http://127.0.0.1:8712/api/executions/forms')).json()).forms,legacy=forms.find(f=>f.config?.tank);
 await page.evaluate(f=>{propertyEditor=CFDFormConfig.open({config:f.config,form:f,valuesOnly:true});},legacy);await d.locator('[data-element-id]').evaluateAll(xs=>xs.find(e=>e.dataset.elementId===JSON.stringify(['tank'])).click());
 check(await d.locator('[data-field-path="layers.air_mm"] .fc-rename-label, [data-field-path="layers.air_mm"] button').count()===0,'legacy base input has no rename or edit');check(await d.locator('[data-config-path="layers.air_mm"]').isEditable(),'legacy base value remains editable');
 await d.locator('.fc-editor-card').screenshot({path:'output/playwright/config-fixed-fields.png'});await page.evaluate(()=>propertyEditor.close());
 check(!errors.length,'no browser errors');return {checks};
 }finally{await page.close();}
}
