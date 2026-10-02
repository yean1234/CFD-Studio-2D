/* Shared Config display contract and bounded, machine-readable diagnostics. */
(function(root){
'use strict';
const version=1,types=['string','number','integer','boolean','object','array','null'];
const rows=[
 ['CFG-J001','JSON 문법이 올바르지 않습니다','Invalid JSON syntax','JSON構文が正しくありません','쉼표·따옴표·괄호를 확인하세요','Check commas, quotes and brackets','カンマ・引用符・括弧を確認してください'],
 ['CFG-J002','Config는 JSON 객체여야 합니다','Config must be a JSON object','ConfigはJSONオブジェクトで指定してください','Template에서 출력한 객체 형식을 사용하세요','Use the object exported by the Template','Templateから出力したオブジェクトを使用してください'],
 ['CFG-J003','입력 양식의 정의가 올바르지 않습니다','Invalid input schema','入力書式の定義が正しくありません','version 1과 fields의 key·type·value를 확인하세요','Check version 1 and field key, type and value','version 1とfieldsのkey・type・valueを確認してください'],
 ['CFG-J004','입력값의 자료형이 맞지 않습니다','Value has the wrong type','入力値の型が一致しません','값은 지정된 자료형으로 입력하고 양식 변경은 스키마에 명시하세요','Use the declared type; declare type changes in the schema','指定型で入力し、型変更はスキーマに明示してください'],
 ['CFG-J005','같은 그룹에 중복된 키가 있습니다','Duplicate key in a group','同じグループにキーが重複しています','표시 이름과 별개로 JSON 키를 고유하게 지정하세요','Use unique JSON keys independently of display names','表示名とは別にJSONキーを一意にしてください'],
 ['CFG-J006','사용할 수 없는 예약 키입니다','Reserved key is not allowed','予約キーは使用できません','__proto__·prototype·constructor 대신 다른 키를 사용하세요','Do not use __proto__, prototype or constructor','__proto__・prototype・constructor以外のキーを使用してください'],
 ['CFG-J007','입력 문서의 크기 제한을 초과했습니다','Input exceeds document limits','入力がサイズ制限を超えています','1 MB·중첩 16단계·필드 512개·목록 10000개 제한을 확인하세요','Check 1 MB, 16 levels, 512 fields and 10000 list items','1 MB・16階層・512フィールド・10000項目の制限を確認してください'],
 ['CFG-J008','허용 범위를 벗어난 값입니다','Value is outside the allowed range','値が許容範囲外です','표시된 최소·최대·정수 조건을 확인하세요','Check the displayed bounds and integer requirements','表示された最小・最大・整数条件を確認してください'],
 ['CFG-J009','필수 입력값이 비어 있습니다','Required value is missing','必須入力値が未入力です','표시된 항목을 입력한 뒤 다시 확인하세요','Fill the indicated field and check again','該当項目を入力して再確認してください'],
 ['CFG-J010','정의된 선택지와 값이 맞지 않습니다','Value is not a declared option','値が定義された選択肢と一致しません','선택지를 사용하거나 Template의 enum 정의를 확인하세요','Use an option or review the Template enum','選択肢を使用するかTemplateのenum定義を確認してください'],
 ['CFG-U001','아직 반영하지 않은 편집이 있습니다','An edit is still pending','未反映の編集があります','JSON 저장·이름 입력 완료 또는 취소 후 진행하세요','Apply or cancel the pending JSON or name edit','JSON・名前の編集を反映または取消してください'],
 ['CFG-U002','읽기 전용 입력은 변경할 수 없습니다','Read-only input cannot be changed','読み取り専用の入力は変更できません','이 Config로 새 Case를 만들어 변경하세요','Create a new Case from this Config','このConfigから新しいCaseを作成してください'],
 ['CFG-U003','이 속성에 필요한 물질 상태가 지정되지 않았습니다','Material state is needed for this property','この属性には物質状態の指定が必要です','고체·액체·기체를 선택하거나 공통 속성을 사용하세요','Select solid, liquid or gas, or use a common property','固体・液体・気体を選ぶか共通属性を使用してください'],
 ['CFG-U004','지원하지 않는 입력 표시 방식입니다','Unsupported input widget','未対応の入力表示形式です','기본 자료형 또는 vector3와 올바른 items 정의를 사용하세요','Use a basic type or vector3 with valid items','基本型またはvector3と正しいitems定義を使用してください'],
 ['CFG-G001','공간 형상 정의를 확인해야 합니다','Geometry definition needs correction','空間形状の定義を確認してください','형상 종류·좌표·치수·단위·공간 채움 연결을 확인하세요','Check shape, coordinates, dimensions, units and fill links','形状・座標・寸法・単位・充填接続を確認してください'],
 ['CFG-G002','표의 행 수가 서로 다릅니다','Table columns have different lengths','表の列ごとの行数が一致しません','온도와 물성값을 같은 행 수로 입력하세요','Give temperature and property columns equal row counts','温度と物性値を同じ行数で入力してください'],
 ['APP-N001','서버에 연결할 수 없습니다','Cannot reach the server','サーバーに接続できません','Studio 실행 상태를 확인하고 저장 여부 확인 후 재시도하세요','Check Studio and saved state before retrying','Studioと保存状態を確認してから再試行してください'],
 ['APP-I001','파일을 읽거나 저장하지 못했습니다','File read or save failed','ファイルの読込・保存に失敗しました','폴더 접근 권한·드라이브 연결·남은 공간을 확인하세요','Check permissions, drive connection and free space','アクセス権・ドライブ接続・空き容量を確認してください'],
 ['APP-S001','해당 Config의 실행 연결이 없습니다','No execution adapter for this Config','このConfigの実行接続がありません','연결된 Template을 선택하거나 실행 어댑터 지원 범위를 확인하세요','Select a connected Template or check adapter support','接続済みTemplateまたは実行アダプターの対応範囲を確認してください'],
 ['APP-S002','솔버 실행 파일을 찾을 수 없습니다','Solver executable not found','ソルバー実行ファイルが見つかりません','Template의 설치 확인과 OpenFOAM 환경을 확인하세요','Check solver installation and the OpenFOAM environment','ソルバーのインストール確認とOpenFOAM環境を確認してください'],
 ['APP-X001','처리 중 분류되지 않은 오류가 발생했습니다','Unclassified operation error','未分類の処理エラーが発生しました','코드와 상세 내용을 보관하고 같은 작업을 자동 반복하지 마세요','Keep the code and details; do not retry automatically','コードと詳細を保存し、自動で再実行しないでください']
];
const catalog=Object.fromEntries(rows.map(([code,ko,en,ja,fixKo,fixEn,fixJa])=>[code,{code,message:{ko,en,ja},action:{ko:fixKo,en:fixEn,ja:fixJa},retry:'review'}]));
function issue(code,detail='',path=[]){const error=new Error((catalog[code]?.message.en||code)+(detail?' · '+String(detail):''));error.code=code;error.path=path;return error;}
const patterns=[
 ['CFG-J001',/올바른 JSON 형식/],
 ['CFG-J006',/Reserved Config|예약 키/i],['CFG-J005',/Duplicate Config|중복.*키/i],
 ['CFG-J007',/1 MB|16 levels|512 fields|too large|크기 제한/i],['CFG-J002',/must be a JSON object|설정 JSON 객체/],
 ['CFG-J003',/schema version|Invalid Config group|Unsupported Config Type|Config Key|Config Unit|nullable flag/i],
 ['CFG-J004',/does not match Type|입력 형식|배열 형식|JSON values|유한한 숫자|finite|숫자를 입력|정수를 입력/],
 ['CFG-G002',/행 수/],['CFG-U001',/JSON 저장 또는 취소|속성 이름 입력|채움 적용 후/],['CFG-U002',/읽기 전용|read.only/i],
 ['CFG-G001',/형상|공간 채움|최소·최대 좌표|Scale/],['CFG-J008',/범위|이상으로|이하로|양수|정수여야|range/i],
 ['CFG-J009',/입력하세요|Value is missing|required.*missing/i],['APP-N001',/Failed to fetch|NetworkError|fetch failed/i],
 ['APP-S001',/실행.*연결|adapter/i],['APP-S002',/실행 파일.*없|solver.*not found/i],
 ['APP-I001',/permission|access denied|ENOSPC|ENOENT|디스크 공간|파일.*없|저장.*실패/i]
];
function normalize(error,language='ko'){
 const detail=String(error?.message??error??'').slice(0,700),embedded=detail.match(/\[(CFG-[JUG]\d{3}|APP-[NISX]\d{3})\]/)?.[1];
 const code=catalog[error?.code]?error.code:catalog[embedded]?embedded:error instanceof SyntaxError?'CFG-J001':patterns.find(([,p])=>p.test(detail))?.[0]||'APP-X001';
 const lang=['ko','en','ja'].includes(language)?language:'en',entry=catalog[code];
 return {code,message:entry.message[lang],action:entry.action[lang],path:Array.isArray(error?.path)?error.path:[],detail,retry:entry.retry};
}
function display(node,error){
 if(!node)return;const lang=root.CFDI18n?.language||'ko';
 if(!error){node.textContent='';delete node.dataset.errorInfo;delete node.dataset.errorCode;return;}
 const info=normalize(error,lang);node.dataset.errorCode=info.code;node.dataset.errorInfo=JSON.stringify(info);node.setAttribute('translate','no');
 node.textContent='['+info.code+'] '+info.message+'\n'+(info.path.length?info.path.join('.')+' · ':'')+info.action+(info.detail&&info.detail!==info.message?'\n'+info.detail:'');
}
function validateDefinitions(schema){
 let count=0;const visit=(fields,path=[],depth=0)=>{
  if(depth>16)throw issue('CFG-J007','16 levels',path);
  if(!Array.isArray(fields))throw issue('CFG-J003','fields must be an array',path);
  const keys=new Set();
  for(const f of fields){
   if(++count>512)throw issue('CFG-J007','512 fields',path);
   if(!f||typeof f!=='object'||typeof f.key!=='string'||!types.includes(f.type))throw issue('CFG-J003','Field key/type',path);
   const p=[...path,f.key];if(keys.has(f.key))throw issue('CFG-J005',f.key,p);keys.add(f.key);
   if(['__proto__','prototype','constructor'].includes(f.key))throw issue('CFG-J006',f.key,p);
   if(f.widget!==undefined&&f.widget!=='vector3')throw issue('CFG-U004',String(f.widget),p);
   if(f.widget==='vector3'&&(f.type!=='array'||!Array.isArray(f.value)||f.value.length!==3||f.value.some(v=>v!==null&&(typeof v!=='number'||!Number.isFinite(v)))))throw issue('CFG-U004','vector3 requires three numeric or null values',p);
   for(const k of ['minimum','maximum','step'])if(f[k]!==undefined&&(!Number.isFinite(f[k])||(k==='step'&&f[k]<=0)))throw issue('CFG-J003',k,p);
   if(f.minimum!==undefined&&f.maximum!==undefined&&f.minimum>f.maximum)throw issue('CFG-J003','minimum > maximum',p);
   for(const k of ['enum','item_enum'])if(f[k]!==undefined&&(!Array.isArray(f[k])||f[k].some(v=>(v!==null&&!['string','number','boolean'].includes(typeof v))||(typeof v==='number'&&!Number.isFinite(v)))))throw issue('CFG-J003',k,p);
   if(f.type==='object')visit(f.fields,p,depth+1);
   if(f.items!==undefined){if(f.type!=='array'||!f.items||typeof f.items!=='object'||!types.includes(f.items.type))throw issue('CFG-J003','items',p);visit([{...f.items,key:'items',...(f.items.type==='array'?{value:blankItem(f.items)}:{})}],p,depth+1);}
  }
 };
 if(!schema||schema.version!==1)throw issue('CFG-J003','version must be 1');visit(schema.fields);
 return schema;
}
function validateValues(config,schema,{required=false}={}){
 validateDefinitions(schema);
 function value(v,f,path){
  if(v===undefined){if(required&&f.required)throw issue('CFG-J009','missing',path);return;}
  if(v===null){if(required&&f.required)throw issue('CFG-J009','null',path);if(f.nullable||f.type==='null')return;throw issue('CFG-J004','null',path);}
  const type=Array.isArray(v)?'array':typeof v;
  if(type!==f.type&&!(f.type==='integer'&&Number.isSafeInteger(v)))throw issue('CFG-J004',f.type,path);
  if(f.type==='integer'&&!Number.isSafeInteger(v)||typeof v==='number'&&!Number.isFinite(v))throw issue('CFG-J004','finite number / integer',path);
  if(typeof v==='number'&&(f.minimum!==undefined&&v<f.minimum||f.maximum!==undefined&&v>f.maximum))throw issue('CFG-J008',`${f.minimum??'−∞'} … ${f.maximum??'∞'}`,path);
  if(f.enum?.length&&!f.enum.some(x=>Object.is(x,v))&&v!=='')throw issue('CFG-J010',String(v),path);
  if(f.type==='object')for(const child of f.fields)value(v[child.key],child,[...path,child.key]);
  if(f.type==='array'){
   if(v.length>10000)throw issue('CFG-J007','10000 items',path);
   if(f.widget==='vector3'&&(v.length!==3||v.some(x=>x!==null&&(typeof x!=='number'||!Number.isFinite(x)))))throw issue('CFG-U004','vector3',path);
   if(f.item_enum&&v.some(x=>!f.item_enum.some(y=>Object.is(x,y))))throw issue('CFG-J010','item_enum',path);
   if(f.items)v.forEach((x,i)=>value(x,f.items,[...path,i]));
  }
  if(required&&f.required&&v==='')throw issue('CFG-J009','empty',path);
 }
 if(!config||typeof config!=='object'||Array.isArray(config))throw issue('CFG-J002');
 for(const f of schema.fields)value(config[f.key],f,[f.key]);return config;
}
function blankItem(def){if(def?.type==='object')return Object.fromEntries((def.fields||[]).map(f=>[f.key,blankItem(f)]));if(def?.widget==='vector3')return [null,null,null];if(def?.type==='array')return [];if(def?.type==='string')return '';return null;}
const rules={version,format:'cfd-studio-config',schema_version:1,limits:{bytes:1000000,depth:16,fields:512,array_items:10000},order:'Template fields order, then additional Config keys',widgets:{string:'text',number:'number',integer:'integer',boolean:'choice',object:'group',array:'rows',null:'explicit type selection',enum:'single choice',item_enum:'multiple choices',vector3:'XYZ inputs'},extension:'Preserve unknown Config keys; declare new fields and array items in config_schema; never assume solver support',workflow:['Generate Template','Export its schema','Fill values and declare extensions','Apply JSON draft','Review visible Config and 3D with user','Save after confirmation','Start only with execution authorization']};
const api={version,catalog,rules,issue,normalize,display,validateDefinitions,validateValues,blankItem};if(typeof module!=='undefined')module.exports=api;root.CFDConfigContract=api;
})(globalThis);
