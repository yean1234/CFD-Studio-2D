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

test('Inspector position and Scale update canonical dimensions and survive reopening',()=>{
 const {transform,transformInfo}=require('../cfd_studio/internal/spatial_editor.js');
 const c={geometry:{shape:'box',unit:'mm',min:[0,0,0],max:[2,4,6]}};const before=structuredClone(c);
 const moved=transform(c,['geometry'],'position',0,5);assert.deepEqual(moved.geometry.min,[4,0,0]);assert.deepEqual(moved.geometry.max,[6,4,6]);assert.deepEqual(c,before);
 const scaled=transform(moved,['geometry'],'scale',1,2);assert.equal(transformInfo(scaled,['geometry']).scale[1],2);assert.deepEqual(scaled.geometry.min,[4,-2,0]);assert.deepEqual(scaled.geometry.max,[6,6,6]);
 assert.equal(transformInfo(transform(scaled,['geometry'],'scale',1,1),['geometry']).size[1],4);
 assert.throws(()=>transform(c,['geometry'],'scale',0,0));
});
test('sphere and cylinder radial scaling preserves supported primitives',()=>{
 const {transform}=require('../cfd_studio/internal/spatial_editor.js');
 const sphere={geometry:{shape:'sphere',unit:'m',center:[0,0,0],radius:2}};
 assert.equal(transform(sphere,['geometry'],'scale',2,3).geometry.radius,6);
 const cylinder={geometry:{shape:'cylinder',unit:'m',center:[0,0,0],radius:2,height:8,axis:'y'}};
 const scaled=transform(cylinder,['geometry'],'scale',0,2);assert.equal(scaled.geometry.radius,4);assert.equal(scaled.geometry.height,8);
});
test('legacy constrained parts cannot be moved independently and originals remain intact',()=>{
 const {transform,transformInfo}=require('../cfd_studio/internal/spatial_editor.js');
 const c={tank:{width_mm:100,depth_mm:50,liquid_height_mm:80},layers:{dielectric_mm:40},water:{},board:{x0:0,x1:5,y0:0,y1:6,z0:0,z1:2}};
 assert.throws(()=>transform(c,['water'],'position',0,1));assert.throws(()=>transform(c,['tank'],'scale',1,.1));
 assert.equal(transform(c,['board'],'position',2,10).board.z0,9);assert.deepEqual(transformInfo(c,['water']).size,[100,40,50]);
});

test('primitive JSON explicitly describes old boxes without touching source Config',()=>{
 const {primitiveDefinition,applyPrimitive,shapes}=require('../cfd_studio/internal/spatial_editor.js');
 const c={tank:{name:'tank',_설명:'User note',width_mm:456,depth_mm:70,liquid_height_mm:800},materials:{rho:1000}},before=structuredClone(c);
 const g=primitiveDefinition(c,['tank']);assert.deepEqual(g,{name:'tank',shape:'box',unit:'mm',min:[0,0,0],max:[456,800,70]});assert.deepEqual(c,before);
 const next=applyPrimitive(c,['tank'],{...g,max:[500,900,80]});assert.equal(next.tank.liquid_height_mm,900);assert.equal(next.tank._설명,'User note');assert.deepEqual(shapes(next).items[0].max,[.5,.9,.08]);assert.deepEqual(c,before);
 const sphere=applyPrimitive(c,['tank'],{name:'tank',shape:'sphere',unit:'m',center:[0,0,0],radius:2});assert.equal(shapes(sphere).items[0].kind,'sphere');assert.equal(sphere.tank.width_mm,456);
});
test('primitive geometry does not infer a shape from its user-defined name',()=>{
 const {primitiveDefinition,shapes,validatePrimitive}=require('../cfd_studio/internal/spatial_editor.js');
 const c={geometry:{regions:[{name:'tank',width_mm:456,depth_mm:70,liquid_height_mm:800}]}};
 assert.equal(primitiveDefinition(c,['geometry','regions',0]),null);assert.equal(shapes(c).items.length,0);
 for(const bad of [{name:'x',shape:'box',unit:'mm',min:[0,0,0],max:[1,2,3],liquid_height_mm:3},{name:'x',shape:'cylinder',unit:'m',center:[0,0,0],radius:1,height:2,axis:'q'},{name:'x',unit:'m',min:[0,0,0],max:[1,2,3]}])assert.throws(()=>validatePrimitive(bad));
});

test('legacy vapour and phase change belong to the runner dielectric region only',()=>{
 const s=require('../cfd_studio/internal/spatial_editor.js');const config={tank:{},layers:{},dielectric_fluid:{},water:{},vapour:{rho:1},phase_change:{evap_C:4}};
 assert.ok(s.partBindings(config,['dielectric_fluid']).some(p=>p.join('.')==='vapour'));
 assert.ok(s.partBindings(config,['dielectric_fluid']).some(p=>p.join('.')==='phase_change'));
 assert.ok(!s.partBindings(config,['water']).some(p=>['vapour','phase_change'].includes(p[0])));
 assert.ok(!s.partBindings({geometry:{regions:[{material_state:'liquid'}]},vapour:{}},['geometry','regions',0]).some(p=>p[0]==='vapour'));
});

test('fill definitions derive fluid shape from explicit interior with units and retain source',()=>{
 const s=require('../cfd_studio/internal/spatial_editor.js');const c={geometry:{regions:[{name:'Housing',material_state:'solid',shape:'box',unit:'m',min:[0,0,0],max:[2,3,2],interior:{shape:'box',unit:'m',min:[.1,.2,.1],max:[1.9,2.8,1.9]}},{name:'Liquid',material_state:'liquid'}]}};
 const original=structuredClone(c),fill={container_path:['geometry','regions',0],axis:'y',start:100,end:1600,unit:'mm'},result=s.applyFill(c,['geometry','regions',1],fill);
 assert.deepEqual(result.geometry.regions[1].max,[1.9,1.8,1.9]);assert.ok(Math.abs(result.geometry.regions[1].min[1]-.3)<1e-9);assert.deepEqual(c,original);assert.equal(s.shapes(result).items.length,2);
 assert.throws(()=>s.applyFill(c,['geometry','regions',1],{...fill,end:9000}),/범위/);delete c.geometry.regions[0].interior;assert.throws(()=>s.applyFill(c,['geometry','regions',1],fill),/내부 공간/);
});
test('cylinder fill follows its axis and legacy two-layer edits remain compatible',()=>{
 const s=require('../cfd_studio/internal/spatial_editor.js');const c={domain:{name:'Space',shape:'cylinder',unit:'m',center:[0,0,2],radius:1,height:4,axis:'z'},regions:[{name:'Gas'}]};
 const f={container_path:['domain'],axis:'z',start:1,end:3,unit:'m'},r=s.applyFill(c,['regions',0],f);assert.equal(r.regions[0].height,2);assert.deepEqual(r.regions[0].center,[0,0,2]);assert.throws(()=>s.applyFill(c,['regions',0],{...f,axis:'x'}),/중심축/);
 const old={tank:{width_mm:100,depth_mm:50,liquid_height_mm:200},layers:{dielectric_mm:80},dielectric_fluid:{name:'Fluid A'},water:{name:'Fluid B'}};
 const updated=s.applyFill(old,['water'],{container_path:['tank'],axis:'y',start:120,end:200,unit:'mm'});assert.equal(updated.layers.dielectric_mm,120);assert.equal(updated.dielectric_fluid.fill.end,120);assert.equal(updated.water.min[1],120);assert.equal(old.layers.dielectric_mm,80);
 assert.throws(()=>s.applyFill(old,['dielectric_fluid'],{container_path:['tank'],axis:'y',start:10,end:100,unit:'mm'}),/두 유체층/);
});
test('local mesh definitions require bounded boxes with finer positive spacing',()=>{
 const s=require('../cfd_studio/internal/spatial_editor.js');const c={tank:{width_mm:100,liquid_height_mm:100,depth_mm:100},mesh:{dx_mm:10,refinement_regions:[{name:'A',shape:'box',unit:'mm',min:[0,0,0],max:[50,50,50],cell_size:{value:5,unit:'mm'}}]}};
 s.validateRefinements(c);c.mesh.refinement_regions[0].cell_size.value=10;assert.throws(()=>s.validateRefinements(c),/기본 격자/);c.mesh.refinement_regions[0].cell_size.value=5;c.mesh.refinement_regions[0].max[0]=101;assert.throws(()=>s.validateRefinements(c),/계산 영역/);
});
test('fill rejects overlap, invalid interior and self-reference without rewriting inputs',()=>{
 const s=require('../cfd_studio/internal/spatial_editor.js');let c={domain:{name:'Space',shape:'box',unit:'m',min:[0,0,0],max:[1,3,1]},regions:[{name:'A'},{name:'B'}]};
 c=s.applyFill(c,['regions',0],{container_path:['domain'],axis:'y',start:0,end:2,unit:'m'});const before=structuredClone(c);
 assert.throws(()=>s.applyFill(c,['regions',1],{container_path:['domain'],axis:'y',start:1,end:3,unit:'m'}),/겹칩니다/);assert.deepEqual(c,before);
 assert.throws(()=>s.applyFill(c,['domain'],{container_path:['domain'],axis:'y',start:0,end:2,unit:'m'}),/자기 자신/);
 c.domain.material_state='solid';c.domain.interior={shape:'box',unit:'m',min:[0,0,0],max:[2,3,1]};assert.throws(()=>s.fillSpace(c,['domain']),/외곽/);
});

test('refinement targets track shapes, guard deletion and reindex remaining references',()=>{
 const sp=require('../cfd_studio/internal/spatial_editor.js');
 const c={tank:{width_mm:100,liquid_height_mm:100,depth_mm:100},regions:[{name:'A',shape:'box',unit:'mm',min:[1,1,1],max:[10,10,10]},{name:'B',shape:'box',unit:'mm',min:[20,20,20],max:[30,30,30]}],mesh:{dx_mm:10,refinement_regions:[{target_path:['regions',1],cell_size:{value:2,unit:'mm'}}]}};
 const before=structuredClone(c);sp.validateRefinements(c);assert.deepEqual(c,before);assert.deepEqual(sp.refinementBox(c,c.mesh.refinement_regions[0]).min,[20,20,20]);
 assert.throws(()=>sp.removeMeshTarget(c,['regions',1]));sp.removeMeshTarget(c,['regions',0]);c.regions.splice(0,1);assert.deepEqual(c.mesh.refinement_regions[0].target_path,['regions',0]);sp.validateRefinements(c);
 c.regions[0].max[0]=110;assert.throws(()=>sp.validateRefinements(c));delete c.regions[0];assert.throws(()=>sp.validateRefinements(c));
});
test('silo refinement validates physical bounds and target-cell reference spacing',()=>{
 const sp=require('../cfd_studio/internal/spatial_editor.js'),c={_해석유형:'grain_silo',published:{storage_diameter_m:.8,total_height_m:1.4},mesh:{target_cells:4000,refinement_regions:[{name:'Band',shape:'box',unit:'m',min:[-.1,-.1,.4],max:[.1,.1,.6],cell_size:{value:.03,unit:'m'}}]}};
 sp.validateRefinements(c);c.mesh.refinement_regions[0].min=[.35,.35,.4];c.mesh.refinement_regions[0].max=[.39,.39,.6];assert.throws(()=>sp.validateRefinements(c));
});
test('component mesh controls and nonphysical regions share containment validation',()=>{
 const sp=require('../cfd_studio/internal/spatial_editor.js');
 const outer={name:'Outer',shape:'box',unit:'m',min:[0,0,0],max:[1,1,1],mesh_control:{cell_size:{value:.05,unit:'m'}}};
 const inner={name:'Inspection',material_state:'mesh_refinement',shape:'box',unit:'m',min:[.2,.2,.2],max:[.8,.8,.8],mesh_control:{cell_size:{value:.02,unit:'m'}}};
 const c={geometry:{regions:[outer]},mesh_regions:[inner],mesh:{cell_size:{value:.1,unit:'m'}}};sp.validateRefinements(c);assert.equal(sp.collectRefinements(c).length,2);assert.equal(sp.shapes(c).items.filter(x=>x.meshOnly).length,1);
 c.mesh_regions[0].mesh_control.cell_size.value=.07;assert.throws(()=>sp.validateRefinements(c),/MESH-R007/);
 c.mesh_regions[0].mesh_control.cell_size.value=.02;c.mesh_regions[0].max=[1.2,1.2,1.2];assert.throws(()=>sp.validateRefinements(c),/MESH-R006/);
 c.mesh_regions[0]=structuredClone(inner);c.mesh_regions[0].properties={density:1};assert.throws(()=>sp.validateRefinements(c),/MESH-R008/);
});
test('geometry folders retain IDs and template geometry while rejecting orphan references',()=>{
 const sp=require('../cfd_studio/internal/spatial_editor.js'),editor=require('../cfd_studio/internal/form_config_editor.js');
 const c={geometry:{regions:[{name:'A',shape:'box',unit:'m',min:[0,0,0],max:[1,1,1],editor_group:'g'}]},_studio:{geometry_groups:[{id:'g',name:'Assembly',expanded:false}]}};
 sp.validateRefinements(c);const copy=editor.toConfig(editor.blankDefinition(editor.fromConfig(c)));assert.deepEqual(copy._studio.geometry_groups,c._studio.geometry_groups);assert.equal(copy.geometry.regions[0].editor_group,'g');
 c._studio.geometry_groups=[];assert.throws(()=>sp.validateRefinements(c),/MESH-R009/);
});


test('connected silo preview uses runner height and porous extent without inventing detailed ducts',()=>{
 const {shapes}=require('../cfd_studio/internal/spatial_editor.js');
 const c={silo:{geometry_model:'equivalent_boundary_ports_v1'},published:{storage_diameter_m:.8,total_height_m:1.4,storage_height_m:1.2,grain_height_m:1}};
 const result=shapes(c);assert.equal(result.items.length,2);assert.equal(result.items[0].height,1.4);assert.equal(result.items[1].height,1);assert.equal(result.items[0].radius,.4);
 assert.throws(()=>shapes({...c,published:{...c.published,grain_height_m:2}}));
 delete c.silo.geometry_model;assert.equal(shapes(c).items.length,0);
});
