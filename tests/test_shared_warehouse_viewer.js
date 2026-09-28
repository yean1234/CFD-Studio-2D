const test=require('node:test'),assert=require('node:assert/strict');
const {warehouseBlend,warehouseBracket,warehouseCompatible,warehouseRange}=require('../cfd_studio/warehouse_viewer.js');
test('animation uses physical time between saved frames without extrapolation',()=>{assert.deepEqual(warehouseBracket([0,60,300],30),{i:0,j:1,u:.5});assert.deepEqual(warehouseBracket([0,60,300],120),{i:1,j:2,u:.25});assert.deepEqual(warehouseBracket([0,60,300],400),{i:2,j:2,u:0});assert.equal(warehouseBlend(2,8,.25),3.5);assert.equal(warehouseBlend(2,8,-1),2);assert.equal(warehouseBlend(2,8,2),8);});
test('animation does not mutate saved fields or confuse scalar ranges',()=>{const a={minimum:0,maximum:2,temperature_range_C:[20,24]},b={minimum:1,maximum:5,temperature_range_C:[19,25]};const source=JSON.stringify([a,b]);assert.deepEqual(warehouseRange(a,b,'concentration'),[0,5]);assert.deepEqual(warehouseRange(a,b,'temperature'),[19,25]);assert.equal(JSON.stringify([a,b]),source);});
test('interpolation refuses different coordinates or sampling',()=>{const a={total_cells:4,sampling_stride:2,cell_centres_m:[[0,0,0],[1,1,1]]};assert.ok(warehouseCompatible(a,structuredClone(a)));assert.ok(!warehouseCompatible(a,{...a,sampling_stride:1}));assert.ok(!warehouseCompatible(a,{...a,cell_centres_m:[[1,1,1],[0,0,0]]}));});

// Exercise the production transition with rendering delayed until after metadata arrives.
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const workspace=fs.readFileSync(path.join(__dirname,'../cfd_studio/execution_workspace.js'),'utf8');
const transition=workspace.slice(workspace.indexOf('  async function viewResult(){'),workspace.indexOf('  function inspectSettings(){'));
function transitionContext(detail){
 const calls=[];
 const ctx={detail,generation:1,viewMode:'cfd',VIZCFG:{_해석유형:'warehouse'},VPROJ:null,
  document:{body:{classList:{add(){},toggle(){}}}},setPlay(){},cancelViewerLoad(){},
  restoreWarehouseUI(){calls.push('restore');},message(t){calls.push(t);},showList(){ctx.viewMode='cfd';},
  setMode(m){assert.equal(ctx.VIZCFG,ctx.detail.config,'selected config must be available before geometry is rendered');calls.push(m);},
  async selVz(rid){calls.push(rid);}};
 vm.createContext(ctx);vm.runInContext(transition,ctx);return {ctx,calls};
}
test('warehouse to legacy transition prepares the selected model before rendering',async()=>{
 for(const config of [{_해석유형:'gas_transport',tracer:{}},{tank:{},layers:{}}]){
  const {ctx,calls}=transitionContext({has_results:true,kind:'legacy',rid:'saved-run',config});
  await ctx.viewResult();assert.deepEqual(calls,['restore','viz','saved-run']);assert.equal(ctx.VPROJ,'saved-run');
 }
});
test('Viewer requested while run detail is loading stays pending for automatic entry',async()=>{
 const {ctx,calls}=transitionContext(null);await ctx.viewResult();assert.equal(ctx.viewMode,'viewer');assert.equal(calls.length,1);
});
