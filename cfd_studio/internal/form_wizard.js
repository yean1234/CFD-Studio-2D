/* Questionnaire only builds input forms; it never starts a CFD calculation. */
(() => {
    const el=(tag,text,cls)=>{const e=document.createElement(tag);if(text!=null)e.textContent=text;if(cls)e.className=cls;return e;};
  function ensureStyle(){
    if(!document.getElementById('formWizardStyle')){const style=el('style');style.id='formWizardStyle';style.textContent=`
      .fw-dialog [hidden]{display:none!important}.fw-dialog{width:min(720px,94vw);max-height:90vh;overflow:auto;border:1px solid var(--line);border-radius:14px;padding:24px;background:var(--card,var(--page));color:var(--text)}.fw-dialog::backdrop{background:#000a}.fw-dialog h2{font-size:18px;margin:0 0 8px}.fw-meta{color:var(--muted);font-size:12px;margin-bottom:20px}.fw-progress{display:flex;gap:8px;margin:0 0 24px}.fw-progress span{flex:1;padding:10px;border-bottom:2px solid var(--line);font-size:12px;color:var(--muted)}.fw-progress [aria-current=step]{color:var(--text);border-color:var(--accent,#579eff)}.fw-question{border:0;padding:0;margin:0 0 22px}.fw-question legend{font-size:14px;font-weight:600;margin-bottom:12px}.fw-options{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.fw-choice{display:flex;align-items:center;gap:10px;padding:14px;border:1px solid var(--line);border-radius:10px;cursor:pointer;background:var(--page);font-size:13px}.fw-choice:has(input:checked){border-color:var(--accent,#579eff);background:color-mix(in srgb,var(--accent,#579eff) 10%,var(--page))}.fw-choice input{width:16px;height:16px;accent-color:var(--accent,#579eff)}.fw-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:18px}.fw-error{color:var(--red,#f88);font-size:12px;min-height:18px}.fw-summary{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:16px 0}.fw-summary div{padding:12px;border:1px solid var(--line);border-radius:9px;font-size:13px}.fw-note{font-size:12px;color:var(--muted);line-height:1.7}.fw-dialog button{min-width:75px}@media(max-width:520px){.fw-options,.fw-summary{grid-template-columns:1fr}}
    `;document.head.append(style);}
  }

  function open({profile,answers={},replace=false,generate,onApply}){
    let step=0,busy=false,generated=null;
    const values={};for(const [key,options] of Object.entries(profile.options)){if(options.some(o=>o.value===answers[key]))values[key]=answers[key];else if(options.length===1)values[key]=options[0].value;}
    const steps=[['유체','medium'],['해석','purpose','regime'],['구성','domain','mesh','termination'],['확인']];
    const titles={medium:'어떤 유체를 해석하나요?',purpose:'어떤 해석을 구성하나요?',regime:'유동 모델은 무엇인가요?',domain:'해석 영역은 어디인가요?',mesh:'격자는 어떻게 준비하나요?',termination:'어떤 기준으로 종료하나요?'};
    ensureStyle();
    const dialog=el('dialog',null,'fw-dialog'),title=el('h2','CFD Template 구성'),meta=el('div',profile.solver+' · '+(profile.time_mode==='steady'?'정상 해석':'비정상 해석'),'fw-meta'),progress=el('nav',null,'fw-progress'),body=el('div'),error=el('div',null,'fw-error'),actions=el('div',null,'fw-actions');error.setAttribute('role','alert');progress.setAttribute('aria-label','양식 구성 단계');
    const btn=(text,fn,cls='')=>{const b=el('button',text,'btn '+cls);b.type='button';b.onclick=fn;return b;};
    const cancel=btn('취소',()=>dialog.close()),back=btn('이전',()=>{if(step>0){step--;render();}}),next=btn('다음',async()=>{
      if(busy)return;error.textContent='';
      if(step<3){for(const key of steps[step].slice(1)){if(!values[key]){error.textContent=titles[key];return;}}}
      if(step<2){step++;render();return;}
      busy=true;next.disabled=true;back.disabled=true;
      try{
        if(step===2){const result=await generate({...values});if(!dialog.isConnected)return;generated=result;step=3;render();}
        else{await onApply(generated);dialog.close();}
      }catch(e){if(dialog.isConnected)error.textContent=e.message;}
      finally{busy=false;next.disabled=false;back.disabled=step===0;}
    },'pri');actions.append(cancel,back,next);dialog.append(title,meta,progress,body,error,actions);
    function render(){
      error.textContent='';progress.replaceChildren();for(const [i,s] of steps.entries()){const n=el('span',(i+1)+'. '+s[0]);if(i===step)n.setAttribute('aria-current','step');progress.append(n);}
      body.replaceChildren();back.hidden=step===0;back.disabled=step===0;next.textContent=step===3?(replace?'새 양식으로 교체':'양식 생성'):'다음';
      if(step<3){for(const key of steps[step].slice(1)){const group=el('fieldset',null,'fw-question'),legend=el('legend',titles[key]),options=el('div',null,'fw-options');group.append(legend,options);for(const item of profile.options[key]){const label=el('label',null,'fw-choice'),input=el('input');input.type='radio';input.name=key;input.value=item.value;input.checked=values[key]===item.value;input.onchange=()=>values[key]=item.value;label.append(input,el('span',item.label));options.append(label);}body.append(group);}body.append(el('p',profile.note,'fw-note'));}
      else{body.append(el('p','선택한 조건에 맞는 빈 Config 양식 · 실제 값은 프로젝트 생성 시 입력','fw-note'));const list=el('div',null,'fw-summary');for(const value of Object.values(generated.summary.choices))list.append(el('div',value));body.append(list,el('p',generated.sections.join(' · '),'fw-note'));if(replace)body.append(el('p','적용 시 현재 Config 양식을 새 양식으로 교체','fw-note'));body.append(btn('JSON 다운로드',()=>{const a=el('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(generated.config,null,2)],{type:'application/json'}));a.download=profile.solver+'-config.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}));}
    }
    dialog.onclose=()=>dialog.remove();render();document.body.append(dialog);dialog.showModal();
  }
  function recommend({options,answers={},selected='',fixedSolver=null,replace=false,loadRecommendations,generate,onApply}){
    ensureStyle();
    let step=0,busy=false,candidates=[],chosen='',summary=null;
    const values={};for(const [key,items] of Object.entries(options))if(items.some(x=>x.value===answers[key]))values[key]=answers[key];
    const steps=[['해석 대상','medium','purpose'],['유동·시간','regime','time_mode'],['영역·종료','domain','mesh','termination'],['솔버 선택']];
    const titles={medium:'어떤 유체를 해석하나요?',purpose:'어떤 해석을 구성하나요?',regime:'유동 모델은 무엇인가요?',time_mode:'시간에 따른 변화를 계산하나요?',domain:'해석 영역은 어디인가요?',mesh:'격자는 어떻게 준비하나요?',termination:'어떤 기준으로 종료하나요?'};
    const d=el('dialog',null,'fw-dialog fw-recommend-dialog'),title=el('h2','새 CFD Template'),progress=el('nav',null,'fw-progress'),body=el('div'),error=el('p',null,'fw-error'),actions=el('div',null,'fw-actions');error.setAttribute('role','alert');
    const button=(label,fn,cls='')=>{const b=el('button',label,'btn '+cls);b.type='button';b.onclick=fn;return b;};
    const cancel=button('취소',()=>d.close()),back=button('이전',()=>{if(!busy&&step>0){step--;render();}}),next=button('다음',async()=>{
      if(busy)return;error.textContent='';
      if(step<3)for(const key of steps[step].slice(1)){if(!values[key]){error.textContent=titles[key];return;}}
      if(step<2){step++;render();return;}
      if(step===3&&!chosen){error.textContent='추천 목록에서 솔버를 선택하세요';return;}
      busy=true;next.disabled=true;back.disabled=true;for(const input of body.querySelectorAll('input'))input.disabled=true;
      const snapshot={...values};
      try{
        if(step===2){summary=await loadRecommendations(snapshot);if(!d.isConnected)return;candidates=summary.candidates.filter(x=>!fixedSolver||x.solver===fixedSolver);chosen=candidates.some(x=>x.solver===selected)?selected:'';step=3;}
        else{const result=await generate(chosen,snapshot);if(!d.isConnected)return;await onApply({solver:chosen,answers:snapshot,result});if(d.isConnected)d.close();return;}
      }catch(e){if(d.isConnected)error.textContent=e.message;}
      finally{busy=false;if(d.isConnected)render();}
    },'pri');actions.append(cancel,back,next);d.append(title,progress,body,error,actions);
    function render(){
      progress.replaceChildren();for(const [i,s] of steps.entries()){const n=el('span',(i+1)+'. '+s[0]);if(i===step)n.setAttribute('aria-current','step');progress.append(n);}
      body.replaceChildren();back.hidden=step===0;back.disabled=busy;next.disabled=busy||(step===3&&!chosen);next.textContent=step===2?'솔버 추천':step===3?'양식 생성':'다음';
      if(step<3){
        for(const key of steps[step].slice(1)){
          const group=el('fieldset',null,'fw-question'),choices=el('div',null,'fw-options');group.append(el('legend',titles[key]),choices);
          for(const item of options[key]){const label=el('label',null,'fw-choice'),radio=el('input');radio.type='radio';radio.name=key;radio.value=item.value;radio.checked=values[key]===item.value;radio.onchange=()=>{values[key]=item.value;chosen='';selected='';error.textContent='';};label.append(radio,el('span',item.label));choices.append(label);}
          body.append(group);
        }
        body.append(el('p','해석 조건을 먼저 선택하면 지원 솔버를 추천합니다','fw-note'));
      }else{
        if(!candidates.length){body.append(el('p',fixedSolver?'기존 Template의 솔버와 조건이 맞지 않습니다 · 이전 단계에서 수정하거나 새 Template을 만드세요':summary.message,'fw-note'));}
        else body.append(el('p','조건이 일치하는 솔버 중 하나를 선택하세요','fw-note'));
        for(const item of candidates){
          const label=el('label',null,'fw-choice fw-solver-choice'),radio=el('input'),content=el('div');label.style.marginBottom='10px';radio.type='radio';radio.name='recommended_solver';radio.value=item.solver;radio.checked=chosen===item.solver;radio.onchange=()=>{chosen=item.solver;selected=chosen;next.disabled=false;error.textContent='';};
          content.append(el('strong',item.solver),el('p',item.summary,'fw-note'),el('p',item.reason,'fw-note'),el('p',item.algorithm+' · '+item.outputs.join(' · '),'fw-note'),el('p',item.note,'fw-note'));
          label.append(radio,content);body.append(label);
        }
        body.append(el('p',summary.basis,'fw-note'),el('p','새 Template은 양식만 생성하며 계산에는 실행기 연결이 필요합니다','fw-note'));
        if(replace)body.append(el('p','양식 생성 시 기존 편집 양식을 교체합니다 · 취소하면 기존 양식 유지','fw-note'));
      }
    }
    d.onclose=()=>d.remove();render();document.body.append(d);d.showModal();
  }

  window.CFDFormWizard={open,recommend};
})();
