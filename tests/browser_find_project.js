// Review server only; folder picking and registration are mocked, no project writes.
async page=>{
 const checks=[];let picks=0,opens=0;
 const check=(ok,label)=>{if(!ok)throw Error(label);checks.push(label);};
 const picker=async route=>{picks++;await route.fulfill({json:{ok:true,result:{cancelled:true}}});};
 const register=async route=>{opens++;await route.fulfill({status:400,json:{ok:false,msg:'프로젝트 형식 오류'}});};
 await page.route('**/api/executions/project-pick',picker);
 await page.route('**/api/executions/project-open',register);
 try{
  await page.goto('http://127.0.0.1:18760');
  await page.locator('#ewFindProject').click();
  let dialog=page.locator('dialog.ew-dialog');
  const path=dialog.locator('[name=storage_path]');
  await dialog.getByRole('heading',{name:'프로젝트 찾기'}).click();
  check(await dialog.locator('.input-feedback:not([hidden])').count()===0,'blur does not show required feedback');
  await path.focus();await dialog.getByRole('button',{name:'찾기',exact:true}).click();
  await page.waitForFunction(()=>!document.querySelector('dialog [data-pick]').disabled);
  check(picks===1&&opens===0,'picker works with an empty path without registration');
  check(await dialog.locator('.input-feedback:not([hidden])').count()===0,'picker cancellation does not show required feedback');
  await path.focus();await dialog.getByRole('button',{name:'취소',exact:true}).click();
  await dialog.waitFor({state:'detached'});
  check(await dialog.count()===0,'cancel closes on first click with an empty path');
  await page.locator('#ewFindProject').click();dialog=page.locator('dialog.ew-dialog');
  await dialog.getByRole('button',{name:'추가',exact:true}).click();
  check(await dialog.locator('[name=storage_path]').getAttribute('aria-invalid')==='true'&&opens===0,'Add validates missing path and blocks registration');
  await dialog.getByRole('button',{name:'찾기',exact:true}).click();
  await page.waitForFunction(()=>!document.querySelector('dialog [data-pick]').disabled);
  check(picks===2&&await dialog.locator('.input-feedback:not([hidden])').count()===0,'picker clears previous required feedback');
  await dialog.locator('[name=storage_path]').fill('D:\\Example');
  await dialog.getByRole('button',{name:'추가',exact:true}).click();
  await dialog.getByRole('status').filter({hasText:'프로젝트 형식 오류'}).waitFor();
  check(opens===1,'Add still shows actual project validation failures');
  await dialog.getByRole('button',{name:'취소',exact:true}).click();
  return {checks};
 }finally{
  await page.unroute('**/api/executions/project-pick',picker);
  await page.unroute('**/api/executions/project-open',register);
 }
}
