# 문서 설계 근거

- 조사일: 2026-10-05
- 아래는 문서 체계와 개발 절차에 참고한 공식 자료 · 특정 인증 준수 선언이 아님
- 프로젝트별 문서 내용은 현재 소스와 사용자 요구사항에 맞게 새로 작성

| 자료 | 조사에서 확인한 핵심 | 적용 |
| --- | --- | --- |
| [Diátaxis](https://diataxis.fr/) | 학습·작업·참조·설명을 구분 | 사용자 사용법과 개발 참조를 분리 |
| [arc42](https://arc42.org/overview/) | 목표·구조·실행·결정·품질·위험을 함께 기록 | 구조 문서와 요구사항·개발 계획 연결 |
| [C4 model](https://c4model.com/) | 시스템 경계에서 구성요소로 점진적으로 설명 | 브라우저·로컬 서버·WSL·저장소 관계도 |
| [ADR](https://adr.github.io/) | 개별 결정의 이유·대안·영향 보존 | 현재 설계의 회고 기록과 미래 제안 분리 |
| [Google Engineering Practices](https://google.github.io/eng-practices/review/reviewer/looking-for.html) | 설계·기능·복잡도·테스트·명명·문서를 함께 검토 | 변경별 검토 기준 |
| [Google SRE Release Engineering](https://sre.google/sre-book/release-engineering/) | 반복 가능한 빌드·검사·릴리스 | 환경·revision·검사·롤백 기록 |

## CFD 기능 근거

- [사과 저장고 논문](https://doi.org/10.1038/s41598-024-76385-y): 대칭 절반·벽 근처 세밀화·성장비 1.2·SST k-ω·y+ 조건
- [OpenFOAM layer addition](https://doc.openfoam.com/2212/tools/pre-processing/mesh/generation/snappyhexmesh/layers/): 벽면 층 생성의 입력과 제약
- [OpenCFD v2312 dynamicRefineFvMesh](https://api.openfoam.com/2312/classFoam_1_1dynamicRefineFvMesh.html): 동적 격자 기능의 구현 기반
- 사과 논문을 AMR 적용 논문으로 인용하지 않음 · [격자 개발 제안](MESH-ROADMAP.md)에 구분
