"""Portable regressions: no local PDFs, downloaded datasets or trained models."""
import io,json,math,tempfile,unittest
from dataclasses import replace
from pathlib import Path
import numpy as np
from vibration import AnalysisConfig,SignalBlock,VibrationAnalyzer,BaselineStage
from vibration.iso import MachineContext,Measurement,Rule,evaluate,energy_equivalent_average

def context(**options):
    return replace(MachineContext('asset','motor',power_kw=75,rated_rpm=1800,operating_rpm=1800,
        support='rigid',operating_state='steady',location='bearing_housing',condition_id='normal'),**options)

def observed(**options):
    return replace(Measurement(1.,'velocity','mm/s','rms','housing',(10.,1000.),10.,'radial','DE',
        calibrated=True,acquisition_verified=True),**options)

class InputContracts(unittest.TestCase):
    def test_invalid_observation_count_rejected(self):
        for value in (True,0,-1,1.5,float('nan'),float('inf'),'10'):
            with self.subTest(value=value),self.assertRaises(ValueError): observed(observations=value).validate()

    def test_invalid_revolution_count_rejected(self):
        for value in (True,0,-1,float('nan'),float('inf'),'10'):
            with self.subTest(value=value),self.assertRaises(ValueError): observed(revolutions_per_observation=value).validate()

    def test_invalid_filter_metadata_rejected(self):
        for name in ('order','filter_bandwidth_hz'):
            for value in (True,0,-1,float('nan'),float('inf')):
                with self.subTest(name=name,value=value),self.assertRaises(ValueError): observed(**{name:value}).validate()

    def test_invalid_custom_band_rejected(self):
        c=context(); m=observed()
        rule=Rule('20816-1:2016','agreement','velocity','rms',('housing',),(1.,2.,3.),(float('nan'),float('nan')),0,'agreement')
        with self.assertRaises(ValueError): evaluate(rule.standard,c,m,custom_rule=rule)

    def test_invalid_custom_duration_rejected(self):
        rule=Rule('20816-1:2016','agreement','velocity','rms',('housing',),(1.,2.,3.),(10.,1000.),0,'agreement',minimum_duration_s=float('nan'))
        with self.assertRaises(ValueError): evaluate(rule.standard,context(),observed(),custom_rule=rule)

    def test_unknown_purpose_rejected(self):
        with self.assertRaises(ValueError): context(purpose='typo').validate()

    def test_boolean_validity_mask_not_string_or_nan(self):
        a=np.ones(300)
        for value in (np.full(300,'false'),np.full(300,float('nan'))):
            with self.subTest(dtype=str(value.dtype)),self.assertRaises(ValueError): SignalBlock(a,12000,valid=value)

    def test_zero_duration_clock_precision_is_rejected(self):
        with self.assertRaises(ValueError): SignalBlock(np.ones(256),12000,start_time_s=1e308)

class StreamContracts(unittest.TestCase):
    def setUp(self):
        self.config=AnalysisConfig(unit='m/s^2',window='boxcar')

    def test_random_packet_boundaries_equal_direct_analysis(self):
        rng=np.random.default_rng(44); fs=12000; t=np.arange(48000)/fs
        a=np.sin(2*np.pi*97*t)+.3*np.cos(2*np.pi*311*t)
        stream=VibrationAnalyzer(self.config); offset=0; rows=[]; seq=0
        while offset<len(a):
            size=int(rng.integers(1,9000)); block=a[offset:offset+size]
            rows+=stream.push(SignalBlock(block,fs,unit='m/s^2',start_time_s=offset/fs,sequence=seq))
            offset+=len(block); seq+=1
        self.assertEqual(len(rows),13)
        for i,row in enumerate(rows):
            expected=np.sqrt(np.mean((a[i*3000:i*3000+12000]-a[i*3000:i*3000+12000].mean())**2))
            self.assertAlmostEqual(row.metrics['rms'],expected,places=12)

    def test_metadata_change_cannot_mix_assets_inside_window(self):
        analyzer=VibrationAnalyzer(self.config)
        a=np.sin(2*np.pi*100*np.arange(6000)/12000)
        analyzer.push(SignalBlock(a,12000,unit='m/s^2',metadata={'asset_id':'A'}))
        rows=analyzer.push(SignalBlock(a,12000,unit='m/s^2',start_time_s=.5,metadata={'asset_id':'B'}))
        self.assertEqual(rows,[])

    def test_stage_cannot_overwrite_computed_metrics(self):
        with self.assertRaises(ValueError): VibrationAnalyzer(self.config,stages={'metrics':lambda r:{'rms':0}})

    def test_stage_error_is_propagated(self):
        def fail(result): raise RuntimeError('injected downstream failure')
        analyzer=VibrationAnalyzer(self.config,stages={'custom':fail})
        a=np.sin(2*np.pi*100*np.arange(12000)/12000)
        with self.assertRaisesRegex(RuntimeError,'injected downstream'):
            analyzer.analyze(SignalBlock(a,12000,unit='m/s^2'))

    def test_core_does_not_mutate_caller_waveform(self):
        a=np.sin(2*np.pi*100*np.arange(12000)/12000); copy=a.copy()
        VibrationAnalyzer(self.config).analyze(SignalBlock(a,12000,unit='m/s^2'))
        np.testing.assert_array_equal(a,copy)

    def test_finite_json_and_array_contract(self):
        a=np.sin(2*np.pi*100*np.arange(12000)/12000)
        r=VibrationAnalyzer(self.config).analyze(SignalBlock(a,12000,unit='m/s^2'))
        self.assertIsInstance(r.payload['spectrum']['x'],np.ndarray)
        json.dumps(r.to_dict(),allow_nan=False)

    def test_baseline_cannot_cross_asset_identity(self):
        baseline=BaselineStage(self.config); baseline.begin('normal',20)
        analyzer=VibrationAnalyzer(self.config,stages={'baseline':baseline})
        a=np.sin(2*np.pi*100*np.arange(12000)/12000)
        for _ in range(20): analyzer.analyze(SignalBlock(a,12000,unit='m/s^2',metadata={'asset_id':'A'}))
        profile=baseline.export_profile(); self.assertEqual(profile['source_scope'],{'asset_id':'A'})
        r=analyzer.analyze(SignalBlock(a,12000,unit='m/s^2',metadata={'asset_id':'B'}))
        self.assertEqual(r.payload['baseline']['status'],'incompatible')
        self.assertIsNone(r.payload['baseline']['score'])


class OptionalModelContracts(unittest.TestCase):
    def test_training_cancels_before_storage_close(self):
        import time
        from types import SimpleNamespace
        from vibration.models import ModelRegistry
        rows=[{'id':str(i),'dataset':'Brito'} for i in range(50)]
        records={str(i):(None,None,{'suggested_split':'train','fault':'normal','trial_id':1}) for i in range(50)}
        def load(id):
            time.sleep(.005)
            return np.sin(2*np.pi*100*np.arange(25000)/25000)[:,None].repeat(4,axis=1),{}
        saved=[]
        registry=ModelRegistry(SimpleNamespace(save=lambda *args:saved.append(args)),SimpleNamespace(rows=rows,records=records,load=load))
        registry.train('cancel-test'); registry.close()
        self.assertFalse(registry.training_thread.is_alive()); self.assertEqual(saved,[])
        self.assertEqual(registry.job['status'],'cancelled')
        with self.assertRaises(RuntimeError): registry.train('after-close')

    def test_nonfinite_classification_features_rejected(self):
        from vibration.models import ModelRegistry
        registry=ModelRegistry(None,None)
        registry.active={'feature_schema':'vibration.features.v2','center':[0]*28}
        config=AnalysisConfig(sample_rate_hz=25000,channels=4,model_enabled=True)
        with self.assertRaises(ValueError): registry.classify(np.full(28,np.nan),config,{'dataset':'Brito'})

if __name__=='__main__': unittest.main()
