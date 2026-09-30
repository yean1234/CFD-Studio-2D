// Isolated review server; editor drafts only, no solver or project writes.
async page=>{
 const checks=[],errors=[];const check=(v,label)=>{if(!v)throw Error(label);checks.push(label);};
 const onerror=e=>errors.push(e.message);page.on('pageerror',onerror);
 await page.goto('http://127.0.0.1:18760');await page.setViewportSize({width:1500,height:1000});await page.evaluate(()=>CFDI18n.setLanguage('ko'));
 await page.evaluate(()=>{
  window.spaceOriginal={geometry:{regions:[{shape:'box',unit:'m',min:[0,0,0],max:[4,2,3]},{shape:'sphere',unit:'m',center:[1,1,1],radius:.4},{shape:'cylinder',unit:'m',center:[3,1,1],radius:.3,height:1,axis:'z'}]},numerics:{dt:.02}};window.spaceSaved=[];
  CFDFormConfig.open({config:spaceOriginal,onSave:v=>spaceSaved.push(v)});
 });
 const form=page.locator('.fc-dialog');
 check(await form.locator('.fc-tools').getByRole('button',{name:'+ Field',exact:true}).count()===1,'field and file actions are in the right toolbar');
 await form.screenshot({path:'output/playwright/spatial-toolbar.png'});
 await form.getByRole('button',{name:'공간 JSON',exact:true}).click();
 let dialog=page.locator('.sp-dialog'),area=dialog.getByRole('textbox',{name:'공간 JSON',exact:true});
 check(await dialog.locator('.sp-code').boundingBox().then(async a=>{const b=await dialog.locator('.sp-preview').boundingBox();return Math.abs(a.height-b.height)<1&&b.x>a.x;}),'code and preview have equal height');
 await dialog.getByRole('button',{name:'형상 확인',exact:true}).click();await dialog.locator('canvas').waitFor();await dialog.getByRole('status').filter({hasText:'3 shapes'}).waitFor();
 await dialog.screenshot({path:'output/playwright/spatial-preview.png'});
 check(await page.evaluate(()=>spaceSaved.length)===0,'preview does not apply or save');
 const initial=await area.inputValue();await area.fill('{broken');check(await dialog.locator('canvas').count()===0,'editing clears stale preview');
 await dialog.getByRole('button',{name:'형상 확인',exact:true}).click();check(await dialog.getByRole('alert').innerText().then(t=>t.length>0),'malformed JSON gets feedback');
 await dialog.getByRole('button',{name:'적용',exact:true}).click();check(await dialog.isVisible(),'invalid JSON cannot apply');
 const invalid=JSON.parse(initial);invalid.geometry.regions[0].max=[-1,2,3];await area.fill(JSON.stringify(invalid));await dialog.getByRole('button',{name:'적용',exact:true}).click();check(await dialog.isVisible()&&await dialog.getByRole('alert').innerText().then(t=>t.includes('최대 좌표')),'invalid dimensions cannot apply');
 await dialog.getByRole('button',{name:'취소',exact:true}).click();await dialog.waitFor({state:'detached'});
 await form.getByRole('button',{name:'공간 JSON',exact:true}).click();dialog=page.locator('.sp-dialog');area=dialog.getByRole('textbox',{name:'공간 JSON',exact:true});check(await area.inputValue()===initial,'Cancel preserves the parent draft');
 const changed=JSON.parse(initial);changed.geometry.regions[0].max=[6,2,3];await area.fill(JSON.stringify(changed));await dialog.getByRole('button',{name:'적용',exact:true}).click();await dialog.waitFor({state:'detached'});
 await form.getByRole('button',{name:'Apply',exact:true}).click();await form.waitFor({state:'detached'});
 check(await page.evaluate(()=>spaceSaved[0].geometry.regions[0].max[0]===6&&spaceSaved[0].numerics.dt===.02&&spaceOriginal.geometry.regions[0].max[0]===4),'Apply updates only draft geometry and preserves the source');
 await page.evaluate(()=>{const schema=CFDFormConfig.fromConfig({geometry:{regions:{domain:{shape:'box',unit:'m',min:[0,0,0],max:[2,3,4]}}},numerics:{dt:1}});window.schemaSaved=[];CFDFormConfig.open({schema,schemaOnly:true,onSave:(v,s)=>schemaSaved.push({v,s})});});
 await page.locator('.fc-dialog').getByRole('button',{name:'공간 JSON',exact:true}).click();dialog=page.locator('.sp-dialog');
 await dialog.getByRole('button',{name:'형상 확인',exact:true}).click();await dialog.locator('canvas').waitFor();
 await dialog.getByRole('button',{name:'적용',exact:true}).click();await dialog.waitFor({state:'detached'});
 await page.locator('.fc-dialog').getByRole('button',{name:'Apply',exact:true}).click();await page.locator('.fc-dialog').waitFor({state:'detached'});
 check(await page.evaluate(()=>schemaSaved[0].v.numerics.dt===null&&schemaSaved[0].v.geometry.regions.domain.max.length===0),'Template preview dimensions do not become defaults');
 await page.evaluate(()=>CFDSettings.open({config:spaceOriginal,readonly:true,name:'Snapshot'}));
 await page.locator('#settingsDialog').getByRole('button',{name:'공간 JSON',exact:true}).click();dialog=page.locator('.sp-dialog');
 check(await dialog.locator('textarea').getAttribute('readonly')!==null&&await dialog.getByRole('button',{name:'적용',exact:true}).count()===0,'snapshot geometry stays read-only');
 await dialog.getByRole('button',{name:'닫기',exact:true}).click();await dialog.waitFor({state:'detached'});await page.locator('#settingsDialog header').getByRole('button',{name:'닫기',exact:true}).click();
 for(const fixture of [{tank:{width_mm:456,depth_mm:70,liquid_height_mm:800},board:{x0:80,x1:380,y0:0,y1:300,z0:15,z1:23}},{geometry_spec:{geometry:{length_m:78,width_m:25,eaves_m:7.2,roof_rise_m:3.5}},loading:{blocks:[{min_m:[2,1,.15],max_m:[13.5,11.5,3]}]}}]){
  await page.evaluate(c=>CFDSpatial.open({config:c,readonly:true}),fixture);dialog=page.locator('.sp-dialog');await dialog.getByRole('button',{name:'형상 확인',exact:true}).click();await dialog.getByRole('status').filter({hasText:'2 shapes'}).waitFor();check(await dialog.locator('canvas').count()===1,'existing geometry renders');await dialog.getByRole('button',{name:'닫기',exact:true}).click();await dialog.waitFor({state:'detached'});
 }
 check(errors.length===0,'no browser errors: '+errors.join('; '));page.off('pageerror',onerror);return {checks};
}
