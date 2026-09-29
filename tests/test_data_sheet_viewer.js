const test=require('node:test'),assert=require('node:assert/strict');
const {sheetRows,sheetCSV,sheetRanges}=require('../cfd_studio/internal/data_sheet_viewer.js');
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

const {sheetMetricKey,sheetPick}=require('../cfd_studio/internal/data_sheet_viewer.js');
test('comparison never mixes normalized and physical units or steady and transient axes',()=>{
 const metric={id:'concentration.mean',unit:'mg/m³'};
 assert.notEqual(sheetMetricKey(metric,'time'),sheetMetricKey({...metric,unit:'C/C_ref'},'time'));
 assert.notEqual(sheetMetricKey(metric,'time'),sheetMetricKey(metric,'iteration'));
});
test('cursor snaps to a stored X and preserves precise Y without interpolating another Case',()=>{
 const s=[{pts:[[0,.123456789123],[2,3]]},{pts:[[1,8],[2,4]]}];
 assert.deepEqual(sheetPick(s,.01),[0,.123456789123,null]);assert.deepEqual(sheetPick(s,1.8),[2,3,4]);
 assert.deepEqual(sheetPick(s,.7),[1,null,8]);assert.equal(sheetPick([],0),null);
});
