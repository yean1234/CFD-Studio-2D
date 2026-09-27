# CFD Studio 저장고 수송 사용·검증 안내

이 문서는 포대식 쌀 저장고의 ClO₂ 훈증 CFD 연구를 위한 **현재 구현 범위**와 재현 절차를 설명한다. 실험 기록이 없는 값을 현장 조건으로 확정하지 않는다. 일반 프로젝트의 설치·실행은 [앱 사용법](../cfd_studio/README.md)을 참고한다.

**새 계산:** 상세계획서 도면과 적재 제약, 문헌의 기온 곡선, 명시적 초기 농도를 사용한 7일 확산 시나리오를 실행했다. [도면 정의·입력 가정·농도장 결과](warehouse-plan-scenario-20260928.md)를 확인한다. 이 시나리오는 실측 자료 없이 실행할 수 있다.

## 화면에서 사용하는 순서

1. Windows에서 `cfd_studio/실행.bat`으로 Studio를 연다. 기존 계산·Raw 폴더를 삭제하거나 이동하지 않는다.
2. `/warehouse`(저장고 설정·격자)에서 도면 공칭 형상을 확인한다. 설정을 저장한 뒤 **격자 검사**를 실행하면 `blockMesh`와 `checkMesh` 결과를 확인할 수 있다. 이 동작은 농도 계산이 아니다.
3. `/warehouse/results`(저장고 수송 결과)에서 **완료된 계산**을 선택한다. 프레임을 바꾸면 OpenFOAM 원본 `C`와 조회 배열을 대조한 뒤 셀 중심 농도를 색 점으로 표시한다. 점 표시는 셀의 실제 체적 렌더링이 아니다.
4. x·y·z(m), 시간(s), 허용 셀 중심 거리(m)를 입력해 농도를 조회한다. 가장 가까운 셀과 저장 시점 간 선형 보간값, 단위, 원본 파일 경로가 나온다. 계산 영역 밖·저장 시간 밖·허용 거리 밖은 오류로 표시한다. 계획서 시나리오는 **공간 균일 가정 기온**도 표시한다. 열 방정식으로 구한 온도장은 아니다.
5. 메인 화면의 오른쪽 위 `!`에서 모델·단위·검증 상태를 다시 확인한다. `/studies/design`의 적재·공급 위치는 후보 미리보기이며 실제 저장고 CFD 최적화가 아니다.

메인 프로젝트 Viewer는 액침냉각·단상 저장고·기존 정규화 추적자 결과를 다룬다. 별도 박공지붕 저장고 수송 계산은 위의 읽기 전용 결과 화면에 표시된다. 저장고 수송 솔버의 실행은 아직 Studio의 Study 실행 버튼과 연결되지 않았다.
결과 화면의 NPZ 읽기는 Windows 내장 Python의 표준 라이브러리만 사용한다. 수송 계산·후처리 명령에는 WSL의 NumPy가 필요하다.

## 모델과 자료의 범위

| 구분 | 현재 상태 |
|---|---|
| 도면 | PNS/PAES 419:2015 예시의 78 m 저장동 + 5 m 부속실, 폭 25 m. 계산 격자는 **78 m 저장동의 공칭 외형**만 사용 |
| 확정되지 않은 형상 | 벽 두께·실내 순치수, 시트 구획, 포대·팔레트·통로, 문·환기구, 5 m 부속실의 실제 연결 개구 |
| 정규화 시험 | 정지 공기, 폐쇄벽, 박공지붕, 초기 코사인 농도, `C/C_ref`; 수치해·질량수지·격자·시간간격 검사 완료 |
| ClO₂ 가스 입력 시험 | 공기 중 확산계수 5/23/40 °C만 [Lee 등(2015)](https://doi.org/10.1016/j.jfoodeng.2014.07.008)의 저자 초록에 근거. 초기 농도와 1차 반응·체적 평균 교환 항은 출처·근거 종류를 입력해야 함. 실제 저장고 모델 검증은 없음 |
| 미연결 물리 | 비영 유동·열전달, 포대 내부 전달, 공간별 실제 외부 누출, 발생·공급 경계와 독립 실측 비교 |

정규화 `C/C_ref`를 mg/m³로 읽지 않는다. ClO₂ 시험의 원본은 kg/m³이며 화면 조회값은 mg/m³로 변환한다. 문헌 공기 확산계수는 저장고 반응·누출·포대 전달 계수의 근거가 아니다. `PH₃`가 남아 있는 과거 파일의 이름은 연구 이력 메타데이터다.

## 명령줄에서 재현

저장소 루트에서 OpenFOAM v2312 환경과 Python NumPy를 준비한다. **새 출력 폴더**를 사용한다. 원본 결과에 다시 실행하지 않는다.

```bash
source /usr/lib/openfoam/openfoam2312/etc/bashrc
cd /path/to/CFD-Studio
cd tracer_transport/solver && wmake && cd ../..
python3 -m tracer_transport.warehouse_case \
  --config tracer_transport/warehouse_gable_verification.json \
  --output output/warehouse_transport_my_new_case
python3 tests/audit_warehouse_case.py output/warehouse_transport_my_new_case
python3 -m tracer_transport.verify_gable_convergence \
  --config tracer_transport/warehouse_gable_verification.json \
  --max-cells 200000 \
  --output output/my_new_warehouse_convergence
```

`--max-cells`는 사용자 지정 계산 예산이다. 격자 세분화가 이를 넘으면 검사기는 실행 전에 중단한다. 결과의 `model_contract.json`, `transport_input.json`, `input_hashes.json`, `mesh_quality.json`, `checks.json`, 원본 시간 폴더와 `concentration.npz`를 함께 보관한다. `state.json`이 `complete`이고 해당 수치시험 또는 실행·보존 검사가 통과한 최상위 `output/warehouse_transport_*` 폴더만 Studio 결과 목록에 나타난다. 시나리오의 실행·보존 검사 통과는 수렴·실험 검증 완료와 구분된다.

독립 실측 CSV가 확보되면 `tracer_transport/compare_measurements.py`의 계약에 따라 `sensor_id,x_m,y_m,z_m,time_s,concentration_mg_m3,uncertainty_mg_m3,split`을 준비한다. `split`은 `calibration` 또는 `validation`이다. 비교 결과가 계산되었다는 사실만으로 모델이 검증되었다고 판정하지 않는다.

## 2026-09-28 실행 기록

- 원래 저장소의 `output/warehouse_transport_20260928_01`: 22,308셀·11프레임, 정규화 해석해 RMSE `5.3339e-6`, 상대 질량수지 오차 `6.2535e-16`.
- `output/warehouse_transport_20260928_convergence_verified`: 격자 2,340 → 22,308 → 178,464셀에서 오차 감소, 시간간격 2 → 1 → 0.5 s에서 오차 감소. 각각 다른 요인을 고정한 시험이다.
- 원본 `C` 11개와 조회 배열의 245,388개 스칼라 최대 차이 0. 이는 저장·조회 충실도 검사이며 물리적 정확도 검증은 아니다.
- 브라우저의 저장고 결과 화면에서 정규화 사례의 모델·단위·수치/실험 상태, 3D 셀 점, 위치 조회를 확인했다. 액침냉각·단상 저장고의 **실제 저장 결과 3D 화면**은 해당 유형의 보존된 원본 결과가 없어 아직 완료 판정하지 않았다.

확정 실내 치수와 배치·개구, 운전·유동·온도 조건, 위치별 센서 시계열과 불확도 및 보정/독립 검증 분리가 확보되어야 실제 저장고 결과의 실험 검증과 공급조건 최적화 범위를 정할 수 있다.
