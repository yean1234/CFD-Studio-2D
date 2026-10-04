# 개발 시작

## 작업 전

- [AGENTS.md](../../AGENTS.md), [코드 규칙](../code-conventions.md), [인계](MAINTENANCE.md) 확인
- 현재 브랜치·HEAD·Git 상태·diff 확인 · 기존 미커밋 변경의 소유 범위 기록
- 프로젝트·Raw·캐시·미저장 Config·대기열·실행 중 프로세스 보존
- 팀원과 같은 파일을 수정할 경우 먼저 변경 범위 조정 · 무관한 정리·전체 포맷 변경 금지
- 별도 테스트 폴더 사용 · 사용자 결과에 테스트를 실행하지 않음

## 환경

| 구분 | 기준 | 역할 |
| --- | --- | --- |
| 제품 호스트 | Windows 10/11 x64 | 포함 Python 서버·브라우저 |
| 제품 Python | 포함 Python 3.12.10 | `cfd_studio/Setup/Python312` |
| 계산 환경 | WSL2 Ubuntu, OpenCFD OpenFOAM v2312 | 격자·솔버·후처리 |
| 개발 Python | 코드·테스트 의존성에 맞는 환경 | 단위·통합 검사 |
| Node.js | `node --test`를 지원하는 환경, 실제 버전 기록 | JavaScript 검사 |
| 브라우저 자동화 | Playwright CLI | 실제 UI 흐름 검사 |
| macOS | 배포 미지원 | 호환된다고 안내하지 않음 |

- 설치·BAT 동작은 [설치](../../cfd_studio/README.md)가 기준
- 연구용 Python 의존성은 [requirements](../../tracer_transport/requirements.txt) · 포함 Windows 런타임과 별개
- 전용 솔버 빌드는 [연결 솔버 안내](../../tracer_transport/coupled_solver/README.md) 확인
- 설치 BAT는 전체 전용 솔버와 GPU 개발 환경을 자동 준비하지 않음
- 이번 문서 작업에서 새 PC의 설치 전체를 재검증한 것은 아님

## 첫 검사

저장소 루트에서 실행

```bash
python tools/check_development_docs.py
python -m unittest discover -s tests -p test_form_schema.py -v
node --test tests/test_form_config_editor.js tests/test_config_contract.js tests/test_i18n.js
```

- 전체 검사·CFD 실행 조건은 [검증](VERIFICATION.md) 참조
- Python 모듈은 `cfd_studio.__path__`가 `internal`을 추가하는 호환 구조 · 모듈 이동 시 import와 브라우저 자원 경로를 함께 확인
- 사용자 앱은 `cfd_studio/실행.bat` 사용 · 개발 중 중복 서버를 무조건 띄우지 않음

## 첫 변경의 완료 기준

1. 해당 요구사항 ID와 코드·테스트 위치 확인
2. 재현 조건·기대 동작·입력/결과 보존 조건 기록
3. 최소 범위 수정, 정상·실패 경로 검사
4. UI 변경은 실제 화면 확인 · 번역 시 사용자 이름 보존
5. 파일·로그·검사 범위·남은 제한을 인계
6. 승인된 배포 범위만 커밋 · 프로젝트 데이터와 인증 정보 제외

## 외부 에이전트

- [에이전트 사용법](../CFD-STUDIO-AGENT-GUIDE.md)의 진행 표시와 일시정지 절차 준수
- 개발 작업은 진행 CLI, 사용자 작업은 현재 탭의 공개 `CFDAgent.run` 명령 사용
- 현재 Template에서 내보낸 JSON을 기준으로 편집 · 숨은 상태 직접 변경 금지
- 서버 응답·탭 연결·초안 적용·저장·계산 시작은 서로 다른 확인 단계
