/* Shared, non-destructive input feedback. Values are never silently coerced. */
(() => {
 const numeric=/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i;
 function acceptsEdit(text,type){
  if(type==='integer')return /^[+-]?\d*$/.test(text)&&(!/\d/.test(text)||Number.isSafeInteger(Number(text)));
  if(type!=='number')return true;
  const partial=/^[+-]?\d*(?:\.\d*)?$/.test(text)||/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)[eE][+-]?\d*$/.test(text);
  return partial&&(!numeric.test(text)||Number.isFinite(Number(text)));
 }
 function parseValue(raw,type,{nullable=false}={}){
  const text=raw.trim();
  if(type==='string')return raw;
  if(!text&&nullable)return null;
  if(type==='number'||type==='integer'){
   if(!text||!numeric.test(text)||!Number.isFinite(Number(text)))throw Error('숫자를 입력하세요. 예: 1, 0.5, 1e-3');
   const n=Number(text);if(type==='integer'&&!Number.isSafeInteger(n))throw Error('정수를 입력하세요. 예: 1, 2, 3');return n;
  }
  let value;try{value=JSON.parse(text);}catch(_){throw Error('올바른 JSON 형식으로 입력하세요.');}
  const finite=v=>{if(typeof v==='number'&&!Number.isFinite(v))throw Error('유한한 숫자를 입력하세요.');if(v&&typeof v==='object')Object.values(v).forEach(finite);};finite(value);
  if(type==='array'&&!Array.isArray(value))throw Error('배열을 입력하세요. 예: [1, 2, 3]');
  if(type==='object'&&(!value||typeof value!=='object'||Array.isArray(value)))throw Error('JSON 객체를 입력하세요. 예: {"key": 1}');
  return value;
 }
 if(typeof module!=='undefined')module.exports={parseValue,acceptsEdit};
 if(typeof document==='undefined')return;
 const records=new WeakMap();let sequence=0;
 const style=document.createElement('style');style.textContent=`input[aria-invalid="true"],textarea[aria-invalid="true"],select[aria-invalid="true"]{color:#ff9292!important;-webkit-text-fill-color:#ff9292!important;border-color:#ff9292!important}.input-feedback-wrap{display:flex;flex-direction:column;gap:5px;min-width:0;flex:1}.input-feedback-wrap>input,.input-feedback-wrap>textarea{width:100%;box-sizing:border-box}.input-feedback{display:block;color:#ff9292!important;font-size:11px!important;line-height:1.4;white-space:normal!important}.input-feedback[hidden]{display:none!important}`;document.head.append(style);
 function present(node,message){
  let record=records.get(node);if(!record){record={};records.set(node,record);}node.setAttribute('aria-invalid',String(!!message));
  if(message&&!record.note&&node.parentElement){
   const active=document.activeElement===node,start=node.selectionStart,end=node.selectionEnd;
   const wrap=document.createElement('span');wrap.className='input-feedback-wrap';
   const note=document.createElement('small');note.className='input-feedback';note.id='input-feedback-'+(++sequence);note.setAttribute('aria-live','polite');record.note=note;
   node.before(wrap);wrap.append(node,note);
   node.setAttribute('aria-describedby',[node.getAttribute('aria-describedby'),note.id].filter(Boolean).join(' '));
   if(active){node.focus({preventScroll:true});if(start!==null&&end!==null)node.setSelectionRange(start,end);}
  }
  if(record.note){if(globalThis.CFDConfigContract){const e=message?new Error(message):null;if(e)e.path=(node.dataset.configPath||'').split('.').filter(Boolean);CFDConfigContract.display(record.note,e);}else record.note.textContent=message;record.note.hidden=!message;}
 }
 function check(node,{show=true,editing=false}={}){
  if(!node?.matches?.('input,textarea,select')||node.disabled||node.readOnly)return true;
  const record=records.get(node),type=record?.type;let message='';
  if(type){node.setCustomValidity('');try{const value=parseValue(node.value,type,{nullable:record.nullable});
    if(typeof value==='number'){
     const min=node.getAttribute('min'),max=node.getAttribute('max');
     if(min!==null&&value<Number(min)||max!==null&&value>Number(max))throw Error(min!==null&&max!==null?min+' ~ '+max+' 범위로 입력하세요.':min!==null?min+' 이상으로 입력하세요.':max+' 이하로 입력하세요.');
    }
   }catch(e){message=e.message;}node.setCustomValidity(globalThis.CFDI18n?.translate(message)||message);
  }
  if(!message&&!node.validity.valid){const v=node.validity;message=v.badInput?'숫자를 입력하세요.':v.valueMissing?'값을 입력하세요.':v.stepMismatch?'허용된 간격에 맞는 값을 입력하세요.':v.rangeUnderflow?node.min+' 이상으로 입력하세요.':v.rangeOverflow?node.max+' 이하로 입력하세요.':node.validationMessage;}
  if(show)present(node,editing&&type&&message&&!node.value.trim()?'':editing&&['number','integer'].includes(type)&&acceptsEdit(node.value,type)&&!numeric.test(node.value)?'':message);return !message;
 }
 function bind(node,{type,nullable=false}={}){
  const record=records.get(node)||{};Object.assign(record,{type,nullable});records.set(node,record);
  if(node.type==='number'&&(type==='number'||type==='integer')){node.type='text';node.inputMode='decimal';}
  if(type==='number'||type==='integer'){
   node.inputMode=type==='integer'?'numeric':'decimal';record.last=node.value;
   const candidate=text=>node.value.slice(0,node.selectionStart??0)+text+node.value.slice(node.selectionEnd??node.value.length);
   node.addEventListener('beforeinput',event=>{if(event.isComposing)return;if(event.inputType.startsWith('insert')&&event.data!==null&&!acceptsEdit(candidate(event.data),type))event.preventDefault();});
   node.addEventListener('paste',event=>{const text=event.clipboardData?.getData('text');if(text==null)return;event.preventDefault();const next=candidate(text.trim());try{parseValue(next,type,{nullable});}catch(_){return;}node.setRangeText(text.trim(),node.selectionStart??0,node.selectionEnd??node.value.length,'end');node.dispatchEvent(new Event('input',{bubbles:true}));});
   node.addEventListener('input',event=>{if(event.isComposing)return;if(!acceptsEdit(node.value,type))node.value=record.last;else record.last=node.value;},true);
   node.addEventListener('compositionend',()=>{if(!acceptsEdit(node.value,type))node.value=record.last;else record.last=node.value;node.dispatchEvent(new Event('input',{bubbles:true}));});
  }
  node.addEventListener('input',()=>check(node,{editing:true}));return node;
 }
 function assertValid(root){let first;for(const node of root.querySelectorAll('input,textarea,select'))if(!check(node)&&!first)first=node;
  if(first){for(let p=first.parentElement;p&&p!==root;p=p.parentElement)if(p.tagName==='DETAILS')p.open=true;first.focus();const info=records.get(first)?.note?.dataset.errorInfo;const detail=info?JSON.parse(info):null;throw globalThis.CFDConfigContract?CFDConfigContract.issue(detail?.code||'CFG-J004',detail?.detail||first.validationMessage,(first.dataset.configPath||'').split('.').filter(Boolean)):Error('빨간색으로 표시된 입력값을 수정하세요.');}}
 for(const event of ['input','change','focusout'])document.addEventListener(event,e=>{
  // Submit-only forms defer feedback until native submission validation.
  if(e.target.closest?.('form[data-validation="submit"]')){
   if(event!=='focusout')present(e.target,'');
   return;
  }
  check(e.target,{editing:event==='input'});
 });
 document.addEventListener('invalid',e=>check(e.target),true);
 globalThis.addEventListener('cfd-language-change',()=>{for(const node of document.querySelectorAll('[aria-invalid="true"]'))check(node);});
 globalThis.CFDInput={parseValue,acceptsEdit,bind,check,assertValid,reset(node){const record=records.get(node);if(record)record.last=node.value;node.setCustomValidity('');present(node,'');node.removeAttribute('aria-invalid');}};
})();
