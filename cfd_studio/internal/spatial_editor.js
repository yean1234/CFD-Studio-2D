/* Spatial JSON editor and geometry preview. Never executes user code or a solver. */
(()=>{
 const keys=['geometry','geometry_spec','domain','regions','tank','layers','board','coil','loading','silo','published','probes_mm'];
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
 function shapes(config){
  const items=[],notes=[],up=config.tank?[0,1,0]:[0,0,1];
  const num=(x,label,positive=false)=>{if(typeof x!=='number'||!Number.isFinite(x)||(positive&&x<=0))throw Error(label+' 숫자·범위를 확인하세요');return x;};
  const vector=(x,label)=>{if(!Array.isArray(x)||x.length!==3)throw Error(label+'에 좌표 3개를 입력하세요');return x.map(v=>num(v,label));};
  const box=(name,min,max,scale=1)=>{min=vector(min,name+'.min').map(v=>v*scale);max=vector(max,name+'.max').map(v=>v*scale);if(max.some((v,i)=>v<=min[i]))throw Error(name+' 최대 좌표는 최소 좌표보다 커야 합니다');items.push({kind:'box',name,min,max});};
  const ready=values=>values.every(x=>x!==null&&x!==undefined&&x!=='');
  const g=config.geometry_spec?.geometry;
  if(g){const a=[g.length_m,g.width_m,g.eaves_m,g.roof_rise_m];if(ready(a)){a.forEach((x,i)=>num(x,'geometry_spec.geometry',i<3));if(a[3]<0)throw Error('roof_rise_m은 0 이상이어야 합니다');items.push({kind:'gable',name:'geometry_spec.geometry',size:a});}else notes.push('geometry_spec.geometry: 치수 미입력');}
  if(config.tank){const t=config.tank,a=[t.width_mm,t.liquid_height_mm,t.depth_mm];if(ready(a))box('tank',[0,0,0],a,.001);else notes.push('tank: 치수 미입력');
   for(const key of ['board','coil'])if(config[key]){const b=config[key],a=['x0','y0','z0','x1','y1','z1'].map(k=>b[k]);if(ready(a))box(key,a.slice(0,3),a.slice(3),.001);else notes.push(key+': 치수 미입력');}
   notes.push('tank·board·coil 표시 · 상분율·발열면·격자는 표시하지 않음');
  }
  for(const [i,b]of (config.loading?.blocks||[]).entries())box('loading.blocks['+i+']',b.min_m,b.max_m);
  function region(r,name,inheritedUnit){
   if(!isObject(r)){notes.push(name+': 지원하지 않는 형식');return;}
   const shape=r.shape||r.type;
   if(!shape){notes.push(name+': shape 미입력');return;}
   const unit=r.unit||inheritedUnit,scale={m:1,cm:.01,mm:.001}[unit];
   if(!scale)throw Error(name+': unit에 m, cm 또는 mm를 입력하세요');
   if(shape==='box')box(name,r.min,r.max,scale);
   else if(shape==='sphere'){const center=vector(r.center,name+'.center').map(v=>v*scale),radius=num(r.radius,name+'.radius',true)*scale;items.push({kind:'sphere',name,center,radius});}
   else if(shape==='cylinder'){const center=vector(r.center,name+'.center').map(v=>v*scale),radius=num(r.radius,name+'.radius',true)*scale,height=num(r.height,name+'.height',true)*scale;if(!['x','y','z'].includes(r.axis))throw Error(name+': axis에 x, y 또는 z를 입력하세요');items.push({kind:'cylinder',name,center,radius,height,axis:r.axis});}
   else notes.push(name+': 지원하지 않는 shape '+String(shape));
  }
  function regions(value,path,unit){if(Array.isArray(value)){value.forEach((r,i)=>region(r,path+'['+i+']',unit));}else if(isObject(value)){Object.entries(value).forEach(([k,r])=>region(r,path+'.'+k,unit));}else if(value!=null)notes.push(path+': 지원하지 않는 형식');}
  if(config.geometry){const g=config.geometry;if(g.source)notes.push('geometry.source: 외부 형상 파일은 미리보기에 포함되지 않음');if(g.shape||g.type)region(g,'geometry',g.unit);else for(const key of ['regions','fluid_regions','solid_regions'])if(g[key])regions(g[key],'geometry.'+key,g.unit);if(!g.shape&&!g.type&&!['regions','fluid_regions','solid_regions','source'].some(k=>k in g))notes.push('geometry: 지원하지 않는 형식');}
  if(config.domain)region(config.domain,'domain',config.domain.unit);
  if(config.regions)regions(config.regions,'regions');
  if(config.silo||config.published)notes.push('silo·published: 외부 격자 형상은 미리보기 미지원');
  if(config.probes_mm)notes.push('probes_mm: 측정 지점은 미리보기에 포함되지 않음');
  if(items.length>1000)throw Error('미리보기 형상은 1000개 이하로 입력하세요');
  if(!items.length)notes.push('표시할 형상이 없습니다 · 치수와 형식을 확인하세요');
  return {items,notes,up};
 }
 async function viewer(host,model){
  const T=await import('/studies/three.module.js');
  const scene=new T.Scene();scene.background=new T.Color('#111315');
  const camera=new T.PerspectiveCamera(40,1,.001,1000),renderer=new T.WebGLRenderer({antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));host.append(renderer.domElement);
  const group=new T.Group();scene.add(group);const disposables=[];
  try{
   for(const [i,item]of model.items.entries()){
    let geometry,mesh;
    if(item.kind==='box'){geometry=new T.BoxGeometry(...item.max.map((v,k)=>v-item.min[k]));}
    else if(item.kind==='sphere')geometry=new T.SphereGeometry(item.radius,24,16);
    else if(item.kind==='cylinder')geometry=new T.CylinderGeometry(item.radius,item.radius,item.height,32);
    else{const [l,w,h,r]=item.size,points=[0,0,0,l,0,0,l,w,0,0,w,0,0,0,h,l,0,h,l,w,h,0,w,h,0,w/2,h+r,l,w/2,h+r];geometry=new T.BufferGeometry();geometry.setAttribute('position',new T.Float32BufferAttribute(points,3));geometry.setIndex([0,2,1,0,3,2,0,1,5,0,5,4,3,7,6,3,6,2,4,5,9,4,9,8,8,9,6,8,6,7,0,4,8,0,8,7,0,7,3,1,2,6,1,6,9,1,9,5]);geometry.computeVertexNormals();}
    const color=new T.Color().setHSL((.57+i*.12)%1,.58,.58),material=new T.MeshBasicMaterial({color,transparent:true,opacity:.15,side:T.DoubleSide,depthWrite:false});mesh=new T.Mesh(geometry,material);disposables.push(geometry,material);
    const edgeGeometry=new T.EdgesGeometry(geometry),edgeMaterial=new T.LineBasicMaterial({color});mesh.add(new T.LineSegments(edgeGeometry,edgeMaterial));disposables.push(edgeGeometry,edgeMaterial);
    if(item.kind==='box')mesh.position.fromArray(item.min.map((v,k)=>(v+item.max[k])/2));
    else if(item.center)mesh.position.fromArray(item.center);
    if(item.kind==='cylinder'){if(item.axis==='z')mesh.rotation.x=Math.PI/2;if(item.axis==='x')mesh.rotation.z=Math.PI/2;}
    group.add(mesh);
   }
   const bounds=new T.Box3().setFromObject(group),size=bounds.getSize(new T.Vector3()),center=bounds.getCenter(new T.Vector3()),extent=Math.max(size.x,size.y,size.z);
   if(!Number.isFinite(extent)||extent<=0)throw Error('형상 크기를 확인하세요');group.position.copy(center).multiplyScalar(-1);group.scale.setScalar(1/extent);group.position.divideScalar(extent);
   const axes=new T.AxesHelper(.65);axes.position.copy(center).multiplyScalar(-1/extent);scene.add(axes);disposables.push(axes.geometry,...(Array.isArray(axes.material)?axes.material:[axes.material]));camera.up.fromArray(model.up);
   let yaw=-.6,pitch=.4,distance=2.8,pointer=null;
   const draw=()=>{const zUp=model.up[2]===1,p=[Math.cos(pitch)*Math.cos(yaw)*distance,Math.cos(pitch)*Math.sin(yaw)*distance,Math.sin(pitch)*distance];camera.position.fromArray(zUp?p:[p[0],p[2],p[1]]);camera.lookAt(0,0,0);renderer.render(scene,camera);};
   const resize=new ResizeObserver(()=>{const w=host.clientWidth,h=host.clientHeight;if(!w||!h)return;renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix();draw();});resize.observe(host);
   const canvas=renderer.domElement;canvas.style.touchAction='none';canvas.setAttribute('aria-label','공간 3D 미리보기');
   canvas.onpointerdown=e=>{if(e.button!==0)return;pointer={id:e.pointerId,x:e.clientX,y:e.clientY};canvas.setPointerCapture(e.pointerId);};
   canvas.onpointermove=e=>{if(!pointer)return;yaw-=(e.clientX-pointer.x)*.007;pitch=Math.max(-1.45,Math.min(1.45,pitch+(e.clientY-pointer.y)*.007));pointer.x=e.clientX;pointer.y=e.clientY;draw();};canvas.onpointerup=canvas.onpointercancel=()=>pointer=null;
   canvas.addEventListener('wheel',e=>{e.preventDefault();distance=Math.max(1,Math.min(15,distance*Math.exp(Math.max(-100,Math.min(100,e.deltaY))*.001)));draw();},{passive:false});
   canvas.ondblclick=()=>{yaw=-.6;pitch=.4;distance=2.8;draw();};draw();
   return ()=>{resize.disconnect();disposables.forEach(x=>x.dispose());renderer.dispose();renderer.domElement.remove();};
  }catch(e){disposables.forEach(x=>x.dispose());renderer.dispose();renderer.domElement.remove();throw e;}
 }
 function open({config,schema=null,schemaOnly=false,readonly=false,onApply}){
  const base=clone(config),original=schema?clone(schema):null;
  const el=(tag,text,cls)=>{const x=document.createElement(tag);if(text!==undefined)x.textContent=text;if(cls)x.className=cls;return x;};
  if(!document.getElementById('spatialStyle')){const style=el('style');style.id='spatialStyle';style.textContent=`.sp-dialog{box-sizing:border-box;width:min(1280px,96vw);max-width:1280px;height:min(840px,92vh);padding:22px;border:1px solid var(--line);border-radius:14px;background:var(--surface,var(--page));color:var(--ink);overflow:auto}.sp-dialog[open]{display:flex;flex-direction:column;gap:14px}.sp-dialog::backdrop{background:#000a}.sp-header,.sp-actions{display:flex;align-items:center;gap:10px}.sp-header h2{font-size:18px;margin:0;flex:1}.sp-actions{justify-content:flex-end}.sp-body{display:grid;grid-template-columns:1fr 1fr;gap:14px;flex:1;min-height:280px}.sp-code,.sp-preview{min-width:0;min-height:0;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:var(--page)}.sp-code{display:flex;flex-direction:column}.sp-code label,.sp-preview-label{font-size:12px;padding:12px;display:block;border-bottom:1px solid var(--line)}.sp-code textarea{flex:1;min-height:0;resize:none;border:0;width:100%;box-sizing:border-box;padding:14px;color:var(--ink);background:var(--page);font:12px/1.7 Consolas,monospace;tab-size:2;white-space:pre;overflow:auto;user-select:text}.sp-preview{display:flex;flex-direction:column}.sp-canvas{flex:1;min-height:160px;position:relative}.sp-canvas canvas{display:block;width:100%;height:100%}.sp-empty{position:absolute;inset:0;display:grid;place-content:center;padding:20px;font-size:12px;color:var(--muted)}.sp-report{padding:10px 12px;max-height:100px;overflow:auto;font-size:11px;white-space:pre-wrap;border-top:1px solid var(--line);color:var(--muted)}.sp-error{color:#ff9292;font-size:12px;margin:0;white-space:pre-wrap}.sp-note{font-size:11px;color:var(--muted);margin:0}.sp-dialog details{font-size:11px;max-height:140px;overflow:auto}.sp-dialog pre{white-space:pre-wrap;user-select:text}@media(max-width:800px){.sp-body{grid-template-columns:1fr;flex:none}.sp-code,.sp-preview{height:320px}}`;document.head.append(style);}
  const dialog=el('dialog',undefined,'sp-dialog'),header=el('div',undefined,'sp-header'),body=el('div',undefined,'sp-body'),code=el('div',undefined,'sp-code'),preview=el('div',undefined,'sp-preview'),host=el('div',undefined,'sp-canvas'),report=el('div',undefined,'sp-report'),error=el('p','', 'sp-error'),actions=el('div',undefined,'sp-actions');error.setAttribute('role','alert');report.setAttribute('role','status');
  const button=(label,fn)=>{const b=el('button',label,'btn');b.type='button';b.onclick=fn;return b;};
  const textarea=el('textarea');textarea.setAttribute('aria-label',schemaOnly?'공간 양식 JSON':'공간 JSON');textarea.setAttribute('translate','no');textarea.spellcheck=false;textarea.readOnly=readonly;
  const initial=schemaOnly?{version:1,fields:original.fields.filter(f=>keys.includes(f.key))}:extract(base);textarea.value=JSON.stringify(initial,null,2);
  const read=()=>{const parsed=parse(textarea.value);if(schemaOnly){const value=CFDFormConfig.toConfig(parsed);merge({},value);return {value,definition:parsed};}return {value:parsed};};
  let clean=null,generation=0,closed=false;
  const clear=()=>{generation++;clean?.();clean=null;host.replaceChildren();report.textContent='';};
  const placeholder=text=>{host.replaceChildren(el('div',text,'sp-empty'));};placeholder('형상 확인을 눌러 미리보기');
  textarea.oninput=()=>{clear();placeholder('입력이 변경되었습니다 · 형상 확인을 눌러 갱신');error.textContent='';};
  textarea.onkeydown=e=>{if(e.key==='Tab'&&!readonly){e.preventDefault();textarea.setRangeText('  ',textarea.selectionStart,textarea.selectionEnd,'end');textarea.dispatchEvent(new Event('input',{bubbles:true}));}};
  const refresh=button('형상 확인',async()=>{clear();error.textContent='';const token=generation;refresh.disabled=true;try{const {value}=read(),model=shapes(merge(base,value));report.textContent=model.notes.join('\n');if(!model.items.length){placeholder('표시할 형상이 없습니다');return;}const dispose=await viewer(host,model);if(closed||token!==generation){dispose();return;}clean=dispose;report.textContent=[model.items.length+' shapes · m · X / Y / Z',...model.items.map(x=>x.name),...model.notes].join('\n');}catch(e){if(!closed&&token===generation){placeholder('미리보기를 생성할 수 없습니다');error.textContent=e.message;}}finally{refresh.disabled=false;}});
  header.append(el('h2','공간 정보'),refresh);code.append(el('label',schemaOnly?'Template JSON':'Config JSON'),textarea);preview.append(el('div','3D 미리보기','sp-preview-label'),host,report);body.append(code,preview);
  const help=el('details'),summary=el('summary','공간 JSON 형식');help.append(summary,el('pre','geometry.regions / fluid_regions / solid_regions: 배열 또는 이름별 객체\nbox: shape, unit, min [x,y,z], max [x,y,z]\nsphere: shape, unit, center [x,y,z], radius\ncylinder: shape, unit, center [x,y,z], radius, height, axis (x/y/z)\nunit: m / cm / mm\n기존 tank·board·coil: mm / geometry_spec·loading.blocks: m'));
  actions.append(button(readonly?'닫기':'취소',()=>dialog.close()));
  if(!readonly)actions.append(button('적용',()=>{try{const {value,definition}=read();let next=merge(base,value),nextSchema=null;if(!schemaOnly)shapes(next);if(schemaOnly){nextSchema=clone(original);nextSchema.fields=[...nextSchema.fields.filter(f=>!keys.includes(f.key)),...definition.fields];nextSchema=CFDFormConfig.blankDefinition(nextSchema);next=CFDFormConfig.toConfig(nextSchema);}onApply(next,nextSchema);dialog.close();}catch(e){error.textContent=e.message;}}));
  dialog.append(header,el('p',schemaOnly?'Template에는 양식만 저장 · 미리보기 치수는 저장하지 않음':'형상 확인용 미리보기 · 격자 생성·솔버 계산은 별도','sp-note'),body,help,error,actions);
  dialog.onclose=()=>{closed=true;clear();dialog.remove();};document.body.append(dialog);dialog.showModal();return dialog;
 }
 const api={keys,parse,extract,merge,shapes,open};if(typeof module!=='undefined')module.exports=api;else globalThis.CFDSpatial=api;
})();
