const WPresentation=typeof module!=='undefined'?require('./viewer_presentation.js'):globalThis.CFDPresentation;
// Adapt warehouse fields to the shared Studio canvas, controls and exports
let WH=null,WHGEN=0,WHREQUESTS=new Set(),WHBASE=null,WHGPU=null;
const WHSAVED=new Map(),WHLAYERS=['lyBub','lyPhase','lySlice','lyTvol','lyGeo','lyCoil','lyTank','lyBound','lyProbe','lyInfo','gcT','gcV','gcB','gcL'];
function warehouseActive(){return VIZCFG?._해석유형==='warehouse';}
function warehouseBlend(a,b,u){return a+(b-a)*Math.max(0,Math.min(1,u));}
function warehouseBracket(times,time){let i=0;while(i+1<times.length&&times[i+1]<=time)i++;const j=Math.min(i+1,times.length-1);return {i,j,u:j===i?0:Math.max(0,Math.min(1,(time-times[i])/(times[j]-times[i])))};}
function warehouseCompatible(a,b){return a.total_cells===b.total_cells&&a.sampling_stride===b.sampling_stride&&a.cell_centres_m.length===b.cell_centres_m.length&&a.cell_centres_m.every((p,i)=>p.every((v,k)=>v===b.cell_centres_m[i][k]));}
function warehouseField(){const fields=WPresentation.layers('warehouse',WH?.meta.available_fields||['concentration']).filter(f=>f.available&&f.kind==='scalar');return (fields.find(f=>LY(f.control))||fields[0])?.id||null;}
function warehouseValues(f,field){return WPresentation.values(f,field);}
function warehouseRange(a,b,field){const x=WPresentation.range(a,field),y=WPresentation.range(b,field);if(!x||!y)throw Error('Result field range unavailable: '+field);return [Math.min(x[0],y[0]),Math.max(x[1],y[1])];}
function warehouseCamera(){if(!WH)return;const g=WH.meta.geometry;tgt=[g.length_m*500,g.width_m*500,(g.eaves_m+g.roof_rise_m)*420];rad=Math.max(g.length_m,g.width_m,g.eaves_m+g.roof_rise_m)*2500;th=-.25;ph=.35;}
function rememberWarehouse(){if(!WH||!warehouseActive())return;WHSAVED.set(WH.id,{clock,th,ph,rad,tgt:[...tgt],layers:Object.fromEntries(WHLAYERS.map(id=>[id,!!document.getElementById(id).checked]))});}
function suspendWarehouseViewer(){rememberWarehouse();WHGEN++;for(const r of WHREQUESTS)r.abort();WHREQUESTS.clear();setPlay(false,true);PLAYBUFSEQ++;PLAYBUFFERING=false;}
function cancelViewerLoad(){VLOADGEN++;VFRAMEGEN++;VPREFETCHTOKEN++;PLAYBUFSEQ++;PLAYBUFFERING=false;loadFrames.busy=false;loadFrames.pending=false;if(REC)stopVideo();setPlay(false,true);}
async function warehouseAPI(path){const abort=new AbortController();WHREQUESTS.add(abort);try{const r=await fetch('/api/warehouse/results/'+path,{signal:abort.signal});const d=await r.json();if(!r.ok)throw Error(d.error||d.msg||'결과 읽기 실패');return d;}finally{WHREQUESTS.delete(abort);}}
function warehouseLabel(id,text,show=true){const input=document.getElementById(id),row=input.closest('label'),sw=row.querySelector('.sw');row.style.display=show?'':'none';row.title=text;while(sw?.nextSibling)sw.nextSibling.remove();if(sw)row.append(document.createTextNode(text));}
function saveWarehouseUI(){if(WHBASE)return;WHBASE={flowGradient:document.getElementById('vbarRange').previousElementSibling.style.background,gradient:document.querySelector('#tcbar .grad').style.background,mode:configureViewerFields.mode,labels:{},titles:GDEF.map(d=>d.title),hrow:document.querySelector('#hud .hrow').innerHTML};
 for(const id of WHLAYERS){const input=document.getElementById(id),row=input.closest('label'),sw=row.querySelector('.sw'),nodes=[];for(let n=sw?.nextSibling;n;n=n.nextSibling)nodes.push(n.cloneNode(true));WHBASE.labels[id]={nodes,display:row.style.display,title:row.title,checked:input.checked,disabled:input.disabled};}}
function restoreWarehouseUI(){if(!WHBASE)return;lastTbarShow=null;lastVbarShow=null;for(const [id,v] of Object.entries(WHBASE.labels)){const input=document.getElementById(id),row=input.closest('label'),sw=row.querySelector('.sw');while(sw?.nextSibling)sw.nextSibling.remove();for(const n of v.nodes)row.append(n.cloneNode(true));row.style.display=v.display;row.title=v.title;input.checked=v.checked;input.disabled=v.disabled;}
 document.getElementById('vbarRange').previousElementSibling.style.background=WHBASE.flowGradient;
 document.querySelector('#tcbar .grad').style.background=WHBASE.gradient;configureViewerFields.mode=WHBASE.mode;GDEF.forEach((d,i)=>d.title=WHBASE.titles[i]);document.querySelector('#hud .hrow').innerHTML=WHBASE.hrow;WHBASE=null;
 document.getElementById('warehouseDetails')?.remove();document.getElementById('saveShot').title='현재 3D 화면 저장';document.getElementById('gcol')._keys='';
 document.querySelector('#tcbar>div').textContent='온도 °C';document.getElementById('tcSat').style.display='';document.getElementById('tcSatL').style.display='';
 const old=document.getElementById('tracerStats');if(old)old.style.display='none';}
function configureWarehouseUI(){if(!WH)return;saveWarehouseUI();document.body.classList.remove('tracerView');
 const old=document.getElementById('tracerStats');if(old)old.style.display='none';
 configureViewerFields.mode='warehouse';const available=WH.meta.available_fields||['concentration'];
 for(const [id,text,show] of [['lyPhase','상분율',false],['lyGeo','다공성 곡물',!!WH.meta.loading?.blocks?.length],['lyTank','저장고 외곽',true],['lyCoil','코일',false],['lyBound','중앙 통로 단면',true],['lyProbe','측정점',false],['lyInfo','시간·원본 정보',true],['gcT','온도 범위',available.includes('temperature')],['gcV','농도 범위',true],['gcB','최대 유속',available.includes('velocity')],['gcL','층별 평균',false]])warehouseLabel(id,text,show);
 for(const def of WPresentation.layers('warehouse',available)){const input=document.getElementById(def.control);warehouseLabel(def.control,def.label,def.available);input.disabled=!def.available;input.closest('label').classList.toggle('off2',input.disabled);}
 document.getElementById('vbarRange').previousElementSibling.style.background='linear-gradient(90deg,#0b4b6b,#5b9268,#ffe03d)';
 GDEF[0].title='온도 범위 (°C)';GDEF[1].title='농도 범위 ('+WH.unit+')';GDEF[2].title='최대 유속 (m/s)';
 document.querySelector('#hud .hrow').innerHTML='<span>t <b id="hT">—</b> s</span><span>표시 <b id="hC">—</b>셀</span><span hidden>농도 표본최대 <b id="hV">—</b> '+WH.unit+'</span>';
 document.querySelector('#hud .hrow').style.display='';document.getElementById('hLiveG').style.display='none';
 const g=WH.meta.geometry;document.getElementById('hGeo').textContent=g.length_m+' × '+g.width_m+' m · '+(WH.meta.loading?.blocks?.length?'다공성 곡물 · ':'')+(WH.meta.model==='normalized_gable_verification'?'정규화 시험':'ClO₂ 가정 기반 계산');
 document.getElementById('plabels').replaceChildren();document.getElementById('gcol')._keys='';
 document.getElementById('saveShot').title='현재 3D 화면 저장';document.getElementById('vizWarn').style.display='none';document.getElementById('empty').style.display='none';
 for(const title of document.querySelectorAll('#vlegend .ltit'))title.style.display='';
 for(const [id,other] of [['lyBub','lyTvol'],['lyTvol','lyBub']]){const input=document.getElementById(id);if(!input.dataset.warehouseBound){input.addEventListener('change',()=>{if(warehouseActive()&&input.checked)document.getElementById(other).checked=false;});input.dataset.warehouseBound='1';}}
 updateWarehouseSlots();
}
function updateWarehouseSlots(){if(!WH)return;const m=WH.meta,n=m.times_s.length;for(const [id,title,text] of [['slBub','농도장',n+'개'],['slPhase','계산 격자',m.cells.toLocaleString()+'셀'],['slFlow','속도장',m.available_fields?.includes('velocity')?n+'개':'해당 없음'],['slTherm','온도장',m.available_fields?.includes('temperature')?n+'개':'해당 없음']]){const e=document.getElementById(id);e.textContent=text;e.parentElement.querySelector('b').textContent=title;e.className='sst ok';}document.getElementById('projDataName').textContent=WH.name;document.getElementById('btnRunTxt').textContent='다시 읽기';document.getElementById('btnRun').disabled=false;document.getElementById('btnUpdateViz').style.display='none';}
function warehouseBuildGeometry(){for(const g of WH.geometry||[])gl.deleteBuffer(g.mesh.b);WH.geometry=[];const g=WH.meta.geometry,L=g.length_m*1000,W=g.width_m*1000,E=g.eaves_m*1000,H=E+g.roof_rise_m*1000;
 const v=[[0,0,0],[L,0,0],[L,W,0],[0,W,0],[0,0,E],[L,0,E],[L,W,E],[0,W,E],[0,W/2,H],[L,W/2,H]];
 const edges=[[0,1],[1,2],[2,3],[3,0],[0,4],[1,5],[2,6],[3,7],[4,5],[6,7],[4,8],[8,7],[5,9],[9,6],[8,9]];
 WH.geometry.push({type:'outline',mesh:mesh(edges.flatMap(([a,b])=>[...v[a],...v[b]]))});
 const roof=[v[4],v[5],v[9],v[4],v[9],v[8],v[8],v[9],v[6],v[8],v[6],v[7]];WH.geometry.push({type:'roof',mesh:mesh(roof.flat())});
 for(const b of WH.meta.loading?.blocks||[]){const a=b.min_m.map(x=>x*1000),z=b.max_m.map(x=>x*1000);WH.geometry.push({type:'grain',mesh:mesh(boxTris(...a,...z))},{type:'grainEdge',mesh:mesh(boxEdges(...a,...z))});}
}
async function loadWarehouseResult(id,name){rememberWarehouse();suspendWarehouseViewer();cancelViewerLoad();const gen=WHGEN;if(WH?.geometry)for(const g of WH.geometry)gl.deleteBuffer(g.mesh.b);WH=null;CFG=VIZCFG={_해석유형:'warehouse'};FRAMES=[];VSTREAMERR.clear();idx=0;clock=0;FLOWMAP={};THERMMAP={};PHASEMAP={};PRESSUREMAP={};TURBMAP={};BUBLOADED=0;Cxyz=null;VHIST=[];VHISTC=[];VHISTV=[];
 document.getElementById('tbar').max=0;document.getElementById('tlab').textContent='불러오는 중';document.getElementById('hFrTit').textContent='재생 프레임 · 불러오는 중';loadMsg('결과 불러오는 중');document.getElementById('empty').style.display='';gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
 try{const meta=await warehouseAPI('meta?id='+encodeURIComponent(id));if(gen!==WHGEN)return;
 if(!meta.times_s?.length||meta.times_s.some((t,i)=>!Number.isFinite(t)||(i&&t<=meta.times_s[i-1])))throw Error('결과 시간 순서를 확인해 주세요');
 WH={id,name,meta,unit:meta.concentration_unit==='kg/m3'?'mg/m³':'C/C_ref',cache:new Map(),pending:new Map(),stats:new Map(),geometry:[],pairKey:'',lastHud:0};VIZCFG=CFG={_해석유형:'warehouse',warehouse:meta};LOADED_RID='warehouse:'+id;
 saveWarehouseUI();const saved=WHSAVED.get(id),defaults={lyBub:true,lyPhase:false,lySlice:meta.available_fields?.includes('velocity'),lyTvol:false,lyGeo:true,lyTank:true,lyCoil:false,lyBound:false,lyProbe:false,lyInfo:true,gcT:meta.available_fields?.includes('temperature'),gcV:true,gcB:false,gcL:false};
 for(const key of WHLAYERS)document.getElementById(key).checked=!!(saved?.layers||defaults)[key];warehouseBuildGeometry();warehouseCamera();if(saved){clock=saved.clock;th=saved.th;ph=saved.ph;rad=saved.rad;tgt=[...saved.tgt];}
 FRAMES=meta.times_s.map(t=>({t,pt:t,ready:false}));configureWarehouseUI();finishFrames(false);if(!await ensureWarehouseFrame(idx))throw Error('첫 표시 프레임을 읽지 못했습니다');if(gen!==WHGEN)return;await ensureWarehouseFrame(Math.min(idx+1,FRAMES.length-1));if(gen!==WHGEN)return;resize();prefetchViz(idx,true);
 }catch(e){if(gen===WHGEN&&e.name!=='AbortError'){setPlay(false,true);FRAMES=[];loadMsg('결과 읽기 실패');toast(e.message,true);}}
}
function warehouseFrameReady(i){return !!(WH&&FRAMES[i]&&WH.cache.has(i));}
async function ensureWarehouseFrame(i){const w=WH,gen=WHGEN;if(!w||!FRAMES[i])return false;if(w.cache.has(i))return true;if(w.pending.has(i))return w.pending.get(i);
 const promise=(async()=>{try{const f=await warehouseAPI('frame?id='+encodeURIComponent(w.id)+'&index='+i+'&maximum_points=125000');if(gen!==WHGEN||WH!==w)return false;const first=w.cache.values().next().value;if(first&&!warehouseCompatible(first,f))throw Error('프레임 간 셀 좌표 또는 표본 순서가 다릅니다');w.cache.set(i,f);while(w.cache.size>Math.max(2,Math.min(8,Math.floor(400000/f.displayed_cells)))){const keys=[...w.cache.keys()].sort((a,b)=>Math.abs(b-idx)-Math.abs(a-idx));w.cache.delete(keys[0]);}w.stats.set(i,{t:f.time_s,c:[f.minimum,f.maximum],T:f.temperature_range_C,U:f.speed_range_m_s});FRAMES[i].ready=true;FRAMES[i].statsReady=true;document.getElementById('gcol')._keys='';return true;
 }catch(e){if(gen===WHGEN&&e.name!=='AbortError'){VSTREAMERR.add('frame-load');setPlay(false,true);toast('결과 읽기 실패: '+e.message,true);}return false;}finally{w.pending.delete(i);}})();w.pending.set(i,promise);return promise;
}
function warehouseGPU(){if(WHGPU)return WHGPU;const shader=prog(`attribute vec3 aP;attribute float aA;attribute float aB;uniform mat4 uM;uniform float uMix;uniform vec2 uRange;uniform float uSize;uniform float uK;varying float vValue;varying float vY;void main(){gl_Position=uM*vec4(aP,1.);gl_PointSize=clamp(uSize*uK/max(gl_Position.w,1.),2.,46.);vValue=clamp((mix(aA,aB,uMix)-uRange.x)/max(uRange.y-uRange.x,0.000000001),0.,1.);vY=aP.y;}`,
 `precision mediump float;varying float vValue;varying float vY;uniform float uSlice;uniform float uMid;uniform float uTemp;void main(){if(uSlice>.5&&abs(vY-uMid)>650.)discard;vec2 p=gl_PointCoord*2.-1.;float d=dot(p,p);if(d>1.)discard;float edge=exp(-3.5*d)*(1.-smoothstep(.65,1.,d));vec3 c=vValue<.5?mix(vec3(.08,.3,.85),vec3(.15,.9,.73),vValue*2.):mix(vec3(.15,.9,.73),vec3(1.,.29,.09),(vValue-.5)*2.);float opacity=uTemp>.5?.17:(.008+.19*vValue);gl_FragColor=vec4(c,opacity*edge);}`);
 WHGPU={shader,pos:gl.createBuffer(),a:gl.createBuffer(),b:gl.createBuffer(),arrows:gl.createBuffer(),dots:gl.createBuffer()};return WHGPU;}
function warehousePreparePair(a,b,i,j,field){const key=i+':'+j+':'+field;if(WH.pairKey===key)return;WH.pairKey=key;const gpu=warehouseGPU();const pos=new Float32Array(a.cell_centres_m.length*3);a.cell_centres_m.forEach((p,k)=>p.forEach((x,d)=>pos[k*3+d]=x*1000));
 for(const [buffer,data] of [[gpu.pos,pos],[gpu.a,new Float32Array(warehouseValues(a,field)||[])],[gpu.b,new Float32Array(warehouseValues(b,field)||[])]]){gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,data,gl.STATIC_DRAW);}WH.range=warehouseRange(a,b,field);WH.count=a.cell_centres_m.length;}
function warehouseDrawCloud(M,a,b,u,field){if(!warehouseValues(a,field)||!warehouseValues(b,field))return;const g=WHGPU,p=g.shader;gl.useProgram(p);gl.uniformMatrix4fv(gl.getUniformLocation(p,'uM'),false,new Float32Array(M));gl.uniform1f(gl.getUniformLocation(p,'uMix'),u);gl.uniform2fv(gl.getUniformLocation(p,'uRange'),WH.range);gl.uniform1f(gl.getUniformLocation(p,'uK'),cv.height/2/Math.tan(19*Math.PI/180));
 const geo=WH.meta.geometry;const size=Math.cbrt(geo.length_m*geo.width_m*geo.eaves_m/WH.count)*2300;gl.uniform1f(gl.getUniformLocation(p,'uSize'),size);gl.uniform1f(gl.getUniformLocation(p,'uSlice'),LY('lyBound')?1:0);gl.uniform1f(gl.getUniformLocation(p,'uMid'),geo.width_m*500);gl.uniform1f(gl.getUniformLocation(p,'uTemp'),field==='temperature'?1:0);
 for(const [name,buffer,n] of [['aP',g.pos,3],['aA',g.a,1],['aB',g.b,1]]){const loc=gl.getAttribLocation(p,name);gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.enableVertexAttribArray(loc);gl.vertexAttribPointer(loc,n,gl.FLOAT,false,0,0);}gl.drawArrays(gl.POINTS,0,WH.count);
 for(const name of ['aP','aA','aB'])gl.disableVertexAttribArray(gl.getAttribLocation(p,name));}
// Sample existing cell centers; display density does not refine the CFD mesh
function warehouseFlowSamples(points,budget,mid=null){
 const lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];
 let nearest=Infinity;for(const p of points){for(let d=0;d<3;d++){lo[d]=Math.min(lo[d],p[d]);hi[d]=Math.max(hi[d],p[d]);}if(mid!==null)nearest=Math.min(nearest,Math.abs(p[1]-mid));}
 const band=Math.max(.65,nearest+1e-7),candidates=[];
 for(let i=0;i<points.length;i++)if(mid===null||Math.abs(points[i][1]-mid)<=band)candidates.push(i);
 if(!candidates.length)return {indices:[],spacing:1};
 const axes=mid===null?[0,1,2]:[0,2],volume=axes.reduce((v,d)=>v*Math.max(hi[d]-lo[d],.01),1);
 let spacing=Math.pow(volume/Math.min(budget,candidates.length),1/axes.length);
 if(candidates.length<=budget)return {indices:candidates,spacing};
 let bins;
 for(let attempt=0;attempt<40;attempt++){
  bins=new Map();
  for(const i of candidates){const p=points[i],q=axes.map(d=>Math.floor((p[d]-lo[d])/spacing)),key=q.join(',');let distance=0;axes.forEach((d,k)=>{distance+=(p[d]-lo[d]-(q[k]+.5)*spacing)**2;});if(mid!==null)distance+=(p[1]-mid)**2;
   const previous=bins.get(key);if(!previous||distance<previous.distance)bins.set(key,{index:i,distance});
  }
  if(bins.size<=budget)break;spacing*=1.15;
 }
 return {indices:[...bins.values()].map(v=>v.index),spacing};
}
function warehouseFlowVector(a,b,u){const velocity=a.map((v,d)=>warehouseBlend(v,b[d],u));return {velocity,speed:Math.hypot(...velocity)};}
function warehouseDrawFlow(M,a,b,u){
 if(!a.velocity_m_s||!b.velocity_m_s)return;
 const budget=viewerFlowBudget(),slice=LY('lyBound'),sampleKey=budget+':'+slice;
 WH.flowSamples??=new Map();if(!WH.flowSamples.has(sampleKey))WH.flowSamples.set(sampleKey,warehouseFlowSamples(a.cell_centres_m,budget,slice?WH.meta.geometry.width_m/2:null));
 const sample=WH.flowSamples.get(sampleKey),max=Math.max(a.speed_range_m_s[1],b.speed_range_m_s[1],1e-10),key=[a.index,b.index,u,clock,sampleKey].join(':');
 if(WH.flowDrawKey!==key){
  const arrows=[],dots=[];
  for(const k of sample.indices){const {velocity,speed}=warehouseFlowVector(a.velocity_m_s[k],b.velocity_m_s[k],u);if(speed<=1e-12)continue;
   const r=Math.min(1,speed/max),length=sample.spacing*1000*(.35+.55*Math.sqrt(r)),v=velocity.map(x=>x/speed),start=a.cell_centres_m[k].map(x=>x*1000),end=start.map((x,d)=>x+v[d]*length);
   const perp=Math.hypot(v[0],v[1])>1e-5?[-v[1],v[0],0]:[1,0,0],norm=Math.hypot(...perp);
   for(const sign of [-1,1])arrows.push(...end,r,...end.map((x,d)=>x-v[d]*length*.23+sign*perp[d]/norm*length*.13),r);
   arrows.push(...start,r,...end,r);const q=(k*.6180339+clock*(.32+.55*r))%1;dots.push(...start.map((x,d)=>x+v[d]*length*q),r);
  }
  WH.flowCounts=[arrows.length/4,dots.length/4];WH.flowDrawKey=key;
  for(const [buffer,vertices] of [[WHGPU.arrows,arrows],[WHGPU.dots,dots]]){gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(vertices),gl.DYNAMIC_DRAW);}
 }
 // Small markers keep dense vectors readable, independent of the legacy tank renderer.
 if(!WHGPU.flowDotShader)WHGPU.flowDotShader=prog(`attribute vec3 aP;attribute float aS;uniform mat4 uM;varying float vS;void main(){gl_Position=uM*vec4(aP,1.);gl_PointSize=2.+1.5*aS;vS=aS;}`,`precision mediump float;varying float vS;void main(){vec2 q=gl_PointCoord*2.-1.;float d=dot(q,q);if(d>1.)discard;gl_FragColor=vec4(mix(vec3(.16,.78,1.),vec3(1.,.91,.32),vS),smoothstep(1.,.15,d)*.65);}`);
 for(const [program,buffer,count,mode] of [[arrowP,WHGPU.arrows,WH.flowCounts[0],gl.LINES],[WHGPU.flowDotShader,WHGPU.dots,WH.flowCounts[1],gl.POINTS]]){
  gl.useProgram(program);gl.uniformMatrix4fv(gl.getUniformLocation(program,'uM'),false,new Float32Array(M));if(program===arrowP){gl.uniform1f(gl.getUniformLocation(program,'uSilo'),1);gl.uniform1f(gl.getUniformLocation(program,'uIf'),0);}
  gl.bindBuffer(gl.ARRAY_BUFFER,buffer);for(const [name,n,offset] of [['aP',3,0],['aS',1,12]]){const loc=gl.getAttribLocation(program,name);gl.enableVertexAttribArray(loc);gl.vertexAttribPointer(loc,n,gl.FLOAT,false,16,offset);}gl.drawArrays(mode,0,count);for(const name of ['aP','aS'])gl.disableVertexAttribArray(gl.getAttribLocation(program,name));
 }
 document.getElementById('vbarTitle').textContent='유속 m/s · 벡터 '+WH.flowCounts[1].toLocaleString()+'개';document.getElementById('vbarRange').textContent='0 ~ '+max.toPrecision(3);
}
function frameWarehouse(now,dt){gl.clearColor(.051,.051,.051,1);gl.enable(gl.DEPTH_TEST);gl.depthMask(true);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);if(!WH||!FRAMES.length)return;
 const times=WH.meta.times_s;if(playing){const next=Math.min(times.at(-1),clock+Math.min(dt,.1)*(+document.getElementById('speed').value||1)),p=warehouseBracket(times,next);if(warehouseFrameReady(p.i)&&warehouseFrameReady(p.j)){clock=next;idx=p.i;if(clock>=times.at(-1))setPlaybackEnded();}else{ensureWarehouseFrame(p.i);ensureWarehouseFrame(p.j);}}
 const {i,j,u}=warehouseBracket(times,clock),a=WH.cache.get(i),b=WH.cache.get(j);if(!a||!b){ensureWarehouseFrame(i);ensureWarehouseFrame(j);return;}idx=i;const field=warehouseField();if(field)warehousePreparePair(a,b,i,j,field);else warehouseGPU();
 const projection=persp(38*Math.PI/180,VW/VH,Math.max(1,rad/1500),rad+cameraModelSpan()*12);projection[8]=Math.min(.38,(document.getElementById('lcol').clientWidth+16)/VW);const M=mul(projection,lookAt(eye(),tgt,viewUp()));gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);gl.depthMask(false);
 for(const part of WH.geometry){if(part.type==='grain'&&LY('lyGeo'))dM(part.mesh,[.32,.49,.28,.12],M);if(part.type==='roof'&&LY('lyTank'))dM(part.mesh,[.6,.69,.8,.025],M);}
 if(field&&(LY('lyBub')||LY('lyTvol')))warehouseDrawCloud(M,a,b,u,field);
 for(const part of WH.geometry){if(part.type==='outline'&&LY('lyTank'))dL(part.mesh,[.8,.84,.92,.5],M);if(part.type==='grainEdge'&&LY('lyGeo'))dL(part.mesh,[.45,.72,.3,.27],M);}
 if(LY('lySlice'))warehouseDrawFlow(M,a,b,u);gl.depthMask(true);
 syncPlaybackTimeline();document.getElementById('tlab').textContent=clock.toFixed(2)+'s ('+FRAMES.length.toLocaleString()+'프레임)';document.getElementById('hT').textContent=clock.toFixed(2);document.getElementById('hC').textContent=a.displayed_cells.toLocaleString()+' / '+a.total_cells.toLocaleString();
 const show=!!field&&(LY('lyBub')||LY('lyTvol'));document.getElementById('tcbar').style.display=show?'flex':'none';document.getElementById('vbar').style.display=LY('lySlice')?'':'none';document.querySelector('#tcbar>div').textContent=field==='temperature'?'온도 °C':'농도 '+WH.unit;document.getElementById('tcHi').textContent=WH.range?.[1]?.toPrecision(4)||'—';document.getElementById('tcLo').textContent=WH.range?.[0]?.toPrecision(4)||'—';document.getElementById('tcSat').style.display='none';document.getElementById('tcSatL').style.display='none';document.querySelector('#tcbar .grad').style.background='linear-gradient(to top,#144dd9,#26e6ba,#ff4a17)';document.querySelector('#hud .hrow').style.display=LY('lyInfo')?'':'none';
 if(now-WH.lastHud>150){WH.lastHud=now;const av=warehouseValues(a,field),bv=warehouseValues(b,field);let max=-Infinity;if(av&&bv)for(let k=0;k<av.length;k++)max=Math.max(max,warehouseBlend(av[k],bv[k],u));document.getElementById('hV').textContent=Number.isFinite(max)?max.toPrecision(3):'—';renderGCol();}
 if(REC)recTick();
}
function warehouseSeries(id){if(!WH)return [];const rows=[...WH.stats.values()].sort((a,b)=>a.t-b.t);const field=id==='gcT'?'T':id==='gcV'?'c':id==='gcB'?'U':null;if(!field)return [];const values=rows.filter(r=>r[field]);return (id==='gcB'?[1]:[0,1]).map((k,i)=>({name:k?'최댓값':'최솟값',color:i?'#e08a3a':'#3987e5',pts:values.map(r=>[r.t,r[field][k]])}));}
function drawWarehouseOverlay(ctx,d){if(!WH)return;ctx.save();ctx.font=12*d+'px Segoe UI';const text=WH.name+' · t = '+clock.toFixed(2)+' s · '+(globalThis.CFDI18n?.translate(warehouseField()==='temperature'?'온도 °C':'농도 '+WH.unit)||(warehouseField()==='temperature'?'온도 °C':'농도 '+WH.unit));ctx.fillStyle='rgba(18,18,18,.8)';ctx.fillRect(10*d,10*d,Math.min(ctx.canvas.width-20*d,ctx.measureText(text).width+20*d),34*d);ctx.fillStyle='#eee';ctx.fillText(text,20*d,32*d);ctx.restore();}
if(typeof module!=='undefined')module.exports={warehouseBlend,warehouseBracket,warehouseCompatible,warehouseRange,warehouseFlowSamples,warehouseFlowVector};
