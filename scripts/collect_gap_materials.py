"""Collect additional public evidence for the eight vibration-module requirements."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import subprocess
import hashlib
import re
import sys

ROOT=Path(__file__).resolve().parents[1]/'data/gap_supplement'
ROOT.mkdir(parents=True,exist_ok=True)

def sha256(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        while block:=f.read(1024*1024): h.update(block)
    return h.hexdigest()

def fetch(url,path):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and path.stat().st_size:
        if path.suffix=='.pdf' and path.read_bytes()[:5]!=b'%PDF-':
            path.replace(ROOT/'sources'/f'{path.stem}_legacy_redirect.html')
        else:
            return path
    part=path.with_suffix(path.suffix+'.part')
    subprocess.run(['C:/Windows/System32/curl.exe','--fail','--location','--retry','2','--connect-timeout','20',
                    '--max-time','1800','--silent','--show-error','--output',str(part),url],check=True)
    part.replace(path)
    if path.suffix=='.pdf' and path.read_bytes()[:5]!=b'%PDF-':
        raise ValueError(f'Expected PDF, got another content type: {url}')
    print('DOWNLOADED',path.relative_to(ROOT),path.stat().st_size,flush=True)
    return path

def run(job):
    result=dict(job)
    try:
        path=fetch(job['url'],ROOT/job['path'])
        digest=sha256(path)
        if job.get('provider_sha256') and digest!=job['provider_sha256']:
            raise ValueError('Provider checksum mismatch')
        result.update(status='downloaded',bytes=path.stat().st_size,sha256=digest)
    except Exception as e:
        result.update(status='failed',error=str(e))
        print('FAILED',job['path'],str(e),flush=True)
    return result

def main():
    jobs=[]
    for id,version,alias in [('zx8pfhdtnb',3,'brito'),('ztmf3m7h5x',6,'kaist')]:
        url=f'https://data.mendeley.com/public-api/datasets/{id}/files?folder_id=root&version={version}'
        path=fetch(url,ROOT/f'sources/{alias}_v{version}_files.json')
        files=json.loads(path.read_text(encoding='utf-8'))
        for row in files:
            # KAIST vibration supplies stated g units and four measured directions.
            # Its current/temperature and acoustic archives remain discoverable via the catalog.
            if alias=='kaist' and row['filename']!='vibration.zip': continue
            details=row['content_details']
            jobs.append({'dataset':alias,'dataset_id':id,'version':version,'filename':row['filename'],
                         'path':f'raw/{alias}/'+row['filename'],'url':details['download_url'],
                         'provider_sha256':details['sha256_hash'],'provider_bytes':row['size'],
                         'license':'CC-BY-4.0'})
    jobs.extend([
        {'dataset':'FEMTO','path':'raw/femto/10.FEMTO_Bearing.zip','url':'https://phm-datasets.s3.amazonaws.com/NASA/10.+FEMTO+Bearing.zip',
         'license':'Public NASA-hosted third-party data; see included terms and acknowledge FEMTO-ST'},
        {'dataset':'MathWorks','path':'raw/mathworks/vibrationData.zip',
         'url':'https://ssd.mathworks.com/supportfiles/predmaint/anomalyDetection3axisVibration/v1/vibrationData.zip',
         'license':'Example support data; no separate open-data license asserted'},
        {'dataset':'reference','path':'references/SKF_initial_envelope_alarm.pdf',
         'url':'https://skftechnicalsupport.zendesk.com/hc/en-us/article_attachments/360043145433'},
        {'dataset':'reference','path':'references/SKF_enveloping_FAQ.pdf',
         'url':'https://skftechnicalsupport.zendesk.com/hc/en-us/article_attachments/360037285414'},
        {'dataset':'reference','path':'references/PRONOSTIA_platform_author_paper.pdf',
         'url':'https://publiweb.femto-st.fr/tntnet/entries/1528/documents/author/data'},
        {'dataset':'reference','path':'references/NASA_prognostic_performance_metrics.pdf',
         'url':'https://ntrs.nasa.gov/api/citations/20100023445/downloads/20100023445.pdf'},
        {'dataset':'reference','path':'references/SKF_spectrum_analysis.pdf',
         'url':'https://www.skf.com/binaries/pub12/Images/0901d1968024acef-CM5118-EN-Spectrum-Analysis_tcm_12-113997.pdf'},
    ])
    references={
        'brito_dataset':'https://data.mendeley.com/datasets/zx8pfhdtnb/3',
        'kaist_dataset':'https://data.mendeley.com/datasets/ztmf3m7h5x/6',
        'pcb_mounting':'https://www.pcb.com/resources/technical-information/mounting',
        'pcb_calibration':'https://www.pcb.com/resources/technical-information/introduction-to-accelerometers',
        'ni_measurement':'https://www.ni.com/en/shop/data-acquisition/sensor-fundamentals/measuring-vibration-with-accelerometers.html',
        'skf_sensor_faults':'https://skftechnicalsupport.zendesk.com/hc/en-us/articles/1500001563501-Accelerometer-Troubleshooting',
        'normal_only_anomaly':'https://www.mathworks.com/help/predmaint/ug/anomaly-detection-using-3-axis-vibration-data.html',
        'femto_author_platform':'https://members.femto-st.fr/patrick-nectoux/fr/pronostic-defaillances-roulement-pronostia',
        'xjtu_author_dataset':'https://biaowang.tech/xjtu-sy-bearing-datasets/',
        'nasa_metrics_library':'https://github.com/nasa/PrognosticsMetricsLibrary',
        'ni_order_tracking':'https://www.ni.com/en/shop/labview/performing-order-analysis-in-labview-with-sound-and-vibration-so.html',
        'fluke_fault_patterns':'https://www.fluke.com/en-gb/learn/blog/alignment/understanding-vibration-monitoring-common-faults-part-4',
    }
    # These two pages are readable through web research, but reject scripted HTTP downloads.
    # Preserve their provenance instead of claiming a local full-text snapshot exists.
    web_only={name:{'url':references[name],'status':'web_reviewed_only','local_html':None,
                    'note':'Public web content reviewed; automated local snapshot returned HTTP 403.'}
              for name in ['pcb_mounting','pcb_calibration']}
    (ROOT/'sources/web_only_references.json').write_text(json.dumps(web_only,ensure_ascii=False,indent=2),encoding='utf-8')
    jobs.extend({'dataset':'reference_page','url':url,'path':'sources/'+name+'.html'} for name,url in references.items() if name not in web_only)
    reference_only='--references-only' in sys.argv
    if reference_only: jobs=[j for j in jobs if j['dataset'] in ['reference','reference_page']]
    prefix='reference_' if reference_only else ''
    (ROOT/(prefix+'download_plan.json')).write_text(json.dumps(jobs,ensure_ascii=False,indent=2),encoding='utf-8')
    results=[]
    with ThreadPoolExecutor(max_workers=5) as pool:
        for future in as_completed([pool.submit(run,j) for j in jobs]):
            results.append(future.result())
            (ROOT/(prefix+'download_manifest.json')).write_text(json.dumps(sorted(results,key=lambda x:x['path']),ensure_ascii=False,indent=2),encoding='utf-8')
    print('FINISHED',len(results),'failed',sum(r['status']=='failed' for r in results),flush=True)

if __name__=='__main__': main()
