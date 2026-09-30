/* Spatial JSON editor and geometry preview. Never executes user code or a solver. */
(()=>{
 const keys=['geometry','geometry_spec','domain','regions','tank','layers','board','coil','loading','silo','published','probes_mm','heater'];
 const clone=x=>structuredClone(x),isObject=x=>x&&typeof x==='object'&&!Array.isArray(x);
 function parse(text){
  if(text.length>1000000)throw Error('공간 JSON은 1 MB 이하로 입력하세요');
  const value=JSON.parse(text);if(!isObject(value))throw Error('공간 JSON 객체를 입력하세요');
  let count=0;
  function visit(x,depth){if(++count>20000||depth>20)throw Error('공간 JSON이 너무 복잡합니다');if(typeof x==='number'&&!Number.isFinite(x))throw Error('유한한 숫자를 입력하세요');if(x&&typeof x==='object')for(const [k,v]of Object.entries(x)){if(['__proto__','constructor','prototype'].includes(k))throw Error('허용되지 않는 JSON 키');visit(v,depth+1);}}
  visit(value,0);return value;
 }
 function extract(config){return Object.fromEntries(keys.filter(k=>Object.hasOwn(config,k)).map(k=>[k,clone(config[k])]));}
 function merge(config,spatial){for(const k of Object.keys(spatial))if(!keys.includes(k))throw Error('공간 항목이 아닙니다: '+k);const next=clone(config);for(const k of keys)delete next[k];return Object.assign(next,clone(spatial));}
 // A spatial document groups original Config paths without inventing dimensions.
 // Mixed legacy components keep all properties so their geometry remains reproducible.
 const documentGroups={
  geometry:['geometry','geometry_spec','domain','regions','coordinate_system','tank','layers','board','coil','heater','loading','silo','published'],
  mesh:['mesh','porous_mesh'],
  boundaries:['interfaces','boundary_conditions'],
  observations:['probes','probes_mm']
 };
 function spatialDocument(config){
  const sections=Object.fromEntries(Object.entries(documentGroups).map(([group,roots])=>[group,Object.fromEntries(roots.filter(k=>Object.hasOwn(config,k)).map(k=>[k,clone(config[k])]))]));
  if(isObject(config.outputs)&&Object.hasOwn(config.outputs,'probes'))sections.observations.outputs={probes:clone(config.outputs.probes)};
  return {format:'cfd-spatial-config',version:1,sections};
 }
 function mergeDocument(config,input){
  const value=parse(JSON.stringify(input));
  if(value.format!=='cfd-spatial-config'||value.version!==1||!isObject(value.sections))throw Error('공간 JSON의 format·version·sections를 유지하세요');
  if(Object.keys(value).some(k=>!['format','version','sections'].includes(k)))throw Error('공간 JSON 최상위 항목을 확인하세요');
  if(Object.keys(value.sections).some(k=>!Object.hasOwn(documentGroups,k)))throw Error('공간 JSON 분류를 확인하세요');
  const original=spatialDocument(config),next=clone(config);
  for(const [group,roots]of Object.entries(documentGroups)){
   const section=value.sections[group];
   if(!isObject(section))throw Error('공간 JSON 분류를 유지하세요: '+group);
   for(const key of Object.keys(original.sections[group]))if(!Object.hasOwn(section,key))throw Error('기존 공간 항목을 유지하세요: '+group+'.'+key);
   for(const [key,content]of Object.entries(section)){
    if(group==='observations'&&key==='outputs'){
     if(!isObject(content)||Object.keys(content).some(k=>k!=='probes')||!Object.hasOwn(content,'probes'))throw Error('observations.outputs에는 probes만 입력하세요');
     next.outputs={...next.outputs,probes:clone(content.probes)};
    }else{if(!roots.includes(key))throw Error('공간 JSON 분류에 맞지 않는 항목: '+group+'.'+key);next[key]=clone(content);}
   }
  }
  return next;
 }
 // Only geometry is inherited; operating values in legacy components remain project inputs.
 function isGeometryPath(path){
  const [root,key]=path;
  if(['geometry','domain','regions','geometry_spec','loading','silo','published','probes_mm'].includes(root))return true;
  if(['tank','board','coil'].includes(root))return ['width_mm','depth_mm','liquid_height_mm','x0','x1','y0','y1','z0','z1','name','role','config_bindings'].includes(key);
  if(root==='layers')return ['dielectric_mm','air_mm'].includes(key);
  return root==='heater'&&key==='cpus';
 }
 const pathId=path=>JSON.stringify(path);
 function at(config,path){return path.reduce((obj,key)=>obj?.[key],config);}
 function elements(config){
  const out=[];
  const add=path=>{const value=at(config,path);if(isObject(value))out.push({path,id:pathId(path),label:value.name||(typeof path.at(-1)==='number'?String(path.at(-2))+' '+(path.at(-1)+1):String(path.at(-1))),value});};
  const collection=path=>{const value=at(config,path);if(Array.isArray(value))value.forEach((_,i)=>add([...path,i]));else if(isObject(value))Object.keys(value).forEach(k=>add([...path,k]));};
  if(config.geometry?.shape||config.geometry?.type)add(['geometry']);
  else for(const key of ['regions','fluid_regions','solid_regions'])collection(['geometry',key]);
  if(config.domain)add(['domain']);collection(['regions']);
  if(config.geometry_spec?.geometry)add(['geometry_spec','geometry']);
  for(const key of ['tank','board','coil'])if(config[key])add([key]);
  collection(['loading','blocks']);collection(['heater','cpus']);
  // Names are presentation only; exact paths retain keys containing punctuation.
  return out.map(e=>({...e,label:typeof e.label==='string'?e.label:e.path.join(' / ')}));
 }
 function shapes(config){
  const items=[],notes=[],up=config.tank?[0,1,0]:[0,0,1];
  const num=(x,label,positive=false)=>{if(typeof x!=='number'||!Number.isFinite(x)||(positive&&x<=0))throw Error(label+' 숫자·범위를 확인하세요');return x;};
  const vector=(x,label)=>{if(!Array.isArray(x)||x.length!==3)throw Error(label+'에 좌표 3개를 입력하세요');return x.map(v=>num(v,label));};
  const box=(name,min,max,scale=1,meta={})=>{min=vector(min,name+'.min').map(v=>v*scale);max=vector(max,name+'.max').map(v=>v*scale);if(max.some((v,i)=>v<=min[i]))throw Error(name+' 최대 좌표는 최소 좌표보다 커야 합니다');items.push({kind:'box',name,min,max,...meta});};
  const ready=values=>values.every(x=>x!==null&&x!==undefined&&x!=='');
  const g=config.geometry_spec?.geometry;
  if(g){const a=[g.length_m,g.width_m,g.eaves_m,g.roof_rise_m];if(ready(a)){a.forEach((x,i)=>num(x,'geometry_spec.geometry',i<3));if(a[3]<0)throw Error('roof_rise_m은 0 이상이어야 합니다');items.push({kind:'gable',name:'geometry_spec.geometry',size:a,path:['geometry_spec','geometry']});}else notes.push('geometry_spec.geometry: 치수 미입력');}
  if(config.tank){const t=config.tank,a=[t.width_mm,t.liquid_height_mm,t.depth_mm];if(ready(a))box('tank',[0,0,0],a,.001,{path:['tank']});else notes.push('tank: 치수 미입력');
   for(const key of ['board','coil'])if(config[key]){const b=config[key],a=['x0','y0','z0','x1','y1','z1'].map(k=>b[k]);if(ready(a))box(key,a.slice(0,3),a.slice(3),.001,{path:[key]});else notes.push(key+': 치수 미입력');}
   for(const [i,cpu]of (config.heater?.cpus||[]).entries()){const a=[cpu.x0,cpu.x1,cpu.y0,cpu.y1,config.board?.z1];if(ready(a)){a.forEach(x=>num(x,'heater.cpus'));if(a[1]<=a[0]||a[3]<=a[2])throw Error('발열면 최대 좌표는 최소 좌표보다 커야 합니다');items.push({kind:'surface',name:'heater.cpus.'+i,path:['heater','cpus',i],center:[(a[0]+a[1])*.0005,(a[2]+a[3])*.0005,a[4]*.001],width:(a[1]-a[0])*.001,height:(a[3]-a[2])*.001});}else notes.push('heater.cpus.'+i+': 치수 미입력');}
   notes.push('상분율·계산 격자는 표시하지 않음');
  }
  for(const [i,b]of (config.loading?.blocks||[]).entries())box('loading.blocks['+i+']',b.min_m,b.max_m,1,{path:['loading','blocks',i]});
  function region(r,name,inheritedUnit,path){
   if(!isObject(r)){notes.push(name+': 지원하지 않는 형식');return;}
   const shape=r.shape||r.type;
   if(!shape){notes.push(name+': shape 미입력');return;}
   const unit=r.unit||inheritedUnit,scale={m:1,cm:.01,mm:.001}[unit];
   if(!scale)throw Error(name+': unit에 m, cm 또는 mm를 입력하세요');
   if(!['box','sphere','cylinder'].includes(shape)){notes.push(name+': 지원하지 않는 shape '+String(shape));return;}
   const dimensions=shape==='box'?[...(r.min||[]),...(r.max||[])]:shape==='sphere'?[...(r.center||[]),r.radius]:[...(r.center||[]),r.radius,r.height];if(!ready(dimensions)){notes.push(name+': 치수 미입력');return;}
   if(shape==='box')box(name,r.min,r.max,scale,{path});
   else if(shape==='sphere'){const center=vector(r.center,name+'.center').map(v=>v*scale),radius=num(r.radius,name+'.radius',true)*scale;items.push({kind:'sphere',name,center,radius,path});}
   else if(shape==='cylinder'){const center=vector(r.center,name+'.center').map(v=>v*scale),radius=num(r.radius,name+'.radius',true)*scale,height=num(r.height,name+'.height',true)*scale;if(!['x','y','z'].includes(r.axis))throw Error(name+': axis에 x, y 또는 z를 입력하세요');items.push({kind:'cylinder',name,center,radius,height,axis:r.axis,path});}
   else notes.push(name+': 지원하지 않는 shape '+String(shape));
  }
  function regions(value,path,unit){if(Array.isArray(value)){value.forEach((r,i)=>region(r,[...path,i].join('.'),unit,[...path,i]));}else if(isObject(value)){Object.entries(value).forEach(([k,r])=>region(r,[...path,k].join('.'),unit,[...path,k]));}else if(value!=null)notes.push(path.join('.')+': 지원하지 않는 형식');}
  if(config.geometry){const g=config.geometry;if(g.source)notes.push('geometry.source: 외부 형상 파일은 미리보기에 포함되지 않음');if(g.shape||g.type)region(g,'geometry',g.unit,['geometry']);else for(const key of ['regions','fluid_regions','solid_regions'])if(g[key])regions(g[key],['geometry',key],g.unit);}
  if(config.domain)region(config.domain,'domain',config.domain.unit,['domain']);
  if(config.regions)regions(config.regions,['regions']);
  if(config.silo||config.published)notes.push('silo·published: 외부 격자 형상은 미리보기 미지원');
  if(config.probes_mm)notes.push('probes_mm: 측정 지점은 미리보기에 포함되지 않음');
  if(items.length>1000)throw Error('미리보기 형상은 1000개 이하로 입력하세요');
  if(!items.length)notes.push('표시할 형상이 없습니다 · 치수와 형식을 확인하세요');
  const names=new Map(elements(config).map(e=>[e.id,e.label]));for(const item of items){item.id=pathId(item.path);item.label=names.get(item.id)||item.name;}
  return {items,notes,up};
 }
 async function viewer(host,model,{onSelect=null,selected=null,cameraState=null}={}){
  const T=await import('/studies/three.module.js');
  const scene=new T.Scene();scene.background=new T.Color('#111315');
  const camera=new T.PerspectiveCamera(40,1,.001,1000),renderer=new T.WebGLRenderer({antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));host.append(renderer.domElement);
  const group=new T.Group();scene.add(group);const disposables=[],tags=[],meshes=[];const overlay=document.createElement('div');overlay.className='sp-tags';host.append(overlay);
  const svgNS='http://www.w3.org/2000/svg',leaders=document.createElementNS(svgNS,'svg');leaders.classList.add('sp-leaders');leaders.setAttribute('aria-hidden','true');overlay.append(leaders);
  try{
   for(const [i,item]of model.items.entries()){
    let geometry,mesh;
    if(item.kind==='box'){geometry=new T.BoxGeometry(...item.max.map((v,k)=>v-item.min[k]));}
    else if(item.kind==='surface')geometry=new T.PlaneGeometry(item.width,item.height);
    else if(item.kind==='sphere')geometry=new T.SphereGeometry(item.radius,24,16);
    else if(item.kind==='cylinder')geometry=new T.CylinderGeometry(item.radius,item.radius,item.height,32);
    else{const [l,w,h,r]=item.size,points=[0,0,0,l,0,0,l,w,0,0,w,0,0,0,h,l,0,h,l,w,h,0,w,h,0,w/2,h+r,l,w/2,h+r];geometry=new T.BufferGeometry();geometry.setAttribute('position',new T.Float32BufferAttribute(points,3));geometry.setIndex([0,2,1,0,3,2,0,1,5,0,5,4,3,7,6,3,6,2,4,5,9,4,9,8,8,9,6,8,6,7,0,4,8,0,8,7,0,7,3,1,2,6,1,6,9,1,9,5]);geometry.computeVertexNormals();}
    const color=new T.Color().setHSL((.57+i*.12)%1,.58,.58),material=new T.MeshBasicMaterial({color,transparent:true,opacity:.15,side:T.DoubleSide,depthWrite:false});mesh=new T.Mesh(geometry,material);disposables.push(geometry,material);
    const edgeGeometry=new T.EdgesGeometry(geometry),edgeMaterial=new T.LineBasicMaterial({color});mesh.add(new T.LineSegments(edgeGeometry,edgeMaterial));disposables.push(edgeGeometry,edgeMaterial);
    if(item.kind==='box')mesh.position.fromArray(item.min.map((v,k)=>(v+item.max[k])/2));
    else if(item.center)mesh.position.fromArray(item.center);
    if(item.kind==='cylinder'){if(item.axis==='z')mesh.rotation.x=Math.PI/2;if(item.axis==='x')mesh.rotation.z=Math.PI/2;}
    group.add(mesh);meshes.push(mesh);mesh.userData.elementId=item.id;
    if(onSelect){const tag=document.createElement('button');tag.type='button';tag.className='sp-tag';tag.textContent=item.label||item.name;tag.setAttribute('translate','no');tag.dataset.elementId=item.id;tag.onclick=()=>onSelect(item.id);tag.title=item.label||item.name;overlay.append(tag);
     const line=document.createElementNS(svgNS,'polyline'),dot=document.createElementNS(svgNS,'circle');line.setAttribute('fill','none');dot.setAttribute('r','2.5');const leader=document.createElementNS(svgNS,'g');leader.style.color='#'+color.getHexString();leader.append(line,dot);leaders.append(leader);tags.push({tag,mesh,leader,line,dot});}

   }
   const bounds=new T.Box3().setFromObject(group),size=bounds.getSize(new T.Vector3()),center=bounds.getCenter(new T.Vector3()),extent=Math.max(size.x,size.y,size.z);
   if(!Number.isFinite(extent)||extent<=0)throw Error('형상 크기를 확인하세요');group.position.copy(center).multiplyScalar(-1);group.scale.setScalar(1/extent);group.position.divideScalar(extent);
   camera.up.fromArray(model.up);
   let yaw=cameraState?.yaw??-.6,pitch=cameraState?.pitch??.4,distance=cameraState?.distance??2.8,pointer=null;
   const draw=()=>{
    const width=host.clientWidth,height=host.clientHeight;if(!width||!height)return;
    const zUp=model.up[2]===1,p=[Math.cos(pitch)*Math.cos(yaw)*distance,Math.cos(pitch)*Math.sin(yaw)*distance,Math.sin(pitch)*distance];
    camera.position.fromArray(zUp?p:[p[0],p[2],p[1]]);camera.lookAt(0,0,0);renderer.render(scene,camera);
    leaders.setAttribute('viewBox',`0 0 ${width} ${height}`);
    const positions=tags.map(entry=>{
     const point=new T.Box3().setFromObject(entry.mesh).getCenter(new T.Vector3()).project(camera);
     const visible=point.z>=-1&&point.z<=1&&Math.abs(point.x)<=1&&Math.abs(point.y)<=1;
     entry.tag.hidden=!visible;entry.leader.style.display=visible?'':'none';
     entry.tag.style.maxWidth=Math.min(144,Math.max(76,width*.23))+'px';
     return {...entry,visible,anchorX:(point.x+1)*width/2,anchorY:(1-point.y)*height/2};
    }).filter(p=>p.visible).sort((a,b)=>a.anchorX-b.anchorX);
    // Two outer lanes keep names away from the geometry. Sort each lane vertically
    // so nearby anchors keep the same order and leader lines cross less often.
    const middle=Math.ceil(positions.length/2);
    for(const [side,lane]of [[-1,positions.slice(0,middle)],[1,positions.slice(middle)]]){
     lane.sort((a,b)=>a.anchorY-b.anchorY);
     const gap=8,margin=12,heights=lane.map(p=>p.tag.offsetHeight),total=heights.reduce((a,b)=>a+b,0)+Math.max(0,lane.length-1)*gap;
     let bottom=margin;
     lane.forEach((p,i)=>{p.y=Math.max(bottom+heights[i]/2,Math.min(height-margin-heights[i]/2,p.anchorY));bottom=p.y+heights[i]/2+gap;});
     // Fit the last labels back into view, then distribute crowded lanes evenly.
     let top=height-margin;
     for(let i=lane.length-1;i>=0;i--){lane[i].y=Math.min(lane[i].y,top-heights[i]/2);top=lane[i].y-heights[i]/2-gap;}
     lane.forEach((p,i)=>{
      const w=p.tag.offsetWidth,h=heights[i];if(total>height-2*margin)p.y=margin+h/2+i*Math.max(0,(height-2*margin-h)/Math.max(1,lane.length-1));
      const x=side<0?margin+w/2:width-margin-w/2,edge=x-side*w/2,elbow=edge-side*16;
      p.tag.style.left=x+'px';p.tag.style.top=p.y+'px';
      p.line.setAttribute('points',`${p.anchorX},${p.anchorY} ${elbow},${p.y} ${edge},${p.y}`);
      p.dot.setAttribute('cx',p.anchorX);p.dot.setAttribute('cy',p.anchorY);
     });
    }
   };
   const resize=new ResizeObserver(()=>{const w=host.clientWidth,h=host.clientHeight;if(!w||!h)return;renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix();draw();});resize.observe(host);
   const canvas=renderer.domElement;canvas.style.touchAction='none';canvas.setAttribute('aria-label','공간 3D 미리보기');
   canvas.onpointerdown=e=>{if(e.button!==0)return;pointer={id:e.pointerId,x:e.clientX,y:e.clientY,startX:e.clientX,startY:e.clientY};canvas.setPointerCapture(e.pointerId);};
   canvas.onpointermove=e=>{if(!pointer)return;yaw-=(e.clientX-pointer.x)*.007;pitch=Math.max(-1.45,Math.min(1.45,pitch+(e.clientY-pointer.y)*.007));pointer.x=e.clientX;pointer.y=e.clientY;draw();};canvas.onpointerup=e=>{if(pointer&&Math.hypot(e.clientX-pointer.startX,e.clientY-pointer.startY)<4&&onSelect){const r=canvas.getBoundingClientRect(),ray=new T.Raycaster();ray.setFromCamera(new T.Vector2(2*(e.clientX-r.left)/r.width-1,1-2*(e.clientY-r.top)/r.height),camera);const hit=ray.intersectObjects(meshes,false)[0];if(hit)onSelect(hit.object.userData.elementId);}pointer=null;};canvas.onpointercancel=()=>pointer=null;
   canvas.addEventListener('wheel',e=>{e.preventDefault();distance=Math.max(1,Math.min(15,distance*Math.exp(Math.max(-100,Math.min(100,e.deltaY))*.001)));draw();},{passive:false});
   canvas.ondblclick=()=>{yaw=-.6;pitch=.4;distance=2.8;draw();};draw();
   const dispose=()=>{resize.disconnect();disposables.forEach(x=>x.dispose());renderer.dispose();renderer.domElement.remove();overlay.remove();};
   dispose.select=id=>{for(const mesh of meshes)mesh.material.opacity=mesh.userData.elementId===id ? .4 : .15;for(const {tag,leader}of tags){const active=tag.dataset.elementId===id;tag.setAttribute('aria-pressed',String(active));leader.classList.toggle('selected',active);}draw();};
   dispose.select(selected);dispose.cameraState=()=>({yaw,pitch,distance});return dispose;
  }catch(e){overlay.remove();disposables.forEach(x=>x.dispose());renderer.dispose();renderer.domElement.remove();throw e;}
 }
 function open({config,schema=null,schemaOnly=false,readonly=false,onApply}){
  const base=clone(config),original=schema?clone(schema):null;
  const el=(tag,text,cls)=>{const x=document.createElement(tag);if(text!==undefined)x.textContent=text;if(cls)x.className=cls;return x;};
  if(!document.getElementById('spatialStyle')){const style=el('style');style.id='spatialStyle';style.textContent=`.sp-dialog{box-sizing:border-box;width:min(1280px,96vw);max-width:1280px;height:min(840px,92vh);padding:22px;border:1px solid var(--line);border-radius:14px;background:var(--surface,var(--page));color:var(--ink);overflow:auto}.sp-dialog[open]{display:flex;flex-direction:column;gap:14px}.sp-dialog::backdrop{background:#000a}.sp-header,.sp-actions{display:flex;align-items:center;gap:10px}.sp-header h2{font-size:18px;margin:0;flex:1}.sp-actions{justify-content:flex-end}.sp-body{display:grid;grid-template-columns:1fr 1fr;gap:14px;flex:1;min-height:280px}.sp-code,.sp-preview{min-width:0;min-height:0;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:var(--page)}.sp-code{display:flex;flex-direction:column}.sp-code label,.sp-preview-label{font-size:12px;padding:12px;display:block;border-bottom:1px solid var(--line)}.sp-code textarea{flex:1;min-height:0;resize:none;border:0;width:100%;box-sizing:border-box;padding:14px;color:var(--ink);background:var(--page);font:12px/1.7 Consolas,monospace;tab-size:2;white-space:pre;overflow:auto;user-select:text}.sp-preview{display:flex;flex-direction:column}.sp-canvas{flex:1;min-height:160px;position:relative}.sp-canvas canvas{display:block;width:100%;height:100%}.sp-empty{position:absolute;inset:0;display:grid;place-content:center;padding:20px;font-size:12px;color:var(--muted)}.sp-report{padding:10px 12px;max-height:100px;overflow:auto;font-size:11px;white-space:pre-wrap;border-top:1px solid var(--line);color:var(--muted)}.sp-error{color:#ff9292;font-size:12px;margin:0;white-space:pre-wrap}.sp-note{font-size:11px;color:var(--muted);margin:0}.sp-dialog details{font-size:11px;max-height:140px;overflow:auto}.sp-dialog pre{white-space:pre-wrap;user-select:text}@media(max-width:800px){.sp-body{grid-template-columns:1fr;flex:none}.sp-code,.sp-preview{height:320px}}`;document.head.append(style);}
  const dialog=el('dialog',undefined,'sp-dialog'),header=el('div',undefined,'sp-header'),body=el('div',undefined,'sp-body'),code=el('div',undefined,'sp-code'),preview=el('div',undefined,'sp-preview'),host=el('div',undefined,'sp-canvas'),report=el('div',undefined,'sp-report'),error=el('p','', 'sp-error'),actions=el('div',undefined,'sp-actions');error.setAttribute('role','alert');report.setAttribute('role','status');
  const button=(label,fn)=>{const b=el('button',label,'btn');b.type='button';b.onclick=fn;return b;};
  const textarea=el('textarea');textarea.setAttribute('aria-label',schemaOnly?'초기 형상 JSON':'공간 JSON');textarea.setAttribute('translate','no');textarea.spellcheck=false;textarea.readOnly=readonly;
  const initial=extract(base);textarea.value=JSON.stringify(initial,null,2);
  const read=()=>{const value=parse(textarea.value);merge({},value);return {value};};
  let clean=null,generation=0,closed=false;
  const clear=()=>{generation++;clean?.();clean=null;host.replaceChildren();report.textContent='';};
  const placeholder=text=>{host.replaceChildren(el('div',text,'sp-empty'));};placeholder('형상 확인을 눌러 미리보기');
  textarea.oninput=()=>{clear();placeholder('입력이 변경되었습니다 · 형상 확인을 눌러 갱신');error.textContent='';};
  textarea.onkeydown=e=>{if(e.key==='Tab'&&!readonly){e.preventDefault();textarea.setRangeText('  ',textarea.selectionStart,textarea.selectionEnd,'end');textarea.dispatchEvent(new Event('input',{bubbles:true}));}};
  const refresh=button('형상 확인',async()=>{clear();error.textContent='';const token=generation;refresh.disabled=true;try{const {value}=read(),model=shapes(merge(base,value));report.textContent=model.notes.join('\n');if(!model.items.length){placeholder('표시할 형상이 없습니다');return;}const dispose=await viewer(host,model);if(closed||token!==generation){dispose();return;}clean=dispose;report.textContent=[model.items.length+' shapes · m',...model.items.map(x=>x.name),...model.notes].join('\n');}catch(e){if(!closed&&token===generation){placeholder('미리보기를 생성할 수 없습니다');error.textContent=e.message;}}finally{refresh.disabled=false;}});
  header.append(el('h2','공간 정보'),refresh);code.append(el('label',schemaOnly?'초기 형상 JSON':'공간 JSON'),textarea);preview.append(el('div','3D 미리보기','sp-preview-label'),host,report);body.append(code,preview);
  const help=el('details'),summary=el('summary','공간 JSON 형식');help.append(summary,el('pre','geometry.regions / fluid_regions / solid_regions: 배열 또는 이름별 객체\nbox: shape, unit, min [x,y,z], max [x,y,z]\nsphere: shape, unit, center [x,y,z], radius\ncylinder: shape, unit, center [x,y,z], radius, height, axis (x/y/z)\nunit: m / cm / mm\n기존 tank·board·coil: mm / geometry_spec·loading.blocks: m'));
  actions.append(button(readonly?'닫기':'취소',()=>dialog.close()));
  if(!readonly)actions.append(button('적용',()=>{try{const {value,definition}=read();let next=merge(base,value),nextSchema=null;shapes(next);if(schemaOnly){nextSchema=CFDFormConfig.blankDefinition(CFDFormConfig.fromConfig(next,original));next=CFDFormConfig.toConfig(nextSchema);}onApply(next,nextSchema);dialog.close();}catch(e){error.textContent=e.message;}}));
  dialog.append(header,el('p',schemaOnly?'초기 형상은 Template에 저장 · 프로젝트에서 독립적으로 수정 가능':'형상 확인용 미리보기 · 격자 생성·솔버 계산은 별도','sp-note'),body,help,error,actions);
  dialog.onclose=()=>{closed=true;clear();dialog.remove();};document.body.append(dialog);dialog.showModal();return dialog;
 }
 const api={keys,parse,extract,merge,document:spatialDocument,mergeDocument,shapes,elements,isGeometryPath,at,pathId,viewer,open};if(typeof module!=='undefined')module.exports=api;else globalThis.CFDSpatial=api;
})();
