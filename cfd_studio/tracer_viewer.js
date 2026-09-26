// Dedicated scalar semantics on the shared Studio canvas and physical timeline.
let TRACERMAP={concentration:{},sorbed:{}},TRACERGEOM=[],TRACERLOAD=new Map();
let TRACERBLEND=null,TRACERMEASURE={wall:0,physical:0,frames:0};
function isTracerConfig(c){return !!(c&&c._해석유형==='gas_transport'&&c.tracer);}
function tracerField(){return LY('lyPhase')?'sorbed':'concentration';}
function tracerCamera(c){
 const lengths=c.tracer.lengths_m.map(v=>v*1000);
 tgt=lengths.map(v=>v/2);rad=Math.max(...lengths)*2.1;th=.22;ph=.35;
}
function setTracerConfig(c){
 VIZCFG=c;
 for(const item of TRACERGEOM)gl.deleteBuffer(item.mesh.b);
 TRACERGEOM=[];
 const lengths=c.tracer.lengths_m.map(v=>v*1000);
 TRACERGEOM.push({type:'tank',mesh:mesh(boxEdges(0,0,0,...lengths))});
 for(const box of c.tracer.porous_boxes_m||[])
  TRACERGEOM.push({type:'porous',mesh:mesh(boxEdges(...box.min.map(v=>v*1000),...box.max.map(v=>v*1000)))});
 if(c.tracer.source&&c.tracer.source.box_m){const box=c.tracer.source.box_m;
  TRACERGEOM.push({type:'source',mesh:mesh(boxEdges(...box.min.map(v=>v*1000),...box.max.map(v=>v*1000)))});}
 PROBEPTS=[];G.probes=[];tracerCamera(c);
 document.getElementById('hGeo').textContent=c.tracer.lengths_m.join(' × ')+' m';
 configureTracerFields(c);
}
function configureTracerFields(c){
 document.body.classList.toggle('tracerView',MODE==='viz');
 const ids=['lyBub','lyPhase','lySlice','lyTvol','lyGeo','lyCoil','lyTank','lyBound'];
 const prior=configureViewerFields.mode;
 if(prior!=='gas_transport'){
  if(prior)VIEWLAYERSTATE[prior]=Object.fromEntries(ids.map(id=>[id,!!document.getElementById(id).checked]));
  const saved=VIEWLAYERSTATE.gas_transport||{lyBub:true,lyPhase:false,lySlice:false,lyTvol:false,lyGeo:true,lyCoil:true,lyTank:true,lyBound:false};
  for(const id of ids)document.getElementById(id).checked=!!saved[id];
 }
 configureViewerFields.mode='gas_transport';
 const label=(id,text,show=true)=>{const e=document.getElementById(id),row=e.closest('label'),sw=row.querySelector('.sw');
  row.style.display=show?'':'none';row.title=text;if(sw){while(sw.nextSibling)sw.nextSibling.remove();row.appendChild(document.createTextNode(text));}};
 label('lyBub','농도 C/C_ref');label('lyPhase','흡착량 Q/C_ref');
 label('lySlice','속도장',false);label('lyTvol','온도장',false);
 label('lyGeo','다공성 적재 영역');label('lyCoil','공급 영역');label('lyTank','계산 영역');label('lyBound','경계',false);
 for(const id of ['lyProbe','lyInfo','gcT','gcV','gcB','gcL']){const e=document.getElementById(id);if(e){e.checked=false;e.closest('label').style.display='none';}}
 document.getElementById('gcol').innerHTML='';
 const graphTitle=[...document.querySelectorAll('#vlegend .ltit')].find(e=>e.textContent.trim()==='그래프');if(graphTitle)graphTitle.style.display='none';
 document.getElementById('probeLabels')?.replaceChildren();
 const p=document.getElementById('lyBub'),q=document.getElementById('lyPhase');
 if(!p.dataset.tracerBound){
  p.addEventListener('change',()=>{if(isTracerConfig(VIZCFG||CFG)){if(p.checked)q.checked=false;refreshViewerFields();}});
  q.addEventListener('change',()=>{if(isTracerConfig(VIZCFG||CFG)){if(q.checked)p.checked=false;refreshViewerFields();}});
  p.dataset.tracerBound='1';
 }
 document.getElementById('appContext').textContent='가스 수송 CFD · 정규화 추적자';
 const hud=document.querySelector('#hud .hrow');if(hud)hud.style.display='none';
 document.getElementById('dash').style.display=MODE==='cfd'?'flex':'none';
 document.getElementById('vbar').style.display='none';
 document.getElementById('vizWarn').style.display='none';
 configureOutputFields(c);
 let stat=document.getElementById('tracerStats');
 if(!stat){stat=document.createElement('div');stat.id='tracerStats';stat.style.cssText='font-size:11px;line-height:1.6;white-space:normal;max-width:330px';document.getElementById('hud').appendChild(stat);}
 stat.style.display='';
 const perf=c.performance||{};
 stat.textContent='모사 '+Number(perf.physical_duration_s||0).toFixed(2)+' s · 저장 '+(perf.saved_frames||0)+'프레임 · 계산 '+Number(perf.elapsed_s||0).toFixed(2)+' s';
}
function showTracerSettings(body,c){
 const p=c.tracer,s=p.source||{},stop=p.termination||{mode:'time'};
 const rows=[['솔버','porousTracerFoam'],['대상 필드','정규화 추적자 (PH₃ 물성 미적용)'],
  ['계산 영역',p.lengths_m.join(' × ')+' m'],['격자',p.shape_xyz.join(' × ')],
  ['초기 농도',p.initial_mean+' C/C_ref'],['계산 시간 간격',p.dt_s+' s'],['저장 간격',p.write_interval_s+' s'],
  ['공급 시작','0 s'],['공급 종료',s.end_s==null?'공급 없음':s.end_s+' s'],
  ['종료 기준',stop.mode==='steady'?'정상상태':'지정 시간'],['최대 모사 시간',p.end_s+' s']];
 if(stop.mode==='steady')rows.push(['상대 변화율 허용치',stop.relative_rate_per_s+' /s'],['절대 변화율 허용치',stop.absolute_rate_per_s+' /s'],['유지 시간',stop.hold_s+' s'],['판정 시작',stop.minimum_time_s+' s']);
 body.innerHTML=rows.map(([label,value])=>'<div class="cr"><span>'+esc(label)+'</span><em>'+esc(value)+'</em><small></small></div>').join('');
}
function updateTracerSlots(){
 for(const [id,title,text] of [['slBub','농도장',SRV.concentration+'개'],['slPhase','흡착량',SRV.concentration+'개'],['slFlow','속도장','해당 없음'],['slTherm','온도장','해당 없음'],['slC','격자','구조 격자']]){
  const e=document.getElementById(id);if(!e)continue;e.textContent=text;const b=e.parentElement.querySelector('b');if(b)b.textContent=title;
 }
 const cfgName=document.getElementById('slCfgName');if(cfgName)cfgName.textContent=SRV.configName||'case_config.json';
 for(const id of ['lyBub','lyPhase']){const e=document.getElementById(id);e.disabled=!SRV.concentration;e.closest('label').classList.toggle('off2',!SRV.concentration);}
 document.getElementById('btnRunTxt').textContent='업데이트';
 document.getElementById('btnRun').disabled=false;
}
function parseTracer(buf,field){
 const dv=new DataView(buf),magic=field==='concentration'?0x434f4e31:0x534f5231;
 if(buf.byteLength<40||dv.getUint32(0,false)!==magic)throw Error('가스 수송 필드 형식 오류');
 const nx=dv.getUint32(4,true),ny=dv.getUint32(8,true),nz=dv.getUint32(12,true),bb=[];
 for(let i=0;i<6;i++)bb.push(dv.getFloat32(16+i*4,true));
 const cfg=(VIZCFG||CFG).tracer,shape=cfg.shape_xyz;
 if(nx!==shape[0]||ny!==shape[1]||nz!==shape[2]||buf.byteLength!==40+nx*ny*nz*4)throw Error('농도 격자 불일치');
 for(let i=0;i<3;i++)if(Math.abs(bb[i])>1e-7||Math.abs(bb[i+3]-cfg.lengths_m[i])>1e-6*Math.max(1,cfg.lengths_m[i]))throw Error('농도 공간 범위 불일치');
 const v=new Float32Array(buf.slice(40));
 for(const x of v)if(!Number.isFinite(x))throw Error('유효하지 않은 농도');
 // Never remove zero planes: a zero initial field is a valid physical state.
 return {nx,ny,nz,bb,v};
}
function tracerFrameReady(i){const f=FRAMES[i];return !!(f&&(!LY('lyBub')&&!LY('lyPhase')||TRACERMAP[tracerField()][f.t]));}
async function ensureTracerFrame(i){
 const f=FRAMES[i],field=tracerField(),gen=VFRAMEGEN;if(!f)return false;
 if(tracerFrameReady(i))return true;
 const key=gen+':'+field+':'+f.t;if(TRACERLOAD.has(key))return TRACERLOAD.get(key);
 const promise=(async()=>{try{
  const buf=await fetchVizBuffer(VFILEURL(f.tracer[field]));
  if(gen!==VFRAMEGEN)return false;
  TRACERMAP[field][f.t]=parseTracer(buf,field);trimFieldCache(TRACERMAP[field],f.t,128);return true;
 }catch(e){if(gen===VFRAMEGEN){const first=!VSTREAMERR.has('frame-load');VSTREAMERR.add('frame-load');setPlay(false,true);if(first)toast('농도 프레임 읽기 실패: '+e.message,true);}return false;
 }finally{TRACERLOAD.delete(key);}})();TRACERLOAD.set(key,promise);return promise;
}
async function loadTracerFrames(info,fileUrl,target,live){
 PLAYBUFSEQ++;PLAYBUFFERING=false;setPlay(false,true);
 const rows=info.tracer_frames||[];
 if(!rows.length||rows[0].t!==0||rows.some((f,i)=>!Number.isFinite(f.t)||(i&&f.t<=rows[i-1].t)))throw Error('농도장의 0초 초기 상태 또는 시간 순서가 잘못되었습니다');
 VFRAMEGEN++;VSTREAMERR.clear();VPREFETCHTOKEN++;VPREFETCHEND=-1;VPREFETCHBUSY=false;
 VFILEURL=fileUrl;LOADED_RID=target;TRACERMAP={concentration:{},sorbed:{}};TRACERLOAD.clear();TRACERBLEND=null;
 FLOWMAP={};THERMMAP={};PHASEMAP={};PRESSUREMAP={};TURBMAP={};Cxyz=null;BUBLOADED=0;
 FRAMES=rows.map(r=>({t:r.t,pt:r.t,tracer:r,n:0,v:0}));idx=0;clock=0;
 TRACERMEASURE={wall:0,physical:0,frames:0};
 finishFrames(false);await ensureTracerFrame(0);if(!live())return;
 prefetchViz(0,true);setDataAvail();SRVDIRTY=false;
 document.getElementById('frSt').textContent=FRAMES.length+'프레임';
}
function frameTracer(now,dt){
 if(!FRAMES.length){gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);return;}
 const lastTime=FRAMES[FRAMES.length-1].t,field=tracerField();
 if(playing){
  const next=Math.min(lastTime,clock+dt*(+document.getElementById('speed').value||1));
  const i=frameIndexAt(next),j=Math.min(i+1,FRAMES.length-1);
  if(tracerFrameReady(i)&&tracerFrameReady(j)){
   TRACERMEASURE.wall+=dt;TRACERMEASURE.physical+=next-clock;TRACERMEASURE.frames++;
   clock=next;idx=i;if(clock>=lastTime){idx=FRAMES.length-1;setPlaybackEnded();}
  }else{ensureTracerFrame(i);ensureTracerFrame(j);}
  prefetchViz(idx);
 }
 const f=FRAMES[idx],j=Math.min(idx+1,FRAMES.length-1),a=TRACERMAP[field][f.t],b=TRACERMAP[field][FRAMES[j].t];
 let T=a;
 if(a&&b&&playing&&j!==idx){
  const u=Math.max(0,Math.min(1,(clock-f.t)/(FRAMES[j].t-f.t)));
  const key=field+':'+idx+':'+Math.floor(now/33);
  if(!TRACERBLEND||TRACERBLEND.key!==key){const v=new Float32Array(a.v.length);for(let k=0;k<v.length;k++)v[k]=a.v[k]*(1-u)+b.v[k]*u;TRACERBLEND={key,T:{...a,v}};}
  T=TRACERBLEND.T;
 }
 document.getElementById('tbar').value=idx;
 document.getElementById('tlab').textContent='t = '+clock.toFixed(2)+' s';
 document.getElementById('hT').textContent=clock.toFixed(2);
 gl.clearColor(.051,.051,.051,1);gl.enable(gl.DEPTH_TEST);gl.depthMask(true);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
 const fov=2*Math.atan(Math.tan(19*Math.PI/180)*Math.max(1,VH/VW));
 const M=mul(persp(fov,VW/VH,Math.max(1,rad/1000),rad*10),lookAt(eye(),tgt,viewUp()));
 gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);gl.depthMask(false);
 if(T&&(LY('lyBub')||LY('lyPhase'))){drawTvol(T,M,field);updateScalarBar(T,field);}
 for(const o of TRACERGEOM){if((o.type==='tank'&&LY('lyTank'))||(o.type==='porous'&&LY('lyGeo'))||(o.type==='source'&&LY('lyCoil')))
  dL(o.mesh,o.type==='source'?[1,.7,.12,1]:o.type==='porous'?[.3,.9,.6,.9]:[.8,.85,.95,.65],M);}
 gl.depthMask(true);
 document.getElementById('tcbar').style.display=T&&(LY('lyBub')||LY('lyPhase'))?'flex':'none';
 const grad=document.querySelector('#tcbar .grad');if(grad){const colors=Array.from({length:9},(_,i)=>'rgb('+scalarRamp(field,i/8).map(Math.round).join(',')+')');grad.style.background='linear-gradient(to top,'+colors.join(',')+')';}
 if(REC)recTick();
}
function drawTracerOverlay(ctx,d){
 ctx.save();ctx.font=(12*d)+'px "Segoe UI",sans-serif';ctx.textBaseline='top';
 const field=tracerField(),range=(VIZCFG||CFG).scalar_ranges[field];
 const title=(field==='concentration'?'C/C_ref':'Q/C_ref (bulk)')+' · t = '+clock.toFixed(2)+' s';
 ctx.fillStyle='rgba(18,18,18,.8)';ctx.fillRect(10*d,10*d,ctx.measureText(title).width+20*d,30*d);
 ctx.fillStyle='#eeeeee';ctx.fillText(title,20*d,17*d);
 if(LY('lyBub')||LY('lyPhase')){
  const X=20*d,Y=55*d,H=120*d;
  for(let i=0;i<120;i++){ctx.fillStyle='rgb('+scalarRamp(field,1-i/119).map(Math.round).join(',')+')';ctx.fillRect(X,Y+i*d,12*d,d+1);}
  ctx.fillStyle='#eeeeee';ctx.fillText(fmtSci(range[1]),38*d,Y);ctx.fillText(fmtSci(range[0]),38*d,Y+H-12*d);
 }
 ctx.restore();
}
