# 시각화 구현 범위와 직접 검증

## 구현 범위

현재는 정규화 추적자의 농도 C와 흡착량 Q에 대한 정적 x-z 단면 PNG 및 질량수지 그래프입니다. 전체 3차원 셀 데이터는 저장하지만, CFD Studio 내부의 회전 가능한 3D Viewer·시간 재생에 연결한 상태는 아닙니다. app.py에 tracer/PH3 결과 연동 경로가 없는 것도 확인했습니다. 기존 액침냉각 Viewer 구현과 혼동하지 않습니다.

## 실제 원본 대조 (2026-09-24)

대상은 sorption 시험의 block3d, 1,280셀, 0~1초의 0.1초 간격 11개 시각입니다. 농도장 생성기의 파서와 별개로 OpenFOAM ASCII 원본을 읽었고, polyMesh points/faces/owner/neighbour에서 직교 셀 중심을 재구성해 축 순서를 비교했습니다. 원본 파일을 수정하지 않았습니다.

| 검사 | 결과 |
|---|---|
| 원본 C와 NPZ의 모든 셀·시각 최대 차이 | 0 |
| 원본 Q와 NPZ의 모든 셀·시각 최대 차이 | 0 |
| 원본 격자와 시각화 좌표 최대 차이 | 2.22e-16 m |
| 다공성 영역 태그와 설정 경계 | 일치 |
| 저장 시각 | 누락 없음 |
| 원본 총량과 수지 CSV 최대 차이 | 9.03e-17 미만 C_ref*m3 |
| 그림 배열·축 방향·범위·공통 색상 범위·경계선 | 일치 |
| 다공성 밖 Q | 모든 시각 0 |

0초와 1초의 C 최대 변화는 0.13589 C/C_ref로, 그림이 같은 프레임을 반복하는 것은 아닙니다. 정적인 세 장의 스냅샷이지 애니메이션 검증은 아닙니다.

## 수정한 표현 문제

- aspect=auto가 실제 길이 비율을 늘리던 문제를 equal로 수정했습니다.
- 셀 사이 자동 보간 대신 nearest로 원래 셀 값을 표시합니다.
- 영역 경계는 설정한 실제 직육면체 치수 그대로 그립니다.
- 색상 범위는 각 변수의 전체 시각에 대해 고정합니다. C와 Q는 정의가 달라 별도 범례를 사용합니다.
- 가로 범례와 명시적 여백으로 제목·단위가 잘리지 않도록 수정하고 생성 PNG를 직접 열어 확인했습니다.
- 형상 메타데이터 불일치와 손상된 Q 데이터는 그림을 만들기 전에 거부합니다.

합성 좌표 마커로 잘못된 축 전치·셀 보간·색상 범위 변경을 잡는 회귀검사를 추가했습니다. 전체 자동 검사 16개가 통과했습니다. 실제 PH3 농도 검증이나 전체 저장고 설계 검증을 의미하지 않습니다.

## 재현

```bash
/tmp/cfd-tracer-env/bin/python -m tracer_transport.verify_visualization /path/to/block3d /path/to/new_audit_folder
/tmp/cfd-tracer-env/bin/python -m unittest discover -s tests -v
```

검사 결과는 visualization_audit.json, 그림은 concentration_sorption.png와 sorption_balance.png입니다. Chrome이나 실행 중 Studio를 조작하지 않습니다. 현재 원본 격자 대조기는 이 모듈이 만든 직교 육면체 ASCII 격자에 한정됩니다.
