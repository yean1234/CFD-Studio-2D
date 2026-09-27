// tests/serve_review.py의 전용 가짜 실행 자료로만 복구·취소 UX를 확인한다.
async page => {
  const origin=await page.evaluate(()=>location.origin),checks=[];
  const check=(ok,label)=>{if(!ok)throw Error(label);checks.push(label);};
  await page.addInitScript(()=>{window.confirm=()=>true;});
  const get=async p=>(await page.request.get(origin+p)).json();
  const studies=(await get('/api/studies')).studies;
  if(studies.length!==2||!studies.every(s=>['UX 복구 확인','UX 예약 취소'].includes(s.name)))throw Error('Recovery fixture server only');
  const a=studies.find(s=>s.name==='UX 복구 확인').id,b=studies.find(s=>s.name==='UX 예약 취소').id;
  await page.goto(origin+'/studies?study='+b);
  await page.locator('#queueBlocker a').waitFor({state:'visible'});
  check((await page.locator('#queueBlocker a').getAttribute('href')).includes(a),'unrelated study links to blocking attempt');
  check(await page.locator('#enqueue').isDisabled(),'blocked queue does not pretend execution can start');
  await page.locator('#queueBlocker a').click();
  await page.locator('[data-attempt-action="resolve_recovery"]').click();
  await page.locator('#recoverySubmit').click();
  check(await page.locator('#recoveryDialog').isVisible(),'recovery requires stop confirmation and note');
  await page.locator('#stoppedConfirmed').check();await page.locator('#recoveryNote').fill('UI fixture: no solver process was launched');
  await page.locator('#recoverySubmit').click();
  await page.waitForFunction(()=>!document.querySelector('#recoveryDialog').open);
  let d=await get('/api/studies/'+a);
  check(d.attempts[0].state==='failed'&&d.attempts[0].result.recovery_audit.confirmed_stopped===true,'recovery audit preserves failed attempt');
  check(d.paused,'recovery does not automatically launch work');
  await page.goto(origin+'/studies?study='+b);
  await page.locator('[data-attempt-action="cancel"]').click();
  await page.waitForFunction(()=>document.querySelector('#attempts').textContent.includes('취소'));
  check((await get('/api/studies/'+b)).attempts[0].state==='cancelled','queued work can be cancelled');
  await page.goto(origin+'/studies?study='+a);
  await page.locator('[data-attempt-action="retry"]').click();
  await page.waitForFunction(()=>document.querySelectorAll('#attempts tr').length===2);
  d=await get('/api/studies/'+a);check(d.attempts[0].state==='failed'&&d.attempts[1].state==='queued','retry creates new attempt without erasing failure');
  await page.locator('#resume').click();
  await page.waitForFunction(()=>document.querySelector('#attempts').textContent.includes('통과'));
  d=await get('/api/studies/'+a);check(d.attempts[1].quality==='pass','explicit queue resume runs fixture');
  return {checks,scope:'UI fixture only; not physical CFD'};
}
