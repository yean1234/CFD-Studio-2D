// Exercise only in-memory drafts on a disposable Studio tab.
async page=>{
 const checks=[],errors=[],check=(v,m)=>{if(!v)throw Error(m);checks.push(m);};page.on('pageerror',e=>errors.push(e.message));
 const config={geometry:{regions:[{name:'Outer',shape:'box',unit:'m',min:[0,0,0],max:[1,1,1]},{name:'Inner',shape:'box',unit:'m',min:[.2,.2,.2],max:[.8,.8,.8]}]},mesh:{cell_size:{value:.1,unit:'m'}}};
 await page.evaluate(c=>{CFDI18n.setLanguage('ko');window.meshEditor?.close();window.meshEditor=CFDFormConfig.open({config:c,valuesOnly:true,onSave:v=>window.meshSaved=v});},config);
 const d=page.locator('.fc-dialog[open]'),part=async name=>d.locator('.fc-element-list').getByRole('button',{name,exact:true}).click(),save=()=>d.locator('.fc-editor-card>.fc-actions').getByRole('button',{name:'저장',exact:true}).click();
 await part('Outer');await d.getByLabel('독립 격자 크기 사용',{exact:true}).check();await d.locator('[data-config-path="geometry.regions.0.mesh_control.cell_size.value"]').fill('.05');
 await part('Inner');await d.getByLabel('독립 격자 크기 사용',{exact:true}).check();await d.locator('[data-config-path="geometry.regions.1.mesh_control.cell_size.value"]').fill('.025');
 await d.getByRole('button',{name:'+ 폴더',exact:true}).click();await d.getByLabel('폴더 이름',{exact:true}).fill('Assembly');await d.locator('.fc-folder-add').getByRole('button',{name:'추가',exact:true}).click();
 await d.getByLabel('폴더',{exact:true}).selectOption({label:'Assembly'});await part('Outer');await d.getByLabel('폴더',{exact:true}).selectOption({label:'Assembly'});
 check(await d.locator('.fc-folder .fc-element-button').count()===2,'two geometries grouped without changing their paths');
 await d.getByRole('button',{name:'+ 국소격자 정의',exact:true}).click();check(await d.getByLabel('물질 상태',{exact:true}).inputValue()==='mesh_refinement','mesh-only type selected');
 check(await d.getByText('물성 및 초기 조건',{exact:true}).count()===0,'mesh-only Inspector has no material properties');
 for(const [key,values] of Object.entries({min:[.3,.3,.3],max:[.5,.5,.5]}))for(let i=0;i<3;i++)await d.locator('[data-config-path="mesh_regions.0.'+key+'.'+i+'"]').fill(String(values[i]));
 await d.locator('[data-config-path="mesh_regions.0.mesh_control.cell_size.value"]').fill('.01');await d.getByLabel('이름',{exact:true}).fill('Observation');await d.getByLabel('폴더',{exact:true}).selectOption({label:'Assembly'});
 check(await page.evaluate(()=>meshEditor.getConfig().mesh_regions[0].mesh_control.cell_size.value===.01),'mesh-only size stored independently');
 await d.locator('.fc-folder summary').click();await page.waitForTimeout(100);await save();
 check(await page.evaluate(()=>meshSaved._studio.geometry_groups[0].expanded===false),'folder collapse saved');
 await page.evaluate(()=>{meshEditor=CFDFormConfig.open({config:meshSaved,valuesOnly:true,onSave:v=>window.meshSaved=v});});check(await d.locator('.fc-folder').getAttribute('open')===null,'folder collapse restored');
 await d.locator('.fc-folder summary').click();await d.locator('.fc-folder-name').dblclick();await d.getByLabel('속성 이름',{exact:true}).fill('Assembly renamed');await d.getByLabel('속성 이름',{exact:true}).press('Enter');
 check(await d.locator('.fc-folder-name').textContent()==='Assembly renamed','folder rename retained');
 await part('Observation');await d.locator('.sp-tag').first().waitFor();await d.locator('.fc-editor-card').screenshot({path:'output/playwright/mesh-only-folder.png'});
 for(const language of ['en','ja']){await page.evaluate(l=>CFDI18n.setLanguage(l),language);await page.waitForTimeout(150);const ko=await d.locator('.fc-main').evaluate(e=>{let n;const out=[],w=document.createTreeWalker(e,NodeFilter.SHOW_TEXT);while(n=w.nextNode())if(n.parentElement.checkVisibility()&&!n.parentElement.closest('[translate=no],pre,textarea')&&/[가-힣]/.test(n.nodeValue))out.push(n.nodeValue);return out;});check(!ko.length,language+' translated '+ko.join(';'));}
 await page.evaluate(()=>CFDI18n.setLanguage('ko'));await d.getByRole('button',{name:'폴더 삭제',exact:true}).click();
 check(await d.locator('.fc-element-button').count()===3,'deleting folder preserves every geometry');await save();
 check(await page.evaluate(()=>meshSaved.geometry.regions.length===2&&meshSaved.mesh_regions.length===1&&meshSaved._studio.geometry_groups.length===0),'physical and mesh-only records remain separate after save');
 await page.evaluate(()=>{const c=structuredClone(meshSaved);c.geometry.regions[1].mesh_control.cell_size.value=.07;meshEditor=CFDFormConfig.open({config:c,valuesOnly:true,onSave:v=>window.unexpectedMeshSave=v});});await save();
 check(await d.locator('.fc-error').getAttribute('data-error-code')==='MESH-R007','unsupported inner coarsening displays a specific error code');check(await page.evaluate(()=>!window.unexpectedMeshSave),'conflict never reaches save');
 await page.evaluate(()=>{meshEditor.close();meshEditor=CFDFormConfig.open({config:meshSaved,schemaOnly:true,onSave:v=>window.meshTemplateSaved=v});});await save();
 check(await page.evaluate(()=>meshTemplateSaved.mesh_regions[0].mesh_control.cell_size.value===.01&&meshTemplateSaved.mesh.cell_size.value===null),'Template preserves spatial refinement and blanks operating values');
 check(!errors.length,'no browser script errors');return {count:checks.length,checks};
}
