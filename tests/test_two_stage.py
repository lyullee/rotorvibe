"""Physical rotor invariants, normal gate, abstention, domain and leakage contracts."""
import copy,json,unittest
import numpy as np
from vibration import AnalysisConfig,SignalBlock,VibrationAnalyzer,extract_rotor_features,fit_two_stage,TwoStageDiagnostic,TwoStageStage
from vibration.rotor_features import RotorFeatures,feature_indices
from vibration.models import ModelRegistry
from vibration.stages import ClassifierStage

SCOPE={'asset_id':'bench','condition_id':'steady','unit':'unknown','channel_names':['radial'],
       'sample_rate_hz':12000,'window_samples':12000,'rpm_range':[1100,1300]}


def simple_profile():
    return fit_two_stage([[-.1,0],[.1,0],[0,-.1],[0,.1]],[1,1,2,2],
        [[-.05,0],[.1,0],[0,-.15],[0,.2]],[3,3,3,3],
        [[3,0],[3.1,.1],[0,3],[.1,3.1]],['unbalance']*2+['misalignment']*2,[4,4,5,5],
        feature_names=['ch1_log_rms','ch1_log_order_power_1X'],scope=SCOPE,mode='combined')


def point(a): return RotorFeatures(('ch1_log_rms','ch1_log_order_power_1X'),np.asarray(a),12000,1200,('radial',),12000)


class TwoStageChecks(unittest.TestCase):
    def test_existing_feature_only_registry_remains_composable(self):
        from types import SimpleNamespace
        registry=SimpleNamespace(classify=lambda vector,config,source:{'status':'custom','features':len(vector)})
        x=np.sin(2*np.pi*20*np.arange(12000)/12000)
        result=VibrationAnalyzer(stages={'classification':ClassifierStage(registry)}).analyze(SignalBlock(x,12000))
        self.assertEqual(result.payload['classification']['status'],'custom')

    def test_normal_is_not_sent_to_fault_classifier(self):
        model=TwoStageDiagnostic(simple_profile()); model.fault.predict=lambda _:self.fail('Normal reached fault stage')
        self.assertEqual(model.predict(point([0,0]),scope=SCOPE)['status'],'normal')

    def test_borderline_is_explicit_hold(self):
        p=simple_profile(); model=TwoStageDiagnostic(p)
        target=(p['normal_accept_limit']+p['anomaly_limit'])/2
        vector=np.asarray(p['normal_center'])+np.asarray(p['normal_scale'])*target
        self.assertEqual(model.predict(point(vector),scope=SCOPE)['reason'],'normal_gate_borderline')

    def test_fault_and_ambiguous_fault_are_distinct(self):
        model=TwoStageDiagnostic(simple_profile())
        a=model.predict(point([3,0]),scope=SCOPE); self.assertEqual(a['status'],'fault_candidate'); self.assertEqual(a['label'],'unbalance')
        b=model.predict(point([3,3]),scope=SCOPE); self.assertEqual(b['status'],'anomaly_unknown'); self.assertIsNone(b['label']); self.assertTrue(b['anomaly'])

    def test_asset_condition_unit_layout_speed_are_scoped(self):
        model=TwoStageDiagnostic(simple_profile())
        for key in ('asset_id','condition_id','unit'):
            scope={**SCOPE,key:'different'}
            self.assertEqual(model.predict(point([0,0]),scope=scope)['status'],'hold')
        for fs,rpm,channels in ((6000,1200,('radial',)),(12000,1800,('radial',)),(12000,1200,('other',))):
            f=RotorFeatures(point([0,0]).names,np.zeros(2),fs,rpm,channels,12000)
            self.assertEqual(model.predict(f,scope=SCOPE)['status'],'hold')
        f=RotorFeatures(point([0,0]).names,np.zeros(2),12000,1200,('radial',),6000)
        self.assertEqual(model.predict(f,scope=SCOPE)['status'],'hold')
        p=simple_profile(); p['scope']['calibration_id']='calibration-A'; model=TwoStageDiagnostic(p)
        self.assertEqual(model.predict(point([0,0]),scope=SCOPE)['status'],'hold')
        self.assertEqual(model.predict(point([0,0]),scope={**SCOPE,'calibration_id':'calibration-A'})['status'],'normal')

    def test_separate_normal_calibration_and_fault_groups_required(self):
        args=([[0,0],[.1,.1]],[1,1],[[0,0]],[1],[[2,0],[0,2]],['a','b'],[2,3])
        with self.assertRaises(ValueError): fit_two_stage(*args,feature_names=point([0,0]).names,scope=SCOPE)

    def test_nan_profiles_and_features_rejected(self):
        for key in ('anomaly_limit','normal_accept_limit','min_fault_margin'):
            p=simple_profile(); p[key]=float('nan')
            with self.assertRaises(ValueError): TwoStageDiagnostic(p)
        with self.assertRaises(ValueError): TwoStageDiagnostic(simple_profile()).predict(point([np.nan,0]),scope=SCOPE)

    def test_json_roundtrip_and_ablation_indices(self):
        p=simple_profile(); a=TwoStageDiagnostic(p).predict(point([3,0]),scope=SCOPE)
        self.assertEqual(a,TwoStageDiagnostic(json.loads(json.dumps(p))).predict(point([3,0]),scope=SCOPE))
        self.assertEqual(feature_indices(p['feature_names'],'legacy'),[0]); self.assertEqual(feature_indices(p['feature_names'],'relative'),[1])
        names,delta=TwoStageDiagnostic(p).relative_features(point([0,0]),scope=SCOPE)
        self.assertEqual(names,tuple(p['feature_names'])); self.assertFalse(delta.flags.writeable)
        with self.assertRaises(ValueError): TwoStageDiagnostic(p).relative_features(point([0,0]),scope={**SCOPE,'asset_id':'different'})

    def test_order_power_ratio_matches_analytic_signal(self):
        fs=12000; t=np.arange(fs)/fs; x=np.sin(2*np.pi*20*t)+.5*np.sin(2*np.pi*40*t)
        f=extract_rotor_features(x,fs,1200,channel_names=['radial'])
        index=f.names.index('ch1_log_order_ratio_2X_to_1X')
        self.assertAlmostEqual(f.values[index],np.log(.25),places=10)

    def test_channel_and_common_gain_invariants(self):
        fs=12000; t=np.arange(fs)/fs; x=np.sin(2*np.pi*20*t)+.5*np.sin(2*np.pi*40*t); a=np.column_stack([x,2*x])
        first=extract_rotor_features(a,fs,1200); second=extract_rotor_features(a*10,fs,1200)
        i=first.names.index('ch1_to_ch2_log_rms_ratio'); self.assertAlmostEqual(first.values[i],-np.log(2),places=12)
        selected=feature_indices(first.names,'relative'); np.testing.assert_allclose(first.values[selected],second.values[selected],atol=1e-10)

    def test_same_orders_at_two_speeds_have_same_order_features(self):
        fs=12000; t=np.arange(fs)/fs
        a=extract_rotor_features(np.sin(2*np.pi*20*t)+.5*np.sin(2*np.pi*40*t),fs,1200)
        b=extract_rotor_features(np.sin(2*np.pi*30*t)+.5*np.sin(2*np.pi*60*t),fs,1800)
        indices=[i for i,n in enumerate(a.names) if '_order_' in n]
        np.testing.assert_allclose(a.values[indices],b.values[indices],atol=1e-9)

    def test_missing_rpm_short_window_and_flat_channels_rejected(self):
        model=TwoStageDiagnostic(simple_profile()); self.assertEqual(model.analyze(np.ones(300),12000,None,scope=SCOPE)['reason'],'rpm_required')
        for x,fs,rpm in ((np.zeros(12000),12000,1200),(np.arange(256),12000,60),(np.arange(12000),12000,100000)):
            with self.assertRaises(ValueError): extract_rotor_features(x,fs,rpm)

    def test_raw_window_hook_is_readonly_and_receives_calibrated_samples(self):
        class Stage:
            def __call__(self,result): raise AssertionError('raw hook required')
            def analyze_window(self,result,values):
                self_test.assertFalse(values.flags.writeable)
                np.testing.assert_allclose(values[:,0],expected)
                return {'received':True}
        self_test=self; t=np.arange(12000)/12000; expected=np.sin(2*np.pi*20*t)
        config=AnalysisConfig(input_representation='volts',sensitivity_mv_per_g=[100],unit='g')
        result=VibrationAnalyzer(config,stages={'raw':Stage()}).analyze(SignalBlock(.1*expected,12000,unit='V'))
        self.assertTrue(result.payload['raw']['received'])

    def test_real_feature_two_stage_pipeline_matches_direct_and_holds_invalid(self):
        fs=12000; t=np.arange(fs)/fs; x=np.sin(2*np.pi*20*t)+.2*np.sin(2*np.pi*40*t)
        f=extract_rotor_features(x,fs,1200,channel_names=['radial']); v=f.values; d=len(v)
        profile=fit_two_stage(np.vstack([v,v+.01]),[1,1],np.vstack([v-.02,v+.02]),[2,2],
            np.vstack([v+3,v-3]),['a','b'],[3,4],feature_names=f.names,scope=SCOPE,mode='combined')
        model=TwoStageDiagnostic(profile); config=AnalysisConfig(rpm=1200)
        analyzer=VibrationAnalyzer(config,stages={'diagnostic':TwoStageStage(model)})
        block=SignalBlock(x,fs,channels=('radial',),rpm=1200,metadata={'asset_id':'bench','condition_id':'steady'})
        result=analyzer.analyze(block)
        self.assertEqual(result.payload['diagnostic'],model.predict(f,scope=SCOPE))
        registry=ModelRegistry(None,None); registry.use_two_stage(profile)
        routed=VibrationAnalyzer(AnalysisConfig(rpm=900,model_enabled=True),stages={'classification':ClassifierStage(registry)})
        self.assertEqual(routed.analyze(block).payload['classification'],result.payload['diagnostic'])
        changing=SignalBlock(x,fs,channels=('radial',),rpm=np.linspace(1150,1250,fs),metadata=block.metadata)
        self.assertEqual(routed.analyze(changing).payload['classification']['reason'],'variable_speed_requires_angle_domain_features')
        invalid=SignalBlock(x,fs,channels=('radial',),valid=np.zeros(len(x),dtype=bool))
        self.assertEqual(analyzer.analyze(invalid).payload['diagnostic']['status'],'quality_hold')

if __name__=='__main__': unittest.main()
