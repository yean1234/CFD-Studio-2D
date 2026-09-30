// Isolated review server only; no solver execution or production data writes.
async page=>{
 const checks=[],errors=[];const check=(v,m)=>{if(!v)throw Error(m);checks.push(m);};const onerror=e=>errors.push(e.message);page.on('pageerror',onerror);
 const origin='http://127.0.0.1:18760',api=async(path,body)=>{const r=body?await page.request.post(origin+'/api/executions'+path,{data:body}):await page.request.get(origin+'/api/executions'+path);return await r.json();};
 const before=await api('/forms');let generated=0;const onrequest=r=>{if(r.url().endsWith('/form-from-survey'))generated++;};page.on('request',onrequest);
 await page.goto(origin);await page.setViewportSize({width:1440,height:1050});await page.evaluate(()=>CFDI18n.setLanguage('ko'));await page.locator('#ewCreateForm').click();
 let wizard=page.locator('.fw-recommend-dialog');await wizard.waitFor();
 check(await page.locator('dialog.ew-form-dialog').count()===0,'new Template begins with questionnaire');check(await wizard.locator('[name=solver],[name=recommended_solver]').count()===0,'no solver choice before questionnaire');
 await wizard.getByRole('button',{name:'다음',exact:true}).click();check(await wizard.getByRole('alert').innerText().then(t=>t.includes('유체')),'unanswered question prevents advance');
 // Every question permits an explicit unsupported answer without creating a Template.
 const noneCheck=async(key,valid)=>{
  const radios=wizard.locator(`input[name=${key}]`);
  check(await radios.last().inputValue()==='not_listed',key+' has none-of-these last');
  await radios.last().check();
  check(await wizard.locator('.fw-unsupported').isVisible(),key+' shows unsupported verdict');
  check(await wizard.locator('.fw-actions .pri').isDisabled(),key+' blocks next step');
  await wizard.locator(`input[name=${key}][value=${valid}]`).check();
  check(await wizard.locator('.fw-unsupported').isHidden()&&!await wizard.locator('.fw-actions .pri').isDisabled(),key+' can recover');
 };
 await noneCheck('medium','gas');await noneCheck('purpose','flow');
 await wizard.locator('input[name=medium][value=not_listed]').check();await wizard.locator('input[name=purpose][value=not_listed]').check();
 check(await wizard.locator('.fw-unsupported li').count()===2,'all unsupported questions listed');
 await page.evaluate(()=>CFDI18n.setLanguage('en'));await wizard.getByText('Not supported',{exact:true}).waitFor();check(await wizard.getByText('None of these',{exact:true}).count()===2,'English none option');
 await page.evaluate(()=>CFDI18n.setLanguage('ja'));await wizard.getByText('対応不可',{exact:true}).waitFor();check(await wizard.getByText('ここにない',{exact:true}).count()===2,'Japanese none option');
 await page.evaluate(()=>CFDI18n.setLanguage('ko'));await wizard.getByText('지원 불가',{exact:true}).waitFor();await wizard.screenshot({path:'output/playwright/survey-unsupported.png'});
 check(JSON.stringify(await api('/forms'))===JSON.stringify(before),'unsupported choices leave stored Templates unchanged');
 await wizard.locator('input[name=medium][value=gas]').check();await wizard.locator('input[name=purpose][value=flow]').check();
 await page.evaluate(()=>CFDI18n.setLanguage('en'));check(await wizard.innerText().then(t=>t.includes('Which fluid')),'English questionnaire');await page.evaluate(()=>CFDI18n.setLanguage('ja'));check(await wizard.innerText().then(t=>t.includes('どの流体')),'Japanese questionnaire');await page.evaluate(()=>CFDI18n.setLanguage('ko'));check(await wizard.locator('input[name=medium][value=gas]').isChecked(),'answers retained across language changes');
 await wizard.screenshot({path:'output/playwright/solver-survey.png'});
 await wizard.getByRole('button',{name:'다음',exact:true}).click();await noneCheck('regime','laminar');await noneCheck('time_mode','transient');await wizard.getByRole('button',{name:'다음',exact:true}).click();
 for(const [k,v] of Object.entries({domain:'internal',mesh:'import',termination:'physical_time'}))await noneCheck(k,v);
 await wizard.locator('input[name=mesh][value=not_listed]').check();await wizard.getByRole('button',{name:'이전',exact:true}).click();await wizard.getByRole('button',{name:'다음',exact:true}).click();check(await wizard.locator('input[name=mesh][value=not_listed]').isChecked(),'back navigation preserves unsupported answer and permits returning to fix it');await wizard.locator('input[name=mesh][value=import]').check();
 await wizard.getByRole('button',{name:'솔버 추천',exact:true}).click();await wizard.locator('input[name=recommended_solver]').first().waitFor();
 check(JSON.stringify(await wizard.locator('input[name=recommended_solver]').evaluateAll(n=>n.map(x=>x.value)))===JSON.stringify(['icoFoam','pimpleFoam','pisoFoam']),'recommended set matches answers');
 check(generated===0,'recommendations do not generate fields');check(await wizard.getByRole('button',{name:'양식 생성',exact:true}).isDisabled(),'explicit solver selection required');
 await wizard.locator('input[value=icoFoam]').check();await wizard.screenshot({path:'output/playwright/solver-recommendations.png'});await wizard.getByRole('button',{name:'양식 생성',exact:true}).click();await wizard.waitFor({state:'detached'});
 const form=page.locator('dialog.ew-form-dialog');await form.waitFor();check(generated===1,'fields generated after selecting solver');check(await form.locator('[name=solver]').inputValue()==='icoFoam','selected solver carried into Template');check(await form.locator('[name=solver]').isDisabled(),'solver changes go through questionnaire');
 await form.locator('[name=name]').fill('Survey Template '+Date.now());const name=await form.locator('[name=name]').inputValue();await form.locator('[name=description]').fill('Survey selection test');
 await form.locator('[data-config]').click();check(await page.locator('.fc-dialog input[aria-label$=" Value"]').count()===0,'generated definition contains no physical value inputs');await page.locator('.fc-dialog').getByRole('button',{name:'Cancel',exact:true}).click();
 await form.locator('[data-wizard]').click();wizard=page.locator('.fw-recommend-dialog');await wizard.waitFor();await wizard.locator('input[name=purpose][value=interface]').check();await wizard.getByRole('button',{name:'다음',exact:true}).click();await wizard.getByRole('button',{name:'다음',exact:true}).click();await wizard.getByRole('button',{name:'솔버 추천',exact:true}).click();await wizard.getByText('선택한 조건에 맞는 등록 솔버가 없습니다 · 이전 단계에서 조건을 확인하세요',{exact:true}).waitFor();
 check(await wizard.locator('input[name=recommended_solver]').count()===0,'incompatible gas-only interface analysis has no recommendation');check(await wizard.getByRole('button',{name:'양식 생성',exact:true}).isDisabled(),'incompatible conditions cannot generate');await wizard.getByRole('button',{name:'취소',exact:true}).click();check(await form.locator('[name=solver]').inputValue()==='icoFoam','cancelling questionnaire preserves generated structure');check(await form.locator('[name=name]').inputValue()===name,'cancelling retains Template name');
 await form.getByRole('button',{name:'Template 저장',exact:true}).click();await form.waitFor({state:'detached'});const saved=(await api('/forms')).forms.find(x=>x.name===name);check(saved.config.analysis.choices.medium==='gas'&&saved.config.analysis.choices.purpose==='flow','saved conditions match successful generation');check(saved.config.initial_conditions.fields.p.value===null,'generated input values remain blank');
 await page.reload();await page.waitForSelector('#ewCreateForm');check((await api('/forms')).forms.some(x=>x.id===saved.id&&x.solver==='icoFoam'),'Template survives reload');const after=await api('/forms');check(before.forms.every(f=>JSON.stringify(after.forms.find(x=>x.id===f.id))===JSON.stringify(f)),'existing Templates unchanged');
 // A request outside the compatible set must also be rejected by the server.
 const forged=await api('/form-from-survey',{solver:'interFoam',answers:{medium:'gas',purpose:'flow',regime:'laminar',time_mode:'transient',domain:'internal',mesh:'import',termination:'physical_time'}});check(forged.ok===false,'server rejects incompatible solver');
 check(errors.length===0,'no browser runtime errors: '+errors.join('; '));page.off('pageerror',onerror);page.off('request',onrequest);return {count:checks.length,checks};
}
