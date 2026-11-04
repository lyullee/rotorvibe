import csv
import io
import json
import re
import math
from numbers import Real
import zipfile
from pathlib import Path,PureWindowsPath
import numpy as np
from scipy.io import loadmat
from .bootstrap import PROJECT, RUNTIME


def local_path(root, relative):
    value=str(relative).replace('\\','/')
    if Path(value).is_absolute() or PureWindowsPath(value).is_absolute(): raise ValueError('Relative paths only.')
    target=(root/value).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError('프로젝트 밖의 경로는 접근할 수 없습니다.')
    return target


def matrix(a):
    a=np.asarray(a,dtype=np.float64)
    if a.ndim==1: a=a[:,None]
    if a.ndim!=2 or not len(a) or not 1<=a.shape[1]<=16 or not np.isfinite(a).all():
        raise ValueError('파형은 유한한 숫자의 samples × channels 배열이어야 합니다.')
    return a


def _check_npy_header(stream,limit=512*1024*1024):
    """Reject impossible declared allocations before numpy creates an array."""
    version=np.lib.format.read_magic(stream)
    if version==(1,0): shape,_,dtype=np.lib.format.read_array_header_1_0(stream)
    elif version==(2,0): shape,_,dtype=np.lib.format.read_array_header_2_0(stream)
    else: raise ValueError('Only NPY header versions 1/2 are supported for numeric uploads.')
    if dtype.hasobject or any(not isinstance(n,int) or n<0 for n in shape) or math.prod(shape)*dtype.itemsize>limit:
        raise ValueError('Unsafe object dtype or declared array allocation exceeds 512 MiB.')


class DatasetCatalog:
    def __init__(self):
        self.public=PROJECT/'data/public_validation'
        self.extra=PROJECT/'data/gap_supplement'
        self.records={}
        self.rows=[]
        self.lives={}
        self._load()

    def _read(self, root, path):
        p=root/path
        return json.loads(p.read_text(encoding='utf-8')) if p.exists() else []

    def _load(self):
        specs=[(self.public,'metadata/record_index.json','public'),
               (self.extra,'metadata/brito_record_index.json','brito'),
               (self.extra,'metadata/kaist_record_index.json','kaist')]
        for root,path,kind in specs:
            for row in self._read(root,path):
                id=kind+':'+row['record_id']
                dataset=row.get('dataset',{'brito':'Brito','kaist':'KAIST'}.get(kind,''))
                if kind=='brito': dataset='Brito'
                item={'id':id,'dataset':dataset,'record_id':row['record_id'],'fault':row.get('fault'),
                      'rpm':row.get('rpm',row.get('approx_reported_shaft_rpm')),
                      'sample_rate_hz':row.get('sample_rate_hz',row.get('de_sample_rate_hz')),
                      'duration_seconds':row.get('duration_seconds',1),
                      'condition':row.get('specimen',row.get('trial_id',row.get('load_hp',row.get('load_torque_nm')))),
                      'bearing_id':row.get('bearing_id'),'kind':kind}
                self.records[id]=(root,kind,row,item)
                self.rows.append(item)
        for row in self._read(self.extra,'metadata/femto_trajectory_index.json'):
            if row['role']=='truncated_test_input': continue
            id='femto:'+row['bearing']
            self.lives[id]=row
            item={'id':id,'dataset':'FEMTO','record_id':row['bearing'],'fault':'life_trajectory',
                  'rpm':row['nominal_rpm'],'sample_rate_hz':row['sample_rate_hz'],'duration_seconds':0.1,
                  'condition':row['nominal_load_n'],'bearing_id':None,'kind':'femto',
                  'snapshots':row['snapshot_count'],'role':row['role']}
            self.records[id]=(self.extra,'femto',row,item); self.rows.append(item)

    def search(self, query='', dataset='', offset=0, limit=100):
        query=query.casefold()
        rows=[r for r in self.rows if (not dataset or r['dataset']==dataset) and
              (not query or query in json.dumps(r,ensure_ascii=False).casefold())]
        return {'total':len(rows),'items':rows[max(0,offset):max(0,offset)+min(200,max(1,limit))],
                'datasets':sorted({r['dataset'] for r in self.rows})}

    def details(self, id):
        if id not in self.records: raise ValueError('측정 기록을 찾을 수 없습니다.')
        _,kind,row,item=self.records[id]
        if kind=='femto':
            row={k:v for k,v in row.items() if not k.endswith('_series')}
        return {'item':item,'metadata':row}

    def trial_ids(self,id):
        if id not in self.records or self.records[id][1]!='brito': return [id]
        row=self.records[id][2]; trial=row['trial_id']
        items=[(key,value[2]) for key,value in self.records.items() if value[1]=='brito' and value[2]['trial_id']==trial]
        items.sort(key=lambda value:value[1]['member_path'])
        ids=[key for key,_ in items]
        return ids[ids.index(id):]

    def load(self, id, snapshot=0):
        if id not in self.records: raise ValueError('측정 기록을 찾을 수 없습니다.')
        root,kind,row,item=self.records[id]
        meta=dict(item)
        meta.update(unit='unknown', unit_provenance='not_confirmed', source_label=row.get('fault'),
                    rpm_provenance=row.get('rpm_provenance','제공처의 명목/근사 RPM'),
                    label_usage='공개 데이터 라벨은 참고 표시용이며 진단/분류 입력 특징에 사용하지 않습니다.')
        if kind=='public':
            path=local_path(root,row['raw_path'])
            if row['dataset']=='CWRU':
                d=loadmat(path,simplify_cells=True)
                a=d[row['channel']]
            elif row['dataset']=='Paderborn':
                d=loadmat(path,simplify_cells=True)[path.stem]
                y={r['Name']:r['Data'] for r in d['Y']}
                a=np.asarray(y['vibration_1'])[:,None]
                meta['auxiliary']={'mean_current_1':float(np.mean(y['phase_current_1'])),
                                   'mean_current_2':float(np.mean(y['phase_current_2']))}
                meta['channel_names']=['진동 1']
            elif row['dataset']=='IMS':
                a=np.loadtxt(path)
                meta['channel_names']=['베어링 1','베어링 2','베어링 3','베어링 4']
                meta['source_label']='시험 종료 시 베어링 1 외륜 손상; 현재 기록의 고장 라벨은 미확정'
            else: raise ValueError('지원하지 않는 공개 자료 형식입니다.')
        elif kind=='brito':
            with zipfile.ZipFile(local_path(root,row['archive_path'])) as z:
                a=np.load(io.BytesIO(z.read(row['member_path'])),allow_pickle=False).T
            meta['channel_names']=row['channel_locations']
            meta.update(asset_id='BritoBench',condition_id='nominal_1238rpm')
            meta['unit_provenance']='제공처 페이지에 진폭 단위가 확정되어 있지 않습니다.'
        elif kind=='kaist':
            with zipfile.ZipFile(local_path(root,row['archive_path'])) as z:
                d=loadmat(io.BytesIO(z.read(row['member_path'])),simplify_cells=True)['Signal']
            a=d['y_values']['values']
            meta.update(unit='m/s^2',unit_provenance='원본 Test.Lab MKS 선언; g 표시는 내장 계수로 별도 변환',
                        display_g_factor=row['embedded_unit_factor'],channel_names=row['channel_locations'])
        elif kind=='femto':
            snapshot=int(snapshot)
            if not 0<=snapshot<row['snapshot_count']: raise ValueError('수명 기록의 스냅샷 번호가 범위 밖입니다.')
            member=row['sequence_prefix']+f'/acc_{snapshot+1:05d}.csv'
            with zipfile.ZipFile(local_path(root,row['archive'])) as z: b=z.read(member)
            values=np.loadtxt(io.BytesIO(b),delimiter=';' if b';' in b.splitlines()[0] else ',')
            a=values[:,4:6]
            meta.update(snapshot_index=snapshot,snapshots=row['snapshot_count'],role=row['role'],
                        channel_names=row['channel_names'],source_label='가속수명시험 기록; 개별 고장 원인 미확정')
            if snapshot>=19:
                # Only the observed prefix supplies a query baseline/history. No future query labels.
                history=np.asarray(row['nominal_rms_series'][:snapshot+1],dtype=float)
                meta['rul_prefix']={'baseline_rms':np.median(history[:20],axis=0).tolist(),
                                    'recent_rms':history[-5:].tolist(),'observed_count':snapshot+1}
        else: raise ValueError('지원하지 않는 파형 형식입니다.')
        a=matrix(a)
        meta.update(channels=a.shape[1],duration_seconds=len(a)/meta['sample_rate_hz'],samples=len(a))
        return a,meta

    def imported(self, filename, payload, fs=None, unit='unknown', channels_axis=1, skip_columns=0):
        import uuid
        if not isinstance(filename,str) or not filename: raise ValueError('Filename required.')
        if not isinstance(payload,(bytes,bytearray)) or not 0<len(payload)<=64*1024*1024: raise ValueError('Upload must contain 1 byte..64 MiB.')
        if isinstance(channels_axis,bool) or channels_axis not in (0,1): raise ValueError('channels_axis must be 0 or 1.')
        if isinstance(skip_columns,bool) or not isinstance(skip_columns,int) or skip_columns<0: raise ValueError('skip_columns must be a nonnegative integer.')
        name=re.sub(r'[^\w. -]','_',Path(filename).name)[:120]
        suffix=Path(name).suffix.lower()
        if suffix not in ['.npz','.csv','.npy']:
            raise ValueError('가져오기는 NPZ, NPY, CSV를 지원합니다.')
        try:
            if suffix=='.npz':
                with zipfile.ZipFile(io.BytesIO(payload)) as z:
                    if sum(i.file_size for i in z.infolist())>512*1024*1024: raise ValueError('Decompressed upload exceeds 512 MiB.')
                    for item in z.infolist():
                        if not item.filename.endswith('.npy'): raise ValueError('NPZ may contain NPY arrays only.')
                        with z.open(item) as member: _check_npy_header(member)
                with np.load(io.BytesIO(payload),allow_pickle=False) as d:
                    key='vibration' if 'vibration' in d else 'data' if 'data' in d else None
                    if not key: raise ValueError('NPZ에 vibration 또는 data 배열이 필요합니다.')
                    a=d[key]
                    if fs is None and 'sample_rate_hz' in d: fs=float(d['sample_rate_hz'].item())
                    if 'unit' in d: unit=str(d['unit'].item())
                    rpm=float(d['rpm'].item()) if 'rpm' in d else None
            elif suffix=='.npy':
                _check_npy_header(io.BytesIO(payload))
                a=np.load(io.BytesIO(payload),allow_pickle=False); rpm=None
            else:
                text=payload.decode('utf-8-sig')
                if not text.strip(): raise ValueError('CSV is empty.')
                delimiter=';' if ';' in text.splitlines()[0] else ','
                try: a=np.loadtxt(io.StringIO(text),delimiter=delimiter,ndmin=2)
                except ValueError: a=np.loadtxt(io.StringIO(text),delimiter=delimiter,skiprows=1,ndmin=2)
                a=a[:,skip_columns:]; rpm=None
        except (OSError,EOFError,zipfile.BadZipFile,UnicodeError,IndexError,TypeError) as ex:
            raise ValueError('Malformed or unsupported measurement file.') from ex
        if channels_axis==0 and np.asarray(a).ndim==2: a=a.T
        a=matrix(a)
        if fs is None or isinstance(fs,bool) or not isinstance(fs,Real) or not np.isfinite(fs) or not 100<=fs<=200000: raise ValueError('샘플링률은 100~200000 Hz여야 합니다.')
        if rpm is not None and (not math.isfinite(rpm) or not 1e-6<=rpm<=1e9): raise ValueError('Invalid RPM metadata.')
        if unit not in ['unknown','g','m/s^2']: raise ValueError('단위는 unknown, g, m/s^2 중 하나입니다.')
        uploads=RUNTIME/'uploads'; uploads.mkdir(parents=True,exist_ok=True)
        path=uploads/(uuid.uuid4().hex+'_'+name); path.write_bytes(payload)
        return a,{'id':'upload:'+path.stem,'dataset':'사용자 파일','record_id':name,'sample_rate_hz':float(fs),
                  'channels':a.shape[1],'duration_seconds':len(a)/fs,'unit':unit,'rpm':rpm,'bearing_id':None,
                  'source_label':None,'unit_provenance':'파일 메타데이터 또는 사용자 입력','uploaded_path':str(path)}

