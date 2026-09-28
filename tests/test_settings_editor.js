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

test('short frame target separates checkpoint interval from result interval',()=>{
 const original=immersion();original._studio={termination:{mode:'frames',frames:3,include_initial:false}};
 const c=editor.applyTermination(original);editor.validate(c);assert.equal(c.run.end_time_s,.03);assert.equal(c.run.write_interval_s,.5);
 c.run.viz_interval_s=1;assert.throws(()=>editor.validate(c),/결과 프레임/);
});

test('search uses displayed names, group names, spacing and raw keys',()=>{
 const c=immersion();
 for(const q of ['결과 프레임 저장 간격','결과프레임저장간격','VIZ_INTERVAL_S'])assert.ok(editor.searchFields(c,q).some(x=>x.path.join('.')==='run.viz_interval_s'),q);
 assert.ok(editor.searchFields(c,'복구 데이터 저장 간격').some(x=>x.path.join('.')==='run.write_interval_s'));
 assert.ok(editor.searchFields(c,'냉각 코일').some(x=>x.path[0]==='coil'));
 assert.ok(editor.searchFields(c,'냉각 코일 온도').some(x=>x.path.join('.')==='coil.Ta_C'));
 assert.ok(editor.searchFields(c,'발열').some(x=>x.path.join('.')==='heater.total_W'));
 assert.deepEqual(editor.searchFields(c,'없는검색어'),[]);
});
test('search keeps output selection as checkboxes including unselected choices',()=>{
 const c=immersion();c.run.output_fields=['therm'];
 for(const q of ['출력 항목','유속','압력'])assert.ok(editor.searchFields(c,q).some(x=>x.path.join('.')==='run.output_fields'&&Array.isArray(x.value)));
});
test('search excludes reference and internal metadata and preserves input',()=>{
 const c=immersion();c.provenance={source:'secretref'};c._studio={termination:{mode:'time',time_s:2},goals:'비교'};
 const before=JSON.stringify(c);
 assert.equal(editor.searchFields(c,'secretref').length,0);
 assert.equal(editor.searchFields(c,'end_time_s',{managed:true}).length,0);
 assert.ok(editor.searchFields(c,'end_time_s',{managed:true,readonly:true}).length);
 assert.ok(editor.searchTermination(c,'종료시간'));assert.ok(editor.searchTermination(c,'목표값'));
 assert.equal(JSON.stringify(c),before);
});
test('search matches labels supplied by the existing UI definitions',()=>{
 global.CBDEF=[['heater','','',[['total_W','히터 전력','W']]]];
 try{assert.ok(editor.searchFields(immersion(),'히터 전력').some(x=>x.path.join('.')==='heater.total_W'));}finally{delete global.CBDEF;}
});

test('Config parts cover each input exactly once and retain the original values',()=>{
 const fs=require('node:fs'),path=require('node:path');const editor=require('../cfd_studio/config_editor.js');
 for(const name of ['immersion','grain_silo']){
  const c=JSON.parse(fs.readFileSync(path.join(__dirname,'../cfd_studio/configs/'+name+'.json'),'utf8')),before=JSON.stringify(c),parts=editor.configParts(c),keys=parts.flatMap(p=>p.keys);
  assert.equal(new Set(keys).size,keys.length);assert.ok(parts.some(p=>p.title==='형상·격자'));assert.ok(parts.some(p=>p.title==='솔버·계산'));assert.ok(keys.includes('run'));assert.equal(JSON.stringify(c),before);
 }
});
