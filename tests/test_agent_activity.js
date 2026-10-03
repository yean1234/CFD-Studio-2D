const test=require('node:test'),assert=require('node:assert/strict');
const {client,presentation}=require('../cfd_studio/internal/agent_activity.js');
const snapshot=(revision=1)=>({server:'server',revision,paused:false,task:{id:'a',mode:'development',stage:'debug',status:'debug',detail:'Checking inputs'},history:[]});
const reply=value=>({ok:true,json:async()=>value});

test('development progress cannot be mistaken for a CFD result',()=>{
 const view=presentation(snapshot());
 assert.equal(view.mode,'개발 작업');assert.equal(view.title,'코드 수정');
 assert.equal(view.detail,'Checking inputs');assert.equal(view.shown,true);
 assert.equal(presentation(snapshot(),false).title,'작업 상태 연결 끊김');
 assert.equal(presentation({...snapshot(),paused:true}).title,'에이전트 일시정지');
 assert.equal(presentation(null).shown,false);
});
test('hidden tabs never acknowledge visible progress',async()=>{
 const calls=[];
 const bridge=client({fetch:async(url,options)=>{calls.push(options);return reply(snapshot());},tab:'tab',visible:()=>false});
 await bridge.refresh();assert.equal(calls.length,1);assert.equal(bridge.snapshot().available,true);
});
test('visible tabs acknowledge the exact rendered revision',async()=>{
 const calls=[];
 const bridge=client({fetch:async(url,options)=>{calls.push(options);return reply(snapshot());},tab:'tab'});
 await bridge.refresh();assert.equal(calls.length,2);
 assert.deepEqual(JSON.parse(calls[1].body),{action:'seen',tab:'tab',revision:1});
});
test('older response cannot clear a user pause',async()=>{
 const responses=[snapshot(1),{...snapshot(3),paused:true},snapshot(2)];
 const bridge=client({fetch:async()=>reply(responses.shift()),tab:'tab',visible:()=>false});
 await bridge.refresh();await bridge.stop();await bridge.refresh();
 assert.equal(bridge.snapshot().paused,true);assert.equal(bridge.snapshot().state.revision,3);
});
test('loss of connection preserves the last task with disconnected status',async()=>{
 let fail=false;
 const bridge=client({fetch:async()=>{if(fail)throw Error('offline');return reply(snapshot());},tab:'tab',visible:()=>false});
 await bridge.refresh();fail=true;await bridge.refresh();
 assert.equal(bridge.snapshot().available,false);assert.equal(bridge.snapshot().detail,'Checking inputs');
 assert.equal(bridge.snapshot().title,'작업 상태 연결 끊김');
});
test('server restart permits revision reset without keeping the previous task',async()=>{
 const responses=[snapshot(15),{server:'new',revision:0,task:null,paused:false}];
 const bridge=client({fetch:async()=>reply(responses.shift()),tab:'tab',visible:()=>false});
 await bridge.refresh();await bridge.refresh();assert.equal(bridge.snapshot().shown,false);
});

test('stop and terminal states hide controls without clearing pause',()=>{
 const value=snapshot();
 assert.equal(presentation({...value,paused:true}).shown,false);
 for(const stage of ['completed','failed'])assert.equal(presentation({...value,task:{...value.task,stage,status:stage}}).shown,false);
 assert.equal(presentation({...value,paused:true}).paused,true);
});
test('activation keeps ownership token private and finish uses that owner',async()=>{
 const calls=[];
 const bridge=client({fetch:async(url,options)=>{calls.push(JSON.parse(options.body));return reply({...snapshot(),token:'owner'});},tab:'tab'});
 await bridge.activate({task:'Review'});
 assert.equal(bridge.snapshot().state.token,undefined);
 await bridge.finish();assert.equal(calls[1].token,'owner');
});
