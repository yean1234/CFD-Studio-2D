const test=require('node:test'),assert=require('node:assert/strict');
const {sheetRows,sheetCSV,sheetRanges}=require('../cfd_studio/data_sheet_viewer.js');
test('aligns physical times and keeps missing and invalid data empty',()=>{
 const series=[{pts:[[2,0],[0,1],[3,NaN]]},{pts:[[1,4],[2,5],[3,Infinity]]}];
 assert.deepEqual(sheetRows(series),[[0,1,null],[1,null,4],[2,0,5],[3,null,null]]);
});
test('CSV preserves precision, quotes text, blanks missing values and neutralizes formulas',()=>{
 const csv=sheetCSV(['시간','="bad"'],[[.123456789,0],[1,null]]);
 assert.ok(csv.includes('"0.123456789","0"'));assert.ok(csv.includes('"1",""'));assert.ok(csv.includes('"\'=""bad"""'));
});
test('normalized arrays report their actual bounds without mutating source',()=>{
 const map={2:{v:new Float32Array([0,2,1])},0:{v:new Float32Array([0,0])},3:{v:[]}};
 const series=sheetRanges(map);assert.deepEqual(series[0].pts,[[0,0],[2,0],[3,null]]);assert.deepEqual(series[1].pts,[[0,0],[2,2],[3,null]]);assert.equal(map[2].v[1],2);
});

const vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
function sheetContext(){
 class Node {constructor(){this.dataset={};this.style={setProperty(){}};this.value='';this.children=[];}append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=nodes;if(nodes[0]?.value)this.value=nodes[0].value;}setAttribute(){} }
 const nodes=new Map(),get=id=>{if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);};
 const ctx={document:{getElementById:get,createElement:()=>new Node(),body:{classList:{toggle(){},remove(){}}}},
 VIZCFG:{},Option:function(title,value){this.value=value;},warehouseActive:()=>true,isTracerConfig:()=>false,
 WH:{unit:'C/C_ref',meta:{available_fields:[]},stats:new Map()},FRAMES:[{t:0}],warehouseSeries:()=>[],clock:0,setPlay(){},ensureWarehouseFrame:async()=>true};
 vm.createContext(ctx);vm.runInContext(fs.readFileSync(path.join(__dirname,'../cfd_studio/data_sheet_viewer.js'),'utf8')+';globalThis.viewer=DataSheetViewer;',ctx);
 return {ctx,get};
}
test('failed result stays failed when toggling modes and clears stale controls',()=>{
 const {ctx,get}=sheetContext();ctx.viewer.begin({name:'failed'});ctx.FRAMES=[];ctx.viewer.loaded();ctx.viewer.toggle();
 assert.match(get('dsCoverage').textContent,/읽지 못했습니다/);assert.equal(get('dsExport').disabled,true);assert.equal(get('dsTable').children.length,0);
});
test('an old frame failure cannot overwrite the newly selected Case',async()=>{
 const {ctx,get}=sheetContext();let finish;ctx.ensureWarehouseFrame=()=>new Promise(resolve=>finish=resolve);
 ctx.viewer.begin({name:'old'});ctx.viewer.loaded();ctx.viewer.toggle();ctx.viewer.begin({name:'new'});
 finish(false);await Promise.resolve();await Promise.resolve();ctx.FRAMES=Array.from({length:201},(_,i)=>({t:i}));ctx.viewer.loaded();assert.equal(get('dsName').textContent,'new');assert.equal(get('dsError').textContent,'');
});

test('steady silo does not show immersion fields or label iterations as seconds',()=>{
 const {ctx,get}=sheetContext();ctx.warehouseActive=()=>false;ctx.isSiloConfig=()=>true;
 ctx.viewer.begin({name:'silo',model:'grain_silo'});ctx.viewer.loaded();
 assert.equal(get('dsField').disabled,true);assert.equal(get('dsExport').disabled,true);
 assert.match(get('dsEmpty').textContent,/아직 지원하지 않습니다/);assert.equal(get('dsPlot').children.length,0);
});
