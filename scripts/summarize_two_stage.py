"""Summarize observed results; keep functional checks separate from predictive quality."""
import json
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'output/two_stage'; DATA=ROOT/'data/normal_independent'


def read(path): return json.loads(path.read_text(encoding='utf-8'))


def main():
    downloads=read(DATA/'metadata/download_manifest.json'); cross=read(DATA/'metadata/cross_speed_validation.json')
    marra=read(DATA/'metadata/marra_validation.json'); normal=read(DATA/'metadata/marra_normal_full_validation.json')
    validation=read(OUT/'external_source_validation.json'); development=read(OUT/'development_comparison.json')
    assert len(downloads)==23 and all(r['status']=='downloaded' and (DATA/r['path']).stat().st_size==r['bytes'] for r in downloads)
    assert cross['status']==marra['status']==normal['status']=='pass'
    audit=DATA/'metadata/reserved_access.jsonl'
    history=[json.loads(line) for line in audit.read_text(encoding='utf-8').splitlines()] if audit.exists() else []
    final_path=ROOT/'output/final_cross_speed/final_test.json'; final=read(final_path) if final_path.exists() else None
    for name,marker in (('portable','Ran 67 tests'),('implementation','RESULT: 58 passed / 0 failed'),('physics','RESULT: 32 passed / 0 failed'),('iso','RESULT: 363 passed / 0 failed')):
        log=(OUT/f'{name}.log').read_text(encoding='utf-8')
        assert marker in log and 'FAILED (' not in log and 'RESULT: 0 passed' not in log
    result={'updated_utc':datetime.now(timezone.utc).isoformat(),'functional_verification':{'status':'pass','tests':520,'portable':67,'implementation':58,'physics':32,'ISO':363,
        'service':read(OUT/'service_integration.json')},
        'new_source_validation':{k:v for k,v in validation.items() if k!='per_acquisition'},
        'exposed_Brito_development':development['modes']['relative'],
        'collection':{'files':len(downloads),'bytes':sum(r['bytes'] for r in downloads),'normal_records_or_windows':1369,
            'development_normal':970,'reserved_normal':399,'source_MAT_arrays_verified':2367,'all_Marra_normal_arrays_verified':200,
            'representative_Marra_fault_arrays_verified':20,'ready_NPZ_examples':6,'provider_checksums_and_full_ZIP_CRC':'pass',
            'new_target_test_windows':1178,'new_target_test_acquisitions':59,'new_target_arrays_decoded':bool(history),
            'unique_target_records_opened':len({r['record_id'] for r in history}),
            'new_target_model_accuracy':final['target_1200rpm']['overall_accuracy_holds_wrong'] if final else None,
            'raw_units':'unknown; no absolute ISO severity conversion'},
        'operational_use':False,'limitations':['Normal thresholds are empirical window quantiles; calibration groups are limited.',
            'CrossSpeed source validation adapts to that apparatus; it is not zero-shot field transfer.',
            'Brito misalignment 13 remains mostly missed.','Current per-speed profiles remain 600/900-only; any pooled 1200RPM qualification is a separate experimental profile.',
            'Public normal references do not replace actual-machine calibration and normal records.'],
        'report':'docs/TWO_STAGE_AND_DATA.rst','github_published':False}
    if final: result['final_cross_speed_qualification']={k:v for k,v in final.items() if k not in ('source_validation','target_1200rpm')}; result['final_cross_speed_qualification']['target_metrics']={k:v for k,v in final['target_1200rpm'].items() if k!='per_acquisition'}
    result['new_source_validation']['reserved_archive_open_flag_is_historical']=True
    (OUT/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    note='''추가 정상·독립 시험 자료 수집 결과 (2026-11-04)

총 23파일 / 3,025,775,506 bytes. 제공자 체크섬과 전체 ZIP CRC 검사 통과.

1. Marra2024 — https://zenodo.org/records/14388093
   Amanda Lucatto Marra / Claudio Garcia, DOI 10.5281/zenodo.14388093, CC BY 4.0.
   raw/marra: 6개 ZIP, LVM 1200기록. 정상 200, 고장 1000.
   4채널 가속도 + 광학 트리거, 6 kHz, 6초, 명목 10/20/30/40 Hz.
   정상 200개는 전수 수치/트리거 검사. 고장은 조건·속도별 대표 20개 검사.
   제공자의 재조립 식별 정보 부족: 1200개 독립 실험이라고 해석하지 말 것.

2. CrossSpeed2026 — https://data.mendeley.com/datasets/y8mv28hjwb/1
   Yakoop Qasim / Hassan Almubarak, DOI 10.17632/y8mv28hjwb.1, CC BY 4.0.
   raw/cross_speed: 9개 ZIP, manifest·공식 분할·체크섬·설명·라이선스.
   총 3545창: 정상 1169 / 불평형 1200 / 정렬불량 1176, 4채널 25.6 kHz.
   600/900RPM 개발 자료 2367창/119개 취득: 정상 770창/39개 취득 포함.
   개발 2367개 파형 전수 검사, 전체 3545개 제공자 signal SHA256 중복 없음.
   1200RPM은 1178창/59개 취득을 새 최종 시험으로 보존.
   보존 시험의 정상 399개도 학습·정규화·임계값 조정에 사용 금지.
   최초 수집 단계에서는 checksum/ZIP CRC/목록만 검사하고 수치 배열은 열지 않았음.

정상 자료 합계 1369기록/창 중 개발용은 970, 시험 보존용은 399.
ready: 기존 NPZ 가져오기로 검증한 정상 예제 6개. 학습 그룹은 원본 manifest를 따를 것.
metadata: 다운로드 계획/완료 SHA256/무결성/분할/접근 보호/현장 수집 양식.

두 자료의 진폭 단위·현장 센서 교정은 확정하지 못해 unit=unknown을 유지.
실제 사용자 설비의 정상·센서 감도·설치 확인을 대신하지 못함.
현장 수집 양식: metadata/field_normal_collection_template.json.

구현·개발 검증 상세: 프로젝트 docs/TWO_STAGE_AND_DATA.rst.
기존 600/900RPM 속도별 모델의 학습 외 취득 검증 479창: 정상 129, 보류 30, 고장 320 정답.
이는 새 1200RPM 시험 결과 또는 새 장비 무학습 적용 성능이 아님.
'''
    if final:
        target=final['target_1200rpm']
        note+=f"\n후속 최종 시험 실행: 1200RPM {target['windows']}창을 source-only 교차속도 모델 고정 후 개봉.\n보류 포함 정답률 {target['overall_accuracy_holds_wrong']:.4%}; 운영 사용 승인 아님.\noutput/final_cross_speed/final_test.json 및 docs/FINAL_CROSS_SPEED_VALIDATION.rst 참조.\n이 자료는 이제 미개봉 시험 자료가 아니므로 결과에 맞춰 조정한 뒤 새 맹검이라 주장하면 안 됨.\n"
    (DATA/'자료_수집결과.txt').write_text(note,encoding='utf-8')
    print('PASS summary: 520 functional checks; 23 collected files; target status:', 'opened for frozen qualification' if history else 'sealed')

if __name__=='__main__': main()
