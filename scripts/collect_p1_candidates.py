"""Fetch/verify pinned sealed candidates; no waveform decoding or model fitting."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import argparse,hashlib,json,urllib.request


def sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        while block:=stream.read(1024*1024): digest.update(block)
    return digest.hexdigest()


def collect(data_root,*,verify_only=False):
    root=Path(data_root).resolve(); repository=Path(__file__).resolve().parents[1]
    plan=json.loads((repository/'research/p1_data_receipt.json').read_text(encoding='utf8'))
    versions={s['dataset']:s['version'] for s in plan['sources']}
    metadata={}
    if not verify_only:
        for dataset,version in versions.items():
            url=f'https://data.mendeley.com/public-api/datasets/{dataset}/files?folder_id=root&version={version}'
            with urllib.request.urlopen(url,timeout=60) as response: rows=json.load(response)
            if not isinstance(rows,list): raise ValueError('Provider metadata unavailable')
            metadata[dataset]={r['filename']:r for r in rows}
    def one(row):
        if row['dataset'] not in versions or row['name'] not in ('data.zip','data description.pdf','data label.xlsx'):
            raise ValueError('Unexpected pinned file identity')
        path=root/'raw'/row['dataset']/row['name']
        if not path.resolve().is_relative_to(root): raise ValueError('Target leaves data root')
        if path.exists():
            if path.stat().st_size!=row['bytes'] or sha256(path)!=row['sha256']:
                raise ValueError('Existing file differs; never overwrite it silently')
        elif verify_only: raise FileNotFoundError(path)
        else:
            provider=metadata[row['dataset']][row['name']]; detail=provider['content_details']
            if provider['size']!=row['bytes'] or detail['sha256_hash']!=row['sha256']:
                raise ValueError('Provider dataset changed; review a new version rather than replacing the plan')
            url=detail['download_url']
            if not url.startswith('https://data.mendeley.com/public-files/datasets/'+row['dataset']+'/'):
                raise ValueError('Unexpected provider download URL')
            path.parent.mkdir(parents=True,exist_ok=True); partial=path.with_name(path.name+'.part')
            with partial.open('xb') as target,urllib.request.urlopen(url,timeout=120) as response:
                total=0
                while block:=response.read(1024*1024):
                    total+=len(block)
                    if total>row['bytes']: raise ValueError('Provider response exceeds expected size')
                    target.write(block)
            if partial.stat().st_size!=row['bytes'] or sha256(partial)!=row['sha256']:
                raise ValueError('Downloaded archive checksum differs')
            partial.replace(path)
        return dict(dataset=row['dataset'],name=row['name'],bytes=row['bytes'],sha256=row['sha256'],status='verified')
    with ThreadPoolExecutor(max_workers=2) as pool: rows=list(pool.map(one,plan['files']))
    return {'files':rows,'waveform_arrays_decoded':False,'role':'sealed_candidate_unassigned','model_fit_or_tuning':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--data-root',required=True)
    parser.add_argument('--verify-only',action='store_true'); args=parser.parse_args()
    print(json.dumps(collect(args.data_root,verify_only=args.verify_only),indent=2))
