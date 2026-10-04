# CFD Studio

- **V1.0** · 프로젝트별 CFD 실행 관리·Config 편집·결과 시각화
- **Windows 10/11 x64 지원 · macOS 미지원**
- 한국어·영어·일본어 인터페이스

## 개발 목적

- **AI 에이전트로 CFD를 수행할 때 조작 비용을 줄이고, 사용자가 같은 화면에서 확인할 수 있도록 설계한 OpenFOAM CFD 인터페이스 도구**
- Template JSON과 공통 화면 명령으로 소스 분석·반복 입력 부담 절감
- Config 변경 검토·조작 담당·인계·사용자 중단으로 협업 과정 확인
- 실제 LLM 비용 절감률은 별도 측정 필요 · [설계 근거와 제한](docs/AGENT-COLLABORATION.md)

## 시작

1. 저장소 전체 다운로드 또는 Git clone
2. WSL2 Ubuntu 설치·사용자 초기화
3. `cfd_studio/설치.bat` 실행
4. `cfd_studio/실행.bat` 실행 → 기본 주소 `http://127.0.0.1:8712`
5. **CFD → 새 프로젝트 → CFD Template·Config 입력 → + CFD Case → 실행 저장 → 대기열에 추가 → 대기열 시작**

- 포함 런타임: Windows Python 3.12.10 x64 · 별도 Windows Python 설치 불필요
- `설치.bat`: OpenCFD OpenFOAM v2312·Linux NumPy·기본 계산 환경 준비
- WSL 자체 설치·전용 솔버 빌드·GPU 환경 준비는 별도
- 기존 계산 폴더가 있으면 설치 중단 · 원본 삭제 없이 [설치 안내](cfd_studio/README.md) 확인

## 문서

| 문서 | 내용 |
|---|---|
| [빠른 시작](docs/quickstart-ko.md) | 설치 후 첫 프로젝트·Case·결과 열기 |
| [사용법](docs/CFD-STUDIO-USER-GUIDE.md) | CFD·Viewer 버튼과 화면 조작 |
| [설명서](docs/CFD-STUDIO-MANUAL.md) | 저장 구조·모델·단위·제한 사항 |
| [설치](cfd_studio/README.md) | 필요한 프로그램·BAT·업데이트 |
| [CFD Template](docs/template-inputs.md) | 솔버·Config 양식·초기 형상·프리셋 |
| [릴리스 노트](docs/RELEASE-NOTES.md) | V1.0 변경과 검사 결과 |
| [배포](docs/distribution.md) | 포함 파일·제외 데이터·검증 범위 |
| [문서 목록](docs/README.md) | 기술 문서·이전 검토 기록 |

- 사용자 안내: [English](docs/CFD-STUDIO-USER-GUIDE.en.md) · [日本語](docs/CFD-STUDIO-USER-GUIDE.ja.md)
- 설명서: [English](docs/CFD-STUDIO-MANUAL.en.md) · [日本語](docs/CFD-STUDIO-MANUAL.ja.md)
- AI 에이전트 사용법: [한국어](docs/CFD-STUDIO-AGENT-GUIDE.md) · [English](docs/CFD-STUDIO-AGENT-GUIDE.en.md) · [日本語](docs/CFD-STUDIO-AGENT-GUIDE.ja.md)

## 기능

- 프로젝트 → 여러 CFD Case → 실행별 Config 스냅샷·로그·결과
- 프로젝트 폴더 지정·기존 프로젝트 찾기·대기열·실패 원인·재시도 및 지원되는 중단 계산 재개
- CFD Template: 솔버·입력 양식·초기 형상 정의 · Template별 입력값 프리셋
- Config: 왼쪽 입력 목록·가운데 3D 형상·오른쪽 JSON 편집
- JSON 버튼: 전체 Config·공간 정의·선택 요소·주요 속성 분류에 제공
- 형상·영역·속성 목록에서 사용자 요소 추가·편집 · 기존 전용 모델은 호환 규칙 유지
- Viewer: 한 번에 Case 하나 선택 · **3D Virtual / Data Sheet** 전환
- Data Sheet 왼쪽: 전체 평균 또는 특정 좌표의 시계열 · 최대 3개 물리량
- Data Sheet 오른쪽: 저장 시점의 선상 프로파일 · 거리별 값 조회
- 3D 영상·사진, 그래프 이미지·CSV, Case 전체 CSV 내보내기
- 에이전트 전용 화면 명령·JSON 입력·사용자 검토·일시정지 신호
- 개발·화면 조작 진행 표시: [상태 전송과 오류 코드](docs/AGENT-PROGRESS.md) · 자료 확인·코드 수정·검사 단계와 연결 상태 표시
- 외부 에이전트 전용 명령으로 조작 표시 활성화 · 사용자의 중단 버튼은 표시를 숨기고 다음 명령 차단
- 에이전트 인터페이스 v1.4: 필요한 상태 조회·Config 변경 검토·조작 담당과 인계
- [연결 확인과 오류 복구](docs/CFD-STUDIO-AGENT-GUIDE.md#연결-확인과-오류-복구): 서버 응답·현재 탭 연결·초안 반영·Case 저장을 별도 확인
- [JSON 규칙](docs/CONFIG-JSON.md) · [오류 코드](docs/ERROR-CODES.md) · [협업과 참고 문헌](docs/AGENT-COLLABORATION.md)

## 지원 범위

- 등록 솔버 목록과 설치 확인은 실행 연결과 별개
- 새 Template의 임의 Config를 계산하려면 입력 생성·솔버 실행·결과 변환 연결 필요
- 종료 조건: 물리시간 또는 완전히 저장된 프레임 수 · 수렴 유지 구간에 따른 종료는 미연결
- GPU 계산은 별도 빌드·검증이 필요한 개발 기능 · 기본 계산 모드는 CPU
- 저장고 예제: 밀폐·균질 다공성 곡물 가정 · 개별 포대 막 전달·반응·흡착·5 m 부속실 공기·공급조건 최적화 미연결
- 저장고 격자·시간간격 수렴 기준 미달 · 정상상태·독립 실험 검증·7일 전체 연결 계산 미완료
- **V1.0은 소프트웨어 버전** · 계산 완료·시각화 준비·수치 검사·실험 검증은 각각 별도 상태
- 정규화 추적자 `C/C_ref`와 실제 물성 모델의 농도 단위 구분

## 저장소 구성

```text
cfd_studio/          앱·Viewer·Template·설치 및 실행 파일·Windows Python
tracer_transport/   추적자 시험·저장고 연결 솔버·후처리
tmc49_full_tank/    액침냉각 케이스 생성기·보조 도구
silo_reproduction/  저장고 예제·연구 도구
study_platform/     별도 연구용 실험 관리
docs/               사용자 문서·기술 자료·검토 기록
tests/              프로그램 검사
```

- Git 포함: 프로그램·배포용 Template·공개 예제·문서·검사 코드
- Git 제외: 사용자 프로젝트·Raw·계산 결과·캐시·개인 프리셋·PC 환경 설정
- 기존 프로젝트는 원래 위치에 보존 · 업데이트 후 **프로젝트 찾기**로 필요한 폴더 등록
- 연구용 Study 경로의 저장고 CFD 실행 연결은 미완료 · [연구 실험 안내](docs/research-studies.md) 참고

## 개발

- [코드 작성 규칙](docs/code-conventions.md)

```bash
python -m unittest discover -s tests -v
node --test tests/test_*.js
```

- Python 검사 의존성: [tracer_transport/requirements.txt](tracer_transport/requirements.txt)
- 브라우저 검사: Node.js·Playwright CLI 별도 필요
- Windows BAT는 CRLF, Linux 셸 스크립트는 LF 유지
- 서버는 로컬 PC 사용 전제
- 외부 구성요소: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
- 자체 코드에 신규 라이선스를 임의 부여하지 않음 · 외부 구성요소는 각 라이선스 적용

- [형상별 격자](docs/MESH-REFINEMENT.md): 형상별 독립 간격·비물리 국소격자 영역·형상 폴더·생성기별 적용 범위

### 실행 양식

- 새 Template에서 솔버에 연결된 실행 양식을 선택 가능
- 단순 사일로 등가 형상 미리보기 지원 · 상세 덕트 재현과 구분
- 범용 JSON 양식·솔버 설치·실행 연결은 각각 별도 상태
