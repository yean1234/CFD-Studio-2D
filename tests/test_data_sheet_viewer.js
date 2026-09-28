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
