const test=require('node:test'),assert=require('node:assert/strict');
const {warehouseBlend,warehouseBracket,warehouseCompatible,warehouseRange}=require('../cfd_studio/internal/warehouse_viewer.js');
test('animation uses physical time between saved frames without extrapolation',()=>{assert.deepEqual(warehouseBracket([0,60,300],30),{i:0,j:1,u:.5});assert.deepEqual(warehouseBracket([0,60,300],120),{i:1,j:2,u:.25});assert.deepEqual(warehouseBracket([0,60,300],400),{i:2,j:2,u:0});assert.equal(warehouseBlend(2,8,.25),3.5);assert.equal(warehouseBlend(2,8,-1),2);assert.equal(warehouseBlend(2,8,2),8);});
test('animation does not mutate saved fields or confuse scalar ranges',()=>{const a={minimum:0,maximum:2,temperature_range_C:[20,24]},b={minimum:1,maximum:5,temperature_range_C:[19,25]};const source=JSON.stringify([a,b]);assert.deepEqual(warehouseRange(a,b,'concentration'),[0,5]);assert.deepEqual(warehouseRange(a,b,'temperature'),[19,25]);assert.equal(JSON.stringify([a,b]),source);});
test('interpolation refuses different coordinates or sampling',()=>{const a={total_cells:4,sampling_stride:2,cell_centres_m:[[0,0,0],[1,1,1]]};assert.ok(warehouseCompatible(a,structuredClone(a)));assert.ok(!warehouseCompatible(a,{...a,sampling_stride:1}));assert.ok(!warehouseCompatible(a,{...a,cell_centres_m:[[1,1,1],[0,0,0]]}));});

// Exercise the production transition with rendering delayed until after metadata arrives.
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const workspace=fs.readFileSync(path.join(__dirname,'../cfd_studio/internal/execution_workspace.js'),'utf8');
const transition=workspace.slice(workspace.indexOf('  async function viewResult(){'),workspace.indexOf('  function inspectSettings(){'));
function transitionContext(detail){
 const calls=[],elements=new Map();
 const ctx={$:id=>{if(!elements.has(id))elements.set(id,{});return elements.get(id);},suspendWarehouseViewer(){},detail,runId:'pending',generation:1,viewMode:'cfd',VIZCFG:{_해석유형:'warehouse'},VPROJ:null,
  DataSheetViewer:{begin(){},resume(){},loaded(){}},document:{body:{classList:{add(){},remove(){},toggle(){}}}},setPlay(){},cancelViewerLoad(){},renderSidebarAction(){},
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


test('a Case without results stays in Viewer with the same Case list',async()=>{
 const {ctx}=transitionContext({has_results:false,can_generate:false});
 let mode;ctx.setMode=value=>mode=value;
 await ctx.viewResult();
 assert.equal(ctx.viewMode,'viewer');assert.equal(mode,'viz');
 assert.equal(ctx.$('controls').inert,true);
 assert.equal(ctx.$('ewViewerEmpty').textContent,'선택한 Case의 결과가 아직 없습니다');
});

test('Viewer controls select explicit modes, retain selection on repeat click and restore project actions',()=>{
 const source=workspace.slice(workspace.indexOf('  function renderSidebarAction(){'),workspace.indexOf('  function button('));
 const controls=Object.fromEntries(['ewFindProject','ewCreateProject','ewSidebarActions'].map(id=>[id,{dataset:{},classList:{toggle(){}},attrs:{},setAttribute(k,v){this.attrs[k]=v;},removeAttribute(k){delete this.attrs[k];}}]));
 let viewer=true;
 const ctx={$:id=>controls[id],pending:false,findProject(){},createProject(){},document:{body:{classList:{contains:()=>viewer}}},DataSheetViewer:{mode:'3d',setMode(mode){this.mode=mode;}}};
 vm.createContext(ctx);vm.runInContext(source,ctx);ctx.renderSidebarAction();
 const three=controls.ewFindProject,data=controls.ewCreateProject;
 assert.equal(data.textContent,'Data Sheet');assert.equal(three.textContent,'3D Virtual');
 assert.equal(three.attrs['aria-pressed'],'true');assert.equal(data.attrs['aria-pressed'],'false');
 data.onclick();assert.equal(ctx.DataSheetViewer.mode,'data');assert.equal(data.attrs['aria-pressed'],'true');assert.equal(three.attrs['aria-pressed'],'false');
 data.onclick();assert.equal(ctx.DataSheetViewer.mode,'data');
 three.onclick();assert.equal(ctx.DataSheetViewer.mode,'3d');
 viewer=false;ctx.renderSidebarAction();assert.equal(three.textContent,'프로젝트 찾기');assert.equal(data.textContent,'새 프로젝트');
 assert.equal(data.attrs['aria-pressed'],undefined);assert.equal(three.attrs['aria-pressed'],undefined);
});

test('Viewer without any selected Case exposes the empty Viewer layout',async()=>{
 const {ctx}=transitionContext(null);ctx.runId='';let mode;ctx.setMode=v=>mode=v;
 await ctx.viewResult();assert.equal(mode,'viz');assert.equal(ctx.viewMode,'viewer');assert.equal(ctx.$('controls').inert,true);
});

test('legacy selection waits for frame reading before signaling ready',async()=>{
 const app=fs.readFileSync(path.join(__dirname,'../cfd_studio/app.py'),'utf8');
 const source=app.slice(app.indexOf('async function selVz(rid)'),app.indexOf('function openProj(rid)'));
 const labels={tlab:{textContent:'0.00s (6프레임)'},hFrTit:{textContent:'재생 프레임 · 6개'},tbar:{value:5,max:5}};
 let finish;const gate=new Promise(resolve=>finish=resolve);const ctx={document:{getElementById:id=>labels[id]},LASTPROJS:[],CURC:'',LOADED_RID:'',renderProjects(){},loadFrames:()=>gate};
 vm.createContext(ctx);vm.runInContext(source,ctx);let done=false;const selecting=ctx.selVz('result').then(()=>done=true);
 await Promise.resolve();assert.equal(done,false);assert.equal(labels.tlab.textContent,'불러오는 중');assert.equal(labels.hFrTit.textContent,'재생 프레임 · 불러오는 중');assert.equal(labels.tbar.max,0);finish();await selecting;assert.equal(done,true);
});

test('playback keys do not hijack CFD, buttons or settings',()=>{
 const app=fs.readFileSync(path.join(__dirname,'../cfd_studio/app.py'),'utf8');
 const start=app.indexOf("addEventListener('keydown',e=>{\n if(MODE"),source=app.slice(start,app.indexOf('\n});',start)+4);
 let handler,plays=0,seeks=0,dataMode=false;const ctx={document:{body:{classList:{contains:()=>dataMode}}},MODE:'cfd',FRAMES:[{},{}],idx:0,addEventListener:(_,f)=>handler=f,togglePlay:()=>plays++,scrub:()=>seeks++};
 vm.createContext(ctx);vm.runInContext(source,ctx);
 const event=(tag,code='Space')=>({target:{tagName:tag,closest:()=>null},code,key:code,preventDefault(){}});
 handler(event('DIV'));ctx.MODE='viz';for(const tag of ['BUTTON','SUMMARY','INPUT','TEXTAREA','SELECT','A'])handler(event(tag));
 assert.equal(plays,0);handler(event('DIV'));assert.equal(plays,1);handler(event('DIV','ArrowRight'));assert.equal(seeks,1);dataMode=true;handler(event('DIV'));handler(event('SVG','ArrowRight'));assert.equal(plays,1);assert.equal(seeks,1);
});

test('settings comparison distinguishes missing baseline from equality and identifies the saved basis',()=>{
 const source=workspace.slice(workspace.indexOf('  function differenceView(value){'),workspace.indexOf('  function resultText(r)'));
 const ctx={};vm.createContext(ctx);vm.runInContext(source,ctx);
 assert.equal(ctx.differenceView({}).label,'기준 없음');
 assert.equal(ctx.differenceView({differences:[]}).label,'변경 없음');
 assert.match(ctx.differenceView({differences:[]}).text,/최초 저장 설정/);
 const changed=ctx.differenceView({preset_id:'preset1',differences:[{path:'heater.total_W',before:265,after:270}]});
 assert.equal(changed.label,'1개 변경');assert.match(changed.text,/생성 당시 프리셋/);assert.match(changed.text,/265 → 270/);
});

test('horizontal and vertical drags have the same projected direction for Y-up and Z-up models',()=>{
 const app=fs.readFileSync(path.join(__dirname,'../cfd_studio/app.py'),'utf8');
 const eyeSource=app.slice(app.indexOf('function eye(){'),app.indexOf('let VW,VH;'));
 const drag=app.match(/th\+=dx\*0\.0055[^;]+;ph=[^;]+;/)[0];
 const projected=(zUp,dx,dy)=>{
  const ctx={tgt:[0,0,0],rad:10,th:0,ph:0,dx,dy,VIZCFG:{},CFG:{},warehouseActive:()=>zUp,isSiloConfig:()=>false,isTracerConfig:()=>false,Math};
  vm.createContext(ctx);vm.runInContext(eyeSource,ctx);vm.runInContext(drag,ctx);
  const e=ctx.eye(),up=ctx.viewUp(),dot=(a,b)=>a.reduce((s,x,i)=>s+x*b[i],0),norm=v=>v.map(x=>x/Math.hypot(...v)),cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
  const z=norm(e),x=norm(cross(up,z)),y=cross(z,x),point=zUp?[0,1,0]:[0,0,1];return [dot(x,point),dot(y,point)];
 };
 for(const [dx,dy] of [[20,0],[-20,0],[0,20],[0,-20]]){
  const a=projected(false,dx,dy),b=projected(true,dx,dy);assert.ok(Math.abs(a[0]-b[0])<1e-10);assert.ok(Math.abs(a[1]-b[1])<1e-10);
 }
});

const {warehouseFlowSamples,warehouseFlowVector}=require('../cfd_studio/internal/warehouse_viewer.js');
test('dense warehouse vectors cover space using original cell centres and a bounded count',()=>{
 const points=[];for(let z=0;z<12;z++)for(let y=0;y<20;y++)for(let x=0;x<78;x++)points.push([x+.5,y+.5,z+.5]);
 const before=JSON.stringify(points),sample=warehouseFlowSamples(points,6000);
 assert.ok(sample.indices.length>350);assert.ok(sample.indices.length<=6000);assert.equal(new Set(sample.indices).size,sample.indices.length);
 const selected=sample.indices.map(i=>points[i]);for(let d=0;d<3;d++){assert.ok(Math.min(...selected.map(p=>p[d]))<2);assert.ok(Math.max(...selected.map(p=>p[d]))>[75,17,9][d]);}
 assert.equal(JSON.stringify(points),before);
});
test('warehouse section is selected before density reduction and retains every available small-section cell',()=>{
 const points=[];for(let z=0;z<8;z++)for(let y=0;y<25;y++)for(let x=0;x<40;x++)points.push([x+.5,y+.5,z+.5]);
 const sample=warehouseFlowSamples(points,6000,12.5);
 assert.equal(sample.indices.length,320);assert.ok(sample.indices.every(i=>points[i][1]===12.5));
});
test('warehouse density levels include all available cells at the highest setting without creating new values',()=>{
 const points=Array.from({length:14880},(_,i)=>[i%124,Math.floor(i/124)%20,Math.floor(i/2480)]);
 const detailed=warehouseFlowSamples(points,18000);assert.equal(detailed.indices.length,14880);
 const low=[.000001,0,0],high=[0,.000001,0];const v=warehouseFlowVector(low,high,.5);
 assert.deepEqual(v.velocity,[.0000005,.0000005,0]);assert.ok(v.speed>0);assert.deepEqual(warehouseFlowVector([0,0,0],[0,0,0],0),{velocity:[0,0,0],speed:0});
});
