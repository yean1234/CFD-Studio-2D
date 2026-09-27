# ClO2 관련 문헌과 적용 범위 검토

조사일: 2026-09-27

## 조사 범위와 반영 상태

사용자 연구계획서에 인용된 핵심 문헌 5편의 서지정보, DOI, 공개 초록 및 연구기관 설명을 확인했다. 이번 작업은 **문헌과 근거의 적용 범위를 정리한 것**이며, 실행용 물성 선정·공급조건 산출·독성 가스의 확산 또는 노출 최적화 구현은 포함하지 않는다.

**Config, 기존 프로젝트, 솔버와 Viewer 코드는 변경하지 않았다. 실제 ClO2 해석을 실행하거나 검증한 결과도 없다.** 정규화 추적자 결과를 실제 ClO2 결과로 재표기하지 않는다.

본문 전체·보충자료·원시 농도 시계열까지 검토한 문헌은 없다. 아래의 '확인 범위'를 넘어 수치 모델을 재현했다고 주장하지 않는다. 이 목록은 핵심 인용문헌 확인이며 해당 분야의 완전한 체계적 문헌고찰이 아니다.

인용용 파일: [clo2-literature-references.bib](clo2-literature-references.bib)

## 문헌별 확인

| ID | 문헌 | 직접 확인한 내용 | 현재 연구에 대한 판단 | 확인 범위 |
|---|---|---|---|---|
| R1 | Kim et al., 2019 | 쌀 포대가 있는 보관실의 ClO2 처리와 위치·곤충종·발육단계에 따른 결과 차이를 연구 | 저장 공간에서 공간적 차이를 고려할 연구 배경. 선정 저장고의 검증 완료 물성표로 취급하지 않음 | 저자 소속 대학의 논문 기록과 초록; 본문 미검토 |
| R2 | Buenavista et al., 2023 | 밀 낟알의 ClO2 처리 및 제분·밀가루 품질 영향을 연구 | 기질·품질 영향을 구분할 배경. 밀의 결과를 정미 쌀의 직접 입력값으로 전용하지 않음 | USDA ARS 연구기관 설명·기술 초록, 출판사 색인 초록; 본문 전체 미검토 |
| R3 | Agrafioti et al., 2021 | 포스핀 센서 측정과 OpenFOAM 기반 컨테이너 CFD 결과를 비교 | 계산과 측정을 대조한 방법론 선례. 포스핀·컨테이너 검증을 ClO2·선정 저장고 검증으로 대체하지 않음 | 출판사 논문 페이지의 색인 초록; 본문 미검토 |
| R4 | Kim et al., 2015 | 거짓쌀도둑거저리의 ClO2 관련 행동 반응을 연구 | 후속 행동 연구의 배경 문헌. 가스 수송 물성이나 CFD 수치 검증 자료와 구분 | 학회 서지정보·DOI, KCI의 논문 초록; 본문 미검토 |
| R5 | E et al., 2018 | 여러 저장해충 종을 대상으로 온도와 먹이 조건에 따른 ClO2 반응을 연구 | 생물학적 반응의 적용 조건을 구분할 배경. 그 결과를 확산계수·정미 쌀 흡착계수로 사용하지 않음 | PubMed에 수록된 저자·학술지·DOI·초록; 본문 미검토 |

R1 근거: [고려대학교 연구성과 기록](https://pure.korea.ac.kr/en/publications/chlorine-dioxide-fumigation-to-control-stored-product-insects-in-/).

R2 근거: [USDA ARS 논문 기록](https://www.ars.usda.gov/research/publications/publication/?seqNo115=403157), [출판사 논문 페이지](https://www.sciencedirect.com/science/article/pii/S0022474X2300053X).

R3 근거: [출판사 논문 페이지](https://www.sciencedirect.com/science/article/pii/S0168169921001058).

R4 근거: [한국응용곤충학회 서지 목록](https://entomology2.or.kr/journal/list.php?keyword=Chlorine+dioxide), [KCI 논문 기록](https://www.kci.go.kr/kciportal/ci/sereArticleSearch/ciSereArtiView.kci?sereArticleSearchBean.artiId=ART002024272).

R5 근거: [PubMed 논문 기록](https://pubmed.ncbi.nlm.nih.gov/29992333/).

표의 '직접 확인한 내용'은 각 출처의 요약이다. '현재 연구에 대한 판단'은 기체·기질·형상·평가 대상의 차이를 고려한 이번 검토의 판단이며, 논문 저자가 CFD Studio의 타당성을 평가한 내용이 아니다.

## 이번 조사로 확정하지 않은 항목

| 항목 | 이번 검토의 결론 | 설정 변경 |
|---|---|---|
| 선정 저장고의 ClO2 실행용 물성 묶음 | 확인한 공개 자료만으로 대상 조건에 대응하는 검증된 입력 세트를 확정하지 않음 | 없음 |
| 정미 쌀·해당 포대에 대한 물성 대응 | 밀·다른 기질의 결과를 동일한 것으로 간주하지 않음 | 없음 |
| 실제 저장고의 경계·누설 및 공급 이력 | 참고문헌 존재와 실제 시설 조건 확보를 구분 | 없음 |
| 공간·시간별 실측 검증 데이터 | 해당 저장고를 직접 검증할 원시 시계열을 이번 조사에서 확보하지 않음 | 없음 |
| 독립적 모델 검증 상태 | 수치 시험 통과와 실물 예측 검증은 별개 | 없음 |

'확정하지 않음'은 해당 자료가 어디에도 존재하지 않는다는 뜻이 아니다. 이번에 확인한 자료 범위와 채택 여부를 뜻한다. 미확정값을 0으로 채우거나 다른 기체의 값을 이름만 바꿔 입력하지 않았다.

## 서지정보

### R1. 쌀 보관실 실험

Kim, B. H., Han, G. D., Kwon, H., Chun, Y. S., Na, J., & Kim, W. (2019). *Chlorine dioxide fumigation to control stored product insects in rice stored in a room*. Journal of Stored Products Research, 84, 101527. [DOI: 10.1016/j.jspr.2019.101527](https://doi.org/10.1016/j.jspr.2019.101527).

### R2. 밀·밀가루 품질 연구

Buenavista, R. M., E, X., Subramanyam, B., Rivera, J. L., Casada, M. E., & Siliveru, K. (2023). *Evaluation of wheat kernel and flour quality as influenced by chlorine dioxide gas treatment*. Journal of Stored Products Research, 102, 102127. [DOI: 10.1016/j.jspr.2023.102127](https://doi.org/10.1016/j.jspr.2023.102127).

### R3. 다른 기체를 사용한 CFD·계측 비교

Agrafioti, P., et al. (2021). *Phosphine distribution and insect mortality in commercial metal shipping containers using wireless sensors and CFD modeling*. Computers and Electronics in Agriculture, 184, 106087. [DOI: 10.1016/j.compag.2021.106087](https://doi.org/10.1016/j.compag.2021.106087).

### R4. 행동 연구

Kim, Y., et al. (2015). *이산화염소에 대한 거짓쌀도둑거저리의 회피행동과 이를 억제하는 열처리 효과*. 한국응용곤충학회지, 54(3), 151-158. [DOI: 10.5656/KSAE.2015.05.0.021](https://doi.org/10.5656/KSAE.2015.05.0.021).

### R5. 온도·먹이 조건을 구분한 반응 연구

E, X., Li, B., & Subramanyam, B. (2018). *Toxicity of Chlorine Dioxide Gas...* [제목 축약; 전체 서지정보는 연결된 논문 기록 참조]. Journal of Economic Entomology, 111(4), 1947-1957. [DOI: 10.1093/jee/toy136](https://doi.org/10.1093/jee/toy136), [PMID: 29992333](https://pubmed.ncbi.nlm.nih.gov/29992333/).

## 접근·보존 기록

- 접근일은 모두 2026-09-27이다.
- 일부 ScienceDirect 및 DOI 직접 열기는 도구에서 실패했다. 이런 항목은 연구기관 기록 또는 검색에서 확인된 출판사 색인 내용을 사용했으며, 원문 전체 열람으로 기록하지 않았다.
- 원문 PDF·협력랩 자료를 저장소에 재배포하지 않았다. 문헌 식별자와 자체 요약만 추가했다.
- 이번 추가 산출물은 이 문서와 서지 파일이다. 기존 수치 검증 보고와 실제 가스에 대한 문헌 검토는 별도로 보관한다.
