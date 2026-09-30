// Run only against tests/serve_execution_review.py with --allow-write and no --allow-run
async (page) => {
 if(new URL(page.url()).port!=='18761')throw Error('Use isolated review server port 18761');
 await page.setViewportSize({width:1600,height:1000});
 const setup=await page.evaluate(async()=>{
  const get=async p=>(await fetch('/api/executions'+p)).json();
  const post=async(p,b)=>{const r=await fetch('/api/executions'+p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});const j=await r.json();if(!r.ok||j.ok===false)throw Error(JSON.stringify(j));return j;};
  const forms=await get('/forms'),f=forms.forms.find(f=>f.id==='immersion');
  const p=await post('/project',{name:'Inspector '+Date.now(),form_id:f.id,default_preset:'form:'+f.id,initial_config:f.config});
  return {id:p.result.id,config:f.config,form:f};
 });
 await page.reload();await page.waitForSelector('#ewProjects .ew-project');
 await page.getByRole('button',{name:/Inspector /}).last().click();
 await page.locator('#ewNewRun').click();
 const d=page.locator('.fc-dialog');await d.waitFor();
 await d.locator('.fc-preview canvas').waitFor();
 if(await d.getByRole('checkbox',{name:'프리셋에 저장',exact:true}).isChecked())throw Error('Preset defaults to checked');
 await d.getByRole('textbox',{name:'실행 이름',exact:true}).fill('Case inspector');
 await d.getByLabel('목표 물리시간 (s)',{exact:true}).fill('20');
 await d.locator('.fc-element-list').getByRole('button',{name:'tank',exact:true}).click();
 await d.locator('.fc-main .fc-titlebar').getByRole('button',{name:'JSON',exact:true}).click();
 const area=d.getByRole('textbox',{name:'선택 항목 JSON',exact:true});let obj=JSON.parse(await area.inputValue());obj.width_mm+=10;await area.fill(JSON.stringify(obj));
 await d.getByRole('button',{name:'JSON 저장',exact:true}).click();
 if(await d.locator('.fc-error').innerText())throw Error(await d.locator('.fc-error').innerText());
 const layout=await d.evaluate(e=>{const box=s=>{const r=e.querySelector(s).getBoundingClientRect();return {x:r.x,width:r.width,right:r.right};};return {left:box('.fc-body'),middle:box('.fc-preview'),right:box('.fc-json-pane')};});
 if(!(layout.left.right<=layout.middle.x&&layout.middle.right<=layout.right.x))throw Error(JSON.stringify(layout));
 await page.waitForTimeout(400);await d.screenshot({path:'output/case-inspector-three-panels.png'});
 await area.fill('{broken');await d.getByRole('button',{name:'JSON 저장',exact:true}).click();if(!(await d.locator('.fc-error').innerText()))throw Error('Invalid JSON accepted');
 await d.locator('.fc-json-pane').getByRole('button',{name:'취소',exact:true}).click();
 await d.getByRole('button',{name:'실행 저장',exact:true}).click();
 await d.waitFor({state:'detached'});
 const data=await page.evaluate(async()=>(await (await fetch('/api/executions')).json()));
 const project=data.projects.find(p=>p.id===setup.id);if(project.runs.length!==1)throw Error(JSON.stringify(project));
 await page.locator('#ewRows .ew-run-card').click();await page.locator('#ewSettings').click();await d.waitFor();await d.locator('.fc-preview canvas').waitFor();
 await d.getByRole('button',{name:'전체 JSON',exact:true}).click();const saved=JSON.parse(await d.getByRole('textbox',{name:'선택 항목 JSON',exact:true}).inputValue());
 if(saved.tank.width_mm!==setup.config.tank.width_mm+10||saved._studio.termination.time_s!==20)throw Error('Saved values mismatch');
 await d.locator('.fc-actions').last().getByRole('button',{name:'취소',exact:true}).click();
 await page.evaluate(x=>{window.snapshotInput=structuredClone(x.config);CFDSettings.open({config:x.config,readonly:true,managed:true,form:x.form,name:'Stored Case',onClone:c=>window.clonedInput=c});},setup);
 await d.waitFor();await d.locator('.fc-element-list').getByRole('button',{name:'tank',exact:true}).click();
 const editable=await d.locator('.fc-main input:not([readonly]):not([disabled]), .fc-main textarea:not([readonly]):not([disabled])').count();if(editable)throw Error('Snapshot editable');
 await d.getByRole('button',{name:'이 Config로 새 Case',exact:true}).click();
 const exact=await page.evaluate(()=>JSON.stringify(snapshotInput)===JSON.stringify(clonedInput));if(!exact)throw Error('Snapshot mutated by inspection');
 return {saved:true,threeColumns:true,jsonValidation:true,snapshotImmutable:true,layout};
}
