# 저장동 수송 연결과 ClO₂ 입력 모델

2026-09-27. 기존 프로젝트, Raw, 설정 및 과거 계산 결과는 변경하지 않았다. 이 문서는 새 독립 실행 경로의 상태를 기록한다.

## 현재 코드 기준

| 기능 | 상태 | 확인 범위 |
|---|---|---|
| 78 m 저장동 박공지붕 격자 ↔ 수송 솔버 | 구현·수치시험 통과 | 공칭 도면 외형, 22,308셀, 정지 공기, 폐쇄벽, 정규화 확산 |
| ClO₂ 공기 중 확산 입력 | 구현·수치시험 통과 | 문헌의 5/23/40 °C 계수만 사용, 온도 보간·외삽 없음 |
| 1차 기상 소멸·체적 평균 외기 교환 항 | 구현·합성 수치시험 통과 | 두 제거량과 잔량을 분리한 수지; 계수는 입력 출처 필수 |
| 실측 농도 비교 | 비교 도구 구현; 실험 검증 미실시 | 센서 좌표·시각·불확도·독립 검증 구분 입력 시 계산 가능 |
| 셀별 농도 시간 적분 | 구현 | 저장 프레임의 사다리꼴 적분; ClO₂ 경로는 mg·s/m³, 사망률 계산 아님 |
| 5 m 부속부 및 연결 개구 | 미구현 | 부속부 상세 내부 치수와 개구 근거 없음 |
| 쌀 포대·시트·팔레트·다공성 저항 | 미구현 | 적재 형상·공극률·유효 전달계수·시트 정보 없음 |
| 실제 누출 위치·면 유속, 열·유동장 | 미구현 | 현재 교환 항은 공간 평균 근사이며 개구 누출 CFD가 아님 |
| Studio 저장고 화면의 새 계산 버튼·불규칙 격자 Viewer | 미연결 | 새 기능은 독립 CLI와 OpenFOAM 출력으로 사용 |
| 현장 ClO₂ 예측 정확도 | 미검증 | 초기 농도, 반응·교환 계수, 독립 센서 시계열 없음 |

## 출처와 적용 범위

- 저장동 길이 78 m, 폭 25 m, 처마 7.2 m, 지붕 상승 3.5 m는 [PNS/PAES 419:2015 Annex A](https://amtec.uplb.edu.ph/wp-content/uploads/2019/07/PNS-PAES-419-2015-Agricultural-Structures-Warehouse-for-Bag-Type-Storage-of-Grains.pdf)의 **예시 도면 공칭 외형**이다. 전체 83 m 중 5 m 부속부를 제외했다. 실제 실내 공기 체적이나 선정 시설 준공 치수가 아니다.
- [Lee et al. (2015)](https://doi.org/10.1016/j.jfoodeng.2014.07.008)는 ClO₂ 기체의 공기 중 확산계수를 5, 23, 40 °C에서 각각 0.129, 0.145, 0.173 cm²/s로 보고했다. 코드에서는 1.29×10⁻⁵, 1.45×10⁻⁵, 1.73×10⁻⁵ m²/s로 변환했다. 해당 논문의 조명·표면·실험실 조건에서의 반응률을 쌀 저장고 반응률로 전용하지 않았다.
- [Kim et al. (2019)](https://pure.korea.ac.kr/en/publications/chlorine-dioxide-fumigation-to-control-stored-product-insects-in-/)은 쌀 저장 공간 내 가스 분포의 불균일성을 보고한다. 공개 초록에서 이 저장동의 경계 조건, 포대 유효 확산계수 또는 독립 검증용 센서 시계열을 확보하지 못했다.

## 모델과 단위

별도 경로 `tracer_transport.warehouse_case`는 자유 공기 단상 농도에 대해 다음 식을 푼다. 비영 유동, 포대, 공급원은 이 경로에서 설정할 수 없다.

`∂C/∂t = ∇·(D∇C) − kᵣC − kₑC`, `U = 0`, 벽 법선 플럭스 0.

- ClO₂ 경로의 `C`와 OpenFOAM 장 단위는 kg/m³다. 입력 초기값과 실측 비교 CSV는 mg/m³이며 10⁻⁶을 곱해 내부 장에 저장한다. 숫자만 바꾼 정규화 추적자 결과가 아니다.
- `kᵣ`은 기상 1차 소멸 계수, `kₑ`는 외부 농도를 0으로 가정한 **체적 평균 교환 계수**다. 둘 다 s⁻¹. 이 교환 근사는 특정 누출 개구의 위치·면적·유량을 나타내지 않는다.
- 입력에는 각 계수의 `value_s_inv`, `basis` (`measured`, `literature`, `scenario_assumption`), `source`를 반드시 기록한다. 값 0도 해당 항을 생략한다는 모델 선택으로 기록한다. 외부 교환 계수는 일반 문헌값만으로 건물에 적용할 수 없도록 막았다.
- ClO₂ 경로의 초기 농도는 양수 값과 출처가 필요하다. 온도는 문헌에서 실제 측정한 세 값 중 하나만 허용한다. 반응·교환 계수를 새로 제공하지 않으면 현장 해석을 실행할 수 없다.
- 기존 `run.py`의 PH₃ 표기는 과거 메타데이터이며 기존 정규화 예제는 그대로 유지한다. 새 경로는 그 예제의 계약이나 과거 결과를 소급 변경하지 않는다.

## 실행과 결과

OpenFOAM v2312 환경에서 `tracer_transport/solver`를 `wmake`로 빌드한 뒤, 저장소 루트에서 다음과 같이 저장동의 **정규화 수치시험**을 실행한다. 출력 경로가 이미 있으면 덮어쓰지 않는다.

```bash
python3 -m tracer_transport.warehouse_case \
  --config tracer_transport/warehouse_gable_verification.json \
  --output /tmp/new-gable-verification
```

ClO₂ 입력은 같은 최상위 JSON 구조의 `transport`를 `clo2_gas_in_air`로 설정하고 `temperature_C`, `initial_mg_m3`, `initial_evidence`, `reaction`, `exchange`를 입력한다. 코드의 `tests/test_warehouse_case.py`에 합성 자료 예시가 있다. 시험용 계수를 현장 계수로 복사해서는 안 된다.

출력에는 입력 해시, 모델 계약, 격자 품질, OpenFOAM 장·로그, 전 프레임 및 셀별 농도 시간 적분을 담은 `concentration.npz`, `checks.json`, 실행 상태가 남는다. 적분은 저장 프레임 사이를 선형으로 가정한다. `numerical_pass`는 시간 출력·양수성·수지·간단 해석해 검사만 뜻한다. 현장 예측 인증 상태는 `model_validation=unvalidated_for_rice_warehouse`로 별도 기록한다. 반응 제거량과 교환 제거량은 `REMOVED` 로그 및 결과 JSON에서 분리한다.

실측 CSV의 열은 `sensor_id,x_m,y_m,z_m,time_s,concentration_mg_m3,uncertainty_mg_m3,split`이며 `split`은 `calibration` 또는 `validation`이다. 독립 검증 행이 필요하다. 공간은 최근접 셀, 시간은 저장 프레임 사이 선형 보간이며 셀 중심 거리 제한을 입력해야 한다. 비교는 측정 자료를 새로 확보한 뒤 실행한다.

```bash
python3 -m tracer_transport.compare_measurements \
  --case /path/to/completed-clo2-case \
  --observations /path/to/measurements.csv \
  --source '측정 자료 출처와 버전' \
  --max-cell-distance-m 1 \
  --output /path/to/new-comparison
```

비교 보고서의 오차·편향·불확도 내 비율은 계산 지표다. 허용오차와 독립 자료, 센서 보정 정보가 없으면 합격/불합격 판정을 하지 않는다. 현재 실측 비교 결과는 없다.

## 이번 실제 확인

OpenFOAM v2312로 솔버를 다시 빌드하고 기존 정규화 확산 사례를 재실행했다. 320셀·11프레임에서 해석해 RMSE 8.05×10⁻⁵, 상대 질량수지 오차 9.54×10⁻¹⁵였다. 저장동 박공지붕 결합 사례는 22,308셀·11프레임, 해석해 RMSE 5.33×10⁻⁶, 상대 수지 오차 6.25×10⁻¹⁶이었다. 이 사례의 확산계수 1 m²/s는 **수치시험 가정**이다.

ClO₂ 입력 경로는 64셀의 **합성 수치시험**으로 실행했다. 23 °C 문헌 공기 확산계수, 가상의 초기 농도 1 mg/m³, 가상의 반응 0.1 s⁻¹ 및 교환 0.05 s⁻¹을 사용했다. 11프레임의 상대 수지 오차는 9.94×10⁻¹⁶이고 균일 1차 소멸 해석해 RMSE는 9.59×10⁻¹⁰ kg/m³였다. 같은 계산에서 만든 가짜 센서값 1개를 비교 도구에 넣어 CSV와 지표 출력 경로를 확인했다. 이 숫자들은 실제 저장고의 농도·누출·노출을 예측하거나 검증한 값이 아니다.

전체 Python 회귀 90개 중 88개가 기본 환경에서 통과하고 그림 라이브러리가 없어 2개가 건너뛰어졌다. 해당 2개는 별도 그림 환경에서 통과했다. JavaScript Viewer 25개도 통과했다. 기존 저장 프로젝트 13개, 253프레임, 647,680개 스칼라값은 읽기 전용 형식 검사에서 오류가 없었다. 기존 결과의 물리적 정확도를 뜻하지 않는다. 새 OpenFOAM 원본과 로그는 Git에 포함하지 않은 `output/warehouse_transport_20260927/`에 보존했다.
