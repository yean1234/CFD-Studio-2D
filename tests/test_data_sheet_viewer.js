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

const {sheetCoordinateBounds,sheetAxes}=require('../cfd_studio/internal/data_sheet_viewer.js');
test('coordinate bounds follow the gable at the entered transverse coordinate without mutating metadata',()=>{
 const metric={bounds_m:[[0,78],[0,25],[0,10]]},domain={kind:'gable',width_m:25,eaves_m:7,roof_rise_m:3};
 assert.equal(sheetCoordinateBounds(metric,domain,0)[2][1],7);
 assert.equal(sheetCoordinateBounds(metric,domain,12.5)[2][1],10);
 assert.equal(sheetCoordinateBounds(metric,domain,25)[2][1],7);
 assert.equal(metric.bounds_m[2][1],10);
 assert.equal(sheetCoordinateBounds({},null,null),null);
});
test('multiple graph units keep separate Y ranges and matching units share a scale',()=>{
 const series=[{unit:'°C',color:'blue',pts:[[0,20],[1,30]]},{unit:'m/s',color:'orange',pts:[[0,.1],[1,.2]]},{unit:'°C',color:'green',pts:[[0,100],[1,null]]}];
 const axes=sheetAxes(series);assert.equal(axes.length,2);assert.ok(axes[0].lo<20&&axes[0].hi>100);assert.ok(axes[1].lo<.1&&axes[1].hi<1);
});
