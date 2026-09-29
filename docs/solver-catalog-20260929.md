# 솔버 선택

## 사용법

- **CFD Template 리스트 → +**
- 이름·설명 입력 → 솔버 선택
- 설명의 원작자·원본 소스 링크와 주요 기능 확인
- **양식 구성 → 양식 편집 → Apply → Template 저장**
- 실제 값은 프로젝트 생성 시 입력 · 프리셋은 Template별 관리
- **설치 확인**은 실행 파일 존재 확인 · 실행기 연결과 별도
- [Template 사용법](template-inputs.md) · [입력 검토](solver-template-audit.md)

## 범용 솔버

OpenCFD OpenFOAM 2312 기준. 인기 순위가 아닌 기능 범주별 선정.

| 솔버 | 방식 | 기능 | Studio 연결 |
|---|---|---|---|
| icoFoam | 비정상 | 비압축성 층류 | 양식·프로젝트 저장 |
| simpleFoam | 정상 | 비압축성 유동·난류 | 기존 사일로 양식 |
| pimpleFoam | 비정상 | 비압축성 유동·난류, PIMPLE | 기존 사일로 양식 |
| pisoFoam | 비정상 | 비압축성 유동·난류, PISO | 양식·프로젝트 저장 |
| buoyantSimpleFoam | 정상 | 부력·열전달 | 양식·프로젝트 저장 |
| buoyantPimpleFoam | 비정상 | 부력·열전달 | 양식·프로젝트 저장 |
| chtMultiRegionFoam | 비정상 | 고체·유체 복합 열전달 | 양식·프로젝트 저장 |
| interFoam | 비정상 | 등온 2상 자유표면, VOF | 양식·프로젝트 저장 |
| interIsoFoam | 비정상 | 등온 2상 자유표면, isoAdvector | 양식·프로젝트 저장 |
| rhoPimpleFoam | 비정상 | 압축성 유동·에너지 | 양식·프로젝트 저장 |

## 기존 전용 구성

- `icoReactingMultiphaseInterFoam`: Studio 액침냉각의 다상·상변화·열전달 구성 유지.
- `warehouseBuoyantFoam`: Studio 저장고의 부력 유동·온도·스칼라 수송·다공성 적재 구성 유지.
- 전용 구성의 기존 가정·물성·검증 상태 유지.

## 상태 구분

| 표시 | 의미 |
|---|---|
| 설치 미확인 | 아직 확인하지 않았거나 환경 확인 실패 |
| 실행 파일 확인 | 선택된 CPU 환경에서 실행 파일 발견 |
| 실행 파일 없음 | 환경 확인은 성공했으나 해당 파일을 찾지 못함 |
| 기존 양식 연결 | 기존 형상·Config·실행기·결과 읽기 경로 존재 |
| Studio 연결 대기 | 솔버 정의·입력 계획 저장만 지원 |

- 실행 파일 존재는 라이브러리·버전 호환성·실제 계산 성공·GPU 지원을 보증하지 않음.
- OpenFOAM Foundation의 모듈형 솔버 이름을 자동 변환하거나 다른 배포판으로 대체하지 않음.
- 범용 솔버 10개가 모든 형상에서 즉시 실행된다는 의미가 아님.
- 미연결 8종은 형상·물성·초기장·경계조건 생성, 실행 제어, 결과 읽기 연결이 필요.
- `interFoam`·`interIsoFoam` 기본 솔버에 열전달·비등이 포함된 것으로 표시하지 않음.
- 비압축성 기본 솔버의 압력은 `p/ρ`이므로 물리 압력과 구분.

## 검사

- Python **43개 통과**: FORM 7개, 솔버 목록 7개, 실행 관리 19개, 대기열 10개.
- JavaScript **61개 통과**: Config·Viewer 회귀 검사.
- 검토 환경 OpenFOAM v2312에서 12개 실행 파일 발견. 실제 계산 시험은 수행하지 않음.
- 실제 브라우저에서 12개 선택 항목의 기능 표시 확인.
- 복합 열전달 FORM 양식·프로젝트 저장·새로고침·입력 계획 복원 확인.
- 비정상 사일로 FORM 저장 시 `pimpleFoam`·`PIMPLE`·물리시간 Config 확인.
- 프로젝트 선택에서 초안 항목 비활성 확인. 서버에서도 직접 요청 차단.
- 재시작 후 FORM 보존은 새 Workspace 인스턴스로 검사.
- 검토용 등록부만 사용. 기존 프로젝트·계산 결과·사용자 브라우저 변경 없음.
- 보류된 3 mm 격자 작업은 이 변경에 포함하지 않음.

## 수정 파일

- `solver_catalog.py`: 솔버 기능·입력·결과·연결 상태·실행 파일 확인.
- `cfd_forms.py`: FORM 양식·프로젝트 저장·복원, 미연결 실행 차단.
- `execution_workspace.py`: 솔버 조회·설치 확인 API, 초안 프리셋 제외.
- `execution_workspace.js`: 솔버 선택·기능 카드·입력 계획·초안 상태.
- `app.py`: v188, 도움말 갱신.
- `test_solver_catalog.py`: 설치와 실행 가능 상태 분리, 초안 보존·오연결 차단 검사.

## 출처

- 설치된 공식 OpenFOAM v2312의 `applications/solvers` 아래 각 솔버 `.C` 파일의 Application·Description·Required fields.
- [OpenFOAM 솔버 문서](https://doc.openfoam.com/2306/tools/processing/solvers/).
- [OpenFOAM 표준 솔버 목록](https://www.openfoam.com/documentation/user-guide/a-reference/a.1-standard-solvers).
- Studio 전용 기능은 저장소의 기존 Config·실행 연결 코드 기준.
