// Disposable local drafts; no project writes or solver runs.
async page=>{
 page=await page.context().newPage();const checks=[],errors=[],check=(v,n)=>{if(!v)throw Error(n);checks.push(n);};page.on('pageerror',e=>errors.push(e.message));
 try{
 await page.goto('http://127.0.0.1:8712');await page.waitForFunction(()=>window.CFDAgent&&window.CFDConfigContract);await page.evaluate(()=>CFDI18n.setLanguage('ko'));await page.setViewportSize({width:1800,height:1100});
 const config={analysis:{solver:'chtMultiRegionFoam'},geometry:{regions:[{name:'Sample region',shape:'box',unit:'m',min:[0,0,0],max:[1,1,1],material_state:''}]}};
 await page.evaluate(c=>{window.contractEditor=CFDFormConfig.open({config:c,valuesOnly:true,onSave:()=>{throw Error('No persistence in this test');}});},config);
 const d=page.locator('.fc-dialog[open]');await d.locator('[data-element-id]').first().click();await d.getByRole('button',{name:'+ 속성',exact:true}).click();
 check(await d.getByLabel('속성 종류',{exact:true}).locator('option').count()>1,'unspecified state still offers common properties');
 check(await d.getByLabel('속성 종류',{exact:true}).locator('optgroup').count()>=2,'properties have named categories');
 await d.getByLabel('물질 상태',{exact:true}).selectOption('gas');await d.getByLabel('속성 종류',{exact:true}).selectOption('initial_velocity');
 check(await d.getByLabel('입력할 내용',{exact:true}).isDisabled(),'catalog controls determine the shape of the input');
 await d.getByRole('button',{name:'속성 추가',exact:true}).click();
 check(await d.locator('[data-config-path$="initial_velocity.value.0"]').count()===1,'vector property has XYZ controls');
 await d.locator('[data-config-path$="initial_velocity.value.0"]').fill('1.25');
 await d.getByRole('button',{name:'+ 속성',exact:true}).click();await d.getByLabel('속성 종류',{exact:true}).selectOption('temperature_property_table');await d.getByRole('button',{name:'속성 추가',exact:true}).click();
 check(await d.getByRole('button',{name:'물성 행 추가',exact:true}).count()===1,'table property offers row input');
 await d.getByRole('button',{name:'물성 행 추가',exact:true}).click();
 check(await d.locator('[data-config-path$="temperature_property_table.value.T_K.0"]').count()===1,'temperature and property are structured cells');
 const doc=await page.evaluate(()=>CFDAgent.configDocument());check(doc.document.format==='cfd-studio-config','export keeps both values and schema');check(doc.document.config.geometry.regions[0].properties.initial_velocity.value[0]===1.25,'export preserves entered vector');
 check(await page.evaluate(()=>!Object.hasOwn(CFDAgent.status(),'controls')&&!Object.hasOwn(CFDAgent.status(),'json')),'compact polling avoids Config and control payloads');
 check(await page.evaluate(()=>CFDAgent.errorInfo('CFG-J004').action.ko.length>0),'one code lookup returns cause and remedy');
 await page.evaluate(()=>contractEditor.close());
 const schema={version:1,fields:[{key:'monitoring',type:'object',fields:[{key:'sensors',label:'Custom sensors',type:'array',value:[],items:{type:'object',fields:[{key:'name',label:'Sensor name',type:'string',value:''},{key:'location',label:'Sensor position',type:'array',widget:'vector3',unit:'m',value:[null,null,null]}]}}]}]};
 await page.evaluate(s=>{contractEditor=CFDFormConfig.open({config:{monitoring:{sensors:[]}},schema:s,valuesOnly:true,onSave:v=>window.contractSaved=v});},schema);
 await d.getByRole('button',{name:'목록 항목 추가',exact:true}).click();check(await d.getByLabel('Sensor name',{exact:true}).count()===1,'empty custom object list creates declared fields');check(await d.getByLabel('Sensor position X',{exact:true}).count()===1,'custom items support explicit XYZ widget');
 await d.getByLabel('Sensor name',{exact:true}).fill('sensor A');await d.getByLabel('Sensor position X',{exact:true}).fill('2.5');
 const export2=await page.evaluate(()=>CFDAgent.configDocument().document);check(export2.config.monitoring.sensors[0].location[0]===2.5,'custom row values roundtrip');check(export2.config_schema.fields[0].fields[0].items.fields[1].widget==='vector3','custom row schema is preserved');
 await d.getByRole('button',{name:'전체 JSON',exact:true}).click();const area=d.locator('.fc-json-pane textarea');await area.fill('{bad');await d.getByRole('button',{name:'JSON 저장',exact:true}).click();
 check(await d.locator('.fc-error').getAttribute('data-error-code')==='CFG-J001','syntax error is coded in the visible UI');
 check(await page.evaluate(()=>CFDAgent.status().errors[0].code==='CFG-J001'),'agent reads the same visible error');
 await area.fill(JSON.stringify({...export2,config:{monitoring:{sensors:[{name:123,location:[1,2,3]}]}}}));await d.getByRole('button',{name:'JSON 저장',exact:true}).click();check(await d.locator('.fc-error').getAttribute('data-error-code')==='CFG-J004','nested custom type errors are blocked with code');
 await area.fill(JSON.stringify(export2));await d.getByRole('button',{name:'JSON 저장',exact:true}).click();check(await d.locator('.fc-error').innerText()==='','correcting same draft clears error');
 await d.locator('.fc-json-pane').getByRole('button',{name:'취소',exact:true}).click();check(await d.getByLabel('Sensor position X',{exact:true}).inputValue()==='2.5','successful import rebuilds custom UI without losing values');
 await d.locator('.fc-editor-card>.fc-actions').getByRole('button',{name:'저장',exact:true}).click();
 await page.evaluate(()=>{contractEditor=CFDFormConfig.open({config:contractSaved,valuesOnly:true});});
 check(await d.getByLabel('Sensor position X',{exact:true}).inputValue()==='2.5','saved Config restores custom row widget without external schema');
 check(await d.getByLabel('Sensor name',{exact:true}).inputValue()==='sensor A','saved Config restores custom labels and values');
 await page.evaluate(()=>CFDI18n.setLanguage('ja'));await d.locator('.fc-editor-card').screenshot({path:'output/playwright/config-json-contract.png'});
 await page.evaluate(()=>{contractEditor.close();CFDI18n.setLanguage('ko');});check(!errors.length,'no browser exceptions');return {passed:checks.length,checks};
 }finally{await page.close();}
}
