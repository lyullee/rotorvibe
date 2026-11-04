"""Write provenance and a compact collection summary after successful validation."""
from pathlib import Path
import json
import hashlib
import sys

ROOT=Path(__file__).resolve().parents[1]/'data/public_validation'
def save(name,obj):
    (ROOT/'metadata'/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')

manifest=json.loads((ROOT/'download_manifest.json').read_text(encoding='utf-8'))
summary=json.loads((ROOT/'metadata/validation_summary.json').read_text(encoding='utf-8'))
if summary['record_counts']!={'CWRU':56,'Paderborn':480,'IMS':984} or summary['ready_npz_count']!=83 or summary['bearing_catalog_entries']!=129:
    raise SystemExit('Validation not complete')
if any(r['status']!='downloaded' for r in manifest):
    raise SystemExit('A download failed')
sources={
    'CWRU':{'landing_page':'https://engineering.case.edu/bearingdatacenter/download-data-file',
            'bearing_source':'https://engineering.case.edu/bearingdatacenter/bearing-information',
            'license_status':'No explicit commercial-use/redistribution license identified on the reviewed provider pages.',
            'scope':'56 selected original records, not the entire CWRU repository'},
    'Paderborn':{'landing_page':'https://mb.uni-paderborn.de/en/kat/research/bearing-datacenter',
                 'archive_index':'https://groups.uni-paderborn.de/kat/BearingDataCenter/',
                 'license':'CC-BY-NC-4.0','commercial_use':'Contact provider',
                 'attribution':'Christian Lessmeier, James Kuria Kimotho, Detmar Zimmer and Walter Sextro, 2016, Chair of Design and Drive Technology, Paderborn University.',
                 'scope':'K001 K002 KA04 KA16 KI04 KI16; 6 of 32 specimens; 480 recordings'},
    'IMS':{'landing_page':'https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/',
           'download':'https://phm-datasets.s3.amazonaws.com/NASA/4.+Bearings.zip',
           'attribution':'J. Lee, H. Qiu, G. Yu, J. Lin, and Rexnord Technical Services (2007). IMS, University of Cincinnati. Bearing Data Set. NASA Prognostics Data Repository.',
           'license_status':'Public provider download; third-party donor data. No blanket public-domain/commercial redistribution assertion.',
           'scope':'All 3 tests archived and archive integrity checked; only test 2 (984 recordings) decoded and indexed'},
    'NSK':{'url':'https://www.nsk.com/content/dam/nsk/am/en_us/documents/bearings-americas/Electric-Motor-Handbook.pdf',
           'scope':'120 frequency rows, PDF pages 52-59','license_status':'Manufacturer public reference; no open database redistribution license asserted.'},
    'IMS_geometry':{'url':'https://onlinelibrary.wiley.com/doi/10.1155/2015/542472','tables':[2,3],
                    'bearing':'Rexnord ZA-2115','rollers_per_row':16,'roller_diameter_inch':0.331,
                    'pitch_diameter_inch':2.815,'contact_angle_deg':15.17,
                    'source_type':'Research reanalysis, not provider README nor a current manufacturer certificate'}
}
save('dataset_sources_and_terms.json',sources)
archive_validation={
    'tool':'7-Zip 26.05, portable console extracted from official vendor distribution',
    'checks':[
        {'path':'raw/ims/4.Bearings.zip','check':'Python zipfile.testzip(): None (CRC passed)'},
        {'path':'IMS.7z (intermediate extracted from provider ZIP)','check':'7z x completed with exit code 0; all four members decoded'},
        {'path':'extracted/ims/1st_test.rar','check':'7z t exit code 0'},
        {'path':'extracted/ims/2nd_test.rar','check':'7z x exit code 0; all 984 ASCII records parsed and finite'},
        {'path':'extracted/ims/3rd_test.rar','check':'7z t exit code 0'},
        *[{'path':f'raw/paderborn/{c}.rar','check':'7z x exit code 0; all 80 MATLAB records parsed and finite'} for c in ['K001','K002','KA04','KA16','KI04','KI16']]
    ],
    'scope_note':'Archive integrity does not certify physical measurement accuracy or fault label accuracy.'
}
save('archive_validation.json',archive_validation)
summary.update({'downloaded_files':len(manifest),
                'original_vibration_archive_and_mat_bytes':sum(r['bytes'] for r in manifest if r['dataset'] in ['CWRU','Paderborn','IMS']),
                'total_indexed_recordings':sum(summary['record_counts'].values()),
                'folder_size_bytes':sum(p.stat().st_size for p in ROOT.rglob('*') if p.is_file()),
                'date':'2026-11-03'})
save('collection_summary.json',summary)
print(json.dumps(summary,ensure_ascii=False,indent=2))
