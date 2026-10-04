# 저장고 대칭과 격자 계획

[한국어](WAREHOUSE-SYMMETRY.md) · [English](WAREHOUSE-SYMMETRY.en.md) · [日本語](WAREHOUSE-SYMMETRY.ja.md)

- 연결된 정렬 적재물 저장고 Config → **격자 → 계산 영역**에서 전체 또는 Y 중앙면의 한쪽 절반 선택
- **최대 셀 변 길이 (m)**에 양수 입력 · 3cm는 `0.03` · 비우면 기존 기본 간격과 세분화 사용
- **격자 계획 확인**: 셀 수·예상 최대 변 길이·기본 배열 크기·셀 수 한도 확인 · 격자 생성이나 계산 시작 아님
- 대칭은 적재·초기 농도·물성·열 경계가 대칭인 현재 연결 모델에만 적용 · 비대칭 유동을 제외하는 가정
- 셀 수 한도 초과 시 생성 차단 · 간격을 자동으로 거칠게 바꾸지 않음 · 배열 크기는 솔버 전체 메모리가 아님
- Viewer는 계산한 절반만 표시 · 계산하지 않은 반대쪽 좌표 조회 차단 · Config 형상 편집은 원래 전체 공간 유지
- 국부 격자는 기존 축 방향으로 전파 · 자동 적응 격자와 양쪽 독립 3D 격자 접합은 미지원

## 지원 범위

| 기능 | 상태 | 적용 범위 |
| --- | --- | --- |
| 유속·온도·희석 농도 연계 | 연결됨 | 기존 가정 기반 저장고 모델 · 외부 누출 제외 |
| 다공성 적재물 | 연결됨 | 적재 외곽의 균질 물성 · 개별 포대 막 미해상 |
| 전체 및 Y 대칭 절반 | 연결됨 | 정렬 적재물 생성기 · 하단/상단 Y 절반 선택 |
| 최대 셀 변 길이와 사전 계획 | 연결됨 | 셀 배열 생성 전 계산 · 명시적 셀 수 한도 유지 |
| 형상별 국부 세분화 | 연결됨 | 기존 블록의 축별 세분화 · 주변까지 전파 |
| 비물리 국소격자와 폴더 | 연결됨 | 물리 벽 생성 없음 · 폴더는 표시 묶음 |
| 반대쪽 결과 자동 복제 | 미구현 | 계산 영역만 표시·조회 |
| 자동 적응 격자·독립 3D 세분화 접합 | 미구현 | 정적 국부 격자와 구분 |
| 임의 축·임의 CAD 대칭 | 미구현 | 일반 솔버 설치만으로 연결되지 않음 |
| 실험 검증·7일 전체·정상상태 보증 | 미완료 | 실행·질량수지 검사와 별도 |

## 대칭 조건

- 절반만 계산하고 중앙면에 OpenFOAM `symmetryPlane` 적용 · 중앙면을 벽으로 생성하지 않음
- 전체 적재 외곽의 거울 대응, 초기 Gaussian 농도의 Y 중앙 정렬 확인 · 균일 물성·초기 온도·초기 정지 유동과 공통 외피 열 경계는 현재 실행기 조건
- 형상 대칭만으로 실제 유동의 대칭성 보장 불가 · 비대칭 열원·급기·문 개방이나 대칭 깨짐 가능성이 있는 문제에는 전체 영역 필요
- 질량·체적은 계산한 절반 기준 · 전체 영역과 비교할 때 총량과 단위체적 값을 구분
- 원래 전체 Config 보존 · 계산 결과의 `computational_domain.bounds_m`과 잘린 적재 외곽으로 실제 범위 기록
- 입력 오류: `MESH-S001` 지원하지 않는 모델/대칭, `MESH-S002` 비대칭 적재, `MESH-S003` 비대칭 초기 농도, `MESH-S004` 초기장의 대칭 경계 누락

## 격자 비용

- 공칭 78×25m, 처마 7.2m·지붕 높이 3.5m인 제공 예시의 계산 계획
- 최대 변 길이 3cm: 전체 808,156,608셀 · 절반 404,078,304셀
- 절반의 속도 3성분·온도·농도 float64 배열만 16.16GB · 압력·난류·메시·행렬·임시 배열·출력은 제외
- 3cm 대규모 격자는 생성·실행하지 않음 · 실제 자원 적합성 확인 필요
- 30m와 30cm는 서로 다른 입력 · 넓이 25m 공간의 절반을 30m 셀로 해상할 수 없음
- `maximum_cell_edge_m`는 상한 · 큰 값을 넣어도 기존 형상 경계·기본 세분화를 제거하지 않음
- 국부 영역은 형상·지붕 경계를 유지하는 축별 전파 방식 · 작은 관찰 상자도 예상보다 많은 셀을 만들 수 있으므로 계획 확인 필수

## 검증

- OpenFOAM v2312에서 전체 1,860셀·각 Y 절반 930셀의 `blockMesh`, `checkMesh`, 연결 솔버 실행
- 1초 개발 시험 · 세 계산 모두 3개 저장 프레임, 실행 검사 통과
- 같은 위치·저장 시점의 전체/절반 최대 차이: 유속 2.67×10⁻⁷ m/s 미만, 온도 3.36×10⁻⁸ K 미만, 농도 4.50×10⁻¹⁵ kg/m³ 미만
- 질량수지 상대오차 8.68×10⁻¹⁵ 미만 · 이 짧은 대칭 시험은 격자·시간 수렴, 실험 검증, 실제 훈증 효과를 입증하지 않음
- Windows 기본 Python에서 추가 NumPy 설치 없이 계획 조회 · 실제 계산은 기존 WSL 수치 환경 사용
- 재현 검사: `python -m unittest discover -s tests -p "test_warehouse_symmetry.py"` · 대칭 입력·체적·초기 질량·예산 차단 검사

## JSON

```json
{"porous_mesh": {"domain_mode": "symmetry_y_min", "maximum_cell_edge_m": 0.03}}
```

- 전체 Config가 아닌 병합할 필드 예시 · 실제 Template 내보내기에 추가 · 기존 `kind`, `base_max_spacing_m`, `refinement`, `maximum_cells` 유지

## 참고 문헌

- [OpenFOAM symmetryPlane](https://doc.openfoam.com/2306/tools/processing/boundary-conditions/rtm/constraint/symmetryPlane/)
- [OpenFOAM blockMesh](https://www.openfoam.com/documentation/user-guide/4-mesh-generation-and-conversion/4.3-mesh-generation-with-the-blockmesh-utility)
- [Dornier et al., Mean Mesh Adaptation for Efficient CFD Simulations with Operating Conditions Variability, 2024](https://arxiv.org/abs/2412.01274)
- 위 연구의 조건 표본 기반 평균 오차 적응은 참고 방법론 · 해당 알고리즘을 구현하거나 임의의 절반 초미세/절반 초거대 격자의 정확도를 입증한 것으로 해석하지 않음

## 연구 기반 격자 전이

- [연구 기반 격자 전이](APPLE-STORAGE-METHODS.md)

- [Alexander, Jakhar & Dasgupta (2024), Scientific Reports 14, 25402](https://doi.org/10.1038/s41598-024-76385-y)
- [Alexander, Jakhar & Dasgupta (2025), Scientific Reports 15, 11534](https://doi.org/10.1038/s41598-025-95886-y)
