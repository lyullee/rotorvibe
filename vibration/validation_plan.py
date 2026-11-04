"""Prospective split/freeze/access contracts. This is not a sandbox for host code."""
from dataclasses import dataclass,asdict
from datetime import datetime,timezone
from pathlib import Path
import hashlib,io,json,os,re,threading

_ROLES={'normal_fit','normal_calibration','fault_fit','development','final_test'}


def _digest(value):
    if not isinstance(value,str) or re.fullmatch('[0-9a-f]{64}',value) is None: raise ValueError('SHA256 hex digest required')
    return value


@dataclass(frozen=True)
class DatasetRecord:
    record_id: str
    acquisition_id: str
    session_id: str
    installation_id: str
    rig_id: str
    label: str
    role: str
    sha256: str


class ValidationPlan:
    def __init__(self,records,*,independent_by='acquisition'):
        self.records=tuple(records); self.independent_by=independent_by
        if not self.records or independent_by not in ('acquisition','session','installation','rig'): raise ValueError('Explicit validation unit required')
        ids=set(); hashes={}; groups={}; final=set(); development=set()
        for row in self.records:
            if not isinstance(row,DatasetRecord): raise ValueError('DatasetRecord required')
            for value in (row.record_id,row.acquisition_id,row.session_id,row.installation_id,row.rig_id,row.label):
                if not isinstance(value,str) or not value.strip(): raise ValueError('Original acquisition and installation identities required')
            if row.role not in _ROLES: raise ValueError('Unknown data role')
            _digest(row.sha256)
            if row.record_id in ids: raise ValueError('Duplicate record ID')
            ids.add(row.record_id)
            if row.role.startswith('normal_') and row.label!='normal': raise ValueError('Normal role needs confirmed normal label')
            if row.role=='fault_fit' and row.label=='normal': raise ValueError('Fault head cannot train on normal class')
            if row.sha256 in hashes: raise ValueError('Duplicate raw records do not constitute independent acquisitions')
            for store,key in ((hashes,row.sha256),(groups,(row.rig_id,row.acquisition_id))):
                prior=store.setdefault(key,row.role)
                if prior!=row.role: raise ValueError('Original acquisition or raw duplicate crosses data roles')
            field={'acquisition':'acquisition_id','session':'session_id','installation':'installation_id','rig':'rig_id'}[independent_by]
            identity=(row.rig_id,getattr(row,field))
            (final if row.role=='final_test' else development).add(identity)
        if final&development: raise ValueError('Final test shares declared independence unit with development')

    def fitting_records(self,role):
        if role not in ('normal_fit','normal_calibration','fault_fit','development'): raise ValueError('Final test is not fitting/calibration data')
        return tuple(r for r in self.records if r.role==role)

    def freeze(self,path,*,model_sha256,preprocessing_sha256):
        payload={'schema':'vibration.validation-plan.v1','records':[asdict(r) for r in self.records],
                 'independent_by':self.independent_by,'model_sha256':_digest(model_sha256),
                 'preprocessing_sha256':_digest(preprocessing_sha256)}
        path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
        content=(json.dumps(payload,sort_keys=True,indent=2)+'\n').encode('utf8')
        with path.open('xb') as stream: stream.write(content)
        return hashlib.sha256(content).hexdigest()


class FrozenEvaluation:
    def __init__(self,plan_path,*,plan_sha256,access_log,max_record_bytes=128*1024*1024):
        content=Path(plan_path).read_bytes()
        if hashlib.sha256(content).hexdigest()!=_digest(plan_sha256): raise ValueError('Frozen plan checksum differs')
        p=json.loads(content)
        if p.get('schema')!='vibration.validation-plan.v1': raise ValueError('Unknown frozen plan')
        self.plan=ValidationPlan([DatasetRecord(**r) for r in p['records']],independent_by=p['independent_by'])
        self.model_sha256=_digest(p['model_sha256']); self.preprocessing_sha256=_digest(p['preprocessing_sha256'])
        self.access_log=Path(access_log); self._lock=threading.Lock()
        if isinstance(max_record_bytes,bool) or not isinstance(max_record_bytes,int) or max_record_bytes<=0: raise ValueError('Positive snapshot size limit required')
        self.max_record_bytes=max_record_bytes

    def load_test(self,record_id,path,loader,*,model_sha256,preprocessing_sha256,replay=False):
        if not callable(loader) or not isinstance(replay,bool): raise ValueError('Explicit loader/replay policy required')
        if _digest(model_sha256)!=self.model_sha256 or _digest(preprocessing_sha256)!=self.preprocessing_sha256:
            raise ValueError('Model/preprocessing changed after freeze')
        record=next((r for r in self.plan.records if r.record_id==record_id),None)
        if record is None or record.role!='final_test': raise ValueError('Record is not in the frozen final test')
        with Path(path).open('rb') as stream:
            snapshot=stream.read(self.max_record_bytes+1)
        if len(snapshot)>self.max_record_bytes: raise ValueError('Raw record exceeds bounded snapshot size')
        if hashlib.sha256(snapshot).hexdigest()!=record.sha256: raise ValueError('Raw data checksum differs')
        with self._lock:
            self.access_log.parent.mkdir(parents=True,exist_ok=True)
            lock_path=self.access_log.with_name(self.access_log.name+'.lock')
            try:
                lock=lock_path.open('x',encoding='utf8')
            except FileExistsError as exc: raise RuntimeError('Access ledger is locked; do not decode concurrently') from exc
            try:
                seen=[]
                if self.access_log.exists(): seen=[json.loads(line) for line in self.access_log.read_text(encoding='utf8').splitlines()]
                if any(r['record_id']==record_id for r in seen) and not replay:
                    raise PermissionError('Already exposed; use an explicitly labeled replay or a new acquisition')
                event={'record_id':record_id,'model_sha256':model_sha256,'preprocessing_sha256':preprocessing_sha256,
                       'purpose':'historical_replay' if replay else 'frozen_final_test',
                       'opened_utc':datetime.now(timezone.utc).isoformat()}
                with self.access_log.open('a',encoding='utf8') as stream:
                    stream.write(json.dumps(event)+'\n'); stream.flush(); os.fsync(stream.fileno())
            finally:
                lock.close(); lock_path.unlink()
        # Decode exactly the hashed immutable snapshot, not a path that a caller
        # could replace between verification and loading. The host owns preprocessing.
        return loader(io.BytesIO(snapshot))
