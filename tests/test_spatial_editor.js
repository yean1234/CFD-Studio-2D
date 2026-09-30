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

test('element selection uses exact paths, including punctuated user names',()=>{
 const c={geometry:{regions:{'a.b':{name:'User <name>',shape:'box',unit:'m',min:[0,0,0],max:[1,1,1]}}}};
 const {elements,at}=require('../cfd_studio/internal/spatial_editor.js'),e=elements(c)[0];
 assert.deepEqual(e.path,['geometry','regions','a.b']);assert.equal(at(c,e.path).name,'User <name>');assert.equal(shapes(c).items[0].id,e.id);
});
test('an incomplete new element does not erase existing preview shapes',()=>{
 const c={geometry:{regions:[{name:'A',shape:'box',unit:'m',min:[0,0,0],max:[1,2,3]},{name:'B',shape:'box',unit:'m',min:[0,0,0],max:[null,null,null]}]}};
 const result=shapes(c);assert.equal(result.items.length,1);assert.match(result.notes.join(' '),/치수 미입력/);
});

test('complete spatial documents roundtrip generic and legacy Config without loss',()=>{
 const {document,mergeDocument}=require('../cfd_studio/internal/spatial_editor.js');
 const generic={geometry:{unit:'m',regions:[{name:'A',shape:'box',min:[0,0,0],max:[2,3,4],config_bindings:[['materials','fluid']]}]},mesh:{cell_size:.1},boundary_conditions:{wall:{mesh_patch:'walls'}},outputs:{fields:['U'],write_interval:1,probes:[[1,1,1]]},materials:{fluid:{density:1}},numerics:{dt:.01}};
 for(const config of [generic,...['tracer_transport/warehouse_coupled_pilot.json','cfd_studio/configs/immersion.json'].map(p=>JSON.parse(readFileSync(p)))]){
  const original=structuredClone(config),doc=document(config);
  assert.deepEqual(mergeDocument(config,doc),config);assert.deepEqual(config,original);
  if(config.geometry_spec){assert.deepEqual(doc.sections.geometry.geometry_spec,config.geometry_spec);assert.deepEqual(doc.sections.geometry.loading,config.loading);}
  if(config.tank){assert.deepEqual(doc.sections.geometry.heater,config.heater);assert.deepEqual(doc.sections.mesh.mesh,config.mesh);assert.deepEqual(doc.sections.observations.probes_mm,config.probes_mm);}
 }
 const doc=document(generic);doc.sections.geometry.geometry.regions[0].max[0]=5;doc.sections.observations.outputs.probes=[[2,1,1]];
 const next=mergeDocument(generic,doc);assert.equal(next.geometry.regions[0].max[0],5);assert.deepEqual(next.outputs.fields,['U']);assert.equal(next.outputs.write_interval,1);assert.deepEqual(next.materials,generic.materials);assert.equal(generic.geometry.regions[0].max[0],2);
});
test('spatial document rejects missing sections, misplaced keys and destructive omissions',()=>{
 const {document,mergeDocument}=require('../cfd_studio/internal/spatial_editor.js');
 const c={geometry:{regions:[]},outputs:{probes:[],fields:['T']}};
 for(const mutate of [d=>delete d.sections.mesh,d=>delete d.sections.geometry.geometry,d=>d.sections.geometry.materials={},d=>d.sections.observations.outputs.fields=['p'],d=>d.version=2]){
  const d=document(c);mutate(d);assert.throws(()=>mergeDocument(c,d));
 }
 const d=document({});assert.deepEqual(d.sections.geometry,{});assert.deepEqual(mergeDocument({},d),{});
 d.sections.geometry.geometry={unit:'m',regions:[]};assert.deepEqual(mergeDocument({},d),{geometry:{unit:'m',regions:[]}});
});

test('legacy liquid regions use stored layer geometry and original material paths',()=>{
 const sp=require('../cfd_studio/internal/spatial_editor.js');const c=JSON.parse(readFileSync('cfd_studio/configs/immersion.json')),before=structuredClone(c);
 const model=sp.shapes(c),lower=model.items.find(x=>x.name==='dielectric_fluid'),upper=model.items.find(x=>x.name==='water');
 assert.deepEqual(lower.min,[0,0,0]);assert.equal(lower.max[1],c.layers.dielectric_mm*.001);assert.equal(upper.min[1],lower.max[1]);assert.equal(upper.max[1],c.tank.liquid_height_mm*.001);
 assert.equal(sp.elements(c).find(x=>x.path[0]==='water').label,c.water.name);
 assert.ok(sp.partBindings(c,['water']).some(p=>p.join('.')==='layers.init_T_water_C'));assert.deepEqual(c,before);
 c.layers.dielectric_mm=c.tank.liquid_height_mm+1;assert.throws(()=>sp.shapes(c));
});
