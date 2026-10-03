/* Map result fields to shared Viewer controls, units and timeline behavior */
(function(root){
'use strict';
const fields={
 concentration:{label:'농도장',kind:'scalar',renderer:'scalar-cloud',unit:'C/C_ref',values:'concentration',range:['minimum','maximum']},
 sorbed:{label:'흡착량',kind:'scalar',renderer:'scalar-cloud',unit:'Q/C_ref'},
 temperature:{label:'온도장',kind:'scalar',renderer:'scalar-cloud',unit:'°C',values:'temperature_field_C',range:'temperature_range_C'},
 velocity:{label:'속도장',kind:'vector',renderer:'vectors',unit:'m/s',values:'velocity_m_s',range:'speed_range_m_s'},
 pressure:{label:'압력장',kind:'scalar',renderer:'scalar-cloud',unit:'m²/s²'},
 turbulence:{label:'난류장 (k)',kind:'scalar',renderer:'scalar-cloud',unit:'m²/s²'},
 phase:{label:'액체 상분율',kind:'fractions',renderer:'phase-volume',unit:'1'},
 bubble:{label:'증기 기포',kind:'particles',renderer:'particles',unit:'mL'},
 history:{label:'시계열',kind:'series',renderer:'chart',unit:null},
 geometry:{label:'공간 형상',kind:'geometry',renderer:'mesh',unit:'m'}
};
const aliases={flow:'velocity',therm:'temperature',speed:'velocity',k:'turbulence'};
// Legacy controls are slots, not physical field identifiers.
const layouts={
 immersion:{lyBub:'bubble',lyPhase:'phase',lySlice:'velocity',lyTvol:'temperature'},
 grain_silo:{lyBub:'pressure',lyPhase:'turbulence',lySlice:'velocity'},
 gas_transport:{lyBub:'concentration',lyPhase:'sorbed'},
 warehouse:{lyBub:'concentration',lySlice:'velocity',lyTvol:'temperature'}
};
function field(id,metadata={}){const key=aliases[id]||id,base=fields[key];if(!base)return null;return {...base,id:key,...(typeof metadata.label==='string'&&metadata.label?{label:metadata.label}:{}),...(typeof metadata.unit==='string'&&metadata.unit?{unit:metadata.unit}:{})};}
function layers(format,available=null,metadata={}){const allowed=available&&new Set(available.map(k=>aliases[k]||k));return Object.entries(layouts[format]||{}).map(([control,id])=>({control,...field(id,metadata[id]),available:!allowed||allowed.has(id)}));}
function range(frame,id){const spec=field(id);if(!spec)return null;const value=Array.isArray(spec.range)?spec.range.map(k=>frame[k]):frame[spec.range];return Array.isArray(value)&&value.length===2&&value.every(Number.isFinite)?value:null;}
function values(frame,id){const spec=field(id);return spec?.values?frame[spec.values]:null;}
// Times share the result axis unit: seconds for transient data, iterations for steady data
function timeline(times,time){if(!times.length)return {value:0,time:0,index:0,disabled:true};const first=times[0],last=times.at(-1),t=Math.max(first,Math.min(last,Number.isFinite(time)?time:first));let lo=0,hi=times.length;while(lo+1<hi){const mid=(lo+hi)>>1;if(times[mid]<=t)lo=mid;else hi=mid;}return {value:last>first?(t-first)/(last-first):0,time:t,index:lo,disabled:times.length<2||last<=first};}
function seek(times,value){const p=Math.max(0,Math.min(1,Number(value)||0));return timeline(times,times.length?times[0]+p*(times.at(-1)-times[0]):0);}
function sync(element,times,time){const state=timeline(times,time);element.min=0;element.max=1;element.step='any';element.value=state.value;element.disabled=state.disabled;return state;}
const api={field,layers,range,values,timeline,seek,sync};if(typeof module!=='undefined')module.exports=api;else root.CFDPresentation=api;
})(globalThis);
