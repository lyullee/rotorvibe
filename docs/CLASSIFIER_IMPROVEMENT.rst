.. note:: Historical private-study record. Public RotorVibe omits normative tables and trained profiles; see DEVELOPMENT_HISTORY.md and CONTINUATION.md. Historical test counts are not public release counts.

분류기 원인 분석·개선·학습 독립 시험
===================================

실행일 2026-11-04. Windows / Python 3.12.14 / NumPy 2.3.5 / SciPy 1.18.1.
결론: 최종 시험 정답률 24.94%에서 63.69%로 개선(+38.75%p).
정상 시험 1회는 전부 오분류해 운영 사용에는 여전히 부족합니다.

확인된 원인
-----------

기존 알고리즘은 클래스별 분산으로 나눈 거리만 비교했습니다. 분산이 큰 클래스는
많은 관측을 가까운 것으로 취급합니다. 서로 다른 분산의 가우시안 밀도를 비교하려면
로그 행렬식 항이 필요합니다. 기존 모델의 특징별 평균 log 분산은 looseness 0.398,
misalignment -0.923, normal -0.627, unbalance -1.022였습니다.
이 보정항 누락이 looseness 편향의 직접 원인이었습니다.

동일한 개발 표본/기존 특징/기존 파라미터에서 보정항만 추가한 비교의 정답률은
52.92%에서 99.17%로 증가했습니다. 최종 시험 후 원인 확인용으로 수행한 읽기 전용
분해에서도 기존 파라미터를 재학습하지 않고 계산식만 바꾸면 강제 분류 정답률이
25.00%에서 63.75%로 증가했습니다. 이 분해에는 미확인 거부를 적용하지 않았으므로
제품의 24.94%/63.69% 수치와 구분해야 합니다. 시험에 맞춰 모델을 조정하지 않았습니다.

두 번째 문제는 물리 실험 간 분포 변화입니다. 제공자는 각 시험 전에 시험대를
분해하고 재조립했다고 명시합니다. 정상 시험 17의 ch3 log RMS 평균은 학습 정상
중심에서 전체 학습 표준편차 기준 -2.00만큼 이동했습니다. 개선 모델에서도 정상
시험 17의 평균 비용은 normal 0.379, misalignment 0.012로 정렬불량에 더 가깝습니다.
재조립·전달 경로 변화와 일관된 관측이지만 개별 원인을 센서 원시 기록만으로
확정할 수는 없습니다. RPM은 제공자의 근사값이며 시험별 타코미터 실측이 아닙니다.

제공자 출처: https://data.mendeley.com/datasets/zx8pfhdtnb/3
Lucas Costa Brito 외, DOI 10.17632/zx8pfhdtnb.3, CC BY 4.0.

적용한 구현
-----------

* vibration/classifier.py: 순수 NumPy fit_gaussian, GaussianClassifier.
* 점수: 0.5 * mean(((z - class_mean)^2 / class_variance) + log(class_variance)).
* 클래스 사전확률은 동일하게 두고, 학습 시 실험마다 전체 가중치를 동일하게 부여합니다.
* 학습 자료만으로 클래스별 미확인 거부 한계를 계산합니다. 미확인은 정답에서 제외합니다.
* ModelRegistry의 학습/추론, 기존 ClassifierStage에 같은 구현을 연결했습니다.
* 특징 28개와 vibration.features.v2 계약을 유지했습니다. 넓은 대역 특징을 세분화한
  복잡한 후보도 개발 자료에서 비교했지만 계산식 수정보다 효과가 작아 채택하지 않았습니다.
* 알고리즘 식별자는 standardized_diagonal_gaussian_log_density_v3.
  이전 모델은 재학습을 요구합니다. 기존 정상 기준 프로파일은 특징이 같아 유지됩니다.

시험 분리와 모델 고정
--------------------

학습: 1,2,3,4,5,6,7,8,10,11,12,15번 실험 / 5040개 창.
개발 검증: 9,13,14,18번 실험 / 1680개 창.
최종 시험: 16,17,19,20번 실험 / 1680개 창.
파일과 물리 실험의 중복이 없음을 검사했습니다. 같은 실험의 인접 창을 임의로
학습/시험에 섞지 않았고, 라벨·실험 번호·파일명은 입력 특징에 포함하지 않았습니다.

학습 실험의 매 7번째 창(720개)으로 실험 전체를 제외하는 3분할 교차검증을 했고,
개발 검증의 매 7번째 창(240개)에서 분산 하한 .05/.25/1.0을 비교했습니다.
선택값 .25로 학습 5040개 창만 다시 적합했습니다. 전체 개발 검증 정답률은
98.93%, 학습 내부 교차검증 정답률은 46.39%입니다. 이 큰 차이 자체가 실험 간
일반화의 불안정성을 보여줍니다. 교차검증 수치를 숨기거나 최종 시험을 이용해
다른 설정으로 재조정하지 않았습니다.

모델을 JSON/SHA256으로 고정한 다음 최종 시험을 한 번 열었습니다.
고정 SHA256: 16fe41cdbbffdea9a77a3352ab7b703386aacc3892dc84c7a2b19146b8ab8329
스크립트는 최종 결과가 존재하면 개발 재조정 및 최종 시험 덮어쓰기를 거부합니다.

기존 시험 결과는 이전 대화에서 이미 확인했습니다. 따라서 이번 시험은 학습/조정과
분리된 동일 벤치의 반복 평가이며, 새로 수집한 맹검 데이터 또는 외부 장비 실증이라고
주장하지 않습니다. 독립 실험은 4회이고 1680개 창은 시간상 상관되어 있습니다.

최종 시험 결과
--------------

================= ========= ========= ========
조건              기존 정답 개선 정답 개선 비율
================= ========= ========= ========
정상              0/420     0/420     0.00%
정렬불량          0/420     267/420   63.57%
헐거움            419/420   418/420   99.52%
불평형            0/420     385/420   91.67%
전체              419/1680  1070/1680 63.69%
================= ========= ========= ========

Macro F1: 56.42%. 실험별 다수결: 3/4(75%). 미확인: 1/1680.
정상 시험에서는 419개가 정렬불량, 1개가 헐거움으로 분류됐습니다.
이 시험으로 정상 오경보 문제는 해결되지 않았음을 명시합니다.
새 장비의 정상/고장 실험, 설치 조건별 정상 기준, 측정 RPM 및 전달 경로 보정
자료를 확보한 뒤 새 최종 시험을 따로 지정해야 합니다.

API 사용
--------

서버·DB 없이 모델 파라미터와 특징 배열로 호출합니다. 아래 모델 JSON은 로컬 검증
산출물이며 소스 배포 압축본에는 포함하지 않습니다.

::

   import json
   from pathlib import Path
   from vibration import GaussianClassifier
   from vibration.dsp import channel_features

   profile = json.loads(Path(
       'output/classifier_improvement/evaluated_model.json'
   ).read_text(encoding='utf-8'))
   model = GaussianClassifier(profile)
   # values: Brito와 같은 순서의 4채널, 25000점, 25 kHz, 원본 진폭 단위.
   names, features = channel_features(values, 25000)
   prediction = model.predict(features)
   # 여러 창의 특징: model.predict_many(feature_matrix)

저수준 GaussianClassifier는 특징 공간의 계산기이므로 장비/단위/채널 순서 적합성은
호출자가 확인해야 합니다. ModelRegistry.classify는 Brito/4채널/25 kHz/1초/unknown
단위라는 기존 적용 범위 검사를 유지합니다. operational_use=False, 기본 비활성을
유지합니다. 높은 상대 일치도도 교정된 확률이나 현장 진단 확정이 아닙니다.

재현 및 회귀 검증
----------------

원본 공개 데이터가 있는 로컬 체크아웃에서:

::

   python scripts/improve_classifier.py develop
   python scripts/improve_classifier.py final
   python scripts/verify_classifier_integration.py
   python scripts/diagnose_classifier.py

이미 최종 결과가 있는 이번 체크아웃에서는 재조정을 막는 보호 장치가 작동합니다.
원래 결과를 삭제해 같은 시험에 맞춰 튜닝해서는 안 됩니다.

신규 계산식 해석해·동일 분산·미확인·배치/단일 일치·실험 가중치·구버전 거부·
비정상 수치·JSON 복원·라벨 무관 파이프라인 시험 10개를 추가했습니다.
데이터 없는 시험 45개, 구현 58개, 물리 32개, ISO 363개: 총 498개 통과.
기존 휠 격리 가져오기/계산도 통과했습니다.

실제 ModelRegistry 학습 경로로 5040개 창을 다시 학습해 고정 모델의 파라미터와
1e-12 허용오차 내 일치를 확인했습니다. 전체 최종 시험 1680개 창에서 순수 API와
레지스트리 결과가 같았고, 4개 시험 각각의 실제 파형을 ClassifierStage까지
전달해 일치함을 확인했습니다. 라벨 메타데이터를 잘못 넣어도 예측은 변하지 않았습니다.

상세 산출물: output/classifier_improvement/development.json, final_test.json,
diagnosis.json, integration.json, frozen_model.json, evaluated_model.json 및 회귀 로그.
파라미터 학습·검증 DB는 같은 폴더의 production_runtime에 격리했습니다.
원본 데이터, 이전 결과, 사용자 기본 실행 DB는 변경하지 않았습니다.
