# 형상별 격자

## 사용

- Config → 격자 → 국부 격자 → 형상 선택 → 형상에서 추가 → 격자 크기 입력
- 좌표 범위는 + 영역 또는 목록의 +로 별도 입력
- 기본 간격보다 작은 양수와 단위 지정 · 겹치는 영역은 가장 작은 간격 적용
- 형상 참조는 현재 치수를 사용 · 구와 원기둥은 외접 직육면체 사용
- UI에서 참조 중인 형상 삭제는 차단 · 앞쪽 배열 요소 삭제 시 참조 인덱스 갱신
- JSON 배열 재정렬 시 target_path도 갱신 · 원본 결과는 새 Case 실행 전까지 유지

## 지원

| 생성기 | 반영 방식 | 제한 |
| --- | --- | --- |
| 이중액침 | 형상 경계 및 각 축 분할·셀 수 반영 | 연결면 유지를 위해 주변 축 구간도 세분화 |
| 정렬된 적재물 저장고 | 기존 블록의 축별 셀 수 증가 | 적재·지붕 경계 유지 · 전체 세분화 배율 추가 적용 |
| 사일로 등가 모델 | 지정 높이에서 블록 분할 · 세분화 간격 반영 | 수평 단면 전체에 적용 · 상세 원문 덕트 구현과 별도 |
| 일반 솔버 Template | 형상 참조·범위·간격 입력 및 저장 | 실행 어댑터에 격자 생성기 연결 필요 |

- 사일로 좌표: 중심 X=0·Y=0, 바닥 Z=0, 원통 축 Z
- 사일로 기준 간격: 원통 체적 / target_cells의 세제곱근 · 격자 길이의 보증값이 아닌 입력 비교 기준
- 사일로 격자 기록: 실제 생성 예정 셀 수·높이 분할·셀 수·해결된 영역 범위·전파 방식
- 세분화 후 셀 수는 target_cells보다 증가 · 최대 2천만 셀, mesh.maximum_cells로 더 낮은 한도 지정 가능
- 실제 생성된 곡면 격자의 품질은 checkMesh로 별도 검사
- 팔분할 적응 격자·임의 CAD 표면 세분화·모든 솔버 자동 연결은 미구현

## JSON

기존 Template에서 출력한 Config의 mesh 또는 porous_mesh에 다음 항목 추가

```json
{
  "refinement_regions": [
    {
      "name": "Inspection region",
      "target_path": ["geometry", "regions", 0],
      "cell_size": {"value": 0.025, "unit": "m"}
    }
  ]
}
```

- 예시의 경로·수치는 실제 Config와 목적에 맞게 변경
- target_path 사용 시 shape·unit·min·max를 같은 영역에 중복 입력하지 않음
- 잘못된 참조·형상·입력·영역·생성 한도는 MESH-R001~MESH-R005로 구분
- [오류 안내](ERROR-CODES.md) · [기계 판독 오류 목록](config-error-codes.json)

## 검증

- 독립 시험용 원통 형상 · 논문 재현 또는 사용자 Case 아님
- OpenFOAM v2312 blockMesh 및 checkMesh 실제 실행
- 기본 4,032셀, 세분화 28,728셀 · 양쪽 Mesh OK
- 최대 비직교각: 기본 24.7616°, 세분화 34.8738°
- 최대 종횡비: 기본 3.63056, 세분화 9.28516
- 유동 솔버 미실행 · 격자 수렴·물리 검증 결과가 아님
- 단위 검사는 tests/test_local_refinement.py, tests/test_spatial_editor.js
- 화면 검사는 tests/browser_geometry_refinement.js · 실제 프로젝트 저장·계산 없음
