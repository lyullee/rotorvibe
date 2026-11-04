"""Explicitly grouped public rotor data reader. Reserved target arrays stay closed."""
import csv,io,json,hashlib,re,zipfile
from pathlib import Path
import numpy as np
from scipy.io import loadmat

CROSS_CHANNELS=('location1_vertical','location1_horizontal','location2_vertical','location2_horizontal')
MARRA_CHANNELS=('DE_horizontal','DE_vertical','NDE_horizontal','NDE_vertical')


class IndependentRotorCatalog:
    def __init__(self,root):
        self.root=Path(root).resolve(); self.records={}
        folder=self.root/'raw/cross_speed'
        manifest=folder/'dataset_manifest.csv'; partitions=folder/'recording_disjoint_partitions.csv'
        roles={}
        if partitions.exists():
            with partitions.open(encoding='utf-8-sig',newline='') as stream:
                for row in csv.DictReader(stream):
                    if row['scenario']=='MS_600_900_to_1200' and row.get('publication_fold','0')=='0':
                        if row['sample_id'] in roles and roles[row['sample_id']]!=row['role']: raise ValueError('Conflicting provider partitions.')
                        roles[row['sample_id']]=row['role']
        if manifest.exists():
            with manifest.open(encoding='utf-8-sig',newline='') as stream:
                for row in csv.DictReader(stream):
                    sample=row['sample_id']; role=roles.get(sample)
                    if role not in ('train','validation','test'): raise ValueError('Missing provider partition.')
                    self.records['cross_speed:'+sample]={**row,'dataset':'CrossSpeed2026','role':'reserved_target_test' if role=='test' else 'source_'+role}
        group_roles={}
        for row in self.records.values():
            group=row['group_id']; previous=group_roles.setdefault(group,row['role'])
            if previous!=row['role']: raise ValueError('Acquisition group crosses source/test roles.')

    def rows(self,*,role=None,normal_only=False):
        return [{'id':key,**row} for key,row in self.records.items() if (role is None or row['role']==role) and (not normal_only or row['condition']=='normal')]

    def _archive(self,path):
        resolved=(self.root/path).resolve()
        if not resolved.is_relative_to(self.root): raise ValueError('Archive path leaves data root.')
        return resolved

    def load(self,record_id,*,frozen_model_sha256=None):
        row=self.records[record_id]
        if row['role']=='reserved_target_test':
            if not isinstance(frozen_model_sha256,str) or not re.fullmatch('[0-9a-f]{64}',frozen_model_sha256):
                raise PermissionError('Reserved target arrays require a frozen model SHA256; no development access.')
            # An explicit opening leaves an audit trail before any signal is decoded.
            audit=self.root/'metadata/reserved_access.jsonl'; audit.parent.mkdir(parents=True,exist_ok=True)
            with audit.open('a',encoding='utf-8') as stream:
                stream.write(json.dumps({'record_id':record_id,'frozen_model_sha256':frozen_model_sha256})+'\n')
        path=self._archive('raw/cross_speed/'+row['archive_name'])
        with zipfile.ZipFile(path) as archive:
            info=archive.getinfo(row['archived_filename'])
            if info.file_size>16*1024*1024: raise ValueError('Unexpected MATLAB member size.')
            raw=archive.read(info)
        if hashlib.sha256(raw).hexdigest()!=row['file_sha256']: raise ValueError('MATLAB file checksum differs from provider manifest.')
        data=loadmat(io.BytesIO(raw),simplify_cells=True); a=np.asarray(data['signals'],dtype=float).T
        if a.shape!=(25600,4) or not np.isfinite(a).all() or float(data['fs'])!=25600 or float(data['speed_rpm'])!=int(row['speed_rpm']):
            raise ValueError('MATLAB acquisition contract mismatch.')
        if str(data['original_file'])!=row['original_file'] or int(data['second_id'])!=int(row['second_id']): raise ValueError('Acquisition identity mismatch.')
        # Original MATLAB 'healthy' is normalized to manifest 'normal'; labels are metadata only.
        declared={'healthy':'normal','imbalance':'unbalance'}.get(str(data['condition']),str(data['condition']))
        label={'imbalance':'unbalance'}.get(row['condition'],row['condition'])
        if declared!=label: raise ValueError('Provider label metadata disagree.')
        meta={'id':record_id,'record_id':row['sample_id'],'dataset':'CrossSpeed2026','duration_seconds':1.,'channels':4,
            'asset_id':'CrossSpeed2026Bench','condition_id':'speed_'+row['speed_rpm'],
            'sample_rate_hz':25600,'rpm':int(row['speed_rpm']),'rpm_provenance':'provider nominal; no tachometer array in release',
            'unit':'unknown','unit_provenance':'amplitude unit not stated in released README','channel_names':list(CROSS_CHANNELS),
            'acquisition_id':row['original_file'],'group_id':row['group_id'],'role':row['role'],
            'reference_label':label,'label_usage':'metadata only; excluded from signal features'}
        return a,meta

    def marra_members(self):
        result=[]
        for path in sorted((self.root/'raw/marra').glob('*.zip')):
            with zipfile.ZipFile(path) as archive:
                for member in archive.namelist():
                    if member.lower().endswith('.lvm'):
                        result.append({'archive':path.name,'member':member,'role':'development_reference'})
        return result

    def load_marra(self,archive_name,member):
        path=self._archive('raw/marra/'+archive_name)
        with zipfile.ZipFile(path) as archive:
            info=archive.getinfo(member)
            if info.file_size>64*1024*1024: raise ValueError('Unexpected LVM size.')
            text=archive.read(info).decode('utf-8-sig',errors='replace')
        # Preserve empty time/derived-velocity fields after the final trigger edge.
        # The X_Value column is a point index, NOT seconds (header Delta_X=1).
        rows=[]
        for line in text.splitlines():
            parts=line.split('\t') if '\t' in line else line.split()
            if len(parts)<7: continue
            try: values=[float(p.replace(',','.')) if p.strip() else float('nan') for p in parts[:7]]
            except ValueError: continue
            rows.append(values)
        a=np.asarray(rows,dtype=float)
        if a.shape!=(36000,7) or not np.isfinite(a[:,[0,2,3,4,5,6]]).all() or not np.array_equal(a[:,0],np.arange(36000)):
            raise ValueError('Expected 36000 LVM rows with trigger + four acceleration channels.')
        signal=a[:,3:7]; trigger=a[:,2]
        threshold=(np.min(trigger)+np.max(trigger))/2
        edges=np.flatnonzero((trigger[:-1]<=threshold)&(trigger[1:]>threshold))+1
        if len(edges)<3: raise ValueError('No reliable multi-revolution trigger.')
        periods=np.diff(edges)/6000
        rpm=float(60/np.median(periods)); jitter=float(np.std(periods)/np.mean(periods))
        if jitter>.05: raise ValueError('Trigger spacing is too irregular for a scalar RPM.')
        label={'Baseline':'normal','Unbalance_DE':'unbalance','Unbalance_NDE':'unbalance','Misalignment_NDE':'misalignment',
            'Bearing':'bearing_fault','Bearing+Unbalance':'bearing_and_unbalance'}.get(Path(archive_name).stem)
        if label is None: raise ValueError('Unknown Marra condition.')
        return signal,{'id':'marra:'+archive_name+':'+member,'record_id':member,'dataset':'Marra2024','duration_seconds':6.,'channels':4,
            'asset_id':'Marra2024Bench','condition_id':f'speed_{round(rpm/60)}Hz',
            'sample_rate_hz':6000,'rpm':rpm,'rpm_provenance':'median optical-trigger period','trigger_jitter_ratio':jitter,
            'unit':'unknown','unit_provenance':'acceleration physical unit not verified from acquisition calibration',
            'channel_names':list(MARRA_CHANNELS),'reference_label':label,'acquisition_id':member,'role':'development_reference',
            'grouping_caution':'Provider does not expose independent reassembly IDs; do not treat windows as independent experiments.'}
