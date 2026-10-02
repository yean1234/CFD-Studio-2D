// Visible, disposable Config drafts; no backend project or solver writes.
async page=>{
 page=await page.context().newPage();const checks=[],errors=[],check=(v,n)=>{if(!v)throw Error(n);checks.push(n);};page.on('pageerror',e=>errors.push(e.message));
 try{
 await page.goto('http://127.0.0.1:8712');await page.waitForFunction(()=>window.CFDAgent?.version==='1.3');await page.evaluate(()=>CFDI18n.setLanguage('ko'));await page.setViewportSize({width:1800,height:1100});
 await page.evaluate(()=>{window.coopSaved=false;window.coopEditor=CFDFormConfig.open({config:{run:{dt_s:.1},geometry:{regions:[{name:'Review region',shape:'box',unit:'m',min:[0,0,0],max:[1,1,1]}]}},valuesOnly:true,onSave:()=>{coopSaved=true;}});});
 const first=await page.evaluate(()=>CFDAgent.observe());check(first.changed&&!!first.cursor,'initial compact observation has cursor');check(!(await page.evaluate(c=>CFDAgent.observe({after:c}),first.cursor)).changed,'unchanged observation omits repeated state');
 check(await page.evaluate(()=>CFDAgent.inspect({query:'JSON',limit:2}).controls.length<=2),'control search is bounded');
 const a=await page.evaluate(()=>CFDAgent.claim({name:'Config agent',task:'Review draft'}));check(!!a.token,'operator acquires token');check((await page.evaluate(()=>CFDAgent.claim({name:'Second agent'}))).error==='OWNER_BUSY','second operator cannot take control');
 check((await page.evaluate(()=>CFDAgent.run('config.json.open',{scope:'config'},{response:'compact'}))).error==='OWNER_REQUIRED','commands without active owner rejected');
 const run=(cmd,args={})=>page.evaluate(([cmd,args,owner])=>CFDAgent.run(cmd,args,{owner,response:'compact'}),[cmd,args,a.token]);
 const opened=await run('config.json.open',{scope:'config'});check(opened.status==='dispatched'&&!opened.state&&!!opened.observation,'compact receipt excludes full controls and Config');
 const doc=await page.evaluate(()=>CFDAgent.configDocument().document);doc.config.run.dt_s=.2;
 await run('config.json.fill',{value:JSON.stringify(doc)});await run('config.json.apply');
 await page.locator('.fc-json-pane').getByRole('button',{name:'취소',exact:true}).click();
 await run('review.open');const review=page.locator('.fc-review[open]');check(await review.innerText().then(s=>s.includes('run.dt_s')&&s.includes('0.1')&&s.includes('0.2')),'review shows actual before and after values');
 const found=await page.evaluate(()=>CFDAgent.inspect({query:'확인 완료',limit:10}));check(found.total===0,'review confirmation excluded from agent targets');
 await review.getByRole('button',{name:'확인 완료',exact:true}).click();check(await page.evaluate(()=>CFDAgent.review.status().confirmed),'user confirms this draft');check(!await page.evaluate(()=>coopSaved),'review does not save Config');
 await run('config.json.open',{scope:'config'});doc.config.run.dt_s=.3;await run('config.json.fill',{value:JSON.stringify(doc)});check(!await page.evaluate(()=>CFDAgent.review.status().confirmed),'pending JSON invalidates review');await run('config.json.apply');check(!await page.evaluate(()=>CFDAgent.review.status().confirmed),'applied edit needs new review');
 const observed=await page.evaluate(()=>CFDAgent.observe());
 await page.locator('.fc-json-pane textarea').fill(JSON.stringify({...doc,config:{...doc.config,run:{dt_s:.4}}}));
 const conflicted=await page.evaluate(([owner,expectedContext])=>CFDAgent.run('config.json.apply',{}, {owner,expectedContext,response:'compact'}),[a.token,observed.context]);check(conflicted.error==='CONTEXT_CHANGED','actual human edit invalidates observed context');
 await run('config.json.apply');
 const timeout=await page.evaluate(async()=>{const s=CFDAgent.observe();return await CFDAgent.waitForChange({after:s.cursor,timeoutMs:20});});check(timeout.timedOut&&!timeout.changed,'unchanged wait returns compact timeout');
 const snapshot=await page.evaluate(()=>CFDAgent.observe());const wait=page.evaluate(c=>CFDAgent.waitForChange({after:c,timeoutMs:2000}),snapshot.cursor);await page.locator('#agentBannerStop').click();const changed=await wait;check(changed.changed&&changed.paused,'wait wakes on user pause');check((await run('config.json.open',{scope:'config'})).error==='PAUSED','owner cannot bypass pause');
 await page.locator('#agentBannerStop').click();
 const stale=await page.evaluate(owner=>CFDAgent.run('config.json.open',{scope:'config'},{owner,expectedContext:'old',response:'compact'}),a.token);check(stale.error==='CONTEXT_CHANGED','stale selection guarded before action');
 const handoff=await page.evaluate(owner=>CFDAgent.release({owner,summary:'Draft ready; user review pending'}),a.token);check(handoff.handoff.summary.includes('review pending'),'handoff records next step');check(!JSON.stringify(handoff).includes(a.token),'handoff never includes operator token');
 const b=await page.evaluate(()=>CFDAgent.claim({name:'Review agent',task:'Check the draft'}));check(!!b.token,'next operator acquires released control');
 await page.locator('#agentExpand').click();await page.locator('#agentTakeover').click();check(await page.evaluate(()=>CFDAgent.status().paused),'user takeover pauses subsequent commands');check(!(await page.evaluate(()=>CFDAgent.status().collaboration)).owner,'user can clear operator');
 await page.locator('#agentBannerStop').click();check((await page.evaluate(owner=>CFDAgent.run('config.json.open',{scope:'config'},{owner,response:'compact'}),b.token)).error==='OWNER_EXPIRED','user takeover revokes the previous token');await page.evaluate(()=>CFDAgent.finish());
 await page.locator('.fc-json-pane').getByRole('button',{name:'취소',exact:true}).click();await page.locator('.fc-dialog[open]').getByRole('button',{name:'변경 검토',exact:true}).click();
 await page.locator('.fc-review').screenshot({path:'output/playwright/agent-change-review.png'});await page.locator('.fc-review>.fc-actions').getByRole('button',{name:'닫기',exact:true}).click();
 const sizes=await page.evaluate(()=>({full:new TextEncoder().encode(JSON.stringify(CFDAgent.state())).length,compact:new TextEncoder().encode(JSON.stringify(CFDAgent.observe())).length}));check(sizes.compact<sizes.full,'compact response smaller on the same synthetic screen');
 await page.evaluate(()=>CFDI18n.setLanguage('ja'));check(await page.locator('#agentRecipe option[value="handoff"]').textContent()==='操作担当・引継ぎ','workflow selector translated');check(await page.evaluate(()=>CFDAgent.recipe('review','en').includes('generated Template')),'localized workflow prompts available');
 await page.evaluate(()=>{CFDI18n.setLanguage('ko');coopEditor.close();CFDAgent.finish();});check(!errors.length,'no browser exceptions');return {passed:checks.length,checks,bytes:sizes};
 }finally{await page.close();}
}
