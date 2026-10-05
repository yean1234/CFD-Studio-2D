# TMC-49 이중 액침 실험 재현 — 전체 수조 OpenFOAM 케이스 (3D 실험형)

> 2026-08-23 형상 근거 개정: 이권영 교수님 발표자료의 치수 표기 수조 사진에 맞춰 보드를 바닥(y=0~300 mm)에 붙이고 CPU 발열면도 y=90~130 mm로 40 mm 내렸다. 기존 프로젝트의 `case_config.json`은 당시 계산 좌표를 보존하며, 수정 형상은 새 프로젝트부터 적용한다.

목적 — **이권영 교수님 연구실의 실험 자체**를 CFD로 재현: 아래층 유전체(TMC-49)에서 CPU 발열로 끓고,
계면에서 응축하며, 위층 액체의 코일이 열을 냉각수로 내보내는 2유체 구조 전체. 기본 상단 액체는 DI수이며 설정에서 다른 액체 물성으로 교체 가능.
기본 모드가 **3D**(실험과 같은 깊이 70 mm, 보드 앞뒤로 유동이 도는 실물 배치)이며,
협력랩 2D CFD는 간소화 모델이므로 재현 대상이 아니다.
(별도 폴더 `tmc49_pool_boiling_2d` = 협력랩 CFD의 부분영역 재현 — 워밍업·검증용)

## 0. 2차 보정판 변경 사항 (실측 기반)

| 변경 | 1차 | 2차 | 근거 |
|---|---|---|---|
| Lee 응축 계수 | −0.1 (자리값) | **−50** | 실측 정성 기준 역산 — 잔기포가 계면 위 ~100 mm 내 소멸, 벽면 상승 없음(협력랩 확인) |
| 코일 배치 | x 100~356 × y 590~660 × 깊이 관통 | **x 28~428 × y 613~643 × z 20~50** (관 스팬 400·중심높이 628·깊이 중앙) | 발표본 14쪽 도면 사진 실측 |
| 코일 h | 190 W/m²K | **310 W/m²K** | 면적 축소에 따른 hA 보존 환산 (핀 사양 수령 시 확정) |
| 보드 | 300×320 | **300×300** (y 0~300, 수조 바닥 접촉) | 발표자료 치수 표기 수조 사진 |
| CPU 발열면 | 60×80 다이 2개 (27.6 kW/m²) | **46×40 패키지 2개, 간격 44 (72.0 kW/m²)** ★위치는 사진 추정 | 도면 사진 (패키지 40 mm, 간격 45 mm) |
| 격자 | 891,348셀 | **943,380셀** (Δ3 mm 동일) | — |

1차(자리값) 실행 데이터는 `tmc49_full_tank_run1`로 보존 — 보정 전후 비교용.

## 0-0. 설정 파일 체계 — 코드 수정 없이 조정

모든 조정 요소는 **config.json** 하나에 모여 있고, 값 수정 후 `./Allrun` 만 실행하면
격자·경계·물성·초기층·시간 설정이 전부 자동 재생성된다 (tools/build_case.py).

| 바꾸고 싶은 것 | config.json 위치 |
|---|---|
| 수조 크기 (폭·깊이·액체 높이) | tank.width_mm / depth_mm / liquid_height_mm |
| 층 높이·비율, 초기 온도 | layers.dielectric_mm (상단 액체층 = 나머지), init_T_* |
| 가열체 (총 전력, CPU 위치·크기·개수) | heater.total_W, heater.cpus[] — 목록에 추가하면 발열면 증가 |
| 보드·코일 위치와 크기 | board.*, coil.* |
| 하단·상단 액체/증기 물성 | dielectric_fluid.*, vapour.*, water.* (`water`는 내부 호환 키) |
| 상변화 계수 | phase_change.evap_C / cond_C |
| 냉각 조건 (h, 입구온도) | coil.h_W_m2K / Ta_C — 또는 conditions.csv 행 선택 |
| 격자 해상도 | mesh.dx_mm (3=94만 셀, 2≈310만 셀) |
| 총 계산 시간·데이터 추출 간격 | run.end_time_s / run.viz_interval_s |
| 출력 데이터 선택 | run.output_fields (bubble / phase / flow / therm) |
| 열전대 좌표 | probes_mm.points |

- 실측 24조건 스윕: `CONDITION=C3_T20 ./Allrun` (conditions.csv의 행 이름; h_meas는 보간★ — 원표 수령 시 교체)
- 검증만: `python3 tools/build_case.py --check` — 상자 겹침·범위 초과·프로브 위치 오류를 실행 전에 잡음
- 재현성: 기본 config는 2차 보정판을 회귀시험(격자 943,380셀·면적·물성표·경계값 전 항목 일치)으로 검증함
- 구 생성기 tools/gen_blockmesh.py 는 build_case.py 로 대체됨

## 0-1. 수치 개선 (전문가 레퍼런스 대조 반영)

| 항목 | 값 | 근거 |
|---|---|---|
| T 대류 스킴 | Gauss limitedLinear 1 (TVD) | 공식 poolEvaporation 튜토리얼(upwind) 대비 층화 보존 개선 — T 진동·발산 시 `div(phi,T) Gauss upwind;`로 롤백 |
| 운동량 대류 | linearUpwind grad(U) 2차 | 튜토리얼(upwind) 대비 상급 |
| MULES 한정자 | nLimiterIter 5 | 강한 상변화 소스 대비 전문 관행 |
| U·T 선형해석기 | PBiCGStab + DILU, tol 1e-8 | 공식 튜토리얼 계열 |
| 계면 Courant | maxAlphaCo 0.5 | 상변화 VOF 전문 권장 |
| 에너지 감사 | coilT functionObject — Q_coil ≈ 15.4×(T̄_coil−293.15) W ↔ 입력 265 W 폐합 | 보존 감사(검증 스킬 E) |

## 1. 실험 ↔ 모델 대응 (3D 기본)

| 실험 | 이 케이스 | 비고 |
|---|---|---|
| 수조 456(폭)×70(깊이)×1,000(높이) mm | 456 × 70 × 800 mm (액체 영역) | 상단 200 mm 여유공간 생략★ |
| 하단 비전도 액체층 / 상단 액체층 | 아래 400 / 위 400 mm ★ · 기본값 TMC-49 / DI수 | setFieldsDict에서 조정 |
| 서버 보드(판) | x 80~380 × y 0~300, 깊이 z 15~23 mm ★ | 수조 바닥 접촉, 앞뒤 유동 허용, 기판은 단열 근사 |
| CPU 2개 (~265 W 실측 합) | 보드 앞면(z=23), x 162~208/252~298 × y 90~130 mm에 **총 265 W** | 3,680 mm² ⇒ 72.0 kW/m². 크기·간격·수직 위치는 치수 표기 사진 판독 |
| 나선 열교환 코일 + 냉각수 회로 | 코일 벽(x 100~356 × y 590~660 mm★, 깊이 관통 근사)에 h·(T−T냉각수) | h·Ta 아래 조건표 |
| TMC-49 끓음·응축 | 3상(액체·증기·물) + Lee 상변화, Tsat 320.15 K | 솔버 icoReactingMultiphaseInterFoam |
| 열전대 T1~T4 | 같은 위치 근사에 온도 프로브(z=35 mm)★ | T5·T6은 냉각수측이라 Ta로 대체 |

## 2. 실행 (WSL, OpenFOAM v2312)

```bash
cd tmc49_full_tank
./Allrun            # 3D DX=3 mm(약 94만 셀) · CFD Studio는 CPU 최대 80% 병렬 · VTK 변환까지
```

- CFD Studio 코어 수 = 논리 CPU × 최대 0.8(예: 32스레드 → 25 worker). 직접 실행은 `NP=16 ./Allrun`처럼 작업자 수 지정 가능
- 격자 옵션: `DX=2 ./Allrun` → 311만 셀(GPU 압력솔버 권장), `MODE=2D ./Allrun` → 연구용 2D 단면(CPU 중심 y–z 단면, CPU 열유속 보존) — [2D 단면 안내](../docs/SECTION-2D.md)
- 형상 수정: `tools/gen_blockmesh.py`의 상수(XS·YS·ZS·BOARD·COIL·CPU_C)만 바꾸고 다시 `./Allrun`
- 예상 소요(약 94만 셀, 30 s 물리시간): **CPU 기준 1~3일 수준**. AmgX는 `p_rgh`만 가속하므로 실제 이득은 동일 구간 A/B 측정으로 판정
- 출력 용량: 0.5 s 간격 저장 ≈ 5~10 GB — 부족하면 controlDict의 `writeInterval`을 1.0으로

### 하드웨어 권장 기준

| 등급 | CPU / RAM | 저장공간 | 대상 |
|---|---|---|---|
| 최소 | 4코어·8스레드 / 16 GB | SSD 여유 40 GB | Δx 3 mm 단기 시험. 완주 시간은 매우 길 수 있음 |
| 권장 | 12코어·24스레드 / 32 GB | NVMe 여유 100 GB | Δx 3 mm 약 94만 셀 표준 계산. NVIDIA CUDA VRAM 8 GB 이상 권장 |
| 고성능 | 16코어·32스레드 이상 / 64 GB 이상 | NVMe 여유 250 GB | Δx 2 mm 약 311만 셀·장시간 계산. NVIDIA VRAM 16 GB 이상 권장 |

Windows 10/11 x64 + WSL2 Ubuntu 기준. GPU는 선택 사항이며 검증된 AmgX/PETSc 환경이 없으면 CPU GAMG를 사용한다. GPU 환경에서도 `p_rgh`만 GPU로 계산하므로 동일한 짧은 구간의 CPU 대비 실측 후 채택한다. 사용자는 `end_time_s`(총 계산 시간)과 `viz_interval_s`(데이터 추출 간격)을 정한다. `viz_interval_s`가 짧을수록 원본 필드 용량이 크게 증가하며, 재시작용 전체 상태 저장은 CFD Studio가 내부 안전 기능으로 관리한다.

### 현재 3 mm 격자의 코일 UA 한계

- 현재 기본 입력 `UA_target_W_K=21.7` W/K는 3 mm 격자 상한 21.61 W/K보다 약간 큼
- 생성기가 격자 상한의 90%로 제한하여 실제 적용 UA는 약 19.45 W/K
- 21.7 W/K 목표를 여유 있게 유지하려면 2.5 mm 이하 격자 또는 실장치와 일치하는 코일 핀 전열면적 반영이 필요
- 3 mm를 유지하면 약 19.5 W/K가 현재 격자에서 정직하게 표현 가능한 값이며, 목표 UA와 구분해 결과에 기록

CFD Studio v81의 **중단**은 솔버만 멈추고 원본을 이동·삭제하지 않는다. 새 프로젝트를 실제 시작할 때 이전 실행의 `processor*`·`postProcessing`·로그는 지우지 않고 케이스 내부 `ProjectRuns/<실행 ID>/`로 이동한다. 리셋 자료만 `Trash/`로 이동한다. 우측 상단 ⚙ 환경 설정에서 CPU·MPI·GPU·Raw 위치를 PC별로 선택한다. Raw 루트는 프로젝트 생성 시 고정되고 `runs/<실행 ID>/times/<시각>/processorN`으로 분리된다. `p_rgh`가 없는 완료 프레임만 전체 MPI 조각 SHA-256 검증 후 이동하고, 원래 processor 시간 경로에는 Viewer/reconstructPar용 링크를 유지한다. 재개 앵커·최신 기록 프레임은 WSL/SSD에 남는다. AmgX/PETSc에서 `cudaErrorIllegalAddress` 또는 PETSc 76이 발생하면 `.cfd_studio_gpu_failed`를 기록해 자동 재시도를 차단하고 다음 수동 실행부터 CPU GAMG를 사용한다.

### 액체 물성 입력과 OpenFOAM 반영

- CFD Studio의 새 설정 창은 **하단 비전도 액체**와 **상단 액체**를 분리한다. 기본값은 TMC-49와 DI수다.
- 각 액체의 이름·기준 온도·ρ·cp·μ·k·β를 입력하면 `manual_properties`로 저장된다. 생성기는 `rho(T)=rho_ref[1-β(T-T_ref)]`와 입력 대표값으로 `icoTabulated/hTabulated/tabulated` 물성 사전을 만든다.
- 입력을 바꾸지 않으면 신규 설정은 TMC-49 제조사 `property_tables`와 DI수 온도표를 사용한다. 구 프로젝트 스냅샷만 과거 다항식 호환 경로로 읽는다.
- 하단 액체의 기화점·잠열·분자량과 증기 cp·μ·k, 세 계면장력도 실제 `thermophysicalProperties.*` 및 `phaseProperties`로 생성된다.
- 상단 액체는 현재 3상 구성에서 기화하지 않는 액상이다. 운전 온도에서 상단 액체도 상변화한다면 별도 증기상을 포함하는 모델 확장이 필요하다.

### GPU(AmgX) 압력솔버 연동 — PC별 환경 자동 감지

```bash
bash gpu_setup_amgx.sh                 # 최초 1회 빌드 (PETSc + AmgX + petscFoam)
# 설치가 끝나면 CFD Studio에서 중단 → 실행 재개. p_rgh만 자동 전환됨
```
GPU 번호·VRAM/클럭·Compute Capability·CUDA 위치·OpenFOAM 경로·nvcc 호환 C/C++ 컴파일러를 자동 검사한다. WSL에서는 Windows NVIDIA 드라이버를 우선하고, OpenMPI가 CUDA-aware가 아니면 PETSc의 호스트 경유 옵션을 자동 적용한다. 사용자명·RTX 모델·CPU 수·GCC 버전 하드코딩 없음. 현재 약 94만 셀에서는 행렬 변환·CPU↔GPU 전송·MPI 통신 비용 때문에 이득이 작거나 느려질 수 있으므로 동일 재시작 구간의 CPU GAMG 대비 실측 후 판단한다.

2026-08-23 `2mm_Test`에서 첫 `p_rgh` GPU 해석 중 `cudaErrorIllegalAddress`와 PETSc 76이 재현되었다. 실패 시 자동 재시도를 막고 CPU GAMG로 복귀한 기록은 [`문서/GPU_AmgX_2mm_적용_검증_20260823.md`](../../문서/GPU_AmgX_2mm_적용_검증_20260823.md)에 남겼다.

## 3. 조건 바꾸기 (실측 24조건 매핑)

`0.orig/T`의 coil 경계 두 값만 교체:

| 실험 조건 | h [W/m²K] (실측 h_DI-HX 기반★) | Ta [K] |
|---|---|---|
| Case 1 (14.67 L/min) | ≈130~210 | 입구온도별 |
| Case 2 (17.26 L/min) | ≈150~222 | 293.15(20°C)~307.15(34°C) |
| Case 3 (23.55 L/min) | ≈188~274 | 〃 |

★ h는 「코일 실제 면적 ÷ 모델 패치 면적」 보정 필요 — 코일 치수 수령 후 확정.

## 4. 채점 (실측 대비 — 요점 문서의 수치)

- T1·T2(하단 비전도 액체층) → 기본 TMC-49에서 **≈47 °C(320 K) 포화 고정** 재현 여부 — 1순위
- T3·T4(상단 액체층) → 현재 DI수 기본값 기준 조건별 실측 31~41 °C 수준 (20 °C 조건이면 ≈31 °C)
- 증기: CPU 다이 위에서 발생 → 대부분 계면·상부 냉각영역 부근에서 응축
- 정성 기준(협력랩 확인 사항): 위층 유입은 잔기포 분산 수준이며 **기포가 벽면을 타고 오르지 않음** —
  1차 실행(자리값 응축계수)은 벽면 상승이 나타나므로 응축 계수 보정 후 재실행으로 이 기준을 맞춘다
- 에너지 수지: CPU 투입 265 W ≈ 코일 흡열 (로그의 heat flux 합)

## 5. ★확인 필요 (전부 파일에 주석 표시)

1. 층 높이 400/400 → **확인 완료** — 협력랩 발표본(26-1 조경제.pptx 14쪽): "Lower layer: 400 mm TMC-49 /
   Upper layer: 400 mm DI water, Tank internal 70×456×1,000 mm". 상단 200 mm 여유 생략·외벽 단열 근사는 유지
   같은 쪽의 증기 순환 서술 "vapor rises, condenses near the upper cooling region" — 위층 증기 유입은 실험에서도 있는 현상
2. 보드·CPU 다이·코일의 위치·치수 (사진 기반 추정치)
3. CPU/보드 발열 분배 — 현재 265 W 전량을 CPU 다이 2면에 투입, 기판은 단열
4. 코일 유효 h·면적 보정. TMC-49–물 계면장력은 직접값 미확보로 PFH–물 실험의 0.0560 N/m를 유사물질값으로 사용 중
5. Lee 계수·방향 규약 — v2312 소스 확인 완료(C>0 증발·C<0 응축). UDF(TMC49_rev1.c) 원값 수령 시 교체.
   원값 수령 전 보정 근거: 응축 C=-0.1이면 특성 응축시간 ~200 s로 기포가 상단 액체층(400 mm, ~2 s 통과)에서
   사실상 응축 불가 → 잔기포가 계면 위 ~100 mm 내 소멸하려면 C(응축) ≈ -50 수준 필요 (2차 실행 보정값)
6. 잠열 h_fg — thermophysicalProperties.vapour의 Hf. 이권영 교수님 측 발표자료 `26-1 조경제.pptx` 12번째 슬라이드(하단 표기 11쪽) TMC-49 Property 표의 93.22 kJ/kg을 변환한 **93220 J/kg**.

참고: TMC-49 액체 물성은 제조사 공식 TDS Rev.4 원표를 OpenFOAM tabulated 물성으로 직접 사용한다. 표 내부는 선형보간하고 범위 밖은 끝값으로 고정한다. 320.15 K에서 rho 1530.38 / Cp 786.4 / mu 4.5646e-4(45 °C 상한 고정) / kappa 0.06195이다. 증기 cp·mu·kappa는 C6F14 공개 EOS·NIST 수송모델의 유사값이며 TMC-49 직접값이 아니고, Lee 계수는 실험 보정 전 미확정이다.

## 6. 한계

- 코일·보드는 경계 모델(내부 형상 미해석) — 국소 유동보다 층 온도·상변화 수지 재현이 1차 목표
- 정상상태 도달은 실험처럼 수십 분 물리시간 필요 — 「30 s 과도 → 이어달리기(startFrom latestTime)」로 접근
- 기포 개별 형상 해상에는 DX=3 mm가 거칠다 — 통계·층 거동 우선, 미세 기포는 DX=2 이하에서

## 7. 모드·격자 요약 (같은 생성기)

| 모드 | 명령 | 셀 수 | 용도 |
|---|---|---|---|
| 3D DX=3 (기본) | `./Allrun` | 943,380 | 실험형 1차 — 층 온도·수지·기포 통계 |
| 3D DX=2 | `DX=2 ./Allrun` | 생성 시 출력값 기준 | 본판 — 동일 구간 CPU/GPU A/B 검증 후 실행 |
| 2D 단면 | `MODE=2D ./Allrun` 또는 `case_dimension: "2D"` | 6,140 | 기포장 연구용 거친 입력 — CPU 중심 y–z 단면, `tools/export_coarse_2d.py`로 내보내기 |

- 2D 생성기(`tools/build_case_2d.py`)는 0.orig 전체에 `frontAndBack`(empty)을 넣고 격자 대응표 `constant/section2d.json`을 쓴다. 3D로 다시 생성하면 대응표는 삭제된다.
- 2D 스케일링 규칙(`section_2d.heat_rule`)·코일 UA 환산·검증 결과·제한은 [2D 단면 안내](../docs/SECTION-2D.md) 참고
