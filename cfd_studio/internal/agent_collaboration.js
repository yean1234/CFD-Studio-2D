/* Compare Config drafts and coordinate agent ownership within one browser page */
(function(root){
'use strict';
const copy=x=>structuredClone(x);
// Count all changes; retain only the requested number of display rows
function diff(before,after,{limit=200}={}){
 if(!Number.isInteger(limit)||limit<1||limit>2000)throw Error('INVALID_LIMIT');
 const rows=[];let total=0;
 const visit=(a,b,path)=>{
  if(Object.is(a,b))return;
  const object=x=>x!==null&&typeof x==='object';
  if(object(a)&&object(b)&&Array.isArray(a)===Array.isArray(b)){
   for(const key of new Set([...Object.keys(a),...Object.keys(b)])){
    visit(a[key],b[key],[...path,Array.isArray(b)?Number(key):key]);
   }return;
  }
  total++;if(rows.length<limit)rows.push({path,kind:a===undefined?'added':b===undefined?'removed':'changed',...(a===undefined?{}:{before:copy(a)}),...(b===undefined?{}:{after:copy(b)})});
 };
 visit(before,after,[]);return {total,rows,truncated:total>rows.length};
}
// Lease times use milliseconds; ownership is advisory and resets on page reload
function coordinator({now=Date.now,uuid=()=>root.crypto.randomUUID(),ttl=120000}={}){
 let owner=null,note=null,engaged=false;
 const expire=()=>{if(owner&&now()>=owner.expires){owner=null;}};
 const state=()=>{expire();return {required:engaged,owner:owner?{name:owner.name,task:owner.task,expires:owner.expires}:null,handoff:note?copy(note):null};};
 const check=token=>{expire();if(token&&!owner)throw Error('OWNER_EXPIRED');if(engaged&&(!owner||owner.token!==token))throw Error(owner?'OWNER_REQUIRED':'OWNER_EXPIRED');};
 return {state,check,
  claim({name,task='',token}={}){if(typeof name!=='string'||!name.trim()||name.length>80||typeof task!=='string'||task.length>500)throw Error('INVALID_OWNER');expire();if(owner&&owner.token!==token)throw Error('OWNER_BUSY');engaged=true;owner={name:name.trim(),task,token:owner?.token||uuid(),expires:now()+ttl};return {...state(),token:owner.token};},
  renew(token){check(token);if(owner)owner.expires=now()+ttl;return state();},
  release(token,summary='',context={}){check(token);if(typeof summary!=='string'||summary.length>2000)throw Error('INVALID_HANDOFF');note={summary,context:copy(context),time:now(),from:owner?.name||null};owner=null;return state();},
  reset(){owner=null;engaged=false;return state();}
 };
}
const prompts={
 ko:{observe:'필요한 상태만 조회: observe()의 cursor를 보관하고 waitForChange({after:cursor,timeoutMs:30000})로 변경을 기다리세요. 입력 대상은 inspect({query,limit:20})로 찾으세요. run의 response:"compact"를 사용하고 오류는 errorInfo(code)로 확인하세요. 변경이 없으면 전체 Config나 화면을 반복해서 읽지 마세요.',review:'Config 변경 검토: 생성한 Template의 출력 JSON을 기준으로 초안을 작성하세요. review.open을 호출해 사용자가 변경 전후 값과 3D를 확인하도록 안내하세요. review.status()의 확인은 해당 초안에만 적용되며 저장 또는 계산 허가가 아닙니다. 값이 바뀌면 다시 검토하세요. 최종 저장과 계산 시작은 사용자가 요청한 범위에서 진행하세요.',handoff:'조작 담당·인계: claim({name,task})로 담당을 확보하고 반환된 token을 run의 owner로 전달하세요. observe()의 context를 expectedContext로 함께 전달하세요. 다른 담당이 있으면 읽기만 하고 기다리세요. 끝나면 release({owner,summary})에 완료·미완료·다음 단계를 짧게 남기세요. 다음 담당은 handoff()와 실제 화면을 함께 확인하세요. PAUSED 상태를 우회하지 마세요.'},
 en:{observe:'Read selectively: keep the cursor from observe() and await waitForChange({after:cursor,timeoutMs:30000}). Find controls with inspect({query,limit:20}). Use run response:"compact" and errorInfo(code). Do not repeatedly load full Config or screens when nothing changed.',review:'Review Config: start from the generated Template JSON. Call review.open and ask the user to check changed values and 3D. review.status() records review of that draft only; it is not permission to save or calculate. Review again after edits. Save and start calculations only within the requested scope.',handoff:'Coordinate control: claim({name,task}) and pass its token as run owner. Pass observe().context as expectedContext. If another operator holds control, remain read-only and wait. release({owner,summary}) with completed work, remaining work and the next step. The next operator reads handoff() and verifies the live screen. Never bypass PAUSED.'},
 ja:{observe:'必要な状態だけ確認：observe()のcursorを保持し、waitForChange({after:cursor,timeoutMs:30000})で変更を待機。inspect({query,limit:20})で操作対象を検索。runはresponse:"compact"を指定し、エラーはerrorInfo(code)で確認。変化がなければConfig全体や画面を繰り返し取得しないでください。',review:'Config変更の確認：生成済みTemplate JSONから下書きを作成。review.openで変更前後の値と3Dをユーザーに確認してもらってください。review.status()はその下書きの確認記録であり、保存や計算の許可ではありません。変更後は再確認し、依頼された範囲で保存・計算を行ってください。',handoff:'操作担当・引継ぎ：claim({name,task})で取得したtokenをrunのownerに渡し、observe().contextをexpectedContextに指定。他の担当がいる間は読み取りのみで待機。release({owner,summary})に完了・未完了・次の手順を記録。次の担当はhandoff()と実際の画面を照合し、PAUSEDを回避しないでください。'}
};
const errors={
 OWNER_BUSY:{ko:'다른 에이전트가 조작 중입니다 · 인계를 기다리세요',en:'Another agent is operating · Wait for handoff',ja:'他のエージェントが操作中です · 引継ぎを待ってください'},
 OWNER_REQUIRED:{ko:'현재 조작 담당의 토큰이 필요합니다 · claim 응답의 token을 전달하세요',en:'The current operator token is required · Pass the claim token',ja:'現在の担当トークンが必要です · claimのtokenを指定してください'},
 OWNER_EXPIRED:{ko:'조작 담당이 만료되었거나 해제되었습니다 · 화면을 확인하고 다시 확보하세요',en:'Control expired or was released · Inspect the screen and claim again',ja:'操作権が期限切れまたは解放済みです · 画面を確認して再取得してください'},
 CONTEXT_CHANGED:{ko:'프로젝트·Case·편집 화면이 변경되었습니다 · 다시 조회하세요',en:'Project, Case or editor changed · Observe again',ja:'プロジェクト・Case・編集画面が変更されました · 再取得してください'},
 USER_ACTION_REQUIRED:{ko:'사용자가 직접 확인하는 버튼입니다 · 확인을 기다리세요',en:'This confirmation is for the user · Wait for review',ja:'ユーザー確認用のボタンです · 確認を待ってください'},
 INVALID_OWNER:{ko:'담당 이름과 작업 내용을 확인하세요',en:'Check operator name and task',ja:'担当名と作業内容を確認してください'},
 INVALID_HANDOFF:{ko:'인계 내용은 2000자 이내로 입력하세요',en:'Keep the handoff within 2000 characters',ja:'引継ぎは2000文字以内で入力してください'},
 INVALID_QUERY:{ko:'검색 범위와 개수를 확인하세요 · 한 번에 최대 100개',en:'Check search range and count · Up to 100 controls',ja:'検索範囲と件数を確認してください · 最大100件'},
 INVALID_WAIT:{ko:'cursor와 대기 시간을 확인하세요 · 최대 60초',en:'Check cursor and timeout · Up to 60 seconds',ja:'cursorと待機時間を確認してください · 最大60秒'},
 TOO_MANY_WAITERS:{ko:'이미 대기 중인 요청을 확인하세요 · 최대 4개',en:'Check pending waits · Up to four concurrent waits',ja:'待機中の要求を確認してください · 同時に最大4件'}
};
const api={diff,coordinator,prompts,errors};if(typeof module!=='undefined')module.exports=api;root.CFDAgentCollaboration=api;
})(globalThis);
