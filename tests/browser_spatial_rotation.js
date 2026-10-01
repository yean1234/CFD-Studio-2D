// Synthetic previews only; no project writes or solver runs.
async page=>{
 page=await page.context().newPage();await page.goto('http://127.0.0.1:8712');await page.setViewportSize({width:1440,height:1000});
 const checks=[],check=(v,n)=>{if(!v)throw Error(n);checks.push(n);};
 for(const up of [[0,1,0],[0,0,1]]){
  await page.evaluate(async up=>{
   const host=document.createElement('div');host.id='rotationCheck';host.style.cssText='position:fixed;inset:80px auto auto 100px;width:700px;height:650px;z-index:99999;background:#111';document.body.append(host);
   const model={up,items:[{id:'front',name:'Front',kind:'box',min:[.4,-.1,-.1],max:[.6,.1,.1]},{id:'back',name:'Back',kind:'box',min:[-.6,-.1,-.1],max:[-.4,.1,.1]}]};
   window.rotationPreview=await CFDSpatial.viewer(host,model,{onSelect:()=>{},cameraState:{yaw:0,pitch:0,distance:2.8}});
  },up);
  const canvas=page.locator('#rotationCheck canvas');await canvas.waitFor();await page.waitForTimeout(100);
  const x=()=>page.locator('#rotationCheck .sp-leaders circle').first().getAttribute('cx').then(Number);
  const box=await canvas.boundingBox(),start=await x(),name=up[1]?'Y-up':'Z-up';
  await page.mouse.move(box.x+box.width/2,box.y+box.height/2+90);await page.mouse.down();await page.mouse.move(box.x+box.width/2+45,box.y+box.height/2+90,{steps:6});await page.mouse.up();
  check((await x())>start+3,name+' right drag moves front geometry right');
  await page.mouse.down();await page.mouse.move(box.x+box.width/2-45,box.y+box.height/2+90,{steps:9});await page.mouse.up();
  check((await x())<start-3,name+' left drag moves front geometry left');
  const before=await page.evaluate(()=>rotationPreview.cameraState());await page.mouse.down();await page.mouse.move(box.x+box.width/2-45,box.y+box.height/2+120,{steps:5});await page.mouse.up();
  const after=await page.evaluate(()=>rotationPreview.cameraState());check(after.pitch>before.pitch&&after.distance===before.distance,name+' vertical drag and distance preserved');
  await page.evaluate(()=>{rotationPreview();document.getElementById('rotationCheck').remove();});
 }
 await page.close();return {passed:checks.length,checks};
}
