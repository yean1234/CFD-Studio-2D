// Run with playwright-cli run-code --filename tests/browser_data_sheet_panels.js
// Synthetic saved fields; does not create or run any CFD Case.
async page => {
 page=await page.context().newPage();const checks=[],errors=[],check=(v,label)=>{if(!v)throw Error(label);checks.push(label);};
 page.on('pageerror',e=>errors.push(e.message));
 const metrics=[{id:'temperature',name:'온도',unit:'°C'},{id:'speed',name:'유속',unit:'m/s'},{id:'pressure',name:'압력',unit:'Pa'}];
 await page.route('**/chart-panel-test',r=>r.fulfill({contentType:'text/html',body:`<!doctype html><html><head><style>:root{--page:#10100f;--surface:#1b1b19;--surface2:#252523;--line:#383835;--ink:#e5e5df;--muted:#a4a49b;--s1:#3987e5;--s3:#ef776d}body{margin:0;font-family:Arial;background:var(--page);color:var(--ink)}#viz{position:absolute;inset:0}.btn{background:var(--surface2);color:var(--ink);border:1px solid var(--line);border-radius:6px}</style></head><body class="grouped execution-viewer"><div id="viz"></div><script>function setPlay(){};window.downloads=[];function exportDownload(blob,name){downloads.push({blob,name});}</script><script src="/input_validation.js"></script><script src="/data_sheet_viewer.js"></script><script src="/i18n.js"></script></body></html>`}));
 await page.route('**/api/executions/chart-catalog?*',r=>r.fulfill({json:{axis:'time',metrics:metrics.map(m=>({...m,id:m.id+'.mean',scope:'global'})),point_metrics:metrics.map(m=>({...m,bounds_m:[[0,2],[0,2],[0,2]]}))}}));
 const values=f=>f==='temperature'?[10,20,30]:f==='speed'?[.1,.2,.3]:[100,200,300];
 await page.route('**/api/executions/chart?*',r=>r.fulfill({json:{points:values(new URL(r.request().url()).searchParams.get('metric').split('.')[0]).map((v,i)=>[i,v]),next:3,total:3,errors:[]}}));
 await page.route('**/api/executions/point-chart?*',r=>{const q=new URL(r.request().url()).searchParams;return r.fulfill({json:{points:values(q.get('field')).map((v,i)=>[i,v*Number(q.get('x'))]),next:3,total:3,errors:[]}});});
 await page.route('**/api/executions/profile-frames?*',r=>r.fulfill({json:{times:[0,1,2],axis:'time'}}));
 await page.route('**/api/executions/line-profile?*',r=>{const q=new URL(r.request().url()).searchParams,n=Number(q.get('count')),frame=Number(q.get('frame'));return r.fulfill({json:{points:Array.from({length:n},(_,i)=>[i/(n-1),10+i+frame]),samples:Array.from({length:n},(_,i)=>({distance_m:i/(n-1),requested_xyz_m:[i/(n-1),.5,.5],cell_index:i,cell_centre_m:[i/(n-1),.5,.5],cell_centre_distance_m:0})),saved_x:frame,frame_axis:'time',sampling:'nearest_saved_cell',next:n,total:n,errors:[]}});});
 try{
  await page.setViewportSize({width:1400,height:950});await page.goto('http://127.0.0.1:8712/chart-panel-test');
  await page.evaluate(()=>{CFDI18n.setLanguage('ko');DataSheetViewer.setSelection({id:'fixture',name:'그래프 검사'},[{id:'case',name:'검사 데이터'}]);DataSheetViewer.setMode('data');});
  await page.waitForFunction(()=>document.getElementById('dsCoverage').textContent.includes('3 / 3'));
  check(await page.locator('#dsCoordinates').isHidden(),'mean mode hides coordinate inputs');
  check(await page.locator('#dsFrame option').count()===3,'profile offers saved frames');
  await page.locator('#dsFieldB').selectOption('speed.mean|m/s|time');await page.locator('#dsFieldC').selectOption('pressure.mean|Pa|time');
  await page.waitForFunction(()=>document.querySelectorAll('#dsPlot path[data-series]').length===3);
  check(await page.locator('#dsPlot [data-y-axis]').count()===3,'three units have separate axes');
  for(const [kind,selector] of [['bar','rect'],['scatter','circle'],['line','path']]){await page.locator('#dsGraphType').selectOption(kind);check(await page.locator('#dsPlot '+selector+'[data-chart-type='+kind+']').count()===(kind==='line'?3:9),kind+' draws all series');}
  await page.locator('#dsScope').selectOption('point');check(await page.locator('#dsCoordinates').isVisible(),'point mode moves coordinates into left card');
  for(const k of ['x','y','z'])await page.locator('#dsCoordinates input[name='+k+']').fill('1');
  await page.locator('#dsCoordinates button').click();await page.waitForFunction(()=>document.getElementById('dsCoverage').textContent.includes('3 / 3'));
  await page.locator('#dsFieldB').selectOption('speed|m/s|time');await page.locator('#dsFieldC').selectOption('pressure|Pa|time');
  await page.waitForFunction(()=>document.querySelectorAll('#dsPlot path[data-series]').length===3);
  check(await page.locator('#dsPlot path[data-series]').count()===3,'point mode supports three quantities');
  for(const [name,value] of Object.entries({x0:0,y0:.5,z0:.5,x1:1,y1:.5,z1:.5,count:4}))await page.locator('#dsLineCoordinates input[name='+name+']').fill(String(value));
  await page.locator('#dsLineCoordinates button').click();await page.waitForFunction(()=>document.querySelectorAll('#dsPlot2 path[data-series]').length===1);
  check((await page.locator('#dsPlot2').textContent()).includes('거리 (m)'),'profile horizontal axis is distance');
  await page.locator('#dsPlot2').focus();await page.locator('#dsPlot2').press('End');check((await page.locator('#dsValues2').innerText()).includes('13 °C'),'profile cursor reports exact sampled value');
  await page.locator('#dsFrame').selectOption('2');await page.waitForFunction(()=>document.getElementById('dsCoverage2').textContent.includes('4 / 4'));
  await page.locator('#dsPlot2').focus();await page.locator('#dsPlot2').press('End');check((await page.locator('#dsValues2').innerText()).includes('15 °C'),'saved frame change updates profile');
  await page.locator('#dsExport2').click();await page.getByRole('button',{name:'CSV 데이터',exact:true}).click();await page.locator('dialog').waitFor({state:'detached'});
  const csv=await page.evaluate(()=>downloads.at(-1).blob.text());check(csv.includes('cell_x_m')&&csv.includes('nearest_saved_cell')&&csv.includes('"1","15","2"'),'profile CSV preserves coordinates and frame');
  await page.locator('#dsExport2').click();await page.getByRole('button',{name:'PNG 이미지',exact:true}).click();await page.locator('dialog').waitFor({state:'detached'});check(await page.evaluate(()=>downloads.at(-1).blob.type==='image/png'&&downloads.at(-1).blob.size>1000),'profile PNG generated');
  const boxes=await page.locator('.ds-chart').evaluateAll(ns=>ns.map(n=>n.getBoundingClientRect()));check(Math.abs(boxes[0].height-boxes[1].height)<1,'both background panels have equal height');
  const plots=await page.locator('.ds-plot').evaluateAll(ns=>ns.map(n=>n.getBoundingClientRect()));check(Math.abs(plots[0].y-plots[1].y)<1,'plots align vertically');
  const box=await page.locator('#dsPlot').boundingBox();await page.mouse.move(box.x+100,box.y+100);await page.mouse.down();await page.mouse.move(box.x+160,box.y+100);await page.mouse.up();check(await page.evaluate(()=>!getSelection().toString()&&!document.body.classList.contains('ds-dragging')),'drag does not select text or leave dragging state');
  await page.locator('#dsCoordinates input[name=x]').fill('3');check(await page.locator('#dsCoordinates button').isDisabled(),'out of bounds blocks point query');
  check(await page.locator('#dsPlot2 path[data-series]').count()===1,'left input edits preserve right profile');
  await page.locator('#dsScope').selectOption('mean');await page.waitForFunction(()=>document.querySelectorAll('#dsPlot path[data-series]').length>0);
  check(await page.locator('#dsCoordinates').isHidden(),'switching back restores mean mode');
  await page.screenshot({path:'output/playwright/data-sheet-profile.png'});
  for(const [locale,caption] of [['en','Line profile'],['ja','ラインプロファイル']]){await page.evaluate(l=>CFDI18n.setLanguage(l),locale);check((await page.locator('.ds-field-heading').nth(1).innerText()).includes(caption),locale+' headings localized');check(await page.locator('#dsName').innerText()==='그래프 검사',locale+' user title preserved');}
  await page.setViewportSize({width:780,height:900});check(await page.locator('#dataSheet').evaluate(n=>n.scrollWidth<=n.clientWidth),'narrow layout does not overflow');
  await page.evaluate(()=>DataSheetViewer.setSelection({id:'fixture',name:'그래프 검사'},[{id:'other',name:'다른 Case'}]));
  check(await page.locator('#dsLineCoordinates input[name=x0]').inputValue()===''&&await page.locator('#dsPlot2 path[data-series]').count()===0,'Case change clears profile');
  check(!errors.length,'no browser runtime errors');return {checks};
 }finally{await page.close();}
}
