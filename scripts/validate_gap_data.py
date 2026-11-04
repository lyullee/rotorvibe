"""Stream validation of supplementary signals; no bulk decompression to disk."""
from pathlib import Path
import sys
import json
import re
import io
import zipfile
import collections
from datetime import datetime
import numpy as np

PROJECT=Path(__file__).resolve().parents[1]
ROOT=PROJECT/'data/gap_supplement'
sys.path.insert(0,str(PROJECT/'tmp/validation_deps'))

def save(name,value):
    path=ROOT/'metadata'/name
    path.parent.mkdir(exist_ok=True,parents=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')

def brito():
    groups={'normal':[1,3,6,9,17],'misalignment':[2,10,11,13,16],
            'unbalance':[4,7,15,18,20],'looseness':[5,8,12,14,19]}
    labels={test:label for label,tests in groups.items() for test in tests}
    splits={test:('train' if i<3 else 'validation' if i==3 else 'test') for tests in groups.values() for i,test in enumerate(tests)}
    files=sorted((ROOT/'raw/brito').glob('*.zip'))
    if len(files)!=20: raise ValueError(f'Need 20 original trial archives, found {len(files)}')
    records=[]
    checks=[]
    ready=ROOT/'ready_npz'
    ready.mkdir(exist_ok=True)
    for path in files:
        trial=int(re.search(r'Test (\d+)',path.name)[1])
        with zipfile.ZipFile(path) as z:
            members=sorted((i for i in z.infolist() if i.filename.endswith('.npy')),key=lambda i:i.filename)
            if len(members)!=420: raise ValueError(f'{path.name}: expected 420 NPY records')
            for i,member in enumerate(members):
                a=np.load(io.BytesIO(z.read(member)),allow_pickle=False)
                if a.shape!=(4,25000) or not np.isfinite(a).all():
                    raise ValueError(f'Invalid waveform: {member.filename}')
                row={'dataset':'Brito_2023_v3','record_id':f'brito_{trial:02d}_{i:03d}',
                     'archive_path':str(path.relative_to(ROOT)),'member_path':member.filename,
                     'trial_id':trial,'fault':labels[trial],'suggested_split':splits[trial],
                     'sample_rate_hz':25000,'samples_per_channel':25000,'duration_seconds':1,
                     'channel_count':4,'approx_reported_shaft_rpm':1238,
                     'rpm_note':'Provider-reported approximate constant shaft speed, not a measured tachometer channel in each file.',
                     'channel_locations':['pulley_side_vertical','pulley_side_horizontal','disc_side_vertical','disc_side_horizontal'],
                     'units':'Amplitude unit not explicitly declared on the reviewed dataset page; calibration adjustment is reported but raw calibration certificates are not included.',
                     'rms_raw_per_channel':np.sqrt(np.mean(a*a,axis=1)).tolist()}
                if i in [0,419]:
                    out=ready/f'brito_{trial:02d}_{i:03d}.npz'
                    np.savez_compressed(out,vibration=a.T,sample_rate_hz=np.array(25000),rpm_approx=np.array(1238))
                    row['ready_path']=str(out.relative_to(ROOT))
                records.append(row)
        checks.append({'archive':str(path.relative_to(ROOT)),'records':420,'shape':[4,25000],'finite':True,'zip_member_crc':'All NPY members read successfully'})
        print('VERIFIED',path.name,flush=True)
    save('brito_record_index.json',records)
    save('brito_archive_validation.json',checks)
    save('brito_experiment_splits.json',{'source':'Engineering proposal, not provider official split',
         'groups':{label:{'train_trials':v[:3],'validation_trials':v[3:4],'test_trials':v[4:]} for label,v in groups.items()},
         'record_counts':{s:sum(r['suggested_split']==s for r in records) for s in ['train','validation','test']},
         'note':'All 420 time-adjacent records from one physical experiment stay together. This controls trial leakage but does not prove generalization to another industrial machine.'})
    save('brito_validation_summary.json',{'trials':20,'records':len(records),'channels_per_record':4,
         'total_channel_waveforms':len(records)*4,'ready_npz':40,'physical_unit_confirmed':False,
         'provider_license':'CC-BY-4.0','all_records_loaded_finite_and_expected_shape':True})

def inventory():
    result=[]
    for path in (ROOT/'raw').rglob('*.zip'):
        if path.parent.name=='brito': continue
        with zipfile.ZipFile(path) as z:
            members=[{'path':i.filename,'bytes':i.file_size,'compressed_bytes':i.compress_size} for i in z.infolist()]
            result.append({'archive':str(path.relative_to(ROOT)),'members':members})
            print(path.name,'members',len(members),'first',members[:12],flush=True)
    save('additional_archive_inventory.json',result)

def femto():
    base=ROOT/'extracted/femto'
    archives={n:zipfile.ZipFile(base/n) for n in ['Training_set.zip','Test_set.zip','Validation_Set.zip']}
    inventory_rows=[]
    groups={}
    for name,z in archives.items():
        inventory_rows.append({'archive':str((base/name).relative_to(ROOT)),
                               'members':[{'path':i.filename,'bytes':i.file_size,'crc32':i.CRC} for i in z.infolist()]})
        groups[name]=collections.defaultdict(list)
        for member in z.infolist():
            if '/acc_' in member.filename and member.filename.endswith('.csv'):
                groups[name][member.filename.split('/')[1]].append(member)
        for bearing,members in groups[name].items():
            members.sort(key=lambda x:x.filename)
            ids=[int(re.search(r'acc_(\d+)',i.filename)[1]) for i in members]
            if ids!=list(range(1,len(ids)+1)): raise ValueError('Missing or reordered FEMTO sequence')
    save('femto_archive_inventory.json',inventory_rows)
    references=[]
    for bearing,test_members in groups['Test_set.zip'].items():
        full=groups['Validation_Set.zip'][bearing]
        if len(full)<=len(test_members): raise ValueError('Full test endpoint must follow truncated test endpoint')
        reformatted=0
        for a,b in zip(test_members,full):
            if a.CRC!=b.CRC or a.file_size!=b.file_size:
                left=archives['Test_set.zip'].read(a)
                right=archives['Validation_Set.zip'].read(b)
                left_values=np.loadtxt(io.BytesIO(left),delimiter=';' if b';' in left.splitlines()[0] else ',')
                right_values=np.loadtxt(io.BytesIO(right),delimiter=';' if b';' in right.splitlines()[0] else ',')
                if not np.array_equal(left_values,right_values): raise ValueError('Truncated prefix numerical values do not match full trajectory')
                reformatted+=1
        references.append({'bearing':bearing,'truncated_snapshot_count':len(test_members),'full_snapshot_count':len(full),
                            'matching_prefix_verified_by':'CRC32/size match or exact equality of all parsed numeric values when CSV encoding differs',
                            'numerically_verified_reformatted_prefix_files':reformatted,
                            'reference_rul_seconds_at_truncation':(len(full)-len(test_members))*10,
                            'provenance':'Derived from provided full/truncated prefix pair using nominal 10-second snapshot cadence, not an independently supplied ground-truth text file.',
                            'target':'Time to recorded accelerated-test endpoint, not transferable field service life',
                            'evaluation_only_do_not_train_on_full_test':True})
    save('femto_test_reference_rul.json',references)
    trajectories=[]
    ready=ROOT/'ready_npz'
    ready.mkdir(exist_ok=True)
    for name,z in archives.items():
        for bearing,members in groups[name].items():
            rms=[]
            peak=[]
            times=[]
            delimiter=None
            for index,member in enumerate(members):
                content=z.read(member)
                if delimiter is None: delimiter=';' if b';' in content.splitlines()[0] else ','
                a=np.loadtxt(io.BytesIO(content),delimiter=delimiter)
                if a.shape!=(2560,6) or not np.isfinite(a).all(): raise ValueError(f'Invalid FEMTO snapshot {member.filename}: {a.shape}')
                signal=a[:,4:6]
                rms.append(np.sqrt(np.mean(signal*signal,axis=0)).tolist())
                peak.append(np.max(np.abs(signal),axis=0).tolist())
                times.append(float(a[0,0]*3600+a[0,1]*60+a[0,2]+a[0,3]/1e6))
                if name!='Test_set.zip' and index in [0,len(members)//2,len(members)-1]:
                    out=ready/f'femto_{bearing}_{index:05d}.npz'
                    np.savez_compressed(out,vibration=signal,sample_rate_hz=np.array(25600),
                                        rpm=np.array({1:1800,2:1650,3:1500}[int(bearing[7])]))
            unwrapped=[]
            offset=0
            for t in times:
                if unwrapped and t+offset<unwrapped[-1]-43200: offset+=86400
                unwrapped.append(t+offset)
            gaps=np.diff(unwrapped)
            condition=int(bearing[7])
            trajectories.append({'bearing':bearing,'archive':str((base/name).relative_to(ROOT)),
                                 'sequence_prefix':members[0].filename.rsplit('/',1)[0],
                                 'snapshot_count':len(members),'sample_rate_hz':25600,
                                 'snapshot_samples':2560,'channels':2,'channel_names':['horizontal','vertical'],
                                 'role':'training_complete_life' if name=='Training_set.zip' else 'truncated_test_input' if name=='Test_set.zip' else 'held_out_full_life_evaluation_only',
                                 'nominal_snapshot_interval_seconds':10,
                                 'observed_median_snapshot_gap_seconds':float(np.median(gaps)),
                                 'observed_gap_min_max_seconds':[float(gaps.min()),float(gaps.max())],
                                 'nominal_rpm':{1:1800,2:1650,3:1500}[condition],
                                 'nominal_load_n':{1:4000,2:4200,3:5000}[condition],
                                 'time_axis_note':'Nominal index*10 s is used for benchmark labels; original timestamp-derived gap statistics are preserved for audit.',
                                 'nominal_rms_series':rms,'peak_abs_series':peak,
                                 'amplitude_unit_note':'Values preserved as delivered; do not infer conversion from sensor model alone.'})
            print('VERIFIED FEMTO',name,bearing,len(members),flush=True)
    save('femto_trajectory_index.json',trajectories)
    summary={'complete_training_bearings':len(groups['Training_set.zip']),
             'held_out_full_bearings':len(groups['Validation_Set.zip']),
             'truncated_test_bearings':len(groups['Test_set.zip']),
             'complete_life_unique_snapshots':sum(len(v) for n in ['Training_set.zip','Validation_Set.zip'] for v in groups[n].values()),
             'truncated_snapshots_duplicate_prefixes':sum(len(v) for v in groups['Test_set.zip'].values()),
             'all_acceleration_snapshots_loaded_finite_expected_shape':True,
             'input_shape_per_snapshot':[2560,6],'vibration_channels':[4,5],
             'rul_reference_targets':len(references),
             'warning':'Do not train on full held-out test lives, even though the download contains them. Last recorded test endpoint is not necessarily functional destruction of the bearing.'}
    save('femto_validation_summary.json',summary)
    print(json.dumps(summary,indent=2),flush=True)

def kaist():
    from scipy.io import loadmat
    path=ROOT/'raw/kaist/vibration.zip'
    rows=[]
    ready=ROOT/'ready_npz'
    ready.mkdir(exist_ok=True)
    with zipfile.ZipFile(path) as z:
        members=sorted((i for i in z.infolist() if i.filename.endswith('.mat')),key=lambda i:i.filename)
        if len(members)!=45: raise ValueError('Expected 45 KAIST MAT measurements')
        for member in members:
            signal=loadmat(io.BytesIO(z.read(member)),simplify_cells=True)['Signal']
            x=signal['x_values']
            y=signal['y_values']
            a=np.asarray(y['values'])
            fs=1/float(x['increment'])
            if a.ndim!=2 or a.shape[1]!=4 or a.shape[0]!=int(x['number_of_values']) or not np.isfinite(a).all():
                raise ValueError(f'Invalid KAIST measurement: {member.filename}')
            if not np.isclose(fs,25600): raise ValueError('Unexpected KAIST sample rate')
            quantity=y['quantity']
            factor=float(quantity['unit_transformation']['factor'])
            offset=float(quantity['unit_transformation']['offset'])
            if quantity['label']!='g' or 'MKS' not in quantity['info'] or not np.isclose(factor,1/9.80665) or not np.isclose(offset,0):
                raise ValueError('KAIST physical-unit interpretation requires review')
            stem=Path(member.filename).stem
            fields=stem.split('_')
            label={'Normal':'normal','BPFI':'inner_race','BPFO':'outer_race','Misalign':'misalignment','Unbalance':'unbalance','Unbalalnce':'unbalance'}[fields[1]]
            row={'record_id':'kaist_'+stem,'archive_path':str(path.relative_to(ROOT)),
                 'member_path':member.filename,'load_torque_nm':float(fields[0][:-2]),
                 'fault':label,'severity_code':'_'.join(fields[2:]) or None,
                 'original_fault_token':fields[1],
                 'filename_typo_note':'Original Unbalalnce spelling normalized to unbalance; original member name preserved.' if fields[1]=='Unbalalnce' else None,
                 'severity_note':'Original filename code preserved; physical severity units are not inferred here.',
                 'sample_rate_hz':fs,'samples_per_channel':len(a),'channels':4,'duration_seconds':len(a)/fs,
                 'channel_locations':['housing_A_x','housing_A_y','housing_B_x','housing_B_y'],
                 'embedded_quantity_label':str(quantity['label']),
                 'embedded_unit_info':str(quantity['info']),
                 'embedded_unit_factor':factor,'embedded_unit_offset':offset,
                 'raw_unit_interpretation':'m/s^2, based on embedded Test.Lab MKS declaration and LENGTH/TIME^2 dimensions',
                 'derived_display_unit':'g','derived_display_formula':'raw * embedded_unit_factor + embedded_unit_offset',
                 'unit_interpretation_note':'Provider landing page labels vibration g, while raw MAT explicitly says data saved in MKS. Both raw values and derived display values are retained; do not relabel raw MKS values as g.',
                 'rpm':None,'rpm_note':'No synchronized RPM channel identified in this vibration archive; do not infer RPM from load code.',
                 'rms_raw_mks_per_channel':np.sqrt(np.mean(a*a,axis=0)).tolist(),
                 'rms_display_g_per_channel':(np.sqrt(np.mean(a*a,axis=0))*factor).tolist()}
            # Bounded 2-second snippets are for reader/replay validation, not a new independent dataset.
            out=ready/f'kaist_{stem}_first2s.npz'
            snippet=a[:int(2*fs)].copy()
            np.savez_compressed(out,vibration=snippet,vibration_display_g=snippet*factor+offset,
                                sample_rate_hz=np.array(fs),unit=np.array('m/s^2'),display_unit=np.array('g'))
            row['ready_path']=str(out.relative_to(ROOT))
            row['ready_span_seconds']=2
            rows.append(row)
            print('VERIFIED KAIST',member.filename,a.shape,flush=True)
    save('kaist_record_index.json',rows)
    save('kaist_validation_summary.json',{'mat_measurements':len(rows),
         'fault_families':sorted({r['fault'] for r in rows}),
         'load_torque_nm':sorted({r['load_torque_nm'] for r in rows}),
         'sample_rate_hz':25600,'all_measurements_loaded_finite_shape_checked':True,
         'total_duration_seconds':sum(r['duration_seconds'] for r in rows),
         'unit_issue_resolved_from_embedded_metadata':'Raw data declares MKS; display g uses embedded factor 0.101971621297793. Preserve both representations.',
         'ready_npz_snippets':45,'ready_npz_span_seconds_each':2,
         'commercial_data_license':'CC-BY-4.0, retain source attribution'})

def mathworks():
    from scipy.io import loadmat
    import h5py
    path=ROOT/'raw/mathworks/vibrationData.zip'
    with zipfile.ZipFile(path) as z:
        bad=z.testzip()
        if bad: raise ValueError('MathWorks ZIP CRC failed')
        license_text=z.read('license.txt').decode()
        (ROOT/'references/mathworks_dataset_license.txt').write_text(license_text,encoding='utf-8')
        machine=loadmat(io.BytesIO(z.read('MachineData.mat')),simplify_cells=True)
        with h5py.File(io.BytesIO(z.read('FeatureEntire.mat')),'r') as f:
            hdf_summary={'top_level_keys':list(f.keys())}
        save('mathworks_validation_summary.json',{'zip_crc_passed':True,'files':z.namelist(),
             'machine_data_variables':{k:type(v).__name__ for k,v in machine.items() if not k.startswith('__')},
             'feature_file':hdf_summary,
             'import_limitation':'MATLAB table/class serialization is not decoded into labeled Python arrays in this pack; raw MAT files and original MATLAB workflow are retained.',
             'label_limitation':'Before/After maintenance are anomaly proxy labels, not confirmed fault causes.',
             'license':'Redistribution/use permitted with original notice, conditions, disclaimer and citation. See references/mathworks_dataset_license.txt.',
             'attribution':'Data Set provided by The MathWorks, Inc. (www.mathworks.com).'})

if __name__=='__main__':
    if '--brito' in sys.argv: brito()
    if '--inventory' in sys.argv: inventory()
    if '--femto' in sys.argv: femto()
    if '--kaist' in sys.argv: kaist()
    if '--mathworks' in sys.argv: mathworks()
