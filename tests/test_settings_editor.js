const test=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');
const editor=require('../cfd_studio/config_editor.js');
const warehouse=()=>JSON.parse(fs.readFileSync('tracer_transport/warehouse_porous_convergence.json','utf8'));
const immersion=()=>{const c=JSON.parse(fs.readFileSync('cfd_studio/configs/immersion.json','utf8'));c.run.output_fields=['flow','therm'];return c;};
test('warehouse and immersion settings preserve complete original schema',()=>{for(const c of [warehouse(),immersion()]){const before=JSON.stringify(c);editor.validate(c);assert.equal(JSON.stringify(c),before);assert.deepEqual(editor.parse(before),c);}});
test('invalid nested numeric input is rejected before saving or launching',()=>{const c=warehouse();c.coupled.nu_m2_s=null;assert.throws(()=>editor.validate(c),/nu_m2_s/);c.coupled.nu_m2_s=NaN;assert.throws(()=>editor.validate(c),/nu_m2_s/);});
test('inconsistent output timing and empty output selection are rejected',()=>{const c=warehouse();c.numerics.write_interval_s=c.numerics.end_s+1;assert.throws(()=>editor.validate(c));const i=immersion();i.run.output_fields=[];assert.throws(()=>editor.validate(i),/출력/);});
test('unsupported archive settings remain readable without becoming runnable',()=>{const c=editor.parse('{"_해석유형":"gas_transport","extra":{"source":"archived"}}');assert.equal(editor.kind(c),'unsupported');assert.equal(c.extra.source,'archived');assert.throws(()=>editor.validate(c),/조회/);});
test('import rejects arrays and prototype keys',()=>{for(const text of ['[]','null','{"__proto__":{}}','{"x":{"constructor":{}}}'])assert.throws(()=>editor.parse(text));});

test('case frame target uses each model output interval without changing the source preset',()=>{
 const {applyTermination}=require('../cfd_studio/config_editor.js');
 const original={tank:{},dielectric_fluid:{},run:{end_time_s:60,write_interval_s:.5,viz_interval_s:.01},_studio:{termination:{mode:'frames',frames:101,include_initial:true}}};
 const actual=applyTermination(original);
 assert.equal(actual.run.end_time_s,1);assert.equal(original.run.end_time_s,60);assert.equal(actual.run.write_interval_s,.5);
 assert.throws(()=>applyTermination({...original,_studio:{termination:{mode:'convergence'}}}),/수렴/);
});

test('reference metadata is collected separately without changing solver inputs',()=>{
 const {references}=require('../cfd_studio/config_editor.js');
 const config={numerics:{dt_s:.1},provenance:{paper:'record'},coupled:{basis:'assumption',rho_kg_m3:1.2},loading:{blocks:[{source:'drawing',porosity:.4}]}};
 const before=JSON.stringify(config),refs=references(config);
 assert.deepEqual(refs.map(x=>x.path.join('.')),['provenance','coupled.basis','loading.blocks.0.source']);
 assert.equal(JSON.stringify(config),before);
 assert.equal(config.coupled.rho_kg_m3,1.2);
});
