// Run on a disposable Studio page; all Config edits remain in memory.
async page=>{
 const checks=[],errors=[],check=(v,m)=>{if(!v)throw Error(m);checks.push(m);};
 page.on('pageerror',e=>errors.push(e.message));
 const c={geometry:{regions:[{name:'Region A',shape:'box',unit:'m',min:[0,0,0],max:[1,1,1]},{name:'Region B',shape:'cylinder',unit:'m',center:[1,1,1],radius:.2,height:.5,axis:'z'}]},mesh:{cell_size:{value:.1,unit:'m'},refinement_regions:[]}};
 await page.evaluate(c=>{CFDI18n.setLanguage('ko');window.meshEditor?.close();window.meshEditor=CFDFormConfig.open({config:c,valuesOnly:true,onSave:v=>window.meshSaved=v});},c);
 const d=page.locator('.fc-dialog[open]');await d.locator('.fc-nav>button[title=mesh]').click();
 await d.getByLabel('격자 대상 형상',{exact:true}).selectOption({label:'Region A'});await d.getByRole('button',{name:'형상에서 추가',exact:true}).click();
 await d.locator('[data-config-path="mesh.refinement_regions.0.cell_size.value"]').fill('0.025');
 await d.getByLabel('격자 대상 형상',{exact:true}).last().selectOption({label:'Region B'});
 check(await page.evaluate(()=>meshEditor.getConfig().mesh.refinement_regions[0].target_path.at(-1)===1),'geometry selection changes the stored target');
 await d.locator('.fc-editor-card>.fc-actions').getByRole('button',{name:'저장',exact:true}).click();
 check(await page.evaluate(()=>meshSaved.mesh.refinement_regions[0].cell_size.value===.025&&!Object.hasOwn(meshSaved.mesh.refinement_regions[0],'min')),'saved spacing refers to live geometry without stale bounds');
 await page.evaluate(()=>{meshEditor=CFDFormConfig.open({config:meshSaved,valuesOnly:true,onSave:v=>window.meshSaved=v});});await d.locator('.fc-nav>button[title=mesh]').click();
 check(await d.getByLabel('격자 대상 형상',{exact:true}).last().inputValue()==='["geometry","regions",1]','geometry reference restored');
 for(const lang of ['en','ja']){await page.evaluate(l=>CFDI18n.setLanguage(l),lang);await page.waitForTimeout(150);const korean=await d.locator('.fc-main').evaluate(e=>{const w=document.createTreeWalker(e,NodeFilter.SHOW_TEXT);let n;const out=[];while(n=w.nextNode())if(n.parentElement.checkVisibility()&&!n.parentElement.closest('[translate=no],pre,code,textarea')&&/[가-힣]/.test(n.nodeValue))out.push(n.nodeValue);return out;});check(!korean.length,lang+' refinement controls translated: '+korean.join(';'));}
 await page.evaluate(()=>{CFDI18n.setLanguage('ko');meshEditor.close();});check(!errors.length,'no browser script errors');return {count:checks.length,checks};
}
