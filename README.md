# CFD Studio

- Windows 기반 OpenFOAM 계산·데이터 보관·3D 시각화
- 포대식 쌀 저장고의 유속·온도·ClO₂ 농도 연결 계산
- 기존 액침냉각·단상 저장고 기능 포함

## 문서

- [사용법](docs/CFD-STUDIO-USER-GUIDE.md)
- [설명서](docs/CFD-STUDIO-MANUAL.md)
- [설치 안내](cfd_studio/README.md)

## 개발 상태

- 현재 모델: 누출 없는 밀폐 저장고, 균질 다공성 곡물
- 핵심 기능: 독립 설정 프리셋, 프로젝트별 실행 초안·대기열·설정 스냅샷·결과 조회
- 저장고 계산: 프로젝트에서 **CFD 실행 추가 → 실행 저장 → 대기열 시작**
- 적용 수준: 가정 조건 기반 연구용 모델

| 구분 | 상태 |
|---|---|
| 구현·실행 | 곡물 경계 정렬 격자, 다공성 저항·열저장·확산, 부력 유동, C/T/U 저장·조회·3D 표시 |
| 검사 통과 | 질량·열수지, 제한된 해석해 시험, 원본·배열 대조, 프로그램 검사 |
| 미완료 | 격자·시간간격 수렴 기준 미달, 정상상태·독립 실험 검증·7일 전체 연결 계산 미완료 |
| 제외 | 사용자 요청에 따른 누출, 외부 가스 경계 밀폐 |
| 미구현·미연결 | 개별 포대 막 전달, 반응·흡착, 5 m 부속실 공기, Study 실행 버튼, 공급조건 최적화 |

- 정량 예측: 정확도 검증 미완료
- 정상상태: 시간변화 외기온 사용, 도달 여부 미확인
- [격자 검사](docs/warehouse-porous-grid-review-20260928.md)
- [연결 계산](docs/warehouse-coupled-cfd-20260928.md)
- [실행 관리](docs/execution-queue-review-20260928.md)
- Git 관리: 코드·설정·문서·요약 검사·그림·프로브 CSV
- 로컬 보존: 기존 설정·Raw·대용량 계산 결과

## 설치 및 실행

- **필수:** Windows 10/11 x64, WSL2 Ubuntu, WebGL2 브라우저, 인터넷 연결(최초 OpenFOAM 설치).

1. 저장소 전체를 내려받거나 clone합니다. 폴더 간 상대 위치를 유지합니다.
2. WSL이 없다면 관리자 PowerShell에서 `wsl --install -d Ubuntu`를 실행하고 재부팅 및 Ubuntu 사용자 설정을 마칩니다.
3. `cfd_studio/설치.bat`을 실행합니다. OpenCFD OpenFOAM v2312, Linux NumPy 및 케이스를 준비합니다. Ubuntu sudo 비밀번호를 요청할 수 있습니다.
4. `cfd_studio/실행.bat`을 실행합니다. 기본 주소는 `http://127.0.0.1:8712`입니다.
5. **프로젝트 → CFD 실행 추가**에서 설정·종료 조건을 저장하고 **대기열에 추가 → 대기열 시작**을 선택합니다.

- Windows 실행용 Python **3.12.10 x64 embedded runtime**이 포함되어 있습니다. 시스템 Python이나 Conda 설치가 필요하지 않습니다. Linux 계산·변환용 Python과 NumPy는 설치 스크립트가 준비합니다. WSL 배포판 선택이 필요하면 `cfd_studio/studio_config.example.json`을 `studio_config.json`으로 복사해 수정합니다.

- 설치 대상에 기존 케이스가 있으면 덮어쓰지 않고 중단합니다. 새 설치에서는 고유한 `wsl_case` 경로를 선택하세요. 기존 CFD Studio 사용자는 원본 프로젝트를 보존하고 소스 업데이트를 별도로 검토해야 합니다.

## 주요 기능

- 형상·물성·열경계·격자·시간 설정, 입력 JSON과 실행별 설정 보존
- 하드웨어 감지, CPU/MPI 배정, 실행·중단·재개 및 계산 상태 표시
- 한 프로젝트의 실행 목록, 실행별 설정·로그·결과 분리 보관
- 기존 Raw·시각화 결과 보존 및 조회
- 기포·상분율·속도·온도 및 해석 유형에 따른 압력·난류 출력
- 재생 배속, 그래프, 스크린샷, 영상·CSV 내보내기
- CPU Only / 압력 GPU 병행 / OpenCFD 개발 기반 GPU Only 선택 경로
- 실험 묶음(Study), 순차 검증 계산, 품질 검사·비교·재현 패키지
- 연구 변수 3그룹, 배치·공급 위치 후보 검사, 3D 형상 미리보기 및 불변 입력 버전

## 구성

```text
cfd_studio/          Windows 앱, Viewer, 설치·실행 파일, Python 런타임
tmc49_full_tank/     공통 케이스 생성기, 액침냉각 기본 설정, GPU 보조 도구
silo_reproduction/  저장고 설정, 설계 실험 도구 및 가정
docs/               모델 근거, GPU 개발 경로 및 배포 노트
tests/              배포 구성과 설치 브리지 검사
study_platform/     실험 관리, 연구 변수·형상 후보, 비교·재현
tracer_transport/   정규화 검증·저장고 열/유동/ClO₂ 연결 솔버, 입력 설정 및 후처리
```

- `cfd_studio/configs`에는 액침냉각과 저장고 예제를 제공합니다. 실제 프로젝트 데이터, 개인 PC의 드라이브 경로와 UI 상태, 협력랩 원자료는 포함하지 않습니다. Raw·Viewer 산출물은 실행 후 생성됩니다.

## 해석 범위

- 액침냉각은 OpenFOAM v2312 `icoReactingMultiphaseInterFoam` 기반 3상 VOF와 Lee 상변화 모델입니다. DI수는 비기화 상으로 취급합니다. 저장고는 단상·다공성 해석이며 `simpleFoam` 정상상태 반복을 물리시간으로 해석하면 안 됩니다. 모델 보정과 격자·시간간격 민감도 검토가 필요합니다.

- GPU Only는 별도 빌드·사전 검증이 필요한 개발 기능입니다. 설치 기본값은 CPU Only입니다. GPU의 속도 향상과 CPU/GPU 결과 동등성은 해당 PC와 조건에서 확인해야 합니다. 웹 서버는 로컬 PC 사용을 전제로 하므로 인터넷에 공개하지 마세요.

## 개발·검사

- Studio 실행 후 `/studies`에서 검증 실험을, `/studies/design`에서 연구 변수·형상 후보를 관리합니다. [연구 실험 사용법](docs/research-studies.md)에 실행 조건과 제한사항을 정리했습니다. **저장고 후보를 실제 ClO₂ CFD로 실행하는 어댑터는 아직 연결하지 않았습니다.** 검증 예제만 실제 솔버로 실행됩니다.

- 정규화 가스 수송 모듈은 [tracer_transport 사용법](tracer_transport/README.md)을 참고하세요. 해당 모듈 검사는 별도의 requirements 설치 환경에서 실행합니다.

```bash
python -m unittest discover -s tests -v
python tmc49_full_tank/tools/build_case.py --check
```

- v174 기반 코드를 보존하고 연구 작업 경로를 v177에 추가했습니다. Windows 배치 파일은 CRLF, Linux 셸 파일은 LF로 관리합니다. 설치나 시험은 기존 계산 폴더에서 수행하지 않습니다.

## 문서와 라이선스

- [빠른 사용 안내](docs/quickstart-ko.md)
- [사용법](docs/CFD-STUDIO-USER-GUIDE.md)
- [설명서](docs/CFD-STUDIO-MANUAL.md)
- [상세계획서 기반 첫 ClO₂ 농도장 결과](docs/warehouse-plan-scenario-20260928.md)
- [앱 사용법](cfd_studio/README.md)
- [배포 및 검증 범위](docs/distribution.md)
- [모델 근거](docs/model-evidence.md)
- [GPU 연구 및 검증 상태](docs/gpu-research.md)
- [외부 구성요소 안내](THIRD_PARTY_NOTICES.md)
- [개발 규칙](docs/code-conventions.md)
- [2026-09-26 구현·검증 범위](docs/research-status-20260926.md)
- [2026-09-26 기능·UX 검토 및 수정](docs/ux-review-20260926.md)
- [2026-09-27 공통 설정 보완](docs/configuration-update-20260927.md)
- [ClO2 문헌·적용 범위 검토 및 참고문헌](docs/clo2-literature-review-20260927.md)

- 저작권자의 별도 명시가 없는 자체 코드에 신규 오픈소스 라이선스를 임의 부여하지 않았습니다. 외부 구성요소는 각 라이선스를 따릅니다.
