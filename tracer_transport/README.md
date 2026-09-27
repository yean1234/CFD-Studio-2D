# 정규화 가스 추적자 수송: 훈증 모듈의 수치 검증 기반

박공지붕 저장동과 수송 솔버를 연결한 별도 실행 경로, ClO₂ 공기 중 확산 입력, 1차 소멸·체적 평균 교환 항 및 실측 비교 도구는 [새 기능의 근거·사용법·남은 제한](../docs/warehouse-clo2-transport-20260927.md)을 참고하세요. 아래 설명은 기존 정규화 예제 경로에 적용됩니다.

현재 구현 범위와 이번 재검사 범위는 [모델 구분·검토 기록](../docs/concentration-module-review-20260927.md)을 우선 확인하세요. 아래 PH3 표기는 과거 연구 계약의 메타데이터이며 PH3 또는 ClO2 물성을 계산했다는 뜻이 아닙니다. 기존 입력·결과의 재현성을 위해 과거 파일은 소급 변경하지 않습니다.

기존 액침냉각·저장고 데이터를 보존하는 수송 연구 모듈입니다. 실제 약제 공급·살포, 해충 행동, 사망률, 설계 최적화를 구현하지 않습니다. 계산은 별도 실행기에서 수행하며, 결과는 **기존 Studio 프로젝트 목록·3D Viewer·재생 타임라인**에 연결했습니다. 메인 UI에서의 훈증 케이스 생성·솔버 실행 버튼은 아직 연결하지 않았습니다.

추가로 [가역 흡착·탈착의 수치검증](SORPTION.md)을 구현했습니다. 현재 B단계는 확산과 정규화 선형 교환까지이며 PH3-쌀 물성 검증과 구분합니다.

[기존 정적 단면도의 원본 대조 결과](VISUALIZATION_CHECK.md), [추가된 3D 재생·공급 시작·정상상태 종료](SUPPLY_AND_3D.md)를 구분해 확인하세요.

[실제 실행 결과](VERIFICATION.md). 치수·공극률·확산계수·초기장·종료/출력 간격은 benchmark.json에서 관리합니다. 수정한 파일은 --config로 지정할 수 있습니다. 검증 묶음의 격자 및 시간 세분화 수준은 run.py에 명시되어 있으며 실물 운용 프리셋이 아닙니다.

[PH3 연구 계약·사전 조건표·단계별 통과 기준·실험 비교 절차·재시작 사용법](RESEARCH_PROTOCOL.md)을 확인하세요. 초기값과 공급/벽/시트/누설 명세, 허용오차와 입력 해시는 계산 전에 각 사례에 기록됩니다. 전체 3차원 농도장은 출력 간격마다 보존합니다.

## 방정식과 범위

`d(eps*C)/dt + div(U_s*C) = div(K*grad(C))`

- C: 공극 내 정규화 농도 C/C_ref. 벌크 농도는 eps*C.
- U_s: 겉보기 유속 m/s. 공극 유속을 입력하는 인터페이스가 아닙니다.
- K: 벌크 면적 기준 확산 전달계수 m2/s. 다공성 K는 이미 유효값이며 공극률을 다시 곱하지 않습니다.
- 질량 대용량은 sum(eps*C*V), 단위 C_ref*m3. 실제 kg이나 ppm으로 보고하지 않습니다.
- 기본 사례는 등온, 정지 공기, 무흡착, 밀폐 경계입니다. 선택적인 선형 흡착·탈착 식과 총질량 수지는 SORPTION.md에 별도 명시합니다.
- 공간은 직교 균일격자, 시간은 implicit Euler, 내부면 K는 조화평균입니다. 전 셀 농도를 잘라내지 않고 음수·질량수지 오류를 실패로 처리합니다.

OpenFOAM v2312의 유한체적 연산자를 사용하는 porousTracerFoam을 빌드합니다. 기존 scalarTransportFoam은 설치와 소스를 확인했지만 공극 저장항을 명시적으로 분리하기 위해 별도 실행파일을 사용합니다. 새 저장동 경로를 위해 porousTracerFoam에 선택적인 1차 제거 항을 추가했으며 기존 정규화 입력·결과는 수정하지 않았습니다. 대류항은 코드에 있지만 이번 검증은 U=0이며 유동장·Darcy 저항 계산은 미구현입니다.

## 재현 (WSL bash, 저장소 루트)

```bash
source /usr/lib/openfoam/openfoam2312/etc/bashrc
python3 -m venv /tmp/cfd-tracer-env
/tmp/cfd-tracer-env/bin/pip install -r tracer_transport/requirements.txt
(cd tracer_transport/solver && wmake)
/tmp/cfd-tracer-env/bin/python -m tracer_transport.run --output "$HOME/cfd_tracer_runs/new_verification"
/tmp/cfd-tracer-env/bin/python -m tracer_transport.report "$HOME/cfd_tracer_runs/new_verification"
```

설치 위치가 다른 PC에서는 실제 OpenFOAM bashrc 경로를 사용합니다. OpenFOAM v2312, C++ 컴파일러와 wmake, /usr/bin/time이 필요합니다. 현재 검증은 직렬 CPU 실행이며 MPI/GPU 지원을 주장하지 않습니다. 출력 폴더가 이미 있으면 실행을 거부합니다. Chrome이나 기존 Studio 프로세스를 조작하지 않습니다.

## 사례와 산출물

- uniform: 닫힌 균일장 유지.
- diffusion: C=1+0.5*cos(pi*x)*exp(-D*pi^2*t) 해석해와 비교.
- porous: x=0.25~0.75 m의 다공성 슬래브, 양쪽 자유 공기. 실제 포대 배치가 아닙니다.
- 확산: 격자 20/40/80 및 시간간격 0.01/0.005/0.0025 s 독립 검사.
- 다공성: 격자·시간을 함께 줄이는 기준선. 독립적인 시간·공간 수렴 검증을 대체하지 않습니다.
- 각 사례: config.json, OpenFOAM 격자·장, 실행 로그, checks.json, mass_balance.csv, concentration.npz.
- 묶음: environment.json, summary.json, integration_checks.json, 농도 단면·고정점·질량수지 PNG.

## 사용자 파라미터 단일 실행

```bash
/tmp/cfd-tracer-env/bin/python -m tracer_transport.run --config tracer_transport/block3d_test.json --case porous --nx 40 --dt .005 --output "$HOME/cfd_tracer_runs/block3d_new"
```

block3d_test.json은 실제 선정 저장고가 아닌 3D 구획 입력의 수치시험입니다. lengths_m, transverse_cells, porous_boxes_m의 min/max로 자유 공기 안의 다공성 블록들을 지정합니다. 겹치는 블록, 격자면과 맞지 않는 경계는 실패 처리하며 형상을 몰래 반올림하지 않습니다. 기존 report 명령은 9개 검증 사례 묶음용이며 단일 실행에는 적용하지 않습니다. 단일 사례에도 농도 NPZ, 영역 태그, 로그와 수지 CSV가 생성됩니다.

이 입력은 직육면체 폐쇄계·동일 재료 다공성 블록과 선택적 선형 교환 모델을 지원합니다. 임의 CAD, 고체 팔레트, 누설·비영 유동 또는 실제 훈증제 모델을 범용 지원한다고 해석하면 안 됩니다. 단일 사례 그림은 python -m tracer_transport.plot_case <case>로 생성할 수 있습니다.

## 위치·시간 조회

```python
from tracer_transport.sample import ConcentrationField
f = ConcentrationField('/path/to/case/concentration.npz')
result = f.sample_concentration([0.4, 0.1, 0.1], 0.35, region_id=1)
```

원점 (0,0,0), 좌표 m, 시간 s. region 0=자유 공기, 1=다공성 공극. 공간은 포함 셀의 일정값, 시간은 선형 보간입니다. 외부 위치·시간, NaN, 영역 불일치는 valid=false를 반환합니다. 공간 최근접 보간으로 벽을 넘지 않습니다. 현재 격자는 내부 고체벽이 없는 직육면체이며 실제 포대·팔레트 고체 판정은 아직 구현하지 않았습니다. 균일장에 대한 인공 이동 경로의 적분은 수치 인터페이스 시험이며 곤충 행동·독성 지표가 아닙니다.

## 근거와 연구 가정

| 항목 | 분류 | 적용 |
|---|---|---|
| OpenFOAM v2312 scalarTransportFoam 소스 | 설치본 확인 | 유한체적 수송 방정식 구성 참고 |
| Agrafioti et al. 2021, DOI 10.1016/j.compag.2021.106087 | 확보된 본문 확인 | 농도장·흡착·열조건을 별개로 다룰 필요성 참고. 계수 미전용 |
| Arora 2025, DOI 10.1016/j.jspr.2025.102584 | 로컬 조사자료: 미리보기만 확보 | 실험 치수·원시 시계열을 확보했다고 주장하지 않음 |
| Arora 관련 2021 학회자료 | 로컬 자료목록 확인 | 5톤·100포대는 배경 정보. 현재 격자와 일치시키지 않음 |
| 1 x 0.2 x 0.2 m, 슬래브 범위, eps=0.4 | 수치시험 연구 가정 | 실측 쌀 적재 치수·공극률 아님 |
| D=0.01, K_porous=0.002 m2/s | 수치시험 연구 가정 | 실제 훈증제·쌀 물성 아님 |
| C0, U=0, 1 s 종료, 무플럭스 | 수치시험 연구 가정 | 운용 처방·실험 재현 아님 |

## 후속 단계

검증된 외부 유동장 연결 및 대류 시험, 독립적인 다공성 시간 수렴, 포대 막 저항, 시트/이음부 경계, 팔레트와 매개변수형 포대 배치, Studio의 신규 설정·계산 실행 버튼 연결은 후속 범위입니다. 프로젝트/Viewer에는 C와 Q를 별도 필드로 연결했습니다. 쌀·가스 물성 및 치수는 출처 확보 전 실물 계산에 적용하지 않습니다.

solver/porousTracerFoam.C는 OpenFOAM 연결용 GPL-3.0-or-later 코드입니다. 원본 논문·비공개 실험자료는 저장소에 복사하지 않습니다.
