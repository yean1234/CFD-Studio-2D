const test=require('node:test');const assert=require('node:assert/strict');
const {fromConfig,toConfig,newField}=require('../cfd_studio/internal/form_config_editor.js');
test('blank Config contains no assumed geometry or translated keys',()=>{assert.deepEqual(toConfig(fromConfig({})),{});assert.deepEqual(fromConfig({}).fields,[]);});
test('arbitrary nested JSON is losslessly reconstructed',()=>{const c={domain:{length:12.5,shape:'house'},enabled:false,zones:[{name:'zone A',origin:[0,2,3]}],optional:null,'user-defined key':'text'};const before=JSON.stringify(c);const schema=fromConfig(c);assert.deepEqual(toConfig(schema),c);assert.equal(JSON.stringify(c),before);assert.equal(schema.fields[0].key,'domain');});
test('units and deliberate number type survive import and reopen',()=>{const s={version:1,fields:[{key:'length',type:'number',unit:'mm',value:3}]};const again=fromConfig(toConfig(s),s);assert.equal(again.fields[0].type,'number');assert.equal(again.fields[0].unit,'mm');assert.equal(toConfig(again).length,3);});
test('duplicate and reserved keys fail instead of overwriting data',()=>{const s=fromConfig({length:1});s.fields.push({...s.fields[0],value:2});assert.throws(()=>toConfig(s),/Duplicate/);for(const key of ['__proto__','constructor','prototype'])assert.throws(()=>fromConfig(JSON.parse('{"'+key+'":1}')),/reserved/i);});
test('invalid numeric and array values fail before apply',()=>{for(const [type,value] of [['integer',1.5],['number',null],['number',Infinity],['boolean',0],['array','[]']])assert.throws(()=>toConfig({version:1,fields:[{key:'x',type,unit:'',value}]}));});
test('field addition is local and supports every JSON type',()=>{const fields=[newField([])];assert.equal(newField(fields).key,'field_2');const values={text:'abc',number:1.5,integer:1,flag:true,array:[],object:{},nil:null};assert.deepEqual(toConfig(fromConfig(values)),values);});

test('general template preserves common sections and user JSON extensions',()=>{const config=require('../cfd_studio/templates/cfd-config-template.json');assert.deepEqual(Object.keys(config),['geometry','mesh','materials','physics','initial_conditions','boundary_conditions','numerics','termination','outputs']);const copy=structuredClone(config);copy.geometry.regions=[{name:'custom',parameters:{length:2}}];copy.outputs.fields=['U','p'];assert.deepEqual(toConfig(fromConfig(copy)),copy);assert.deepEqual(config.geometry.regions,[]);assert.equal(config.numerics.time_step,null);});
test('nullable number placeholders remain editable and survive JSON roundtrip',()=>{const s={version:1,fields:[{key:'value',type:'number',unit:'m/s',nullable:true,value:null}]};const copy=fromConfig(toConfig(s),s);assert.equal(copy.fields[0].type,'number');assert.equal(copy.fields[0].nullable,true);assert.equal(copy.fields[0].unit,'m/s');copy.fields[0].value=2.5;assert.equal(toConfig(copy).value,2.5);copy.fields[0].value=null;assert.equal(toConfig(copy).value,null);copy.fields[0].nullable=false;assert.throws(()=>toConfig(copy));});

test('quantity units follow edited JSON units',()=>{const old=fromConfig({length:{value:2,unit:'m'}});const next=fromConfig({length:{value:200,unit:'cm'}},old);assert.equal(next.fields[0].fields[0].unit,'cm');});
test('required field annotations survive JSON edits without treating optional fields as required',()=>{const schema={version:1,fields:[{key:'nu',type:'number',nullable:true,value:null,unit:'m^2/s',required:true},{key:'rho',type:'number',nullable:true,value:null,required:false}]};const result=fromConfig({nu:0.000001,rho:null},schema);assert.equal(result.fields[0].required,true);assert.equal(result.fields[1].required,false);assert.equal(toConfig(result).nu,0.000001);});

test('display names survive JSON editing without changing solver keys or values',()=>{
 const schema=fromConfig({density:1.2,optional:null});schema.fields[0].label='공기 밀도';schema.fields[0].description='실험 조건의 밀도';schema.fields[1].required=false;
 const next=fromConfig({density:1.4,optional:null},schema);assert.equal(next.fields[0].label,'공기 밀도');assert.equal(next.fields[0].description,'실험 조건의 밀도');assert.deepEqual(toConfig(next),{density:1.4,optional:null});
});
test('required and conditional classification keeps boundary inputs accessible',()=>{
 const {fieldStatus}=require('../cfd_studio/internal/form_config_editor.js');
 assert.equal(fieldStatus({key:'density',type:'object',fields:[{key:'value',type:'number',required:true}]}),'required');
 assert.equal(fieldStatus({key:'value',type:'number',required:false},['boundary_conditions','inlet','fields','p']),'conditional');
 assert.equal(fieldStatus({key:'probes',type:'array',required:false}),'optional');
 assert.equal(fieldStatus({key:'algorithm',type:'string',readonly:true}),'fixed');
 assert.equal(newField([]).value,null);
});

test('Template layout survives blanking without storing operating values',()=>{
 const {blankDefinition}=require('../cfd_studio/internal/form_config_editor.js');
 const source={geometry:{regions:[{name:'A',shape:'box',unit:'m',min:[0,0,0],max:[1,2,3],config_bindings:[['materials','fluid']]}]},coil:{x0:1,x1:2,h_W_m2K:20},materials:{fluid:{density:1000}}};
 const schema=fromConfig(source),before=structuredClone(schema),blank=toConfig(blankDefinition(schema));
 assert.deepEqual(blank.geometry,source.geometry);assert.equal(blank.coil.x0,1);assert.equal(blank.coil.h_W_m2K,null);assert.equal(blank.materials.fluid.density,null);assert.deepEqual(schema,before);
 blank.geometry.regions[0].max[0]=9;assert.equal(source.geometry.regions[0].max[0],1);
});

test('JSON section edits reject wrong types and unsafe keys without changing originals',()=>{
 const {validateValueEdits}=require('../cfd_studio/internal/form_config_editor.js');
 const original={geometry:{regions:[{min:[0,0,0],max:[1,1,1]}]},enabled:true};
 const before=JSON.stringify(original),wrong=structuredClone(original);wrong.geometry.regions[0].min[0]='bad';
 assert.throws(()=>validateValueEdits(original,wrong));
 assert.throws(()=>validateValueEdits(original,JSON.parse('{"constructor":1}')));
 const valid=structuredClone(original);valid.geometry.regions[0].max[0]=2;validateValueEdits(original,valid);
 assert.equal(JSON.stringify(original),before);
});

test('part property definitions survive Template blanking while values remain project inputs',()=>{
 const {blankDefinition}=require('../cfd_studio/internal/form_config_editor.js');
 const c={geometry:{regions:[{name:'Custom part',role:'user role',shape:'sphere',unit:'m',center:[0,0,0],radius:2,properties:{voltage:{name:'Voltage',type:'number',unit:'V',value:24}}}]},coil:{x0:1,x1:2,properties:{enabled:{name:'Enable',type:'boolean',unit:'',value:true}}}};
 const schema=fromConfig(c),before=structuredClone(schema),blank=toConfig(blankDefinition(schema));
 assert.equal(blank.geometry.regions[0].radius,2);assert.equal(blank.geometry.regions[0].role,'user role');assert.deepEqual(blank.geometry.regions[0].properties.voltage,{name:'Voltage',type:'number',unit:'V',value:null});assert.equal(blank.coil.properties.enabled.value,null);assert.equal(blank.coil.properties.enabled.type,'boolean');assert.deepEqual(schema,before);
});

test('material catalog is filtered by state and documented solver capabilities',()=>{
 const {materialProfile}=require('../cfd_studio/internal/form_config_editor.js');
 const profile=(solver,state,extra={})=>materialProfile({analysis:{solver}},{material_state:state,...extra});
 const flow=profile('icoFoam','liquid');assert.ok(flow.basic.includes('kinematic_viscosity'));assert.ok(!flow.basic.includes('initial_temperature'));assert.equal(flow.phaseSupported,false);assert.ok(!flow.catalog.some(p=>p.key==='voltage'));
 const solid=profile('chtMultiRegionFoam','solid');for(const k of ['density','heat_capacity','thermal_conductivity','initial_temperature'])assert.ok(solid.basic.includes(k));assert.equal(solid.solidUnsupported,false);assert.equal(solid.phaseSupported,false);
 assert.equal(profile('interFoam','liquid').phaseSupported,false);assert.ok(!profile('interFoam','liquid').catalog.some(p=>p.key==='latent_heat'));
 const phase=profile('icoReactingMultiphaseInterFoam','liquid',{properties:{phase_change:{value:true}}});assert.ok(phase.catalog.some(p=>p.key==='latent_heat'));assert.ok(!profile('icoReactingMultiphaseInterFoam','solid').phaseSupported);
 assert.equal(profile('custom','gas').known,false);assert.ok(profile('rhoPimpleFoam','gas').catalog.some(p=>p.key==='molecular_weight'));
});
test('invalid nested list values cannot be silently converted to null',()=>{assert.throws(()=>toConfig({version:1,fields:[{key:'table',type:'array',value:[1,undefined]}]}),/JSON/);});

test('external raw, schema and exported envelope imports preserve data and metadata',()=>{
 const {importedSchema}=require('../cfd_studio/internal/form_config_editor.js');
 const source={materials:{rho:null,arbitrary:null,coefficients:{},curve:{T_K:[273,300],values:[1,2],unit:'kg/m³'}},enabled:false};
 const schema=fromConfig(source);schema.fields[1].enum=[true,false];schema.fields[1].label='Custom switch';
 const before=structuredClone(schema);
 for(const input of [source,schema,{config:source,config_schema:schema}])assert.deepEqual(toConfig(importedSchema(input)),source);
 const result=importedSchema(schema);assert.deepEqual(result.fields[1].enum,[true,false]);assert.equal(result.fields[1].label,'Custom switch');assert.equal(result.fields[0].fields[0].type,'number');assert.equal(result.fields[0].fields[1].type,'null');assert.deepEqual(schema,before);
 assert.throws(()=>importedSchema(JSON.parse('{"constructor":{}}')),/reserved/i);assert.throws(()=>importedSchema({version:1,fields:[{key:'v',type:'number',value:'bad'}]}),/Type/);
});
test('temperature-property tables are recognised semantically and mismatches rejected without mutation',()=>{
 const {tableColumns,validateTables}=require('../cfd_studio/internal/form_config_editor.js');
 const value={T_K:[273.15,300],rho:[1000,990],cp:[4000,4010]};assert.equal(tableColumns(fromConfig(value).fields).length,3);validateTables(value);
 assert.equal(tableColumns(fromConfig({coordinates:[1,2,3],values:[4,5,6]}).fields).length,0);
 const mismatch={materials:{T_K:[1,2],values:[3]}};const before=structuredClone(mismatch);assert.throws(()=>validateTables(mismatch),/행 수/);assert.deepEqual(mismatch,before);
});
test('component definitions retain model and unit metadata but not Template operating values',()=>{
 const {blankDefinition}=require('../cfd_studio/internal/form_config_editor.js');
 const config={geometry:{regions:[{name:'Liquid',shape:'box',unit:'m',min:[0,0,0],max:[1,1,1],components:{vapour:{rho:1.2,unit:'kg/m³'},phase_change:{model:'UserModel',enabled:true,coefficient:2}}}]}};
 const before=structuredClone(config),blank=toConfig(blankDefinition(fromConfig(config)));
 assert.equal(blank.geometry.regions[0].components.vapour.rho,null);assert.equal(blank.geometry.regions[0].components.vapour.unit,'kg/m³');assert.equal(blank.geometry.regions[0].components.phase_change.model,'UserModel');assert.equal(blank.geometry.regions[0].components.phase_change.enabled,null);assert.deepEqual(config,before);
});
test('JSON numbers permit decimal editing unless an integer schema was declared',()=>{
 assert.equal(fromConfig({coefficient:1}).fields[0].type,'number');
 assert.equal(fromConfig({count:2},{fields:[{key:'count',type:'integer',value:1}]}).fields[0].type,'integer');
});
