# Config 편집

## 사용법

1. **CFD FORM 리스트 → 새로 만들기**
2. FORM 이름·솔버 선택
3. **양식 구성**에서 질문에 응답
4. **양식 생성 → Config 편집**
5. 항목에 값 입력 후 **Download JSON**
6. 파일 수정은 **Import JSON**으로 다시 적용
7. **Apply → FORM 초안 저장**

- [질문별 구성과 화면](form-wizard-20260929.md)
- 아래 기본 구조는 수동 편집용 공통 JSON 설명. 실제 생성 양식은 솔버·응답에 따라 변경
- [공통 JSON 파일](../cfd_studio/templates/cfd-config-template.json)

![Config 편집](assets/generic-config-20260929/editor.png)

## 기본 구조

| 파트 | 입력 내용 |
|---|---|
| geometry | 형상 원본, 해석 영역 |
| mesh | 격자 원본, 생성 도구, 격자 제어 |
| materials | 물성 정의, 영역별 재료 배정 |
| physics | 사용할 물리 모델 |
| initial_conditions | 초기장 |
| boundary_conditions | 경계별 조건 |
| numerics | 수치 기법, 선형 솔버, 계산 시간간격 |
| termination | 종료 방식, 기준 |
| outputs | 저장할 장, 결과 저장 간격, 조회 지점 |

- `null`: 미입력. 0이나 기본 물성으로 간주하지 않음
- `{}`·`[]`: 세부 항목을 채울 자리
- 특정 대상·치수·물성·모델·시간간격 자동 지정 없음
- 이름·하위 구조·추가 항목 자유 편집
- 새 FORM에만 기본 구조 제공. 기존 FORM 자동 재구성 없음
- 경로와 모델명은 정의 데이터. JSON을 저장해도 형상 가져오기나 솔버 입력 파일 생성이 자동 실행되지 않음

## 기능

- Key: 사용자 입력 그대로 표시·저장. 한글로 자동 변환하지 않음
- Type: string / number / integer / boolean / object / array / null
- Object: 하위 항목 추가·삭제, 계층 구성
- Array: JSON 배열 직접 입력
- Unit: 사용자 지정 단위 보존. 수치 변환 기능 없음
- JSON: 전체 값 구조 편집
- Import JSON / Download JSON: 값만 가져오기·내보내기. 단위·자료형 스키마는 FORM 저장에 포함
- Cancel: 편집 취소
- 중복 Key·자료형 불일치·잘못된 JSON: 저장 차단
- 기존 양식: Config Template에서 명시적으로 선택
- 새 FORM: 수조·집·저장고 형상 자동 생성 없음

## 범위

- 자유 Config 정의·저장·복원 지원
- 사용자 정의 FORM: 솔버 입력 파일 생성·실행·결과 읽기 연결 전까지 초안
- 솔버 설치 여부와 임의 Config 실행 가능 여부 별도
- 기존 연결 템플릿: 필수 Config 계약 유지
- 기존 Case·프리셋·계산 결과: 자동 변경 없음
- 제한: 항목 512개, 중첩 16단계, 배열당 10,000개, JSON 가져오기 1 MB

## 확인

- Python 관련 검사 19개 통과
- JavaScript Config 검사 7개 통과
- 실제 화면: 공통 파트 9개, JSON 다운로드 확인
- 내려받은 JSON과 제공 템플릿 값 일치 확인
- 파일 수정·Import JSON·FORM 저장·새로고침 후 동일 값 복원 확인
- 임시 저장소에서 UI 확인. CFD 계산 미실행
- 적용 버전: v191
- 재시작 후 기존 프로젝트 2개·실행 28개·대기열 상태 일치 확인

## 변경 파일

- `cfd_studio/templates/cfd-config-template.json`: 공통 양식 파일
- `cfd_studio/internal/form_config_editor.js`: 파트별 펼치기·JSON 다운로드
- `cfd_studio/internal/form_schema.py`: 스키마·값 검사
- `cfd_studio/internal/cfd_forms.py`: FORM 스키마 저장
- `cfd_studio/internal/execution_workspace.js`: 공통 Config·선택 템플릿 연결
- `cfd_studio/internal/execution_workspace.py`: Config 스키마 API 전달
- `cfd_studio/app.py`: 편집기 로딩·도움말
- `tests/test_form_config_editor.js`, `tests/test_form_schema.py`: 데이터 검사·복원 검사
