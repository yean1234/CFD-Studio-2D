# 사일로 실행 및 에이전트 연결 점검

- 기준: 2026-10-03 · 사용자 요청으로 파일럿 준비 중단 후 개발 디버깅 수행
- 기존 프로젝트·원본 결과·진행 중 계산의 중단 및 덮어쓰기 없음
- 원안 Case 생성·사용자 탭 조작·실제 격자 생성·CFD 계산 미실행

## 발견과 수정

| 항목 | 원인 | 처리 |
| --- | --- | --- |
| 사용자 탭 연결 실패 | 조작 도구가 `sandboxCwd is not a local file URI`로 호출 자체를 거부 | 외부 연결 오류 `APP-A001` 기록 · Studio 오류와 분리하는 진단 명령 추가 · 외부 호스트 복구는 미확인 |
| Studio HTTP 연결 거부 | 설정 포트 8712에서 연결 거부 확인 | `APP-N001` 기록 · 재시작이나 포트 변경 없이 보존 · 서비스가 꺼졌는지 다른 환경인지 단정하지 않음 |
| 원안 입력 혼합 | 원안도 최적화 설계 범위·기본값을 적용 | 원안 A=10·B=7 검사 · C/D=0은 최적화용 추가 하부 포트 없음이라는 내부 표현 · 혼합 입력 `CFG-G003` |
| 순환 급기 없는 모델 실행 | `geometry_model` 누락 시 기본 원통 계산으로 진행 | 명시적 실행 모델 없으면 `CFG-G004` · 초안 저장과 실행 가능 여부 구분 |
| 미공개 형상 자동 가정 | 층당 4개·높이 0.25~0.75 m 등 기본값 사용 | 원통·사각 입구·유량 분배·포트 위치·근거를 명시하고 검토해야 실행 가능 · 미확정은 `CFG-G005` |
| 외부 격자 요구 무시 | `require_external_mesh`를 실행기가 읽지 않음 | 외부 격자 요구 시 현재 내부 격자 실행 차단 · 명시적으로 false인 등가 모델만 허용 |
| 격자 검사 후 실행 지속 | 단계별 실패 반환값과 품질 성공 문구를 확인하지 않음 | blockMesh·topoSet·createPatch·checkMesh·decomposePar 실패 시 종료 · `Mesh OK.` 없으면 `CFG-G006` |
| 실패 자동 재시도 안내 | 형상·격자 오류가 일반 실행 실패로 분류될 가능성 | 관련 코드에 입력 수정 안내 · 새 계산 재시도 전 동일 검사 적용 |

- 검사는 대기열 추가·새 계산 HTTP 진입·WSL 파일 생성 전 적용
- 이미 시작된 계산이나 기존 결과를 소급 수정하지 않음
- 입력의 `reviewed` 표시는 모델 가정의 검토 기록 · 실행 권한이나 원문 재현 인증이 아님
- 실패한 설정도 읽기·보존 가능 · 미확정 형상을 임의로 보완하지 않음

## 실제 실행 연결

- Studio 대기열 → 기존 실행 어댑터 → `tools/build_case.py` → `build_silo_runtime.py` → Allrun
- 현재 연결 형상: O-grid 원통, 동등 면적 사각 하부 입구, 경계면 포트
- 전체 높이를 원통으로 모델링 · 원문 원추 상부·외부 순환 덕트·팬 분기 손실을 해석하는 형상이 아님
- 경계면 포트는 주변 기존 면 선택으로 구성 · 10 mm 원형 구멍의 정확한 CAD/격자 재현이 아님
- 총 유량은 중앙 덕트 면적×지정 속도로 산정하고 명목 개구 면적비로 분배 · 팬 및 분기 유량의 직접 해석이 아님
- 전 영역 RANS 설정과 균질 다공성 저항 사용 · 원문의 곡물층 층류 설명과 동등하다는 검증 없음
- `silo_reproduction/tools/build_silo_case.py`의 외부 격자 검토 계약은 별도 도구 · Studio 활성 실행기의 실제 경로와 구분
- 사일로 정규화 추적자 실행 연결 미구현 · 별도 tracer 결과를 사일로 계산 결과로 연결하지 않음

## 명시적 등가 모델 계약

| Config 경로 | 의미 |
| --- | --- |
| `silo.kind` | original / custom / optimized |
| `silo.geometry_model` | 현재 연결: equivalent_boundary_ports_v1 |
| `mesh.require_external_mesh` | 내부 격자 실행은 명시적으로 false 필요 |
| `silo.geometry_assumptions.reviewed` | 가정 검토 기록 |
| `domain_model` | cylinder_full_height |
| `central_inlet_model` | equal_area_square |
| `flow_distribution` | nominal_area_proportional |
| `ports_per_layer` | 층당 포트 수 · 명시적 양의 정수 |
| `layer_z_min_m` / `layer_z_max_m` | 곡물층 내부 포트 높이 범위 · 여러 층이면 서로 다른 높이 |
| `bottom_outlets_enabled` | 추가 하부 포트 활성 · 원안은 false |
| `bottom_ring_radius_m` | 추가 하부 포트 활성 시에만 필요 |
| `source` | 선택값의 근거·한계 |

- 위 표에서 `reviewed`부터 `source`까지는 `silo.geometry_assumptions` 내부
- 실행 산출물 `case_manifest.json`에 가정과 `reviewed_surrogate_not_paper_geometry` 상태 보관
- 이 문서는 어떤 미공개 치수나 가정값도 사용자 대신 승인하지 않음

## 연결 진단

저장소 루트에서 실행

```bat
cfd_studio\Setup\Python312\python.exe cfd_studio\internal\agent_diagnostics.py
```

외부 도구 오류가 있는 경우

```bat
cfd_studio\Setup\Python312\python.exe cfd_studio\internal\agent_diagnostics.py --client-error "sandboxCwd is not a local file URI"
```

- `studio_config.json`의 포트 사용 · 브라우저·계산·설정 변경 없음
- 에이전트 스크립트와 의존 스크립트를 조회 · 성공해도 사용자 탭 연결 완료로 판정하지 않음
- `APP-A001`: 외부 에이전트 호스트의 작업 경로 문제 · Windows 로컬 작업 환경은 복구 후보이며 해결 여부 미확인
- `APP-A002`: 포트 설정 또는 에이전트 스크립트 응답 문제
- `APP-N001`: Studio HTTP 접근 실패 · 브라우저나 계산을 종료하지 않고 실행 상태와 포트 확인
- 현재 환경의 연결 복구 및 사용자 화면 검증은 아직 완료되지 않음

## 원문 확인과 보류 항목

- Fig. 1(a,c)는 원안, (b,d)는 개선 구조 · 원안 10 mm·7층은 본문 p.426에 명시
- C/D=0은 추가 하부 포트가 없는 원안을 표현하기 위한 코드 규칙이며, 논문 보고 치수가 아님
- 덕트 단면·정확한 개구 위치·층별 간격·급기 속도 기준 면적·유량 분배는 별도 확정 필요
- 원안 CV=0.6188과 비교하려면 표본 분포와 통계 정의 복원 필요
- 원문 Table 1의 CV와 1−CV 표기 사이 산술 불일치도 확인 · 임의 보정 금지
- 논문의 온도 시험을 전체 유속장의 실측 검증으로 취급하지 않음
- 원문: [Chen et al. (2026), Fig. 1 및 원안 해석](https://bioresources.cnr.ncsu.edu/wp-content/uploads/2025/11/BioRes_21_1_420_Chen_WZL_Structure_Optimizat_Ventillation_Corn_Grain_Storage_Silo_25014.pdf)

## 검증

- Python 관련 검사 64개 통과 · JavaScript 관련 검사 17개 통과
- Allrun 셸 문법 검사 및 Git 공백 오류 검사 통과
- 계약·정규화·대기열·HTTP 사전 검사·파일 보존·다국어 오류 검사
- Allrun은 가짜 격자·솔버 명령으로 실패 전파 검증 · 실제 checkMesh 또는 CFD 통과를 뜻하지 않음
- 실제 설치 환경 및 사용자 탭에서의 통합 검증은 미완료
- 원안 형상 연결·CFD 파일럿·격자 민감도·질량수지·CV 비교·추적자 계산은 보류

### 재현 명령

저장소 루트에서 실행 · 셸 제어 흐름 검사는 WSL/Linux 필요

```sh
python3 -m unittest tests.test_silo_contract tests.test_silo_mesh_gate tests.test_agent_diagnostics tests.test_config_presets tests.test_execution_adapters tests.test_agent_delivery tests.test_execution_workspace tests.test_cfd_forms -q
node --test tests/test_config_contract.js tests/test_agent_controls.js
sh -n tmc49_full_tank/Allrun
git diff --check
```

- 테스트용 가정값은 임시 디렉터리의 합성 입력 · 사용자 Case 승인값이 아님
- 기존 미커밋 저장고 격자 연구 변경과 개인 진단 산출물은 배포 대상에서 제외

## 재시도 중 발견한 시작 경로 문제

- 사용자 요청에 따라 연결 재확인 후 같은 외부 작업 경로 오류 재현
- 설정 포트의 HTTP 연결 거부 재현 · 확인 시점에 Windows Python 서버와 해당 포트의 수신 상태 없음
- 서버 종료 원인을 입증하는 시작 로그는 확보하지 못함 · 아래 강제 종료 코드가 이번 연결 거부의 원인이었다고 단정하지 않음
- 배치 파일의 기존 서버 강제 종료 제거 · 이미 실행 중인 Studio면 해당 주소를 열고 종료
- 서버 내부의 포트 점유 프로세스 강제 종료 및 기록된 PID 강제 종료 제거
- 다른 서비스가 포트를 사용하거나 확인할 수 없으면 APP-A002 표시 · 포트 자동 변경 및 새 서버 시작 없음
- 서버의 포트 확보 실패 시 시작 단계의 프로젝트 마이그레이션과 PID 기록을 수행하지 않음
- 기존 Studio의 정적 에이전트 스크립트로 식별 · 결과를 변환할 수 있는 API는 식별에 사용하지 않음
- 앱 최상위 모듈 초기화는 별도 개선 범위 · 직접 app.py 실행을 완전한 읽기 전용 검사로 사용하지 않음
- 외부 에이전트 호스트 경로 오류는 미해결 · 원래 Windows 로컬 저장소에 연결된 작업 환경에서 재확인 필요
- 이번 수정 확인을 위해 사용자 브라우저·Studio·솔버를 종료하거나 재시작하지 않음

### 추가 검증

- WSL/Linux: 시작 경로·연결 진단·사일로 계약·격자 실패 전파 26개 통과
- Windows 내장 Python: 시작 경로·연결 진단 12개 통과
- 포트 충돌·기존 서버 재사용·잘못된 포트·정상 새 실행의 종료 코드 전달·프로젝트 마이그레이션 차단·PID 보존 경로 검사
- HTTP·프로세스 호출을 대체한 모의 검사 · 실제 사용자 탭 연결과 CFD 실행 검증은 미완료

```sh
python3 -m unittest tests.test_studio_launcher tests.test_agent_diagnostics tests.test_silo_contract tests.test_silo_mesh_gate -q
```

## Windows 시작 검사 수정

- 시작 검사의 1초 TCP 연결 제한이 빈 포트에서도 TimeoutError를 반환하는 현상 재현
- 연결 거부 응답 지연을 포트 사용 불가로 잘못 분류한 시작 프로그램 회귀 오류
- 포트 사용 가능 여부를 로컬 소켓 바인딩으로 확인하도록 수정 · Windows는 배타적 주소 사용 옵션 적용
- 포트를 열 수 없는 경우에만 기존 Studio 식별 · 실행 직전의 경쟁은 서버의 최종 바인딩으로 처리
- Windows와 WSL/Linux 각각 시작 경로·진단 검사 13개 통과 · 실제 임시 소켓의 빈 포트와 점유 포트 포함
- 실제 Studio 서버 시작 및 에이전트 스크립트 v1.3 HTTP 정상 응답 확인 · 사용자가 화면 표시 확인
- 수정된 검사에서 실행 중 서버를 reuse로 식별 · 실행 중 화면과 서버 유지
- 외부 화면 조작 도구의 작업 경로 오류는 별도 미해결 · CFD 파일럿 미실행

## 지침과 진단의 일치

- 서버·스크립트·외부 도구·현재 탭 상태를 진단의 stages로 구분
- 실행 포트 환경변수를 진단에도 반영 · 잘못된 설정 문서 형식은 APP-A002로 보고
- 현재 탭에서 내보내지 않은 자료의 출처와 검토 상태를 명시하도록 한·영·일 지침 및 앱 안내 수정
- 같은 대상·입력·범위의 기존 명시적 승인과 새 가정에 대한 사용자 확인을 구분
- 질문 UI가 표시되지 않을 때 일반 대화로 필요한 질문을 전달하도록 명시
- 서버 Template 사본과 별도 JSON 초안 검사는 화면 조작·Case 저장·CFD 실행을 증명하지 않음

- Windows 내장 Python의 격리 실행에서 진단 모듈 import 실패를 실제 CLI로 발견하고 수정
- 지침에 적힌 진단 명령으로 서버 정상·외부 조작 도구 실패·현재 탭 미확인을 각각 확인
- 관련 검사: Windows Python 19개, WSL/Linux Python 19개, JavaScript 18개 · 별도 JSON 초안의 실제 편집기 가져오기·값 보존 검사 통과
- 앱 안내 변경은 다음 페이지 로드에서 반영 · 미저장 입력을 보존하기 위해 사용자 탭을 강제 새로고침하지 않음
