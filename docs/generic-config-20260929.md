# Config 편집

## 사용법

1. **CFD FORM 리스트 → 새로 만들기**
2. FORM 이름과 솔버 선택
3. **Blank Config → Config 편집**
4. **+ Field**로 항목 추가
5. **Key · Type · Unit · Value** 입력
6. **Apply → FORM 초안 저장**

![Config 편집](assets/generic-config-20260929/editor.png)

## 기능

- Key: 사용자 입력 그대로 표시·저장. 한글로 자동 변환하지 않음
- Type: string / number / integer / boolean / object / array / null
- Object: 하위 항목 추가·삭제, 계층 구성
- Array: JSON 배열 직접 입력
- Unit: 사용자 지정 단위 보존. 수치 변환 기능 없음
- JSON: 전체 값 구조 편집
- Import JSON / Export JSON: 값만 가져오기·내보내기. 단위·자료형 스키마는 FORM 저장에 포함
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

- 실제 브라우저: 빈 Config, 항목 추가, JSON 편집, 중첩 구조, 단위 입력
- 저장·새로고침 후 값 12.5와 단위 m 복원 확인
- JSON 버튼 재선택 시 미저장 입력 유지 확인
- 솔버·템플릿 전환 후 자유 Config 입력 유지 확인
- 임시 저장소에서 UI 확인. CFD 계산 미실행
- Python 전체 검사: 186개 실행, 184개 통과·2개 제외. 보류 중인 격자 관련 로컬 검사 포함
- JavaScript: 67개 통과
- 적용 버전: v190
- 앱 재시작 후 프로젝트 2개·실행 28개·대기열 상태 일치 확인

## 변경 파일

- `cfd_studio/internal/form_config_editor.js`: 범용 Config 편집기
- `cfd_studio/internal/form_schema.py`: 스키마·값 검사
- `cfd_studio/internal/cfd_forms.py`: FORM 스키마 저장
- `cfd_studio/internal/execution_workspace.js`: 빈 Config·선택 템플릿 연결
- `cfd_studio/internal/execution_workspace.py`: Config 스키마 API 전달
- `cfd_studio/app.py`: 편집기 로딩·도움말
- `tests/test_form_config_editor.js`, `tests/test_form_schema.py`: 데이터 검사·복원 검사
