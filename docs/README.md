# 문서

- 현재 기준: CFD Studio V1.0

## 사용자 안내

- [설치](../cfd_studio/README.md)
- [빠른 시작](quickstart-ko.md)
- [사용법](CFD-STUDIO-USER-GUIDE.md)
- [설명서](CFD-STUDIO-MANUAL.md)
- [CFD Template](template-inputs.md)
- [배포](distribution.md)
- [릴리스 노트](RELEASE-NOTES.md)

## AI 에이전트

- [한국어](CFD-STUDIO-AGENT-GUIDE.md)
- [English](CFD-STUDIO-AGENT-GUIDE.en.md)
- [日本語](CFD-STUDIO-AGENT-GUIDE.ja.md)
- Studio V1.0 · 에이전트 인터페이스 v1.4
- 연결 확인·단계별 복구·오프라인 초안의 출처·개발 모드 절차 포함

## 기술 자료

- [Viewer 데이터](VIEWER-DATA.md)
- [액침 수조 2D 단면](SECTION-2D.md) · [English](SECTION-2D.en.md) · [日本語](SECTION-2D.ja.md)
- [모델 근거](model-evidence.md)
- [연구 실험](research-studies.md)
- [GPU 개발 범위](gpu-research.md)
- [개발 규칙](code-conventions.md)
- [외부 구성요소](../THIRD_PARTY_NOTICES.md)

- [사일로 실행·에이전트 연결 점검](silo-agent-debug-20261003.md)

## 이전 검토 기록

- 파일명에 날짜가 있는 검토·실행 보고서는 해당 날짜의 코드와 결과에 대한 기록
- 이전 화면 명칭·검사 개수·실행 조건은 역사적 기록으로 보존
- 현재 조작은 사용법·설명서, 현재 배포 검사는 릴리스 노트 기준
- [저장고 연결 계산](warehouse-coupled-cfd-20260928.md)
- [저장고 격자 검사](warehouse-porous-grid-review-20260928.md)
- [농도 모듈 검토](concentration-module-review-20260927.md)
- [결과 무결성 검토](result-integrity-review-20260927.md)

## Config

- [JSON 규칙](CONFIG-JSON.md)
- [오류 코드](ERROR-CODES.md)
- [다국어 오류 사전](config-error-codes.json)

## 다국어 문서

- 사용법: [English](CFD-STUDIO-USER-GUIDE.en.md) · [日本語](CFD-STUDIO-USER-GUIDE.ja.md)
- 설명서: [English](CFD-STUDIO-MANUAL.en.md) · [日本語](CFD-STUDIO-MANUAL.ja.md)
- [에이전트 협업·참고 문헌](AGENT-COLLABORATION.md)

- [형상별 격자](MESH-REFINEMENT.md): 독립 격자 크기·중첩 충돌 처리·국소격자 정의·형상 폴더

## 실행 연결

- 새 Template의 **실행 양식**은 설치 확인과 별도 · 지원 어댑터를 명시적으로 선택
- [릴리스 노트](RELEASE-NOTES.md)의 실행 연결 및 결과 조회 항목 참고
- 개인 프로젝트·원본 계산·화면 증거는 프로젝트 저장 위치에 보관하며 공개 문서에서 제외

## 대칭 영역과 사전 계획

- [한국어](WAREHOUSE-SYMMETRY.md) · [English](WAREHOUSE-SYMMETRY.en.md) · [日本語](WAREHOUSE-SYMMETRY.ja.md)
- 연결된 정렬 저장고의 Y 대칭 절반·최대 셀 변 길이·셀 수 사전 검사 · 일반 AMR 및 독립 3D 접합은 미지원

## 연구 기반 격자 전이

- [선행연구·입력·구현 범위](APPLE-STORAGE-METHODS.md) · 축 구간 간격비 한도 · 자동 경계층/AMR은 미지원

## 개발자 안내

- [개발 문서](development/README.md) · [English](development/README.en.md) · [日本語](development/README.ja.md)
- [요구사항](development/REQUIREMENTS.md) · [구조](development/ARCHITECTURE.md) · [데이터 계약](development/DATA-CONTRACTS.md)
- [검증](development/VERIFICATION.md) · [운영과 배포](development/OPERATIONS.md) · [개발 계획](development/BACKLOG.md)
- [저장소 목록](development/INVENTORY.md) · [문서 관리](development/MAINTENANCE.md)
