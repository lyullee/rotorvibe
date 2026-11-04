"""Versioned new recording holdout and explicitly exposed development data readers."""
import hashlib,io,json,re,zipfile,threading
from pathlib import Path
import numpy as np
from scipy.io import loadmat
from .independent_data import IndependentRotorCatalog


def file_sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        while block:=stream.read(1024*1024): h.update(block)
    return h.hexdigest()


class UosRotorCatalog:
    """16kHz/MOCHU6204/bearing-healthy subset. Entire 1200RPM files stay together."""
    def __init__(self,root):
        self.root=Path(root).resolve()
        self.records={r['id']:r for r in json.loads((self.root/'metadata/record_plan.json').read_text(encoding='utf-8'))}
        extra=self.root/'metadata/matched_normal_plan.json'
        if extra.exists(): self.records.update({r['id']:r for r in json.loads(extra.read_text(encoding='utf-8'))})

    def rows(self,role=None): return [r for r in self.records.values() if role is None or r['role']==role]

    def load(self,record_id,*,frozen_model_sha256=None):
        row=self.records[record_id]
        if row['role']=='reserved_new_test':
            if not isinstance(frozen_model_sha256,str) or not re.fullmatch('[0-9a-f]{64}',frozen_model_sha256):
                raise PermissionError('New UOS test recordings require a prospectively frozen model SHA256.')
            audit=self.root/'metadata/new_test_access.jsonl'
            with audit.open('a',encoding='utf-8') as stream:
                stream.write(json.dumps({'record_id':record_id,'model_sha256':frozen_model_sha256,'purpose':'frozen_final_test'})+'\n')
        path=(self.root/row['path']).resolve()
        if not path.is_relative_to(self.root): raise ValueError('Recording path leaves dataset root.')
        if file_sha(path)!=row['provider_sha256']: raise ValueError('Recording checksum mismatch.')
        data=loadmat(path,variable_names=['Data'],simplify_cells=True)
        values=np.asarray(data['Data'],dtype=float).squeeze()
        if values.ndim!=1 or len(values)!=1280000 or not np.isfinite(values).all(): raise ValueError('Expected 1280000 finite raw single-channel g values.')
        meta={'id':record_id,'dataset':'UOS6204','asset_id':'UOS_MOCHU6204','condition_id':'steady_bearing_healthy',
            'unit':'g','unit_provenance':'Provider states Data field in g; sensor calibration certificate not supplied',
            'sample_rate_hz':row['sample_rate_hz'],'rpm':row['rpm'],'rpm_provenance':'provider nominal; no tachometer array',
            'channel_names':['radial_vibration'],'duration_seconds':1280000/row['sample_rate_hz'],'recording_id':row['recording_id'],
            'reference_label':row['reference_label'],'role':row['role'],'bearing':'MOCHU 6204'}
        return values[:,None],meta


class ExposedCrossSpeedDevelopment:
    """An opened old final test may be used for development, never called new holdout.

    Preserves the original final-test access ledger. Development reads have their
    own purpose ledger, and require the completed prior execution record.
    """
    def __init__(self,root):
        self.root=Path(root).resolve(); self.catalog=IndependentRotorCatalog(root); self.lock=threading.Lock()
        execution=json.loads((self.root/'metadata/final_test_execution.json').read_text(encoding='utf-8'))
        if execution['status']!='complete': raise ValueError('Prior test is not recorded as completed/exposed.')

    def rows(self): return self.catalog.rows()

    def load(self,record_id):
        row=self.catalog.records[record_id]
        path=self.root/'raw/cross_speed'/row['archive_name']
        with zipfile.ZipFile(path) as archive: raw=archive.read(row['archived_filename'])
        if hashlib.sha256(raw).hexdigest()!=row['file_sha256']: raise ValueError('Exposed development record checksum mismatch.')
        d=loadmat(io.BytesIO(raw),variable_names=['signals','fs','speed_rpm','original_file'],simplify_cells=True)
        a=np.asarray(d['signals'],dtype=float).T
        if a.shape!=(25600,4) or not np.isfinite(a).all() or d['fs']!=25600 or d['speed_rpm']!=int(row['speed_rpm']): raise ValueError('Invalid exposed signal.')
        if str(d['original_file'])!=row['original_file']: raise ValueError('Original recording identity mismatch.')
        if row['role']=='reserved_target_test':
            with self.lock, (self.root/'metadata/exposed_development_access.jsonl').open('a',encoding='utf-8') as stream:
                stream.write(json.dumps({'record_id':record_id,'purpose':'user_authorized_development_after_exposure','new_independent_test':False})+'\n')
        return a,{'rpm':int(row['speed_rpm']),'group_id':row['group_id'],'reference_label':{'imbalance':'unbalance'}.get(row['condition'],row['condition']),
            'asset_id':'CrossSpeed2026Bench','condition_id':'steady','unit':'unknown','channel_names':['location1_vertical','location1_horizontal','location2_vertical','location2_horizontal']}
