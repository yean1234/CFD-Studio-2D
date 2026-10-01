const test=require('node:test'),assert=require('node:assert/strict');
const {VERSION,commands,validate,prompt}=require('../cfd_studio/internal/agent_controls.js');
test('versioned catalogue has no duplicate commands',()=>{assert.equal(VERSION,'1.0');assert.equal(new Set(commands).size,commands.length);});
test('reject unsupported commands and invalid parameters',()=>{
 for(const [name,args] of [['eval',{}],['ui.fill',{target:'x',value:3}],['ui.check',{target:'x',checked:1}],['ui.select',{value:'x'}],['viewer.mode',{mode:'bad'}],['project.select',{}],['case.select',null]])assert.throws(()=>validate(name,args));
});
test('accept stable navigation and observed field actions',()=>{
 for(const [name,args] of [['cfd.open',{}],['project.select',{id:'p'}],['case.select',{id:'r'}],['ui.fill',{target:'ui-1',value:'1e-3'}],['ui.check',{target:'ui-1',checked:false}],['viewer.mode',{mode:'data'}]])assert.equal(validate(name,args),args);
});
test('prompt distinguishes dispatch, execution and physical validation',()=>{
 const text=prompt();for(const fragment of ['existing visible tab','NOT that a save/export/CFD run succeeded','queue.start resumes the entire','Do not invent geometry','does not stop an in-flight command or solver'])assert.ok(text.includes(fragment),fragment);
 for(const name of commands)assert.ok(text.includes(name));
});
