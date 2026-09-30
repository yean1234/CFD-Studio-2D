const test=require('node:test'),assert=require('node:assert/strict');
const ui=require('../cfd_studio/internal/i18n.js');
test('all registered messages have English and Japanese text',()=>{
 assert.ok(Object.keys(ui.messages).length>400);
 for(const [key,values] of Object.entries(ui.messages)){assert.equal(values.length,2);for(const v of values)assert.ok(typeof v==='string'&&v.trim(),key);}
});
test('source strings and unknown solver identifiers are preserved',()=>{
 for(const s of ['저장','icoFoam','transportProperties','U','m/s','ClO₂','input.custom']){assert.equal(ui.translate(s,'ko'),s);}
 for(const lang of ['en','ja'])for(const s of ['icoFoam','input.custom','m/s'])assert.equal(ui.translate(s,lang),s);
});
test('labels, units, whitespace and dynamic counts translate',()=>{
 assert.equal(ui.translate('  저장  ','en'),'  Save  ');
 assert.equal(ui.translate('Config 3개 변경','ja'),'Config変更 3件');
 assert.equal(ui.translate('온도 (°C)','en'),'Temperature (°C)');
 assert.equal(ui.translate('7 프레임 · 초기 제외','en'),'7 frames · Initial excluded');
 assert.equal(ui.translate('1. 유체','ja'),'1. 流体');
});
test('separator-only strings cannot recurse',()=>{
 for(const s of ['',' ', ' · ','\n'])assert.equal(ui.translate(s,'en'),s);
 assert.equal(ui.translate('유속 · 온도','en'),'Velocity · Temperature');
});
test('settings search recognizes current translated labels without modifying Config',()=>{
 const editor=require('../cfd_studio/internal/config_editor.js');const c={tank:{},dielectric_fluid:{},run:{end_time_s:2,viz_interval_s:.1}};const before=JSON.stringify(c);
 const old=globalThis.CFDI18n;
 try{for(const lang of ['en','ja']){globalThis.CFDI18n={translate:s=>ui.translate(s,lang)};assert.ok(editor.searchFields(c,ui.translate('결과 프레임 저장 간격',lang)).some(f=>f.path.join('.')==='run.viz_interval_s'));}}finally{globalThis.CFDI18n=old;}
 assert.equal(JSON.stringify(c),before);
});
