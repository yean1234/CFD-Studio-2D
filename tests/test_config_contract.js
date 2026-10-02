const {test}=require('node:test'),assert=require('node:assert/strict');
const contract=require('../cfd_studio/internal/config_contract.js'),editor=require('../cfd_studio/internal/form_config_editor.js');
const fails=(fn,code)=>assert.throws(fn,e=>e.code===code);
test('coded diagnostics provide three languages, actions and stable paths',()=>{
 for(const [code,row] of Object.entries(contract.catalog)){assert.equal(row.code,code);for(const lang of ['ko','en','ja']){const info=contract.normalize(contract.issue(code,'detail',['geometry',0]),lang);assert.ok(info.message&&info.action);assert.deepEqual(info.path,['geometry',0]);assert.equal(info.code,code);}}
 assert.equal(contract.normalize(new SyntaxError('bad')).code,'CFG-J001');assert.equal(contract.normalize(Error('unexpected')).code,'APP-X001');
});
test('state-free elements retain common choices and solver-specific options are filtered',()=>{
 const keys=p=>p.catalog.map(x=>x.key);
 assert.ok(keys(editor.materialProfile({},{})).includes('density'));
 assert.ok(keys(editor.materialProfile({},{})).includes('reference_note'));
 assert.ok(!keys(editor.materialProfile({},{})).includes('initial_velocity'));
 const c={analysis:{solver:'icoFoam'}};const gas=editor.materialProfile(c,{material_state:'gas'});
 assert.ok(keys(gas).includes('initial_velocity'));assert.ok(!keys(gas).includes('convection'));
 const solid=editor.materialProfile({analysis:{solver:'chtMultiRegionFoam'}},{material_state:'solid'});
 assert.ok(keys(solid).includes('temperature_property_table'));assert.ok(!keys(solid).includes('initial_velocity'));
 const turbulent=editor.materialProfile({analysis:{solver:'simpleFoam'},physics:{flow_regime:'RANS'}},{material_state:'gas'});
 assert.ok(keys(turbulent).includes('turbulent_kinetic_energy'));assert.ok(!keys(gas).includes('turbulent_kinetic_energy'));
 assert.ok(solid.catalog.every(p=>p.category));
});
test('catalog creates empty structured properties and retains semantics across raw JSON',()=>{
 for(const key of ['initial_velocity','convection','temperature_property_table','temperature_samples']){
  const item=editor.materialCatalog.find(x=>x.key===key),schema={version:1,fields:[editor.propertyDefinition(item)]},config=editor.toConfig(schema);
  assert.equal(config[key].type,item.type);const reopened=editor.fromConfig(config),value=reopened.fields[0].fields.find(f=>f.key==='value');
  if(item.widget)assert.equal(value.widget,item.widget);if(item.items)assert.deepEqual(value.items,item.items);
  assert.deepEqual(editor.toConfig(reopened),config);
 }
});
test('typed empty object arrays generate rows from items and roundtrip metadata',()=>{
 const schema={version:1,fields:[{key:'sensors',type:'array',value:[],items:{type:'object',fields:[{key:'name',type:'string',value:''},{key:'position',type:'array',widget:'vector3',value:[null,null,null],unit:'m'}]}}]};
 assert.deepEqual(contract.blankItem(schema.fields[0].items),{name:'',position:[null,null,null]});
 const copy=editor.importedSchema({config:{sensors:[{name:'A',position:[1,2,3]}]},config_schema:schema});assert.deepEqual(copy.fields[0].items,schema.fields[0].items);
 fails(()=>editor.importedSchema({config:{sensors:[{name:'A',position:['bad',2,3]}]},config_schema:schema}),'CFG-U004');
});
test('malformed custom definitions fail predictably without mutating baseline',()=>{
 const schema=editor.fromConfig({value:1});const before=structuredClone(schema);
 const change=patch=>({version:1,fields:[{...schema.fields[0],...patch}]});
 fails(()=>editor.toConfig(change({widget:'html'})),'CFG-U004');
 fails(()=>editor.toConfig(change({type:'array',value:[],items:{type:'unknown'}})),'CFG-J003');
 fails(()=>editor.toConfig(change({minimum:2,maximum:1})),'CFG-J003');
 fails(()=>editor.toConfig(change({enum:{}})),'CFG-J003');
 fails(()=>editor.toConfig(change({enum:[Infinity]})),'CFG-J003');
 fails(()=>editor.importedSchema({format:'cfd-studio-config',version:2,config:{},config_schema:schema}),'CFG-J003');
 fails(()=>editor.toConfig({version:1,fields:[schema.fields[0],schema.fields[0]]}),'CFG-J005');
 assert.deepEqual(schema,before);
});
test('envelope validation enforces declared bounds, options and types',()=>{
 const config={gain:1,mode:'a',fields:['U']},schema=editor.fromConfig(config);
 Object.assign(schema.fields[0],{minimum:0,maximum:2});schema.fields[1].enum=['a','b'];schema.fields[2].item_enum=['U','p'];
 const check=c=>editor.importedSchema({config:{...config,...c},config_schema:schema});
 fails(()=>check({gain:3}),'CFG-J008');fails(()=>check({mode:'unknown'}),'CFG-J010');fails(()=>check({fields:['T']}),'CFG-J010');
 assert.throws(()=>check({gain:'bad'}));assert.deepEqual(config,{gain:1,mode:'a',fields:['U']});
 assert.deepEqual(editor.toConfig(check({custom:{enabled:true}})).custom,{enabled:true});
});
test('required validation is explicit and permits unfinished drafts',()=>{
 const schema={version:1,fields:[{key:'value',type:'number',value:null,nullable:true,required:true}]};contract.validateValues({value:null},schema);
 fails(()=>contract.validateValues({value:null},schema,{required:true}),'CFG-J009');
});
test('display schema persists inside saved Config when callback stores values only',()=>{
 const config={custom:{samples:[]}},schema=editor.fromConfig(config);Object.assign(schema.fields[0].fields[0],{label:'My samples',items:{type:'object',fields:[{key:'x',type:'number',nullable:true,value:null}]}});
 const saved=editor.withDisplayMetadata(config,schema);const reopened=editor.fromConfig(saved,editor.fromConfig(config),{preferMetadata:true});
 assert.deepEqual(reopened.fields[0].fields[0].items,schema.fields[0].fields[0].items);assert.equal(reopened.fields[0].fields[0].label,'My samples');assert.ok(!config._studio);
});
test('published error dictionary matches runtime catalog',()=>{
 const published=require('../docs/config-error-codes.json');assert.equal(published.version,contract.version);assert.deepEqual(published.codes,contract.catalog);
});
test('renaming an optional property retains its input form without its catalog label',()=>{
 const item=editor.materialCatalog.find(x=>x.key==='initial_velocity'),config=editor.toConfig({version:1,fields:[editor.propertyDefinition(item)]});
 delete config.initial_velocity.catalog_key;config.initial_velocity.name='Custom vector';
 const value=editor.fromConfig(config).fields[0].fields.find(f=>f.key==='value');assert.equal(value.widget,'vector3');assert.deepEqual(value.value,[null,null,null]);
 const nullable=editor.fromConfig({custom:{name:'Switch',type:'boolean',unit:'',value:null}}).fields[0].fields.find(f=>f.key==='value');assert.equal(nullable.type,'boolean');
});
