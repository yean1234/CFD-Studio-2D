const test=require('node:test'),assert=require('node:assert/strict');
const {VERSION,commands,validate,prompt}=require('../cfd_studio/internal/agent_controls.js');
test('versioned catalogue has no duplicate commands',()=>{assert.equal(VERSION,'1.4');assert.equal(new Set(commands).size,commands.length);});
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

test('JSON commands validate scope, syntax and size before dispatch',()=>{
 for(const scope of ['config','geometry'])assert.doesNotThrow(()=>validate('config.json.open',{scope}));
 for(const args of [{},{scope:'files'},{scope:['config']}])assert.throws(()=>validate('config.json.open',args));
 for(const value of ['{"a":1}','[1,2,3]','0'])assert.doesNotThrow(()=>validate('config.json.fill',{value}));
 for(const value of [{a:1},'{bad}',JSON.stringify('x'.repeat(1000000))])assert.throws(()=>validate('config.json.fill',{value}));
 assert.doesNotThrow(()=>validate('config.json.apply',{}));
});
test('agent prompt requires JSON drafts and staged user review',()=>{
 const text=prompt();for(const fragment of ['state().json','not field-by-field entry','before final saving','before queue.add or queue.start','not a server-enforced approval system','JSON apply does not save'])assert.ok(text.includes(fragment),fragment);
});

test('connection recovery never confuses server responses with visible draft review',()=>{
 const text=prompt();
 for(const fragment of ['even an OK result does not prove current-tab access','NOT a live-editor export',
  'no reply is not approval','pause the affected operational step','stop unchanged retries',
  'reconcile user changes','proposed assumptions','only when its target, reviewed inputs and scope are unchanged'])
  assert.ok(text.includes(fragment),fragment);
});

test('external progress is cooperative and never a CFD control transport',()=>{
 const text=prompt();
 for(const fragment of ['agent_progress.py start','Exit 3 or PAUSED','exit 4 means no visible-tab render receipt',
  'cannot interrupt your provider','cannot apply Config or run CFD','not attachment to the user'])assert.ok(text.includes(fragment),fragment);
});
