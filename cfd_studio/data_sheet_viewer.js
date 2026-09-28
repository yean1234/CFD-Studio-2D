/* Shared presentation of saved results. Never edits solver settings or fields. */
function sheetRows(series){
 const times=new Set(),maps=series.map(s=>{const m=new Map();for(const [t,v] of s.pts){if(Number.isFinite(t)){times.add(t);m.set(t,Number.isFinite(v)?v:null);}}return m;});
 return [...times].sort((a,b)=>a-b).map(t=>[t,...maps.map(m=>m.get(t)??null)]);
}
function sheetCSV(headers,rows){return '\ufeff'+[headers,...rows].map(r=>r.map(v=>{let s=v==null?'':String(v);if(typeof v==='string'&&/^[=+@-]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';}).join(',')).join('\r\n');}
function sheetRanges(map){return [0,1].map((k,i)=>({name:k?'최댓값':'최솟값',color:i?'#e08a3a':'#3987e5',pts:Object.entries(map).map(([t,f])=>{let lo=Infinity,hi=-Infinity;for(const v of f.v||[])if(Number.isFinite(v)){lo=Math.min(lo,v);hi=Math.max(hi,v);}return [+t,Number.isFinite(lo)?[lo,hi][k]:null];}).sort((a,b)=>a[0]-b[0])}));}
if(typeof module!=='undefined')module.exports={sheetRows,sheetCSV,sheetRanges};
const DataSheetViewer=(()=>{
 let mode='3d',context=null,ready=false,epoch=0,reading=false,error='',loadError='',signature='';
 const $=id=>document.getElementById(id),el=(tag,text)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;return n;};
 function mount(){if($('dataSheet'))return;
 const css=el('style',`body.grouped #gcol,body.grouped #vlegend label:has(input[id^="gc"]),body.grouped #graphControlsTitle{display:none!important}
 #dataSheet{display:none;position:absolute;inset:16px 16px 68px;z-index:5;overflow:auto;background:var(--page);border:1px solid var(--line);border-radius:14px;padding:20px;color:var(--ink)}
 body.data-sheet-viewer #dataSheet{display:block}body.data-sheet-viewer #gl,body.data-sheet-viewer #rcol,body.data-sheet-viewer #plabels,body.data-sheet-viewer #empty,body.data-sheet-viewer #saveShot{visibility:hidden!important}
 .ds-heading,.ds-actions{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.ds-heading{justify-content:space-between;margin-bottom:18px}.ds-heading h2{font-size:16px;margin:0;overflow-wrap:anywhere;color:var(--ink)}.ds-heading>div:first-child{flex:1;min-width:180px}.ds-heading p{color:var(--muted);font-size:11px;margin:6px 0 0}.ds-actions select{max-width:260px;padding:8px 28px 8px 10px;border-radius:8px;background:var(--surface2);border:1px solid var(--line);color:var(--ink)}
 .ds-card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:14px}#dsPlot{width:100%;height:280px;display:block}#dataSheet [hidden]{display:none!important}#projDataName{max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}#dsLegend{display:flex;gap:16px;flex-wrap:wrap;font-size:11px;margin:4px 0}#dsLegend span:before{content:'';display:inline-block;background:var(--series);width:14px;height:3px;vertical-align:middle;margin-right:6px}
 #dsTableScroll{max-height:260px;overflow:auto}#dsTable{width:100%;border-collapse:collapse;font-size:12px;font-variant-numeric:tabular-nums}#dsTable th,#dsTable td{padding:10px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}#dsTable th{position:sticky;top:0;background:var(--surface2);font-weight:500}#dsTable tr.ds-current{background:rgba(57,135,229,.12)}#dsTable tbody tr{cursor:pointer}#dsTable tbody tr:focus{outline:1px solid var(--s1)}
 #dsTools #warehouseDetails{border:0;margin:0;padding:0}#dsTools .wh-inputs{grid-template-columns:repeat(auto-fit,minmax(100px,1fr));gap:12px}#dsTools details{margin-top:12px}#dsTools p{font-size:12px;line-height:1.7;white-space:pre-wrap}#dsEmpty{padding:30px;text-align:center;color:var(--muted)}#dsNotice{color:var(--muted);font-size:11px;margin:10px 0}#dsError{color:var(--s3);font-size:12px}`);document.head.append(css);
 const box=el('section');box.id='dataSheet';box.setAttribute('aria-label','Data Sheet Viewer');box.innerHTML=`<header class="ds-heading"><div><h2 id="dsName"></h2><p id="dsCoverage"></p></div><div class="ds-actions"><select id="dsField" aria-label="그래프 물리량"></select><button class="btn" id="dsRead">전체 구간 읽기</button><button class="btn" id="dsExport">CSV 저장</button></div></header><p id="dsError" role="status"></p><div class="ds-card"><div id="dsLegend"></div><svg id="dsPlot" role="img" aria-label="저장 데이터 시간 그래프" viewBox="0 0 900 280"></svg><div id="dsEmpty"></div><p id="dsNotice"></p></div><div class="ds-card" id="dsTableScroll"><table id="dsTable"></table></div><div id="dsTools"></div><details id="dsModel"><summary>모델·검증</summary><p id="dsFacts"></p></details>`;$('viz').append(box);
 $('dsField').onchange=()=>{signature='';refresh();};$('dsRead').onclick=readAll;
 $('dsExport').onclick=()=>{const d=dataset();exportDownload(new Blob([sheetCSV(['시간 (s)',...d.series.map(s=>s.name+' · '+d.title)],sheetRows(d.series))],{type:'text/csv;charset=utf-8'}),'data-sheet.csv');};
 setInterval(()=>{if(mode==='data'&&ready)refresh();},500);
 }
 function choices(){if(!ready||(warehouseActive()&&!WH))return [];
 if(warehouseActive())return [{id:'gcV',title:'농도 ('+WH.unit+')'},...(WH.meta.available_fields?.includes('temperature')?[{id:'gcT',title:'온도 (°C)'}]:[]),...(WH.meta.available_fields?.includes('velocity')?[{id:'gcB',title:'유속 (m/s)'}]:[])];
 if(isTracerConfig(VIZCFG))return [{id:'concentration',title:'정규화 농도 (C/C_ref)'},{id:'sorbed',title:'정규화 흡착량 (Q/C_ref)'}];
 // The shared immersion series do not represent steady silo pressure/iterations.
 if(typeof isSiloConfig==='function'&&isSiloConfig(VIZCFG))return [];
 return GDEF;
 }
 function dataset(){const defs=choices(),def=defs.find(d=>d.id===$('dsField').value)||defs[0];if(!def)return {title:'',series:[]};
 let series;if(warehouseActive())series=warehouseSeries(def.id);else if(isTracerConfig(VIZCFG))series=sheetRanges(TRACERMAP[def.id]||{});else if(def.id==='gcV'||def.id==='gcB')series=[{name:def.title,color:def.color,pts:FRAMES.filter(f=>f.statsReady).map(f=>[f.t,f[def.id==='gcV'?'v':'n']??null])}];else series=gSeries(def.id);
 return {title:def.title,series};
 }
 function refresh(){mount();if(!ready||(warehouseActive()&&!WH)){$('dsName').textContent=context?.name||'실행 선택';$('dsCoverage').textContent=loadError||'결과 불러오는 중';$('dsError').textContent='';$('dsNotice').textContent='';$('dsPlot').replaceChildren();$('dsTable').replaceChildren();$('dsLegend').replaceChildren();$('dsEmpty').textContent='';$('dsExport').disabled=true;$('dsField').disabled=true;$('dsRead').disabled=true;return;}
 $('dsField').disabled=false;const defs=choices(),key=JSON.stringify(defs),select=$('dsField');if(select.dataset.key!==key){const prev=select.value;select.replaceChildren(...defs.map(d=>new Option(d.title,d.id)));if(defs.some(d=>d.id===prev))select.value=prev;select.dataset.key=key;}
 select.disabled=!defs.length;const d=dataset(),rows=sheetRows(d.series),key2=JSON.stringify([d,clock,reading,error]);if(key2===signature)return;signature=key2;
 $('dsName').textContent=context?.name||'계산 결과';$('dsCoverage').textContent=warehouseActive()?`읽은 프레임 ${WH.stats.size} / ${FRAMES.length}`:`읽은 데이터 ${rows.length}개 시점`;
 $('dsRead').hidden=!warehouseActive();$('dsRead').disabled=reading||WH?.stats.size===FRAMES.length;$('dsRead').textContent=reading?'읽는 중':'전체 구간 읽기';$('dsError').textContent=error;$('dsExport').disabled=!rows.length;
 $('dsModel').hidden=warehouseActive();$('dsFacts').textContent=`계산 모델: ${isTracerConfig(VIZCFG)?'정규화 추적자':context?.model||'미확인'} · 수치 검사: ${{passed:'통과',incomplete:'미완료'}[context?.numerical_status]||'미검사'} · 실험 검증: 미확인`;
 $('dsNotice').textContent=warehouseActive()?'저장 프레임의 셀 표본 범위 · 표의 행을 선택하면 해당 시점으로 이동':isTracerConfig(VIZCFG)?'읽은 격자 데이터 범위 · 정규화 값':'읽은 데이터 기준 · 열전대 그래프는 최근 600개 기록 · T5는 설정값, T6는 계산값';
 $('dsLegend').replaceChildren(...d.series.map(s=>{const n=el('span',s.name);n.style.setProperty('--series',s.color);return n;}));
 draw(d.series,rows,d.title);if(!defs.length){$('dsEmpty').textContent='이 해석 유형의 Data Sheet는 아직 지원하지 않습니다. 3D Viewer에서 확인하세요.';$('dsNotice').textContent='';}const head=el('thead'),hr=el('tr');for(const h of ['시간 (s)',...d.series.map(s=>s.name)])hr.append(el('th',h));head.append(hr);const body=el('tbody');
 const nearest=rows.length?rows.reduce((a,b)=>Math.abs(a[0]-clock)<=Math.abs(b[0]-clock)?a:b)[0]:null;
 for(const r of rows){const tr=el('tr');tr.tabIndex=0;if(r[0]===nearest)tr.className='ds-current';for(const v of r)tr.append(el('td',v==null?'—':String(Number(v.toPrecision(7)))));const seek=()=>{const i=FRAMES.findIndex(f=>Number(f.t)===r[0]);if(i>=0)scrub(i);};tr.onclick=seek;tr.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();seek();}};body.append(tr);}$('dsTable').replaceChildren(head,body);
 }
 function draw(series,rows,title){const svg=$('dsPlot');svg.replaceChildren();const points=series.flatMap(s=>s.pts).filter(([t,v])=>Number.isFinite(t)&&Number.isFinite(v));$('dsEmpty').textContent=points.length?'':'읽은 데이터가 없습니다.';svg.style.display=points.length?'block':'none';if(!points.length)return;
 let lo=Infinity,hi=-Infinity;for(const [,v] of points){lo=Math.min(lo,v);hi=Math.max(hi,v);}if(lo===hi){const p=Math.max(Math.abs(lo)*.05,1e-6);lo-=p;hi+=p;}const a=rows[0][0],b=rows.at(-1)[0],x=t=>70+(t-a)/Math.max(b-a,1e-12)*800,y=v=>235-(v-lo)/(hi-lo)*210;
 const add=(tag,attrs,text)=>{const n=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v);if(text!=null)n.textContent=text;svg.append(n);return n;};
 add('text',{x:70,y:15,fill:'#aaa','font-size':11},title);
 for(let i=0;i<=4;i++){const yy=25+i*52.5;add('line',{x1:70,y1:yy,x2:870,y2:yy,stroke:'#343431'});add('text',{x:62,y:yy+4,fill:'#aaa','font-size':11,'text-anchor':'end'},Number((hi-i*(hi-lo)/4).toPrecision(4)));const t=a+(b-a)*i/4;add('text',{x:x(t),y:259,fill:'#aaa','font-size':11,'text-anchor':'middle'},Number(t.toPrecision(5)));}add('text',{x:870,y:277,fill:'#aaa','font-size':11,'text-anchor':'end'},'시간 (s)');
 for(const s of series){let path='',gap=true;for(const [t,v] of [...s.pts].sort((a,b)=>a[0]-b[0])){if(!Number.isFinite(v)){gap=true;continue;}path+=(gap?'M':'L')+x(t)+','+y(v)+' ';gap=false;add('circle',{cx:x(t),cy:y(v),r:2,fill:s.color});}add('path',{d:path,fill:'none',stroke:s.color,'stroke-width':2,...(s.dash?{'stroke-dasharray':'5 4'}:{})});}
 if(clock>=a&&clock<=b)add('line',{x1:x(clock),x2:x(clock),y1:25,y2:235,stroke:'#ddd','stroke-dasharray':'3 4'});
 }
 async function readAll(){if(!ready||!warehouseActive()||reading)return;const token=epoch,w=WH;reading=true;error='';refresh();try{for(let i=0;i<FRAMES.length;i++){if(token!==epoch||mode!=='data'||WH!==w)return;if(w.stats.has(i))continue;const ok=await ensureWarehouseFrame(i);if(token!==epoch||mode!=='data'||WH!==w)return;if(!ok){error='일부 프레임을 읽지 못했습니다. 다시 읽으면 누락된 구간부터 확인합니다.';break;}refresh();}}finally{if(token===epoch){reading=false;signature='';refresh();}}}
 function setMode(value){mount();mode=value;epoch++;reading=false;document.body.classList.toggle('data-sheet-viewer',mode==='data');setPlay(false,true);signature='';refresh();if(mode==='data'&&ready&&warehouseActive()&&FRAMES.length<=200)readAll();return mode;}
 return {get mode(){return mode;},toggle(){return setMode(mode==='3d'?'data':'3d');},begin(value){mount();epoch++;reading=false;error='';loadError='';context=value;ready=false;signature='';$('dsTools').replaceChildren();$('dsModel').hidden=true;refresh();},loaded(){ready=FRAMES.length>0&&(!warehouseActive()||!!WH);loadError=ready?'':'결과를 읽지 못했습니다. 다시 읽기를 눌러 주세요.';if(!ready){refresh();return;}signature='';refresh();if(mode==='data'&&warehouseActive()&&FRAMES.length<=200)readAll();},suspend(){epoch++;reading=false;ready=false;document.body.classList.remove('data-sheet-viewer');},resume(){document.body.classList.toggle('data-sheet-viewer',mode==='data');},mount};
})();
