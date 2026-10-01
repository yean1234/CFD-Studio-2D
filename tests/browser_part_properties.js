// In-memory drafts; no user project changes or solver execution.
async page=>{
 const checks=[],errors=[],check=(ok,text)=>{if(!ok)throw Error(text);checks.push(text);};page.on('pageerror',e=>errors.push(e.message));
 await page.reload();await page.setViewportSize({width:1920,height:1000});await page.evaluate(()=>CFDI18n.setLanguage('ko'));
 const forms=(await (await page.request.get(new URL('/api/executions/forms',page.url()).href)).json()).forms;
 const config=forms.find(f=>f.config?.tank).config;
 await page.evaluate(config=>{window.partBefore=structuredClone(config);window.partsEditor=CFDFormConfig.open({config,valuesOnly:true,onSave:c=>window.savedParts=c});},config);
 const d=page.locator('.fc-dialog[open]');await d.locator('.sp-tag').first().waitFor();
 for(const label of ['수조 형상','코일 형상','보드 형상','하단 액체 물성','상단 액체 물성','층 구성·초기 온도'])check(await d.locator('.fc-nav').getByRole('button',{name:label,exact:true}).count()===0,'no duplicate fixed menu '+label);
 const selectPart=async path=>{await d.locator('.fc-element-list button').evaluateAll((buttons,path)=>buttons.find(b=>b.dataset.elementId===JSON.stringify(path)).click(),path);};
 await selectPart(['water']);check(await d.getByRole('textbox',{name:'영역 역할',exact:true}).count()===1,'role is free text');
 await d.getByRole('textbox',{name:'영역 역할',exact:true}).fill('custom / cooling liquid');
 const h=d.getByRole('spinbutton',{name:'영역 높이',exact:true});await h.fill('350');
 await d.getByRole('button',{name:'+ 속성',exact:true}).click();await d.getByLabel('속성 종류',{exact:true}).selectOption('custom');await d.getByLabel('속성 키',{exact:true}).fill('voltage');await d.getByLabel('단위',{exact:true}).last().fill('V');await d.getByLabel('속성 이름',{exact:true}).fill('테스트 전압');await d.getByRole('button',{name:'속성 추가',exact:true}).click();
 await d.getByLabel('테스트 전압',{exact:true}).fill('24');
 await selectPart(['coil']);await d.getByRole('button',{name:'형상 JSON',exact:true}).click();const coilGeometry=JSON.parse(await d.locator('.fc-json-pane textarea').inputValue());coilGeometry.min[0]=30;await d.locator('.fc-json-pane textarea').fill(JSON.stringify(coilGeometry));await d.getByRole('button',{name:'JSON 저장',exact:true}).click();await d.locator('.fc-json-pane').getByRole('button',{name:'취소',exact:true}).click();
 await selectPart(['water']);check(await d.getByRole('textbox',{name:'영역 역할',exact:true}).inputValue()==='custom / cooling liquid','custom role survives part switching');check(await d.getByLabel('테스트 전압',{exact:true}).inputValue()==='24','property value survives part switching');
 await page.waitForTimeout(300);check(await d.locator('.sp-tag').evaluateAll(tags=>tags.some(t=>t.dataset.elementId===JSON.stringify(['water']))),'water region is selectable in 3D');
 await d.getByRole('button',{name:'전체 공간 형상 JSON',exact:true}).click();const doc=JSON.parse(await d.locator('.fc-json-pane textarea').inputValue());check(doc.sections.geometry.water.properties.voltage.value===24,'full spatial JSON includes part properties');await d.locator('.fc-json-pane').getByRole('button',{name:'취소',exact:true}).click();
 await page.waitForTimeout(500);await d.locator('.fc-main').evaluate(e=>e.scrollTop=0);await d.screenshot({path:'output/playwright/part-inspector.png'});
 check(await d.locator('.fc-nav .btn').evaluateAll(buttons=>buttons.every(b=>getComputedStyle(b).whiteSpace==='nowrap')),'navigation labels do not wrap');
 await d.locator('.fc-editor-card > .fc-actions').getByRole('button',{name:'저장',exact:true}).click();
 check(await page.evaluate(()=>savedParts.water.role==='custom / cooling liquid'&&savedParts.water.properties.voltage.value===24&&savedParts.layers.dielectric_mm===savedParts.tank.liquid_height_mm-350&&savedParts.coil.x0===30),'saved Config retains linked geometry, roles and properties');
 check(await page.evaluate(()=>partBefore.water.role===undefined&&partBefore.water.properties===undefined&&partBefore.coil.x0!==30),'original Config untouched');
 await page.evaluate(()=>{partsEditor=CFDFormConfig.open({config:savedParts,valuesOnly:true,onSave:c=>window.savedParts=c});});await selectPart(['water']);check(await d.getByLabel('테스트 전압',{exact:true}).inputValue()==='24','property survives reopening without schema metadata');
 await d.getByRole('button',{name:'속성 삭제',exact:true}).click();check(await d.getByLabel('테스트 전압',{exact:true}).count()===0,'custom property removable');await d.locator('.fc-editor-card > .fc-actions').getByRole('button',{name:'취소',exact:true}).click();
 await page.evaluate(()=>{partsEditor=CFDFormConfig.open({config:{geometry:{shape:'sphere',unit:'m',center:[0,0,0],radius:1}},schemaOnly:true,onSave:c=>window.savedTemplateParts=c});});
 await d.getByRole('button',{name:'+ 요소',exact:true}).click();
 for(const axis of ['X','Y','Z'])await d.getByLabel('최대 좌표 '+axis,{exact:true}).fill('2');
 await d.getByRole('textbox',{name:'영역 역할',exact:true}).fill('custom material region');
 await d.getByLabel('물질 상태',{exact:true}).selectOption('solid');await d.getByRole('button',{name:'+ 속성',exact:true}).click();await d.getByLabel('속성 종류',{exact:true}).selectOption('density');await d.getByRole('button',{name:'속성 추가',exact:true}).click();
 check(await d.getByLabel('밀도',{exact:true}).getAttribute('readonly')!==null,'Template property values remain blank');
 await d.locator('.fc-editor-card > .fc-actions').getByRole('button',{name:'저장',exact:true}).click();
 check(await page.evaluate(()=>savedTemplateParts.geometry.shape==='sphere'&&savedTemplateParts.regions.length===1&&savedTemplateParts.regions[0].role==='custom material region'&&savedTemplateParts.regions[0].properties.density.name==='밀도'&&savedTemplateParts.regions[0].properties.density.type==='number'&&savedTemplateParts.regions[0].properties.density.value===null),'new generic part and property definition survive Template save');
 await page.evaluate(()=>{partsEditor=CFDFormConfig.open({config:savedTemplateParts,valuesOnly:true,onSave:c=>window.genericProjectParts=c});});await selectPart(['regions',0]);await d.getByLabel('밀도',{exact:true}).fill('950');
 await d.locator('.fc-editor-card > .fc-actions').getByRole('button',{name:'저장',exact:true}).click();check(await page.evaluate(()=>genericProjectParts.regions[0].properties.density.value===950&&savedTemplateParts.regions[0].properties.density.value===null),'project fills property value independently from Template');
 check(!errors.length,'no browser errors '+errors.join('; '));return {count:checks.length,checks};
}
