# 외부 구성요소

- **CPython 3.12.10 x64 embedded:** Python Software Foundation 및 원 저작권자. `cfd_studio/Setup/Python312/LICENSE.txt`에 포함된 조건을 따릅니다. 바이너리는 기존 CFD Studio에 포함된 런타임의 복사본입니다.
- **OpenFOAM:** 이 저장소에는 OpenFOAM 자체 바이너리·전체 소스가 포함되어 있지 않습니다. 설치 스크립트에서 OpenCFD 배포 패키지를 설치합니다. 설치 패키지의 GPL 및 관련 저작권 고지를 따릅니다.
- **MPI, NumPy, GPU 의존성:** 실행 환경에서 별도로 설치됩니다. GPU 설치 도구를 실행하기 전에 해당 도구가 설치하는 컴파일러·라이브러리와 개별 라이선스를 확인하세요.
- **Three.js 0.160.1:** 연구 후보의 3D 형상 미리보기에 사용합니다. MIT License, Copyright 2010-2024 Three.js Authors. 배포 파일은 `study_platform/vendor/three.module.js`, 라이선스 전문은 `study_platform/vendor/THREE-LICENSE.txt`입니다. 원본: https://github.com/mrdoob/three.js/tree/r160
- **porousTracerFoam:** `tracer_transport/solver/porousTracerFoam.C`의 GPL-3.0-or-later 고지를 유지합니다. 라이선스 전문은 `tracer_transport/solver/COPYING`에 포함했습니다. OpenFOAM 연산자를 이용하는 별도 검증 솔버입니다.

프로젝트 내 설정·문서에는 연구 근거를 위한 출처가 포함되어 있습니다. 협력랩 발표자료, 실험 원본과 CFD 대용량 결과는 배포 대상에서 제외했습니다.
