"""Real optional process-monitoring-toolkit 0.1.0 bridge; synthetic data only."""
import numpy as np
from process_monitoring import SignalBatch,Monitor,create_detector
from process_monitoring.features import WindowFeatures
from rotorvibe import AnalysisConfig,VibrationAnalyzer,from_process_batch,to_process_batch,process_adapter_info

assert process_adapter_info()['compatible']
fs=12000; time=np.arange(fs*4)/fs
raw=SignalBatch(time,np.sin(2*np.pi*100*time)[:,None],('radial',),('m/s^2',),
    origin='original-synthetic-example',metadata={'clock_id':'elapsed','vibration_source':{'asset_id':'demo-motor'}})
block=from_process_batch(raw,sample_rate_hz=fs,clock_id='elapsed',rpm=1200)
results=VibrationAnalyzer(AnalysisConfig(unit='m/s^2',rpm=1200)).push(block)
features=to_process_batch(results)
monitor=Monitor(create_detector('isolation_forest',n_estimators=20,random_state=7),
                WindowFeatures(window=1,statistics=('mean',)))
# Wiring demonstration only: these reused synthetic rows are not an independent
# fit/calibration/test experiment or a normal false-positive-rate estimate.
monitor.fit(features); monitor.calibrate(features,false_alarm_fraction=.1)
detection=monitor.score(features)
assert detection.valid.any()
assert features.metadata['clock_id']=='elapsed'
assert features.metadata['vibration_source']['asset_id']=='demo-motor'
print({'source_samples':len(raw.time_s),'feature_windows':len(features.time_s),
       'process_usable_rows':int(detection.valid.sum()),'independent_validation':False})
