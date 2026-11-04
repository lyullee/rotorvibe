"""Actual source recordings through public Python composition; no final-test access."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
import vibration.bootstrap
from vibration import ConditionedDiagnostic
from vibration.fault_discrimination import FaultDiscriminator
from examples.fault_discrimination_composition import create_analyzer,analyze_block
from scripts.develop_fault_discrimination import OUT,SCOPE,rows,load,write

def main():
    normal=json.loads((OUT/'baseline_frozen.json').read_text(encoding='utf-8')); profile=json.loads((OUT/'frozen.json').read_text(encoding='utf-8'))
    gate=ConditionedDiagnostic(normal); model=FaultDiscriminator(profile); checked=[]; source={r['filename']:r for r in rows()}
    for name in ['H_H_16_6204_1000.mat','L_H_16_6204_1000.mat','U3_H_16_6204_1000.mat']:
        row=source[name]; a=load(row)[:32000]
        analyzer=create_analyzer(normal,profile,sample_rate_hz=16000,rpm=1000)
        result=analyze_block(analyzer,a,sample_rate_hz=16000,rpm=1000,asset_id=SCOPE['asset_id'],condition_id=SCOPE['condition_id'])
        expected_gate=gate.analyze(a,16000,1000,scope=SCOPE,channel_names=['radial_vibration'])
        assert result.payload['conditioned']==expected_gate
        if expected_gate.get('anomaly') is True:
            assert result.payload['fault_type']==model.analyze(a,16000,1000,scope=SCOPE)
        else: assert result.payload['fault_type']['reason']=='confirmed_anomaly_gate_required'
        checked.append(dict(recording=name,gate=expected_gate['status'],type_status=result.payload['fault_type']['status'],label=result.payload['fault_type']['label']))
    write(OUT/'api_integration.json',dict(status='pass',actual_source_cases=checked,core_and_direct_agree=True,new_final_files_reopened=0,operational_use=False))
    print('PASS actual source -> normal gate -> morphology stage/direct API parity',checked)

if __name__=='__main__': main()
