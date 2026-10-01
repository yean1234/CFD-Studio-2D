// In-memory drafts only; no stored projects or templates are modified.
async page=>{
 page=await page.context().newPage();const checks=[],errors=[],check=(v,n)=>{if(!v)throw Error(n);checks.push(n);};page.on('pageerror',e=>errors.push(e.message));
 try{
 await page.goto('http://127.0.0.1:8712');await page.waitForFunction(()=>window.CFDFormConfig);await page.setViewportSize({width:1920,height:1080});await page.evaluate(()=>CFDI18n.setLanguage('ko'));
 const fixture={loading:{blocks:[{id:'Box A',min_m:[0,0,0],max_m:[2,2,2]}],porosity:.4,tortuosity:2},run:{dt_s:.1,write_interval_s:1},geometry:{regions:[{name:'Custom object',shape:'box',unit:'m',min:[3,0,0],max:[4,1,1],material_state:'solid',density:900,properties:{extra:{name:'Custom input',type:'number',unit:'K',value:4}}}]}};
 await page.evaluate(c=>{window.scopeOriginal=structuredClone(c);window.scopeEditor=CFDFormConfig.open({config:c,valuesOnly:true,onSave:c=>window.scopeSaved=c});},fixture);
 const d=page.locator('.fc-dialog[open]'),json=d.locator('.fc-json-pane textarea'),closeJSON=()=>d.locator('.fc-json-pane').getByRole('button',{name:'취소',exact:true}).click();
 check(await d.locator('.fc-nav>button[title=loading]').count()===0,'no separate hardcoded loading tab');
 await d.locator('[data-scene-group=loading]').click();
 check(await d.locator('[data-field-path="loading.blocks"]').count()===0,'shared attributes do not duplicate block list');
 check(await d.locator('[data-field-path="loading.porosity"] input').inputValue()==='0.4','shared material values preserved');
 check(await d.locator('.fc-field .fc-json-action').count()===0,'individual shared inputs have no JSON buttons');
 await d.locator('.fc-main>.fc-titlebar .fc-json-action').click();let value=JSON.parse(await json.inputValue());check(!value.blocks&&value.porosity===.4,'shared JSON excludes geometry');value.porosity=.45;await json.fill(JSON.stringify(value));await d.getByRole('button',{name:'JSON 저장',exact:true}).click();await closeJSON();
 await d.locator('.fc-element-list [data-element-id]').filter({hasText:'Box A'}).click();
 check(await d.locator('.fc-field .fc-json-action').count()===0,'position and geometry coordinates have no per-field JSON');
 const transform=d.locator('fieldset.fc-section').filter({has:page.locator('legend').filter({hasText:'변환'})}).first();
 await transform.locator('legend .fc-json-action').click();value=JSON.parse(await json.inputValue());check(Object.keys(value).sort().join(',')==='position,scale,unit','transform JSON contains only transform');value.position[0]=4;await json.fill(JSON.stringify(value));await d.getByRole('button',{name:'JSON 저장',exact:true}).click();await closeJSON();
 check(await page.evaluate(()=>scopeEditor.getConfig().loading.blocks[0].min_m[0]===3),'transform updates canonical saved block coordinates');
 await d.getByRole('button',{name:'형상 JSON',exact:true}).click();value=JSON.parse(await json.inputValue());check(value.shape==='box'&&value.min[0]===3,'primitive JSON follows transformed shape');await closeJSON();
 await d.getByRole('button',{name:'요소 JSON',exact:true}).click();value=JSON.parse(await json.inputValue());check(value.id==='Box A'&&value.min_m[0]===3,'whole element JSON preserved');await closeJSON();
 await d.locator('.fc-element-list [data-element-id]').filter({hasText:'Custom object'}).click();
 check(await d.locator('.fc-part-properties .fc-section .fc-json-action').count()===0,'custom property cards have no repeated JSON buttons');
 await d.locator('.fc-editor-card').screenshot({path:'output/playwright/config-section-scopes.png'});
 const physical=d.locator('fieldset.fc-section').filter({has:page.locator('legend').filter({hasText:'물리 속성'})}).first();await physical.locator('legend .fc-json-action').click();value=JSON.parse(await json.inputValue());check(value.density===900&&!value.shape&&!value.properties,'physical JSON excludes geometry and custom properties');value.density=950;await json.fill(JSON.stringify(value));await d.getByRole('button',{name:'JSON 저장',exact:true}).click();await closeJSON();
 await d.locator('.fc-part-properties>.fc-property-head .fc-json-action').click();value=JSON.parse(await json.inputValue());check(value.extra.value===4&&!value.min,'property group JSON contains custom properties only');await closeJSON();
 await d.locator('.fc-nav>button[title=run]').click();check(await d.locator('.fc-main .fc-json-action').count()===1,'common section has one JSON action');
 await d.locator('.fc-editor-card>.fc-actions').getByRole('button',{name:'저장',exact:true}).click();
 check(await page.evaluate(()=>scopeSaved.loading.porosity===.45&&scopeSaved.geometry.regions[0].density===950&&scopeSaved.loading.blocks[0].min_m[0]===3),'saved draft contains independent group edits');check(await page.evaluate(()=>JSON.stringify(scopeOriginal)===JSON.stringify(window.scopeOriginal)&&scopeOriginal.loading.porosity===.4&&scopeOriginal.geometry.regions[0].density===900),'source fixture unchanged');
 await page.evaluate(()=>{scopeEditor=CFDFormConfig.open({config:scopeSaved,valuesOnly:true,onSave:c=>window.scopeSaved=c});});await d.locator('.fc-element-list [data-element-id]').filter({hasText:'Box A'}).click();await d.getByRole('button',{name:'+ 요소',exact:true}).click();check(await page.evaluate(()=>scopeEditor.getConfig().loading.blocks.length===2&&scopeEditor.getConfig().geometry.regions.length===1),'new element stays in selected collection');
 await page.evaluate(()=>scopeEditor.close());await page.evaluate(()=>{scopeEditor=CFDFormConfig.open({config:scopeSaved,readonly:true});});await d.locator('.fc-element-list [data-element-id]').filter({hasText:'Box A'}).click();await d.getByRole('button',{name:'형상 JSON',exact:true}).click();check(!await json.isEditable(),'saved Config JSON remains read only');await page.evaluate(()=>scopeEditor.close());
 check(!errors.length,'no browser exceptions: '+errors.join(';'));return {checks};
 }catch(e){await page.screenshot({path:'output/playwright/config-scope-failure.png'});throw Error(e.message+'; passed: '+checks.join(', '));}finally{await page.close();}
}
