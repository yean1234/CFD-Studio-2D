/* Shared presentation of saved results. Never edits solver settings or fields. */
function sheetRows(series){
 const times=new Set(),maps=series.map(s=>{const m=new Map();for(const [t,v] of s.pts){if(Number.isFinite(t)){times.add(t);m.set(t,Number.isFinite(v)?v:null);}}return m;});
 return [...times].sort((a,b)=>a-b).map(t=>[t,...maps.map(m=>m.get(t)??null)]);
}
function sheetCSV(headers,rows){return '\ufeff'+[headers,...rows].map(r=>r.map(v=>{let s=v==null?'':String(v);if(typeof v==='string'&&/^[=+@-]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';}).join(',')).join('\r\n');}
function sheetRanges(map){return [0,1].map((k,i)=>({name:k?'최댓값':'최솟값',color:i?'#e08a3a':'#3987e5',pts:Object.entries(map).map(([t,f])=>{let lo=Infinity,hi=-Infinity;for(const v of f.v||[])if(Number.isFinite(v)){lo=Math.min(lo,v);hi=Math.max(hi,v);}return [+t,Number.isFinite(lo)?[lo,hi][k]:null];}).sort((a,b)=>a[0]-b[0])}));}
function sheetMetricKey(metric,axis){return [metric.id,metric.unit,axis].join('|');}
function sheetPick(series,target){const rows=sheetRows(series);if(!rows.length)return null;return rows.reduce((a,b)=>Math.abs(a[0]-target)<=Math.abs(b[0]-target)?a:b);}
function sheetCoordinateBounds(metric,domain,y){
 const bounds=metric?.bounds_m;if(!Array.isArray(bounds)||bounds.length!==3||bounds.some(v=>!Array.isArray(v)||v.length!==2||!v.every(Number.isFinite)||v[0]>=v[1]))return null;
 const result=bounds.map(v=>[...v]);if(domain?.kind==='gable'&&Number.isFinite(y)&&y>=0&&y<=domain.width_m)result[2][1]=domain.eaves_m+domain.roof_rise_m*(1-Math.abs(2*y/domain.width_m-1));return result;
}
function sheetAxes(series,includeZero=false){
 const groups=new Map();for(const s of series){if(!groups.has(s.unit))groups.set(s.unit,{unit:s.unit,color:s.color,lo:Infinity,hi:-Infinity});const axis=groups.get(s.unit);for(const [,v] of s.pts)if(Number.isFinite(v)){axis.lo=Math.min(axis.lo,v);axis.hi=Math.max(axis.hi,v);}}
 return [...groups.values()].map(a=>{if(!Number.isFinite(a.lo))return {...a,lo:0,hi:1};if(includeZero){a.lo=Math.min(0,a.lo);a.hi=Math.max(0,a.hi);}const pad=Math.max((a.hi-a.lo)*.08,a.hi-a.lo<Math.abs(a.hi)*1e-6?Math.abs(a.hi)*.01:0,1e-9);return {...a,lo:includeZero&&a.lo===0?0:a.lo-pad,hi:includeZero&&a.hi===0&&a.lo<0?0:a.hi+pad};});
}
if(typeof module!=='undefined')module.exports={sheetRows,sheetCSV,sheetRanges,sheetMetricKey,sheetPick,sheetCoordinateBounds,sheetAxes};
const DataSheetViewer=(()=>{
 const $=id=>document.getElementById(id),el=(tag,text)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;return n;};
 const colors=['#68aafa','#efad62','#65d3ac','#c49bfa','#ee849b','#8ed5ec','#d6cf7b','#b4bdd0'];
 const panels=[0,1].map(index=>({index,cache:new Map(),epoch:0,controller:null,reading:false,error:'',chartType:'line',metric:'',metrics:['','',''],cursor:null,domain:null,drag:null,position:null}));
 const at=(p,id)=>$(id+(p.index?'2':''));
 let mode='3d',context=null,project=null,selected=[],selectionKey='',catalogs=new Map(),catalogsReady=false,catalogEpoch=0,catalogController=null,catalogError='';
 const api=async(path,signal)=>{const r=await fetch('/api/executions/'+path,{signal}),d=await r.json();if(!r.ok)throw Error(d.msg||'결과를 읽지 못했습니다');return d;};
 function mount(){if($('dataSheet'))return;
 const css=el('style',`body.grouped #gcol,body.grouped #vlegend label:has(input[id^="gc"]),body.grouped #graphControlsTitle{display:none!important}
 body.grouped.execution-viewer.data-sheet-viewer #secData{display:none!important}
 body.data-sheet-viewer #controls,body.data-sheet-viewer #lcol,body.data-sheet-viewer #rcol,body.data-sheet-viewer #plabels,body.data-sheet-viewer #empty,body.data-sheet-viewer #saveShot,body.data-sheet-viewer #vizWarn{display:none!important}body.data-sheet-viewer #gl{visibility:hidden!important}
 #dataSheet{display:none;position:absolute;inset:0;z-index:5;overflow:auto;background:var(--page);padding:24px;color:var(--ink)}body.data-sheet-viewer #dataSheet{display:block}#dataSheet [hidden]{display:none!important}
 .ds-heading{margin-bottom:20px}.ds-heading h2{color:var(--ink);font-size:21px;letter-spacing:-.4px;margin:0}.ds-heading p{margin:7px 0 0;font-size:12px;color:var(--muted)}
 .ds-grid{width:100%;margin:0 auto;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px;align-items:stretch}.ds-panel{min-width:0;padding:0;border:0;display:flex;flex-direction:column}.ds-chart{flex:1;background:var(--surface);border:1px solid var(--line);border-radius:12px;overflow:hidden;min-width:0}
 .ds-kind-row{height:40px;margin-bottom:8px;display:flex;align-items:center}.ds-kind-row .ds-kind{width:100%;justify-content:space-between} .ds-field-heading{font-size:12px;margin-bottom:8px;min-height:34px;display:flex;align-items:center;justify-content:space-between;gap:12px}.ds-toolbar .ds-kind{font-size:11px;gap:8px}.ds-toolbar .ds-kind select{flex:none;width:100px!important;height:32px;padding:5px 8px}.ds-field-row{display:grid;grid-template-columns:minmax(0,1fr);min-height:52px;align-items:end}.ds-metrics{grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.ds-toolbar .ds-field-row label{flex-direction:column;align-items:stretch;gap:4px;font-size:10px}.ds-toolbar .ds-field-row select{box-sizing:border-box;flex:auto;width:100%!important;height:34px;padding:5px;font-size:11px}
 .ds-toolbar{padding:14px 16px;border-bottom:1px solid var(--line)}.ds-toolbar label{display:flex;align-items:center;gap:12px;color:var(--muted);font-size:12px}.ds-toolbar label span{white-space:nowrap}.ds-toolbar select{flex:1;min-width:0;width:0!important;padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--page);color:var(--ink)}.ds-actions{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin-top:12px}.ds-actions .btn{font-size:11px;height:30px;padding:0 10px}.ds-coverage{font-size:11px;color:var(--muted);margin-right:auto}
 .ds-legend{display:flex;gap:10px 16px;flex-wrap:wrap;padding:14px 18px 4px;font-size:11px}.ds-legend span{max-width:100%;overflow-wrap:anywhere}.ds-legend span:before,.ds-values span:before{content:'';display:inline-block;width:14px;height:3px;background:var(--series);margin-right:7px;vertical-align:middle}
 .ds-plot{display:block;width:80%;margin:0 auto 16px;height:clamp(260px,34vh,370px);touch-action:none;user-select:none;-webkit-user-select:none;cursor:crosshair;outline:none}.ds-plot *{user-select:none;-webkit-user-select:none}.ds-plot:focus-visible{outline:1px solid var(--s1);outline-offset:-2px}body.ds-dragging,body.ds-dragging *{user-select:none!important;-webkit-user-select:none!important}
 .ds-cursor{padding:14px 18px;border-top:1px solid var(--line);background:var(--surface2);font-size:12px;min-height:84px;box-sizing:border-box}.ds-x{font-variant-numeric:tabular-nums;display:block;margin-bottom:8px}.ds-values{display:flex;gap:10px 16px;flex-wrap:wrap;font-variant-numeric:tabular-nums}.ds-values span{overflow-wrap:anywhere}.ds-empty{height:clamp(260px,34vh,370px);box-sizing:border-box;display:flex;align-items:center;justify-content:center;padding:18px;text-align:center;color:var(--muted);font-size:12px}.ds-error{color:var(--s3);font-size:12px;white-space:pre-wrap}
 .ds-coordinates{display:flex;gap:8px;align-items:center;min-height:44px;margin-top:10px}.ds-coordinates label{flex:1;min-width:0;gap:5px}.ds-coordinates input{width:100%;min-width:0;box-sizing:border-box;background:var(--page);color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:7px}.ds-coordinates input::placeholder{color:var(--muted);opacity:.6}.ds-coordinates input:invalid:not(:placeholder-shown){border-color:var(--s3)}.ds-coordinates .btn{height:30px;flex:none}.ds-coordinate-spacer{min-height:44px;margin-top:10px}
 #viewerHeading{display:none;position:absolute;left:24px;top:24px;z-index:4;pointer-events:none;max-width:calc(100% - 304px);color:var(--ink);text-shadow:0 1px 4px var(--page)}#viewerHeading p{overflow-wrap:anywhere}body.execution-viewer:not(.data-sheet-viewer) #viewerHeading{display:block}@media(max-width:950px){#viewerHeading{top:238px;left:16px;max-width:calc(100% - 32px)}}
 .ds-export-dialog{box-sizing:border-box;max-width:calc(100vw - 32px);width:480px;background:var(--surface);color:var(--ink);border:1px solid var(--line);border-radius:12px;padding:22px}.ds-export-dialog::backdrop{background:#0008}.ds-export-dialog h2{margin:0 0 12px;font-size:20px}.ds-export-dialog p{line-height:1.6;overflow-wrap:anywhere}.ds-export-dialog .ew-bar{display:flex;flex-wrap:wrap;gap:8px}
 @supports(grid-template-rows:subgrid){.ds-grid{grid-template-rows:repeat(5,auto)}.ds-panel{display:grid;grid-row:span 5;grid-template-rows:subgrid;row-gap:0}.ds-chart{display:grid;grid-row:span 4;grid-template-rows:subgrid;row-gap:0}.ds-error{margin-bottom:0}}
 @media(max-width:950px){#dataSheet{padding:16px}.ds-grid{width:100%;grid-template-columns:1fr}.ds-plot,.ds-empty{height:280px}}`);document.head.append(css);
 const box=el('section');box.id='dataSheet';box.setAttribute('aria-label','Data Sheet Viewer');box.innerHTML='<header class="ds-heading"><h2 id="dsName">Data Sheet</h2><p id="dsSelection"></p></header><div class="ds-grid"></div>';$('viz').append(box);const heading=el('header');heading.id='viewerHeading';heading.className='ds-heading';heading.innerHTML='<h2></h2><p></p>';$('viz').append(heading);
 for(const p of panels){
  const id=name=>name+(p.index?'2':''),panel=el('section');panel.className='ds-panel';panel.setAttribute('aria-label',p.index?'오른쪽 그래프':'왼쪽 그래프');
  panel.innerHTML=`<div class="ds-chart"><div class="ds-toolbar"><div class="ds-field-heading">${p.index?'좌표 조회':'전체 평균'}</div><div class="ds-kind-row" ${p.index?'aria-hidden="true"':''}>${p.index?'':'<label class="ds-kind"><span>그래프 형식</span><select id="dsGraphType" aria-label="왼쪽 그래프 형식"><option value="line">선</option><option value="bar">막대</option><option value="scatter">산점도</option></select></label>'}</div><div class="ds-field-row ${p.index?'':'ds-metrics'}">${p.index?`<label><span>결과</span><select id="dsField2" aria-label="오른쪽 그래프 결과 항목"></select></label>`:['dsField','dsFieldB','dsFieldC'].map((name,i)=>`<label><span style="color:${colors[i]}">요소 ${i+1}</span><select id="${name}" aria-label="왼쪽 그래프 요소 ${i+1}"></select></label>`).join('')}</div>${p.index?`<form class="ds-coordinates" id="dsCoordinates" title="가장 가까운 저장 셀의 값을 조회합니다">${['X','Y','Z'].map(axis=>`<label><span>${axis} (m)</span><input type="number" step="any" name="${axis.toLowerCase()}" aria-label="${axis} 좌표 (m)" placeholder="" required></label>`).join('')}<button class="btn" type="submit">조회</button></form>`:'<div class="ds-coordinate-spacer" aria-hidden="true"></div>'}<div class="ds-actions"><span class="ds-coverage" id="${id('dsCoverage')}"></span><button class="btn" id="${id('dsRead')}">전체 구간 읽기</button><button class="btn" id="${id('dsExport')}">Export</button></div></div><div class="ds-legend" id="${id('dsLegend')}"></div><svg class="ds-plot" id="${id('dsPlot')}" role="img" tabindex="0" aria-label="그래프 ${p.index+1}. 클릭 또는 좌우 화살표로 저장 시점 선택" viewBox="0 0 640 360" preserveAspectRatio="none"></svg><div class="ds-empty" id="${id('dsEmpty')}"></div><div class="ds-cursor" aria-live="polite"><strong class="ds-x" id="${id('dsX')}">그래프에서 확인할 위치를 선택하세요</strong><div class="ds-values" id="${id('dsValues')}"></div></div></div><p class="ds-error" id="${id('dsError')}" role="status"></p>`;box.querySelector('.ds-grid').append(panel);
  if(p.index){const form=$('dsCoordinates');form.oninput=()=>{stopRead(p);p.position=null;p.cache.clear();p.cursor=null;p.error='';refreshPanel(p);};for(const input of form.querySelectorAll('input'))globalThis.CFDInput?.bind(input,{type:'number'});form.onchange=()=>{refreshPanel(p);};form.onsubmit=e=>{e.preventDefault();updateCoordinateInputs(p);if(!form.reportValidity())return;const xyz=['x','y','z'].map(k=>Number(form.elements[k].value));if(!xyz.every(Number.isFinite))return;stopRead(p);p.position=xyz;p.cache.clear();p.cursor=null;p.error='';refreshPanel(p);read(p,false);};}
  if(!p.index)$('dsGraphType').onchange=()=>{endDrag(p);p.chartType=$('dsGraphType').value;draw(p,dataset(p));};
  for(const [index,select] of controls(p).entries())select.onchange=()=>{stopRead(p);if(p.index)p.metric=select.value;else p.metrics[index]=select.value;p.cursor=null;refreshPanel(p);read(p,false);};
  at(p,'dsRead').onclick=()=>{if(p.reading){stopRead(p);refreshPanel(p);return;}const d=dataset(p);if(d.series.length&&d.series.every(s=>{const item=p.cache.get(s.cacheKey);return item&&item.next>=item.total;}))for(const s of d.series)p.cache.delete(s.cacheKey);read(p,true);};
  at(p,'dsExport').onclick=()=>openChartExport(p);
  const svg=at(p,'dsPlot'),pick=e=>{if(!p.domain)return;const rect=svg.getBoundingClientRect(),px=(e.clientX-rect.left)/rect.width*640;p.cursor=p.domain.a+Math.max(0,Math.min(1,(px-p.domain.left)/p.domain.width))*(p.domain.b-p.domain.a);draw(p,dataset(p));};
  svg.onpointerdown=e=>{if(e.button!==0)return;e.preventDefault();svg.focus({preventScroll:true});p.drag=e.pointerId;document.body.classList.add('ds-dragging');svg.setPointerCapture?.(e.pointerId);pick(e);};
  svg.onpointermove=e=>{if(p.drag===e.pointerId&&e.buttons===1){e.preventDefault();pick(e);}};
  svg.onpointerup=svg.onpointercancel=svg.onlostpointercapture=()=>endDrag(p);
  svg.ondragstart=e=>e.preventDefault();
  svg.onkeydown=e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;const d=dataset(p),rows=sheetRows(d.series);if(!rows.length)return;e.preventDefault();const chosen=sheetPick(d.series,p.cursor??rows[0][0]),index=rows.findIndex(r=>r[0]===chosen[0]);p.cursor=rows[e.key==='Home'?0:e.key==='End'?rows.length-1:Math.max(0,Math.min(rows.length-1,index+(e.key==='ArrowRight'?1:-1)))][0];draw(p,d);};
 }
 window.addEventListener('blur',()=>panels.forEach(endDrag));
 }
 function chartSnapshot(p){
  const d=dataset(p),rows=sheetRows(d.series);if(!rows.length)return null;
  return {index:p.index,chartType:p.chartType,project:project?.name||context?.name||'Data Sheet',name:d.name+(p.index?' · ('+p.position.join(', ')+') m · 최근접 저장 셀':''),unit:d.unit,
   metric:d.id,axis:d.axis,series:d.series,rows,svg:at(p,'dsPlot').cloneNode(true),
   position:p.index?[...p.position]:null,coverage:at(p,'dsCoverage').textContent,x:p.cursor==null?'':at(p,'dsX').textContent,
   values:p.cursor==null?[]:[...at(p,'dsValues').children].map(n=>n.textContent)};
 }
 async function chartPNG(snapshot){
  const ns='http://www.w3.org/2000/svg',root=document.createElementNS(ns,'svg'),width=1280;
  root.setAttribute('xmlns',ns);root.setAttribute('width',width);root.setAttribute('font-family','Segoe UI, Arial, sans-serif');
  const add=(tag,attrs,text)=>{const n=document.createElementNS(ns,tag);for(const [key,value] of Object.entries(attrs))n.setAttribute(key,value);if(text!=null)n.textContent=text;root.append(n);return n;};
  add('rect',{width:'100%',height:'100%',fill:'#1b1b19'});const canvas=document.createElement('canvas'),measure=canvas.getContext('2d');
  if(!measure)throw Error('이미지 생성을 위한 Canvas를 사용할 수 없습니다');
  let y=36;
  const text=(value,size=18,color='#dcdcd5')=>{
   measure.font=size+'px "Segoe UI", Arial, sans-serif';let line='';
   for(const char of String(value)){if(line&&measure.measureText(line+char).width>width-64){add('text',{x:32,y,fill:color,'font-size':size},line);y+=size+10;line='';}line+=char;}
   if(line){add('text',{x:32,y,fill:color,'font-size':size},line);y+=size+10;}
  };
  const translate=value=>globalThis.CFDI18n?.translate(value)||value;
  text(translate('그래프')+' '+(snapshot.index+1)+' · '+translate({line:'선',bar:'막대',scatter:'산점도'}[snapshot.chartType])+' · '+translate(snapshot.name)+' ('+snapshot.unit+')',24);
  text(snapshot.project+' · '+snapshot.series.map(s=>snapshot.index?s.name:translate(s.name)).join(', '));
  text(snapshot.coverage,16,'#a4a49b');
  const graph=snapshot.svg;for(const name of ['id','class','style','tabindex'])graph.removeAttribute(name);
  graph.setAttribute('x',String(width*.1));graph.setAttribute('y',y);graph.setAttribute('width',width*.8);graph.setAttribute('height','720');root.append(graph);y+=740;
  if(snapshot.x)text(snapshot.x);for(const value of snapshot.values)text(value);
  const height=y+16;root.setAttribute('height',height);root.setAttribute('viewBox','0 0 '+width+' '+height);
  const source=URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(root)],{type:'image/svg+xml;charset=utf-8'}));
  try{const img=new Image();await new Promise((resolve,reject)=>{img.onload=resolve;img.onerror=()=>reject(Error('그래프 이미지 변환 실패'));img.src=source;});canvas.width=width;canvas.height=height;canvas.getContext('2d').drawImage(img,0,0);return await new Promise((resolve,reject)=>canvas.toBlob(blob=>blob?resolve(blob):reject(Error('PNG 이미지 생성 실패')),'image/png'));}
  finally{URL.revokeObjectURL(source);}
 }
 function openChartExport(p){
  const snapshot=chartSnapshot(p);if(!snapshot)return;
  const dialog=el('dialog');dialog.className='ew-dialog ds-export-dialog';dialog.setAttribute('aria-label','그래프 '+(p.index+1)+' Export');
  dialog.innerHTML='<h2>Export</h2><p class="ds-export-name"></p><p class="ew-path-note">현재 그래프에 읽어온 구간을 저장합니다. 이미지는 표시 중인 축·곡선·조회 위치를 포함합니다.</p><div class="ew-bar"><button type="button" class="btn pri" data-png>PNG 이미지</button><button type="button" class="btn" data-csv>CSV 데이터</button><button type="button" class="btn" data-close>닫기</button></div><p role="status" aria-live="polite"></p>';
  dialog.querySelector('.ds-export-name').textContent='그래프 '+(p.index+1)+' · '+snapshot.name+' ('+snapshot.unit+') · '+snapshot.coverage;
  let busy=false;dialog.oncancel=e=>{if(busy)e.preventDefault();};dialog.onclose=()=>dialog.remove();dialog.querySelector('[data-close]').onclick=()=>dialog.close();
  const save=async format=>{if(busy)return;busy=true;for(const b of dialog.querySelectorAll('button'))b.disabled=true;const status=dialog.querySelector('[role=status]');status.textContent='파일 생성 중…';
   try{const blob=format==='png'?await chartPNG(snapshot):new Blob([sheetCSV([snapshot.axis==='iteration'?'반복 횟수':'시간 (s)',...snapshot.series.map(s=>s.runName+' · '+s.label+' ('+s.unit+')'+(snapshot.position?' · ('+snapshot.position.join(', ')+') m · 최근접 저장 셀':''))],snapshot.rows)],{type:'text/csv;charset=utf-8'});
    const safe=value=>String(value).replace(/[\\/:*?"<>|]+/g,'_').replace(/[. ]+$/,'').slice(0,60)||'graph';
    exportDownload(blob,safe(snapshot.project)+'_graph-'+(p.index+1)+'_'+safe(snapshot.metric)+'_'+snapshot.chartType+'.'+format);dialog.close();
   }catch(e){status.textContent='내보내기 실패: '+e.message;}finally{busy=false;for(const b of dialog.querySelectorAll('button'))b.disabled=false;}
  };
  dialog.querySelector('[data-png]').onclick=()=>save('png');dialog.querySelector('[data-csv]').onclick=()=>save('csv');document.body.append(dialog);dialog.showModal();
 }
 function endDrag(p){const svg=at(p,'dsPlot'),pointer=p.drag;p.drag=null;if(pointer!=null&&svg?.hasPointerCapture?.(pointer))svg.releasePointerCapture(pointer);if(panels.every(v=>v.drag==null))document.body.classList.remove('ds-dragging');}
 function stopRead(p){p.epoch++;p.controller?.abort();p.controller=null;p.reading=false;endDrag(p);}
 function stopAll(){panels.forEach(stopRead);}
 function metricsFor(c,p){return p.index?(c.point_metrics||[]):c.metrics.filter(m=>m.id.endsWith('.mean')&&m.scope==='global');}
 function metricOptions(p){const options=new Map();for(const r of selected){const c=catalogs.get(r.id);if(!c)continue;for(const m of metricsFor(c,p))options.set(sheetMetricKey(m,c.axis),{...m,axis:c.axis});}return options;}
 function controls(p){return p.index?[at(p,'dsField')]:['dsField','dsFieldB','dsFieldC'].map($);}
 function dataset(p){
 const options=metricOptions(p),keys=[...new Set(controls(p).map(n=>n?.value).filter(k=>options.has(k)))],metrics=keys.map(k=>options.get(k));
 const series=keys.flatMap((key,slot)=>selected.flatMap(r=>{const c=catalogs.get(r.id),m=options.get(key);if(!c||!metricsFor(c,p).some(v=>sheetMetricKey(v,c.axis)===key))return [];const cacheKey=r.id+'|'+key;return [{id:r.id,cacheKey,metricId:m.id,unit:m.unit,label:m.name,runName:r.name,name:p.index?r.name:m.name,color:colors[p.index?0:controls(p).findIndex(n=>n.value===key)],pts:p.cache.get(cacheKey)?.points||[]}];}));
 return {id:metrics.map(m=>m.id).join('+'),name:metrics.map(m=>m.name).join(' / '),unit:[...new Set(metrics.map(m=>m.unit))].join(', '),axis:metrics[0]?.axis||'time',series};
 }
 function updateCoordinateInputs(p){
 const metric=metricOptions(p).get(at(p,'dsField').value),form=$('dsCoordinates'),c=catalogs.get(selected[0]?.id),y=form.elements.y.value;
 const bounds=sheetCoordinateBounds(metric,c?.coordinate_domain,y===''?null:Number(y));
 for(const [k,axis] of ['x','y','z'].entries()){const input=form.elements[axis];input.disabled=!bounds;if(bounds){input.min=String(bounds[k][0]);input.max=String(bounds[k][1]);input.placeholder=input.min+' ~ '+input.max;input.title=axis.toUpperCase()+' '+input.placeholder+' m';}else{input.removeAttribute('min');input.removeAttribute('max');input.placeholder='범위 없음';}globalThis.CFDInput?.check(input,{show:input.hasAttribute('aria-invalid')});}
 form.querySelector('button').disabled=!bounds;
 if(p.position&&(!bounds||p.position.some((v,k)=>v<bounds[k][0]||v>bounds[k][1]))){stopRead(p);p.position=null;p.cache.clear();p.error='좌표가 선택한 결과의 범위를 벗어났습니다.';}
 return bounds;
 }
 function refresh(){mount();const name=project?.name||context?.name||'Data Sheet',caseName=selected.length?selected[0].name:'왼쪽에서 Case를 선택하세요';$('dsName').textContent=name;$('dsSelection').textContent=caseName;$('dsSelection').setAttribute('translate',selected.length?'no':'yes');const heading=$('viewerHeading');heading.querySelector('h2').textContent=name;heading.querySelector('h2').setAttribute('translate','no');heading.querySelector('p').textContent=caseName;heading.querySelector('p').setAttribute('translate',selected.length?'no':'yes');panels.forEach(refreshPanel);}

 function refreshPanel(p){
 const options=metricOptions(p),signature=JSON.stringify([...options.keys()]);
 for(const [slot,select] of controls(p).entries()){
  const old=(p.index?p.metric:p.metrics[slot])||select.value;
  if(select.dataset.key!==signature){const choices=[...options].map(([id,m])=>new Option(m.name+' ('+m.unit+')'+(m.axis==='iteration'?' · 반복 횟수':''),id));if(!p.index&&slot)choices.unshift(new Option('선택 안 함',''));select.replaceChildren(...choices);select.value=options.has(old)?old:slot&&!p.index?'':([...options.keys()][0]||'');select.dataset.key=signature;if(options.size){if(p.index)p.metric=select.value;else p.metrics[slot]=select.value;}}
  select.disabled=!options.size;
 }
 if(!p.index){const values=controls(p).map(n=>n.value);for(const [slot,select] of controls(p).entries())for(const option of select.options)option.disabled=!!option.value&&values.some((v,i)=>i!==slot&&v===option.value);}
 if(p.index)updateCoordinateInputs(p);
 const d=dataset(p),rows=sheetRows(d.series);at(p,'dsExport').disabled=!rows.length;at(p,'dsRead').disabled=!options.size||!!(p.index&&!p.position);
 at(p,'dsRead').textContent=p.reading?'읽기 중지':d.series.length&&d.series.every(s=>{const c=p.cache.get(s.cacheKey);return c&&c.next>=c.total;})?'다시 읽기':'전체 구간 읽기';
 const counts=d.series.map(s=>p.cache.get(s.cacheKey));at(p,'dsCoverage').textContent=counts.length?'읽음 '+counts.reduce((n,c)=>n+(c?.points.length||0),0)+' / '+counts.reduce((n,c)=>n+(c?.total||0),0)+(d.series.length>1?' 값':' 시점'):'';
 at(p,'dsLegend').replaceChildren(...d.series.map(s=>{const n=el('span',s.name+' ('+s.unit+')');if(p.index)n.setAttribute('translate','no');n.style.setProperty('--series',s.color);return n;}));at(p,'dsError').textContent=[catalogError,p.error].filter(Boolean).join('\n');draw(p,d);
 }
 function draw(p,d){const svg=at(p,'dsPlot');svg.replaceChildren();const rows=sheetRows(d.series),points=d.series.flatMap(s=>s.pts).filter(([x,y])=>Number.isFinite(x)&&Number.isFinite(y));
 at(p,'dsEmpty').hidden=!!points.length;at(p,'dsEmpty').textContent=p.index&&!p.position?'X·Y·Z 좌표를 입력하고 조회하세요.':p.reading?'저장값을 읽고 있습니다.':'선택한 결과 항목의 저장값이 없습니다.';svg.style.display=points.length?'block':'none';p.domain=null;at(p,'dsValues').replaceChildren();at(p,'dsX').textContent='그래프에서 확인할 위치를 선택하세요';if(!points.length)return;
 const kind=p.index?'line':p.chartType,axes=sheetAxes(d.series,kind==='bar'),left=72,right=620-Math.max(0,axes.length-1)*56,a=rows[0][0],b=rows.at(-1)[0];let step=Infinity;for(let i=1;i<rows.length;i++)step=Math.min(step,rows[i][0]-rows[i-1][0]);if(!Number.isFinite(step))step=1;const padding=kind==='bar'?step*.5:0,domainA=a-padding,domainB=b+padding;p.domain={a:domainA,b:domainB,left,width:right-left};const x=t=>left+(t-domainA)/Math.max(domainB-domainA,1e-12)*(right-left),y=(v,unit)=>{const axis=axes.find(a=>a.unit===unit);return 300-(v-axis.lo)/(axis.hi-axis.lo)*265;};
 const add=(tag,attrs,text)=>{const n=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v);if(text!=null)n.textContent=text;svg.append(n);return n;};
 const short=n=>Number(n.toPrecision(5));
 for(let i=0;i<=4;i++){const yy=35+i*265/4;add('line',{x1:left,y1:yy,x2:right,y2:yy,stroke:'#343431','stroke-dasharray':i===4?'':'3 5'});const t=a+(b-a)*i/4;if(a!==b||i===0)add('text',{x:x(t),y:326,fill:'#9b9b93','font-size':11,'text-anchor':'middle'},short(t));}
 axes.forEach((axis,j)=>{const xx=j?right+(j-1)*56:left,anchor=j?'start':'end',tick=xx+(j?8:-10);add('line',{x1:xx,x2:xx,y1:35,y2:300,stroke:axis.color,opacity:.55,'data-y-axis':axis.unit});add('text',{x:j?xx:left,y:20,fill:axis.color,'font-size':11},axis.unit);for(let i=0;i<=4;i++)add('text',{x:tick,y:39+i*265/4,fill:axis.color,'font-size':10,'text-anchor':anchor},short(axis.hi-i*(axis.hi-axis.lo)/4));});
 add('text',{x:right,y:350,fill:'#aaa','font-size':12,'text-anchor':'end'},d.axis==='iteration'?'반복 횟수':'시간 (s)');
 const groupWidth=Math.min(64,Math.max(.5,(x(a+step)-x(a))*.72)),slotWidth=groupWidth/Math.max(1,d.series.length);
 for(const [slot,s] of d.series.entries()){
  if(kind==='scatter'){
   for(const [t,v] of s.pts)if(Number.isFinite(v))add('circle',{cx:x(t),cy:y(v,s.unit),r:3.5,fill:s.color,'data-series':s.metricId,'data-chart-type':'scatter'});
  }else if(kind==='bar'){
   const zero=y(0,s.unit);
   for(const [t,v] of s.pts)if(Number.isFinite(v)){const yy=y(v,s.unit);add('rect',{x:x(t)-groupWidth/2+slot*slotWidth+slotWidth*.06,y:Math.min(zero,yy),width:slotWidth*.88,height:Math.abs(zero-yy),fill:s.color,opacity:.85,'data-series':s.metricId,'data-chart-type':'bar'});}
  }else{
   let path='',gap=true;for(const [t,v] of s.pts){if(!Number.isFinite(v)){gap=true;continue;}path+=(gap?'M':'L')+x(t)+','+y(v,s.unit)+' ';gap=false;}
   add('path',{d:path,fill:'none',stroke:s.color,'stroke-width':2,'vector-effect':'non-scaling-stroke','data-series':s.metricId,'data-chart-type':'line'});
   if(s.pts.length===1&&Number.isFinite(s.pts[0][1]))add('circle',{cx:x(s.pts[0][0]),cy:y(s.pts[0][1],s.unit),r:3,fill:s.color});
  }
 }
 if(p.cursor!=null){const picked=sheetPick(d.series,p.cursor);if(!picked)return;add('line',{x1:x(picked[0]),x2:x(picked[0]),y1:35,y2:300,stroke:'#eee','stroke-dasharray':'4 5','data-cursor':'x'});at(p,'dsX').textContent='X = '+String(picked[0])+(d.axis==='iteration'?' 회':' s')+' · 저장 시점';d.series.forEach((s,i)=>{const v=picked[i+1],label=el('span');const name=el('span',s.name);if(p.index)name.setAttribute('translate','no');label.append(name,' · Y = '+(v==null?'— (이 X의 저장값 없음)':String(v)+' '+s.unit));label.style.setProperty('--series',s.color);at(p,'dsValues').append(label);if(v!=null)add('circle',{cx:x(picked[0]),cy:y(v,s.unit),r:4,fill:s.color,stroke:'#151514','stroke-width':2});});}
 }

 async function loadCatalogs(){const token=++catalogEpoch;catalogController?.abort();const c=catalogController=new AbortController();stopAll();catalogsReady=false;catalogs=new Map();catalogError='';refresh();await Promise.all(selected.map(async r=>{try{const value=await api('chart-catalog?id='+encodeURIComponent(r.id),c.signal);if(token===catalogEpoch)catalogs.set(r.id,value);}catch(e){if(token===catalogEpoch&&e.name!=='AbortError')catalogError+=(catalogError?'\n':'')+r.name+': '+e.message;}}));if(token!==catalogEpoch)return;catalogsReady=true;refresh();if(mode==='data'&&document.body.classList.contains('data-sheet-viewer'))readPanels();}
 async function read(p,all){if(p.reading||!catalogsReady||mode!=='data'||(p.index&&!p.position))return;const d=dataset(p);if(!d.id)return;const token=++p.epoch;p.controller?.abort();const ctl=p.controller=new AbortController();p.reading=true;p.error='';refreshPanel(p);try{
  for(const s of d.series){const key=s.cacheKey;let item=p.cache.get(key)||{points:[],next:0,total:null};do{if(token!==p.epoch||mode!=='data')return;if(item.total!=null&&item.next>=item.total)break;const v=await api((p.index?'point-chart?id='+encodeURIComponent(s.id)+'&field='+encodeURIComponent(s.metricId)+'&'+new URLSearchParams({x:p.position[0],y:p.position[1],z:p.position[2]}):'chart?id='+encodeURIComponent(s.id)+'&metric='+encodeURIComponent(s.metricId))+'&offset='+item.next+'&limit=16',ctl.signal);if(token!==p.epoch)return;item={...v,next:v.errors.length?item.next:v.next,points:[...new Map([...item.points,...v.points])].sort((a,b)=>a[0]-b[0])};p.cache.set(key,item);if(v.errors.length)p.error+=(p.error?'\n':'')+s.name+': '+v.errors[0];refreshPanel(p);if(v.errors.length)break;}while((all||item.total<=200)&&item.next<item.total);}
 }catch(e){if(token===p.epoch&&e.name!=='AbortError')p.error=e.message;}finally{if(token===p.epoch){p.reading=false;refreshPanel(p);}}}
 function readPanels(){panels.forEach(p=>read(p,false));}
 function reset(){stopAll();panels.forEach(p=>{p.cache.clear();p.cursor=null;p.error='';});}
 function setMode(value){if(!['3d','data'].includes(value))throw Error('지원하지 않는 Viewer 모드');if(value===mode)return mode;mount();mode=value;stopAll();document.body.classList.toggle('data-sheet-viewer',mode==='data');setPlay(false,true);if(mode==='data'){if(typeof VPREFETCHTOKEN!=='undefined'){VPREFETCHTOKEN++;VPREFETCHBUSY=false;}refresh();if(!catalogsReady)loadCatalogs();else readPanels();}return mode;}
 return {get mode(){return mode;},setMode,toggle(){return setMode(mode==='3d'?'data':'3d');},
 setSelection(p,runs){mount();const oldProjectId=project?.id;project=p;const key=JSON.stringify([p?.id,runs.map(r=>[r.id,r.last_saved,r.frames,r.result_status])]);const changedCase=selected[0]?.id!==runs[0]?.id||oldProjectId!==p?.id;selected=runs;if(changedCase){panels[1].position=null;$('dsCoordinates').reset();for(const input of $('dsCoordinates').querySelectorAll('input'))globalThis.CFDInput?.reset(input);}if(key===selectionKey){refresh();return;}selectionKey=key;reset();loadCatalogs();},
 reload(){reset();loadCatalogs();},begin(value){mount();context=value;refresh();},loaded(){refresh();},
 suspend(){stopAll();document.body.classList.remove('data-sheet-viewer');},resume(){document.body.classList.toggle('data-sheet-viewer',mode==='data');if(mode==='data'&&!catalogsReady)loadCatalogs();else if(mode==='data')readPanels();},mount};
})();
