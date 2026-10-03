/* Transport progress separately from browser commands and CFD execution */
(function(root){
'use strict';
const labels = {
  review:'자료 확인', draft:'초안 작성', debug:'코드 수정', test:'검사 중', ui:'화면 조작',
  waiting:'사용자 확인 대기', blocked:'진행 불가', completed:'작업 완료', failed:'작업 실패',
  disconnected:'에이전트 연결 끊김', paused:'에이전트 일시정지'
};
function presentation(state, available=true){
  const task=state?.task;
  return {
    shown:!!task || !!state?.paused,
    paused:!!state?.paused,
    title:!available && task ? '작업 상태 연결 끊김' : state?.paused ? labels.paused : labels[task?.status] || '',
    mode:task?.mode==='development' ? '개발 작업' : 'Studio 작업',
    detail:task?.detail || '',
    settled:!available || !!state?.paused || ['completed','failed','blocked','waiting','disconnected'].includes(task?.status)
  };
}
function client({fetch,notify=()=>{},tab,visible=()=>true}){
  let state=null,available=false,pending=null;
  async function request(body){
    const response=await fetch('/api/agent/activity',{
      cache:'no-store',signal:AbortSignal.timeout(3000),
      ...(body ? {method:'POST',headers:{'Content-Type':'application/json','X-CFD-Activity':'1'},body:JSON.stringify(body)} : {})
    });
    const value=await response.json();
    const next=response.ok ? value : value.state;
    if(next && typeof next.revision==='number' &&
       (!state || next.server!==state.server || next.revision>=state.revision))state=next;
    available=true;
    notify();
    if(!response.ok)throw Error(value.error || 'ACTIVITY_UNAVAILABLE');
    return value;
  }
  async function refresh(){
    if(pending)return pending;
    pending=(async()=>{
      try{
        const value=await request();
        // A hidden tab must not claim the user can see the progress banner
        if(visible() && (value.task || value.paused))await request({action:'seen',tab,revision:value.revision});
      }catch(error){
        if(error.message!=='ACTIVITY_STALE'){available=false;notify();}
      }finally{pending=null;}
      return snapshot();
    })();
    return pending;
  }
  function snapshot(){return {state,available,...presentation(state,available)};}
  async function pause(value){
    try{await request({action:value ? 'pause' : 'resume'});}
    catch(error){available=false;notify();throw error;}
    return snapshot();
  }
  return {refresh,pause,snapshot};
}
if(typeof module!=='undefined')module.exports={client,presentation,labels};
if(!root.document)return;
const bridge=client({fetch:root.fetch.bind(root),tab:root.crypto.randomUUID(),
  visible:()=>root.document.visibilityState==='visible' && !!root.document.getElementById('agentProgressDetail'),
  notify:()=>root.dispatchEvent(new CustomEvent('cfd-agent-progress'))});
root.CFDAgentActivity=Object.freeze({...bridge,labels});
setInterval(()=>bridge.refresh(),2000);
root.document.addEventListener('visibilitychange',()=>bridge.refresh());
})(globalThis);
