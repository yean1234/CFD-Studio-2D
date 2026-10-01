// Read-only result inspection in a separate tab; no solver or project mutations.
async page=>{
 page=await page.context().newPage();
 const errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto('http://127.0.0.1:8712');await page.waitForFunction(()=>window.CFDWorkspaceState?.().projects.length);
 const checks=[],check=(v,n)=>{if(!v)throw Error(n);checks.push(n);};
 const id=await page.evaluate(()=>CFDWorkspaceState().projects.flatMap(p=>p.runs).find(r=>r.kind==='warehouse'&&r.has_results)?.rid);
 // Read the catalogue if workspace entries do not expose a result ID.
 const records=await page.request.get('http://127.0.0.1:8712/api/warehouse/results');const listing=await records.json();
 const entries=Array.isArray(listing)?listing:(listing.results||listing.cases||[]);const target=entries.find(r=>r.frames>1&&r.id.includes('porous_r2_serial'))?.id||entries.find(r=>r.frames>1&&r.id.includes('porous'))?.id||id;if(!target)throw Error('No saved warehouse sequence');
 await page.evaluate(async id=>{await loadWarehouseResult(id,'Playback check');setMode('viz');},target);
 await page.waitForFunction(()=>typeof WH!=='undefined'&&WH&&FRAMES.length>1&&warehouseFrameReady(0));
 check(await page.locator('#tbar').getAttribute('step')==='any','continuous slider enabled');
 await page.evaluate(()=>{seekPlayback(0);setPlay(true,true);});await page.waitForTimeout(900);
 const playing=await page.evaluate(()=>({clock,idx,value:Number(document.getElementById('tbar').value),end:FRAMES.at(-1).pt}));
 check(playing.clock>0&&playing.value>0,'warehouse slider moves before next stored frame');check(Math.abs(playing.value-playing.clock/playing.end)<.00001,'slider uses elapsed duration');
 await page.evaluate(()=>{setPlay(false,true);seekPlayback(.37);});
 const seek=await page.evaluate(()=>({clock,end:FRAMES.at(-1).pt,value:Number(document.getElementById('tbar').value),idx}));check(Math.abs(seek.clock-seek.end*.37)<1e-6,'scrubbing selects fractional physical time');
 await page.evaluate(()=>setPlay(true,true));await page.waitForTimeout(150);check(await page.evaluate(t=>clock>=t,seek.clock),'resume does not jump back to sample');await page.evaluate(()=>setPlay(false,true));
 await page.locator('#controls').screenshot({path:'output/playwright/continuous-playback.png'});
 // Verify adapters share the same time mapping without requesting or altering saved data.
 const edge=await page.evaluate(()=>{const b=document.getElementById('tbar');CFDPresentation.sync(b,[10,70,310],40);const first=Number(b.value);CFDPresentation.sync(b,[0],0);return {first,disabled:b.disabled};});check(edge.first===.1&&edge.disabled,'irregular and one-frame sequences handled');
 check(!errors.length,'no browser exceptions: '+errors.join(';'));await page.close();return {passed:checks.length,checks,playing,seek};
}
