# CFD FORM 검토

## 변경

- Studio v185
- 왼쪽 CFD FORM 리스트: 이중액침냉각·옥수수 사일로·식량 저장고 훈증 시스템
- 새 FORM 생성, 각 행 오른쪽 수정 버튼
- 해석 엔진·지원 솔버 선택, 파트 제목·기본 Config 편집
- 프로젝트 생성 시 FORM 필수, 프리셋은 FORM별로 분리
- 기존 프리셋 파일 보존, 신규 프리셋은 FORM ID와 함께 저장
- Case별 Config·비교 기준·FORM 버전 보존
- Config 분류: 형상·격자 / 물성·경계조건 / 솔버·계산 / 관측·비교
- 분류마다 오른쪽 화살표, 펼쳐지는 둥근 패널
- FORM에서 변경한 파트 이름으로도 Config 검색
- Y축·Z축 모델의 마우스 회전 방향 통일
- 사용법·설명서·앱 우측 상단 도움말 갱신

## 보존

- 기존 프로젝트 2개, 실행 연결 28개 유지
- 식량창고 27개, D 드라이브 이중액침 1개
- 사용자 Raw·결과·기존 Config 파일 수정 없음
- 기존 미커밋 파일 `cfd_studio/configs/.initialized` 보존
- 실험용 생성·저장 검사는 별도 임시 등록부 사용
- Studio 재시작 전 계산·변환·대기열 비활성 확인
- 사용자 Chrome·CFD 계산 프로세스 중단 없음

## 검사

| 검사 | 결과 |
| --- | --- |
| Python 전체 | 162개 통과 |
| JavaScript Viewer·Config | 59개 통과 |
| Windows 내장 Python FORM 검사 | 7개 통과 |
| 프로젝트 저장 관련 추가 검사 | 16개 통과 |
| FORM·프리셋·Case 실제 브라우저 흐름 | 통과 |
| 서버 재시작·화면 새로고침 후 데이터 복원 | 통과 |
| 기존 결과 화면의 마우스 드래그 | 이중액침·저장고 확인 |

- FORM 미선택 프로젝트 생성 차단
- 같은 엔진의 서로 다른 FORM 사이 프리셋 혼용 차단
- 다른 해석 대상·솔버 Config 차단
- FORM 수정·재시작 후 기존 Case 입력·비교 기준 동일
- 프리셋 저장 실패 시 Case 변경·불완전 프리셋 잔존 방지
- 체크박스 기본 해제, 체크 시 해당 FORM에 새 프리셋 생성
- 실제 화면: FORM 생성 → 이름 수정 → FORM 전용 프리셋 → 프로젝트 → Case 저장 → 새로고침 → Config 재열람
- 사용자 파트 이름 `수조 치수` 검색: 해당 입력 3개 표시
- 카메라 수치시험: 동일 드래그의 화면 투영 방향 일치
- 실제 화면 드래그: 수평 40px·수직 20px, 이중액침 방위각 −0.22 / 저장고 +0.22, 고도각 모두 +0.09

## 재현

```text
python -m unittest discover -s tests -p "test_*.py" -q
node --test tests/test_data_sheet_viewer.js tests/test_shared_warehouse_viewer.js tests/test_settings_editor.js tests/test_viewer_review.js
```

## 범위

- 새 FORM은 지원되는 해석 엔진의 입력 양식
- 임의 솔버 실행 파일·새 물리 모델을 만드는 기능은 아님
- 기존 FORM의 해석 대상·솔버는 고정. 다른 대상·솔버는 새 FORM으로 생성
- FORM·프리셋 등록부는 Studio에 보관, Case 스냅샷은 각 프로젝트에 보관
- 이번 작업에서 CFD 계산 실행 없음
- 물리 검증·격자 수렴·실험 검증 상태 변경 없음
