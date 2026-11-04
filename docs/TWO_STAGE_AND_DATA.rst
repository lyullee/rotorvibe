.. note:: Historical private-study record. Public RotorVibe omits normative tables and trained profiles; see DEVELOPMENT_HISTORY.md and CONTINUATION.md. Historical test counts are not public release counts.

정상 우선 진단·물리 특징·추가 정상/독립 시험 자료
================================================

2026-11-04 구현 및 로컬 검증. 결론: 정상 기준 -> 고장 후보 -> 판단 보류를
순수 Python API와 기존 레지스트리/실제 재생 작업자에 연결했습니다.
새 시험대의 학습 외 취득 기록 479개 창에서는 보류를 오답으로 세어 93.74%였습니다.
이후 최종 시험에서 별도 600+900 RPM 통합 후보를 고정해 1200 RPM을 평가했습니다.
정답률 11.04%, 정상 오경보 100%로 실패했습니다. 기존 속도별 모델과 다른 후보이며
상세 고정 절차/결과는 docs/FINAL_CROSS_SPEED_VALIDATION.rst를 참조하십시오.

구현 모듈
---------

* vibration/rotor_features.py: extract_rotor_features / RotorFeatures.
* vibration/two_stage.py: fit_two_stage / TwoStageDiagnostic / TwoStageStage.
* vibration/independent_data.py: IndependentRotorCatalog, 공개 자료 읽기 및 시험 접근 기록.
* ModelRegistry.use_two_stage / classify_window 및 ClassifierStage에 연결했습니다.
* VibrationAnalyzer는 단계의 analyze_window(result, readonly_values) 훅을 지원합니다.
  전압 입력은 기존 감도 변환을 마친 값이 전달됩니다. 기존 특징 전용 단계도 유지됩니다.

물리 특징
---------

4채널에서 총 156개를 추출합니다. 기존 28개 절대/대역 특징을 유지하고,
0.5X/1X/2X/3X/4X/5X/6X/8X/10X의 정규화 대역 에너지,
각 차수 대 1X 비율, 채널 간 RMS 비율과 차수별 에너지 비율을 추가했습니다.
회전수는 외부에서 공급해야 하며 고장 라벨이나 최대 피크로 추정하지 않습니다.
대역 반폭은 max(FFT 1.5 bins, 회전 기본주파수의 3%)입니다.
차수 대역이 겹치거나 Nyquist를 넘으면 거부/보류합니다.
현재 특징은 창 내 거의 일정한 RPM용입니다. 단계 연결 시 RPM 범위 변화가
평균의 3%를 넘으면 보류합니다. 가변속 각도 재표본화 특징은 별도 과제입니다.

relative 조합은 절대/대역 28개를 제외한 128개를 사용합니다. 공통 진폭 이득에
불변인 비율 특징을 포함하지만 모든 설치·전달 경로 변화에 불변인 것은 아닙니다.
absolute/relative/combined의 개발 비교 결과에 따라 기본값을 relative로 정했습니다.
다른 모듈에는 model.relative_features(features, scope=...)로 정상 기준 대비
전체 특징 변화량과 이름을 읽기 전용 NumPy 배열로 전달할 수 있습니다.
원시 특징 스키마는 vibration.rotor_features.v1, 정상 기준 변화 스키마는
vibration.rotor_normal_changes.v1로 구분합니다.

정상 우선 판정
--------------

정상 기준 적합, 정상 임계값 보정, 고장 학습의 취득 그룹은 서로 분리합니다.
알려진 정상 여부는 호출자가 확인해야 하며 모델 자신의 판정으로 정상 라벨을
만들지 않습니다. 정상 중심과 robust scale에 대한 변화 점수를 계산합니다.
별도 정상 보정 기록의 80%/99% 분위수를 정상 수용/이상 경계로 사용합니다.
이상 경계의 최소값은 정상 스케일 점수 1입니다.
이것은 상관된 창들의 경험적 분위수이며 현장 오경보 확률의 보증이 아닙니다.

* normal: 정상 기준 이내. 고장 종류 분류기를 호출하지 않습니다.
* hold: 정상 경계 부근 또는 장비/조건/단위/채널/RPM/샘플링/창 길이가 맞지 않음.
* fault_candidate: 정상에서 이탈하고 고장 특징 거리·후보 간 차이가 충분함.
* anomaly_unknown: 정상 이탈은 있으나 고장 종류 근거가 부족함.
* quality_hold: 입력 품질이 나빠 진단하지 않음.

asset_id, condition_id, unit, channel_names, sample_rate_hz, window_samples,
rpm_range를 모델 범위에 고정합니다. 필요하면 calibration_id와
sensor_installation_id도 범위에 포함해 변경 시 보류할 수 있습니다.
기존 RMS/ISO/정상 추세 경보와 진단 결과는 별도 출력이며 이 모듈이 다른
안전·진폭 경보를 억제하지 않습니다. operational_use=False, 기본 비활성을 유지합니다.

기존 Brito 개발 비교
-------------------

이미 결과를 확인한 Brito 20회는 모두 개발 자료로 명시했습니다.
정상 적합 1/3/6번, 정상 보정 9번, 고장 적합 2/4/5/7/8/10/11/12/15번,
평가 13/14/16/17/18/19/20번으로 그룹을 분리했습니다.
평가 2940개 창: 정상 420, 고장 2520. 정상 보정은 단 한 실험으로 약합니다.

* legacy 28개: 정상 오경보 0%, 고장 감지 1.43%. 대부분을 정상으로 보내 부적합.
* combined 156개: 정상 오경보 0%, 고장 감지 1.43%. 같은 이유로 기본값에서 제외.
* relative 128개: 정상 오경보 0%, 정상 수용 92.38%, 정상 보류 7.62%.
  고장 감지 71.87%, 고장을 정상으로 판단 12.02%, 고장 보류 16.11%.
  전체 고장 중 종류까지 정답 59.13%. 보류를 오답으로 세면 전체 정답 63.88%.

정상 17번은 388개 정상/32개 보류이며 고장 후보는 0개입니다.
그러나 정렬불량 13번은 301/420개가 정상으로 통과했습니다. 따라서 오경보 감소가
모든 고장의 해결을 뜻하지 않습니다. 이 비교는 새 맹검 성능이 아닙니다.

새 시험대의 학습 외 취득 그룹 검증
----------------------------------

CrossSpeed2026의 600/900 RPM에 대해 해당 시험대의 정상 기준과 고장 모델을
각각 적합했습니다. Brito에서 정한 relative/80%/99%/margin 0.10 조합을 유지했고
새 검증 결과에 맞춰 튜닝하지 않았습니다. 새 시험대에 무학습 적용한 결과가 아닙니다.

제공자 MS_600_900_to_1200 fold 0의 source_train 1888개 창만 적합/보정에 사용했습니다.
600 RPM: 정상 적합 13개 취득/253창, 정상 보정 2개 취득/40창, 고장 638창.
900 RPM: 정상 적합 14개 취득/278창, 정상 보정 2개 취득/40창, 고장 639창.
정상 보정 그룹은 source_train 내에서 미리 정한 2개씩이며 검증 그룹과 분리했습니다.

source_validation 24개 취득/479개 창은 학습과 보정에 들어가지 않았습니다.

* 정상 159개: 정상 129, 보류 30, 고장 경보 0.
* 고장 320개: 감지 320, 고장 종류 정답 320, 정상 오판 0, 보류 0.
* 보류를 오답으로 세는 전체 정답률 449/479 = 93.74%.
* 판단을 내린 비율 93.74%, 판단한 경우의 정답률 100%.

검증 대상 고장은 불평형·정렬불량 두 종류뿐입니다. 다른 고장, 새 속도, 실제 설비에
이 수치를 확장할 수 없습니다. 정상 검증 취득은 8개이고 보정도 속도별 2개뿐입니다.
연속 창 479개를 서로 독립된 실증 479회로 해석하면 안 됩니다.

추가 수집 자료와 시험 보존
--------------------------

저장 위치: data/normal_independent. 원본은 기존 자료와 구분해 보관했습니다.
총 23개 파일, 3,025,775,506 bytes(약 3.03 GB)를 수집했습니다.

Marra2024: https://zenodo.org/records/14388093
Amanda Lucatto Marra / Claudio Garcia, DOI 10.5281/zenodo.14388093, CC BY 4.0.
6개 ZIP, 총 1200개 LVM 기록. 정상 200, 고장 1000. 4개 가속도 채널과
광학 트리거, 6 kHz/6초. 명목 10/20/30/40 Hz.
각 압축본의 제공자 MD5·로컬 SHA256·전체 ZIP CRC를 검사합니다.
원시 가속도·트리거를 이용하는 대표 기록 검사는 속도 폴더별로 수행합니다.
정상 200개 기록은 전부 36000 x 4 형상·유한값·광학 트리거 간격을 추가 검사해 통과했습니다.
고장은 각 조건/속도의 대표 20개 기록을 검사했으며, 나머지 고장 파형의 수치 내용을
전수 검사했다고 주장하지 않습니다.
시간/적분 속도 열은 마지막 회전 이후 비어 있으므로 해당 빈칸 때문에 가속도
샘플을 삭제하지 않습니다. X_Value는 시간 대신 포인트 번호입니다.
제공자의 재조립/독립 취득 식별 정보는 충분하지 않아 독립 실험 수를 확정하지 않습니다.

CrossSpeed2026: https://data.mendeley.com/datasets/y8mv28hjwb/1
Yakoop Qasim / Hassan Almubarak, DOI 10.17632/y8mv28hjwb.1, CC BY 4.0.
9개 데이터 ZIP와 manifest/분할/체크섬/설명/라이선스 파일을 수집했습니다.
4채널, 25.6 kHz/1초, 정상 1169/불평형 1200/정렬불량 1176, 총 3545창.
제공자의 original_file/group_id와 acquisition-disjoint 분할을 유지했습니다.
600/900 RPM 개발 자료: 2367창, 119개 취득, 그중 정상 770창/39개 취득.
2367개 원본 MATLAB 파형의 유한값·형상·파일 SHA256·취득 메타데이터를 모두 검사했습니다.
전체 3545개 창의 제공자 signal SHA256에도 중복이 없었습니다.

1200 RPM 전체는 최초 수집 당시 새 최종 시험으로 보존했습니다: 1178창/59개 취득.
정상 399, 불평형 400, 정렬불량 379창입니다. 다운로드 체크섬·압축 무결성·목록만
확인했으며 수집 단계에서는 수치 배열을 열지 않았습니다. 이후 후속 최종 시험에서
고정한 통합 후보로 한 번 개봉했고, 1200 RPM의 학습·정규화·보정은 하지 않았습니다.
읽기 API도 기본적으로 접근을 거부하며, 명시적 모델 SHA256을 주고 열면
metadata/reserved_access.jsonl에 기록합니다. 이것은 실수 방지 절차이며 보안 장벽은 아닙니다.

새 정상 자료 총 1369개 기록/창 중 399개는 시험용이므로 정상 기준 학습에 쓰면 안 됩니다.
두 제공처의 진폭 단위·센서 교정 증명은 확인되지 않아 unit=unknown으로 유지했습니다.
절대 RMS를 서로 비교하거나 ISO mm/s/g 기준을 적용하면 안 됩니다.
공개 정상 자료는 사용자 실제 설비의 정상 기준·센서 설치·교정 자료를 대체하지 못합니다.
ready 폴더에는 기존 NPZ 가져오기로 읽을 수 있는 정상 예제 6개를 만들고
다시 가져와 검사했습니다. 학습/시험 구분에는 원본 manifest와 읽기 API를 사용하십시오.

API 및 재현
-----------

::

   import json
   from pathlib import Path
   from vibration import TwoStageDiagnostic, IndependentRotorCatalog

   model = TwoStageDiagnostic(json.loads(Path(
       'output/two_stage/model_relative.json').read_text(encoding='utf-8')))
   # samples: 해당 Brito 모델의 25000 x 4 파형, 동일 채널 순서.
   scope = {'asset_id': 'BritoBench', 'condition_id': 'nominal_1238rpm', 'unit': 'unknown'}
   result = model.analyze(samples, 25000, 1238, scope=scope,
                          channel_names=model.scope['channel_names'])

   catalog = IndependentRotorCatalog('data/normal_independent')
   normal_rows = catalog.rows(role='source_train', normal_only=True)
   values, metadata = catalog.load(normal_rows[0]['id'])
   # reserved_target_test 자료를 개발에 열지 마십시오.

examples/two_stage_composition.py는 새 장비의 정상 적합/정상 보정/확인된 고장
자료를 받아 모델을 만들고 VibrationAnalyzer에 연결하는 코드입니다.
기존 서비스에는 registry.use_two_stage(profile)로 연결할 수 있고, 저장 모델은
Storage.save('classifier', name, profile) 후 ModelRegistry.load로 읽을 수 있습니다.
자료 변경 시 기존 서비스가 model_enabled를 해제하는 동작은 유지됩니다.

::

   python scripts/collect_normal_independent.py
   python scripts/validate_normal_independent.py cross
   python scripts/validate_normal_independent.py marra
   python scripts/validate_normal_independent.py marra_normal
   python scripts/verify_two_stage.py
   python scripts/verify_external_source.py
   python scripts/verify_two_stage_service.py
   python -m unittest discover -s tests -v

스크립트는 개발용 source_validation을 다시 평가할 수 있지만 1200 RPM 시험은 열지 않습니다.
후속 최종 시험 절차는 docs/FINAL_CROSS_SPEED_VALIDATION.rst에 기록했습니다.
이미 개봉한 이번 자료로 재조정한 결과는 새 맹검 성능이 아닙니다. 현장 정상 수집 양식은
data/normal_independent/metadata/field_normal_collection_template.json에 있습니다.

검증 산출물
-----------

output/two_stage의 development_comparison.json, external_source_validation.json,
service_integration.json, model_relative.json, cross_speed_600_frozen.json,
cross_speed_900_frozen.json과 실행 로그를 확인하십시오.
데이터 원본/분할/체크섬/라이선스/무결성 보고서는 data/normal_independent/metadata에 있습니다.

데이터 없는 시험 67개, 기존 구현 58개, 물리 32개, ISO 363개: 총 520개 통과.
전체 재생 작업자·레지스트리·DB와 순수 API의 4개 실제 파형 결과가 일치했습니다.
새 자료 읽기 API의 결과를 loaded 재생으로 전달한 경우도 일치했습니다.
4채널/25 kHz/1초 창을 단계까지 계산한 로컬 30회 처리시간 p95는 약 27 ms였습니다.
실행별 최신 측정값은 service_integration.json에 있습니다.
휠 격리 실행에서도 새 특징과 정상 우선 진단이 동작했습니다.
이는 기능·수치 검증과 제한된 벤치 검증이며 장시간 실센서 실증·현장 오경보 보증은 아닙니다.
