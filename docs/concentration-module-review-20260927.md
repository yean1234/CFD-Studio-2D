# 농도장 모듈 검토 기록

검토일: 2026-09-27. 대상: 기존 소스와 문서, 합성 데이터 기반 오프라인 검사.

## 결론

현재 실행 모델은 `normalized_inert_tracer`이며 실제 ClO2 물성 모델이 아니다. 연구 대상의 이름, 정규화 계산, 실험 검증 여부를 별개로 해석해야 한다. 이번 작업은 표시 계약의 회귀 검사와 결과 관리 검토이며 농도 솔버의 기능 확장이나 실제 저장고 계산이 아니다.

## 확인한 범위와 한계

| 항목 | 확인 내용 | 판정 |
|---|---|---|
| 모델 구분 | `study_platform/contracts.py`는 연구 대상을 ClO2, 계산 모델을 정규화 추적자로 별도 기록 | 구분 구현됨; 새 회귀 검사 통과 |
| 과거 PH3 이름 | `tracer_transport/protocol.py`와 기존 입력에 남은 과거 연구 메타데이터 | 실제 PH3 계산 아님; 원본 호환성을 위해 변경하지 않음 |
| 자유 공간·다공성 영역 | 기존 정규화 확산 검증 코드와 문서가 있음 | 실제 쌀 물성 및 선정 저장고 검증 아님 |
| 이류 | 코드에 수송 항은 있으나 현재 공개 기능 표기는 U=0 | 비영 유동의 정확도 검증을 완료로 표시하지 않음 |
| 유동 저항 | 농도 모듈은 저장고의 Darcy-Forchheimer 유동장을 계산하지 않음 | 미구현 |
| 흡착 | 정규화 선형 교환 시험 이력이 있음 | 실제 재료 계수의 타당성 검증 아님 |
| 포대 전달·외부 누출 | 기능 표에서 false, 기존 계약에서 미지원 입력 거부 | 미구현 |
| 질량수지·격자·시간 세분화 | 과거 `VERIFICATION.md`에 소규모 시험 기록이 있음 | 이번에는 CFD 재실행하지 않음; 과거 기록을 새 검증 결과로 집계하지 않음 |
| 다공성 수렴 시험 | 과거 일부 사례는 격자와 시간간격을 동시에 줄였다고 명시 | 각각의 오차를 분리한 수렴 검증은 미완료 |
| 위치·시간별 조회 | 저장된 NPZ를 읽는 `FieldProvider`와 오프라인 조회 코드 존재 | 합성 데이터 조회 검사 통과; 실제 화학종 단위로 변환하지 않음 |
| 온도 조회 | `FieldProvider`가 농도 이외 필드를 거부 | 미구현 |
| 결과 그림 | 합성 배열의 축 순서·종횡비·공통 색 범위 검사 | 2개 검사 통과; 이번 브라우저 3D 재생 실측은 미실시 |
| 결과 보존 | 패키지 경로·해시·기존 목적지 보호 및 코드 변조 검사 | 선택한 오프라인 검사 통과 |
| 실제 저장고·실험 비교 | 실제 가스 모델과 독립 실험 비교의 완료 근거 없음 | 미구현 또는 미검증; 성공으로 표시하지 않음 |

## 이번 수정

- `tests/test_model_scope.py`: 연구 대상 이름만으로 실제 물성 모델 또는 실험 검증 완료로 표시하지 않는지 확인하는 5개 검사 추가.
- `tracer_transport/README.md`, `RESEARCH_PROTOCOL.md`: 과거 PH3 메타데이터와 현재 연구 대상·실제 계산 모델의 차이를 명시.
- 기존 솔버, 계수, 설정 JSON, Raw, 저장 결과와 운영 앱은 변경하지 않음.

## 실제 실행한 검사

총 10개 통과, 건너뛴 검사 없음. OpenFOAM 솔버는 실행하지 않았다.

1. 새 모델 구분 검사 5개: 실제 계산 모델, 단위, 미지원 기능, 실제 화학종 입력 거부, 읽기 시 원본 보존.
2. `test_tracer_visualization.py` 2개: 합성장 단면 방향·색 범위·종횡비, 잘못된 저장 배열 거부.
3. `StudyTests`에서 3개: `test_archive_paths_and_hashes`, `test_preview_hash_and_field_provider`, `test_modified_code_refused`.

첫 두 묶음의 재현 명령:

```bash
python -m unittest discover -s tests -p test_model_scope.py -v
python -m unittest discover -s tests -p test_tracer_visualization.py -v
```

세 번째 묶음은 저장소 루트에서 다음 명령으로 실행한다. 임시 파일은 테스트가 관리하며 운영 계산을 시작하지 않는다.

```bash
python -c "import sys, unittest; sys.path.insert(0, 'tests'); names=['test_studies.StudyTests.test_archive_paths_and_hashes','test_studies.StudyTests.test_preview_hash_and_field_provider','test_studies.StudyTests.test_modified_code_refused']; result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(names)); sys.exit(not result.wasSuccessful())"
```

## 근거 확인 수준

- 개발전달 폴더의 `CFD_Studio_UIUX_재현성_상세설계_20260926.md`에서 모델 상태·실행 상태·품질 상태 분리 요구를 확인했다.
- 기존 저장소의 `README.md`, `RESEARCH_PROTOCOL.md`, `VERIFICATION.md`와 현재 코드를 대조했다. 과거 실행 결과의 원시 로그 전체를 이번에 재감사한 것은 아니다.
- 기존 문서에 기재된 Agrafioti 2021 및 Arora 2025는 이번에 논문 원문을 새로 검토하지 않았다. 해당 논문에서 실제 가스 계수를 추출하거나 입력하지 않았다.
- OpenCFD의 [Verification and Validation](https://doc.openfoam.com/2306/examples/verification-validation/) 공식 검색 결과는 기준 데이터와의 비교 사례를 안내한다. 본문 직접 열기는 403으로 실패했으므로 전문을 검토했다고 주장하지 않는다. 이 문서는 소프트웨어 출처이며 쌀 또는 ClO2 물성의 출처가 아니다.

## 이번에 제공하지 않은 작업

실제 ClO2 물성·흡수·누출·공급 조건을 해당 시설의 실행 모델에 연결하는 구현·보정은 수행하지 않았다. 공급 최적화, 해충 사망률, 장비 제어도 포함하지 않았다. 정규화 시험의 성공이나 일반 결과 파일 검사 통과를 이 범위의 완성으로 해석하면 안 된다.
