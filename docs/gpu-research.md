# OpenFOAM GPU 가속 기능: 연구 근거와 CFD Studio 적용

## PPT 핵심 문장

CFD Studio는 OpenCFD가 개발 중인 `std::execution`·Umpire 기반 GPU offloading 기술을 별도 실행 모드로 통합했다. 기존 CPU 해석은 유지하면서, PC별 전용 빌드와 사전 검증을 통과한 경우에만 단일 GPU 실행을 허용한다.

> 발표 시에는 **GPU 가속 실행 경로를 구축했다**고 표현한다. **해석이 더 빨라졌다**, **CPU와 결과가 동일하다**, **상용 CFD를 대체할 성능이 검증됐다**고 아직 표현하지 않는다.

## 1. 연구 배경

- 전통적인 OpenFOAM 해석은 MPI 기반 CPU 병렬 계산이 중심이다.
- OpenCFD 최신 개발 계열은 C++17 Parallel STL의 `std::execution::par_unseq`를 이용해 반복 계산을 GPU로 offloading하는 구조를 개발하고 있다.
- GPU와 CPU가 같은 데이터를 다루는 비용을 줄이기 위해 Umpire managed memory pool을 사용한다.
- NVIDIA 환경에서는 NVIDIA HPC SDK의 `nvc++ -stdpar=gpu`로 OpenFOAM 전체를 별도 컴파일한다.

SPUMA 연구도 OpenFOAM 전체 GPU 이식 가능성을 보여준다. NVIDIA A100과 AMD MI250X에서 DrivAer 사례를 검증했고, 약 8백만 셀/GPU 부근의 확장성과 최대 82% 에너지 절감 결과를 보고했다. 다만 2025년 12월 제출된 arXiv preprint이며 주 검증 대상과 셀 규모도 현재 이중 액침 3상 상변화 모델과 다르므로, 이 수치를 CFD Studio의 예상 성능으로 직접 사용하지 않는다.

## 2. 기술 선택

CFD Studio의 GPU Only에는 **OpenCFD `openfoam-ecse/feature-gpu`**를 선택했다.

| 후보 | 장점 | 적용 판단 |
|---|---|---|
| OpenCFD feature-gpu | 기존 OpenCFD 케이스·솔버 계열 유지, 공식 개발 소스와 빌드 지침 존재 | GPU Only 실행 경로로 채택 |
| SPUMA | NVIDIA·AMD 다중 GPU 확장성과 성능 연구 결과 존재 | 연구 근거로 참고, 현재 3상 솔버에는 미적용 |

선택한 소스는 커밋 `f36870083be0f391cf44c4aa6e1623214282e271`로 고정해 PC마다 다른 개발 버전을 받는 문제를 막았다.

## 3. CFD Studio 구성

사용자는 환경 설정에서 세 실행 방식을 구분해 선택한다.

| 실행 방식 | 계산 범위 | MPI |
|---|---|---:|
| CPU Only | 기존 OpenFOAM CPU 해석 | PC별 자동 배정 |
| CPU + GPU 병행 | CPU 해석 + 압력 선형해석 PETSc CUDA | PC별 자동 배정 |
| GPU Only | OpenCFD 개발 브랜치 전체 GPU offloading | 1 |

GPU Only는 기존 CPU 경로를 덮어쓰지 않는 별도 런타임이다. CPU로 만든 프로젝트를 GPU Only로 바로 재개하거나, GPU 오류 후 CPU로 몰래 전환하지 않는다.

## 4. PC별 자동 대응

1. 시작 전 NVIDIA GPU 목록과 선택 GPU 번호를 다시 탐지한다.
2. `nvidia-smi`에서 compute capability를 읽어 `ccXY` 컴파일 옵션을 만든다.
3. NVIDIA HPC SDK 24.9가 해당 GPU용 `stdpar` 코드를 실제 컴파일·실행하는지 사전 시험한다.
4. 같은 OpenCFD 커밋과 Umpire 2025.03.0으로 PC별 바이너리를 만든다.
5. 빌드 대상 커밋·compute capability·컴파일러 버전이 달라지면 이전 GPU 빌드 산출물을 제거하고 다시 만든다.
6. 선택한 물리 GPU(UUID)가 바뀌거나 솔버 바이너리가 변경되면 기존 검증을 무효화한다.

지원 범위는 **WSL에서 NVIDIA GPU가 정상 인식되고 NVIDIA HPC SDK 24.9의 사전 시험을 통과한 PC**다. AMD GPU, NVIDIA 드라이버가 없는 PC, 해당 컴파일러가 지원하지 않는 신형·구형 GPU에서는 GPU Only를 비활성화하고 CPU Only를 유지한다.

## 5. 다단계 안전 검증

GPU Only는 다음 검증을 모두 통과한 경우에만 활성화된다.

1. 전용 OpenCFD bashrc와 `WM_COMPILER=Nvidia-gpu` 확인
2. `nvc++`, 선택 GPU, GPU용 `icoReactingMultiphaseInterFoam` 확인
3. OpenCFD 공식 `Test-std_execution` 실행
4. Umpire `managed` memory pool 활성 확인
5. CFD Studio 3상 상변화 케이스를 12 mm 축소 격자·0.004초로 실제 실행
6. 시간 적분 시작, 정상 종료, CUDA·Thrust·메모리·부동소수점 치명 오류 부재 확인

검증 마커에는 OpenCFD 커밋, GPU 모델·UUID·compute capability, 드라이버, 컴파일러, WSL 커널, 솔버 바이너리 정보와 검증 시각을 기록한다.

## 6. 현재 달성 수준

| 항목 | 상태 |
|---|---|
| CPU / 혼합 / GPU Only 모드 분리 | 구현 완료 |
| PC별 GPU 탐지와 아키텍처별 빌드 | 구현 완료 |
| 공식 GPU 테스트와 실제 케이스 smoke test | 자동화 완료, 현재 PC 실행 대기 |
| CPU 프로젝트와 GPU 프로젝트 상태 격리 | 구현 완료 |
| 현재 RTX 4090 PC의 GPU 전용 바이너리 | 기존 CPU 계산 종료 후 빌드 예정 |
| CPU 대비 속도·에너지 비교 | 미검증 |
| 3상 상변화 결과의 CPU/GPU 수치 동등성 | 미검증 |

## 7. 다음 검증 실험

- 동일한 3 mm 설정과 짧은 종료 시각으로 CPU Only와 GPU Only를 각각 새 프로젝트에서 실행한다.
- 총 실행시간, 셀당 시간, GPU 메모리, GPU 사용률, CPU 사용률과 에너지 사용량을 기록한다.
- T1~T6 온도, 총 증기량, 상별 질량, 코일 제거열, 에너지 잔차의 시계열을 비교한다.
- 차이가 발생하면 원인을 연산 순서에 따른 절단오차, 수렴 차이, 모델 오류로 구분한다.
- 허용오차는 결과를 확인하기 전에 임의로 정하지 않고 물리량별 수치 검증 기준으로 별도 승인한다.

## 8. 기여점

- 무료 OpenFOAM 기반 이중 액침 해석에 최신 GPU 연구개발 경로를 선택 가능한 모드로 연결했다.
- PC마다 다른 하드웨어를 자동 확인하고 검증되지 않은 GPU 실행을 차단한다.
- 기존 CPU 데이터와 GPU 실험 데이터를 프로젝트 단위로 분리해 비교 가능한 연구 환경을 만들었다.
- 성능 향상을 미리 가정하지 않고 실제 케이스 smoke test와 CPU/GPU 교차 검증을 제품 동작에 포함했다.

## 9. 한계

- OpenCFD GPU 기능은 개발 트랙이며 현재 단일 GPU offloading만 지원한다.
- 부동소수점 연산 순서가 달라 CPU와 미세한 수치 차이가 발생할 수 있다.
- 약 94만 셀인 3 mm 케이스는 SPUMA의 약 8백만 셀/GPU 성능 구간보다 작아 GPU가 더 느릴 가능성도 있다.
- smoke test 통과는 실행 안정성 확인이며 장시간 계산의 정확도·성능 보증이 아니다.
- 다른 PC에서는 전용 런타임을 다시 빌드하고 검증해야 한다.

## 근거 자료

- OpenCFD, GPU infrastructure: https://www.openfoam.com/news/main-news/openfoam-v2606/infrastructure#gpu
- OpenCFD `feature-gpu` source: https://gitlab.com/openfoam/gpu/openfoam-ecse/-/tree/feature-gpu
- OpenCFD GPU build guide: https://gitlab.com/openfoam/gpu/openfoam-ecse/-/wikis/build
- OpenCFD GPU dependencies/Umpire guide: https://gitlab.com/openfoam/gpu/openfoam-ecse/-/wikis/dependencies
- NVIDIA HPC SDK 24.9, Stdpar and managed memory: https://docs.nvidia.com/hpc-sdk/archive/24.9/compilers/hpc-compilers-user-guide/index.html
- Bna et al., *SPUMA: a minimally invasive approach to the GPU porting of OPENFOAM*, arXiv:2512.22215: https://arxiv.org/abs/2512.22215
