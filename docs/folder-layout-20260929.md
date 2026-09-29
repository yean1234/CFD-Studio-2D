# 폴더 정리

- 내부 코드·JavaScript·HTML·설치 보조 파일 **22개**를 `cfd_studio/internal`로 이동.
- 실행 위치 유지: `cfd_studio/실행.bat`.
- 기존 Python import 경로 유지: `cfd_studio.execution_workspace` 등의 모듈 이름 변경 없음.
- 설치 배치·압축 보조 실행·화면 제공·검토 도구의 파일 참조 갱신.
- 프로젝트·Raw·결과·프리셋·사용자 Config 저장 위치 변경 없음.
- 실행 중인 계산·변환이 없음을 확인한 후 Studio 서버 재시작.
- 재실행 버전 v189, 프로젝트 2개·실행 28개 연결 유지.
- JavaScript 검사 61개 통과.
- 현재 작업 트리 Python 검사 182개 중 180개 통과·2개 건너뜀. 보류된 격자 검사 3개 포함.
- 포함 Windows Python에서 모듈 import 및 저장소 루트 해석 확인.
- 새 경로의 화면 파일 API 응답 확인.
- 파일 삭제 없음. 보류된 3 mm 격자 변경은 별도 미커밋 상태 유지.
