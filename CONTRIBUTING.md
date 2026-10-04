# 개발 참여

- [개발 문서](docs/development/README.md)에서 시작
- [코드 규칙](docs/code-conventions.md)과 [AGENTS.md](AGENTS.md) 준수
- 요구사항 ID·변경 범위·기존 데이터 영향·검사 증거를 함께 제출
- 기존 미커밋 작업·사용자 프로젝트·Raw·결과 보존
- 실행 중 계산이나 브라우저를 임의 종료하지 않음
- 설정·API·결과 계약이 바뀌면 관련 문서와 언어별 안내 동시 갱신
- 미구현/미검증을 구현 완료로 표시하지 않음
- [변경 제안](docs/development/templates/RFC.md) · [시험 보고서](docs/development/templates/TEST-REPORT.md) · [인계](docs/development/templates/HANDOFF.md)

```bash
python tools/check_development_docs.py
```

- 새 파일은 검토 대상만 스테이징한 뒤 `--write-inventory`로 목록 갱신
- 사용자 데이터·로컬 설정·인증 정보·개인 실행 산출물은 커밋 제외
