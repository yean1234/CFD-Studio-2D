# 프로젝트 실행 관리

## 변경

- 기존 기록 27개를 `식량창고` 프로젝트 하나의 실행 이력으로 통합
- 기존 폴더·Raw·계산 결과 보존
- 프로젝트 선택 시 해당 실행 목록 표시
- 솔버 로그 영역에 실행 목록·검색·상태·계산 범위 표시
- 실행 선택 시 해당 설정·로그·결과 표시
- 프로젝트 고정 설정 제거, 새 CFD 실행 시 조건 입력
- 실행별 입력 사본·SHA-256·고유 결과 폴더 보관
- 이전 실행의 설정과 결과를 유지하며 추가 실행
- Windows 한글 경로의 WSL 전달·UTF-8 처리 보완
- 사용법·설명서·우측 상단 `!` 도움말 갱신

## 검사

| 항목 | 결과 |
|---|---|
| Python | 114개 중 112개 통과, 환경 조건 2개 제외 |
| JavaScript Viewer | 27개 통과 |
| UI 실행 1 | 2초·초기 온도 23°C, 1,860셀, 완료 |
| UI 실행 2 | 3초·초기 온도 22°C, 1,860셀, 완료 |
| Windows 실행 | 포함된 Python → WSL → 솔버 연결, 2초 계산 완료 |
| 원본 C/T/U 대조 | 위 세 실행의 저장 배열과 일치 |
| 설정 분리 | 첫 실행 설정 유지, 다음 실행은 기본 입력에서 시작 |
| 프로젝트 전환 | 빈 프로젝트에 다른 실행·설정 미표시 |
| 실제 Studio | 프로젝트 1개·실행 27개, 과거 추적자·저장고 결과 선택 확인 |
| 기존 프로젝트 파일 | 545개 내용 변경 없음 |

- 짧은 계산의 목적: UI·실행기·설정 보존·결과 연결 검사
- 격자 수렴·시간간격 수렴·실험 검증 상태: 기존 미완료 판정 유지
- 검사 실행: 기존 결과와 분리된 폴더 사용
- [검사 기록](project-execution-review-20260928.json)

## 재현

```bash
python -m unittest tests.test_execution_workspace -v
python -m unittest discover -s tests
node --test tests/test_viewer_review.js
```

- UI 검토 서버: `tests/serve_execution_review.py`
- `--folder`: 별도 프로젝트 목록·입력 저장 폴더
- `--output`: 별도 CFD 출력 폴더
- `--allow-run`: 검토 서버에서 실제 솔버 실행 허용
- 실제 Studio의 **식량창고 → 새 CFD 실행**으로 반복 실행 가능

## 보관

- 프로젝트 목록·실행 입력: `cfd_studio/_runtime/executions`
- 새 계산 원본·배열: `output/warehouse_transport_ui_*`
- 기존 데이터: 원래 폴더 유지, 프로젝트 목록에서 참조
- 백업 시 목록·입력과 계산 원본 함께 보관
- 한 번에 한 실행 시작, 완료 후 다음 실행
- [사용법](CFD-STUDIO-USER-GUIDE.md)
- [설명서](CFD-STUDIO-MANUAL.md)
