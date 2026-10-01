const test=require('node:test'),assert=require('node:assert/strict');
const p=require('../cfd_studio/internal/viewer_presentation.js');
test('progress follows elapsed time between sparse irregular samples',()=>{
 assert.deepEqual(p.timeline([0,60,300],9.46),{value:9.46/300,time:9.46,index:0,disabled:false});
 assert.equal(p.timeline([0,60,300],150).value,.5);assert.equal(p.seek([0,60,300],.5).index,1);assert.equal(p.seek([0,60,300],.5).time,150);
 assert.equal(p.seek([10,70],.5).time,40);assert.equal(p.timeline([],0).disabled,true);assert.equal(p.timeline([20],100).disabled,true);assert.equal(p.seek([0,60],2).time,60);
});
test('range input accepts continuous progress and resets for another dataset',()=>{
 const bar={};p.sync(bar,[0,60,300],9.46);assert.equal(bar.step,'any');assert.equal(bar.max,1);assert.ok(bar.value>0);p.sync(bar,[0],0);assert.equal(bar.value,0);assert.equal(bar.disabled,true);
});
test('the same field has the same renderer and units across adapters',()=>{
 for(const format of ['warehouse','immersion','grain_silo']){const v=p.layers(format).find(f=>f.id==='velocity');assert.equal(v.renderer,'vectors');assert.equal(v.unit,'m/s');}
 assert.equal(p.field('pressure').unit,'m²/s²');assert.equal(p.field('pressure',{unit:'Pa'}).unit,'Pa');assert.equal(p.field('not-defined'),null);
 assert.equal(p.layers('warehouse',['concentration']).find(f=>f.id==='velocity').available,false);
 const a=p.field('temperature');a.label='changed';assert.equal(p.field('temperature').label,'온도장');
});
test('field data and ranges use explicit payload keys without altering source',()=>{
 const f={concentration:[0,1],minimum:0,maximum:1,temperature_field_C:[20,30],temperature_range_C:[20,30]};
 assert.equal(p.values(f,'concentration'),f.concentration);assert.deepEqual(p.range(f,'temperature'),[20,30]);assert.equal(p.range({},'temperature'),null);
});
