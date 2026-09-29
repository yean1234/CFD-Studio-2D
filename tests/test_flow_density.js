const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../cfd_studio/app.py'),'utf8');
const code=source.slice(source.indexOf('function viewerFlowBudget(){'),source.indexOf('function drawArrows(M){'));
function context(){const select={value:'6000'},ctx={document:{getElementById:id=>id==='flowDensity'?select:null},isSiloConfig:()=>false,VIZCFG:{},CFG:{},arrN:0,lastArrF:null,lastArrBudget:0,arrSeeds:[],arrScale:.15,arrBuf:{},gl:{bindBuffer(){},bufferData(_,data){ctx.upload=data;}}};vm.createContext(ctx);vm.runInContext(code,ctx);return {ctx,select};}
test('density samples stay within their budget, cover thin domains and preserve stored data',()=>{
 const {ctx}=context();
 for(const dims of [[44,80,7],[1,300,2],[10,10,10],[120,80,50]]){
  const F={nx:dims[0],ny:dims[1],nz:dims[2],bb:[0,0,0,.44,.8,.07]},before=JSON.stringify(F);let previous=0;
  for(const budget of [1500,6000,18000]){const samples=ctx.flowGridSamples(F,budget);assert.ok(samples.length<=budget);assert.ok(samples.length>=previous);previous=samples.length;assert.equal(new Set(samples.map(p=>p.join(','))).size,samples.length);for(const p of samples)p.forEach((n,k)=>assert.ok(Number.isInteger(n)&&n>=0&&n<dims[k]));}
  assert.equal(JSON.stringify(F),before);
 }
 const F={nx:10,ny:10,nz:10,bb:[0,0,0,1,1,1]};assert.equal(ctx.flowGridSamples(F,18000).length,1000);
});
test('changing density rebuilds arrows for the same paused frame without modifying velocities',()=>{
 const {ctx,select}=context(),F={nx:44,ny:80,nz:7,bb:[0,0,0,.44,.8,.07],u:new Float32Array(44*80*7*3).fill(.1)},before=F.u.slice();
 select.value='1500';ctx.buildArrows(F);const low=ctx.arrN,upload=ctx.upload;ctx.buildArrows(F);assert.equal(ctx.upload,upload);
 select.value='18000';ctx.buildArrows(F);assert.ok(ctx.arrN>low);assert.notEqual(ctx.upload,upload);assert.deepEqual(F.u,before);
 select.value='invalid';assert.equal(ctx.viewerFlowBudget(),6000);
});
