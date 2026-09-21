# OpenFOAM 이중 액침 CFD 설정 근거 및 검증 기준

- 작성일: 2026-08-22
- 대상: TMC-49 하부층 / DI수 상부층 / CPU 2개 / 상부 수냉 코일의 3상 OpenFOAM 모델
- 적용 설정: `OpenFOAM_케이스/cfd_studio/configs/이권영 교수님 기준.json`
- 생성기: `OpenFOAM_케이스/tmc49_full_tank/tools/build_case.py`
- 현재 판정: **연구용 예비 모델(`research_preliminary`)**

## 1. 결론

이번 개정으로 TMC-49 액체의 밀도, 비열, 점도, 열전도도는 출처를 알 수 없는 상수나 다항식이 아니라 제조사 TDS의 온도별 시험표를 OpenFOAM에 직접 넣도록 변경했다. 비등점, 잠열, 분자량, 액체-증기 표면장력도 제조사 직접값으로 교정했다.

따라서 현재 설정은 **물성 출처를 추적할 수 있는 데이터셋 생성용 기준 설정**으로 사용할 수 있다. 다만 TMC-49 증기 수송물성은 유사유체 모델값이고, Lee 상변화 계수, TMC-49-물 직접 계면장력, 정밀 형상과 열전대 좌표도 아직 확정되지 않았다. 따라서 절대 기포율, 기포 소멸거리, 국소 열전달계수를 검증 완료값으로 주장해서는 안 된다.

현재 모델이 답할 수 있는 범위는 다음과 같다.

- 실험 장치와 동일한 층 구성에서의 온도장·상분율·유동 변화 경향
- 냉각수 조건, 발열량, 격자 크기 변화에 따른 상대 비교
- TMC-49 포화온도 근처 유지 여부와 전체 에너지 수지
- 향후 실험 데이터 보정에 사용할 OpenFOAM 기반 데이터 생성 파이프라인의 타당성

현재 모델만으로 확정할 수 없는 범위는 다음과 같다.

- 실험 보정 없는 절대 기포 크기·개수·체류시간
- Lee 계수에 민감한 증발량·응축거리의 정량값
- 실제 코일 핀과 CPU 표면 형상을 생략한 국소 열전달계수
- 배치 물성 확인 전 TMC-49 비열의 최종 확정값

## 2. 근거 등급

설정 JSON과 문서에는 다음 등급을 구분해 기록한다.

| 등급 | 의미 | 사용 원칙 |
|---|---|---|
| `direct` | 해당 TMC-49 제품 또는 교수님 실험의 직접 측정·명시값 | 기준값으로 사용 |
| `derived` | 직접값의 단위 변환, 보간, 물리식 계산 | 계산식과 입력값을 함께 기록 |
| `analogous` | 구조·비등특성이 가까운 유사 유체의 실험값 | 민감도용 대입값이며 직접값으로 표현 금지 |
| `calibration_required` | 모델 계수로서 대상 장치 실험 보정이 필요 | 단일값 확정 금지, 민감도 후 보정 |
| `unresolved` | 직접·유사 근거를 아직 확보하지 못함 | 정량 검증 제한을 명시 |

근거 우선순위는 `TMC-49 제조사 시험표 > 교수님 제공자료·원시계측 > 동일 CAS 공인 자료 > 동일 유체 논문 > 유사 유체 실험 > 수치 모델 가정`이다.

## 3. TMC-49 직접 적용값

### 3.1 상수 및 포화 조건

| Config 항목 | 적용값 | 등급 | 근거 및 처리 |
|---|---:|---|---|
| `dielectric_fluid.CAS` | 2070-70-4 | `direct` | 제조사 제품 페이지와 NIST Chemistry WebBook 교차 확인 |
| `Tsat_C` | 47.0 °C | `direct` | 제조사 공식 TDS Rev.4·현재 제품 페이지, 교수님 실험의 46.7~47.8 °C 포화 유지 관측 |
| `h_fg_J_kg` | 93,220 J/kg | `direct` | 제조사 93.22 kJ/kg를 SI 단위로 변환 |
| `molWeight` | 300.05 g/mol | `direct` | 제조사 직접값; NIST 300.0450 g/mol과 일치 |
| `sigma_lv` | 0.01144 N/m | `direct` | 제조사 25 °C 값 11.44 mN/m를 SI 단위로 변환 |

제조사 공식 TDS Rev.4(문서번호 `DS-ENG-20250630-4900-Rev4`, ©2026)와 현재 제품 페이지는 모두 비등점 47 °C를 명시한다. 교수님 실험에서도 TMC-49가 약 47 °C에서 유지된다. 구 유통사 보관본의 첫 페이지에는 49 °C가 적혀 있으나 같은 문서의 ASTM D86 비등 범위는 46.7~48.9 °C이므로, 모델은 최신 공식값 47 °C를 사용한다. 버전 차이는 삭제하지 않고 충돌 이력으로 남긴다.

### 3.2 온도별 액체 물성

제조사 TDS의 시험표를 JSON `property_tables`에 그대로 저장하고 OpenFOAM `icoTabulated`, `hTabulated`, `tabulated` 물성으로 생성한다. 표 내부만 선형보간하며 표 밖에서는 가장 가까운 시험값으로 고정한다. 임의 다항식 외삽은 하지 않는다.

| 온도 (°C) | 밀도 (kg/m³) | 비열 (J/kg·K) | 열전도도 (W/m·K) |
|---:|---:|---:|---:|
| -20 | 1748.8 | 705 | 0.072 |
| 0 | 1683.6 | 729 | 0.069 |
| 20 | 1618.4 | 754 | 0.066 |
| 40 | 1553.2 | 778 | 0.063 |
| 60 | 1488.0 | 802 | 0.060 |
| 80 | 1422.7 | 826 | 0.057 |
| 100 | 1357.5 | 850 | 0.054 |

동점도는 제조사 ASTM D445 표를 사용한다.

| 온도 (°C) | 동점도 (cSt) |
|---:|---:|
| 16 | 0.395 |
| 18 | 0.387 |
| 21 | 0.376 |
| 24 | 0.365 |
| 27 | 0.354 |
| 29 | 0.348 |
| 32 | 0.338 |
| 35 | 0.328 |
| 40 | 0.312 |
| 45 | 0.297 |

OpenFOAM이 요구하는 동점성계수 `mu`는 같은 TDS의 밀도를 해당 온도에 선형보간한 뒤 `mu = nu × rho`로 계산했다. 이 변환은 `derived`이며 원 동점도 표와 변환 결과를 JSON에 함께 남겼다.

47 °C에서 생성기에 적용되는 대표값은 다음과 같다.

| 물성 | 47 °C 적용값 | 처리 |
|---|---:|---|
| 밀도 | 1530.38 kg/m³ | 40~60 °C 표 선형보간 |
| 비열 | 786.4 J/kg·K | 40~60 °C 표 선형보간 |
| 열전도도 | 0.06195 W/m·K | 40~60 °C 표 선형보간 |
| 점도 | 0.00045646 Pa·s | 점도 시험 상한 45 °C 값으로 고정 |

45 °C를 넘는 점도는 검증된 시험값이 없으므로 47 °C까지 추세를 임의 외삽하지 않았다. 후속 TDS 또는 배치 시험값이 확보되면 47 °C 점도점을 추가한다.

### 3.3 상단 DI수 물성

DI수는 0.1 MPa 조건의 IAPWS 표준 상관식으로 다시 계산했다. 밀도와 비열은 IAPWS-95 계열, 점도는 IAPWS R12-08, 열전도도는 IAPWS R15-11을 따르는 SR6-08(2011) 액체수 상관식을 사용한다. 설정의 0~100 °C 표는 `standard_correlation`으로 기록했으며 OpenFOAM은 해당 온도표를 직접 보간한다.

현재 운전 대표온도 30 °C의 적용값은 밀도 995.64882 kg/m³, 비열 4179.899 J/kg·K, 점도 0.0007972062 Pa·s, 열전도도 0.61437701 W/m·K이다. 기존 표와의 차이는 대부분 1% 이내지만 출처가 불명확한 반올림표를 계속 쓰지 않기 위해 교체했다. 공식 기준: https://www.iapws.org/relguide/LiquidWater.html

## 4. 상충 근거와 채택 판단

### 4.1 TMC-49 비열

동일 CAS 2070-70-4에 대해 NIST/IUPAC 비열 비평 자료 Table 21.51은 순도 99%, 293.1~313.1 K, 2개 측정점의 회귀계수를 제공한다. 논문의 식 `C/R = A1 + A2(T/100)`과 `A1=1.87886`, `A2=6.13480`을 적용하면 약 550~584 J/kg·K이다. TMC 제조사 TDS는 같은 온도 범위에서 약 754~778 J/kg·K를 제시하고, 다른 동일 CAS 공급사는 25 °C에서 1279 J/kg·K를 제시한다. 2024년 공개 FCM-47 분무냉각 논문도 액체 비열 1.26 kJ/kg·K, 잠열 121.7 kJ/kg을 제시한다. 동일 CAS 공개값의 산포가 매우 크다.

현재는 다음 이유로 제조사값을 채택했다.

- 교수님 제공 TMC-49 Property 표와 제조사 TDS가 동일한 754 J/kg·K 대표값을 사용한다.
- 실제 구매·운전 대상은 일반 화합물명이 아니라 TMC-49 상용 제품이다.
- NIST 회귀는 두 점뿐이며 불확실성 등급 V로 제시되어 있다.

이 판단은 제조사값이 절대적으로 옳다는 뜻이 아니다. NIST 값은 TMC 표보다 약 25~27% 낮고 다른 공급사 및 FCM-47 논문값은 약 65~67% 높다. 비열은 과도 가열속도와 축열량에 직접 영향을 주므로, 사용 배치의 CoA 또는 DSC 측정 전까지 핵심 불확실성으로 유지한다. 1차 민감도는 최소한 TMC 제조사 표와 NIST 회귀표 두 가지로 나눠 수행해야 한다. 별도 공급사 자료: https://www.fluorochemie.com/product/perfluoro4-methylpent-2-ene-tpd-hfpd, FCM-47 공개 논문: https://doi.org/10.1088/1742-6596/2683/1/012030

### 4.2 비등점 47 °C와 49 °C

- 제조사 공식 TDS Rev.4 및 현재 제품 페이지: 47 °C
- 구 유통사 보관본 첫 페이지: 49 °C
- 공식 Rev.4 ASTM D86 비등 범위: 초기 116 °F(46.7 °C), 주 분획 118 °F(47.8 °C), 99% 회수 120 °F(48.9 °C)
- 교수님 실험: TMC-49 온도 약 46.7~47.8 °C 유지

따라서 현재 모델은 47 °C를 채택한다. 동일 배치의 대기압 비등곡선 또는 CoA를 받으면 최종 확정한다.

## 5. 유사 유체 문헌을 사용한 항목

### 5.1 TMC-49-물 계면장력 `sigma_lw`

TMC-49 직접 측정값을 찾지 못했다. 물과의 상분리, 탄소수, 낮은 비등점과 표면장력이 가까운 perfluorohexane(C6F14, PFH/FC-72)을 유사 유체로 선택했다.

- PFH-물 계면장력 실험값 약 56 mN/m
- 2020년 연구는 물-perfluoroalkane 계면장력을 273~340 K에서 직접 측정해 온도 의존성을 확인함
- 적용값: `sigma_lw = 0.0560 N/m`
- 등급: `analogous`

TMC-49는 C6F12이고 PFH는 C6F14이므로 동일 물질이 아니다. 이 값은 과거 근거 없는 0.045 N/m보다 추적 가능한 대입값이지만, TMC-49 직접값으로 표현해서는 안 된다.

### 5.2 TMC-49 증기-물 계면장력 `sigma_vw`

포화 PFH 증기가 물 표면장력을 20 °C에서 약 66.7 mN/m로 낮춘 실험을 유사 기준으로 사용했다.

- 적용값: `sigma_vw = 0.0667 N/m`
- 등급: `analogous`
- 근거: Chernyshev and Skliar, *Soft Matter* 2014, DOI 10.1039/C3SM52289J

`sigma_lv=0.01144`, `sigma_lw=0.0560`, `sigma_vw=0.0667 N/m` 조합은 3상 계면장력 삼각조건을 만족한다. 다만 온도와 화학종이 완전히 같지 않으므로 기포·접촉선 결과의 민감도 항목으로 취급한다.

### 5.3 TMC-49 증기 `cp/mu/kappa`

TMC-49와 동일 화학종인 FCM-47의 2026년 액적 연구는 이 유체가 NIST REFPROP에 포함되지 않았고 기초 물성이 부족하다고 명시한다. 제조사 Rev.4와 SDS에도 증기 비열·점도·열전도도는 없다. 따라서 직접값인 것처럼 기존 수치를 유지하지 않고, 가장 가까운 공개 유사유체인 n-perfluorohexane(C6F14)의 추적 가능한 모델값으로 교체했다.

- 기준 상태: 320.15 K(47 °C) 포화증기
- `cp = 858.9821 J/kg·K`: CoolProp 8.0.0의 n-perfluorohexane Helmholtz EOS
- `mu = 1.15262×10⁻⁵ Pa·s`: NIST IR 8209의 Lennard-Jones `epsilon/k=160 K`, `sigma=0.805 nm`, Chapman-Enskog/Neufeld 식
- `kappa = 0.0131966 W/m·K`: 같은 NIST 문서의 Eucken 희박기체 식과 위 `cp`, `mu`
- 등급: 세 값 모두 `analogous`

기존 증기 점도 `1.0926×10⁻⁴ Pa·s`는 근거를 확인하지 못했고 NIST 유사유체 계산보다 약 9.5배 컸다. 이번 개정에서 제거했다. 이 교체는 증기 유동 저항과 응축부 열전달에 영향을 줄 수 있으므로 신규 프로젝트에서만 사용하며, TMC-49 증기 직접값을 확보하면 반드시 다시 교체한다. 근거: https://doi.org/10.6028/NIST.IR.8209, https://coolprop.org/fluid_properties/fluids/n-Perfluorohexane.html

## 6. 동일 유체 및 유사 유체 연구가 주는 범위

### 6.1 TMC-49 동일 유체 실험

1. Ga et al., 2026, TMC-49와 SF33을 11 mm 2상 폐쇄형 thermosyphon에서 비교했다. TMC-49의 최소 열저항은 약 0.19 K/W, 최대 증발부 HTC는 약 1670 W/m²K였다. 이는 TMC-49가 실제 상변화 열수송 유체로 기능한다는 외부 실험 근거지만, 본 수조의 코일·CPU 경계계수로 직접 대입할 수는 없다. DOI: https://doi.org/10.1016/j.icheatmasstransfer.2026.112165
2. 2026년 평활 알루미늄 표면 pool boiling 비교 연구는 FC-72, Novec 649, HFE-7100, TMC-49, SF33을 동일 조건에서 시험했고 TMC-49가 FC-72와 유사한 비등 성능을 보였다고 보고한다. 데이터와 유체별 Rohsenow 계수는 논문 또는 저자 원자료 수령 후 벽비등 모델 검증에 사용할 수 있다. DOI: https://doi.org/10.1016/j.ijft.2026.101684
3. 2025년 TMC-49 실리콘 칩 실험은 평활 실리콘의 CHF 약 85 kW/m²와 금속 micropillar 표면의 CHF 약 379 kW/m²를 보고한다. 현재 모델 CPU 평균 열유속 약 72 kW/m²는 평활 실리콘 CHF와 가까우므로 실제 CPU 표면 구조·젖음성·발열분포를 확인하기 전 과도한 안전여유를 주장할 수 없다. DOI: https://doi.org/10.1109/THERMINIC65879.2025.11216872
4. 2026년 동일 화학종 FCM-47 액적 증발 연구는 이 유체가 NIST REFPROP 같은 표준 열역학 데이터베이스에 아직 포함되지 않아 기초 물성 공백이 있다고 명시한다. 따라서 증기 `cp/mu/kappa`는 TMC-49 직접값으로 표현하지 않고 C6F14 유사모델값(`analogous`)으로 명시했으며, 직접값 확보 전 정량 한계를 유지한다. DOI: https://doi.org/10.1016/j.icheatmasstransfer.2026.111278

### 6.2 PFH 유사 유체 실험

PFH는 TMC-49와 분자량·조성이 다르므로 직접 물성 대체재가 아니다. 다만 57 °C 부근에서 밀도, 잠열, 열전도도, 표면장력의 크기가 유사해 계면장력의 1차 유사 기준으로 사용했다. PFH의 57 °C 실험 물성은 밀도 1620.9 kg/m³, 잠열 83.54 kJ/kg, 비열 1106.8 J/kg·K, 열전도도 0.05416 W/m·K, 점도 0.0004128 Pa·s, 표면장력 0.00843 N/m로 보고되어 있다. 원문: https://www.jasma.info/journal/wp-content/uploads/sites/2/2016/01/2016_p3301061.pdf

## 7. Lee 상변화 계수

OpenFOAM v2312의 Lee 모델은 다음 형태다.

`mDot = C × rho × alpha × (T - Tactivate) / Tactivate`

공식 소스는 `C`를 물성이 아니라 model constant로 정의하며, 양수는 활성온도 이상에서 증발, 음수는 활성온도 이하에서 응축을 뜻한다. 공식 소스: https://api.openfoam.com/2312/Lee_8H_source.html

현재 설정의 `evap_C=50 1/s`, `cond_C=-50 1/s`는 TMC-49 실험으로 확정된 값이 아니다. 2025년 실험 검증 연구도 Lee 계수는 장치, 포화압력, 온도 조건에 따라 달라지며 실험 보정이 필요하다고 보고한다. 그 연구의 물 계수값을 TMC-49 수조에 옮기지 않았다. DOI: https://doi.org/10.1016/j.rineng.2025.104430

따라서 두 계수는 `calibration_required`로 저장하며 다음 절차로 보정한다.

1. 동일 격자·시간간격에서 `C=5/50/500 1/s` 민감도 계산
2. 교수님 T1~T6 온도 시계열, 증발량 또는 액면감소량, 기포 영상에서 보정 지표 확보
3. 포화온도 오차, 증기 체적, 응축거리, 에너지 수지를 동시에 비교
4. 격자 3 mm와 2 mm에서 보정값의 망 독립성 확인
5. 한 조건에서 맞춘 계수를 다른 유량·냉각수 온도 조건으로 교차 검증

## 8. 아직 확정하지 못한 값

| 항목 | 현재 처리 | 결과 영향 | 필요한 자료 |
|---|---|---|---|
| `vapour.cp/mu/kappa` | C6F14 유사모델값, `analogous` | 증기 온도확산, 속도, 응축 열전달 | TMC-49 제조사 증기 물성 또는 검증된 전용 EOS/수송모델 |
| `phase_change.evap_C/cond_C` | ±50, `calibration_required` | 증발량, 응축거리, 기포 체류 | UDF 원본, T1~T6, 액면·기포 시계열 |
| `sigma_lw/sigma_vw` | PFH 유사값, `analogous` | 기포형상, 계면 곡률, 접촉선 | TMC-49-물 pendant/drop tensiometry |
| 보드·CPU 좌표/치수 | 발표자료 치수 표기 사진 판독. 2026-08-23 보드 y=0~300 mm, CPU y=90~130 mm로 수정 | 국소 유동·열유속 | CAD, 실제 CPU IHS 정밀 좌표·z 이격 |
| 코일 형상·전열면적 | 상자 경계와 UA 모델 | 코일 근처 유동·국소 열전달 | 코일 관경·핀·피치·CAD |
| T1~T4 좌표 | 사진 판독 근사 | 지점 온도 비교 | mm 단위 설치 도면 |
| 조건별 `h_meas`, `UA` | 발표 그래프 판독·보간 포함 | 상부 수온·열배출 | 실험 원표 |
| 초기 TMC/DI수 온도 | 정상운전 근사 | 초기 과도시간 | 각 실험 시작 시각 원시값 |
| 상단 공기 200 mm | 격자에서 생략, top 개방 경계 | 증기 배출·압력·응축량 | 공기 포함 4상 또는 압축성 headspace 모델 검증 |
| 난류 | `laminar/Stokes` 가정 | 기포유도 혼합·열전달 | 속도장/PIV 또는 laminar-난류 민감도 |
| CPU 표면 발열 | 총 265 W를 두 footprint에 균일 분배 | 국소 벽온·기포 발생점 | CPU별 시간전력과 IHS 국소 발열지도 |
| 코일 UA 구현 | 상자형 대류경계, 3 mm에서 실효 19.41 W/K | 열배출·상부 수온 | 실제 코일 CAD/전열면적; 현재 목표 21.70 W/K는 격자 상한 21.57 W/K를 0.6% 초과 |
| 벽면 젖음성 | 접촉각·동적 젖음성 미보정 | 벽 기포 핵생성·접촉선 | TMC-49/DI수와 실제 재질의 접촉각 측정 |

이 목록의 값은 숨기지 않는다. `build_case.py --check`와 실제 생성 때 `research_preliminary`, `unresolved`, `calibration_required`, `analogous` 경고를 출력한다.

## 9. 설정 변경 내용

### 물성 생성기

- `dielectric_fluid.property_tables`를 검증하고 OpenFOAM 표 물성으로 직접 생성
- 표 온도는 엄격한 오름차순, 모든 값은 양수, 길이는 2점 이상으로 강제
- 표 내부 선형보간, 표 밖 끝값 고정
- 신규 설정에서는 과거 `rho_poly/cp_poly/mu_poly/kappa_poly` 제거
- 과거 프로젝트 스냅샷은 호환 목적으로 기존 다항식도 읽을 수 있게 유지
- 설정 생성 전 근거 상태를 콘솔에 출력

### CFD Studio 설정

- 신규 TMC-49 기본값: 47 °C, 93,220 J/kg, 300.05 g/mol, 0.01144 N/m
- 설정 요약값은 `property_tables`에서 현재 기준온도 값을 보간해 표시
- 실행용 저장 설정 JSON 전체에 출처·상충근거·검증상태 기록

### 재현성 원칙

기존 프로젝트의 `Project/<프로젝트명>/case_config.json`은 과거 계산에 실제 사용된 입력 기록이므로 자동 수정하지 않았다. 이는 과거 값이 물리적으로 옳다는 뜻이 아니라 **그 결과가 어떤 입력으로 생성되었는지 보존한다는 뜻**이다.

새 물성으로 계산하려면 CFD Studio에서 `이권영 교수님 기준` 또는 교정된 저장 설정을 선택하고 새 프로젝트를 0초부터 생성해야 한다. 기존 프로젝트 재개는 과거 물성과 새 물성을 섞게 되므로 허용하지 않는다. 과거 결과는 `legacy_pre_evidence_baseline`, 신규 결과는 `research_preliminary_20260822`로 구분해 비교한다.

## 10. 검증 실행 순서

### 단계 A: 물성·수치 확인

1. `python3 tools/build_case.py --check`
2. 생성된 `thermophysicalProperties.liquid`에서 320.15 K 대표값 확인
3. OpenFOAM 사전 파싱, blockMesh, setFields가 오류 없이 통과하는지 확인
4. 0.01~0.1 s 짧은 구간에서 질량·에너지·Courant 수 확인

### 단계 B: 물성 민감도

1. 제조사 비열표 기준
2. NIST 동일 CAS 비열 회귀 기준
3. 계면장력 PFH 유사값 ±20%
4. 증기 수송물성 후보 범위

### 단계 C: 상변화 보정

1. Lee `C=5/50/500 1/s`
2. 3 mm 격자에서 후보 축소
3. 2 mm 격자에서 재검증
4. 한 실험 조건으로 보정하고 나머지 조건으로 교차 검증

### 단계 D: 실험 대조

- TMC-49 포화온도: 46.7~47.8 °C
- T1~T6 온도 시계열
- CPU package 전력 합: 약 265.3 W
- 냉각수 입·출구 온도와 유량
- 액면 변화 또는 총 증발·응축량
- 기포 발생 위치, 계면 통과량, 응축거리
- CPU 입력열과 코일 제거열의 에너지 폐합

## 11. PPT 반영용 핵심 문장

### 연구 기여

유료 CFD 없이 OpenFOAM으로 이중 액침 냉각 수조의 3상 상변화, 온도장, 기포 거동, 유동장을 계산하고 프로젝트별 데이터셋으로 변환하는 독립 소프트웨어 체계를 구축했다. 이번 개정에서는 TMC-49 물성을 제조사 온도별 시험표에 직접 연결하고 모든 설정값을 `직접값/유도값/유사값/보정필요/미확정`으로 구분해 재현성과 검증 가능성을 높였다.

### 현재 성과

- 교수님 실험의 수조, 2개 액체층, CPU 발열, 상부 코일 냉각 구조를 3D 모델로 구성
- TMC-49 상변화와 DI수 열수송을 OpenFOAM 3상 모델로 계산
- 제조사 물성표를 온도별로 직접 반영한 근거 추적형 Config 구축
- 프로젝트 생성·재개·증분 시각화·Raw 데이터 분리 저장을 CFD Studio로 통합
- 하드웨어별 MPI/CPU 자원 자동 조정과 중단·재개·오류 복구 적용

### 한계와 다음 단계

현재 모델은 연구용 예비 모델이며, TMC-49 직접 증기 물성, Lee 상변화 계수, 직접 계면장력, 실제 코일·CPU 형상과 열전대 좌표가 추가로 필요하다. 이 항목들을 실험 원시데이터로 보정하고 독립 조건에 교차 검증하면, 자체 CFD 데이터셋의 정량 신뢰도를 단계적으로 확보할 수 있다.

## 12. 출처

### TMC-49 직접 자료

1. TMC Industries, TMC-49 product page: https://tmcindustries.com/products/tmc-49
2. TMC Industries, TMC-49 Technical Data Sheet Rev.4: https://tmcindustries.com/cdn/shop/files/TMC-49-TDS-Rev4.pdf?v=5304461421983960090
3. 공식 Rev.4 로컬 보관본: `문서/근거자료/TMC-49/TMC-49_TDS_Rev4_2026.pdf`
4. 구판 충돌 이력: https://yottadeft.com/wp-content/uploads/2025/02/TMC-49_TDS_7.pdf, 로컬 `문서/근거자료/TMC-49/TMC-49_TDS_7.pdf`
5. NIST Chemistry WebBook, CAS 2070-70-4: https://webbook.nist.gov/cgi/inchi?ID=C2070704&Units=SI
6. Zábranský, Růžička, Domalski, *Heat Capacity of Liquids: Critical Review and Recommended Values. Supplement I*, DOI: https://doi.org/10.1063/1.1407866
7. NIST 로컬 보관본: `문서/근거자료/TMC-49/NIST_Heat_Capacity_of_Liquids_Supplement_I_2002.pdf`

### 동일·유사 유체 연구

1. Ga et al., TMC-49 thermosyphon experiment: https://doi.org/10.1016/j.icheatmasstransfer.2026.112165
2. TMC-49 dielectric-fluid pool boiling comparison: https://doi.org/10.1016/j.ijft.2026.101684
3. TMC-49 silicon/micropillar pool boiling: https://doi.org/10.1109/THERMINIC65879.2025.11216872
4. Water-perfluoroalkane interfacial tension vs temperature: https://doi.org/10.1016/j.molliq.2020.113385
5. PFH-water interfacial tension: https://doi.org/10.1021/la00085a043
6. Water surface tension under saturated PFH vapor: https://doi.org/10.1039/C3SM52289J
7. PFH thermophysical property experiment: https://www.jasma.info/journal/wp-content/uploads/sites/2/2016/01/2016_p3301061.pdf
8. 동일 화학종 FCM-47 액적 증발 및 데이터베이스 공백: https://doi.org/10.1016/j.icheatmasstransfer.2026.111278
9. 동일 CAS 별도 공급사 물성표: https://www.fluorochemie.com/product/perfluoro4-methylpent-2-ene-tpd-hfpd
10. Fu et al., FCM-47 분무냉각 공개 원문: https://doi.org/10.1088/1742-6596/2683/1/012030, 로컬 `문서/근거자료/TMC-49/FCM-47_Fu_2024_IOP_012030.pdf`
11. NIST IR 8209, perfluorohexane 수송물성 모델: https://doi.org/10.6028/NIST.IR.8209, 로컬 `문서/근거자료/유사유체/NIST_IR_8209_transport.pdf`
12. CoolProp n-perfluorohexane 공개 EOS: https://coolprop.org/fluid_properties/fluids/n-Perfluorohexane.html

### 모델 근거

1. OpenFOAM v2312 Lee model source: https://api.openfoam.com/2312/Lee_8H_source.html
2. Lee coefficient experimental calibration study: https://doi.org/10.1016/j.rineng.2025.104430
3. IAPWS SR6-08(2011), liquid-water properties at 0.1 MPa: https://www.iapws.org/relguide/LiquidWater.html
4. IAPWS-95 thermodynamic formulation: https://iapws.org/documents/release/IAPWS-95
5. IAPWS R12-08 viscosity formulation: https://iapws.org/documents/release/viscosity
6. IAPWS R15-11 thermal-conductivity formulation: https://www.iapws.org/relguide/ThCond.html
7. 로컬 보관본: `문서/근거자료/IAPWS/IAPWS95-2018.pdf`, `IAPWS_R12-08_viscosity.pdf`, `IAPWS_R15-11_thermal_conductivity.pdf`, `IAPWS_SR6-08_LiquidWater_0.1MPa.pdf`

### 교수님 제공자료

1. `협력랩자료/26-1 조경제.pptx`
2. `협력랩자료/3. New Data/1. Steady State/hwinfo/hwinfo_pump3_ver3.0.CSV`
3. `협력랩자료/경제형_데이터PPT_요점.md`
