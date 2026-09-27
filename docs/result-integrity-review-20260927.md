# 일반 결과 파일·Viewer 점검 (2026-09-27)

## 상태 구분

| 항목 | 코드 및 이번 확인 | 상태 |
|---|---|---|
| 연구 대상 | Study 계약에는 ClO₂, 과거 수송 입력에는 PH₃ 메타데이터가 있음 | 결과 파일에 대상이 없으면 Viewer에서 `별도 기록 없음`으로 표시 |
| 실제 계산 모델·단위 | `normalized_inert_tracer`; 공극 농도 `C/C_ref`, 벌크 기준 흡착량 `Q/C_ref` | 정규화 값만 지원 |
| 수치 검사 | 과거 소형 예제 실행 기록과 `checks.json`이 있음. 이번에는 합성 파일·오프라인 검사만 재실행 | 과거 결과와 이번 검사를 분리 |
| 실험 비교 | 실제 대상 가스의 독립 실측 비교 완료 근거가 없음 | 미검증 |
| 저장고 형상 | 78 m 저장동의 형상 미리보기 코드 존재 | 부속실 포함 전체 계산 및 실제 수송 연결 미완료 |
| 비영 유동·포대 저항·누출·온도 조회 | 해당 정확도 검증 또는 기능 완료 근거 없음 | 미검증 또는 미구현 |

## 이번 보완

- Viewer 파일명으로 반올림한 시각이 충돌하거나 float32 저장 범위를 넘는 값을 거부한다.
- 원본 NPZ 조회에서 소수인 `region_id`를 정수로 잘라 읽지 않고 거부한다.
- 기존 프로젝트 갱신 시 모든 프레임 충돌을 쓰기 전에 확인한다. 신규 프로젝트는 임시 폴더에서 파일을 완성한 뒤 게시한다. 갱신 시 프레임을 먼저, 목록과 완료 메타데이터를 나중에 게시한다.
- 다른 자료가 든 폴더에 결과를 덮어쓰지 않는다. 손상된 첫 Viewer 프레임을 읽었을 때 로딩 완료로 표시하지 않는다. 비유한 공간 헤더를 거부한다.
- Viewer 설정에 연구 대상 기록, 계산 모델, 단위, 저장본 수치 검사 기록, 실험 비교 기록을 별도 행으로 표시한다. 연구 대상이 결과 메타데이터에 없으면 추정해서 채우지 않는다.
- 기존 Raw·계산 결과·프리셋을 수정하지 않았다. 실제 물성이나 공급 조건을 추가하지 않았다.

## 이번에 실제 수행한 검사

운영 솔버·앱·사용자 Chrome은 실행하지 않았다. 다음 명령은 저장소 루트에서 재현할 수 있다. `python3`은 NumPy 2.4.4, 그림 검사용 별도 Python은 NumPy 2.4.4와 Matplotlib 3.11.2를 사용했다.

```bash
python3 -m unittest discover -s tests -p test_model_scope.py -v
python3 -m unittest discover -s tests -p test_tracer.py -v
python3 -m unittest discover -s tests -p test_tracer_supply.py -v
python3 -m unittest discover -s tests -p test_studies.py -v
/tmp/cfd-ux-review-venv/bin/python -m unittest discover -s tests -p test_tracer_visualization.py -v
'/mnt/c/Program Files/nodejs/node.exe' --test tests/test_viewer_review.js
python3 tests/audit_saved_results.py cfd_studio/Project
git diff --check
```

Python 검사 31개와 JavaScript 검사 25개가 통과했다. 기존 Viewer 프로젝트 13개의 253프레임, 스칼라값 647,680개에 대해 시간 순서·헤더·격자 크기·공간 범위·유한값을 읽기 전용으로 확인했고 오류는 없었다. 이 검사는 파일 형식의 무결성만 확인한다. 원본 OpenFOAM 장과의 값 비교, 브라우저의 실제 3D 픽셀 확인, 새 CFD 수치 수렴 시험, 실제 저장고 계산, 실험 검증은 이번에 수행하지 않았다.

`output/study_acceptance_20260926_04/acceptance.json`에는 과거 3개 시도의 `finished/pass`와 별도 재계산 비교 기록이 있다. 파일과 연관 산출물의 존재를 확인했으나 이번 작업의 새 CFD 실행 결과로 집계하지 않았다.

## 남은 자료와 제한

실제 저장고 해석과 실험 비교에는 확정된 내부 치수·최종 적재 배치, 물성·경계 조건의 출처, 독립 실측 시계열과 측정 위치·불확도가 필요하다. 이번 결과 파일 검사로 그 공백을 메울 수 없다. 기존 프로젝트 갱신 도중 저장 매체가 실패하면 새 프레임 일부가 목록에 등록되지 않은 채 남을 수 있으며, 이 경우 기존 목록과 원본 프레임은 보존된다. 다중 프로세스가 같은 프로젝트에 동시에 내보내는 상황은 이번에 검증하지 않았다.
