# 에이전트 사용법

## 준비

- CFD Studio 실행: `cfd_studio/실행.bat`
- 지원 환경: Windows 10/11 x64 · macOS 미지원
- 브라우저 조작 도구가 있는 LLM 에이전트 사용
- **사용자가 보고 있는 CFD Studio 탭**에 에이전트 연결
- 다른 브라우저 창에서 명령을 실행하면 그 창에만 화면 변경이 표시됨
- LLM 설치·계정 연결·브라우저 연결은 사용하는 에이전트 도구에서 진행
- Studio는 외부 HTTP·MCP 명령 서버나 원격 디버깅 포트를 열지 않음
- 계산 전 솔버 설치 상태와 실행 연결, Config·종료 조건·대기열 확인

## 안내 프롬프트

- 오른쪽 상단 **환경 설정 → LLM 에이전트 → 에이전트 안내**
- **안내 프롬프트 복사**를 눌러 에이전트 대화에 전달
- 복사가 제한된 브라우저에서는 **안내 보기**의 내용을 직접 복사
- 단축키 **Alt + Shift + A**: 에이전트 안내 펼치기·접기
- 안내에는 사전 준비, 명령 목록, 입력 방법, 실행·검증 상태 판독 기준 포함
- 안내 프롬프트는 에이전트용 영문 · 화면 버튼은 한국어·영어·일본어 지원

## 화면 표시

- 명령 대상 버튼·입력창을 파란 테두리로 강조
- 실제 프로젝트·Case 선택과 Config·Viewer 화면에 동작 반영
- 최상단 가운데 **에이전트 조작 중** 표시 · 천천히 깜박이며, 움직임 최소화 설정에서는 고정 표시
- 최상단 오른쪽 **에이전트 조작 중단**: 이후 명령 차단, 에이전트에 일시정지 신호 전달
- 일시정지 후 같은 위치의 **에이전트 조작 재개**로 재개 신호 전달
- 오른쪽 아래에 현재 명령과 최근 전달 기록 표시
- **명령 일시정지**: 이후 에이전트 명령 차단
- **명령 허용**: 명령 수신 재개
- 일시정지는 이미 전달한 동작이나 진행 중인 CFD 계산을 중단하지 않음
- **×**: 안내 패널만 숨김 · 에이전트 명령 차단은 **명령 일시정지** 사용
- 사용자가 동시에 선택·입력을 변경한 경우 에이전트는 현재 화면을 다시 확인한 뒤 진행

![에이전트 조작 표시](assets/agent-controls/banner.png)

![에이전트 안내](assets/agent-controls/guide.png)

## 명령

- 연결된 탭의 JavaScript 실행 기능에서 `window.CFDAgent` 사용
- 코드를 해석하거나 프로젝트 파일을 직접 편집할 필요 없음
- `CFDAgent.describe()`: 인터페이스 버전·명령 목록·안내 프롬프트
- `CFDAgent.state()`: 현재 프로젝트·Case·대기열·화면·입력값·버튼·알림·로그
- `CFDAgent.prompt()`: 복사용 안내 프롬프트
- `CFDAgent.history()`: 최근 명령 기록 최대 100개
- `CFDAgent.waitForResume({timeoutMs:30000})`: 사용자 재개 신호 대기 · 최대 60초씩 대기 가능
- `CFDAgent.finish()`: 작업 종료 표시 · 사용자의 일시정지 상태는 유지
- `await CFDAgent.run(명령, 인자)`: 화면 조작
- 안내 패널의 **명령 입력 → 명령 실행**에서도 JSON 명령 실행 가능

```javascript
// 현재 화면과 프로젝트·Case 식별자 확인
const state = CFDAgent.state();

// 실제 목록에서 받은 식별자 사용
await CFDAgent.run('project.select', { id: state.workspace.projects[0].id });

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
await CFDAgent.run('ui.fill', { target: field.target, value: '열전달 비교' });
```

- 안내 패널에서 실행하는 JSON 예시

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
- `PAUSED`: 사용자가 명령 일시정지 선택
- `STALE_TARGET` / `CONTROL_NOT_VISIBLE`: 화면을 다시 읽고 현재 항목 선택
- `CONTROL_DISABLED`: 현재 조건에서 비활성 · 화면의 필요 조건 확인
- `INVALID_INPUT` / `INPUT_INVALID`: 입력 형식·범위 수정
- 계산·재시도·중단은 사용자가 요청한 범위에서 수행
- 대기열 시작은 다른 프로젝트의 Case에도 적용될 수 있으므로 전체 순서 확인
- 시각화율·수치 검사·계산 완료·실험 검증을 구분해서 보고

## 일시정지 신호

- 중단 시 `state().paused`가 `true`로 변경되고 `cfd-agent-pause` 이벤트 발생
- 재개 시 `cfd-agent-resume` 이벤트 발생 · 신호에 세션·순번·발생 시각 포함
- 에이전트는 매 명령 전 상태를 확인하고 일시정지 신호나 `PAUSED` 응답을 받으면 대기
- 아래 예시는 에이전트 연결 도구에서 사용하는 대기 처리

```javascript
while (CFDAgent.state().paused) {
  const signal = await CFDAgent.waitForResume({ timeoutMs: 30000 });
  if (signal.status === 'resumed') break;
}
// 현재 화면과 사용자 변경을 다시 확인한 뒤 다음 명령 결정
const current = CFDAgent.state();
```

- 작업을 마치면 `CFDAgent.finish()` 호출 · 상단 조작 표시 해제
- 에이전트가 응답하지 않으면 사용자가 **에이전트 조작 중단**으로 추가 명령 차단 가능
- Studio가 외부 LLM 프로세스 자체를 강제 정지하지는 않음 · 연결 도구가 신호를 따라 대기하도록 안내 프롬프트 적용
- 이미 전달한 화면 동작과 CFD 계산은 유지 · 계산 중단은 기존 Case의 **실행 중단** 기능 사용
- 일시정지를 우회하기 위한 새 탭 연결·새로고침·직접 UI 호출·자동 재개 금지

## 범위

- 같은 탭의 기존 버튼과 입력 이벤트 사용 · 기존 검증·저장·스냅샷 규칙 적용
- 명령 처리 중 다른 명령은 거부 · 자동 재전송 없음
- 원본 Config 값은 상태 조회에 포함되므로 연결된 에이전트에 전달할 정보 범위 확인
- 활동 기록에는 입력값을 저장하지 않음 · 명령·대상 식별자·전달 상태만 기록
- 기록은 탭 메모리에 유지 · 새로고침 시 초기화
- 세션 식별자는 새로고침마다 변경 · 이전 입력창 식별자 재사용 금지
- JavaScript 실행 기능이 없는 에이전트는 화면 조작 도구로 같은 버튼 사용
- 브라우저 연결, 파일 업로드, 네이티브 폴더 선택, 운영체제 권한은 에이전트 도구와 브라우저의 지원 범위 적용
