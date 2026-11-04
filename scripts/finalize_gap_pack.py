"""Summarize verified supplementary evidence and map it to module requirements."""
from pathlib import Path
import json
import numpy as np
import pypdfium2 as pdfium

ROOT=Path(__file__).resolve().parents[1]/'data/gap_supplement'
META=ROOT/'metadata'
def read(name): return json.loads((META/name).read_text(encoding='utf-8'))
def save(name,obj): (META/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')

brito=read('brito_validation_summary.json')
femto=read('femto_validation_summary.json')
kaist=read('kaist_validation_summary.json')
mw=read('mathworks_validation_summary.json')
assert brito['records']==8400 and femto['complete_training_bearings']==6 and femto['held_out_full_bearings']==11 and kaist['mat_measurements']==45
manifest=json.loads((ROOT/'download_manifest.json').read_text(encoding='utf-8'))
assert all(r['status']=='downloaded' and (ROOT/r['path']).is_file() for r in manifest)

matrix=[
 {'feature':'실시간 파형·FFT·스펙트로그램','evidence':['기존 공개 파형','Brito 8400개 4채널 기록','KAIST 45개 4채널 측정','NI 측정/차수 분석 안내'],
  'updated_assessment':'파일 재생 기반 개발·검증 가능','remaining':['대상 DAQ 스트리밍 규격','실제 패킷 손실·시각 동기·처리 지연']},
 {'feature':'RMS·피크·첨도·대역별 에너지 추세','evidence':['KAIST 원본 단위/변환계수','NI 감도/측정 안내','PCB 교정·설치 안내'],
  'updated_assessment':'메타데이터 단위를 해석한 오프라인 검증 가능','remaining':['실제 센서별 교정값','설치 후 주파수 응답','대역·진폭·첨도 정의'],
  'important_finding':'KAIST raw MAT는 MKS를 선언하며 g 표시는 내장 factor 0.101971621297793를 적용한다. 원본과 표시 변환본을 분리했다.'},
 {'feature':'베어링 결함주파수 표시','evidence':['기존 129개 카탈로그','NI tachometer/order tracking 안내'],
  'updated_assessment':'개발 가능','remaining':['현장 베어링 정확한 사양','RPM 동기 입력','변속 시 차수 분석']},
 {'feature':'엔벨로프 기반 베어링 이상 감시','evidence':['SKF 엔벨로프 FAQ','SKF 초기 경보 가이드','기존 결함 파형·KAIST'],
  'updated_assessment':'벤치데이터에서 개발·검증 가능','remaining':['현장 센서/장착/공진대역','검출기·필터·스케일을 맞춘 정상 경보 기준']},
 {'feature':'불평형·정렬불량·헐거움 후보 제시','evidence':['Brito 네 상태별 독립 시험 5회','KAIST 부하별 교차검증','SKF·Fluke 진단 해석 자료'],
  'updated_assessment':'세 기계적 결함의 실측 후보 제시 검증 가능','remaining':['위상/축방향 정보','복합·미지 결함','현장 설비 일반화']},
 {'feature':'정상 대비 이상 점수·경보','evidence':['독립 정상 시험','부하별 정상 자료','MathWorks 정비 전후 예제 및 정상 전용 학습 안내'],
  'updated_assessment':'공개자료에서 점수·오경보·지연 평가 가능','remaining':['현장 RPM/부하/온도별 정상 기준','설비별 경보 지속시간·오경보 허용치'],
  'weak_label_warning':'MathWorks Before/After는 정비 전후 가정에 의한 이상 라벨이며 고장 원인 확정 라벨이 아니다.'},
 {'feature':'고장 종류 자동 확정','evidence':['유도 결함/실제 손상 벤치 라벨','Brito 독립 시험 분할','Paderborn 베어링별 손상 정보','KAIST 교차조건'],
  'updated_assessment':'알려진 벤치 고장 분류기 개발·평가 가능; 현장 원인 확정은 조건 미충족',
  'remaining':['현장 정비·분해 확인 라벨','고장 종류별 현장 샘플','미지·복합 결함 판정 보류 기준']},
 {'feature':'잔여수명 몇 시간 예측','evidence':['PRONOSTIA 완전 수명 6+11개','11개 절단/전체 이력 쌍','NASA 예측 성능 지표','기존 IMS'],
  'updated_assessment':'운전조건·종료 정의를 제한한 오프라인 RUL 연구·평가 가능',
  'remaining':['현장 수명 이력','실패/중도교체 정의','향후 부하·윤활·온도 가정','불확실성 검증'],
  'target_warning':'잔여시간 기준값은 공개된 전체/절단 이력에서 유도한 시험 종료까지의 시간이다. 현장 수명으로 직접 환산하지 않는다.'}
]
save('feature_coverage_matrix.json',matrix)
standards=[
 {'id':'ISO 20816-3:2026','edition':2,'publication_date_observed':'2026-10-28','url':'https://www.iso.org/standard/89922.html',
  'replaces':'ISO 20816-3:2022','role':'Machine broadband vibration evaluation, not bearing/gear defect diagnosis','full_text_downloaded':False},
 {'id':'ISO 13373-1:2002','review_confirmed':2024,'url':'https://www.iso.org/standard/21831.html','role':'General vibration condition-monitoring measurement procedures','full_text_downloaded':False},
 {'id':'ISO 13381-1:2025','edition':3,'url':'https://www.iso.org/standard/88029.html','replaces':'ISO 13381-1:2015','role':'Prognostics general guidance/requirements','full_text_downloaded':False}
]
save('standards_reference_register.json',standards)
save('source_terms_and_limits.json',{
 'Brito':{'doi':'10.17632/zx8pfhdtnb.3','license':'CC-BY-4.0','url':'https://data.mendeley.com/datasets/zx8pfhdtnb/3',
          'cite':'Lucas Costa Brito, Gian Antonio Susto, Jorge Nei Brito, Marcus Antonio Viana Duarte. Fault Diagnosis using eXplainable AI: A transfer learning-based approach for rotating machinery exploiting augmented synthetic data. Expert Systems with Applications 232:120860. DOI 10.1016/j.eswa.2023.120860.'},
 'KAIST':{'doi':'10.17632/ztmf3m7h5x.6','license':'CC-BY-4.0','url':'https://data.mendeley.com/datasets/ztmf3m7h5x/6',
          'scope':'vibration.zip only downloaded. acoustic/current-temperature archives remain linked in original API inventory.',
          'cite':'Wonho Jung, Seong-Hu Kim, SungHyun Yun, Jaewoong Bae, Yong-Hwa Park (2023), Vibration, Acoustic, Temperature, and Motor Current Dataset of Rotating Machine Under Varying Load Conditions for Fault Diagnosis, version 6.'},
 'FEMTO':{'url':'https://phm-datasets.s3.amazonaws.com/NASA/10.+FEMTO+Bearing.zip','license':'NASA-hosted third-party public research data. No blanket unrestricted commercial-use assertion.',
          'cite':'FEMTO Bearing Data Set, NASA Prognostics Data Repository; P. Nectoux et al., PRONOSTIA, IEEE PHM 2012.'},
 'MathWorks':{'license_file':'references/mathworks_dataset_license.txt','license':mw['license'],'required_citation':mw['attribution'],
              'import_limitation':mw['import_limitation'],'weak_labels':mw['label_limitation']},
 'standards':{'full_text':'Not purchased or copied. Only official identification, status, scope and links recorded.'},
 'PCB':{'local_snapshot':'Two pages rejected scripted download; reviewed through web research. See sources/web_only_references.json.'},
 'unit_evidence':{'primary_source':'KAIST original MAT embedded quantity metadata',
                  'vendor_context':'https://community.sw.siemens.com/articles/en_US/Knowledge/Simcenter-Testlab-Automation-Excel-Export',
                  'interpretation':'Raw MKS acceleration and user-display g conversion are stored separately; this is based on embedded declarations and coefficient, not a new calibration.'}
})
pdf_checks=[]
for path in (ROOT/'references').glob('*.pdf'):
    assert path.read_bytes()[:5]==b'%PDF-'
    doc=pdfium.PdfDocument(path)
    pdf_checks.append({'path':str(path.relative_to(ROOT)),'pages':len(doc),'readable_pdf':True})
for path in (ROOT/'ready_npz').glob('*.npz'):
    with np.load(path,allow_pickle=False) as r:
        assert np.isfinite(r['vibration']).all()
summary={
 'date':'2026-11-03','downloaded_files':len(manifest),'failed_downloads':0,
 'downloaded_raw_bytes':sum(r['bytes'] for r in manifest if r['dataset'] not in ['reference','reference_page']),
 'Brito':brito,'KAIST':kaist,'FEMTO':femto,'MathWorks':mw,
 'ready_npz_files':len(list((ROOT/'ready_npz').glob('*.npz'))),
 'pdf_checks':pdf_checks,
 'folder_bytes':sum(p.stat().st_size for p in ROOT.rglob('*') if p.is_file()),
 'not_done':['No diagnostic classifier trained','No diagnostic accuracy measured','No field sensor calibration performed','No industrial RUL guarantee established'],
 'field_templates':['measurement_contract_template.json','ground_truth_and_life_template.json']
}
save('collection_summary.json',summary)
print(json.dumps({k:summary[k] for k in ['downloaded_files','failed_downloads','downloaded_raw_bytes','ready_npz_files','folder_bytes']},indent=2))
