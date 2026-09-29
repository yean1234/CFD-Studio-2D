# 솔버 입력 검토

## 기준

- OpenCFD OpenFOAM v2312의 솔버 본체·createFields·제어 사전과 대조
- 저장고 전용 솔버는 저장소의 해당 소스 기준
- 링크의 저작자명은 원본 소스의 저작권 표기 기준
- 임의 확장 모델 전체를 자동 지원하는 실행기 검증은 포함하지 않음

## 보완 항목

- PISO·SIMPLE·PIMPLE별 반복 제어 항목
- 자동 시간간격 선택과 활성 시 Courant 수·최대 시간간격 검사
- 압력 기준점 지정 시 셀 번호·기준 압력 검사
- interFoam·interIsoFoam의 MULES·isoAdvector 정의 구분
- 상분율 반복·하위 시간단계 입력과 다상 초기 상분율 합 검사
- 상변화 모델 활성 시 계수·상 연결 입력 검사
- 이동 격자·복사 모델 활성 시 계수 입력 검사
- 열역학·고체 물성·영역별 수치 설정용 입력 구조
- 프레임 종료의 초기 프레임 포함 여부도 미선택 상태로 생성
- Template에는 물성·치수·초기값을 넣지 않으며 프로젝트 생성 시 작성

## 솔버

| 솔버 | 필수 항목 범위 | 원작자·소스 |
|---|---|---|
| icoFoam | transportProperties: nu / 0/U·0/p 및 경계조건 / fvSchemes·fvSolution/PISO·controlDict | [OpenFOAM Foundation · OpenCFD Ltd · 원본 소스](https://api.openfoam.com/2312/icoFoam_8C_source.html) |
| simpleFoam | transportProperties: 점성 모델·nu / 0/U·0/p, turbulenceProperties / fvSolution/SIMPLE·정상 수렴 조건 | [OpenFOAM Foundation · 원본 소스](https://api.openfoam.com/2312/simpleFoam_8C_source.html) |
| pimpleFoam | transportProperties·turbulenceProperties / 0/U·0/p / fvSolution/PIMPLE·deltaT·저장 간격 | [OpenFOAM Foundation · OpenCFD Ltd · 원본 소스](https://api.openfoam.com/2312/pimpleFoam_8C_source.html) |
| pisoFoam | transportProperties·turbulenceProperties / 0/U·0/p / fvSolution/PISO·deltaT | [OpenFOAM Foundation · OpenCFD Ltd · 원본 소스](https://api.openfoam.com/2312/pisoFoam_8C_source.html) |
| buoyantSimpleFoam | thermophysicalProperties: thermoType·mixture / U·p·p_rgh·T 및 열 경계조건 / 중력 g·SIMPLE·정상 수렴 조건 | [OpenFOAM Foundation · 원본 소스](https://api.openfoam.com/2312/buoyantSimpleFoam_8C_source.html) |
| buoyantPimpleFoam | thermophysicalProperties: thermoType·mixture / U·p·p_rgh·T·중력 g / PIMPLE·deltaT·열 경계조건 | [OpenFOAM Foundation · OpenCFD Ltd · 원본 소스](https://api.openfoam.com/2312/buoyantPimpleFoam_8C_source.html) |
| chtMultiRegionFoam | regionProperties: fluid·solid 영역 / 영역별 thermophysicalProperties·fvSchemes·fvSolution / 유체 초기장·고체 T·열 접합 경계조건 | [OpenFOAM Foundation · OpenCFD Ltd · 원본 소스](https://api.openfoam.com/2312/chtMultiRegionFoam_8C_source.html) |
| interFoam | 두 상의 rho·nu·상 이름 / U·p_rgh·alpha.phase_1·중력·표면장력 / MULES 상분율 이송·PIMPLE·deltaT | [OpenFOAM Foundation · OpenCFD Ltd · 원본 소스](https://api.openfoam.com/2312/interFoam_8C_source.html) |
| interIsoFoam | 두 상의 rho·nu·상 이름 / U·p_rgh·alpha.phase_1·중력·표면장력 / isoAdvector 상분율 이송·PIMPLE·deltaT | [OpenFOAM Foundation · DHI · OpenCFD Ltd · Johan Roenby · DLR · 원본 소스](https://api.openfoam.com/2312/interIsoFoam_8C_source.html) |
| rhoPimpleFoam | thermophysicalProperties: 상태방정식·에너지·수송 모델 / U·p·T 및 경계조건 / PIMPLE·deltaT·압축성 수치 기법 | [OpenFOAM Foundation · OpenCFD Ltd · 원본 소스](https://api.openfoam.com/2312/rhoPimpleFoam_8C_source.html) |
| icoReactingMultiphaseInterFoam | phaseProperties·상별 thermophysicalProperties / 각 상분율·U·p_rgh·T / 중력·계면 모델·PIMPLE·상분율 이송 | [OpenCFD Ltd · 원본 소스](https://api.openfoam.com/2312/icoReactingMultiphaseInterFoam_8C_source.html) |
| warehouseBuoyantFoam | 전용 transportProperties·Boussinesq 열물성 / U·p_rgh·T·스칼라 정의·확산계수 / 중력·PIMPLE·전용 격자·경계 연결 | [CFD Studio · 전용 솔버 소스](https://github.com/ReYoungSung/CFD-Studio/blob/main/tracer_transport/coupled_solver/warehouseBuoyantFoam.C) · [OpenFOAM Foundation · OpenCFD · 기반 솔버](https://api.openfoam.com/2312/buoyantBoussinesqPimpleFoam_8C_source.html) |

## 남은 범위

- 선택한 난류·열역학·경계·이동 격자·복사 모델의 세부 계수는 사용자 작성
- 열역학 조합과 수치 기법의 타당성은 OpenFOAM 입력 사전·실행 단계에서 추가 검토 필요
- 다중 영역의 실제 격자·접합면 대응은 별도 확인 필요
- 필수값 검사 통과는 물리 검증·수렴·계산 성공 판정이 아님
- 신규 범용 Template의 실행기 자동 연결은 미구현
- 이번 변경에서 CFD 계산은 실행하지 않음
