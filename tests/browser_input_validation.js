// Isolated browser fixture. No production project writes or solver execution.
async page => {
 const checks=[],errors=[];const check=(ok,label)=>{if(!ok)throw Error(label);checks.push(label);};const onerror=e=>errors.push(e.message);page.on('pageerror',onerror);
 await page.route('**/input-validation-test',r=>r.fulfill({contentType:'text/html',body:`<!doctype html><html><head><style>:root{--page:#161616;--surface:#222;--card:#222;--line:#444;--ink:#eee;--text:#eee;--muted:#aaa;--ink2:#ccc}body{background:#161616;color:#eee;font:14px Arial}.btn{background:#333;color:#eee;padding:8px;border:1px solid #555;border-radius:6px}</style></head><body><script src="/input_validation.js"></script><script src="/form_config_editor.js"></script><script src="/config_editor.js"></script></body></html>`}));
 const paste=async(locator,text)=>locator.evaluate((node,text)=>{node.focus();node.select();const clipboardData=new DataTransfer();clipboardData.setData('text/plain',text);node.dispatchEvent(new ClipboardEvent('paste',{clipboardData,bubbles:true,cancelable:true}));},text);
 try{
 await page.goto('http://127.0.0.1:18760/input-validation-test');await page.setViewportSize({width:1300,height:950});
 await page.evaluate(()=>{window.applied=[];CFDFormConfig.open({config:{inputs:{count:3,ratio:1.5,samples:[1,2],label:'text'}},onSave:value=>window.applied.push(value)});});
 const count=page.getByRole('textbox',{name:'count',exact:true}),ratio=page.getByRole('textbox',{name:'ratio',exact:true}),array=page.getByRole('textbox',{name:'samples',exact:true});
 await count.fill('1.5');check(await count.inputValue()==='3','fractional integer input cannot replace previous value');
 await paste(count,'2.5');check(await count.inputValue()==='3','fractional integer paste is blocked');
 await ratio.focus();await ratio.press('End');await ratio.pressSequentially('abc한글');check(await ratio.inputValue()==='1.5','non-numeric typing is blocked');
 check(await ratio.evaluate(e=>document.activeElement===e),'blocked typing preserves input focus');
 await paste(ratio,'12px');check(await ratio.inputValue()==='1.5','invalid paste preserves previous number');
 await paste(ratio,'1e-3');check(await ratio.inputValue()==='1e-3','valid scientific notation paste is accepted');
 await ratio.fill('');await ratio.pressSequentially('-1.5e-3');check(await ratio.inputValue()==='-1.5e-3','sign, decimal and exponent can be entered incrementally');
 await ratio.press('Control+Z');await ratio.fill('0.5');check(await ratio.inputValue()==='0.5','numeric input remains editable after undo');
 await count.fill('-');await page.getByRole('button',{name:'적용',exact:true}).click();check(await page.evaluate(()=>applied.length)===0,'unfinished numeric prefix cannot be saved');await count.fill('4');
 await array.fill('{}');check(await array.getAttribute('aria-invalid')==='true','array JSON rejects an object');await page.getByRole('button',{name:'적용',exact:true}).click();check(await page.evaluate(()=>applied.length)===0,'wrong JSON type cannot be saved');
 await page.getByRole('textbox',{name:'label',exact:true}).fill('자유 text 123');check(await page.getByRole('textbox',{name:'label',exact:true}).inputValue()==='자유 text 123','free-text fields accept text');
 await ratio.fill('1e-3');await array.fill('[3,4]');await page.getByRole('button',{name:'적용',exact:true}).click();
 check(await page.evaluate(()=>applied[0].inputs.count===4&&applied[0].inputs.ratio===.001&&applied[0].inputs.samples[1]===4),'valid numeric and array data save exactly');
 await page.evaluate(()=>CFDFormConfig.open({config:{x:1},onSave:value=>applied.push(value)}));
 await page.getByRole('button',{name:'JSON',exact:true}).click();const json=page.getByRole('textbox',{name:'Config JSON',exact:true});await json.fill('{"x":');
 await page.getByRole('button',{name:'적용',exact:true}).click();check(await page.evaluate(()=>applied.length)===1,'unfinished JSON cannot apply');await json.fill('[]');await page.getByRole('button',{name:'적용',exact:true}).click();check(await page.evaluate(()=>applied.length)===1,'root JSON must be an object');
 await json.fill('{"x":2}');await page.getByRole('button',{name:'적용',exact:true}).click();check(await page.evaluate(()=>applied[1].x===2),'completed JSON applies');
 await page.evaluate(()=>CFDSettings.open({config:{numerics:{end_s:10,dt_s:.1,write_interval_s:1},coupled:{processes:1},geometry:{width:2}},managed:true,onRun:(name,value)=>applied.push(value)}));
 const time=page.getByRole('textbox',{name:'목표 물리시간 (s)',exact:true});await time.fill('bad');check(await time.inputValue()==='10','Case termination blocks non-numeric input');
 await page.getByRole('combobox',{name:'종료 방식'}).selectOption('frames');const frames=page.getByRole('textbox',{name:'목표 저장 프레임 수',exact:true});const beforeFrames=await frames.inputValue();await frames.fill('2.5');check(await frames.inputValue()===beforeFrames,'frame count blocks fractional input');await frames.fill('3');
 await page.locator('#settingsSearch').fill('dt_s');const dt=page.locator('input[data-path="numerics.dt_s"]');await dt.fill('abc');check(await dt.inputValue()==='0.1','Case Config blocks text in numeric field');
 await dt.fill('-');await page.locator('#settingsSearch').fill('width');await page.locator('#settingsStart').click();check(await page.evaluate(()=>applied.length)===2,'unfinished number in hidden Config section blocks save');await page.locator('#settingsSearch').fill('dt_s');check(await dt.inputValue()==='-','unfinished draft survives section change');
 await dt.fill('0.1');await page.locator('#settingsStart').click();check(await page.evaluate(()=>applied.length)===3,'corrected Config saves');
 check(errors.length===0,'no browser runtime errors: '+errors.join('; '));return {checks};
 }finally{page.off('pageerror',onerror);await page.unrouteAll({behavior:'ignoreErrors'});}
}
