# 설치

- CFD Studio V1.0

- [사용법](../docs/CFD-STUDIO-USER-GUIDE.md)
- [설명서](../docs/CFD-STUDIO-MANUAL.md)

## 필요한 프로그램

- **지원 운영체제: Windows 10/11 x64**
- **macOS(Mac) 미지원** · 현재 배포판은 Windows 실행 환경과 WSL2를 사용

| 항목 | 준비 방법 | 용도 |
|---|---|---|
| Windows 10/11 x64 | 사용자 PC | Studio 실행 |
| Windows Python 3.12.10 x64 | `Setup/Python312`에 포함 | Studio 서버·결과 읽기 |
| WebGL2 지원 브라우저 | Edge 또는 Chrome 등 | 3D Viewer |
| WSL2 Ubuntu | 사용자가 먼저 설치·초기화 | Linux 계산 환경 |
| OpenCFD OpenFOAM v2312 | `설치.bat`에서 확인·설치 | 기본 CFD 솔버 |
| Linux Python 3·NumPy | `설치.bat`에서 확인·설치 | 계산 입력·결과 변환 |
| util-linux·procps | `설치.bat`에서 확인·설치 | CPU 배정·프로세스 확인 |
| 인터넷 연결·Ubuntu sudo 권한 | 최초 패키지 설치 시 필요 | 다운로드·패키지 설치 |

- Windows용 Python·Conda 별도 설치 불필요
- Git: 저장소 clone·업데이트를 사용할 때만 필요. ZIP 다운로드 가능
- Node.js·Playwright: 개발·검사용. 일반 사용자 실행에는 불필요
- 포함 Python은 실행 환경. 별도 Python 설치 EXE는 제공하지 않음

## 설치 파일

| 파일 | 역할 |
|---|---|
| `설치.bat` | 최초 계산 환경 준비 |
| `실행.bat` | Studio 실행 |
| `internal/setup_bridge.py` | Windows 경로·WSL 배포판 연결 |
| `internal/setup.sh` | OpenFOAM·보조 도구 설치·새 기본 계산 폴더 준비 |
| `studio_config.example.json` | 환경 설정 예시 |
| `Setup/Python312` | 포함 Windows Python 실행 환경 |

- 사용자가 직접 실행할 파일: `설치.bat`, `실행.bat`
- 저장소 전체 폴더 구조 유지. BAT 파일만 따로 옮기지 않음

## 최초 설치

- 저장소 전체 다운로드·압축 해제
- WSL이 없으면 관리자 PowerShell에서 다음 명령 실행

```powershell
wsl --install -d Ubuntu
```

- 재부팅이 요청되면 재부팅
- Ubuntu 실행 → Linux 사용자 이름·비밀번호 생성
- PowerShell에서 배포판 이름과 WSL 버전 확인

```powershell
wsl -l -v
```

- 배포판 이름이 `Ubuntu`가 아니면 `studio_config.example.json`을 `studio_config.json`으로 복사한 뒤 `wsl_distro` 변경
- 기존 `studio_config.json`이 있으면 보존하고 필요한 항목만 수정
- `cfd_studio/설치.bat` 더블클릭
- sudo 요청 시 Ubuntu 사용자 비밀번호 입력
- 완료 메시지 확인 → `cfd_studio/실행.bat` 더블클릭
- 기본 접속 주소: `http://127.0.0.1:8712`. 실제 주소는 실행창에서 확인
- 프로젝트 생성 → CFD Template 선택 → 직접 Config 입력 또는 해당 Template의 프리셋 선택 → 저장
- 실행 연결된 Template: **+ CFD Case → 실행 저장 → 대기열에 추가 → 대기열 시작**

## 설치 범위

- BAT는 WSL 자체를 설치하지 않음. Ubuntu 설치·사용자 초기화 먼저 필요
- 기본 설치 대상: OpenCFD OpenFOAM v2312·보조 도구·액침냉각 기본 계산 폴더
- 기존 `wsl_case` 경로가 있으면 덮어쓰지 않고 중단
- 설치 BAT는 소스 업데이트용 명령이 아님. 이미 설치된 사용자는 일반적으로 `실행.bat` 사용
- `warehouseBuoyantFoam` 등 저장소의 전용 솔버: 별도 빌드 필요. BAT가 모든 전용 솔버를 빌드하지 않음
- GPU 전용 환경·라이브러리: 별도 설치·검증 필요. 기본 설치는 CPU 환경
- `tracer_transport/requirements.txt`: 별도 Python 연구·그림 생성 도구의 의존성. Studio 일반 실행용 필수 설치 목록과 구분
- Template의 **설치 확인**: 실행 파일 존재 여부 확인. 패키지 설치 버튼이 아님
- 솔버 설치와 Studio의 입력 생성·실행·결과 연결 지원은 별도

## 문제 해결

| 증상 | 확인 |
|---|---|
| WSL 연결 실패 | `wsl -l -v`, 배포판 이름, Ubuntu 사용자 초기화 |
| 기존 케이스 감지 | 기존 계산 폴더 보존. 새 설치가 필요하면 `wsl_case`에 새 경로 지정 |
| Python 누락 | 저장소의 `Setup/Python312` 전체 복구 |
| 솔버 실행 파일 없음 | 선택한 솔버와 OpenFOAM 환경 확인. 전용 솔버 빌드 여부 확인 |
| 화면이 이전 버전 | 계산·변환 상태 확인 후 앱 재시작, 브라우저 새로고침 |

## 배포 구성

- 기본 CFD Template 정의: `templates/cfd-forms.json`
- 기본 Config: `configs/immersion.json`, `configs/grain_silo.json`, `tracer_transport`의 저장고 입력 템플릿
- 솔버별 입력 정의·양식 생성·결과 항목: `internal`의 Template 및 솔버 모듈
- 사용자 프로젝트·Case·원본 결과·캐시·PC별 등록 정보: Git 업로드 제외
- 사용자 정의 Template과 프리셋: 로컬 등록부에 보관. 배포용 기본 정의와 별도
- 다른 위치의 프로젝트 사용: **CFD → 프로젝트 찾기 → 폴더 지정 → 추가**

## 업데이트

- 배포 버전: V1.0 · `main` 브랜치·`v1.0` 태그
- 계산 종료와 대기열 상태 확인 → Studio 정상 종료 → 프로그램 파일 업데이트
- 프로젝트 폴더·Raw·결과·개인 프리셋·`studio_config.json` 보존
- 기존 환경을 갱신할 때 `설치.bat` 재실행을 필수 단계로 취급하지 않음
- 소프트웨어 폴더를 옮겼다면 **프로젝트 찾기**로 기존 프로젝트 폴더 검사·등록
- [릴리스 노트](../docs/RELEASE-NOTES.md)에서 검사 결과와 지원 제한 확인

## 에이전트 협업

- OpenFOAM CFD의 에이전트 조작 부담을 줄이고 사용자가 같은 화면에서 확인하는 인터페이스
- 별도 LLM 서비스나 계정은 설치 BAT에 포함하지 않음 · 사용하는 에이전트의 브라우저 도구를 기존 탭에 연결
- [한·영·일 안내](../docs/CFD-STUDIO-AGENT-GUIDE.md) · [협업 기능·참고 문헌](../docs/AGENT-COLLABORATION.md)

## 설치 경로

- 한글·공백이 있는 Windows 경로 지원 · 제공된 `설치.bat` 사용
- WSL 내부 설치 스크립트는 임시 파일로 전달 · Linux 패키지 설치에 필요한 암호 입력은 터미널에서 진행
- 설치 완료 후 솔버 설치와 Studio 실행 양식 연결을 각각 확인

## 격자 계획

- 정렬 저장고의 셀 수 계획은 포함된 Windows Python에서 수행 · 추가 Windows NumPy 설치 불필요
- 실제 격자 생성·솔버는 기존 WSL OpenFOAM·NumPy 환경 필요
- [대칭 영역·셀 수 한도·메모리 산정 범위](../docs/WAREHOUSE-SYMMETRY.md)

## 개발 환경 안내

- [개발 문서](../docs/development/README.md): 코드 구조·계약·검사·인계
- 문서 검사 도구는 개발용 Python과 Git 사용 · 일반 사용자 설치 절차에 추가 프로그램을 요구하지 않음
