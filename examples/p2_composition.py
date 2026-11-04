"""Original synthetic example: protected consumers, PSD history and reviewed rules."""
import hashlib
import numpy as np
from rotorvibe import AnalysisConfig,SignalBlock,VibrationAnalyzer,SpectrogramAccumulator,SpectrogramStage
from vibration.iso import MachineContext,Rule,RuleDocument,MemoryRuleProvider,IsoStage

fs=12000
context=MachineContext('demo-motor','motor',operating_rpm=1200,operating_state='steady',
                       condition_id='demo-run',location='DE')
# Invented demonstration limits: these are not taken from any standard.
source=b'Original example: compare velocity to illustrative 1, 2, 3 mm/s limits.'
rule=Rule('example-only','velocity-demo','velocity','rms',('housing',),(1.,2.,3.),
          (10.,1000.),1,'original illustrative agreement')
document=RuleDocument(rule,'example-1','urn:example:authored-limits',hashlib.sha256(source).hexdigest(),
    'example-reviewer','2026-11-04',{'asset_id':'demo-motor','machine':'motor','condition_id':'demo-run',
                                  'location':'DE','operating_state':'steady','operating_rpm':1200})
provider=MemoryRuleProvider([document])
history=SpectrogramAccumulator(hop_seconds=.25,max_frames=8,max_age_seconds=5)
received=[]

def local_consumer(result):
    # This local edit is intentionally isolated from the next sink and caller.
    result.payload['metrics']['rms']=-999

analyzer=VibrationAnalyzer(AnalysisConfig(unit='m/s^2',rpm=1200),stages={
    'history':SpectrogramStage(history),
    'user_rule':IsoStage(rule.standard,context,rule_provider=provider,point_id='DE',
                        calibrated=True,acquisition_verified=True)},sinks=(local_consumer,received.append))
# Qualification flags are declarations for this synthetic example, not certificates.
time=np.arange(fs*2)/fs
results=analyzer.push(SignalBlock(np.sin(2*np.pi*100*time),fs,unit='m/s^2',rpm=1200,channels=('radial',),
    metadata={'asset_id':'demo-motor','condition_id':'demo-run','location':'DE','operating_state':'steady'}))
assert len(results)==5 and len(history.snapshot()['rows'])==5
assert all(r.metrics['rms']>0 and r.payload['user_rule']['status']=='evaluated' for r in results)
assert received[-1] is not results[-1]
print({'windows':len(results),'history_frames':len(history.snapshot()['rows']),
       'consumer_isolation':True,'rule_zone':results[-1].payload['user_rule']['zone']})
