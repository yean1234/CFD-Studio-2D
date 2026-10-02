const {test}=require('node:test'),assert=require('node:assert/strict');
const {diff,coordinator,prompts}=require('../cfd_studio/internal/agent_collaboration.js');
test('review identifies added, changed and removed values including termination metadata',()=>{
 const before={x:1,list:[1,2],_studio:{termination:{time_s:30}}},after={x:2,list:[1],y:true,_studio:{termination:{time_s:60}}};
 const result=diff(before,after);assert.equal(result.total,4);assert.ok(result.rows.some(x=>x.path.join('.')==='_studio.termination.time_s'));assert.equal(result.rows.find(x=>x.path[0]==='y').kind,'added');assert.deepEqual(before.list,[1,2]);
 const bounded=diff(before,after,{limit:1});assert.equal(bounded.total,4);assert.equal(bounded.truncated,true);assert.equal(bounded.rows.length,1);
});
test('one operator at a time, renew, handoff and expiry retain write protection',()=>{
 let now=0;const c=coordinator({now:()=>now,uuid:()=>String(now),ttl:100});const a=c.claim({name:'A',task:'Config'});
 assert.throws(()=>c.claim({name:'B'}),/OWNER_BUSY/);assert.throws(()=>c.check('wrong'),/OWNER_REQUIRED/);assert.ok(!JSON.stringify(c.state()).includes('token'));
 now=90;c.renew(a.token);now=110;c.check(a.token);now=200;assert.throws(()=>c.check(a.token),/OWNER_EXPIRED/);
 const b=c.claim({name:'B'});c.release(b.token,'Check the draft',{case_id:'x'});assert.equal(c.state().handoff.summary,'Check the draft');assert.throws(()=>c.check(),/OWNER_EXPIRED/);
 c.reset();assert.doesNotThrow(()=>c.check());assert.throws(()=>c.check(b.token),/OWNER_EXPIRED/);
});
test('handoff is bounded and invalid writes preserve owner',()=>{
 const c=coordinator({uuid:()=> 'token'});const a=c.claim({name:'A'});assert.throws(()=>c.release(a.token,'x'.repeat(2001)),/INVALID_HANDOFF/);c.check(a.token);
 assert.throws(()=>c.claim({name:''}),/INVALID_OWNER/);assert.throws(()=>diff({}, {}, {limit:0}),/INVALID_LIMIT/);
});
test('three recipes available in all interface languages',()=>{
 for(const lang of ['ko','en','ja'])for(const name of ['observe','review','handoff'])assert.ok(prompts[lang][name].length>80);
});
