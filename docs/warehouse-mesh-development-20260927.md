# 저장고 CFD 격자 개발 기록 (2026-09-27)

## 기존 구현과 이번 변경

- 기존 `tracer_transport/warehouse_geometry.py`는 저장동 공칭 외형의 `blockMeshDict`를 생성하고 OpenFOAM `blockMesh`·`checkMesh`를 실행한다. Studio의 저장고 설정 화면은 별도 설정 저장과 격자 검사 작업을 이미 제공한다. 이 기능은 다시 구현하지 않았다.
- 이번에는 기존 `checkMesh` 로그에서 실제 셀 수·체적·연결 영역 수·경계면 수·최대 비직교각·최대 왜도를 읽어 요청한 형상과 대조하고 `geometry_report.json`에 보존하도록 확장했다. Studio 검사 목록에도 두 품질 수치를 표시한다.
- 첨부 `상세연구계획서.pdf` 4~5쪽에서 83 m 전체 길이 중 저장동 78 m와 부속부 5 m를 구분하고 폭 25 m, 처마 높이 7.2 m, 지붕 상승 3.5 m를 명시한 것을 확인했다. 현재 격자는 저장동 78 m의 공칭 외형이며 부속부와 실내 유효 치수를 포함하지 않는다. PDF의 연구 계획 문구는 구현 완료의 증거로 사용하지 않았다.

## 실제 실행

저장소 루트에서 격리된 새 출력 폴더에 다음 명령을 실행했다. OpenFOAM v2312의 `blockMesh`와 `checkMesh -allTopology -allGeometry`가 성공했다. 기존 프로젝트나 계산 결과는 변경하지 않았다.

```bash
source /usr/lib/openfoam/openfoam2312/etc/bashrc
python3 -m tracer_transport.warehouse_geometry \
  --config tracer_transport/warehouse_geometry_20260925.json \
  --output /tmp/cfd-warehouse-mesh-quality-20260927-fixed --check-mesh
python3 -m unittest discover -s tests -p test_warehouse_geometry.py -v
python3 -m unittest discover -s tests -p test_warehouse_workspace.py -v
```

실측 로그와 새 보고서의 셀 수는 22,308개, 총 체적은 17,452.5 m³, 연결 영역은 1개다. 최대 비직교각은 14.9638°, 최대 왜도는 0.39503이다. 격자 단위 검사 5개와 저장고 작업공간 검사 3개가 통과했다. 별도의 임시 작업공간에서 `Workspace.save`→`Workspace.start`→완료 보고서 수신도 확인했다.

## 현재 한계

이 결과는 **격자 생성과 형상 품질 검사**다. 실제 내부 치수, 문·환기구·부속부 연결 상세, 최종 적재 배치, 열·유동 경계 조건은 확정되지 않았다. 유동·온도·화학종 수송 솔버를 이 형상에 연결하거나 물리적 정확도를 검증한 결과가 아니다.
