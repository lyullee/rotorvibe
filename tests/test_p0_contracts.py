"""Reproduced P0 failures and actual stage-to-alarm regressions, no raw datasets."""
import copy,json,unittest,warnings
from dataclasses import replace
import numpy as np
from rotorvibe import (AnalysisConfig,SignalBlock,VibrationAnalyzer,BaselineStage,AlarmStage,
                       DecisionStage,normalize_decision)
from vibration.fault_discrimination import FaultDiscriminator
from test_fault_discrimination import fixture,SCOPE
from test_conditioned import profile as conditioned_profile,f,SCOPE as CONDITIONED_SCOPE
from test_two_stage import simple_profile,point,SCOPE as TWO_STAGE_SCOPE
from vibration import ConditionedDiagnostic,TwoStageDiagnostic
from vibration import ConditionedStage,fit_conditioned
from vibration.conditioned import canonical_values
from vibration.rotor_features import rotor_features
from vibration.fault_discrimination import FaultDiscriminationStage


class ProfileLoadChecks(unittest.TestCase):
    def test_missing_blank_scope_and_bad_unit_refused_at_load(self):
        bad=[{},None,{'asset_id':' ','condition_id':'steady','unit':'g'},
             {**SCOPE,'unit':'V'},{**SCOPE,'sensor_id':float('nan')}]
        for scope in bad:
            p=fixture(); p['scope']=scope
            with self.subTest(scope=scope),self.assertRaises(ValueError): FaultDiscriminator(p)
        p=fixture(); del p['scope']
        with self.assertRaisesRegex(ValueError,'Missing'): FaultDiscriminator(p)

    def test_feature_mode_names_and_recording_contracts_checked_on_load(self):
        for field,value in [('names',['same','same']),('names',['order_1','']),
                            ('mode','typo'),('indices',[1,0]),('groups',[1]),
                            ('groups',[1]*6),('operational_use',True)]:
            p=fixture(); p[field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError): FaultDiscriminator(p)

    def test_serialized_existing_fit_loads_and_predicts_identically(self):
        p=fixture(); restored=FaultDiscriminator(json.loads(json.dumps(p,allow_nan=False)))
        before=FaultDiscriminator(p)
        for vector in ([0,0],[3,0],[0,3],[100,100],[1.5,1.5]):
            self.assertEqual(before.predict(vector,1200,scope=SCOPE),restored.predict(vector,1200,scope=SCOPE))

    def test_missing_inference_scope_is_hold_not_wildcard(self):
        model=FaultDiscriminator(fixture())
        for scope in ({},None,{'asset_id':'rig'}):
            result=model.predict([0,0],1200,scope=scope)
            self.assertEqual(result['status'],'hold'); self.assertIsNone(result['label'])
            json.dumps(result,allow_nan=False)


class FiniteOutputChecks(unittest.TestCase):
    def test_huge_finite_vectors_rejected_without_runtime_warnings(self):
        model=FaultDiscriminator(fixture())
        with warnings.catch_warnings():
            warnings.simplefilter('error',RuntimeWarning)
            for value in (1e308,-1e308):
                with self.subTest(value=value),self.assertRaises(ValueError):
                    model.predict([value,0],1200,scope=SCOPE)

    def test_small_scale_overflow_is_explicit_error(self):
        p=fixture(); p['scale']=[1e-300,1e-300]
        with warnings.catch_warnings():
            warnings.simplefilter('error',RuntimeWarning)
            with self.assertRaisesRegex(ValueError,'numeric range'):
                FaultDiscriminator(p).predict([100,100],1200,scope=SCOPE)

    def test_small_boundary_and_supported_extreme_results_are_finite(self):
        model=FaultDiscriminator(fixture())
        for vector in ([0,0],[1e-308,-1e-308],[1e100,-1e100]):
            for rpm in (590,1200,1620):
                with self.subTest(vector=vector,rpm=rpm):
                    json.dumps(model.predict(vector,rpm,scope=SCOPE),allow_nan=False)

    def test_profile_extremes_rejected_before_prediction(self):
        for field in ('center','scale','prototypes','limits'):
            p=fixture(); array=np.asarray(p[field]); array.flat[0]=1e308; p[field]=array.tolist()
            with self.subTest(field=field),self.assertRaises(ValueError): FaultDiscriminator(p)


class DecisionChecks(unittest.TestCase):
    def test_real_conditioned_and_two_stage_decisions_keep_score_definition(self):
        for raw in (ConditionedDiagnostic(conditioned_profile()).predict(f([2.05,2],1200),scope=CONDITIONED_SCOPE),
                    TwoStageDiagnostic(simple_profile()).predict(point([0,0]),scope=TWO_STAGE_SCOPE)):
            result=normalize_decision(raw,source_stage='diagnostic')
            self.assertEqual(result['status'],'normal'); self.assertFalse(result['anomaly'])
            self.assertEqual(result['score'],raw['normal_score']); self.assertEqual(result['score_name'],'normal_score')
            self.assertTrue(result['alarm_eligible']); json.dumps(result,allow_nan=False)

    def test_hold_never_becomes_alarm_eligible_even_with_zero_or_high_score(self):
        for status in ('hold','incompatible','missing','collecting','outside_condition','quality_hold'):
            for score in (0,100):
                raw=normalize_decision({'status':status,'score':score},source_stage='gate')
                self.assertFalse(raw['alarm_eligible']); self.assertIsNone(raw['anomaly'])
                self.assertIn(raw['status'],('hold','invalid'))

    def test_head_similarities_are_not_invented_as_alarm_scores(self):
        raw=FaultDiscriminator(fixture()).predict([0,0],1200,scope=SCOPE)
        result=normalize_decision(raw,source_stage='fault')
        self.assertEqual(result['status'],'fault_candidate'); self.assertIsNone(result['score'])
        self.assertFalse(result['alarm_eligible'])

    def test_conflicting_nonfinite_or_boolean_scores_rejected(self):
        for raw in ({'score':float('nan')},{'score':float('inf')},{'score':True},
                    {'score':-1},{'score':1,'normal_score':2},{'status':'normal','anomaly':True}):
            with self.subTest(raw=raw),self.assertRaises(ValueError): normalize_decision(raw,source_stage='test')

    def test_normalization_roundtrip_retains_score_kind(self):
        first=normalize_decision({'status':'normal','normal_score':.2},source_stage='gate')
        second=normalize_decision(json.loads(json.dumps(first)),source_stage='adapter')
        self.assertEqual(second['score_name'],'normal_score'); self.assertEqual(second['score'],.2)

    def test_actual_baseline_adapter_alarm_sink_chain_and_scope_hold(self):
        fs=12000; values=.2*np.sin(2*np.pi*20*np.arange(fs)/fs)
        config=AnalysisConfig(unit='g',rpm=1200,hop_seconds=1)
        baseline=BaselineStage(config); baseline.begin(windows=20); received=[]
        analyzer=VibrationAnalyzer(config,stages={'baseline':baseline,'decision':DecisionStage('baseline'),
            'alarm':AlarmStage(score_stage='decision',expected_score_name='score',persistence_seconds=0,release_seconds=0)},sinks=(received.append,))
        def block(index,asset='rig'):
            return SignalBlock(values,fs,unit='g',start_time_s=index,rpm=1200,
                               metadata={'asset_id':asset,'condition_id':'steady'})
        for i in range(20): analyzer.analyze(block(i))
        result=analyzer.analyze(block(20))
        self.assertEqual(result.payload['decision']['status'],'scored')
        self.assertEqual(result.payload['alarm']['level'],'normal'); self.assertIs(received[-1],result)
        held=analyzer.analyze(block(21,'other'))
        self.assertEqual(held.payload['decision']['status'],'hold')
        self.assertEqual(held.payload['alarm']['level'],'unavailable')
        self.assertEqual(held.payload['alarm']['retained_level'],'normal')
        json.dumps(held.to_dict(),allow_nan=False)

    def test_raw_conditioned_gate_adapter_alarm_and_fault_head_chain(self):
        fs=12000; t=np.arange(fs*2)/fs; wave=.2*np.sin(2*np.pi*20*t)+.1*np.sin(2*np.pi*40*t)
        features=rotor_features(canonical_values(wave,fs,4000),4000,1200,channel_names=('radial',))
        v=features.values; scope={**CONDITIONED_SCOPE,'rpm_range':[1188,1212]}
        p=fit_conditioned(np.vstack([v,v+.01]),[1200]*2,[1,1],
            np.vstack([v-.02,v+.02]),[1200]*2,[2,2],
            np.vstack([v+3,v+3.1,v-3,v-3.1]),[1200]*4,['a','a','b','b'],[3,4,5,6],
            feature_names=features.names,scope=scope)
        p.update(canonical_sample_rate_hz=4000,permitted_input_rates=[12000])
        analyzer=VibrationAnalyzer(AnalysisConfig(unit='g',rpm=1200,window_seconds=2),stages={
            'conditioned':ConditionedStage(ConditionedDiagnostic(p)),
            'decision':DecisionStage('conditioned'),
            'alarm':AlarmStage(score_stage='decision',expected_score_name='normal_score',
                                persistence_seconds=0,release_seconds=0),
            'fault':FaultDiscriminationStage(FaultDiscriminator(fixture()))})
        block=SignalBlock(wave,fs,unit='g',rpm=1200,channels=('radial',),metadata=scope)
        result=analyzer.analyze(block)
        self.assertEqual(result.payload['decision']['status'],'normal')
        self.assertEqual(result.payload['alarm']['level'],'normal')
        self.assertEqual(result.payload['fault']['reason'],'confirmed_anomaly_gate_required')
        held=analyzer.analyze(replace(block,start_time_s=2,metadata={**scope,'asset_id':'different'}))
        self.assertEqual(held.payload['decision']['status'],'hold')
        self.assertEqual(held.payload['alarm']['level'],'unavailable')
        self.assertEqual(held.payload['fault']['status'],'hold')

    def test_alarm_retains_danger_on_held_numeric_score_and_checks_score_kind(self):
        fs=12000; values=np.sin(2*np.pi*20*np.arange(fs)/fs)
        alarm=AlarmStage(score_stage='decision',expected_score_name='normal_score',persistence_seconds=0,release_seconds=0)
        producer={'status':'fault_candidate','anomaly':True,'normal_score':10}
        analyzer=VibrationAnalyzer(AnalysisConfig(unit='g'),stages={
            'gate':lambda _:dict(producer),'decision':DecisionStage('gate'),'alarm':alarm})
        def run(i): return analyzer.analyze(SignalBlock(values,fs,unit='g',start_time_s=i))
        self.assertEqual(run(0).payload['alarm']['level'],'danger')
        producer.update(status='hold',anomaly=None,normal_score=0)
        held=run(1); self.assertEqual(held.payload['alarm']['level'],'unavailable')
        self.assertEqual(held.payload['alarm']['retained_level'],'danger')
        producer.clear(); producer.update(status='ready',score=0)
        self.assertEqual(run(2).payload['alarm']['level'],'unavailable')

    def test_missing_stage_and_invalid_window_are_explicit(self):
        a=np.sin(2*np.pi*20*np.arange(12000)/12000)
        analyzer=VibrationAnalyzer(stages={'decision':DecisionStage('absent')})
        self.assertEqual(analyzer.analyze(SignalBlock(a,12000)).payload['decision']['reason'],'source_stage_missing')
        result=analyzer.analyze(SignalBlock(np.zeros(12000),12000))
        self.assertEqual(result.payload['decision']['status'],'invalid')

    def test_existing_legacy_score_alarm_interface_still_works(self):
        a=np.sin(2*np.pi*20*np.arange(12000)/12000)
        analyzer=VibrationAnalyzer(stages={'baseline':lambda _:{'score':8},
                                         'alarm':AlarmStage(persistence_seconds=0)})
        self.assertEqual(analyzer.analyze(SignalBlock(a,12000)).payload['alarm']['level'],'danger')


if __name__=='__main__': unittest.main()
