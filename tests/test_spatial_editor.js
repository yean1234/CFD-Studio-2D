const {test}=require('node:test'),assert=require('node:assert/strict');
const {parse,extract,merge,shapes}=require('../cfd_studio/internal/spatial_editor.js');
const {readFileSync}=require('node:fs');
test('spatial roundtrip preserves unrelated Config and original input',()=>{
 const c={geometry:{regions:[]},numerics:{dt:.02},materials:{rho:1000}},original=structuredClone(c);
 const subset=extract(c);subset.geometry.regions=[{shape:'box',unit:'m',min:[0,0,0],max:[1,2,3]}];
 const next=merge(c,subset);assert.deepEqual(c,original);assert.deepEqual(next.numerics,c.numerics);assert.equal(shapes(next).items.length,1);
 assert.throws(()=>merge(c,{numerics:{dt:1}}));
});
test('shape units, offsets and cylinder axes are explicit',()=>{
 const result=shapes({geometry:{fluid_regions:[{shape:'box',unit:'mm',min:[-100,0,0],max:[100,500,1000]},{shape:'sphere',unit:'cm',center:[10,20,30],radius:5},{shape:'cylinder',unit:'m',center:[2,3,4],radius:.2,height:5,axis:'x'}]}});
 assert.deepEqual(result.items[0].min,[-.1,0,0]);assert.deepEqual(result.items[0].max,[.1,.5,1]);assert.equal(result.items[1].radius,.05);assert.equal(result.items[2].axis,'x');
});
test('invalid coordinates, units and dimensions are not coerced',()=>{
 const base={shape:'box',unit:'m',min:[0,0,0],max:[1,2,3]};
 for(const change of [{unit:'ft'},{max:[0,2,3]},{min:['0',0,0]},{max:[1,2]}])assert.throws(()=>shapes({geometry:{regions:[{...base,...change}]}}));
 assert.throws(()=>shapes({domain:{shape:'sphere',unit:'m',center:[0,0,0],radius:-1}}));
 assert.throws(()=>parse('{"x":1e999}'));assert.throws(()=>parse('{"__proto__":{}}'));assert.throws(()=>parse('[]'));
});
test('existing warehouse and immersion dimensions are read without mutation',()=>{
 for(const path of ['tracer_transport/warehouse_coupled_pilot.json','cfd_studio/configs/immersion.json']){
  const c=JSON.parse(readFileSync(path)),original=structuredClone(c),r=shapes(c);
  assert.ok(r.items.length>=3);assert.deepEqual(c,original);
  if(c.tank){assert.deepEqual(r.up,[0,1,0]);assert.deepEqual(r.items[0].max,[.456,.8,.07]);}
  else{assert.equal(r.items[0].kind,'gable');assert.deepEqual(r.items[0].size,[78,25,7.2,3.5]);}
 }
});
test('blank and unsupported geometry is explicitly reported',()=>{
 assert.equal(shapes({geometry:{fluid_regions:[]}}).items.length,0);
 assert.match(shapes({geometry:{source:'mesh.stl'}}).notes.join(' '),/외부 형상/);
 const result=shapes({domain:{shape:'custom',unit:'m'}});assert.equal(result.items.length,0);assert.match(result.notes.join(' '),/지원하지 않는 shape/);
});
