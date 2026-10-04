# AI 에이전트 사용법

- CFD Studio V1.0 · 에이전트 인터페이스 v1.4

[한국어](CFD-STUDIO-AGENT-GUIDE.md) · [English](CFD-STUDIO-AGENT-GUIDE.en.md) · [日本語](CFD-STUDIO-AGENT-GUIDE.ja.md)

## 작업 진행 표시

- 화면 명령 이외의 자료 확인·코드 수정·검사도 상태 전송이 필요 · 파일 수정만으로 자동 표시되지 않음
- 실행 위치: 저장소 루트 · Windows 내장 Python 사용 · 세션 파일은 Git에서 제외한 새 `output/` 경로
- 작업 시작 전 `start`, 각 단계 전에 `update`, 종료 시 `finish` · 장시간 작업은 60초 이내 간격으로 상태 확인·갱신
- `--mode development`: 개발 작업 · 실제 CFD 조작은 `--mode operation`
- `--stage`: `review`, `draft`, `debug`, `test`, `ui`, `waiting`, `blocked` · 종료는 `completed` 또는 `failed`
- `--detail`: 사용자가 이해할 수 있는 짧은 설명 · Config 전체·인증 정보 입력 금지

```bat
cfd_studio\Setup\Python312\python.exe cfd_studio\internal\agent_progress.py start --session-file output\agent-session.json --mode development --stage review --detail "입력 및 실행 경로 확인" --wait-visible
cfd_studio\Setup\Python312\python.exe cfd_studio\internal\agent_progress.py update --session-file output\agent-session.json --stage test --detail "관련 검사 실행" --wait-visible
cfd_studio\Setup\Python312\python.exe cfd_studio\internal\agent_progress.py status
cfd_studio\Setup\Python312\python.exe cfd_studio\internal\agent_progress.py finish --session-file output\agent-session.json --stage completed --detail "검사 완료 · CFD 미실행"
```

- `output` 폴더가 없으면 먼저 생성 · 기존 세션 파일을 덮어쓰지 않음
- 종료 코드 `3` 또는 `PAUSED`: 다음 파일 수정·명령을 중단하고 상태만 조회 · 사용자의 새 지시 대기
- 종료 코드 `2`: 오류 확인 · 코드 `4`: 화면 표시 수신 미확인 · 성공으로 보고하지 않음
- `displayed: true`: 보이는 Studio 탭이 해당 상태를 렌더링했다는 수신 확인 · 사용자 검토·특정 탭 연결·계산 승인은 아님
- 120초간 갱신이 없으면 **에이전트 연결 끊김** · 서버 통신 실패는 **작업 상태 연결 끊김** · 완료·대기·차단은 점멸하지 않음
- 상태·최근 20건·일시정지는 서버 메모리에 보관 · 탭 새로고침 후 재조회 · 서버 재시작 시 초기화
- 일시정지는 외부 LLM·이미 시작한 명령·솔버를 강제로 중단하지 않음 · 에이전트가 짧은 작업 단위 사이에서 신호 확인
- 이 통로는 상태 전용 · Config 입력·저장·계산 시작은 계속 현재 화면의 공개 명령 사용
- 업데이트 적용은 실행 중 서버와 탭에 자동 주입되지 않음 · 미저장 입력과 계산 상태를 확인한 뒤 Studio 재실행·페이지 새로고침
- [상태 오류 코드](AGENT-PROGRESS.md)

## 연결 확인과 오류 복구

1. 화면 조작 도구가 시작되는지 확인
2. Studio 서버와 에이전트 스크립트 응답 확인
3. 사용자가 보는 탭에서 `CFDAgent.describe()`와 `CFDAgent.observe()` 조회
4. 반환된 session·프로젝트·Case를 실제 화면과 대조한 뒤 조작 시작

| 확인 항목 | 확인 수단 | 증명하지 않는 것 |
| --- | --- | --- |
| 도구 시작 | 조작 도구 호출 성공 | Studio 연결 |
| 서버·스크립트 | `agent_diagnostics.py` | 현재 탭 접근·사용자 검토 |
| 현재 탭 | 해당 탭의 describe·observe 및 화면 대조 | 저장·계산 승인 |
| 초안 반영 | JSON 재조회·알림·3D 확인 | Case 저장·CFD 완료 |

- 진단의 `stages`: automation_host / studio_http / agent_scripts / current_tab
- HTTP 정상이어도 `current_tab: not_checked` · 종료 코드 0도 탭 연결 성공을 뜻하지 않음
- 설정 포트는 `CFD_STUDIO_PORT` 환경변수, 없으면 `studio_config.json` 기준 · Windows 실행 환경에서 진단
- `APP-A001`: Studio 접근 전 외부 조작 도구의 작업 경로 오류 · 도구별 제한된 복구 절차 후 같은 실패의 반복 호출 중단
- 로컬 작업 환경 변경은 복구 후보 · 확인 없이 해결된다고 단정하지 않음
- `APP-N001`: 서버 접근 실패 · 꺼진 서버의 시작과 실행 중 서버의 재시작을 구분
- 정상 서버·사용자 브라우저·실행 중 솔버를 외부 도구 오류 해결 목적으로 종료하지 않음
- 질문 창이 표시되지 않으면 일반 대화에 필요한 질문을 다시 작성 · 무응답을 확인·승인으로 해석하지 않음

### 조작과 개발의 구분

- 일반 사용: 현재 탭의 공개 CFDAgent 명령과 화면 조작 사용
- 사용자가 디버깅을 요청한 경우: 해당 조작 단계 중지 → 오류·영향 범위 기록 → 관련 코드 수정·검사 → 재연결·현재 상태 재조회
- 개발 중에도 기존 프로젝트·미저장 입력·계산·Raw·결과 보존 · 소스 테스트를 실제 CFD 실행으로 보고하지 않음
- 서버 상태만 바뀌었을 때도 미저장 입력을 확인하지 않고 브라우저를 새로고침하지 않음
- 복구 범위 밖의 오류는 남은 원인과 필요한 조치를 명시 · 무관한 기능을 계속 수정하지 않음

### 초안의 출처와 상태

- 자료를 `현재 편집기 내보내기`, `서버 Template 사본`, `저장소 참고 파일`로 구분
- 별도 파일로 작성한 초안은 화면 반영·사용자 검토·Case 저장으로 취급하지 않음
- 연결 복구 후 실제 편집기 JSON을 다시 읽고 사용자 변경과 대조한 뒤 필요한 값만 반영
- 문헌값·단위 환산·Template 기본값·제안 가정·미공개값을 구분 · 기본값을 문헌값으로 승격하지 않음
- 설치된 솔버, 실행 어댑터, 형상 지원, 결과 읽기, 수송 연결을 각각 확인
- 필요한 모델이 연결되지 않으면 해당 계산 단계 보류 · 다른 모듈 결과나 등가 형상으로 조용히 대체하지 않음
- 저장과 계산은 별도 단계 · 사용자가 요구한 화면 검토는 먼저 완료 · 동일 대상·입력·범위에 대한 명시적 승인은 반복 질문하지 않음


## 협업 기능 v1.3

- 목적: OpenFOAM CFD를 AI 에이전트로 조작할 때 반복 입력·조회 부담을 줄이고 사용자가 같은 화면에서 확인하도록 지원
- **필요한 상태만 조회**: `observe({after})`, `inspect({query,limit})`, `waitForChange({after,timeoutMs})` 사용 · 변하지 않은 전체 Config 반복 조회 금지
- **Config 변경 검토**: `review.open` 호출 → 사용자에게 변경 전후와 3D 확인 안내 → `review.status()` 확인 · 검토는 저장·계산 승인이 아님
- **조작 담당·인계**: `claim({name,task})` → 반환된 token을 run의 `owner`로 전달 → `release({owner,summary})` → 다음 담당이 `handoff()`와 실제 화면 확인
- `run(command,args,{owner,expectedContext:CFDAgent.observe().context,response:"compact"})`: 기존 명령을 간결한 응답으로 사용
- 담당 유효 시간 120초 · 성공한 명령 또는 `renew({owner})`로 갱신 · 다른 담당이 있으면 읽기만 수행
- 사용자가 입력이나 선택 대상을 바꾸면 오래된 context의 작업을 재조회 · 변경된 내용을 덮어쓰지 않음
- 담당·인계·검토는 현재 페이지의 메모리 · 재시작 후 재확인 · 서버·다른 탭까지 잠그지 않음
- 인계는 참고 메모이며 권한 부여가 아님 · 이미 명확히 승인된 동일 작업을 반복 확인하지 않음
- [기능·명령·협업 오류·참고 문헌](AGENT-COLLABORATION.md)

## Template 기반 Config 작성

1. 사용할 기존 Template 선택 · 적합한 양식이 없을 때만 설문과 솔버 선택으로 생성
2. **양식 편집 → JSON 내보내기** 또는 `CFDAgent.configDocument()`로 생성된 JSON 양식 확보
3. 출력된 양식을 기준으로 Config 작성 · 새 문서를 임의로 만들어 대체하지 않음
4. 확장할 항목은 `config_schema`에 자료형·표시 이름·단위·`items` 등을 명시하고 `config`에 값 입력
5. JSON 초안 적용 후 사용자가 입력 목록·3D 형상·단위·미확정값을 확인하도록 안내
6. 확인 후 최종 저장 · 계산 시작은 실행 대상·종료 조건·대기열 확인을 거친 별도 단계

- Config 내보내기 문서: `format: "cfd-studio-config"`, `version: 1`, `config`, `config_schema`
- Template 내보내기는 `version`·`fields` 형식 · 공간 문서는 공간 JSON 창에서 조회한 형식 유지
- `items`로 빈 목록의 행 양식 정의 · `widget: "vector3"`로 XYZ 입력 지정
- 기존 키·단위·식별자·관계·관련 없는 값 보존 · 사용자 추가 키는 명시적으로 확장
- 입력 UI에 표시되는 것과 솔버가 계산에 사용하는 것은 별개 · 실행 어댑터 지원 확인
- [JSON 규칙](CONFIG-JSON.md) · [오류 코드](ERROR-CODES.md) · [다국어 오류 사전](config-error-codes.json)

### 실행 전 확인

- 진행 CLI로 현재 작업을 이미 활성화했다면 `CFDAgent.activate()`를 중복 호출하지 않음 · 다른 담당의 세션은 사용하지 않음
- `CFDAgent.configDocument()`의 반환값은 `{document: ...}` 또는 오류 객체 · `document` 존재를 확인한 뒤 사용
- Template의 `document.fields`는 양식, 프로젝트·Case의 `document.config`는 입력값 · 두 문서를 서로 대체하지 않음
- 기존 프리셋을 선택하지 않아도 Template에 남은 값이 있을 수 있음 · 문헌값·기본값·미확정값을 대조
- 공간 JSON 조회 성공과 3D 형상 생성 성공은 별도 · 미리보기 경고·경계·다공성 영역 확인
- 솔버 설치 확인만으로 형상 생성·격자 가져오기·수송·실행 어댑터 연결을 판정하지 않음
- 미지원 형상 오류가 나오면 그 단계에서 계산 보류 · 초안과 정확한 오류 코드를 보존하고 임의의 등가 모델로 바꾸지 않음
- 현재 편집기 초안, 프로젝트 저장, Case 저장, 격자 검사, 계산 완료를 각각 기록

### 간결한 상태 확인

| 조회 | 용도 |
| --- | --- |
| `CFDAgent.status()` | 화면·일시정지·오류 확인 · 전체 입력·로그 생략 |
| `CFDAgent.configRules()` | JSON 표시 규칙 1회 확인 |
| `CFDAgent.configDocument()` | 열린 편집기의 내보내기 문서 조회 · 반영 전 편집이 있으면 오류 반환 |
| `CFDAgent.errorInfo("CFG-J004")` | 해당 코드의 원인·해결 방법만 조회 |
| `CFDAgent.state()` | 화면이 바뀌었거나 조작할 입력을 찾아야 할 때 상세 조회 |

- 인터페이스 v1.3의 추가 읽기 기능 · 기존 명령과 호환
- 오류의 `code`·`path`·`action`으로 해당 입력만 수정 · 전체 소스 분석이나 같은 명령 반복부터 시작하지 않음
- `APP-X001`: 분류되지 않은 오류 · 상세 내용을 보존하고 원인 확인
- 일시정지 시 기존 대기 절차 유지 · 새 사용자 지시 없이 재활성화하지 않음

## 결과 확인

- Viewer에서는 Case 하나를 선택한 뒤 **3D Virtual / Data Sheet** 전환
- Data Sheet 왼쪽: 전체 평균 또는 특정 좌표의 시계열 · 최대 3개 물리량
- 오른쪽: 저장 프레임의 선상 프로파일 · 시작점·끝점·표본 수 지정
- 선상 값은 최근접 저장 셀 기준 · 공간·시간 보간 결과로 설명하지 않음
- JSON은 전체 Config·전체 공간 정의 또는 주요 분류 단위로 입력 · 개별 속성마다 JSON 버튼을 찾지 않음
- 새 Template 생성만으로 실행기가 추가되지는 않음 · 실제 실행 연결 상태 확인


## 시작 순서

1. CFD Studio를 실행하고 사용할 프로젝트 선택
2. 외부 에이전트에게 이 지침서와 작업 내용 전달
3. 사용하는 에이전트에 프롬프트와 작업 요청 전달 · 사용자가 보고 있는 Studio 탭에 연결
4. 상단 **에이전트 조작 중** 표시와 화면에서 진행 상황 확인
5. **에이전트 조작 중단**을 누르면 관련 UI 숨김과 중단 신호 전송 · 계속할 작업은 에이전트 대화에서 새로 지시

- 프롬프트 전달만으로 브라우저 연결이 완료되지는 않음 · 연결 방법은 사용하는 에이전트 도구에 따름
- 명령 이름과 JSON 키는 화면 언어와 관계없이 동일

## JSON 입력과 단계별 확인

- 에이전트 인터페이스 **v1.1**부터 Config·공간 형상 전용 JSON 명령 지원
- 개별 입력칸을 차례로 채우는 대신 JSON을 일괄 전달 · 같은 화면에서 Config와 3D 미리보기 확인
- 현재 탭의 편집기와 입력 검사 사용 · 파일 직접 변경이나 별도 서버 연결 불필요

| 순서 | 에이전트 작업 | 사용자 확인 |
| --- | --- | --- |
| 1 | 프로젝트·Case·CFD Template·솔버와 작업 목적 확인 | 대상과 해석 목적 확인 |
| 2 | 실제 Template 양식과 기존 공간 JSON 읽기 | 누락된 형상 치수·물성·조건 제공 |
| 3 | 공간 형상 JSON 작성 및 초안 반영 | 3D 형상·영역 이름·단위·고체/액체/기체 구분 확인 |
| 4 | 양식에 맞는 나머지 Config JSON 작성 및 초안 반영 | 각 설정의 의미·값·단위·근거·미확정값 확인 |
| 5 | 변경 전후를 요약하고 저장 여부 질문 | 확인 응답 후 Config·Case 최종 저장 |
| 6 | 종료 조건·저장 간격·대기열 대상과 순서 안내 | 계산 진행 확인 응답 후 대기열 추가·시작 |
| 7 | 로그·Case 상태·결과 확인 | 완료·실패·검증 상태 안내 |

- 각 단계 결과를 설명하고 다음 단계 안내 · Config 작성 요청만으로 계산 시작 금지
- 사용자 확인을 기다리는 절차는 에이전트 안내 규칙 · 프로그램에서 승인 응답을 강제로 검사하는 기능은 아님
- **JSON 저장**은 초안 반영 · Config 최종 저장·Case 실행 저장·대기열 시작과 구분
- 읽기 전용 실행 기록은 **이 Config로 새 Case**에서 사본을 만든 뒤 편집

### 전용 명령

| 명령 | 기능 | 인자 |
| --- | --- | --- |
| `config.json.open` | Config 또는 전체 공간 형상 JSON 열기 | `scope: "config"` 또는 `"geometry"` |
| `config.json.fill` | JSON 편집 버퍼에 일괄 입력 | `value`: JSON 문자열 · 최대 1 MB |
| `config.json.apply` | 기존 검사로 JSON을 초안에 반영 | 없음 |

- `CFDAgent.state().json`: 열린 JSON의 `scope`·`title`·`value`·`readonly`·`dirty` 조회 · 창이 닫혀 있으면 `null`
- `config.json.open` 전에 해당 Config 편집창 열기 · 명령은 프로젝트·Case를 자동 선택하지 않음
- 실제 조회된 JSON을 복사해 필요한 값만 변경 · 항목 이름·자료형·단위·식별자·관계·기존 메타데이터 유지
- Template의 `version`·`fields` 양식 정의, Config 값 객체, 전체 공간 문서는 서로 다른 형식 · 조회된 형식 그대로 수정
- 입력 양식이나 필수 자료가 없으면 사용자에게 요청 · 누락값을 임의로 확정하지 않음
- 공간 JSON에 포함되지 않은 물성·계산 조건은 Config JSON에서 입력
- `apply` 응답의 `dispatched`만으로 반영 성공 판정 금지 · `notices`, JSON 재조회, 3D 미리보기 확인
- 문법·자료형 오류는 수정 후 같은 초안에 재입력 · 읽기 전용·일시정지 상태 유지
- `apply`는 최종 저장이나 CFD 실행을 호출하지 않음

### JSON 입력 예시

- 아래 코드는 이미 열린 Config에서 전체 공간 JSON을 조회

```javascript
await CFDAgent.run('config.json.open', { scope: 'geometry' });
const current = CFDAgent.state().json;
if (!current || current.readonly) throw new Error('Editable JSON required');
const document = JSON.parse(current.value);
// document를 실제 양식과 사용자가 제공한 치수·조건에 맞게 수정
```

- 수정한 문서를 전달하는 함수 · 적용 후 사용자에게 화면 확인 요청

```javascript
async function applyDraft(document) {
  const fill = await CFDAgent.run('config.json.fill', {
    value: JSON.stringify(document, null, 2)
  });
  if (fill.status !== 'dispatched') return fill;
  return await CFDAgent.run('config.json.apply');
}
// 반환된 state.json과 state.notices 확인
// 사용자 확인 전에는 최종 저장·queue.add·queue.start 호출 금지
```

- 일반 Config에는 `scope: "config"` 사용 · 새로 읽은 문서에 같은 절차 적용
- 사용자에게 확인할 내용: 대상 형상, 치수와 단위, 재료와 물성, 초기·경계조건, 시간간격, 종료 조건, 출력 간격, 변경사항과 가정

## 준비

- CFD Studio 실행: `cfd_studio/실행.bat`
- 지원 환경: Windows 10/11 x64 · macOS 미지원
- 브라우저 조작 도구가 있는 LLM 에이전트 사용
- **사용자가 보고 있는 CFD Studio 탭**에 에이전트 연결
- 다른 브라우저 창에서 명령을 실행하면 그 창에만 화면 변경이 표시됨
- LLM 설치·계정 연결·브라우저 연결은 사용하는 에이전트 도구에서 진행
- Studio는 외부 HTTP·MCP 명령 서버나 원격 디버깅 포트를 열지 않음
- 계산 전 솔버 설치 상태와 실행 연결, Config·종료 조건·대기열 확인

## 에이전트 활성화

- 내장 AI 실행 버튼 없음 · 외부 에이전트가 `CFDAgent.prompt()`를 읽고 현재 Studio 탭에 연결
- 에이전트 전용 명령: `await CFDAgent.activate({name:"Agent", task:"작업 내용"})`
- 개발 작업은 진행 CLI의 `start` 사용 · 활성 세션이 있으면 기존 세션으로 갱신
- 사람에게 시작·재개·명령 실행 버튼이나 키보드 단축키를 제공하지 않음
- 작업 중에만 상단 **외부 에이전트 조작 중**과 **에이전트 조작 중단** 표시
- 중단 버튼을 누르면 관련 UI 즉시 숨김 · `cfd-agent-pause` 신호와 `PAUSED` 응답으로 다음 작업 차단
- 완료 시에도 관련 UI 숨김 · 재시작하려면 새로운 사용자 지시 필요
- 준비·진행·검토는 같은 화면에서 확인 · 사용자 입력과 선택이 바뀌면 다시 관측

## 명령

- 연결된 탭의 JavaScript 실행 기능에서 `window.CFDAgent` 사용
- Studio 소스 분석이나 프로젝트 파일 직접 편집 없이 기존 화면 조작 가능
- `CFDAgent.describe()`: 인터페이스 버전·명령 목록·안내 프롬프트
- `CFDAgent.state()`: 현재 프로젝트·Case·대기열·화면·입력값·버튼·알림·로그
- `CFDAgent.prompt()`: 복사용 안내 프롬프트
- `CFDAgent.history()`: 최근 명령 기록 최대 100개
- `CFDAgent.finish()`: 작업 종료 표시 · 사용자의 일시정지 상태는 유지
- `await CFDAgent.run(명령, 인자)`: 화면 조작

```javascript
// 현재 화면과 프로젝트·Case 식별자 확인
await CFDAgent.activate({name: 'Agent', task: 'Review project'});
const state = CFDAgent.state();

// 첫 프로젝트가 요청 대상인지 확인한 뒤 실제 식별자로 선택
const project = state.workspace?.projects?.[0];
if (!project) throw new Error('No project available');
await CFDAgent.run('project.select', { id: project.id });

// 선택된 Case의 Config 창 열기
await CFDAgent.run('config.open');

// 변경된 화면의 입력창과 버튼을 다시 확인
CFDAgent.state().controls;
```

| 명령 | 동작 | 인자 |
| --- | --- | --- |
| `cfd.open` | CFD 화면 | 없음 |
| `viewer.open` | 선택 Case의 Viewer 열기 또는 결과 준비 | 없음 |
| `project.select` | 프로젝트 선택 | `id` |
| `project.find` / `project.new` | 프로젝트 찾기 / 새 프로젝트 창 | 없음 · CFD 화면에서 사용 |
| `project.manage` | 프로젝트 관리 창 | 없음 |
| `case.select` | 현재 프로젝트의 Case 선택 | `id` |
| `case.new` | 새 Case Config 창 | 없음 |
| `config.open` | Config 편집 또는 읽기 | 없음 |
| `template.new` | 새 CFD Template 창 | 없음 |
| `queue.add` | 선택 초안을 대기열에 추가 | 없음 |
| `queue.start` | 표시된 전체 대기열 시작·재개 | 없음 |
| `queue.pause` | 다음 실행부터 일시정지 | 없음 |
| `case.stop` | 선택한 실행 중 Case 중단 | 없음 |
| `case.recovery` | 실패 사유·복구 창 | 없음 |
| `queue.skip` | 대기열의 실패 Case 건너뛰기 | 없음 |
| `result.open` | 생성·업데이트·열기 버튼 | 없음 |
| `result.refresh` | Viewer 결과 다시 읽기 | 없음 |
| `result.csv` | 선택 Case의 전체 CSV 추출 | 없음 |
| `viewer.mode` | Viewer 모드 선택 | `mode: "3d"` 또는 `"data"` |
| `settings.open` | 환경 설정 창 | 없음 |
| `ui.click` | 현재 화면의 버튼·접기·펼치기 조작 | `target` |
| `ui.fill` | 입력창에 문자열 입력 | `target`, `value` |
| `ui.select` | 선택 목록 변경 | `target`, `value` |
| `ui.check` | 체크박스·라디오 선택 | `target`, `checked` |

## 입력

- `state().controls`에서 `target`·`label`·`value`·`options`·`disabled`·`readonly` 확인
- 새 창·항목 전환 후 목록을 다시 읽기
- 화면에서 제거된 입력창의 `target`은 재사용 불가
- 숫자도 문자열로 전달: `value: "0.01"`
- 선택 목록은 표시 문구가 아닌 `options[].value` 사용
- 잘못된 숫자 형식은 거부 · 범위 오류는 입력창에 표시하며 수정 필요
- 파일 선택은 기존 브라우저 조작 도구의 파일 업로드 기능 사용
- 읽기 전용 실행 기록은 편집 불가 · **이 Config로 새 Case** 사용
- 입력 명령만으로는 저장되지 않음 · 같은 화면의 **저장** 버튼 사용
- 새로운 물성·경계조건·형상을 임의로 가정하지 않음

```javascript
const field = CFDAgent.state().controls.find(item => item.label === '프로젝트 이름');
if (!field) throw new Error('Read the current controls first');
await CFDAgent.run('ui.fill', { target: field.target, value: '열전달 비교' });
```

- 입력창 라벨은 표시 언어에 따라 다르므로 실제 목록에서 선택
- 외부 에이전트가 사용하는 명령 JSON 예시

```json
{"command":"config.open","args":{}}
```

## 결과 확인

- 반환값 `status: "dispatched"`: 화면 동작 전달됨
- **저장 성공·계산 시작·계산 완료를 의미하지 않음**
- 비동기 작업은 `state()`의 알림·대기열·Case 상태·로그에서 별도 확인
- 알림에 실패 사유가 있으면 입력이나 연결 상태 확인 후 진행
- `status: "rejected"`: 전달 거부 · `error` 확인
- `BUSY`: 다른 명령 전달 중 · 현재 동작을 확인하고 순차 진행
- `PAUSED`: 사용자가 에이전트 조작 중단 선택
- `STALE_TARGET` / `CONTROL_NOT_VISIBLE`: 화면을 다시 읽고 현재 항목 선택
- `CONTROL_DISABLED`: 현재 조건에서 비활성 · 화면의 필요 조건 확인
- `INVALID_INPUT` / `INPUT_INVALID`: 입력 형식·범위 수정
- 계산·재시도·중단은 사용자가 요청한 범위에서 수행
- 대기열 시작은 다른 프로젝트의 Case에도 적용될 수 있으므로 전체 순서 확인
- 시각화율·수치 검사·계산 완료·실험 검증을 구분해서 보고

## 중단 후 대기

- 중단 시 `state().paused`가 참이 되고 `cfd-agent-pause` 이벤트 발생
- 에이전트는 다음 편집·명령을 멈추고 새로운 사용자 지시를 기다림 · 자동 재활성화 금지
- 새 지시를 받은 뒤에만 `CFDAgent.state().progress.state.stop_revision`을 읽고 아래 전용 명령 사용
- `userRequest`에는 실제 새 지시를 전달 · 서버는 대화의 진위를 검증하지 않으므로 에이전트가 이 규칙을 준수해야 함

```javascript
await CFDAgent.activate({name: 'Agent', task: taskSummary,
  afterStop: stopRevision, userRequest: actualNewUserInstruction});
```

- CLI: `activate --session-file output\new-agent-session.json --after-stop N --user-request "실제 새 지시" --stage review --detail "새 작업" --wait-visible`
- `N`은 현재 `stop_revision` · 기존 파일을 덮어쓰지 않고 새 세션 파일 사용 · 이전 담당 토큰 무효화
- 브라우저 소유 세션은 `await CFDAgent.finish()`, CLI 소유 세션은 CLI `finish`로 종료
- 페이지 새로고침은 중단을 해제하지 않음 · 우회 목적의 탭·서버 재시작 금지
- 이미 진행 중인 셸 명령·CFD와 외부 LLM 프로세스의 강제 종료 기능은 아님 · 에이전트가 단계 사이에 신호 확인

## 범위

- 같은 탭의 기존 버튼과 입력 이벤트 사용 · 기존 검증·저장·스냅샷 규칙 적용
- 명령 처리 중 다른 명령은 거부 · 자동 재전송 없음
- 원본 Config 값은 상태 조회에 포함되므로 연결된 에이전트에 전달할 정보 범위 확인
- 활동 기록에는 입력값을 저장하지 않음 · 명령·대상 식별자·전달 상태만 기록
- 기록은 탭 메모리에 유지 · 새로고침 시 초기화
- 세션 식별자는 새로고침마다 변경 · 이전 입력창 식별자 재사용 금지
- JavaScript 실행 기능이 없는 에이전트는 화면 조작 도구로 같은 버튼 사용
- 브라우저 연결, 파일 업로드, 네이티브 폴더 선택, 운영체제 권한은 에이전트 도구와 브라우저의 지원 범위 적용

- `CFDAgent`가 없으면 미저장 편집을 보존한 뒤 새로고침 · Studio 재시작은 대기 중에만 진행하고 실행 중인 솔버나 사용자 브라우저를 종료하지 않음

## 연결 진단

- 연결 실패 시 `agent_diagnostics.py`로 Studio HTTP와 외부 에이전트 도구 오류를 구분
- HTTP 성공은 사용자 탭 연결 완료가 아님 · 브라우저·계산을 재시작하지 않음
- `APP-A001`: 외부 도구의 작업 경로 오류 · `APP-A002`: 포트/스크립트 오류 · `APP-N001`: HTTP 연결 실패
- [진단 명령 및 사일로 실행 제한](silo-agent-debug-20261003.md)

```bat
cfd_studio\Setup\Python312\python.exe cfd_studio\internal\agent_diagnostics.py
```

- 실행 파일 재실행: 기존 Studio 서버를 유지하고 해당 주소 열기 · 다른 서비스의 포트 점유 시 APP-A002 · 포트 자동 변경 및 프로세스 강제 종료 없음

## 형상별 격자

- 실제 Template JSON의 `mesh.refinement_regions` 또는 `porous_mesh.refinement_regions` 사용
- 형상 참조는 `target_path`·`cell_size` 지정 · 좌표 범위와 중복 지정 금지
- 원본 형상 치수 변경은 참조 영역에 반영 · JSON 배열 재정렬 시 참조 경로도 갱신
- 사일로 등가 형상은 지정 높이 구간 및 전체 수평 단면 세분화 · 원문 덕트 구현 여부 별도 확인
- 범위·예상 셀 수 확인 후 새 Case에 반영 · 기존 결과 유지 · [지원 범위](MESH-REFINEMENT.md)

## 독립 격자와 형상 폴더

- Template에서 출력한 JSON을 기준으로 형상에 `mesh_control.cell_size` 추가
- 비물리 영역은 `mesh_regions`에 `material_state: "mesh_refinement"`로 정의 · 물리 속성·벽·채움 금지
- 중첩은 안쪽 우선 · 동일 범위·부분 겹침의 다른 간격은 MESH-R006 · 거친 안쪽 간격은 MESH-R007
- 폴더는 `_studio.geometry_groups`와 형상의 `editor_group`으로 구성 · 키·좌표·물성 변경 금지
- 적용 후 사용자에게 투명 범위·간격·폴더 소속 확인 안내 · 저장·실행 절차는 별도 유지
- [Mesh refinement](MESH-REFINEMENT.md)
