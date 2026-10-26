# 액침 수조 2D 단면 실행

[한국어](SECTION-2D.md) · [English](SECTION-2D.en.md) · [日本語](SECTION-2D.ja.md)

- TMC-49 이중 액침 수조 Config를 **CPU 중심을 지나는 y–z 수직 단면**의 2D OpenFOAM 케이스로 생성
- 거친 격자(2~3 mm) CFD의 셀별 증기분율과 벽 열유속을 기포장 연구 파이프라인 입력 형식으로 내보냄
- 3D Config가 형상·물성·실행 설정의 단일 기준 · 2D는 같은 Config에 `case_dimension`과 `section_2d`만 추가
- 3D 기본 동작과 생성 파일은 변경 없음 · 2D는 명시적으로 선택할 때만 생성

## 연구 연결

- 연구 흐름: 거친 격자 CFD → 셀별 `(α, q″)` → 상관식 기포 명세서 → 합성 기포장 → 열유속 추정 모델 검증
- 2D 단면은 BubbleML 2D 정답 자료와 같은 차원에서 거친 입력을 비교하기 위한 **적용 경로** 입력
- `coarse_inputs.csv`는 Cooper 게이트 코드(`cooperval.coarsen`)의 `coarse_inputs.csv`와 같은 열 사용
- BubbleML 쪽 거친 입력 생성(검증 경로)은 Cooper 게이트 코드가 담당 · 이 저장소는 수조 CFD 쪽만 생성

## 단면과 축

| OpenFOAM 축 | 수조 좌표 | 비고 |
| --- | --- | --- |
| x | 깊이 z (0 = 뒤 벽, 70 mm = 앞 벽) | 보드 z 15~23 mm, CPU 면 z = 23 mm |
| y | 높이 y | 중력 −y · 계면 400 mm · 상단 개방면 800 mm |
| z | 1셀 두께 (`frontAndBack` = `empty`) | 두께 기본값 = `mesh.dx_mm` |

- 단면 위치: `section_2d.x_mm` · 비우면 `heater.cpus[cpu_index]`의 x 중심(기본 CPU0, 185 mm)
- y–z 단면만 CPU 발열면이 벽으로 남음 · x–y 정면 단면에서는 CPU 면이 단면에 수직이라 발열 벽이 사라짐
- 단면이 CPU를 지나지 않으면 생성 전 오류 · 보드·코일은 단면 위치에 걸칠 때만 고체 영역으로 생성
- 기본 Config: 셀 6,140개 · 히터 면 13개(3.08 mm) · 계산 시간 0.1 s당 약 6 s(직렬, 아래 검증 환경)

## 실행

```bash
cd tmc49_full_tank
MODE=2D ./Allrun                                  # Config의 case_dimension보다 우선
python3 tools/build_case.py --dimension 2D --check # 생성 없이 검증
python3 tools/export_coarse_2d.py --out export_2d  # 계산 후 거친 입력 내보내기
```

- Config에 `"case_dimension": "2D"`가 있으면 `./Allrun`과 Studio 실행도 2D 생성기 사용
- Studio 배포 Config 목록의 `immersion_2d`가 이 설정을 포함한 기본값
- 2D에서는 병렬 코어를 `NP2D_MAX`(기본 4)로 제한 · 수천 셀 격자의 통신 비용 방지
- 측정 조건 행 적용: `CONDITION=C3_T20 MODE=2D ./Allrun`
- 3D로 다시 생성하면 `constant/section2d.json`을 삭제해 2D 격자 대응표가 남지 않음

## 3D → 2D 스케일링

| `heat_rule` | 보존 | 2D 히터 (기본 Config) | 폭당 입열 |
| --- | --- | --- | --- |
| `local_flux` (기본) | CPU 열유속·발열 높이 | 72.0 kW/m² · 40 mm | 2,880 W/m (수조 폭 평균의 4.96배) |
| `width_average` | 발열 높이·수조 폭당 전력 | 14.5 kW/m² · 40 mm | 581 W/m |
| `flux_and_power` | CPU 열유속·수조 폭당 전력 | 72.0 kW/m² · 8.07 mm (CPU 중심 기준 축소) | 581 W/m |

- 폭당 전력 기준 폭: `represented_width_mm` · 비우면 수조 폭 456 mm
- CPU 면은 `externalWallHeatFluxTemperature`의 `flux` 모드 · 두께와 무관하게 열유속 지정
- 코일 UA 목표 = 3D `UA_target_W_K` × (2D 폭당 입열 ÷ 3D 입열) · 상단 액체 평형 온도 `Ta + Q/UA`를 3D와 같게 맞추는 규칙
- 코일 UA는 격자 상한의 90%로 제한(3D 생성기와 같은 규칙) · 직접 지정: `section_2d.coil_UA_W_mK`
- `local_flux`는 3 mm 격자 코일 상한(약 52 W/(m·K))을 넘어 상단 액체가 초기 약 0.02 K/s로 가열 · 약 730 s 후 TMC-49 기화점 47 °C 도달
- 장시간 열평형이 필요하면 `flux_and_power` 또는 코일 주변 격자 세분화 사용 · 생성기가 매 실행 이 수치를 출력

## 내보내기 파일

| 파일 | 내용 |
| --- | --- |
| `fields_2d.h5` (h5py 없으면 `.npz`) | `temperature`·`velx`·`vely`·`alpha_vapour`·`alpha_water` (프레임, y, x) · 고체 셀 NaN · `mask`·좌표·무차원 기준값 |
| `heater_wall_2d.csv` | 프레임·히터 면별 q″, 벽 인접 셀 온도, CFD 벽면 온도, 증기분율, 하단 액체 평균 온도 |
| `coarse_inputs.csv` | `case_id, coarse_cell, x_m, q_W_m2, vapor_fraction` · 시간 평균 · Cooper 게이트 열과 동일 |
| `coarse_inputs_extended.csv` | 위 열 + 벽면 온도·과열도·서브쿨도·평균 프레임 수 |
| `export_manifest.json` | 단면·스케일링·코일·유체값·사용 프레임·가정 목록 |

- 시간 평균: 앞쪽 30% 프레임 제외(`--skip-initial`) · 초기조건 `0` 폴더는 기본 제외
- `x_m`: 히터를 따라 잰 위치 · 이 케이스에서는 높이 y [m]
- `--coarse-dx-mm`: 히터 면을 더 굵은 길이로 묶어 평균 · 남는 면은 Cooper 게이트 규칙처럼 제외
- 서브쿨도: TMC-49 기화점 − 하단 액체층(액상 분율 0.9 이상 셀) 면적 평균 온도
- OpenFOAM 없이 ASCII·binary 필드를 직접 읽음 · 셀 순서는 `constant/section2d.json` 격자 대응표 사용

## 검증 결과

- 기준: 2026-10-05 · Linux 컨테이너 · OpenCFD OpenFOAM v2312 · 기본 `immersion_2d` Config
- `blockMesh`·`checkMesh`: Mesh OK · 2개 해석 방향 · `cpu` 면 13개 · `frontAndBack` empty
- 직렬 0.1 s 계산 완료 · CPU 앞 셀에서 증기 생성(최대 증기분율 약 0.6)
- 하단 액체층(y < 300 mm) 에너지 증가가 CPU 투입 열량과 2% 이내 일치(0.1 s: 0.882 J / 0.864 J)
- `MODE=2D ./Allrun` 4개 프로세스 0.05 s: 분할·계산·재조립·VTK 변환 완료 · 직렬 결과와 셀 값 일치(상관계수 1.0)
- 3D 생성 파일이 변경 전 코드와 바이트 단위로 동일(기본 Config·`C3_T20`)
- 단위 검사 `tests/test_section_2d.py` 9개 통과
- 장시간 계산·격자/시간 수렴·실험 비교·기포 통계 검증은 수행하지 않음

## 제한

- 2D 단면은 수조 x 방향 유동과 기포 확산을 표현하지 않음 · 증기가 보드 앞 47 mm 간격에 머무는 경향 과대 가능
- CPU 벽면 온도는 3 mm 셀에서 약 1,100~1,500 K의 벽 경계 모델 값 · 물리적 벽 과열도가 아님
- 기포 명세서의 ΔT_sup는 q″로부터 Cooper 역산 또는 벽함수 경로로 구해야 함 · 3D도 같은 셀 크기와 경계 사용
- TMC-49 임계압은 Config 근거가 없어 `p_critical_Pa = null` · Cooper 환산압력 계산 전 출처 확인 필요
- Config 편집 미리보기: `case_dimension`이 `2D`이면 **2D 단면**으로 전환 · `section_2d.x_mm`·두께 위치의 얇은 판과 단면에 걸친 보드·코일·CPU 면만 표시 · 생성기 격자·경계 패치·계산 결과는 표시하지 않음
- 결과 Viewer의 2D 계산 결과 표시는 미검증 · 연구 분석은 내보내기 파일 사용 권장
- `section_2d`의 `x_mm`·`represented_width_mm`·`thickness_mm`·`coil_UA_W_mK`는 비워 두면 자동 계산 · Studio 저장 검증도 이 네 값의 `null`을 허용
- Lee 계수·증기 수송물성·계면장력 등 3D Config의 research_preliminary 상태를 그대로 상속

## 출처

- 설계 참고(측정 결과 아님): 개별연구 노트의 거친 입력 정의·조건당 대표값 1개·BubbleML 2D/3D 역할 구분
- 열 구성 참고: Cooper 게이트 코드 `cooperval/coarsen.py`의 `coarse_inputs.csv` 열
- 배열 배치 참고: BubbleML 데이터셋의 (시간, y, x) 필드 배치 — Hassan et al., *BubbleML*, NeurIPS 2023 Datasets and Benchmarks
- 상관식: Cooper, M. G. (1984), *Saturation nucleate pool boiling — a simple correlation*, IChemE Symp. Ser. 86
- 측정값: 위 검증 결과만 이 저장소에서 실행한 결과
