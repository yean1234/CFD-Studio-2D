// Review registry only; no save or CFD execution.
async page=>{
 const checks=[];const check=(v,m)=>{if(!v)throw Error(m);checks.push(m);};
 await page.goto('http://127.0.0.1:18760');await page.setViewportSize({width:1440,height:1050});await page.evaluate(()=>CFDI18n.setLanguage('ko'));
 const answers=async a=>{
  await page.locator('#ewCreateForm').click();const d=page.locator('.fw-recommend-dialog');await d.waitFor();
  for(const keys of [['medium','purpose'],['regime','time_mode'],['domain','mesh','termination']]){
   for(const k of keys)await d.locator(`input[name=${k}][value=${a[k]}]`).check();
   await d.getByRole('button',{name:keys[0]==='domain'?'솔버 추천':'다음',exact:true}).click();
  }
  await d.locator('.fw-selection').waitFor();return d;
 };
 let d=await answers({medium:'gas',purpose:'flow',regime:'laminar',time_mode:'steady',domain:'internal',mesh:'import',termination:'physical_time'});
 check(await d.locator('input[name=recommended_solver]').count()===0,'incompatible conditions are not presented as supported');
 const first=d.locator('.fw-alternative').first();check(await first.innerText().then(t=>t.includes('simpleFoam')&&t.includes('물리시간')&&t.includes('수렴 기준')),'exact blocking condition and proposed change are shown');
 check(await d.locator('.fw-selection').innerText().then(t=>t.includes('물리시간')),'original answer is unchanged before confirmation');
 await d.screenshot({path:'output/playwright/solver-mismatch.png'});
 await first.getByRole('button',{name:'이 조건으로 다시 추천',exact:true}).click();await d.locator('input[name=recommended_solver][value=simpleFoam]').waitFor();
 await d.locator('.fw-selection summary').click();
 check(await d.locator('.fw-selection').innerText().then(t=>t.includes('수렴 기준')),'explicit acceptance updates the termination condition');
 check(await d.getByRole('button',{name:'양식 생성',exact:true}).isDisabled(),'solver must still be explicitly selected');
 await d.locator('input[value=simpleFoam]').check();await d.getByRole('button',{name:'양식 생성',exact:true}).click();await d.waitFor({state:'detached'});
 await page.locator('.ew-form-dialog').getByRole('button',{name:'취소',exact:true}).click();await page.locator('.ew-form-dialog').waitFor({state:'detached'});
 d=await answers({medium:'liquid_gas',purpose:'flow',regime:'RAS',time_mode:'transient',domain:'internal',mesh:'generate',termination:'physical_time'});
 check(await d.locator('input[name=recommended_solver][value=interFoam]').count()===1,'multiphase general flow now recommends a VOF solver');
 await d.screenshot({path:'output/playwright/solver-multiphase.png'});
 await d.locator('input[value=interFoam]').check();await d.getByRole('button',{name:'양식 생성',exact:true}).click();await d.waitFor({state:'detached'});
 const form=page.locator('.ew-form-dialog');await form.locator('[data-config]').click();await page.locator('.fc-dialog').getByRole('button',{name:'JSON',exact:true}).click();
 const definition=JSON.parse(await page.locator('.fc-json').inputValue());
 check(await page.evaluate(s=>{const c=CFDFormConfig.toConfig(s);return Object.keys(c.materials.fluids).length===2&&Object.hasOwn(c.initial_conditions.fields,'alpha.phase_1')},definition),'multiphase fields are retained for a general flow intention');
 await page.locator('.fc-dialog').getByRole('button',{name:'Cancel',exact:true}).click();await form.getByRole('button',{name:'취소',exact:true}).click();
 return {checks};
}
