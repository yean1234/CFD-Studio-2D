// Read-only smoke test of both existing result formats through the live app.
async page=>{
 page=await page.context().newPage();const checks=[],errors=[];page.on('pageerror',e=>errors.push(e.message));const check=(v,n)=>{if(!v)throw Error(n);checks.push(n);};
 try{
 await page.goto('http://127.0.0.1:8712');await page.waitForFunction(()=>window.CFDWorkspaceState?.().projects.length);
 const selections=await page.evaluate(()=>{const ps=CFDWorkspaceState().projects;return ['warehouse','legacy'].map(kind=>{for(const p of ps){const r=p.runs.find(r=>(kind==='warehouse'?r.id.startsWith('warehouse:'):r.id.startsWith('legacy:ext-')));if(r)return {project:p,run:{...r,kind}};}return null;}).filter(Boolean);});
 check(selections.length===2,'both warehouse and binary results available');
 for(const {project,run} of selections){
  await page.evaluate(()=>CFDI18n.setLanguage('ko'));
  await page.locator('#mCFD').click();
  await page.locator('.ew-project').filter({hasText:project.name}).first().click();
  await page.locator('.ew-run-card').filter({hasText:run.name}).first().click();
  await page.waitForFunction(id=>CFDWorkspaceState().selected?.id===id,run.id);
  await page.locator('#mViz').click();await page.locator('#ewCreateProject').click();
  await page.waitForFunction(()=>document.querySelectorAll('#dsFrame option').length>0,null,{timeout:30000});
  const limits=await page.locator('#dsLineCoordinates').evaluate(f=>Object.fromEntries([...f.querySelectorAll('input')].map(n=>[n.name,[Number(n.min),Number(n.max)]])));
  for(const suffix of ['0','1'])for(const axis of ['x','y','z']){const [lo,hi]=limits[axis+suffix];const v=lo+(hi-lo)*(axis==='x'?(suffix==='0'?.25:.75):.5);await page.locator('#dsLineCoordinates input[name='+axis+suffix+']').fill(String(v));}
  await page.locator('#dsLineCoordinates input[name=count]').fill('16');await page.locator('#dsLineCoordinates button').click();
  await page.waitForFunction(()=>document.getElementById('dsCoverage2').textContent.includes('16 / 16')||document.getElementById('dsError2').textContent,null,{timeout:60000});
  check(!(await page.locator('#dsError2').innerText()),run.kind+' profile succeeds');
  check(await page.locator('#dsPlot2 path[data-series]').count()===1,run.kind+' profile drawn');
  await page.locator('#dsPlot2').focus();await page.locator('#dsPlot2').press('End');
  check((await page.locator('#dsX2').innerText()).includes(' m'),run.kind+' distance cursor');
  await page.waitForFunction(()=>document.querySelectorAll('#dsPlot path[data-series]').length>0||document.getElementById('dsError').textContent,null,{timeout:60000});check(await page.locator('#dsPlot path[data-series]').count()===1,run.kind+' mean graph drawn');
  if(run.kind==='warehouse'){await page.setViewportSize({width:1600,height:1000});await page.locator('#dataSheet').evaluate(n=>n.scrollTop=0);await page.screenshot({path:'output/playwright/data-sheet-saved-warehouse.png'});}
 }
 check(!errors.length,'no live browser errors');return {checks};
 }finally{await page.close();}
}
