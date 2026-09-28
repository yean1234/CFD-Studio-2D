import * as THREE from '/studies/three.module.js';

export function mountWarehouseViewer(root, onSettings) {
  root.className='warehouse-native';root.hidden=true;
  root.innerHTML=`<div data-wv="scene" class="wn-scene" tabindex="0" aria-label="저장고 3D Viewer"></div>
<div class="wn-title"><strong data-wv="title">실행 결과</strong><small data-wv="status" role="status"></small></div>
<aside class="wn-tools"><div class="wn-bar"><strong>결과 표시</strong><button data-wv="settings" class="btn">설정 보기</button></div>
<label>물리량<select data-wv="field"><option value="concentration">농도</option><option value="temperature">온도</option><option value="velocity">유속·방향</option></select></label>
<label>표시 영역<select data-wv="slice"><option value="all">전체</option><option value="aisle">중앙 통로 단면</option></select></label>
<div class="wn-gradient"></div><p data-wv="legend"></p>
<details><summary>위치·시간 조회</summary><form data-wv="probe"><div class="wn-grid"><label>X (m)<input data-wv="x" type="number" step="any" value="39" required></label><label>Y (m)<input data-wv="y" type="number" step="any" value="12.5" required></label><label>Z (m)<input data-wv="z" type="number" step="any" value="3" required></label><label>시간 (s)<input data-wv="time" type="number" step="any" value="0" required></label><label>최대 거리 (m)<input data-wv="distance" type="number" step="any" min="0.000001" value="3" required></label></div><button class="btn" type="submit">조회</button></form><p data-wv="probeResult"></p></details>
<details><summary>모델·검증</summary><div data-wv="facts"></div></details>
<details><summary>원본 파일</summary><p data-wv="sources"></p></details>
<div class="wn-bar"><button data-wv="reset" class="btn">시점 초기화</button><button data-wv="capture" class="btn">화면 저장</button><button data-wv="csv" class="btn">CSV 저장</button><button data-wv="video" class="btn">영상 저장</button></div>
</aside>
<div class="wn-timeline"><button data-wv="previous" class="btn" aria-label="이전 프레임">◀</button><button data-wv="play" class="btn pri">재생</button><button data-wv="next" class="btn" aria-label="다음 프레임">▶</button><input data-wv="frame" aria-label="저장 프레임" type="range" min="0" max="0" value="0" disabled><span data-wv="clock">0 s</span><select data-wv="speed" aria-label="재생 속도"><option value="0.5">0.5 프레임/s</option><option value="1" selected>1 프레임/s</option><option value="2">2 프레임/s</option><option value="4">4 프레임/s</option></select></div>`;
  const style=document.createElement('style');style.textContent=`
.warehouse-native{position:absolute;inset:0;z-index:3;background:var(--page);color:var(--ink);overflow:hidden}.warehouse-native[hidden]{display:none}.wn-scene{position:absolute;inset:85px 340px 100px 0;touch-action:none}.wn-scene canvas{display:block}.wn-title{position:absolute;left:16px;top:16px;max-width:calc(100% - 360px);pointer-events:none;background:#1a1a19da;padding:10px 14px;border:1px solid var(--line);border-radius:9px}.wn-title strong,.wn-title small{display:block;overflow-wrap:anywhere}.wn-title small{margin-top:6px;color:var(--ink2)}.wn-tools{position:absolute;right:16px;top:16px;width:295px;max-height:calc(100% - 110px);overflow:auto;background:#1a1a19ed;padding:14px;border:1px solid var(--line);border-radius:10px;font-size:12px}.wn-tools label{display:grid;gap:5px;margin:10px 0}.wn-tools select,.wn-tools input,.wn-timeline select{background:var(--surface2);color:var(--ink);border:1px solid var(--line);padding:7px;border-radius:5px;min-width:0;width:100%;font:inherit}.wn-tools p{font-size:11px;line-height:1.6;white-space:pre-wrap;overflow-wrap:anywhere}.wn-tools summary{cursor:pointer;padding:10px 0;border-top:1px solid var(--line)}.wn-tools strong{font-size:12px}.wn-tools [data-wv=facts]>div{margin:8px 0;display:grid;gap:4px}.wn-bar{display:flex;gap:6px;align-items:center;flex-wrap:wrap}.wn-bar strong{flex:1}.wn-bar .btn{font-size:11px;padding:6px 8px}.wn-gradient{height:8px;border-radius:4px;background:linear-gradient(90deg,blue,cyan,lime,yellow,red);margin-top:12px}.wn-grid{display:grid;grid-template-columns:1fr 1fr;gap:0 8px}.wn-timeline{position:absolute;left:16px;right:16px;bottom:16px;display:flex;align-items:center;gap:9px;padding:12px;background:#1a1a19ec;border:1px solid var(--line);border-radius:13px;font-size:12px}.wn-timeline input{flex:1;min-width:50px}.wn-timeline select{width:115px}.wn-timeline span{min-width:58px}.wn-timeline .btn{padding:7px 10px}@media(max-width:900px){.wn-scene{right:275px}.wn-tools{width:230px}.wn-title{max-width:calc(100% - 280px)}.wn-timeline{gap:5px}.wn-timeline select{width:85px}}
`;document.head.append(style);
  const $=id=>root.querySelector(`[data-wv="${id}"]`);
  let meta=null,scene,camera,renderer,points,currentFrame=null,rotation=0,tilt=0,frameGeneration=0,caseGeneration=0,playing=false,timer=null,request=null,recording=null;
  const saved=new Map(),cache=new Map();let resizeObserver;
  const events=new AbortController();
  async function api(path,signal){const response=await fetch(path,{signal});const data=await response.json();if(!response.ok)throw Error(data.error||data.msg||'결과 읽기 실패');return data;}
  function fact(label,value){const div=document.createElement('div'),a=document.createElement('span'),b=document.createElement('strong');a.textContent=label;b.textContent=String(value);div.append(a,b);$('facts').append(div);}
  function disposePoints(){if(points){scene.remove(points);points.traverse(p=>{p.geometry?.dispose();p.material?.dispose();});points=null;}}
  function pause(){playing=false;clearTimeout(timer);$('play').textContent='재생';}
  function remember(){if(meta)saved.set(meta.id,{frame:Number($('frame').value),field:$('field').value,slice:$('slice').value,rotation,tilt,camera:camera?.position.toArray()});}
  function resetCamera(){rotation=0;tilt=0;camera.position.set(0,25,Math.max(85,(meta?.geometry.length_m||78)*1.25));camera.lookAt(0,0,0);if(points)points.rotation.set(0,0,0);renderer.render(scene,camera);}
  function rendererReady(){if(renderer)return;scene=new THREE.Scene();scene.background=new THREE.Color(0x141819);camera=new THREE.PerspectiveCamera(45,1,.1,2000);renderer=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});renderer.setPixelRatio(Math.min(devicePixelRatio||1,2));$('scene').append(renderer.domElement);resetCamera();
    resizeObserver=new ResizeObserver(()=>{const host=$('scene');if(!host.clientWidth||!host.clientHeight)return;renderer.setSize(host.clientWidth,host.clientHeight);camera.aspect=host.clientWidth/host.clientHeight;camera.updateProjectionMatrix();renderer.render(scene,camera);});resizeObserver.observe($('scene'));
    let down=null;const host=$('scene');host.addEventListener('pointerdown',e=>{down=[e.clientX,e.clientY];host.setPointerCapture(e.pointerId);},{signal:events.signal});
    host.addEventListener('pointermove',e=>{if(!down||!points)return;const dx=e.clientX-down[0],dy=e.clientY-down[1];down=[e.clientX,e.clientY];if(e.shiftKey){camera.position.x-=dx*.06;camera.position.y+=dy*.06;}else{rotation+=dx*.008;tilt=Math.max(-1.5,Math.min(1.5,tilt+dy*.008));points.rotation.set(tilt,rotation,0);}renderer.render(scene,camera);},{signal:events.signal});
    for(const type of ['pointerup','pointercancel'])host.addEventListener(type,()=>{down=null;},{signal:events.signal});
    host.addEventListener('wheel',e=>{e.preventDefault();camera.position.multiplyScalar(e.deltaY>0?1.08:.92);renderer.render(scene,camera);},{passive:false,signal:events.signal});
  }
function showFrame(data) {
  rendererReady();
  if (points) {scene.remove(points); points.traverse(p => {p.geometry?.dispose(); p.material?.dispose();});}
  currentFrame = data;
  const field = $('field').value;
  const values = field === 'temperature' ? data.temperature_field_C : field === 'velocity' ? data.speed_m_s : data.concentration;
  const bounds = field === 'temperature' ? data.temperature_range_C : field === 'velocity' ? data.speed_range_m_s : [data.minimum, data.maximum];
  const unit = field === 'temperature' ? '°C' : field === 'velocity' ? 'm/s' : data.concentration_unit;
  const indices = data.cell_centres_m.map((_,i) => i).filter(i => $('slice').value === 'all' || Math.abs(data.cell_centres_m[i][1]-meta.geometry.width_m/2) <= .6);
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array(indices.length * 3);
  const colors = new Float32Array(indices.length * 3);
  const span = Math.max(bounds[1] - bounds[0], Number.EPSILON);
  for (let i = 0; i < indices.length; i++) {
    const sourceIndex = indices[i];
    const xyz = data.cell_centres_m[sourceIndex];
    positions[3*i] = xyz[0] - meta.geometry.length_m/2;
    positions[3*i+1] = xyz[2] - (meta.geometry.eaves_m+meta.geometry.roof_rise_m)/2;
    positions[3*i+2] = xyz[1] - meta.geometry.width_m/2;
    const ratio = Math.max(0, Math.min(1, (values[sourceIndex]-bounds[0])/span));
    const c = new THREE.Color().setHSL((1-ratio)*0.66, 0.9, 0.56);
    colors[3*i] = c.r; colors[3*i+1] = c.g; colors[3*i+2] = c.b;
  }
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  points = new THREE.Group();
  points.add(new THREE.Points(geometry, new THREE.PointsMaterial({size: 1.0, vertexColors: true, sizeAttenuation: true})));
  if (field === 'velocity' && bounds[1] > 0) {
    const stride = Math.max(1, Math.ceil(indices.length / 180));
    for (let j=0; j<indices.length; j+=stride) {
      const i=indices[j], xyz=data.cell_centres_m[i], u=data.velocity_m_s[i];
      const magnitude=data.speed_m_s[i];
      if (magnitude < bounds[1]*.03) continue;
      const direction=new THREE.Vector3(u[0],u[2],u[1]).normalize();
      const origin=new THREE.Vector3(xyz[0]-meta.geometry.length_m/2,
        xyz[2]-(meta.geometry.eaves_m+meta.geometry.roof_rise_m)/2,xyz[1]-meta.geometry.width_m/2);
      points.add(new THREE.ArrowHelper(direction,origin,3*magnitude/bounds[1],0xffffff,.4,.2));
    }
  }
  for (const block of meta.loading?.blocks || []) {
    const lo=block.min_m, hi=block.max_m;
    const box = new THREE.BoxGeometry(hi[0]-lo[0],hi[2]-lo[2],hi[1]-lo[1]);
    const outline = new THREE.LineSegments(new THREE.EdgesGeometry(box), new THREE.LineBasicMaterial({color:0xffffff}));
    box.dispose();
    outline.position.set((hi[0]+lo[0]-meta.geometry.length_m)/2,
      (hi[2]+lo[2]-meta.geometry.eaves_m-meta.geometry.roof_rise_m)/2,
      (hi[1]+lo[1]-meta.geometry.width_m)/2);
    points.add(outline);
  }
  const L=meta.geometry.length_m/2,W=meta.geometry.width_m/2,H=(meta.geometry.eaves_m+meta.geometry.roof_rise_m)/2,E=meta.geometry.eaves_m-H;
  const vertices=[[-L,-H,-W],[L,-H,-W],[L,-H,W],[-L,-H,W],[-L,E,-W],[L,E,-W],[L,E,W],[-L,E,W],[-L,H,0],[L,H,0]];
  const edges=[[0,1],[1,2],[2,3],[3,0],[0,4],[1,5],[2,6],[3,7],[4,5],[6,7],[4,8],[7,8],[5,9],[6,9],[8,9]];
  const outlineGeometry=new THREE.BufferGeometry().setFromPoints(edges.flatMap(pair=>pair.map(i=>new THREE.Vector3(...vertices[i]))));
  points.add(new THREE.LineSegments(outlineGeometry,new THREE.LineBasicMaterial({color:0x8c969f,transparent:true,opacity:.45})));
  points.rotation.set(tilt, rotation, 0);
  scene.add(points);
  renderer.render(scene, camera);
  $('status').textContent='원본장 대조 통과 · '+data.total_cells.toLocaleString()+'셀';
  if(document.activeElement!==$('time'))$('time').value = data.time_s;
  $('clock').textContent=data.time_s+' s';
  $('legend').textContent = `${data.time_s} s (${(data.time_s/3600).toFixed(2)} h) · ${bounds[0].toPrecision(5)}–${bounds[1].toPrecision(5)} ${unit} · 파랑: 낮음 / 빨강: 높음 (프레임별 범위) · 표시 ${indices.length.toLocaleString()} / 전체 ${data.total_cells.toLocaleString()}셀 · 원본장 대조 통과` + (field === 'velocity' ? ' · 화살표: 방향, 길이: 현재 최대속도 대비 상대값' : '') + (data.temperature_C == null ? '' : ` · 가정 기온 ${data.temperature_C.toFixed(2)} °C`);
  $('sources').textContent = `원본장: ${data.source_files ? Object.values(data.source_files).join(' , ') : data.raw_file}`;
}
  function stopVideo(discard=false){if(recording&&recording.state!=='inactive'){recording.discard=discard;recording.stop();}$('video').textContent='영상 저장';}
  function download(blob,name){const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  async function loadFrame(){const generation=++frameGeneration;if(!meta)return false;request?.abort();request=new AbortController();const index=Number($('frame').value),key=meta.id+':'+index;$('status').textContent='프레임 불러오는 중';
    try{const data=cache.get(key)||await api(`/api/warehouse/results/frame?id=${encodeURIComponent(meta.id)}&index=${index}`,request.signal);if(generation!==frameGeneration)return false;cache.set(key,data);while(cache.size>6)cache.delete(cache.keys().next().value);showFrame(data);return true;}
    catch(e){if(e.name!=='AbortError'&&generation===frameGeneration){pause();stopVideo(true);$('status').textContent=e.message;}if(generation===frameGeneration)$('play').disabled=!currentFrame;return false;}
  }
  async function tick(){if(!playing||!meta||root.hidden)return;const i=Number($('frame').value);if(i>=Number($('frame').max)){pause();stopVideo();return;}$('frame').value=i+1;const ok=await loadFrame();if(playing&&ok)timer=setTimeout(tick,1000/Number($('speed').value));}
  async function play(){if(!meta||!currentFrame)return;if(playing){pause();return;}playing=true;$('play').textContent='일시정지';if(Number($('frame').value)>=Number($('frame').max)){$('frame').value=0;if(!await loadFrame())return;}timer=setTimeout(tick,1000/Number($('speed').value));}
  async function load(id,title){remember();pause();stopVideo(true);request?.abort();const generation=++caseGeneration;++frameGeneration;meta=null;currentFrame=null;root.hidden=false;rendererReady();disposePoints();renderer.render(scene,camera);$('title').textContent=title;$('status').textContent='결과 불러오는 중';$('sources').textContent='';$('legend').textContent='';$('facts').replaceChildren();$('probeResult').textContent='';$('clock').textContent='—';for(const control of root.querySelectorAll('button,input,select'))if(control!==$('settings'))control.disabled=true;
    try{const loaded=await api('/api/warehouse/results/meta?id='+encodeURIComponent(id));if(generation!==caseGeneration)return;meta=loaded;const state=saved.get(id);for(const o of $('field').options)o.disabled=!(meta.available_fields||['concentration']).includes(o.value);$('field').value=state?.field&&meta.available_fields.includes(state.field)?state.field:'concentration';$('slice').value=state?.slice||'all';$('frame').max=meta.times_s.length-1;$('frame').value=Math.min(state?.frame||0,Number($('frame').max));$('frame').disabled=false;resetCamera();if(state){rotation=state.rotation;tilt=state.tilt;if(state.camera)camera.position.fromArray(state.camera);}
      fact('계산 모델',meta.model==='clo2_coupled_scenario'?'유동·온도·ClO₂ 연결':meta.model==='normalized_gable_verification'?'정규화 추적자 시험':'가정 기반 확산');fact('수치 검증',meta.grid_assessment&&!meta.grid_assessment.grid_converged?'격자 수렴 기준 미달':meta.numerical_pass?'해당 시험 통과':'수렴 미검증');fact('실험 검증','미완료');fact('셀 수',meta.cells.toLocaleString());fact('농도 단위',meta.concentration_unit==='kg/m3'?'mg/m³ · 원본 kg/m³':meta.concentration_unit);fact('누출','해석 범위에서 제외');fact('질량수지 상대오차',meta.relative_balance_error);if(meta.loading)fact('다공성 곡물',meta.loading.blocks.length+'개 적재 블록 · 공극률 '+meta.loading.porosity);for(const assumption of meta.assumptions||[])fact('가정',assumption);
      if(await loadFrame()&&generation===caseGeneration)for(const control of root.querySelectorAll('button,input,select'))control.disabled=false;
    }catch(e){if(generation===caseGeneration)$('status').textContent=e.message;}
  }
  function hide(){remember();pause();stopVideo(true);request?.abort();caseGeneration++;frameGeneration++;root.hidden=true;}
  $('settings').onclick=onSettings;$('play').onclick=play;$('frame').oninput=()=>{pause();loadFrame();};
  for(const [id,step] of [['previous',-1],['next',1]])$(id).onclick=()=>{if(!meta)return;pause();$('frame').value=Math.max(0,Math.min(Number($('frame').max),Number($('frame').value)+step));loadFrame();};
  for(const id of ['field','slice'])$(id).onchange=()=>{if(currentFrame)showFrame(currentFrame);};
  $('reset').onclick=()=>{if(renderer)resetCamera();};$('capture').onclick=()=>{if(renderer&&currentFrame){renderer.render(scene,camera);renderer.domElement.toBlob(blob=>{if(blob)download(blob,meta.id+'_'+currentFrame.time_s+'s.png');});}};
  $('csv').onclick=()=>{if(!currentFrame)return;const f=currentFrame;const rows=[['time_s','cell_index','x_m','y_m','z_m','concentration_'+f.concentration_unit,'temperature_C','Ux_m_s','Uy_m_s','Uz_m_s']];f.cell_centres_m.forEach((xyz,i)=>rows.push([f.time_s,i*f.sampling_stride,...xyz,f.concentration[i],f.temperature_field_C?.[i]??'',...(f.velocity_m_s?.[i]||['','',''])]));download(new Blob([rows.map(r=>r.join(',')).join('\n')],{type:'text/csv'}),meta.id+'_'+f.time_s+'s_sampled.csv');};
  $('video').onclick=async()=>{if(!currentFrame)return;if(recording){if(recording.state!=='inactive'){pause();stopVideo();}return;}try{if(typeof MediaRecorder==='undefined')throw Error('이 브라우저에서는 영상 저장을 지원하지 않습니다');pause();$('frame').value=0;if(!await loadFrame())return;const stream=renderer.domElement.captureStream(15);recording=new MediaRecorder(stream);const session=recording;session.discard=false;const chunks=[],name=meta.id;recording.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};recording.onstop=()=>{stream.getTracks().forEach(t=>t.stop());if(!session.discard)download(new Blob(chunks,{type:'video/webm'}),name+'.webm');if(recording===session)recording=null;};recording.start();$('video').textContent='영상 저장 종료';play();}catch(e){$('status').textContent=e.message;}};
  $('probe').onsubmit=async e=>{e.preventDefault();if(!meta)return;const token=caseGeneration;const p=new URLSearchParams({id:meta.id,x:$('x').value,y:$('y').value,z:$('z').value,time:$('time').value,max_distance:$('distance').value});try{const v=await api('/api/warehouse/results/sample?'+p);if(token!==caseGeneration)return;$('probeResult').textContent=`농도 ${v.concentration.toPrecision(7)} ${v.concentration_unit}\n온도 ${v.temperature==null?'계산되지 않음':v.temperature.toFixed(3)+' °C'}\n유속 ${v.speed_m_s==null?'계산되지 않음':v.speed_m_s.toPrecision(6)+' m/s'}\n셀 ${v.cell_index} · 중심 거리 ${v.cell_centre_distance_m.toPrecision(4)} m\n원본 ${v.source_files.join(' , ')}`;}catch(e){if(token===caseGeneration)$('probeResult').textContent=e.message;}};
  root.addEventListener('keydown',e=>{if(['INPUT','SELECT','TEXTAREA','BUTTON'].includes(e.target.tagName))return;if(e.code==='Space'){e.preventDefault();play();}else if(e.key==='ArrowLeft')$('previous').click();else if(e.key==='ArrowRight')$('next').click();},{signal:events.signal});
  return {load,hide,pause,destroy(){hide();events.abort();resizeObserver?.disconnect();disposePoints();renderer?.dispose();style.remove();root.replaceChildren();}};
}
