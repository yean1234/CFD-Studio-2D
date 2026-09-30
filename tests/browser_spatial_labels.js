// In-memory drafts only: no project saves or solver runs.
async page=>{
 const checks=[],errors=[],check=(ok,text)=>{if(!ok)throw Error(text);checks.push(text);};
 const onerror=e=>errors.push(e.message);page.on('pageerror',onerror);
 await page.reload();await page.evaluate(()=>CFDI18n.setLanguage('ko'));
 const forms=(await (await page.request.get(new URL('/api/executions/forms',page.url()).href)).json()).forms;
 const generic={geometry:{regions:[{name:'Outer domain',shape:'box',unit:'m',min:[0,0,0],max:[4,3,2]},...Array.from({length:6},(_,i)=>({name:'Component '+(i+1),shape:'box',unit:'m',min:[.4+i%3, .3+Math.floor(i/3),.2],max:[.9+i%3,.8+Math.floor(i/3),1.5]}))]}};
 try{
 for(const [name,config]of [['generic',generic],...['tank','geometry_spec'].map(root=>[root,forms.find(f=>f.config?.[root]).config])]){
  await page.setViewportSize({width:1920,height:1000});await page.evaluate(config=>{window.labelsBefore=JSON.stringify(config);window.labelDraft=CFDFormConfig.open({config,readonly:true,title:'Case Config'});},config);
  const d=page.locator('.fc-dialog');await d.locator('.sp-tag').first().waitFor();
  const measure=()=>d.locator('.fc-preview-host').evaluate(host=>{const r=host.getBoundingClientRect();const boxes=[...host.querySelectorAll('.sp-tag:not([hidden])')].map(e=>{const b=e.getBoundingClientRect();return {x:b.left-r.left,y:b.top-r.top,right:b.right-r.left,bottom:b.bottom-r.top};});return {w:r.width,h:r.height,boxes,paths:[...host.querySelectorAll('.sp-leaders polyline')].map(e=>e.getAttribute('points')),count:host.querySelectorAll('.sp-tag').length};});
  let m=await measure();check(m.count===m.paths.length&&m.paths.every(p=>p&&p.split(' ').length===3),name+' has a leader for each tag');
  check(m.boxes.every(b=>b.x>=0&&b.right<=m.w+1&&b.y>=0&&b.bottom<=m.h+1),name+' tags stay in preview');
  check(m.boxes.every(b=>b.x<15||m.w-b.right<15),name+' tags are in outer lanes');
  const tag=d.locator('.sp-tag').first(),id=await tag.getAttribute('data-element-id');await tag.click();check(await tag.getAttribute('aria-pressed')==='true'&&await d.locator('.sp-leaders .selected').count()===1,name+' tag selects its element and leader');
  const canvas=d.locator('.fc-preview canvas'),box=await canvas.boundingBox(),before=(await measure()).paths;
  await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();await page.mouse.move(box.x+box.width/2+65,box.y+box.height/2+30,{steps:8});await page.mouse.up();
  check(JSON.stringify((await measure()).paths)!==JSON.stringify(before),name+' leaders follow rotation');
  const rotated=(await measure()).paths;await page.mouse.wheel(0,-80);await page.waitForTimeout(100);check(JSON.stringify((await measure()).paths)!==JSON.stringify(rotated),name+' leaders follow zoom');
  await d.locator('.fc-preview').screenshot({path:'output/playwright/spatial-labels-'+name+'.png'});
  await page.setViewportSize({width:1280,height:850});await page.waitForTimeout(150);m=await measure();check(m.boxes.every(b=>b.x>=0&&b.right<=m.w+1&&b.y>=0&&b.bottom<=m.h+1),name+' resize keeps tags visible');
  check(await page.evaluate(()=>JSON.stringify(labelDraft.getConfig())===labelsBefore),name+' display changes preserve Config');
  await d.locator('.fc-editor-card > .fc-actions').getByRole('button',{name:'닫기',exact:true}).click();
 }
 check(!errors.length,'no browser runtime errors '+errors.join('; '));return {count:checks.length,checks};
 }finally{page.off('pageerror',onerror);}
}
