// Run through playwright-cli run-code on the isolated review server (port 18759).
// Uses synthetic result responses; no CFD run or user project is created.
async page => {
 const checks=[],errors=[];const check=(value,label)=>{if(!value)throw Error(label);checks.push(label);};
 const onerror=e=>errors.push(e.message);page.on('pageerror',onerror);
 let releasePressure;const pressureGate=new Promise(resolve=>releasePressure=resolve);
 const metrics=[{id:'temperature',name:'온도',unit:'°C'},{id:'velocity',name:'유속',unit:'m/s'},{id:'pressure',name:'압력',unit:'Pa'}];
 await page.route('**/chart-panel-test',r=>r.fulfill({contentType:'text/html',body:`<!doctype html><html><head><style>:root{--page:#10100f;--surface:#1b1b19;--surface2:#252523;--line:#383835;--ink:#e5e5df;--muted:#a4a49b;--s1:#3987e5;--s3:#ef776d}body{margin:0;font-family:Arial,sans-serif;background:var(--page);color:var(--ink)}#viz{position:absolute;inset:0}.btn{background:var(--surface2);color:var(--ink);border:1px solid var(--line);border-radius:6px}button,select{cursor:pointer}</style></head><body class="grouped execution-viewer"><div id="viz"></div><script>function setPlay(){};window.downloads=[];function exportDownload(blob,name){window.downloads.push({blob,name});}</script><script src="/data_sheet_viewer.js"></script></body></html>`}));
 await page.route('**/api/executions/chart-catalog?*',r=>r.fulfill({json:{axis:'time',metrics}}));
 await page.route('**/api/executions/chart?*',async r=>{const q=new URL(r.request().url()).searchParams,metric=q.get('metric');if(metric==='pressure')await pressureGate;const values=metric==='temperature'?[10,20,30]:metric==='velocity'?[.1,.2,.3]:[100,200,300];try{await r.fulfill({json:{points:values.map((v,i)=>[i,v]),next:3,total:3,errors:[],basis:'UI 검사용 데이터'}});}catch(_){} });
 try{
  await page.setViewportSize({width:1360,height:850});await page.goto('http://127.0.0.1:18759/chart-panel-test');
  await page.evaluate(()=>{const run={id:'fixture',name:'검사 데이터'};DataSheetViewer.setSelection({id:'fixture-project',name:'그래프 검사',runs:[run]},[run]);DataSheetViewer.setMode('data');});
  await page.waitForFunction(()=>document.getElementById('dsCoverage').textContent.includes('3 / 3')&&document.getElementById('dsCoverage2').textContent.includes('3 / 3'));
  const left=await page.locator('#dsPlot').boundingBox(),right=await page.locator('#dsPlot2').boundingBox();
  check(left.x+left.width<right.x&&Math.abs(left.y-right.y)<2,'two charts are side by side');
  check(left.height<=370&&right.height<=370,'chart height is bounded');
  check(await page.locator('#dsField').inputValue()!==await page.locator('#dsField2').inputValue(),'initial panels show different available metrics');
  await page.mouse.move(left.x+left.width*.2,left.y+left.height*.5);await page.mouse.down();await page.mouse.move(left.x+left.width*.54,left.y+left.height*.6,{steps:8});
  check(await page.evaluate(()=>window.getSelection().toString()===''),'drag does not select text');
  check(await page.evaluate(()=>document.body.classList.contains('ds-dragging')),'selection guard is active while dragging');
  await page.mouse.up();
  check(!await page.evaluate(()=>document.body.classList.contains('ds-dragging')),'selection guard is released after pointer up');
  check((await page.locator('#dsX').innerText()).includes('X = 1'),'left cursor snaps to the stored time');
  check((await page.locator('#dsValues').innerText()).includes('20 °C'),'left cursor displays its exact value');
  check(await page.locator('#dsPlot2 [data-cursor]').count()===0,'left dragging does not move right cursor');
  await page.locator('#dsPlot2').click({position:{x:right.width*.54,y:right.height*.5}});await page.locator('#dsPlot2').press('End');
  check((await page.locator('#dsX2').innerText()).includes('X = 2'),'right keyboard navigation is independent');
  check((await page.locator('#dsX').innerText()).includes('X = 1'),'right navigation preserves left cursor');
  await page.locator('#dsExport').click();await page.getByRole('button',{name:'CSV 데이터',exact:true}).click();await page.locator('dialog').waitFor({state:'detached'});await page.locator('#dsExport2').click();await page.getByRole('button',{name:'CSV 데이터',exact:true}).click();await page.locator('dialog').waitFor({state:'detached'});
  const csv=await page.evaluate(async()=>Promise.all(window.downloads.map(async x=>({name:x.name,text:await x.blob.text()}))));
  check(csv[0].name!==csv[1].name&&csv[0].text.includes('°C')&&csv[1].text.includes('m/s'),'each CSV uses its own metric and filename');
  await page.evaluate(()=>{window.exportDownload=(blob,name)=>{window.downloads.push({blob,name});if(blob.type==='image/png'){const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),5000);}};});
  await page.locator('#dsExport').click();
  check((await page.locator('dialog').innerText()).includes('온도'),'left Export identifies its metric');
  check(await page.getByRole('button',{name:'영상 내보내기',exact:true}).count()===0,'Data Sheet Export has no video action');
  const downloadEvent=page.waitForEvent('download');await page.getByRole('button',{name:'PNG 이미지',exact:true}).click();
  const download=await downloadEvent;await download.saveAs('output/playwright/chart-export-temperature.png');await page.locator('dialog').waitFor({state:'detached'});
  const image=await page.evaluate(async()=>{const d=window.downloads.at(-1),bitmap=await createImageBitmap(d.blob),c=document.createElement('canvas');c.width=bitmap.width;c.height=bitmap.height;const x=c.getContext('2d');x.drawImage(bitmap,0,0);const rgba=x.getImageData(0,0,c.width,c.height).data;let colored=0;for(let i=0;i<rgba.length;i+=4)if(rgba[i+2]>150&&rgba[i+2]>rgba[i]+30)colored++;return {width:c.width,height:c.height,bytes:d.blob.size,colored};});
  check(image.width===1280&&image.height>720&&image.bytes>1000&&image.colored>100,'PNG is decodable and contains the plotted series');
  await page.locator('#dsExport2').click();check((await page.locator('dialog').innerText()).includes('유속'),'right Export identifies its independent metric');await page.getByRole('button',{name:'닫기',exact:true}).click();
  await page.locator('#dsField').selectOption('pressure|Pa|time');
  await page.waitForFunction(()=>document.getElementById('dsRead').textContent==='읽기 중지');
  check((await page.locator('#dsX2').innerText()).includes('X = 2'),'changing left metric preserves right cursor');
  await page.locator('#dsField').selectOption('temperature|°C|time');releasePressure();
  await page.waitForFunction(()=>document.getElementById('dsRead').textContent==='다시 읽기');
  check((await page.locator('#dsCoverage2').innerText()).includes('3 / 3'),'cancelling left request preserves right data');
  check(await page.locator('#dsField').inputValue()==='temperature|°C|time','late response cannot replace the current metric');
  // Explicit pointer cancellation must also restore normal text selection.
  await page.mouse.move(left.x+left.width*.5,left.y+left.height*.5);await page.mouse.down();
  await page.locator('#dsPlot').dispatchEvent('pointercancel',{pointerId:1});await page.mouse.up();
  check(!await page.evaluate(()=>document.body.classList.contains('ds-dragging')),'pointer cancellation removes selection guard');
  await page.screenshot({path:'output/playwright/two-chart-desktop.png'});
  await page.setViewportSize({width:780,height:850});
  const narrowLeft=await page.locator('#dsPlot').boundingBox(),narrowRight=await page.locator('#dsPlot2').boundingBox();
  check(narrowRight.y>narrowLeft.y+narrowLeft.height,'narrow screen stacks charts');
  check(await page.evaluate(()=>document.getElementById('dataSheet').scrollWidth<=document.getElementById('dataSheet').clientWidth),'narrow charts do not overflow horizontally');
  await page.screenshot({path:'output/playwright/two-chart-narrow.png'});
  check(errors.length===0,'no browser runtime errors');return {checks};
 }finally{releasePressure();page.off('pageerror',onerror);await page.unrouteAll({behavior:'ignoreErrors'});}
}
