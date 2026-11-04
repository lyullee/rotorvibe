"""Analytic conditioning/resampling, no extrapolation, abstention and composition."""
import json,unittest,copy
import numpy as np
from vibration import fit_conditioned,ConditionedDiagnostic,ConditionedStage,VibrationAnalyzer,AnalysisConfig,SignalBlock
from vibration.rotor_features import RotorFeatures,rotor_features
from vibration.conditioned import reference_at,canonical_values
from vibration.models import ModelRegistry
from vibration.stages import ClassifierStage

SCOPE={'asset_id':'unit','condition_id':'steady','unit':'g','channel_names':['radial'],'sample_rate_hz':4000,'window_samples':8000,'rpm_range':[590,1800]}
NAMES=('ch1_log_rms','ch1_log_order_power_1X')


def profile():
    return fit_conditioned([[0,0],[.1,0],[2,2],[2.1,2]],[600,600,1200,1200],[1,1,2,2],
        [[.02,.02],[.03,.04],[2.02,2.02],[2.03,2.04]],[600,600,1200,1200],[3,3,4,4],
        [[3,0],[3.1,0],[0,3],[0,3.1]],[600]*4,['a','a','b','b'],[5,6,7,8],feature_names=NAMES,scope=SCOPE,mode='levels_orders')


def f(v,rpm=600): return RotorFeatures(NAMES,np.asarray(v),4000,rpm,('radial',),8000)


class ConditionedChecks(unittest.TestCase):
    def test_exact_speed_normal_baselines_differ(self):
        model=ConditionedDiagnostic(profile())
        self.assertEqual(model.predict(f([.05,0]),scope=SCOPE)['status'],'normal')
        self.assertEqual(model.predict(f([2.05,2],1200),scope=SCOPE)['status'],'normal')

    def test_unseen_speed_never_extrapolates_even_with_broad_scope(self):
        p=profile(); model=ConditionedDiagnostic(p)
        self.assertEqual(model.predict(f([0,0],1600),scope=SCOPE)['reason'],'normal_reference_speed_unavailable')
        p['interpolate']=True; self.assertEqual(ConditionedDiagnostic(p).predict(f([0,0],1600),scope=SCOPE)['status'],'hold')

    def test_interpolation_is_opt_in_and_bounded(self):
        p=profile(); model=ConditionedDiagnostic(p)
        self.assertEqual(model.predict(f([1,1],900),scope=SCOPE)['status'],'hold')
        ref=reference_at(p['references'],np.sqrt(600*1200),interpolate=True,max_gap=600,uncertainty=0)
        np.testing.assert_allclose(ref[0],[1.05,1.]); self.assertEqual(ref[2]['mode'],'interpolated_qualification')
        self.assertIsNone(reference_at(p['references'],900,interpolate=True,max_gap=200,uncertainty=0))

    def test_confounded_recording_roles_rejected(self):
        with self.assertRaises(ValueError):
            fit_conditioned([[0,0]],[600],[1],[[0,0]],[600],[1],[[3,0],[0,3]],[600,600],['a','b'],[2,3],feature_names=NAMES,scope=SCOPE)

    def test_zero_margin_does_not_force_equal_fault_matches(self):
        p=profile(); p['min_margin']=0; p['fault_prototypes']=[[0,0],[0,0]]; p['prototype_labels']=['a','b']
        model=ConditionedDiagnostic(p); result=model.predict(f([10,10]),scope=SCOPE)
        self.assertEqual(result['status'],'anomaly_unknown'); self.assertIsNone(result['label'])

    def test_scope_and_window_mismatch_hold(self):
        model=ConditionedDiagnostic(profile())
        self.assertEqual(model.predict(f([0,0]),scope={**SCOPE,'asset_id':'other'})['status'],'hold')
        wrong=RotorFeatures(NAMES,np.zeros(2),4000,600,('radial',),4000)
        self.assertEqual(model.predict(wrong,scope=SCOPE)['status'],'hold')

    def test_nonfinite_profiles_and_features_rejected(self):
        p=profile(); p['references'][0]['scale'][0]=float('nan')
        with self.assertRaises(ValueError): ConditionedDiagnostic(p)
        with self.assertRaises(ValueError): ConditionedDiagnostic(profile()).predict(f([np.nan,0]),scope=SCOPE)
        p=profile(); p['interpolate']='false'
        with self.assertRaises(ValueError): ConditionedDiagnostic(p)

    def test_common_band_preserves_known_amplitude_and_frequency(self):
        fs=16000; t=np.arange(fs*2)/fs; a=1.2*np.sin(2*np.pi*20*t)
        out=canonical_values(a,fs,4000)[:,0]
        self.assertEqual(len(out),8000); self.assertAlmostEqual(np.sqrt(np.mean(out[100:-100]**2)),1.2/np.sqrt(2),delta=.002)
        self.assertEqual(np.argmax(np.abs(np.fft.rfft(out)))*4000/len(out),20)

    def test_antialias_filter_rejects_out_of_band_energy(self):
        fs=16000; t=np.arange(fs*2)/fs; a=np.sin(2*np.pi*5300*t)
        out=canonical_values(a,fs,4000)[:,0]
        self.assertLess(np.sqrt(np.mean(out[100:-100]**2)),.001)

    def test_json_roundtrip(self):
        p=profile(); first=ConditionedDiagnostic(p).predict(f([3,0]),scope=SCOPE)
        self.assertEqual(first,ConditionedDiagnostic(json.loads(json.dumps(p))).predict(f([3,0]),scope=SCOPE))

    def test_canonical_raw_pipeline_registry_and_direct_agree(self):
        fs=16000; t=np.arange(fs*2)/fs; a=.2*np.sin(2*np.pi*20*t)+.1*np.sin(2*np.pi*40*t)
        features=rotor_features(canonical_values(a,fs,4000),4000,1200,channel_names=['radial']); v=features.values
        scope={**SCOPE,'rpm_range':[1188,1212]}
        p=fit_conditioned(np.vstack([v,v+.01]),[1200,1200],[1,1],np.vstack([v-.02,v+.02]),[1200,1200],[2,2],
            np.vstack([v+3,v+3.1,v-3,v-3.1]),[1200]*4,['a','a','b','b'],[3,4,5,6],feature_names=features.names,scope=scope)
        p.update(canonical_sample_rate_hz=4000,permitted_input_rates=[8000,16000])
        model=ConditionedDiagnostic(p); registry=ModelRegistry(None,None); registry.use_conditioned(p)
        config=AnalysisConfig(sample_rate_hz=fs,window_seconds=2,rpm=1200,unit='g',model_enabled=True)
        analyzer=VibrationAnalyzer(config,stages={'diagnostic':ConditionedStage(model),'classification':ClassifierStage(registry)})
        result=analyzer.analyze(SignalBlock(a,fs,unit='g',channels=('radial',),rpm=1200,metadata={'asset_id':'unit','condition_id':'steady'}))
        direct=model.analyze(a,fs,1200,scope=scope,channel_names=['radial'])
        self.assertEqual(result.payload['diagnostic'],direct); self.assertEqual(result.payload['classification'],direct)
        self.assertEqual(model.analyze(a,fs,None,scope=scope)['reason'],'rpm_required')

if __name__=='__main__': unittest.main()
