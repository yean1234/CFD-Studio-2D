const test=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');
const editor=require('../cfd_studio/config_editor.js');
const warehouse=()=>JSON.parse(fs.readFileSync('tracer_transport/warehouse_porous_convergence.json','utf8'));
const immersion=()=>{const c=JSON.parse(fs.readFileSync('cfd_studio/configs/immersion.json','utf8'));c.run.output_fields=['flow','therm'];return c;};
test('warehouse and immersion settings preserve complete original schema',()=>{for(const c of [warehouse(),immersion()]){const before=JSON.stringify(c);editor.validate(c);assert.equal(JSON.stringify(c),before);assert.deepEqual(editor.parse(before),c);}});
test('invalid nested numeric input is rejected before saving or launching',()=>{const c=warehouse();c.coupled.nu_m2_s=null;assert.throws(()=>editor.validate(c),/nu_m2_s/);c.coupled.nu_m2_s=NaN;assert.throws(()=>editor.validate(c),/nu_m2_s/);});
test('inconsistent output timing and empty output selection are rejected',()=>{const c=warehouse();c.numerics.write_interval_s=c.numerics.end_s+1;assert.throws(()=>editor.validate(c));const i=immersion();i.run.output_fields=[];assert.throws(()=>editor.validate(i),/출력/);});
test('unsupported archive settings remain readable without becoming runnable',()=>{const c=editor.parse('{"_해석유형":"gas_transport","extra":{"source":"archived"}}');assert.equal(editor.kind(c),'unsupported');assert.equal(c.extra.source,'archived');assert.throws(()=>editor.validate(c),/조회/);});
test('import rejects arrays and prototype keys',()=>{for(const text of ['[]','null','{"__proto__":{}}','{"x":{"constructor":{}}}'])assert.throws(()=>editor.parse(text));});
