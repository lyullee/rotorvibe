"""Download a bounded validation corpus from original, public providers."""
from pathlib import Path
from html.parser import HTMLParser
from urllib.request import Request, urlopen
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1] / 'data' / 'public_validation'
SOURCE = ROOT / 'sources'
CASE = 'https://engineering.case.edu/bearingdatacenter/'
PU = 'https://mb.uni-paderborn.de/en/kat/research/bearing-datacenter'
NASA = 'https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/'
NSK = 'https://www.nsk.com/content/dam/nsk/am/en_us/documents/bearings-americas/Electric-Motor-Handbook.pdf'


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.current = [dict(attrs).get('href', ''), '']

    def handle_data(self, data):
        if self.current is not None:
            self.current[1] += data

    def handle_endtag(self, tag):
        if tag == 'a' and self.current is not None:
            self.links.append(tuple(self.current))
            self.current = None


def fetch(url, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size:
        return dest
    partial = dest.with_suffix(dest.suffix + '.part')
    for attempt in range(3):
        try:
            req = Request(url, headers={'User-Agent': 'BearingValidationResearch/1.0'})
            with urlopen(req, timeout=90) as response, partial.open('wb') as output:
                expected = response.headers.get('Content-Length')
                count = 0
                while block := response.read(1024 * 1024):
                    output.write(block)
                    count += len(block)
                if expected and count != int(expected):
                    raise IOError(f'incomplete download: {count}/{expected}')
            partial.replace(dest)
            print(f'DOWNLOADED {dest.relative_to(ROOT)} {count:,} bytes', flush=True)
            return dest
        except Exception as error:
            if 'CERTIFICATE_VERIFY_FAILED' in str(error):
                # Windows curl uses the Windows trust store/chain builder.
                # Certificate verification remains enabled.
                subprocess.run(['C:/Windows/System32/curl.exe', '--fail', '--location',
                                '--retry', '2', '--max-time', '900', '--silent', '--show-error',
                                '--output', str(partial), url], check=True)
                partial.replace(dest)
                print(f'DOWNLOADED {dest.relative_to(ROOT)} {dest.stat().st_size:,} bytes (Windows TLS)', flush=True)
                return dest
            if attempt == 2:
                raise
            time.sleep(2)


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            h.update(block)
    return h.hexdigest()


def main():
    SOURCE.mkdir(parents=True, exist_ok=True)
    pages = {
        'cwru_12k': CASE + '12k-drive-end-bearing-fault-data',
        'cwru_normal': CASE + 'normal-baseline-data',
        'cwru_bearings': CASE + 'bearing-information',
        'cwru_apparatus': CASE + 'apparatus-and-procedures',
        'cwru_download': CASE + 'download-data-file',
        'paderborn_home': PU,
        'paderborn_download': PU + '/data-sets-and-download',
        'paderborn_conditions': PU + '/operating-conditions',
        'paderborn_index': 'https://groups.uni-paderborn.de/kat/BearingDataCenter/',
        'nasa_repository': NASA,
    }
    source_rows = []
    jobs = []
    for name, url in pages.items():
        path = fetch(url, SOURCE / (name + '.html'))
        source_rows.append({'id': name, 'url': url, 'local_path': str(path.relative_to(ROOT)), 'sha256': sha256(path)})
    for name in ['cwru_normal', 'cwru_12k']:
        p = Links()
        p.feed((SOURCE / (name + '.html')).read_text(encoding='utf-8'))
        for href, label in p.links:
            label = label.strip()
            if not href.lower().endswith('.mat'):
                continue
            if name == 'cwru_12k' and not re.match(r'^(IR|B|OR)(007|014|021)', label):
                continue  # NTN 028 geometry is not assumed to be SKF geometry.
            url = urljoin(pages[name], href)
            match = re.search(r'_(\d)$', label)
            if not match:
                raise ValueError(label)
            load = int(match[1])
            if name == 'cwru_normal':
                fault, diameter = 'normal', 0.0
            else:
                m = re.match(r'^(IR|B|OR)(\d{3})', label)
                fault = {'IR': 'inner_race', 'B': 'rolling_element', 'OR': 'outer_race'}[m[1]]
                diameter = int(m[2]) / 1000
            jobs.append({'dataset': 'CWRU', 'label': label, 'url': url,
                         'path': 'raw/cwru/' + url.rsplit('/', 1)[-1],
                         'fault': fault, 'fault_diameter_inch': diameter,
                         'load_hp': load, 'approx_rpm_from_table': [1797,1772,1750,1730][load],
                         'fault_bearing': 'SKF 6205-2RS JEM',
                         'de_sample_rate_hz': 48000 if fault == 'normal' else 12000,
                         'sampling_note': 'Normal DE baseline is 48 kHz; do not treat it as 12 kHz. Channel-specific rates require separate handling.',
                         'outer_race_position_clock': (re.search(r'@(\d+)', label)[1] if '@' in label else None)})
    jobs.extend([
        {'dataset': 'Paderborn', 'label': code, 'url': 'https://groups.uni-paderborn.de/kat/BearingDataCenter/' + code + '.rar',
         'path': 'raw/paderborn/' + code + '.rar', 'state_note': state,
         'license': 'CC-BY-NC-4.0; commercial use requires author permission'}
        for code, state in [('K001','healthy'),('K002','healthy'),
                            ('KA04','real accelerated-life outer-ring damage'),('KA16','real accelerated-life outer-ring damage'),
                            ('KI04','real accelerated-life inner-ring damage'),('KI16','real accelerated-life inner-ring damage')]
    ])
    jobs.extend([
        {'dataset': 'IMS', 'label': 'all_three_tests', 'url': 'https://phm-datasets.s3.amazonaws.com/NASA/4.+Bearings.zip', 'path': 'raw/ims/4.Bearings.zip'},
        {'dataset': 'reference', 'label': 'NSK_Electric_Motor_Handbook', 'url': NSK, 'path': 'references/NSK_Electric_Motor_Handbook.pdf'},
        {'dataset': 'reference', 'label': 'Paderborn_Lessmeier_2016', 'url': 'https://mb.uni-paderborn.de/fileadmin-mb/kat/PDF/Veroeffentlichungen/20160703_PHME16_CM_bearing.pdf', 'path': 'references/Paderborn_Lessmeier_2016.pdf'},
        {'dataset': 'tooling', 'label': '7zr', 'url': 'https://www.7-zip.org/a/7zr.exe', 'path': 'tools/7zr.exe'},
        {'dataset': 'tooling', 'label': '7zip_archive_do_not_install', 'url': 'https://github.com/ip7z/7zip/releases/download/26.05/7z2605-x64.exe', 'path': 'tools/7z2605-x64.exe'},
        {'dataset': 'reference', 'label': 'CWRU_baseline_sampling_primary_paper', 'url': 'https://papers.phmsociety.org/index.php/phme/article/download/3329/1947', 'path': 'references/CWRU_baseline_sampling_PHME2022.pdf'},
    ])
    (ROOT / 'download_plan.json').write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding='utf-8')
    print('PLANNED',len(jobs),'files',flush=True)
    results = []
    def run(job):
        row = dict(job)
        try:
            dest = fetch(job['url'], ROOT / job['path'])
            row.update(status='downloaded', bytes=dest.stat().st_size, sha256=sha256(dest))
            if dest.suffix == '.mat' and not dest.read_bytes()[:20].startswith(b'MATLAB'):
                raise ValueError('Downloaded response is not a MATLAB file')
        except Exception as error:
            row.update(status='failed', error=str(error))
            print('FAILED',job['label'],str(error),flush=True)
        return row
    with ThreadPoolExecutor(max_workers=5) as pool:
        for future in as_completed([pool.submit(run, j) for j in jobs]):
            results.append(future.result())
            (ROOT / 'download_manifest.json').write_text(json.dumps(sorted(results,key=lambda r:r['path']),ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT / 'source_manifest.json').write_text(json.dumps(source_rows,ensure_ascii=False,indent=2),encoding='utf-8')
    print('FINISHED',len(results),'failed',sum(r['status']=='failed' for r in results),flush=True)


if __name__ == '__main__':
    main()
