// Synthetic editor drafts only. No project saves or solver execution.
async page=>{
 const checks=[],errors=[];const check=(ok,text)=>{if(!ok)throw Error(text);checks.push(text);};
 page.on('pageerror',e=>errors.push(e.message));await page.reload();await page.evaluate(()=>CFDI18n.setLanguage('ko'));
 for(const width of [1920,1600,1280]){
  await page.setViewportSize({width,height:1000});
  await page.evaluate(()=>{
   const c={geometry:{regions:[{name:'Domain',shape:'box',unit:'m',min:[0,0,0],max:[4,3,2]},{name:'Component',shape:'box',unit:'m',min:[1,1,0],max:[2,2,1]}]},mesh:{cell_size:.1},materials:{density:1},boundary_conditions:{wall:{mesh_patch:'walls'}},outputs:{fields:['U'],probes:[[1,1,1]]}};
   for(let i=0;i<35;i++)c['group_'+i]={value:i};
   window.spatialDraft=CFDFormConfig.open({config:c,title:'프로젝트 Config',onSave:value=>window.savedSpatial=value});
  });
  const d=page.locator('.fc-dialog');await d.locator('.fc-preview canvas').waitFor();
  const measure=()=>d.evaluate(e=>{const r=s=>{const a=e.querySelector(s).getBoundingClientRect();return {x:a.x,right:a.right,width:a.width,height:a.height};};return {editor:r('.fc-editor-card'),preview:r('.fc-preview'),json:r('.fc-json-pane'),siblings:e.querySelector('.fc-preview').parentElement===e&&e.querySelector('.fc-json-pane').parentElement===e};});
  const before=await measure();check(before.siblings&&before.preview.x-before.editor.right>=17,'independent Config and 3D cards '+width);
  check(before.preview.width>=459&&Math.abs(before.editor.height-before.preview.height)<1,'large equal-height 3D card '+width);
  const nav=d.locator('.fc-nav');await nav.evaluate(e=>e.scrollTop=800);
  const clickVisible=index=>nav.evaluate((e,index)=>{const r=e.getBoundingClientRect();const b=[...e.querySelectorAll('button')].filter(b=>{const q=b.getBoundingClientRect();return q.top>r.top+50&&q.bottom<r.bottom-20;})[index];const before=e.scrollTop;b.click();return {before,after:document.querySelector('.fc-nav').scrollTop};},index);
  for(let i=0;i<3;i++){const result=await clickVisible(i);check(result.before>100&&result.before===result.after,'navigation scroll preserved '+width+'/'+i);}
  const top=await nav.evaluate(e=>e.scrollTop);await d.locator('.sp-tag').filter({hasText:'Domain'}).click();check(await nav.evaluate(e=>e.scrollTop)===top,'3D selection preserves navigation scroll '+width);
  await d.getByRole('button',{name:'전체 공간 형상 JSON',exact:true}).click();await page.waitForTimeout(500);
  const after=await measure();check(after.json.x-after.preview.right>=17&&Math.abs(after.editor.width-before.editor.width)<1&&Math.abs(after.preview.width-before.preview.width)<1,'three separate stable-width cards '+width);
  const area=d.locator('.fc-json-pane textarea'),doc=JSON.parse(await area.inputValue());check(doc.format==='cfd-spatial-config'&&doc.sections.geometry.geometry.regions.length===2&&doc.sections.mesh.mesh.cell_size===.1&&doc.sections.observations.outputs.probes.length===1&&doc.sections.boundaries.boundary_conditions.wall.mesh_patch==='walls','complete grouped spatial JSON '+width);
  doc.sections.geometry.geometry.regions[0].max[0]=5;await area.fill(JSON.stringify(doc,null,2));await d.getByRole('button',{name:'JSON 저장',exact:true}).click();check(!(await d.locator('.fc-error').innerText()),'spatial JSON saves without error '+width);
  check(await page.evaluate(()=>spatialDraft.getConfig().geometry.regions[0].max[0]===5&&spatialDraft.getConfig().materials.density===1&&spatialDraft.getConfig().outputs.fields[0]==='U'),'JSON updates geometry and preserves unrelated values '+width);
  if(width===1920){await page.evaluate(()=>{const c=spatialDraft.getConfig();for(const k of Object.keys(c))if(k.startsWith('group_'))delete c[k];spatialDraft.setConfig(c);});await d.locator('.sp-tag').filter({hasText:'Domain'}).click();await area.evaluate(e=>e.scrollTop=0);await d.screenshot({path:'output/playwright/spatial-panels.png'});await d.screenshot({path:'docs/assets/config-inspector/panels.png'});}
  await d.locator('.fc-json-pane').getByRole('button',{name:'취소',exact:true}).click();await d.locator('.fc-editor-card > .fc-actions').getByRole('button',{name:'취소',exact:true}).click();
 }
 await page.setViewportSize({width:1920,height:1000});
 const forms=(await (await page.request.get(new URL('/api/executions/forms',page.url()).href)).json()).forms;
 for(const root of ['geometry_spec','tank']){
  const fixture=forms.find(f=>f.config?.[root]);check(!!fixture,'fixture '+root);
  await page.evaluate(c=>CFDFormConfig.open({config:c,readonly:true,title:'Case Config'}),fixture.config);
  const d=page.locator('.fc-dialog');await d.getByRole('button',{name:'전체 공간 형상 JSON',exact:true}).click();const doc=JSON.parse(await d.locator('.fc-json-pane textarea').inputValue());check(doc.sections.geometry[root]&&Object.keys(doc.sections.geometry).length>1,'legacy full spatial definitions '+root);
  check(await d.locator('.fc-json-pane textarea').getAttribute('readonly')!==null&&await d.getByRole('button',{name:'JSON 저장',exact:true}).count()===0,'read-only snapshots '+root);
  await d.locator('.fc-editor-card > .fc-actions').getByRole('button',{name:'닫기',exact:true}).click();
 }
 await page.evaluate(()=>{
  const c={geometry:{regions:[{shape:'box',unit:'m',min:[0,0,0],max:[3,2,1]}]},materials:{density:1000}};
  CFDFormConfig.open({config:c,schema:CFDFormConfig.fromConfig(c),schemaOnly:true,onSave:value=>window.templateSaved=value});
 });
 const d=page.locator('.fc-dialog');await d.getByRole('button',{name:'전체 공간 형상 JSON',exact:true}).click();const area=d.locator('.fc-json-pane textarea'),doc=JSON.parse(await area.inputValue());doc.sections.geometry.geometry.regions[0].max[0]=6;await area.fill(JSON.stringify(doc));await d.getByRole('button',{name:'JSON 저장',exact:true}).click();await d.locator('.fc-json-pane').getByRole('button',{name:'취소',exact:true}).click();await d.locator('.fc-editor-card > .fc-actions').getByRole('button',{name:'저장',exact:true}).click();
 check(await page.evaluate(()=>templateSaved.geometry.regions[0].max[0]===6&&templateSaved.materials.density===null),'Template spatial JSON edits initial geometry while operating values stay blank');
 check(errors.length===0,'no browser runtime errors '+errors.join('; '));return {count:checks.length,checks};
}
