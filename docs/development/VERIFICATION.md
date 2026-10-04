# 검증

## 증거 수준

| 구분 | 확인 내용 | 대신 증명하지 않는 것 |
| --- | --- | --- |
| 구문·단위 검사 | 자료형·분기·파일 계약·실패 처리 | 실제 UI·CFD 정확도 |
| 통합 검사 | 저장·대기열·결과 변환 연결 | 사용자가 보는 화면 |
| 실제 UI 검사 | 버튼·레이아웃·입력·에이전트 가시성 | 수치 정확도 |
| CFD 실행 검사 | 격자·솔버 실행·저장 완료 | 격자/시간 수렴 |
| 수치 검증 | 보존성·기준해·격자/시간 민감도 | 실측 재현 |
| 실험 검증 | 독립 측정·불확도·비교 조건 | 다른 저장고·물질의 정확도 |

## 변경별 필수 검사

| 변경 | 관련 검사 파일 | 추가 확인 |
| --- | --- | --- |
| Config/JSON | test_form_schema.py, test_form_config_editor.js, test_config_contract.js | 가져오기→편집→내보내기 왕복 |
| 공간·국소 격자 | test_spatial_editor.js, test_primitive_geometry.py, test_local_refinement.py, test_mesh_components.py | 겹침·포함·단위·다공성 경계 |
| 프로젝트 저장 | test_project_storage.py, test_config_assets.py, test_storage_layout.py | D 드라이브·오프라인·쓰기 실패·복사 복구 |
| Case/큐 | test_run_management.py, test_execution_workspace.py, test_execution_adapters.py, test_case_recovery.py | 3 Case 순차 실행·실패 정지·재시작 |
| 솔버·Template | test_solver_catalog.py, test_solver_requirements.py, test_solver_recommendations.py, test_cfd_forms.py | 정의만 제공/연결됨 구분 |
| 결과·Viewer | test_result_integrity.py, test_result_series.py, test_viewer_presentation.js, test_data_sheet_viewer.js | 빈/부분 프레임·좌표·단위·선택 전환 |
| 내보내기 | test_csv_export.py, test_line_profile_warehouse.py | 범위·열·원본 대조·실패 파일 |
| 에이전트 | test_agent_activity.py, test_agent_controls.js, test_agent_collaboration.js, test_agent_diagnostics.py | 중단·재개·현재 탭·진행 표시 |
| 격자 전이/대칭 | test_mesh_transition.py, test_warehouse_symmetry.py, test_porous_warehouse_mesh.py | 크기 제한·셀 예산·원본 보존 |
| 번역·장치 | test_i18n.js, test_hardware_monitor.py, test_background_console.py | 사용자 이름 미번역·측정 지연·창 점멸 |

- 표의 파일은 모두 `tests/` 아래 위치
- 브라우저 검사 스크립트는 [전체 목록](INVENTORY.md) 참고 · 스크립트별 환경을 읽고 격리 실행

## 명령

저장소 루트와 준비된 개발 환경에서 실행

```bash
python tools/check_development_docs.py
python -m unittest discover -s tests -v
node --test tests/test_*.js
```

- 전체 검사에는 플랫폼·개발 라이브러리 조건이 존재할 수 있음 · 설치 실패/환경 미지원은 제품 결함과 구분
- Windows 셸의 glob 처리 차이가 있으면 Node에 검사 파일 목록을 명시적으로 전달
- 테스트 통과 숫자만 기록하지 말고 commit·환경·명령·범위·skip/fail·산출물 기록
- 문서만 변경한 경우 문서/카탈로그/도움말 검사로 제한 · CFD를 불필요하게 다시 실행하지 않음

## CFD 검사 기준

- 생성 영역·체적·다공성 분류·경계 patch를 3D와 원본 파일로 대조
- checkMesh 결과·문제 셀 위치·셀 수·최대 비직교성 등 기록
- 잔차와 종료 조건 외에 질량/에너지 수지·압력차·극값·Courant 수 확인
- 격자/시간간격을 각각 바꾸고 동일 형상·물성·초기장·비교 시점 유지
- 허용오차는 시험 전에 명시 · 결과를 통과시키려고 사후 완화하지 않음
- AMR 제안의 경우 세분화 전후 적분 보존·프레임별 셀 대응·재개를 추가 검증
- 저장 원본장·변환장·조회값·Viewer 값을 대조
- 연구용 물성·반응·공급 최적화의 타당성은 소프트웨어 테스트로 대체하지 않음

## 실제 UI 인수 시나리오

1. Template 생성 → JSON 양식 → 프로젝트 생성 → 독립 Case 3개
2. 프리셋 저장 해제/새 이름 저장 → 원본 프리셋 불변 확인
3. 순서 변경·실행·실패·재시도/건너뛰기·재시작 복원
4. 프로젝트 간 CFD/Viewer 목록·선택·버튼 위치 일관성
5. 3D/Data Sheet·평균/좌표·선상 프로파일·Export
6. KO/EN/JA 전환 · 사용자 이름과 입력값 보존
7. 외부 에이전트 활성화·동일 화면 조작·사용자 중단·인계
8. 격자 전이 켜기/끄기·값 보존·계획 한도 오류

- 반복 가능한 작은 소프트웨어 시험과 실제 연구 Case를 명확하게 구분
- 결과 기록은 [시험 보고서 양식](templates/TEST-REPORT.md) 사용
