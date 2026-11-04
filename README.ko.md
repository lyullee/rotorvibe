# RotorVibe — 회전기기 진동분석

Python 배열을 직접 연결해 파형·FFT·베어링 주파수·정상 기준·고장 후보를 계산하는
연구용 라이브러리입니다. 웹 서버를 띄우지 않고 다른 모듈의 함수·객체와 조립할 수 있습니다.
기존 `vibration` import를 유지하며 새 `rotorvibe` 진입점도 제공합니다.

**0.1.0a5는 P0~P2를 통합한 알파 릴리스입니다. 다른 장비와 베어링으로 옮기는 무학습 진단은 검증에
실패했습니다. 고장 자동 확정·자동 정지·잔여수명·ISO 적합성 인증을 제공하지 않습니다.**

## P0~P2 통합 검증과 개발 기록

P0는 프로파일·수치·공통 판정·배포 계약을 수정했고, P1은 정상 기준·취득 품질·가변속·
경보 평가·실시간 큐를 추가했으며, P2는 결과 격리·외부 연결·프로파일·누적 표시·기준 제공자·
수명 실험 API를 보완했습니다.

릴리스 준비 과정에서 전체 **224개 시험**, 두 깨끗한 환경의 문서 예제 **7개**, 기존 자료를
활용한 추가 공학 검증 **58개**를 통과했습니다. 이 수치를 과거 단계의 시험 수와 더하지 않습니다.
상세 과정과 재현 명령은 [통합 릴리스 기록](docs/RELEASE_0_1_0a5.md),
[개발 이력](docs/DEVELOPMENT_HISTORY.md), [후속 연구 안내](docs/CONTINUATION.md)에 있습니다.
게시 전 Windows/Linux·Python 3.11~3.13, 실제 외부 패키지, 설치본 검사를 통과하도록 CI를 구성했습니다.

새 독립 고장 정답률·현장 잔여수명 정확도는 여전히 검증되지 않았습니다.
48kHz·4채널 일괄 입력은 250ms 지연 기준을 17회 넘겼습니다. 새 P1 파형은 봉인 상태입니다.

## P2 세부 모듈과 입출력

각 함수의 전체 서명은 [API 명세](docs/API_REFERENCE.md), 사용 조건과 오류 처리는
[P2 사용 지침](docs/P2_GUIDE.md), 실행 결과와 남은 검증은 [검증 보고서](docs/P2_VERIFICATION.md)에 있습니다.
웹 서버 없이 Python 객체와 함수로 연결합니다.

| 모듈·API | 목적 | 입력 파라미터 | 반환값·연결 조건 |
|---|---|---|---|
| `AnalysisResult.detached()` / `VibrationAnalyzer` | 결과 소비자 간 수정 격리 | 기존 결과 / `stages`, `sinks` | 중첩 사전·배열·메타데이터의 독립 복사본. 각 단계·sink와 호출자 객체가 달라짐 |
| `process_adapter_info()` | 외부 패키지 호환 확인 | 설치된 배포 메타데이터 | 지원/설치 버전·호환 여부. 지원 버전은 `process-monitoring-toolkit==0.1.0` |
| `from_process_batch(batch, *, sample_rate_hz, clock_id, rpm=None)` | 외부 원시 파형 → 진동 입력 | 실제 `SignalBatch`, 샘플링률 Hz, 시계 ID, 독립 RPM 값/추적 배열 | `SignalBlock`. 균일 시간·공통 단위·단일 episode/mode 필요. 누락·혼합 조건·특징 배열은 거부 |
| `to_process_batch(results)` | 진동 특징 → 외부 분석 | 시간순 결과 목록, 동일 시계·취득 조건·출처·특징 정의 | `[창 수, 7×채널 수]` `SignalBatch`. 창 끝 시각·유효 마스크·원래 단위 기준을 전달 |
| `condition_evidence(result, *, asset_id)` | 중립적인 상태 관측 전달 | 분석 결과, 설비 ID | 독립 복사한 관측 사전. 사고 확률이 아님 |
| `create_profile`, `validate_profile`, `profile_digest` | 공통 프로파일 계약·해시 | 모델 payload, ID/종류/알고리즘/특징 정의, 전처리, 원본 학습 그룹, 교정 이력, 적용 범위 | 유한 JSON 봉투·SHA-256·호환 검사. 모델 변환이나 작성자 인증을 하지 않음 |
| `ProfileRegistry` | 버전별 프로파일 명시적 관리 | `register(envelope)`, `get/load(..., expected_contract, expected_scope)`; `load`에는 원래 모델 로더 | 복사된 봉투/원래 모델. ID 덮어쓰기 거부, 원래 수치 검증 유지 |
| `SpectrogramAccumulator` | 시간·주파수 이력 누적 | `hop_seconds`, `max_frames`, `max_age_seconds`, `max_frequencies`; `update(result)` | `snapshot()`에 Hz 축·구간 경계·창 시작/끝 초·유효성·누락·구간 ID. 개수와 시간으로 보관 제한 |
| `SpectrogramStage(accumulator)` | 분석기와 누적기 연결 | 누적기 | 작은 갱신 요약. 전체 이력은 누적기에서 조회하며 reset 시 제거 |
| `vibration.iso.RuleDocument / RuleProvider / MemoryRuleProvider` | 검토된 사용자 기준 공급 | 원래 `Rule`, 판본, 출처 URI/해시, 검토자/날짜, 설비·조건 범위 | 일치 문서 또는 없음. 중복·모호한 선택 거부. ISO 기준표는 배포하지 않음 |
| `evaluate_with_provider` / `IsoStage(rule_provider=...)` | 출처를 보존한 기준 평가 | 기준 식별자, `MachineContext`, 교정된 `Measurement`, 제공자. stage는 실제 입력 식별정보도 검사 | 위치별 구간 판정/보류, 검토 이력·문서 해시. 설비 전체 인증이 아님 |
| `vibration.experimental.ReferenceLifeEstimator` | 참고 수명 실험 분리 | 가속시험 이력, `experimental_enabled=True`, 현재까지의 관측 prefix | 벤치 종료까지의 유사도 참고값. 기존 `LifeEstimator`와 `LifeStage`도 기본 비활성화 |
| `vibration.experimental.LifeHistory / evaluate_life_predictions` | 완전·검열 수명 평가 | 원본 그룹, RPM·부하·단위·설치, 경과시간/RMS, 고장 또는 관측 종료 시각, 최종 예측·학습/교정 그룹 목록 | 수명별 동일 가중 MAE/RMSE, 경험적 구간 포함률, 검열 생존과의 양립 여부. 검열 자료의 정확한 고장 시간을 만들지 않음 |

스펙트로그램은 성긴 격자의 점 보간 대신 **주파수 구간 평균 PSD**로 변경했습니다.
기존 `frequencies`, `db` 키는 유지하고 구간 경계·표현 방식·단위를 추가했습니다.
좁은 피크가 사라지는 문제를 수정했으며, 표시 하한을 제외한 PSD 적분을 보존합니다.
분류 특징 계산식은 변경하지 않았습니다.

실행 예제는 [기본 연결](examples/p2_composition.py)과 [실제 외부 패키지 연결](examples/process_bridge.py)에 있습니다.
외부 0.1.0은 조회한 패키지 인덱스에서 설치되지 않아 검토한 Git 커밋을 고정해 설치합니다.
설치 명령은 [영문 README의 P2 절](README.md#p2-composition-apis--010a4)을 참고하세요.
코어를 사용할 때는 외부 패키지가 필요하지 않습니다.

**호환성 변경:** sink와 반환 결과의 `is` 동일성은 유지하지 않습니다. sink가 결과를
수정해 다음 소비자에게 전달하던 방식은 명시적인 stage 반환값으로 바꿔야 합니다.
참고 수명 실험은 명시적으로 켜야 하며, 현장 잔여수명 정답률·신뢰구간은 아직 검증되지 않았습니다.

## 설치와 시작

공개된 알파 버전을 명시해 설치합니다.

```console
python -m pip install rotorvibe==0.1.0a5
```

[GitHub 릴리스](https://github.com/lyullee/rotorvibe/releases/tag/v0.1.0a5),
[PyPI](https://pypi.org/project/rotorvibe/0.1.0a5/),
[Zenodo 버전 DOI](https://doi.org/10.5281/zenodo.23941252)를 같은 버전의 기준으로 사용합니다.
이전 0.1.0a1 배포 파일은 과거 기록으로 보존합니다.

Python 3.11 이상, NumPy 2.x, SciPy 1.13 이상이 필요합니다. 합성 파형으로 실행 가능한
전체 코드는 [영문 README](README.md)의 첫 계산 예제에 있습니다. 실제 사용 시에는
센서 원시 배열, 샘플링률, 물리 단위, RPM, 채널 방향, 장비·운전 조건 식별정보를 전달합니다.

`VibrationAnalyzer.analyze(block)`은 완성된 블록 하나를 계산합니다.
`push(block)`은 연속 입력을 분석 창으로 나누어 완료된 결과 목록을 반환합니다.
`stages`로 사용자 계산을 추가하고 `sinks`로 결과를 전달합니다. 스케줄링과 저장은
호스트가 맡습니다. 한 분석기 인스턴스를 여러 설비 스트림이 동시에 공유하지 않습니다.

## P1 운영 모듈 — 0.1.0a5에 포함

설치·RPM·부하별 정상 기준, 별도 원본을 사용하는 교정, 보류 조치 안내, 경보/성능 평가,
측정 RPM 기반 각도 분석, 수명주기와 유한 큐를 추가했습니다. **아직 게시하지 않은 로컬 후보**입니다.

| 모듈 / 진입점 | 목적·입력 | 출력·조건 |
|---|---|---|
| `AcquisitionInfo`, `AcquisitionQualityStage` | 실제 장비·센서·설치·교정 ID, 측정/교정기한 날짜, 채널·축, Hz·가속도 단위·센서 대역·안티앨리어싱·RPM 출처와 확인 플래그 | accepted/hold/quality_hold와 누락 항목. 호스트 선언의 일관성을 검사하며 설치를 인증하지 않음 |
| `NormalRecording` / `.from_plan` | 원본 기록/취득 그룹, 관측 결과, 정상 확인, normal_fit/normal_calibration 역할, 선택적 원본 SHA256 | 최종 시험 역할·중복 그룹·제공된 중복 해시 거부. 학습과 교정 각각 원본 그룹 2개 이상 |
| `fit_normal_reference` | 학습/교정 원본, name·rpm_range·load_range·quantile, time/angle 표현·각도 grid; source의 load_unit 필수 | 그룹 동일 가중 중앙값/MAD 기준과 원본별 최대 점수의 교정 분위수. 현장 오경보율 보장 아님 |
| `NormalReferenceBank`, `ReferenceStage` | 장비·설치·교정·축/채널·대역·단위·조건·RPM·부하가 맞는 프로파일과 현재 결과 | normal/hold/anomaly_unknown, normal_score·문턱값·참조 이름. 미등록·중복 범위·운전점 불일치는 보류 |
| `GuidanceStage`, `hold_guidance` | 앞 모듈의 상태·보류 이유 | 필요한 조치 코드·대상 파라미터. 설비 이름을 임의 변경해 범위를 우회하지 않음 |
| `angle_resample`, `angle_features` | N 또는 N×C 파형·Hz·샘플별 측정 RPM, samples_per_revolution=256·revolutions=16 | 위상 적분·저역통과 후 각도 배열과 채널당 23개 특징. 속도 범위/대역/회전 수 부족 거부 |
| `fit_angle_fault_discriminator`, `AngleFaultDiscriminator`, `AngleFaultStage` | 별도 각도 특징으로 새로 학습한 모델·원본 그룹·측정 속도 출처. 앞 게이트의 이상 확인과 취득 품질 필요 | 실험적 고장 후보, 기본 비활성. 기존 고정속도 모델 자동 전환 없음. 새 실측 성능 검증은 남아 있음 |
| `ValidationObservation`, `evaluate_observations` | 원본/취득/설비/clock·초 단위 구간·정답·실제 파이프라인 판정·경보·선택적 고장 발생시각 | 정상 수락/판정 범위·지원 정상 FPR·무조건/조건부 종류 정답률·고장 전용 head 별도 정확도·시간당 경보·탐지 지연. 분모 0은 None |
| `DatasetRecord`, `ValidationPlan`, `FrozenEvaluation` | 실제 원본/세션/설치/시험대와 역할·정답·SHA256, 동결 모델/전처리 해시 | 역할 누출 거부·덮어쓰기 없는 동결·개봉 전 접근 기록·해시 확인 BytesIO로 loader 호출. 재사용은 replay 표시; 외부 코드의 임의 읽기를 막는 보안 샌드박스는 아님 |
| `VibrationAnalyzer.reset` | reset_stages=False, preserve_profiles=True | 기존 reset은 버퍼만 초기화. 명시적 stage 초기화 또는 push의 구간 단절 시 경보·수집 상태 초기화. 공유 bank 삭제 없음 |
| `RealtimeProcessor` | max_pending·max_chunk_samples·max_pending_bytes, reject/drop_oldest, 선택적 latency_budget_seconds; 호스트가 process_next/drain 호출 | 유한 큐·완성 결과·누락/거절/실패·처리/대기/전체 지연·예산 초과 계수. 소비자 1개, 자동 worker나 엄격한 실시간 보장 없음 |

실행 가능한 전체 연결 예제는 [영문 README의 P1 예제](README.md)와
[examples/p1_pipeline.py](examples/p1_pipeline.py)에 있습니다.
취득 품질→정상 기준→공통 판정→조치 안내→경보→유한 큐를 연결하고, 설치가 바뀌면 보류되는지 확인합니다.
예제의 합성 기록과 확인 플래그를 실제 센서 증빙처럼 사용하면 안 됩니다.

고정속도 정상 기준은 창 내 RPM 변화율 <=3%가 필요합니다. 단일 채널 angle 정상 기준은
representation='angle'과 실제 측정 RPM을 요구하며, 별도 특징 정의·grid를 저장합니다.
원시 속도는 result.rpm_trace로 전달하고 include_features=False JSON에서는 제외합니다.
기존 고정속도 모델은 지원하지 않는 가변속 입력을 계속 보류합니다.

preserve_profiles=False는 BaselineStage의 소유 프로파일을 해제합니다. ReferenceStage는
공유 bank를 삭제하지 않고 사용을 중단하며 activate()로 다시 연결합니다.
analyze()의 스트림 경계는 호스트가 reset으로 선언하고, 자동 구간 검사는 push()에 적용합니다.

성능 시험에서는 48 kHz·4채널의 4초 분량 일괄 입력이 0.25초 지연 예산을 초과했습니다.
이를 통과로 표시하지 않았습니다. 새 외부 자료는 파형 개봉·학습·튜닝에 사용하지 않은
후보 상태이며 실제 고장 종류 정답률 개선을 입증한 상태는 아닙니다.
자세한 입력·출력·실행 절차는 [P1 사용 설명서](docs/P1_GUIDE.md),
검사 결과와 남은 실증은 [P1 검증 보고서](docs/P1_VERIFICATION.md)에 있습니다.

## P0 수정과 공통 입출력 계약 — 0.1.0a2 후보

이 작업본에는 앞선 0.1.0a2 후보의 P0 수정도 포함됩니다. 이미 공개된 PyPI/Zenodo **0.1.0a1** 파일은
그대로이며, 아래 API는 0.1.0a5 또는 일치하는 소스 태그로 설치합니다.
이번 수정은 새 실측 데이터 학습이나 현장 진단 성능 합격을 의미하지 않습니다.

| 모듈 / API | 입력 변경 | 출력·호환성 |
|---|---|---|
| `FaultDiscriminator(profile)` | 로딩 시에도 필수 필드, asset_id/condition_id, 교정 가속도 단위 g/m/s^2, 유한 JSON scope, 고유 특징 이름·순서·mode·indices, 원본 취득 그룹을 검사. 클래스별 원본 그룹 2개 이상, operational_use=False 요구 | 기존 정상 학습 생성 profile은 유지. 예전에는 통과하던 잘못된 profile은 ValueError로 거부 |
| `fit_fault_discriminator(...)` | 로더와 같은 scope·특징 계약 적용. 특징 절댓값 <=1e100, 모델 인자 유한·범위 검사 | 반환 profile을 로더로 다시 검사. 알고리즘 ID와 정상 범위 계산식 유지 |
| `FaultDiscriminator.predict(features, rpm, *, scope)` | 호출 scope 누락/오류는 hold. 비유한·범위 초과 특징이나 거리 중간 계산 넘침은 ValueError | 유한 결과 또는 명시적 오류. NaN/Infinity를 포함한 결과를 반환하지 않음 |
| `normalize_decision(output, *, source_stage, valid=True)` | stage 사전·생산자 이름·bool 품질. score/normal_score 인식, 둘이 있으면 값 일치 요구. 상대 일치도를 점수로 추정하지 않음 | 아래 vibration.decision.v1 공통 사전. 원래 stage 출력과 문턱값은 변경하지 않음 |
| `DecisionStage(source_stage)` | 생산 stage 다음, 경보 등 소비 stage 앞에 연결. 생산자 누락은 명시적 hold | 호스트가 정한 이름으로 공통 사전 추가. 기존 생산 stage 필드는 유지 |
| `AlarmStage(..., expected_score_name=None)` | score 또는 normal_score 정의를 선택적으로 고정. 기존 score_stage·문턱값·시간 인자는 유지 | 공통 사전 지원. 보류·무효·점수 정의 불일치는 unavailable + retained_level. 기존 score 콜백 유지, 보류에 남은 점수로 경보 해제하지 않음 |

공통 사전의 출력 필드:

| 필드 | 자료형·의미 |
|---|---|
| schema, source_stage | vibration.decision.v1, 생산 stage 이름 |
| status | normal / scored / candidate / anomaly_unknown / fault_candidate / hold / invalid |
| score, score_name, score_unit | 유한한 음이 아닌 수 또는 None, 원래 score/normal_score 정의, 무차원. 점수 없는 고장 전용 head에 점수를 만들지 않음 |
| label, anomaly | 선택적 label, bool/None 이상 증거. Gaussian known_candidate는 candidate로 옮기며 이상을 확정하지 않음 |
| alarm_eligible | 보류·무효가 아니고 수치 점수가 있을 때만 True. 경계 보류 점수는 표시할 수 있어도 경보에는 사용하지 않음 |
| reason, operational_use | 비어 있지 않은 이유, 연구용 계약에서 False |

**정상 기준 score와 조건부 모델 normal_score의 문턱값을 서로 바꿔 쓰면 안 됩니다.**
선택한 모델에 맞게 warning/danger를 교정하고 expected_score_name으로 정의를
고정할 수 있습니다. 어댑터가 문턱값을 자동 보정하지는 않습니다.

실행 예제는 [영문 README의 baseline→decision→alarm 예제](README.md)에 있으며,
정상 기준 수집·점수·경보 연결 후 다른 설비 입력이 보류되는 동작까지 포함합니다.

배포 workflow는 초기 압축본 복원 방식에서 **명시적 버전 태그 기반 빌드**로 교체했습니다.
태그/패키지/진입점 버전 일치, HEAD 일치, 작업본 청결을 검사합니다. 소스 복원·commit·push는
수행하지 않습니다. 일반 브랜치 push는 게시하지 않으며, 버전 태그 push 또는 명시적
release dispatch만 게시 경로를 시작합니다. 후보 검증과 실제 게시 상태는
[P0 검증 보고서](docs/P0_VERIFICATION.md)에 구분해 기록합니다.

## 단위 모듈 선택표: 목적 · 입력 · 출력

**다른 Python 시스템과 연결할 때 이 절부터 확인하세요.** `rotorvibe`는 대표 API를
재공개하는 진입점이고, 세부 모듈은 아래 `vibration.*` 경로로 import합니다.
`N`은 샘플 수, `C`는 채널 수, `W`는 관측 창 수, `F`는 특징 수입니다.
핵심 계산에는 웹 서버·DB·외부 서비스가 필요하지 않습니다.

```text
호스트 센서/DAQ -> SignalBlock + AnalysisConfig -> VibrationAnalyzer
  -> DSP/베어링 주파수 -> 순서 있는 stages -> AnalysisResult -> 호스트 sinks
                         정상 기준 -> 경보
                         정상/이상 게이트 -> 조건부 고장 종류 분류
                         측정량 -> 사용자 제공 기준 평가
```

### 신호 계약과 핵심 계산

| 단위 모듈 / 진입점 | 목적 | 입력 파라미터 | 출력 / 연결 대상 |
|---|---|---|---|
| [`contracts.SignalBlock`](vibration/contracts.py) | 신호·단위·시간·식별정보를 하나의 계약으로 전달 | `values[N]` 또는 `[N,C]`, `sample_rate_hz`, `unit`, 시간/채널/RPM/유효성/metadata | 복사 후 읽기 전용인 `[N,C]` 입력 블록 |
| [`config.AnalysisConfig`](vibration/config.py) | 분석 창·교정·대역·채널 설정 | 아래 설정 파라미터 표 참조 | 검증된 설정; `create(dict)`, `to_dict()`, `signature()` |
| [`core.VibrationAnalyzer`](vibration/core.py) | 동기 계산 및 연속 입력 창 분할 | `config=None`, keyword `bearing_provider=None`, `stages=None`, `sinks=()` | `analyze(block)` -> 결과 1개; `push(block)` -> 완성된 결과 목록; `reset()` -> 버퍼 초기화 |
| `core.analyze_signal(values, config=None, **block_options)` | 한 번의 함수 호출로 창 하나 계산 | 배열, 설정, SignalBlock 부가 파라미터 | `AnalysisResult`; 매번 새 분석기를 만들므로 스트림 상태 미보존 |
| [`dsp.spectrum(x, fs, window='hann')`](vibration/dsp.py) | FFT와 PSD | 1차원 파형, 샘플링 Hz, 창 함수 | `(주파수[Hz], 진폭[입력단위], PSD[입력단위²/Hz])` 배열 |
| `dsp.channel_features(data, fs)` | 공통 특징 추출 | `[N,C]` 파형과 Hz | `(names, vector)`; 채널당 7개: log RMS·log crest·첨도·4개 log 대역 비율 |
| `dsp.analyze(data, config, rpm_trace=None, bearing_frequencies=None, *, native=False)` | 지표·엔벨로프·오더·고조파 증거 | 물리 단위 파형, 검증 설정, RPM 배열, 주파수 사전 | 아래 출력 계약의 DSP payload 사전; 교정/품질/식별 검사는 상위 분석기 사용 |
| `dsp.waveform(...)`, `compact_spectrum(...)` | 표시용 배열 축약 | 파형/주파수/진폭 배열, 최대 점 수, `native` | `{x,y}`; `native=True`면 전체 배열, 표시 축약값을 정량 측정 입력으로 쓰지 않음 |
| `dsp.peak_evidence(f, amplitude, target, tolerance_ratio, resolution, *, spacing_hz=None)` | 예상 주파수 주변 피크 확인 | Hz·진폭 배열, 목표 Hz·허용 비율·분해능·고조파 간격 | 증거 사전 또는 `None`; 분리 불가능한 검색 대역을 명시 |
| [`geometry.BearingGeometry`](vibration/geometry.py) | 이상 운동학 베어링 결함주파수 | `rolling_elements`, `rolling_diameter`, `pitch_diameter`, `contact_angle_deg=0`; `.frequencies(rpm)` | `{BPFI, BPFO, FTF, BSF, 2BSF}` Hz; 두 지름 단위 동일, 각도 도, 미끄럼 모델 없음 |
| `geometry.BearingMap(geometries)` | 사용자 베어링 목록 주입 | `{형번: BearingGeometry}`, `.frequencies(id,rpm)` | Hz 사전; 분석기 `bearing_provider`와 `config.bearing_id`로 연결 |
| [`ports`](vibration/ports.py) | 사용자 모듈 구조적 인터페이스 | provider `.frequencies(id,rpm)`, stage `__call__(result)`, 선택적 `.analyze_window(result, readonly_values)`, sink `__call__(result)` | provider -> Hz 사전; stage -> 이름 있는 payload; sink -> 호스트 부수효과, 반환값 미사용 |

### 정상 기준·경보·고장 후보

학습용 특징은 `[W,F]`, `groups[W]`는 **원본 취득 기록 식별자**입니다. 창을 무작위로
섞은 번호가 아닙니다. `scope`는 실제 장비·센서·운전 조건의 적용 범위입니다.
정상 기준 학습, 문턱값 교정, 최종 시험에는 서로 다른 원본을 사용해야 합니다.
프로파일은 명시적인 사전이며 훈련 완료 모델을 패키지에 내장하지 않습니다.

| 단위 모듈 / 진입점 | 목적 | 입력 파라미터 | 출력 / 연결 대상 |
|---|---|---|---|
| [`baseline.BaselineStage(config, *, profile=None)`](vibration/baseline.py) | 정상 기준 수집·상대 점수 | 설정, 선택적 정상 profile; `.begin(name='normal', windows=60)` 후 유효 결과 입력 | `status`, 지원될 때 `score`, 기여 특징; `.export_profile()` -> 사전 또는 `None` |
| [`alarm.AlarmStage`](vibration/alarm.py) | 관측 시간 기반 경보 지속/해제 | keyword `score_stage='baseline'`, `warning=3`, `danger=6`, `persistence_seconds=2`, `release_seconds=3`, `max_gap_seconds=2`; 이전 stage 점수와 시간/유효성 | `level`, `pending`, `score` 또는 unavailable/retained_level; 자동 정지 명령 아님 |
| [`rotor_features.extract_rotor_features`](vibration/rotor_features.py) | 회전수 기준 고조파·방향 비율·레벨 | `values`, `sample_rate_hz`, `rpm`, keyword `channel_names=None` | `RotorFeatures(names, values, sample_rate_hz, rpm, channel_names, sample_count, schema)` |
| [`classifier.fit_gaussian`](vibration/classifier.py) / `GaussianClassifier(profile)` | 대각 공분산 Gaussian 기준 분류 | `x[W,F]`, `y[W]`, `groups`; `variance_floor=0.25`, feature schema; 추론 `.predict(vector)` | 학습 profile / label·matches 사전; 보정된 고장 확률 아님 |
| [`two_stage.fit_two_stage`](vibration/two_stage.py) | 정상 게이트와 고장 원형 학습 | `normal_fit`, `normal_fit_groups`, `normal_calibration`, `calibration_groups`, `faults`, `fault_labels`, `fault_groups`; `feature_names`, `scope`, mode·quantile·margin | profile; `TwoStageDiagnostic(profile)`로 사용 |
| `TwoStageDiagnostic` / `TwoStageStage(model)` | 정상 먼저 판단한 뒤 고장 후보 | `.predict(features, *, scope)` 또는 `.analyze(values, sample_rate_hz, rpm, *, scope, channel_names=None)`; stage는 결과와 원시 창 | `status`, `label`, 이상 증거·보류 사유를 포함한 사전 |
| [`conditioned.fit_conditioned`](vibration/conditioned.py) | RPM별 정상 기준 학습 | `normal`, `normal_rpm`, `normal_groups`, `calibration`, `calibration_rpm`, `calibration_groups`, `faults`, `fault_rpm`, `fault_labels`, `fault_groups`; `feature_names`, `scope`, mode·보간·RPM 간격·불확도·margin | profile; `ConditionedDiagnostic(profile)`로 사용 |
| `ConditionedDiagnostic` / `ConditionedStage(model)` | 운전속도에 맞는 정상/이상 게이트 | `.predict(features, *, scope)` 또는 `.analyze(values, sample_rate_hz, rpm, *, scope, channel_names=None)` | 정상·이상·보류 사전; 적용 범위 밖은 보류, 다음 고장 head에 연결 |
| [`fault_discrimination.fault_features`](vibration/fault_discrimination.py) | 헐거움·불평형·정렬불량 형태 특징 | `values`: **정확히 2초, 단일 채널**, `sample_rate_hz`, `rpm` | `(names, vector[61])`; 일정 속도 연구용 특징 |
| `fit_fault_discriminator` | 조건부 고장 종류 원형 학습 | `x`, `labels`, `rpms`, `groups`; keyword `names`, `scope`, `mode='morphology'`, `rpm_penalty=1`, `margin=0.03` | 고장 전용 profile; 정상 클래스 없음 |
| `FaultDiscriminator(profile)` | 이상이 확인된 창의 고장 종류 | `.predict(features, rpm, *, scope)` 또는 `.analyze(values, sample_rate_hz, rpm, *, scope)` | `hold` / `anomaly_unknown` / `fault_candidate`와 label·거리 증거 |
| `FaultDiscriminationStage(model, gate_key='conditioned')` | 게이트 후 고장 head 순서 강제 | 이전 `payload[gate_key]['anomaly'] is True`, 유효 창·적용 범위·RPM 변화율 <=3% | 고장 후보 사전; 조건 미충족이면 이유와 함께 보류 |
| [`stages.ClassifierStage(registry)` / `LifeStage(estimator, experimental_enabled=False)`](vibration/stages.py) | 호스트 객체를 stage로 연결 | 주입한 registry/estimator와 결과/원시 창 | 분류/수명 payload; 생성자에서 자동 학습하지 않음 |
| [`models.ModelRegistry(storage, catalog)`](vibration/models.py) | 선택적 모델 저장·학습 작업 | 저장소/자료목록, `load(name)`, `use_two_stage(profile)`, `use_conditioned(profile)`, `train(name)` | 분류 결과/작업 상태; `.close()` 필수 |
| `models.LifeEstimator(catalog, experimental_enabled=False).estimate(source)` | PRONOSTIA 참고 수명 유사도 | 학습용 완전 수명 catalog, 현재까지의 dataset·record_id·RPM·baseline/recent RMS 이력 | 거부 상태 또는 실험적 `remaining_seconds`·참고 범위·매칭; **현장 잔여수명 검증 미완료**, 범위는 신뢰구간 아님 |

### 측정량과 사용자 제공 평가 기준

**공개 `vibration.iso`에는 ISO/KS 기준표·기계 분류별 기준 선택기가 없습니다.**
`available_standards()`는 `()`입니다. 평가 기준은 사용자가 적법하게 확보해 주입합니다.

| 단위 모듈 / 진입점 | 목적 | 입력 파라미터 | 출력 / 연결 대상 |
|---|---|---|---|
| [`iso.contracts.MachineContext`](vibration/iso/contracts.py) | 평가 대상과 운전 상태 명시 | 필수 `asset_id`, `machine`; `operating_state`, `condition_id`, `location` 및 선택적 기계 정보 | 검증된 context; 부가 기계 분류 필드가 규정 기준 선택 기능을 켜지는 않음 |
| `Measurement` | 측정점의 물리량 계약 | `value`, `quantity`, `unit`, `statistic`, `frame`, `band_hz`, `duration_s`, `axis`, `point_id`; 교정·취득 확인·시간·출처 | 관측 객체; `.canonical_value()` -> 가속도 m/s²·속도 mm/s·변위 µm |
| `Rule` | 사용자 기준 계약 | `standard`, `key`, `quantity`, `statistic`, `frames`, 오름차순 `limits`, `band_hz`, `source_page`, `source_clause`; zones·최소 시간·notes | 검증 기준 객체/사전; RMS와 피크를 임의 변환하지 않음 |
| [`iso.measurements.measure_waveform`](vibration/iso/measurements.py) | 파형에서 대역별 물리량 측정 | `values`; keyword `sample_rate_hz`, `input_unit`, `quantity`, `statistic`, `frame`, `band_hz`, `point_id`, `axes`; 교정/취득 플래그·시간·clock·선택적 order/filter bandwidth | 채널별 `list[Measurement]`; DFT 대역 측정, 계측기 인증 아님 |
| `energy_equivalent_average(measurements)` / `EnergyEquivalentAccumulator(period_s).push(measurement)` | 시간 가중 RMS 평균 | 단위·측정점·대역·시간이 호환되는 RMS 관측, 누적 기간 초 | 평균 `Measurement`; 누적 기간 전에는 `None` |
| [`iso.evaluation.evaluate`](vibration/iso/evaluation.py) | 관측 하나와 사용자 한계값 비교 | `standard`, `context`, `measurement`, keyword `custom_rule=None` | `status`, `zone`, 표준화 값/단위·기준 출처; 기준 누락/조건 불일치면 zone 없음 |
| `aggregate(results)` | 측정점 평가 범위 취합 | 같은 장비·기준·조건의 비어 있지 않은 평가 목록 | 취합 사전; `whole_machine_compliance=False` |
| [`iso.stage.IsoStage`](vibration/iso/stage.py) | 파형→측정→평가 stage | `standard`, `context`; keyword `custom_rule`, `point_id`, `axis='radial'`, `calibrated=False`, `acquisition_verified=False` | 평가 payload; 단일 채널 입력, 기준 없으면 indeterminate |

### 다른 시스템 연결과 선택적 실행 모듈

| 단위 모듈 / 진입점 | 목적 | 입력 파라미터 | 출력 / 관리 책임 |
|---|---|---|---|
| [`adapters.from_process_batch`](vibration/adapters.py) | 외부 배치를 신호 블록으로 변환 | `batch`의 time_s·values·동일 units·channels·origin·metadata; keyword `sample_rate_hz`, `clock_id`, `rpm=None` | `SignalBlock`; 혼합 episode/mode는 먼저 분리 |
| `adapters.to_process_batch(results)` | 결과들을 특징 배치로 전달 | 시간축·분석 설정·특징 순서가 호환되는 결과 목록 | 외부 `process_monitoring.SignalBatch[W,F]`, 창 종료 시각 사용; **해당 외부 패키지는 호스트가 별도 설치** |
| `adapters.condition_evidence(result, *, asset_id)` | 타 시스템에 상태 증거 전달 | 결과와 명시적 설비 ID | `vibration.condition-evidence.v1` 사전; 사고 확률·빈도 아님 |
| [`datasets.DatasetCatalog`](vibration/datasets.py) | 로컬 자료 검색·읽기·가져오기 | 로컬 파일, `search`, `details(id)`, `load(id,snapshot=0)`, `imported(filename,payload,fs,unit,channels_axis,skip_columns)` | 목록/메타데이터 또는 `(배열, metadata)`; 자료 자동 다운로드 없음 |
| [`independent_data.IndependentRotorCatalog`](vibration/independent_data.py) | 원본 단위로 분리한 회전기기 자료 읽기 | root·manifest, `rows(*, role=None, normal_only=False)`, `load(record_id, *, frozen_model_sha256=None)`, Marra archive 메서드 | 원본 ID / 파형·metadata; 원본 단위 분리 유지 |
| [`condition_data.UosRotorCatalog` / `ExposedCrossSpeedDevelopment`](vibration/condition_data.py) | 조건부 모델 연구 자료 접근 | 로컬 root; UOS는 `rows(role=None)`, `load(record_id, *, frozen_model_sha256=None)` | 목록 또는 `(배열, metadata)`; 이미 개봉한 자료를 새 holdout으로 간주하지 않음 |
| [`client.VibrationClient`](vibration/client.py) | HTTP/UDP 신호 송신 | `base_url`, `token`, `timeout`; `start(sample_rate_hz,channels,unit,rpm,**configuration)`, `push(samples,**kwargs)`, `push_udp`, `stop` | 서버 JSON/패킷 응답; 네트워크·재시도는 호스트 책임 |
| [`engine.Engine(storage,catalog,bearings,models)`](vibration/engine.py) | 선택적 수집/재생 worker | 주입 서비스, `configure`, `live`, `ingest(payload)`, `replay(id,speed,loop,...)` | 상태·이벤트·이력; `EventHub` 이벤트 분배, `Ring` 버퍼; `.close()` |
| [`storage.Storage`](vibration/storage.py) | 선택적 SQLite 저장 | 세션·설정·프레임·이벤트·이름 있는 profile, `save/get/history` | ID·저장 행·조회 자료; writable runtime 사용, `.close()` |
| [`server.Application` / `rotorvibe-monitor`](vibration/server.py) | 선택적 HTTP/SSE/UDP 대시보드 | `--host`, `--port`, runtime/project 경로·설정된 인증 | 로컬 UI/서비스; 직접 계산 API와 별개, 자원 종료 필요 |
| [`bearings.Bearings`](vibration/bearings.py), [`bootstrap`](vibration/bootstrap.py) | 대시보드용 목록·경로 지원 | 별도 로컬 베어링 자료와 프로젝트/runtime 경로 | 서비스 조회·경로; 이식 가능한 직접 API는 Geometry/Map 사용 |

### 실제 입력 파라미터 계약

`analyze`는 `N == round(sample_rate_hz * window_seconds)`인 **정확히 한 창**을 요구합니다.
`push`는 임의 길이의 비어 있지 않은 청크를 받고 완성된 창만 반환합니다.
블록과 설정의 샘플링률·채널 수·입력 단위가 같아야 합니다.

| `SignalBlock` 파라미터 | 자료형 / 기본값 | 의미·단위 |
|---|---|---|
| `values` | 필수 `[N]` / `[N,C]` 배열 | 샘플, 1..16채널; 복사 후 읽기 전용 |
| `sample_rate_hz` | 필수 양의 유한 수 | 실제 샘플링 Hz |
| `unit` | `'unknown'` | `g`, `m/s^2`, `V`, 또는 단위 미확인 |
| `start_time_s` | `0.0` | 선언한 clock에서 첫 샘플 시각, 초 |
| `clock_id`, `episode_id` | `'sample_clock'`, `'default'` | 시간 기준과 연속 취득 구간 ID; 실제 사용 시 명시 |
| `channels` | `()` | 열 순서와 일치하는 고유 센서/축 이름; 생략하면 자동 생성 |
| `valid` | `None` 또는 bool `[N]` | 샘플 유효성; 비유한 값도 무효 처리 |
| `rpm` | `None`, 수 하나 또는 `[N]` | 외부에서 측정한 회전수 rev/min; config보다 우선 |
| `sequence` | `None` 또는 음이 아닌 정수 | 연속 패킷 순서 |
| `metadata` | `{}` | 실제 asset/sensor/condition/calibration/frame 식별정보, 결과 source로 전달 |

| `AnalysisConfig` 파라미터와 기본값 | 목적·단위 |
|---|---|
| `sample_rate_hz=12000`, `channels=1`, `channel=0` | Hz·총 채널 수·스칼라 지표/스펙트럼용 0기반 채널 번호; 특징은 전체 채널 사용 |
| `window_seconds=1`, `hop_seconds=0.25` | 창/갱신 간격 초; 창 256..2,000,000샘플, hop >=0.02초·창 이하 |
| `unit='unknown'`, `input_representation='physical'` | 출력 가속도 단위 g/m/s²/unknown; 입력 표현 physical/volts |
| `sensitivity_mv_per_g=None`, `conditioner_gain=1`, `bias_voltage_v=0`, `calibration_id=''` | 전압 교정 `(V-bias)/(감도/1000*gain)`; 감도 양수 목록 1개 또는 C개, volts 모드는 교정 후 단위 필수 |
| `rpm=None`, `bearing_id=None`, `condition`, `load=None` | rev/min·사용자 베어링 ID·운전조건 이름·선택적 부하 정보 |
| `window='hann'` | FFT 창, hamming/boxcar도 지원 |
| `envelope_low_hz=500`, `envelope_high_hz=5000` | 엔벨로프 반송 대역 Hz, Nyquist 미만; 저속 샘플링이면 별도 조정 |
| `velocity_low_hz=10`, `velocity_high_hz=1000` | 속도 적분 대역 Hz; 출력 mm/s RMS |
| `peak_tolerance_ratio=0.03` | 주파수 탐색 상대 허용오차, 분해능 조건도 적용 |
| `warning_score=3`, `danger_score=6`, `persistence_seconds=2`, `release_seconds=3` | 선택적 서비스 경보 설정; 직접 API의 AlarmStage는 자체 인자를 명시해 연결 |
| `rms_warning=None`, `rms_danger=None`, `clip_abs=None` | 선택적 서비스 RMS 기준·절대 클리핑 기준, 설정 단위; clip 검사는 직접 core에도 적용 |
| `model_enabled=False`, `order_tracking=True` | 선택적 서비스 분류 활성화·RPM trace 오더 재표본화; 직접 API는 모델 stage를 명시적으로 연결 |

### 출력 파라미터 계약

| `AnalysisResult` 필드 / payload | 의미·단위 |
|---|---|
| `start_time_s`, `end_time_s`, `clock_id`, `episode_id`, `channels` | 창 식별; 종료 시각은 미포함(exclusive), 선언 clock 기준 초 |
| `valid`, `payload['quality']['flags']` | **수치 계산 품질이지 정상 판정 아님**; 무효 창에는 수치 DSP 결과 없음 |
| `metrics` | AC rms·peak·peak_to_peak·mean·rms_raw는 설정 단위; crest_factor·Pearson kurtosis·skewness는 무차원; velocity_rms_mm_s, envelope_rms, band_power(단위²) |
| `payload['spectrum']`, `['psd']`, `['envelope_spectrum']` | `{x,y}` 배열; x=Hz, y=진폭·단위²/Hz·엔벨로프 진폭 |
| `payload['waveform']` | 상대 시간 초와 교정된 선택 채널 샘플 `{x,y}` |
| `payload['spectrogram']` | 한 창의 frequencies와 log-PSD db 행; **시간별 행을 호스트가 쌓아** 스펙트로그램 구성 |
| `payload['rpm']`, `['rpm_variation_ratio']`, `['frequency_resolution_hz']`, `['order_spectrum']` | rev/min·무차원 변화율·Hz 간격·선택적 cycles/revolution 오더와 재표본화 mode |
| `payload['bearing_markers']`, `['rotation_markers']`, `['diagnosis']` | 예상/관측 Hz·피크 대비·중복 가능한 후보 증거, 확정 진단 아님 |
| `features`, `feature_names` | 특징 벡터와 정확한 순서/이름; profile schema·설정과 함께 전달 |
| `payload[stage_name]` | 정상 점수·경보·진단·사용자 기준 등 stage별 사전 |
| `metadata['measurement']`, `metadata['source']` | 실제 적용된 설정·호스트 원본 metadata |
| `to_dict(include_features=True)` | JSON 호환 `vibration.analysis.v1`; False면 밑줄로 시작하는 내부 특징 필드 제외 |

stage는 넣은 순서로 실행하고 앞 stage 출력을 다음 stage가 읽습니다. 원시 창 stage는
표시용 축약 파형 대신 교정된 전체 배열을 받습니다. sink는 stage 완료 후 동기 실행됩니다.
예외는 호출자에게 전달되므로 재시도·저장 중복 방지는 호스트가 맡습니다.
`hold`나 점수 누락을 정상/위험도 0으로 바꿔 연결하지 마세요.

모든 공개 생성자·메서드의 정확한 전체 시그니처와 dataclass 필드는
[전체 API 레퍼런스](docs/API_REFERENCE.md)에 있습니다. 여기 표가 모듈 선택과 연결의
기준이고, [사용 설명서](docs/USER_GUIDE.md)는 실행 순서를 설명합니다.

## 계산 결과를 해석하는 방법

- 파형 품질·단위·시간축이 유효해야 숫자의 의미를 해석할 수 있습니다.
- 정상 기준이 없거나 장비/설정이 다르면 `hold`입니다. 정상 판정이 아닙니다.
- `anomaly_unknown`은 이상은 감지했지만 고장 종류의 근거가 부족한 상태입니다.
- `fault_candidate`는 후보이며 물리 원인 확정이 아닙니다. 점수는 고장 확률이 아닙니다.
- 베어링 주파수는 명시한 내부 치수와 이상 운동학을 바탕으로 계산합니다. 실제 미끄럼과
  전달 경로 때문에 측정 피크가 정확히 일치한다고 보장하지 않습니다.

## 가장 중요한 검증 결과

동일 시험대·6204 베어링·같은 고장 강도의 별도 원본에서는 고장 종류 559/560개를
맞혔습니다. 하지만 새 30204 베어링과 다른 기관 시험대의 자료를 추가하자 정식 API는
580개 창을 모두 보류했습니다. 정상 수락률과 종류 판정률 모두 0%였습니다.

적용 범위를 제외한 오프라인 수치 시험에서도 30204 정상 240개를 전부 이상으로
표시하고, 고장 종류는 124/280개만 맞혔습니다. 다른 기관의 UFRJ 자료는 종류 정답이
0/30이었고 원시 값 단위도 명확하지 않았습니다. 따라서 기존 99.82%를 새 설비의
성능으로 인용할 수 없습니다. 기능 시험 통과와 예측 성능 합격은 다릅니다.

각 단계의 데이터, 원본 분할, 보류, 실패, 모델 해시를 문서와 연구 기록에 남겼습니다.
이미 개봉한 기록을 다시 나누어 새로운 독립 시험이라고 주장하면 안 됩니다.

## 공개본에서 제외한 자료

원래 연구 폴더의 KS/ISO 원문과 기준 수치표, 외부 원시 측정 자료, 외부 저장소 코드
사본, 훈련된 시험대별 프로파일, 실행 DB와 개인 경로는 공개하지 않습니다.
표준을 참고해 작성한 수치표도 코드에 넣어 재배포하지 않도록 분리했습니다.
공개 `vibration.iso`는 사용자가 적법하게 준비한 `custom_rule`만 평가합니다.
표준 번호를 입력했다고 규정 기준이 자동으로 제공되는 구조가 아닙니다.

이 변경은 원본 연구 폴더에 덮어쓰지 않았습니다. 로컬 원본의 동결 모델과 감사
기록은 그대로 보존했습니다. 공개본의 달라진 파일과 과거 결과의 범위는 별도 목록에 있습니다.

## 공개 배포본과 문서 버전

[PyPI](https://pypi.org/project/rotorvibe/0.1.0a1/) ·
[GitHub Release](https://github.com/lyullee/rotorvibe/releases/tag/v0.1.0a1) ·
[Zenodo DOI](https://doi.org/10.5281/zenodo.23937890)의 0.1.0a1 wheel·소스 압축본은
서로 SHA-256이 같은 공개 파일입니다. GitHub main의 이 README는 이후 API 설명을
보강한 최신 문서입니다. 이미 발행한 0.1.0a1 압축본과 PyPI 내부 README는 최초 발행
스냅샷을 보존합니다. 이번 보강은 수치 모델·학습 자료를 변경하지 않습니다.

## 자세한 문서

- [사용 설명서](docs/USER_GUIDE.md): 설치, 신호 계약, 스트리밍, API 연결, 고장 처리.
- [알고리즘 설명](docs/ALGORITHMS.md): 식, 가정, 특징, 정상 판정 및 후보 거리의 의미.
- [개발 과정](docs/DEVELOPMENT_HISTORY.md): 초기 구현부터 독립 시험 실패와 공개 준비까지.
- [연구 인계](docs/CONTINUATION.md): 남은 파일, 재현 명령, 개봉 이력, 다음 검증 조건.
- [모듈 목록](docs/MODULE_CATALOG.md): 파일별 역할과 함수/클래스 인터페이스.
- [출처·저작권](docs/SOURCES_AND_RIGHTS.md): 외부 자료 조건과 공개 제외 원칙.
- [연구 결과 모음](research/README.md): 예측 집계·동결 조건·접근 감사 기록.

직접 작성한 코드·문서의 라이선스는 MIT입니다. 외부 데이터나 표준의 권리를
MIT로 바꾸는 것은 아닙니다. 소프트웨어 DOI: https://doi.org/10.5281/zenodo.23937890.
