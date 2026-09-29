/* Config schema editor. Field keys and units are user-owned, never translated. */
(() => {
  const types=['string','number','integer','boolean','object','array','null'];
  const forbidden=new Set(['__proto__','prototype','constructor']);
  const clone=x=>structuredClone(x);
  const kind=value=>value===null?'null':Array.isArray(value)?'array':typeof value==='object'?'object':typeof value==='number'?(Number.isInteger(value)?'integer':'number'):typeof value;
  function fromConfig(config,previous=null){
    if(!config||typeof config!=='object'||Array.isArray(config))throw Error('Config must be a JSON object');
    function fields(object,prior=[],depth=0){
      if(depth>16)throw Error('Config nesting exceeds 16 levels');
      return Object.entries(object).map(([key,value])=>{const old=prior.find(f=>f.key===key),actual=kind(value),type=old?.nullable&&actual==='null'?old.type:old?.type==='number'&&actual==='integer'?'number':actual;return {key,type,unit:['value','x','y','z'].includes(key)&&typeof object.unit==='string'?object.unit:(old?.unit||''),...(old?.nullable?{nullable:true}:{}),...(typeof old?.required==='boolean'?{required:old.required}:{}),...(type==='object'?{fields:fields(value,old?.fields,depth+1)}:{value:clone(value)})};});
    }
    const schema={version:1,fields:fields(config,previous?.fields)};toConfig(schema);return schema;
  }
  function toConfig(schema){
    if(schema?.version!==1)throw Error('Config schema version must be 1');let count=0;
    function checkJSON(v,depth){if(depth>16)throw Error('Config nesting exceeds 16 levels');if(typeof v==='number'&&!Number.isFinite(v))throw Error('Config numbers must be finite');if(Array.isArray(v)){if(v.length>10000)throw Error('Config array is too large');for(const x of v)checkJSON(x,depth+1);}else if(v&&typeof v==='object')for(const [k,x] of Object.entries(v)){if(forbidden.has(k))throw Error('Reserved Config Key: '+k);checkJSON(x,depth+1);}}
    function group(fields,depth){
      if(depth>16||!Array.isArray(fields))throw Error('Invalid Config group');const result={};
      for(const f of fields){
        if(++count>512||!f||typeof f!=='object')throw Error('Config supports up to 512 fields');
        if(typeof f.key!=='string'||!f.key.trim()||f.key.length>80||forbidden.has(f.key))throw Error('Config Key must contain 1–80 characters and not be reserved');
        if(Object.hasOwn(result,f.key))throw Error('Duplicate Config Key: '+f.key);
        if(!types.includes(f.type))throw Error('Unsupported Config Type');
        if(typeof (f.unit??'')!=='string'||(f.unit||'').length>64)throw Error('Config Unit is too long');
        let value;
        if(f.type==='object')value=group(f.fields,depth+1);
        else{value=f.value;const actual=kind(value);if(actual!==f.type&&!(f.type==='number'&&actual==='integer')&&!(f.nullable===true&&value===null))throw Error('Config Value does not match Type: '+f.key);checkJSON(value,depth+1);value=clone(value);}
        result[f.key]=value;
      }return result;
    }return group(schema.fields,0);
  }
  function newField(fields){let n=1;while(fields.some(f=>f.key==='field_'+n))n++;return {key:'field_'+n,type:'number',unit:'',value:0};}
  function open({config={},schema=null,onSave,onValidate=null,title='Config'}){
    let draft=schema?clone(schema):fromConfig(config),mode='fields';toConfig(draft);const expanded=new WeakSet();
    const el=(tag,text,cls)=>{const x=document.createElement(tag);if(text!=null)x.textContent=text;if(cls)x.className=cls;return x;};
    const button=(text,fn)=>{const x=el('button',text,'btn');x.type='button';x.onclick=fn;return x;};
    if(!document.getElementById('formConfigStyle')){const style=el('style');style.id='formConfigStyle';style.textContent=`
      .fc-dialog{width:min(1000px,94vw);max-width:1000px;max-height:90vh;padding:24px;border:1px solid var(--line);border-radius:14px;background:var(--card,var(--page));color:var(--text);box-sizing:border-box}.fc-dialog::backdrop{background:#000a}
      .fc-header,.fc-actions,.fc-toolbar{display:flex;align-items:center;justify-content:space-between;gap:10px}.fc-header h2{font-size:18px;margin:0}.fc-toolbar{justify-content:flex-start;flex-wrap:wrap;margin:18px 0}.fc-body{max-height:60vh;overflow:auto;padding-right:6px}.fc-empty{padding:40px;text-align:center;color:var(--muted);border:1px dashed var(--line);border-radius:10px}.fc-field{border:1px solid var(--line);border-radius:10px;padding:12px;margin:10px 0;background:var(--page)}
      .fc-row{display:grid;grid-template-columns:minmax(120px,1.4fr) 125px minmax(70px,.6fr) minmax(120px,1.4fr) auto;gap:10px;align-items:start}.fc-field label{display:flex;flex-direction:column;gap:6px;font-size:11px;color:var(--muted)}.fc-field input,.fc-field select,.fc-field textarea,.fc-json{box-sizing:border-box;width:100%;background:var(--card,var(--page));color:var(--text);border:1px solid var(--line);border-radius:7px;padding:8px;font:12px Consolas,monospace;min-height:34px}.fc-field .btn{margin-top:19px}.fc-children{padding-left:16px;border-left:2px solid var(--line);margin-top:12px}.fc-children>.btn{margin-top:6px}.fc-group{border:1px solid var(--line);border-radius:10px;margin:10px 0;background:var(--page)}.fc-group>summary{display:flex;align-items:center;gap:12px;cursor:pointer;padding:14px;list-style:none;font-size:13px}.fc-group>summary::-webkit-details-marker{display:none}.fc-group>summary small{margin-left:auto;color:var(--muted);font-size:11px}.fc-group>summary::after{content:'⌄';font-size:18px;color:var(--muted);transition:transform .15s}.fc-group[open]>summary::after{transform:rotate(180deg)}.fc-group>.fc-field{border:0;margin:0;border-top:1px solid var(--line);border-radius:0 0 10px 10px}.fc-json{min-height:360px;resize:vertical}.fc-error{color:var(--red,#ef8989);font-size:12px;min-height:18px;white-space:pre-wrap}.fc-required{color:var(--accent,#579eff);font-size:10px;margin:0 0 8px}.fc-dialog:has(.fc-validation) .fc-body{max-height:42vh}.fc-validation{max-height:16vh;overflow:auto;font-size:12px;padding:12px;border:1px solid var(--line);border-radius:9px;margin:12px 0}.fc-validation ul{max-height:140px;overflow:auto;padding-left:18px}.fc-actions{justify-content:flex-end;margin-top:14px}.fc-toolbar [aria-pressed=true]{border-color:var(--accent,#579eff)}
      @media(max-width:700px){.fc-row{grid-template-columns:1fr 1fr}.fc-row>.btn{grid-column:2}.fc-children{padding-left:6px}}
    `;document.head.append(style);}
    const dialog=el('dialog',null,'fc-dialog'),header=el('div',null,'fc-header');header.append(el('h2',title));dialog.append(header);
    const toolbar=el('div',null,'fc-toolbar'),body=el('div',null,'fc-body'),error=el('p',null,'fc-error'),actions=el('div',null,'fc-actions');error.setAttribute('role','alert');
    let jsonArea;const commitJSON=()=>{if(mode==='json')draft=fromConfig(JSON.parse(jsonArea.value),draft);};
    const guarded=fn=>{try{error.textContent='';fn();}catch(e){error.textContent=e.message;}};
    const fieldButton=button('Fields',()=>guarded(()=>{commitJSON();mode='fields';render();}));const jsonButton=button('JSON',()=>guarded(()=>{if(mode==='json')return;toConfig(draft);mode='json';render();}));
    const add=button('+ Field',()=>guarded(()=>{commitJSON();draft.fields.push(newField(draft.fields));mode='fields';render();}));
    const upload=el('input');upload.type='file';upload.accept='.json,application/json';upload.hidden=true;
    upload.onchange=async()=>{const file=upload.files[0];if(!file)return;try{if(file.size>1000000)throw Error('JSON file must be under 1 MB');const next=fromConfig(JSON.parse(await file.text()),draft);draft=next;mode='fields';error.textContent='';render();}catch(e){error.textContent=e.message;}upload.value='';};
    toolbar.append(fieldButton,jsonButton,add,button('Import JSON',()=>upload.click()),button('Download JSON',()=>guarded(()=>{commitJSON();const a=el('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(toConfig(draft),null,2)],{type:'application/json'}));a.download='cfd-config.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);})),upload);dialog.append(toolbar,body,error,actions);
    if(onValidate){const report=el('section',null,'fc-validation');report.setAttribute('aria-live','polite');report.textContent='Required 항목을 입력한 뒤 입력 검사로 누락값을 확인하세요. 초안 저장·JSON 출력은 미입력 상태에서도 가능합니다.';body.after(report);const check=button('입력 검사',async()=>{check.disabled=true;try{commitJSON();const result=await onValidate(toConfig(draft));report.replaceChildren(el('strong',result.missing_count?'필수 입력 '+result.missing_count+'개 확인 필요':'정의된 필수 입력 작성 완료'),el('p','입력 완전성 검사 · 물리 검증·실행 연결은 별도'));const list=el('ul');for(const issue of result.issues){list.append(el('li',issue.path.join('.')+' · '+issue.message));}for(const note of result.model_review||[])list.append(el('li',note));report.append(list);}catch(e){report.textContent=e.message;}finally{check.disabled=false;}});toolbar.append(check);}
    function renderFields(fields,host,path=''){
      for(const [index,field] of fields.entries()){
        const box=el('div',null,'fc-field'),row=el('div',null,'fc-row'),label=path+field.key;
        let heading;
        if(!path&&field.type==='object'){
          const section=el('details',null,'fc-group'),summary=el('summary');heading=el('span',field.key);summary.append(heading,el('small',field.fields.length+' fields'));section.append(summary,box);section.open=expanded.has(field);section.ontoggle=()=>{if(section.open)expanded.add(field);else expanded.delete(field);};host.append(section);
        }else host.append(box);
        if(field.required)box.append(el('p','Required','fc-required'));box.append(row);
        const input=(caption,node)=>{const l=el('label',caption);node.setAttribute('aria-label',label+' '+caption);l.append(node);row.append(l);return node;};
        const key=input('Key',el('input'));key.value=field.key;key.maxLength=80;key.oninput=()=>{field.key=key.value;if(heading)heading.textContent=key.value;};
        const type=input('Type',el('select'));for(const t of types)type.append(new Option(t,t));type.value=field.type;
        const unit=input('Unit',el('input'));unit.value=field.unit||'';unit.maxLength=64;unit.placeholder='—';unit.oninput=()=>field.unit=unit.value;
        type.onchange=()=>{field.type=type.value;delete field.fields;delete field.value;if(field.type==='object')field.fields=[];else field.value={string:'',number:0,integer:0,boolean:false,array:[],null:null}[field.type];render();};
        if(field.type==='object'){const count=el('output',field.fields.length+' fields');input('Value',count);}
        else if(field.type==='boolean'){const v=input('Value',el('select'));v.append(new Option('true','true'),new Option('false','false'));v.value=String(field.value);v.onchange=()=>field.value=v.value==='true';}
        else if(field.type==='null')input('Value',el('output','null'));
        else if(field.type==='array'){const v=input('Value',el('textarea'));v.rows=2;v.value=JSON.stringify(field.value);v.oninput=()=>{try{const value=JSON.parse(v.value);field.value=value;}catch(_){field.value=undefined;}};}
        else{const v=input('Value',el('input'));v.type=['number','integer'].includes(field.type)?'number':'text';v.step=field.type==='integer'?'1':'any';v.value=field.value??'';v.placeholder=field.nullable?'Enter value':'';v.oninput=()=>field.value=v.type==='number'?(v.value.trim()===''?null:Number(v.value)):v.value;}
        const remove=button('Remove',()=>{fields.splice(index,1);render();});remove.setAttribute('aria-label',label+' Remove');row.append(remove);
        if(field.type==='object'){const children=el('div',null,'fc-children');box.append(children);renderFields(field.fields,children,label+'.');children.append(button('+ Field',()=>{field.fields.push(newField(field.fields));render();}));}
      }
    }
    function render(){body.replaceChildren();fieldButton.setAttribute('aria-pressed',String(mode==='fields'));jsonButton.setAttribute('aria-pressed',String(mode==='json'));if(mode==='json'){jsonArea=el('textarea',null,'fc-json');jsonArea.setAttribute('aria-label','Config JSON');jsonArea.spellcheck=false;jsonArea.value=JSON.stringify(toConfig(draft),null,2);body.append(jsonArea);}else if(!draft.fields.length)body.append(el('div','+ Field 또는 Import JSON으로 Config를 정의하세요.','fc-empty'));else renderFields(draft.fields,body);}
    const save=button('Apply',async()=>{save.disabled=true;try{commitJSON();const value=toConfig(draft);await onSave(value,clone(draft));dialog.close();}catch(e){error.textContent=e.message;}finally{save.disabled=false;}});save.classList.add('pri');actions.append(button('Cancel',()=>dialog.close()),save);
    dialog.onclose=()=>dialog.remove();render();document.body.append(dialog);dialog.showModal();
  }
  const api={fromConfig,toConfig,newField,open};if(typeof module!=='undefined'&&module.exports)module.exports=api;else window.CFDFormConfig=api;
})();
