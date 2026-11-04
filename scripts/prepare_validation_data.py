"""Inspect and index downloaded public bearing recordings without altering raw signals."""
from pathlib import Path
import sys
import json
import re
from datetime import datetime

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'tmp/validation_deps'))
sys.path.insert(0, str(PROJECT / 'scripts'))
import numpy as np
from scipy.io import loadmat
import pypdfium2 as pdfium
from bearing_frequency import geometry_orders, frequencies

ROOT = PROJECT / 'data/public_validation'


def save_json(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')


def signal_stats(x):
    x=np.asarray(x,dtype=np.float64).ravel()
    if x.size < 2 or not np.isfinite(x).all():
        raise ValueError('Empty, short or non-finite recording')
    centered=x-x.mean()
    variance=np.mean(centered**2)
    return {'samples':x.size,'rms_raw':float(np.sqrt(np.mean(x*x))),
            'mean':float(x.mean()),'peak_abs':float(np.max(np.abs(x))),
            'kurtosis_pearson':float(np.mean(centered**4)/variance**2) if variance else None}


def build_catalog():
    bearings=[
        {'id':'cwru_de_skf_6205','manufacturer':'SKF','model':'6205-2RS JEM','dataset':'CWRU',
         'orders':{'BPFI':5.4152,'BPFO':3.5848,'FTF':0.39828,'BSF':4.7135/2,'2BSF':4.7135},
         'geometry':{'rolling_elements':9,'rolling_diameter':0.3126,'pitch_diameter':1.537,'contact_angle_deg':0},
         'geometry_unit':'inch','source_url':'https://engineering.case.edu/bearingdatacenter/bearing-information',
         'note':'Provider Rolling Element=4.7135 is retained as 2BSF; BSF is half. Geometry is rounded; published orders take precedence. SKF 007/014/021 defects only.'},
        {'id':'cwru_fe_skf_6203','manufacturer':'SKF','model':'6203-2RS JEM','dataset':'CWRU',
         'orders':{'BPFI':4.9469,'BPFO':3.0530,'FTF':0.3817,'BSF':3.9874/2,'2BSF':3.9874},
         'geometry':{'rolling_elements':8,'rolling_diameter':0.2656,'pitch_diameter':1.122,'contact_angle_deg':0},
         'geometry_unit':'inch','source_url':'https://engineering.case.edu/bearingdatacenter/bearing-information',
         'note':'Geometry rounded. This is the fan-end bearing, not the damaged bearing of the downloaded drive-end fault subset.'}
    ]
    for code in ['K001','K002','KA04','KA16','KI04','KI16']:
        path=ROOT/f'extracted/paderborn/{code}/{code}.pdf'
        document=pdfium.PdfDocument(path)
        text='\n'.join(document[i].get_textpage().get_text_range() for i in range(len(document)))
        compact=re.sub(r'\s+',' ',text)
        maker=re.search(r'Manufacturer\s*-\s*(\S+)',compact)[1]
        pitch=float(re.search(r'Pitch circle diameter mm ([\d.]+)',compact)[1])
        elements=int(re.search(r'Number of rolling elements pc\. (\d+)',compact)[1])
        diameter=float(re.search(r'Rolling element diameter mm ([\d.]+)',compact)[1])
        angle=float(re.search(r'Nominal pressure angle ° ([\d.]+)',compact)[1])
        bearings.append({'id':'paderborn_'+code,'manufacturer':maker,'model':'6203','dataset':'Paderborn',
                         'specimen':code,'geometry':{'rolling_elements':elements,'rolling_diameter':diameter,
                         'pitch_diameter':pitch,'contact_angle_deg':angle},'geometry_unit':'mm',
                         'source_local_path':str(path.relative_to(ROOT)),'source_pdf_page':1,
                         'note':'Individual specimen factsheet. Do not replace all 6203 bearings by one shared geometry.'})
    bearings.append({'id':'ims_rexnord_za2115','manufacturer':'Rexnord','model':'ZA-2115','dataset':'IMS',
                     'geometry':{'rolling_elements':16,'rolling_diameter':0.331,'pitch_diameter':2.815,'contact_angle_deg':15.17},
                     'geometry_unit':'inch','source_url':'https://onlinelibrary.wiley.com/doi/10.1155/2015/542472',
                     'source_locator':'Table 2; check against Table 3 at 2000 RPM',
                     'verification_level':'Published research reanalysis; geometry not present in provider README',
                     'note':'16 rollers PER ROW, not 32 in the single-row frequency equation. Approximate kinematic prediction; validate measured frequencies.'})
    document=pdfium.PdfDocument(ROOT/'references/NSK_Electric_Motor_Handbook.pdf')
    count=0
    for i in range(51,59):
        text=document[i].get_textpage().get_text_range()
        series={51:'6200',52:'6200',53:'6300',54:'6300',55:'N/NJ/NU 200',56:'N/NJ/NU 200',57:'N/NJ/NU 300',58:'N/NJ/NU 300'}[i]
        for match in re.finditer(r'(?m)^\s*(\d{3,4}[WM]?)\s+1\s+(0\.\d{3})\s+(0\.\d{3})\s+(0\.\d{3})\s+(0\.\d{3})\s*$',text):
            model=match[1]
            values=dict(zip(['BPFI','BPFO','rolling_element_defect_source','FTF'],map(float,match.groups()[1:])))
            bearings.append({'id':'nsk_'+model,'manufacturer':'NSK','model':model,'series':series,'dataset':'manufacturer_reference',
                             'hz_per_rpm':values,'source_pdf_page':i+1,
                             'source_local_path':'references/NSK_Electric_Motor_Handbook.pdf',
                             'source_url':'https://www.nsk.com/content/dam/nsk/am/en_us/documents/bearings-americas/Electric-Motor-Handbook.pdf',
                             'note':'Table is at 1 RPM, not 1 Hz. Multiply by RPM directly. BALL DEFECT FREQUENCY is preserved under its source name, not silently relabeled BSF. Printed precision is 0.001 Hz at 1 RPM; nominal rounding uncertainty is +/-0.0005*RPM Hz. Manufacturer/series-specific; do not substitute for SKF/FAG geometry.'})
            count+=1
    if count!=120 or len({b['id'] for b in bearings})!=len(bearings):
        raise ValueError(f'Catalog integrity check failed: NSK rows={count}')
    catalog={'created_date':'2026-11-03','assumptions':'Stationary outer ring, rotating inner ring, pure rolling. Actual speed/load/slip/contact angle can shift peaks.',
             'conversion':'orders * RPM / 60 -> Hz; hz_per_rpm * RPM -> Hz',
             'nsk_rows':count,'bearings':bearings}
    save_json(ROOT/'metadata/bearing_frequency_catalog.json',catalog)
    examples=[]
    for bearing in bearings:
        for rpm in ([900,1500] if bearing['dataset']=='Paderborn' else [2000] if bearing['dataset']=='IMS' else [1730,1750,1772,1797] if bearing['dataset']=='CWRU' else [1500,1800]):
            examples.append({'bearing_id':bearing['id'],'rpm':rpm,'frequencies_hz':frequencies(bearing,rpm)})
    save_json(ROOT/'metadata/frequency_examples.json',examples)
    return {b['id']:b for b in bearings}


def process_all():
    catalog=build_catalog()
    manifest=json.loads((ROOT/'download_manifest.json').read_text(encoding='utf-8'))
    records=[]
    ready=ROOT/'ready_npz'
    ready.mkdir(exist_ok=True)
    for row in manifest:
        if row['dataset']!='CWRU' or row['status']!='downloaded':
            continue
        path=ROOT/row['path']
        data=loadmat(path,simplify_cells=True)
        key=next(k for k in data if k.endswith('_DE_time'))
        signal=np.asarray(data[key],dtype=np.float64).ravel()
        stats=signal_stats(signal)
        rpm_keys=[k for k in data if 'RPM' in k.upper()]
        rpm=float(np.asarray(data[rpm_keys[0]]).ravel()[0]) if rpm_keys else row['approx_rpm_from_table']
        fs=row['de_sample_rate_hz']
        out=ready/f'cwru_{path.stem}_DE.npz'
        np.savez_compressed(out,vibration=signal,sample_rate_hz=np.array(fs),rpm=np.array(rpm))
        records.append({'dataset':'CWRU','record_id':'cwru_'+path.stem,'raw_path':row['path'],
                        'ready_path':str(out.relative_to(ROOT)),'fault':row['fault'],'fault_diameter_inch':row['fault_diameter_inch'],
                        'outer_race_position_clock':row['outer_race_position_clock'],'load_hp':row['load_hp'],
                        'channel':key,'sample_rate_hz':fs,'duration_seconds':len(signal)/fs,
                        'rpm':rpm,'rpm_provenance':'MAT RPM variable' if rpm_keys else 'approximate provider table',
                        'bearing_id':'cwru_de_skf_6205','expected_hz':frequencies(catalog['cwru_de_skf_6205'],rpm),
                        'units':'provider amplitude; physical unit not asserted by this pack',
                        'channel_stats':{k:signal_stats(v) for k,v in data.items() if k.endswith('_time')},'stats':stats})
    print('CWRU loaded and verified',len(records),flush=True)
    for path in sorted((ROOT/'extracted/paderborn').glob('*/*.mat')):
        code=path.parent.name
        data=loadmat(path,simplify_cells=True)
        root=data[path.stem]
        channels={y['Name']:y for y in root['Y']}
        rpm=float(np.mean(channels['speed']['Data']))
        n,m,f,_,repeat=path.stem.split('_')
        signals={k:np.asarray(channels[k]['Data'],dtype=np.float64).ravel() for k in ['vibration_1','phase_current_1','phase_current_2']}
        stats={k:signal_stats(v) for k,v in signals.items()}
        row={'dataset':'Paderborn','record_id':path.stem,'raw_path':str(path.relative_to(ROOT)),
             'specimen':code,'fault':('normal' if code.startswith('K00') else 'outer_race' if code.startswith('KA') else 'inner_race'),
             'damage_origin':'healthy' if code.startswith('K00') else 'accelerated_lifetime_damage',
             'repeat':int(repeat),'nominal_rpm':int(n[1:])*100,'rpm':rpm,
             'nominal_torque_nm':int(m[1:])/10,'nominal_radial_load_n':int(f[1:])*100,
             'sample_rate_hz':64000,'sample_rate_provenance':'Lessmeier 2016, section 4.1',
             'bearing_id':'paderborn_'+code,'expected_hz':frequencies(catalog['paderborn_'+code],rpm),
             'channel_stats':stats,'unit_note':'MAT Unit fields are empty; signal numeric values are preserved without physical-unit conversion.',
             'license':'CC-BY-NC-4.0'}
        if len({len(v) for v in signals.values()})!=1:
            raise ValueError(f'Current/vibration alignment failed: {path.name}')
        y=channels['vibration_1']
        time_axis=np.asarray(root['X'][int(y['XIndex'])-1]['Data'])
        row['host_time_axis_apparent_rate_hz']=float(1/np.median(np.diff(time_axis)))
        row['host_time_axis_note']='HostService time axis is preserved separately; its apparent rate differs from the paper nominal 64 kHz. Do not treat host timing as independently calibrated ADC sampling. Frequency analysis defaults to the published 64 kHz.'
        row['duration_seconds']=len(signals['vibration_1'])/64000
        if int(repeat)==1:
            out=ready/f'paderborn_{path.stem}.npz'
            np.savez_compressed(out,vibration=signals['vibration_1'],current_1=signals['phase_current_1'],current_2=signals['phase_current_2'],
                                sample_rate_hz=np.array(64000),rpm=np.array(rpm),host_time_seconds=time_axis)
            row['ready_path']=str(out.relative_to(ROOT))
        records.append(row)
    print('Paderborn loaded and verified',sum(r['dataset']=='Paderborn' for r in records),flush=True)
    files=sorted((ROOT/'extracted/ims/test2/2nd_test').glob('*'))
    files=[f for f in files if f.is_file()]
    if len(files)!=984:
        raise ValueError(f'Expected 984 IMS test 2 files, found {len(files)}')
    end=datetime.strptime(files[-1].name,'%Y.%m.%d.%H.%M.%S')
    for i,path in enumerate(files):
        signal=np.loadtxt(path)
        if signal.shape!=(20480,4):
            raise ValueError(f'Unexpected IMS shape {path.name}: {signal.shape}')
        timestamp=datetime.strptime(path.name,'%Y.%m.%d.%H.%M.%S')
        row={'dataset':'IMS','record_id':'ims_test2_'+path.name,'raw_path':str(path.relative_to(ROOT)),
             'test':2,'sequence_index_zero_based':i,'timestamp':timestamp.isoformat(),'sample_rate_hz':20000,
             'sample_rate_provenance':'Provider README: 20 kHz; 20480 samples. Use duration 1.024 s. Do not infer 20480 Hz just from nominal 1-second wording.',
             'duration_seconds':1.024,'rpm':2000,'bearing_id':'ims_rexnord_za2115',
             'expected_hz':frequencies(catalog['ims_rexnord_za2115'],2000),
             'end_of_test_fault':{'bearing_1':'outer_race'},'instantaneous_fault_label':None,
             'seconds_to_test_end':(end-timestamp).total_seconds(),
             'label_note':'Seconds to test end is a derived benchmark target, not a verified remaining service life or per-window fault label.',
             'channel_stats':{'bearing_'+str(j+1):signal_stats(signal[:,j]) for j in range(4)}}
        if i in [0,len(files)//2,len(files)-1]:
            out=ready/f'ims_test2_{i:04d}.npz'
            np.savez_compressed(out,vibration=signal,sample_rate_hz=np.array(20000),rpm=np.array(2000))
            row['ready_path']=str(out.relative_to(ROOT))
        records.append(row)
    save_json(ROOT/'metadata/record_index.json',records)
    splits={'warning':'Suggested development/evaluation groups, not an official benchmark split. Split before windowing. Freeze evaluation before tuning.',
            'CWRU':{'train_record_ids':[r['record_id'] for r in records if r['dataset']=='CWRU' and r['load_hp'] in [0,1,2]],
                    'test_record_ids':[r['record_id'] for r in records if r['dataset']=='CWRU' and r['load_hp']==3],
                    'limitation':'Load holdout does not prove generalization to unseen bearings or industrial equipment.'},
            'Paderborn':{'train_specimens':['K001','KA04','KI04'],'test_specimens':['K002','KA16','KI16'],
                         'train_record_ids':[r['record_id'] for r in records if r['dataset']=='Paderborn' and r['specimen'] in ['K001','KA04','KI04']],
                         'test_record_ids':[r['record_id'] for r in records if r['dataset']=='Paderborn' and r['specimen'] in ['K002','KA16','KI16']],
                         'limitation':'Two specimens per class only; manufacturer, damage severity and operating conditions can confound results.'},
            'IMS':{'evaluation':'Chronological test 2 degradation tracking. No per-snapshot verified fault-onset label. Do not randomize time windows or use future information to fit thresholds.'}}
    for dataset in ['CWRU','Paderborn']:
        if set(splits[dataset]['train_record_ids']) & set(splits[dataset]['test_record_ids']):
            raise ValueError('Split leakage')
    save_json(ROOT/'metadata/suggested_splits.json',splits)
    save_json(ROOT/'metadata/ims_test2_trend.json',[{'timestamp':r['timestamp'],'seconds_to_test_end':r['seconds_to_test_end'],'channel_stats':r['channel_stats']} for r in records if r['dataset']=='IMS'])
    summary={'record_counts':{d:sum(r['dataset']==d for r in records) for d in ['CWRU','Paderborn','IMS']},
             'ready_npz_count':len(list(ready.glob('*.npz'))),'bearing_catalog_entries':len(catalog),
             'checks':'All indexed recordings loaded; expected shapes, finite samples, nonempty arrays checked; synchronized Paderborn channels have equal lengths. Raw waveforms are unmodified.',
             'cwru_rpm_range':[min(r['rpm'] for r in records if r['dataset']=='CWRU'),max(r['rpm'] for r in records if r['dataset']=='CWRU')],
             'paderborn_host_time_axis_apparent_rate_range_hz':[min(r['host_time_axis_apparent_rate_hz'] for r in records if r['dataset']=='Paderborn'),max(r['host_time_axis_apparent_rate_hz'] for r in records if r['dataset']=='Paderborn')]}
    # Verify replay artifacts can be loaded safely without Python object pickles.
    for path in ready.glob('*.npz'):
        with np.load(path,allow_pickle=False) as replay:
            if not np.isfinite(replay['vibration']).all() or int(replay['sample_rate_hz'])<=0:
                raise ValueError(f'Invalid replay: {path}')
    save_json(ROOT/'metadata/validation_summary.json',summary)
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)


def shape_tree(value, depth=0):
    if depth > 4:
        return str(type(value).__name__)
    if isinstance(value,dict):
        return {k:shape_tree(v,depth+1) for k,v in value.items() if not k.startswith('__')}
    if isinstance(value,list):
        return [shape_tree(v,depth+1) for v in value[:10]]
    if isinstance(value,np.ndarray):
        if value.dtype==object:
            return [shape_tree(v,depth+1) for v in value.flat][:10]
        return {'shape':list(value.shape),'dtype':str(value.dtype),'first':str(value.flat[0]) if value.size else None}
    return value


if __name__=='__main__':
    if '--inspect' in sys.argv:
        p=next((ROOT/'extracted/paderborn/K001').glob('*.mat'))
        print(json.dumps(shape_tree(loadmat(p,simplify_cells=True)),ensure_ascii=False,indent=2))
    else:
        process_all()
