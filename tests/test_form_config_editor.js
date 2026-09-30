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
