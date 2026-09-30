const test=require('node:test'),assert=require('node:assert/strict');
const ui=require('../cfd_studio/internal/i18n.js');
test('all registered messages have English and Japanese text',()=>{
 assert.ok(Object.keys(ui.messages).length>400);
 for(const [key,values] of Object.entries(ui.messages)){assert.equal(values.length,2);for(const v of values)assert.ok(typeof v==='string'&&v.trim(),key);}
});
test('source strings and unknown solver identifiers are preserved',()=>{
 for(const s of ['저장','icoFoam','transportProperties','U','m/s','ClO₂','input.custom']){assert.equal(ui.translate(s,'ko'),s);}
 for(const lang of ['en','ja'])for(const s of ['icoFoam','input.custom','m/s'])assert.equal(ui.translate(s,lang),s);
});
test('labels, units, whitespace and dynamic counts translate',()=>{
 assert.equal(ui.translate('  저장  ','en'),'  Save  ');
 assert.equal(ui.translate('Config 3개 변경','ja'),'Config変更 3件');
 assert.equal(ui.translate('온도 (°C)','en'),'Temperature (°C)');
 assert.equal(ui.translate('7 프레임 · 초기 제외','en'),'7 frames · Initial excluded');
 assert.equal(ui.translate('1. 유체','ja'),'1. 流体');
});
test('separator-only strings cannot recurse',()=>{
 for(const s of ['',' ', ' · ','\n'])assert.equal(ui.translate(s,'en'),s);
 assert.equal(ui.translate('유속 · 온도','en'),'Velocity · Temperature');
});
test('settings search recognizes current translated labels without modifying Config',()=>{
 const editor=require('../cfd_studio/internal/config_editor.js');const c={tank:{},dielectric_fluid:{},run:{end_time_s:2,viz_interval_s:.1}};const before=JSON.stringify(c);
 const old=globalThis.CFDI18n;
 try{for(const lang of ['en','ja']){globalThis.CFDI18n={translate:s=>ui.translate(s,lang)};assert.ok(editor.searchFields(c,ui.translate('결과 프레임 저장 간격',lang)).some(f=>f.path.join('.')==='run.viz_interval_s'));}}finally{globalThis.CFDI18n=old;}
 assert.equal(JSON.stringify(c),before);
});

test('Config toolbar, termination and geometry notices are localized',()=>{
 const messages=['전체 JSON','JSON 가져오기','JSON 내보내기','목표값·비교 목적','솔버 시간간격 · 결과 저장 간격 · Viewer 재생 속도는 개별 항목','선택한 출력 항목이 모두 저장된 시점만 1프레임으로 계산','높이','열원','Config 저장','프리셋을 불러오는 중입니다','상분율·계산 격자는 표시하지 않음','공간 JSON 분류를 유지하세요: mesh','상분율·계산 격자는 표시하지 않음 · probes_mm: 측정 지점은 미리보기에 포함되지 않음'];
 for(const locale of ['en','ja'])for(const message of messages)assert.doesNotMatch(ui.translate(message,locale),/[가-힣]/,locale+': '+message);
});
test('dynamic Config labels and validation messages translate without changing identifiers',()=>{
 assert.equal(ui.translate('geometry.regions.0.max 입력 형식을 확인하세요','ja'),'geometry.regions.0.max: 入力形式を確認してください');
 assert.equal(ui.translate('tank: 치수 미입력','ja'),'tank: 寸法未入力');
 assert.equal(ui.translate('유체 2','ja'),'流体 2');
 assert.equal(ui.translate('상분율 3','en'),'Phase fraction 3');
 assert.equal(ui.translate('X 최소','ja'),'X 最小');
 assert.equal(ui.translate('geometry.region: 지원하지 않는 shape cone','en'),'geometry.region: unsupported shape cone');
});


test('Studio notices and delayed hardware status translate',()=>{
 const messages=['비교 기준이 저장되지 않은 기존 결과입니다','비교 기준이 저장되지 않은 기존 결과입니다.','코어 자동 감지','기준: Case 최초 저장 설정\n\n기준 설정과 차이 없음','NVIDIA HPC SDK nvc++가 없습니다','OpenFOAM이 Nvidia-gpu 아키텍처로 빌드되지 않았습니다','공식 GPU 테스트와 CFD Studio 3상 smoke 검증이 완료되지 않았습니다','읽음 12 / 30 값','X = 10 회 · 저장 시점','Y = — (이 X의 저장값 없음)'];
 for(const locale of ['en','ja'])for(const message of messages)assert.doesNotMatch(ui.translate(message,locale),/[가-힣]/,locale+': '+message);
 assert.equal(ui.translate('내 프로젝트 시각화 준비','ja'),'내 프로젝트 可視化準備');
 assert.equal(ui.translate('내 템플릿 수정','en'),'Edit 내 템플릿');
 assert.equal(ui.translate('0 ~ 2 범위로 입력하세요.','en'),'Enter a value between 0 and 2');
});
