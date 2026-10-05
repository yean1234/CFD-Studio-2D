# 데이터 계약

## 기준 문서

- [Config JSON](../CONFIG-JSON.md): 입력 양식·가져오기·표시 규칙의 기준
- [결과 시각화](../VIEWER-DATA.md): 물리량·단위·표시·조회 방식의 기준
- [오류 사전](../config-error-codes.json): 코드별 원인·다음 행동
- 아래 내용은 개발 변경 시 확인할 경계와 저장 구조

## 엔터티

| 엔터티 | 핵심 식별·내용 | 변경 규칙 |
| --- | --- | --- |
| Template | id, solver, config_schema, 초기 형상 | 배포 정의와 사용자 정의 구분 |
| Preset | Template 연결·이름·입력값 | Case 수정과 별도 저장 |
| Project | id, name, description, form_id, default_preset, storage_path | 기본값 변경은 이후 Case에 적용 |
| Case | id, project_id, revision, config, 종료 조건, 상태 | 시작 전만 편집 · 다른 Case와 독립 |
| Attempt | 실행 시점·스냅샷·job·출력 경로 | 재시도·재개 이력 분리 |
| Result | 원본 위치·모델·단위·시간 축·검사 상태 | 계산 완료와 물리 검증 분리 |

- 실제 필드의 선택/필수 여부는 `project_storage.py`, `run_management.py`, `cfd_forms.py` 기준
- 표는 새 범용 스키마를 선언한 것이 아님 · 기존 파일에 표의 키를 일괄 강제하지 않음

## 프로젝트 저장

```text
<사용자가 지정한 프로젝트 폴더>/
  project.cfdproj
  ProjectSettings/
    executions.json
  Cases/
    <case id>/Attempts/<attempt id>/
      job.json
      Raw/
      Results/
  Results/
  Cache/
```

- 파일·하위 폴더는 실행 어댑터와 진행 상태에 따라 생성 · 모든 결과가 동일 파일 형식인 것은 아님
- Studio 등록부: `cfd_studio/_runtime/executions` · 프로젝트 위치와 실행 조정을 관리
- 이전 결과는 외부 연결 경로를 유지할 수 있음 · 전체가 새 구조로 이동했다고 가정하지 않음
- C/D 등 선택 경로의 존재·쓰기·겹침 확인 · 드라이브 루트 자체를 프로젝트로 사용하지 않음
- 이동: 새 위치 복사 → 크기·SHA-256 검증 → 연결 전환 · 원본 보존
- `.copy-incomplete`가 있는 복사 실패 폴더는 정상 프로젝트로 채택하지 않음
- 원자 JSON 교체는 개별 파일 수준 · 전체 디스크 트랜잭션/전원 장애 복구 보장과 구분

## JSON 왕복

- `format: cfd-studio-config`, `version: 1`, `config`, `config_schema`
- Studio 필드 스키마는 JSON Schema 전체 규격과 다름
- key는 연결 식별자, label은 화면 이름, unit은 단위 · 사용자 이름·입력값 번역 금지
- 사용자 확장 키·배열 items·벡터·null·읽기 전용·`_studio.field_metadata` 보존
- 형상 JSON은 전체 공간/선택 요소의 범위를 명시 · 부분 문서가 전체 Config를 덮어쓰지 않도록 검사
- 미지원 솔버 입력은 UI에 표시 가능해도 계산 적용 완료로 처리하지 않음
- 외부 JSON의 중복 키는 파서에서 마지막 값이 남을 수 있음 · 완전한 중복 검출 보장 없음

## 격자 전이 계약

| 키 | 의미 | 호환 규칙 |
| --- | --- | --- |
| `porous_mesh.domain_mode` | 전체/Y 중앙면 절반 | 대칭 조건 검사 필요 |
| `maximum_cell_edge_m` | 실제 최대 셀 변 길이 제한 | 미지정 시 기존 간격 |
| `mesh_transition_enabled` | 간격 전이 사용 여부 | 키가 없으면 ratio 유무로 기존 동작 유지 |
| `max_axis_spacing_ratio` | 인접 기준 축 간격비 | 사용 시 유한한 수 > 1 · 끄면 값 보존 |
| `maximum_cells` | 생성 전 셀 수 한도 | 초과 시 오류 · 자동 조대화 금지 |

- 저장고 정렬 블록 실행기에 연결된 계약 · 모든 솔버에 공통 적용된다고 주장하지 않음
- `mesh_plan`은 생성/CFD 실행이 아니며 기본 배열 크기는 솔버 전체 RAM 예측이 아님

## 2D 단면 계약

| 키·파일 | 의미 | 호환 규칙 |
| --- | --- | --- |
| `case_dimension` | `2D`/`3D` 선택 | 키가 없으면 3D · `MODE` 환경변수·`--dimension`이 우선 · 그 밖의 값은 생성 전 오류 |
| `section_2d.x_mm` | 단면 x 위치 [mm] | `null`이면 `heater.cpus[cpu_index]` x 중심 · CPU를 지나지 않으면 오류 |
| `section_2d.heat_rule` | `local_flux`·`width_average`·`flux_and_power` | 기본 `local_flux` · 다른 값은 오류 |
| `section_2d.represented_width_mm` | 폭당 전력 기준 폭 | `null`이면 `tank.width_mm` |
| `section_2d.thickness_mm` | empty 방향 두께 | `null`이면 `mesh.dx_mm` · 결과는 단위 폭당 값 |
| `section_2d.coil_UA_W_mK` | 코일 폭당 UA 직접 지정 | `null`이면 3D UA × 폭당 입열비 · 격자 상한 90% 제한 |
| `constant/section2d.json` | 단면·스케일링·코일·유체값·셀 `(ix, iy)` 대응·히터 면 | 2D 생성 때만 작성 · 3D 생성 시 삭제 · 셀 순서는 blockMesh 블록 순서 |
| `coarse_inputs.csv` | `case_id, coarse_cell, x_m, q_W_m2, vapor_fraction` | Cooper 게이트 열 순서 유지 · 추가 열은 `coarse_inputs_extended.csv`에만 |

- 2D 결과 배열은 (프레임, y, x) · 고체 셀은 NaN과 `mask = 0` · 누락값을 0으로 치환하지 않음
- 벽면 온도는 솔버 `cpu` 패치 값을 높이 오름차순으로 사용 · 없을 때만 전도 추정값과 `T_wall_source` 표시
- 3D 실행의 Config·생성 파일 계약은 변경 없음

## 결과 계약

- 정규화 추적자와 물성 모델의 모델명·단위·유효 영역 구분
- 저장고 원본 U/T/C와 변환 배열의 대응·프레임 시각·셀 좌표·체적 확인
- 현재 저장고 변환은 고정 셀 배열에 의존 · AMR은 프레임별 격자 버전·좌표·체적 계약이 선행되어야 함
- 계산한 절반 밖의 좌표 조회를 차단 · 반대쪽 결과를 계산한 것으로 생성하지 않음
- 정량 그래프는 최근접 셀/평균 등 추출 방법과 실제 좌표를 유지
- 준비율 100%는 결과 읽기·시각화 준비 상태 · 수치 정확도 비율이 아님

## 계약 변경 절차

1. 구버전 입력과 결과를 읽는 회귀 fixture 확보
2. 새로운 버전/선택 키와 기본값 의미 정의
3. 읽기 → 검증 → 변환 → 임시 저장 → 검증 → 교체
4. 실패 시 기존 파일·등록부 유지 및 오류 코드 제공
5. UI·실행기·결과·에이전트·다국어 안내를 동일 변경으로 검토
6. 원본을 삭제하는 일괄 마이그레이션을 배포 기본 동작으로 넣지 않음
