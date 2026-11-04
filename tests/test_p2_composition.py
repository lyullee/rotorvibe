"""P2 contracts and analytic checks; optional bridge uses the real dependency."""
import copy,json,unittest
from dataclasses import replace
from unittest.mock import patch
from importlib.metadata import PackageNotFoundError
from types import SimpleNamespace
import numpy as np
from rotorvibe import (AnalysisConfig,SignalBlock,AnalysisResult,VibrationAnalyzer,
    ProfileRegistry,create_profile,validate_profile,profile_digest,
    SpectrogramAccumulator,SpectrogramStage,condition_evidence,process_adapter_info,
    from_process_batch,to_process_batch)
from vibration.iso import (MachineContext,Measurement,Rule,RuleDocument,MemoryRuleProvider,
                           evaluate_with_provider,IsoStage)
from vibration.experimental import LifeHistory,evaluate_life_predictions,ReferenceLifeEstimator
from vibration.models import LifeEstimator
from vibration.stages import LifeStage


def observed(start=0,*,stages=None,sinks=(),metadata=None):
    fs=12000; wave=.2*np.sin(2*np.pi*100*np.arange(fs)/fs)
    return VibrationAnalyzer(AnalysisConfig(unit='g',rpm=1200),stages=stages,sinks=sinks).analyze(
        SignalBlock(wave,fs,unit='g',start_time_s=start,rpm=1200,metadata=metadata or {'asset_id':'motor'}))


def envelope():
    return create_profile({'algorithm':'example','feature_schema':'features.example.v1','weights':[1.,2.]},
        profile_id='model-1',kind='fault_model',algorithm='example',feature_schema='features.example.v1',
        preprocessing={'window':'hann','unit':'g'},training_groups=['original-1','original-2'],
        calibration_history=[{'calibration_id':'cal-1','group_id':'original-3','reviewed_on':'2026-11-04','method':'record-max quantile'}],
        scope={'asset_id':'motor','rpm_range':[1100,1300]})


class ResultIsolation(unittest.TestCase):
    def test_detached_nested_arrays_metadata(self):
        result=observed(); snapshot=result.detached()
        snapshot.features[0]=100; snapshot.payload['metrics']['band_power'][0]['power']=123
        snapshot.metadata['source']['asset_id']='changed'
        self.assertNotEqual(result.features[0],100)
        self.assertNotEqual(result.metrics['band_power'][0]['power'],123)
        self.assertEqual(result.metadata['source']['asset_id'],'motor')

    def test_sink_mutation_cannot_reach_other_sink_or_return(self):
        received=[]
        def mutate(r):
            r.payload['metrics']['rms']=999; r.features[0]=999
            r.metadata['source']['asset_id']='changed'
        result=observed(sinks=(mutate,received.append))
        self.assertAlmostEqual(result.metrics['rms'],.2/np.sqrt(2))
        self.assertEqual(result.to_dict(),received[0].to_dict())
        received[0].payload['metrics']['rms']=500
        self.assertNotEqual(result.metrics['rms'],500)

    def test_stage_cannot_modify_inputs_to_later_stage(self):
        def bad(r): r.payload['metrics']['rms']=99; r.features[:]=0; return {'local':1}
        def next_stage(r): return {'rms':r.metrics['rms'],'feature':float(r.features[0])}
        r=observed(stages={'first':bad,'second':next_stage})
        self.assertAlmostEqual(r.payload['second']['rms'],.2/np.sqrt(2))
        self.assertNotEqual(r.payload['second']['feature'],0)

    def test_stage_output_aliases_detached(self):
        output={'values':np.array([1.,2.]),'nested':{'x':[3]}}
        r=observed(stages={'custom':lambda r:output})
        output['values'][0]=99; output['nested']['x'][0]=99
        self.assertEqual(r.payload['custom']['values'][0],1)
        self.assertEqual(r.payload['custom']['nested']['x'][0],3)

    def test_later_stage_cannot_change_earlier_output(self):
        def bad(r): r.payload['first']['nested']['x']=10; return {'ok':True}
        r=observed(stages={'first':lambda r:{'nested':{'x':1}},'bad':bad})
        self.assertEqual(r.payload['first']['nested']['x'],1)

    def test_raw_hook_write_flag_cannot_be_enabled(self):
        class Hook:
            def __call__(self,r): raise AssertionError('Wrong hook')
            def analyze_window(self,r,values):
                with self_test.assertRaises(ValueError): values.setflags(write=True)
                return {'rms':float(np.sqrt(np.mean(values**2)))}
        self_test=self
        r=observed(stages={'hook':Hook()})
        self.assertAlmostEqual(r.payload['hook']['rms'],r.metrics['rms'])

    def test_condition_evidence_is_detached(self):
        r=observed(); e=condition_evidence(r,asset_id='motor')
        e['metrics']['band_power'][0]['power']=999; e['diagnosis']['candidates'].append({'x':1})
        self.assertNotEqual(r.metrics['band_power'][0]['power'],999)
        self.assertNotIn({'x':1},r.payload['diagnosis']['candidates'])


class ProfileChecks(unittest.TestCase):
    def test_roundtrip_digest_and_registry(self):
        row=envelope(); registry=ProfileRegistry(); digest=registry.register(row)
        restored=registry.get('model-1',expected_contract=row['contract'],expected_scope=row['scope'])
        self.assertEqual(digest,row['envelope_sha256']); self.assertEqual(row,restored)
        self.assertEqual(validate_profile(json.loads(json.dumps(row))),row)

    def test_canonical_digest_order_and_arrays(self):
        self.assertEqual(profile_digest({'b':np.array([1,2]),'a':1}),profile_digest({'a':1,'b':[1,2]}))

    def test_tamper_each_component(self):
        for key in ('payload','preprocessing','scope','training_groups','calibration_history'):
            row=envelope()
            if isinstance(row[key],dict): row[key]['tampered']=1
            else: row[key].append('tampered')
            with self.subTest(key=key),self.assertRaises(ValueError): validate_profile(row)

    def test_incompatible_contract_rejected(self):
        row=envelope()
        for field in row['contract']:
            changed={**row['contract'],field:'different'}
            with self.subTest(field=field),self.assertRaises(ValueError): validate_profile(row,expected_contract=changed)
        with self.assertRaises(ValueError): validate_profile(row,expected_contract={})

    def test_scope_is_exact(self):
        with self.assertRaises(ValueError): validate_profile(envelope(),expected_scope={'asset_id':'other'})

    def test_payload_definition_cannot_be_relabeled(self):
        row=envelope()
        with self.assertRaises(ValueError):
            create_profile(row['payload'],profile_id='x',kind='fault_model',algorithm='wrong',feature_schema='features.example.v1',
                preprocessing=row['preprocessing'],training_groups=['1'],calibration_history=[],scope=row['scope'])

    def test_nonfinite_profile_not_json(self):
        for bad in (float('nan'),float('inf'),np.array([float('nan')])):
            with self.assertRaises(ValueError): profile_digest({'bad':bad})

    def test_fit_calibration_overlap_refused(self):
        row=envelope(); row['calibration_history'][0]['group_id']='original-1'
        row['envelope_sha256']=profile_digest({k:v for k,v in row.items() if k!='envelope_sha256'})
        with self.assertRaises(ValueError): validate_profile(row)

    def test_empty_scope_or_training_refused(self):
        row=envelope()
        for key,value in [('scope',{}),('training_groups',[]),('training_groups',['same','same'])]:
            changed=copy.deepcopy(row); changed[key]=value
            with self.assertRaises(ValueError): validate_profile(changed)

    def test_algorithm_loader_required_and_receives_copy(self):
        row=envelope(); registry=ProfileRegistry(); registry.register(row)
        def loader(payload): payload['weights'][0]=100; return payload
        loaded=registry.load('model-1',loader,expected_contract=row['contract'],expected_scope=row['scope'])
        self.assertEqual(loaded['weights'][0],100)
        self.assertEqual(registry.get('model-1',expected_contract=row['contract'],expected_scope=row['scope'])['payload']['weights'][0],1)
        with self.assertRaises(TypeError): registry.load('model-1',None,expected_contract=row['contract'],expected_scope=row['scope'])

    def test_registry_no_implicit_overwrite(self):
        row=envelope(); registry=ProfileRegistry(); registry.register(row)
        with self.assertRaises(ValueError): registry.register(row)
        listed=registry.list(); listed[0]['contract']['algorithm']='bad'
        self.assertEqual(registry.list()[0]['contract']['algorithm'],'example')
        registry.remove('model-1'); self.assertEqual(registry.list(),[])

    def test_actual_normal_reference_wrap_load_and_infer_unchanged(self):
        from test_p1_monitoring import reference,make
        from rotorvibe import NormalReferenceBank
        payload=reference()
        wrapped=create_profile(payload,profile_id='real-reference',kind='normal_reference',
            algorithm=payload['algorithm'],feature_schema=payload['feature_schema'],
            preprocessing=payload['scope']['signature'],training_groups=payload['fit_groups'],
            calibration_history=[{'calibration_id':'record-'+g,'group_id':g,'reviewed_on':'2026-11-04',
                                  'method':payload['calibration_unit']} for g in payload['calibration_groups']],scope=payload['scope'])
        registry=ProfileRegistry(); registry.register(wrapped)
        restored=registry.load('real-reference',lambda p:NormalReferenceBank([p]),
                              expected_contract=wrapped['contract'],expected_scope=wrapped['scope'])
        self.assertEqual(restored.analyze(make()),NormalReferenceBank([payload]).analyze(make()))

    def test_relabeling_original_groups_refused(self):
        row=envelope(); row['payload']['fit_groups']=['different']
        row['payload_sha256']=profile_digest(row['payload'])
        row['envelope_sha256']=profile_digest({k:v for k,v in row.items() if k!='envelope_sha256'})
        with self.assertRaises(ValueError): validate_profile(row)


class SpectrogramChecks(unittest.TestCase):
    def test_axes_and_analytic_peak(self):
        acc=SpectrogramAccumulator(hop_seconds=.25)
        r=observed(); acc.update(r); s=acc.snapshot()
        frequencies=np.array(s['frequencies_hz']); db=np.array(s['rows'][0]['db'])
        # 384 display bins; peak within one interpolation bin of 100 Hz.
        self.assertLess(abs(frequencies[np.argmax(db)]-100),6000/383)
        self.assertEqual(s['rows'][0]['end_time_s'],1)

    def test_display_bins_preserve_psd_integral_and_narrow_tone(self):
        r=observed(); spectral=r.payload['spectrogram']
        reconstructed=float(np.sum(10**(spectral['db']/10)*np.diff(spectral['bin_edges_hz'])))
        psd=r.payload['psd']; expected=float(np.sum(psd['y'])*(psd['x'][1]-psd['x'][0]))
        self.assertAlmostEqual(reconstructed,expected,places=12)
        self.assertAlmostEqual(reconstructed,.2**2/2,places=12)

    def test_gap_segment_not_filled_with_fake_rows(self):
        acc=SpectrogramAccumulator(hop_seconds=.25)
        for start in (0,.25,1.): acc.update(observed(start))
        s=acc.snapshot(); self.assertEqual(len(s['rows']),3)
        self.assertEqual(s['rows'][-1]['gap_before_s'],[.5,1.])
        self.assertEqual(s['rows'][-1]['segment_id'],1)

    def test_invalid_observation_is_explicit_missing(self):
        acc=SpectrogramAccumulator(hop_seconds=.25); acc.update(observed())
        acc.update(replace(observed(.25),valid=False,payload={}))
        row=acc.snapshot()['rows'][-1]; self.assertFalse(row['valid']); self.assertIsNone(row['db'])

    def test_count_bound_and_detached_snapshot(self):
        acc=SpectrogramAccumulator(hop_seconds=.25,max_frames=2)
        for i in range(4): acc.update(observed(i*.25))
        s=acc.snapshot(); self.assertEqual(len(s['rows']),2); self.assertEqual(s['evicted_frames'],2)
        s['rows'][0]['db'][0]=999; self.assertNotEqual(acc.snapshot()['rows'][0]['db'][0],999)

    def test_age_bound(self):
        acc=SpectrogramAccumulator(hop_seconds=1,max_age_seconds=1.1)
        for i in range(5): acc.update(observed(i))
        self.assertEqual(len(acc.snapshot()['rows']),2)

    def test_identity_change_clears_history(self):
        acc=SpectrogramAccumulator(hop_seconds=.25); acc.update(observed())
        acc.update(replace(observed(.25),clock_id='other'))
        self.assertEqual(len(acc.snapshot()['rows']),1)
        self.assertEqual(acc.snapshot()['rows'][0]['segment_id'],1)

    def test_bad_axis_and_nonfinite_rejected_without_mutation(self):
        acc=SpectrogramAccumulator(hop_seconds=.25); acc.update(observed())
        before=acc.snapshot()
        for spectrum in ({'frequencies':[1,1],'db':[2,3]}, {'frequencies':[1,2],'db':[np.nan,3]},
                         {'frequencies':[1,2],'db':[2,3]}):
            r=observed(.25)
            with self.assertRaises(ValueError): acc.update(replace(r,payload={**r.payload,'spectrogram':spectrum}))
            self.assertEqual(before,acc.snapshot())

    def test_duplicate_or_too_short_hop_rejected(self):
        acc=SpectrogramAccumulator(hop_seconds=.25); acc.update(observed())
        for start in (0,-1,.1):
            with self.assertRaises(ValueError): acc.update(observed(start))
        self.assertEqual(len(acc.snapshot()['rows']),1)

    def test_short_hop_after_invalid_row_does_not_set_frequency_axis(self):
        acc=SpectrogramAccumulator(hop_seconds=.25)
        acc.update(replace(observed(),valid=False,payload={}))
        before=acc.snapshot()
        with self.assertRaises(ValueError): acc.update(observed(.1))
        self.assertEqual(acc.snapshot(),before)

    def test_bounds_and_stage_lifecycle(self):
        for kw in ({'max_frames':True},{'max_age_seconds':np.inf},{'max_frames':100000,'max_frequencies':100000}):
            with self.assertRaises(ValueError): SpectrogramAccumulator(hop_seconds=.25,**kw)
        acc=SpectrogramAccumulator(hop_seconds=.25); stage=SpectrogramStage(acc)
        result=observed(stages={'history':stage})
        self.assertEqual(result.payload['history']['frames'],1)
        stage.reset_state(); self.assertEqual(acc.snapshot()['rows'],[])


def rule_context():
    return MachineContext('motor','motor',operating_state='steady',condition_id='run',location='DE')


def rule_document():
    return RuleDocument(Rule('illustrative-private-rule','demo','velocity','rms',('housing',),
        (1.,2.,3.),(10.,1000.),1,'invented example; no standard thresholds'),
        'example-edition-1','urn:example:private-reviewed-rule','a'*64,'reviewer','2026-11-04',
        {'asset_id':'motor','machine':'motor','operating_state':'steady','condition_id':'run','location':'DE'})


class ProviderChecks(unittest.TestCase):
    def measurement(self):
        return Measurement(1.5,'velocity','mm/s','rms','housing',(10.,1000.),1.,'radial','DE',
                           calibrated=True,acquisition_verified=True)

    def test_evaluation_provenance_and_invented_limits(self):
        provider=MemoryRuleProvider([rule_document()])
        r=evaluate_with_provider('illustrative-private-rule',rule_context(),self.measurement(),provider)
        self.assertEqual(r['zone'],'B'); self.assertEqual(r['rule_provenance']['edition'],'example-edition-1')
        self.assertFalse(r['whole_machine_compliance'])

    def test_scope_mismatch_never_evaluated(self):
        r=evaluate_with_provider('illustrative-private-rule',replace(rule_context(),asset_id='other'),
                                 self.measurement(),MemoryRuleProvider([rule_document()]))
        self.assertEqual(r['status'],'indeterminate'); self.assertIsNone(r['zone'])

    def test_ambiguous_editions_and_duplicate_refused(self):
        doc=rule_document(); provider=MemoryRuleProvider([doc])
        with self.assertRaises(ValueError): provider.register(doc)
        provider.register(replace(doc,edition='other'))
        with self.assertRaises(ValueError): provider.resolve(doc.rule.standard,rule_context())

    def test_missing_or_invalid_provenance_refused(self):
        doc=rule_document()
        for kw in ({'source_sha256':'bad'},{'reviewed_on':'not-date'},{'edition':''},{'context_scope':{}}):
            with self.subTest(kw=kw),self.assertRaises(ValueError): MemoryRuleProvider([replace(doc,**kw)])

    def test_provider_document_copy_not_shared(self):
        doc=rule_document(); provider=MemoryRuleProvider([doc]); doc.context_scope['asset_id']='other'
        returned=provider.resolve(doc.rule.standard,rule_context()); returned.context_scope['asset_id']='other'
        self.assertIsNotNone(provider.resolve(doc.rule.standard,rule_context()))

    def test_custom_provider_cannot_return_wrong_identifier(self):
        provider=SimpleNamespace(resolve=lambda standard,c:rule_document())
        with self.assertRaises(ValueError): evaluate_with_provider('wrong',rule_context(),self.measurement(),provider)

    def test_provider_in_raw_analyzer_and_mutual_exclusion(self):
        doc=rule_document(); provider=MemoryRuleProvider([doc])
        stage=IsoStage(doc.rule.standard,rule_context(),rule_provider=provider,point_id='DE',calibrated=True,acquisition_verified=True)
        result=observed(stages={'rule':stage},metadata={'asset_id':'motor','condition_id':'run','location':'DE','operating_state':'steady'})
        self.assertEqual(result.payload['rule']['status'],'evaluated')
        self.assertIn('rule_provenance',result.payload['rule'])
        with self.assertRaises(ValueError):
            IsoStage(doc.rule.standard,rule_context(),custom_rule=doc.rule,rule_provider=provider,point_id='DE')

    def test_provider_does_not_trust_wrong_live_asset_or_missing_context(self):
        doc=rule_document()
        stage=IsoStage(doc.rule.standard,rule_context(),rule_provider=MemoryRuleProvider([doc]),point_id='DE',calibrated=True,acquisition_verified=True)
        self.assertEqual(observed(stages={'rule':stage}).payload['rule']['reason'],'live_measurement_context_mismatch')
        result=observed(stages={'rule':stage},metadata={'asset_id':'other','condition_id':'run','location':'DE','operating_state':'steady'})
        self.assertIsNone(result.payload['rule']['zone'])


def history(*,record='held-life',group='held-group',event=True,role='final_test'):
    return LifeHistory(record,group,{'rpm':1800,'load':.5,'load_unit':'fraction','unit':'g','installation_id':'mount'},
                       (0.,10.,20.),((1.,),(1.2,),(2.,)),event,30.,role)


def forecast(record='held-life',point=20,lo=15,hi=25,cutoff=10):
    return dict(record_id=record,observed_until_s=cutoff,remaining_seconds=point,lower_seconds=lo,upper_seconds=hi)


class ExperimentalLifeChecks(unittest.TestCase):
    def test_compatibility_and_direct_default_disabled(self):
        catalog=SimpleNamespace(lives={'bad':None})
        for estimator in (LifeEstimator(catalog),ReferenceLifeEstimator(catalog)):
            r=estimator.estimate({}); self.assertEqual(r['status'],'disabled'); self.assertFalse(r['operational_use'])

    def test_life_stage_requires_explicit_opt_in(self):
        est=SimpleNamespace(estimate=lambda source:dict(status='experimental',remaining_seconds=10,operational_use=True))
        self.assertEqual(observed(stages={'life':LifeStage(est)}).payload['life']['status'],'disabled')
        r=observed(stages={'life':LifeStage(est,experimental_enabled=True)}).payload['life']
        self.assertFalse(r['operational_use']); self.assertFalse(r['field_rul_qualified'])

    def test_complete_life_hand_calculation(self):
        r=evaluate_life_predictions([history()],[forecast(point=18)],training_groups=['fit-life'])
        self.assertEqual(r['mae_seconds_equal_life'],2); self.assertEqual(r['rmse_seconds_equal_life'],2)
        self.assertEqual(r['empirical_interval_coverage_equal_life'],1)
        self.assertFalse(r['field_rul_qualified'])

    def test_censored_life_does_not_fabricate_exact_failure(self):
        r=evaluate_life_predictions([history(event=False)],[forecast(hi=19,point=18)],training_groups=['fit-life'])
        self.assertIsNone(r['mae_seconds_equal_life']); self.assertIsNone(r['empirical_interval_coverage_equal_life'])
        self.assertEqual(r['censored_survival_compatible_fraction'],0)

    def test_equal_life_weight_not_window_weight(self):
        a=history(); b=history(record='b',group='b')
        r=evaluate_life_predictions([a,b],[forecast(point=20),forecast(cutoff=20,point=10,lo=0,hi=20),
            forecast('b',point=24)],training_groups=['fit-life'])
        self.assertEqual(r['mae_seconds_equal_life'],2)

    def test_training_overlap_or_wrong_role_refused(self):
        for h in (history(group='fit-life'),history(role='life_fit')):
            with self.assertRaises(ValueError): evaluate_life_predictions([h],[forecast()],training_groups=['fit-life'])

    def test_invalid_followup_condition_and_nonfinite_history(self):
        h=history()
        for kw in ({'terminal_time_s':19},{'event_observed':1},{'condition':{}},{'rms':((np.nan,),)*3},
                   {'times_s':(0,10,10)}):
            with self.subTest(kw=kw),self.assertRaises(ValueError): replace(h,**kw).validate()

    def test_prediction_intervals_cutoffs_and_duplicates(self):
        for predictions in ([forecast(lo=22)], [forecast(cutoff=15)], [forecast(point=np.inf)],
                            [forecast(),forecast()]):
            with self.assertRaises(ValueError): evaluate_life_predictions([history()],predictions,training_groups=['fit-life'])

    def test_large_finite_life_errors_stay_json_finite(self):
        h=replace(history(),terminal_time_s=1e99)
        r=evaluate_life_predictions([h],[forecast(point=1e99,lo=0,hi=1e100)],training_groups=['fit-life'])
        json.dumps(r,allow_nan=False)

    def test_old_experiment_rejects_bad_reference(self):
        catalog=SimpleNamespace(lives={'a':{'role':'training_complete_life','nominal_rms_series':[[np.nan]]}})
        with self.assertRaises(ValueError): ReferenceLifeEstimator(catalog,experimental_enabled=True)

    def test_explicit_bench_estimate_is_not_confidence_interval(self):
        rms=np.linspace(1,5,40)[:,None]
        catalog=SimpleNamespace(lives={str(i):{'role':'training_complete_life','nominal_rms_series':rms,
              'bearing':str(i),'nominal_rpm':1800} for i in range(2)})
        est=ReferenceLifeEstimator(catalog,experimental_enabled=True)
        r=est.estimate({'dataset':'FEMTO','record_id':'new','rpm':1800,
                        'rul_prefix':{'baseline_rms':[1.],'recent_rms':[[4.],[4.2]]}})
        self.assertEqual(r['status'],'experimental'); self.assertFalse(r['confidence_interval_validated'])
        self.assertTrue(np.isfinite(r['remaining_seconds'])); json.dumps(r,allow_nan=False)


class AdapterAvailability(unittest.TestCase):
    def test_missing_optional_dependency_actionable(self):
        with patch('vibration.adapters.version',side_effect=PackageNotFoundError):
            self.assertFalse(process_adapter_info()['compatible'])
            with self.assertRaises(ImportError): to_process_batch([observed()])

    def test_wrong_optional_version_rejected(self):
        with patch('vibration.adapters.version',return_value='0.2.0'):
            self.assertFalse(process_adapter_info()['compatible'])
            with self.assertRaises(ImportError): from_process_batch(None,sample_rate_hz=12000,clock_id='clock')


@unittest.skipUnless(process_adapter_info()['compatible'],'Optional real process-monitoring-toolkit 0.1.0 not installed')
class ActualProcessBridge(unittest.TestCase):
    def batch(self,**kwargs):
        from process_monitoring import SignalBatch
        fs=12000; t=np.arange(fs*2)/fs
        return SignalBatch(t,np.sin(2*np.pi*100*t)[:,None],('radial',),('g',),
            metadata={'clock_id':'elapsed','vibration_source':{'asset_id':'motor'}},**kwargs)

    def test_real_bidirectional_pipeline(self):
        batch=self.batch(); block=from_process_batch(batch,sample_rate_hz=12000,clock_id='elapsed',rpm=1200)
        rows=VibrationAnalyzer(AnalysisConfig(unit='g',rpm=1200)).push(block)
        output=to_process_batch(rows)
        self.assertEqual(output.values.shape,(5,len(rows[0].feature_names)))
        self.assertEqual(output.metadata['clock_id'],'elapsed')
        self.assertEqual(output.metadata['vibration_source']['asset_id'],'motor')
        self.assertTrue(output.valid.all()); self.assertEqual(output.time_s[0],1)

    def test_real_process_monitor_scores_exported_features(self):
        from process_monitoring import Monitor,create_detector
        from process_monitoring.features import WindowFeatures
        block=from_process_batch(self.batch(),sample_rate_hz=12000,clock_id='elapsed',rpm=1200)
        features=to_process_batch(VibrationAnalyzer(AnalysisConfig(unit='g')).push(block))
        monitor=Monitor(create_detector('isolation_forest',n_estimators=10,random_state=3),
                        WindowFeatures(window=1,statistics=('mean',)))
        monitor.fit(features); monitor.calibrate(features,false_alarm_fraction=.2)
        detection=monitor.score(features)
        self.assertTrue(detection.valid.any()); self.assertEqual(len(detection.time_s),len(features.time_s))

    def test_gap_and_mixed_episode_or_modes_refused(self):
        from process_monitoring import SignalBatch
        batch=self.batch()
        gap=batch.time_s.copy(); gap[12000:]+=.1
        for changed in (replace(batch,time_s=gap),replace(batch,episodes=np.arange(len(gap))),
                        replace(batch,modes=np.arange(len(gap)))):
            with self.assertRaises(ValueError): from_process_batch(changed,sample_rate_hz=12000,clock_id='elapsed')

    def test_clock_mismatch_and_feature_reimport_refused(self):
        with self.assertRaises(ValueError): from_process_batch(self.batch(),sample_rate_hz=12000,clock_id='other')
        rows=VibrationAnalyzer(AnalysisConfig(unit='g')).push(from_process_batch(self.batch(),sample_rate_hz=12000,clock_id='elapsed'))
        output=to_process_batch(rows)
        with self.assertRaises(ValueError): from_process_batch(output,sample_rate_hz=4,clock_id='elapsed')

    def test_invalid_feature_window_retains_mask(self):
        a=observed(); b=replace(observed(.25),valid=False,payload={})
        output=to_process_batch([a,b])
        self.assertTrue(output.valid[0].all()); self.assertFalse(output.valid[1].any())
        self.assertTrue(np.isnan(output.values[1]).all())

    def test_mixed_identity_and_unsorted_results_refused(self):
        a=observed(); b=observed(.25)
        with self.assertRaises(ValueError): to_process_batch([b,a])
        with self.assertRaises(ValueError): to_process_batch([a,replace(b,metadata={**b.metadata,'source':{'asset_id':'other'}})])

    def test_constant_mode_preserved_and_cross_packet_change_resets_buffer(self):
        batch=self.batch(); analyzer=VibrationAnalyzer(AnalysisConfig(unit='g'))
        def block(start,mode):
            raw=batch.subset(np.arange(start,start+6000))
            raw=replace(raw,modes=np.full(6000,mode))
            return from_process_batch(raw,sample_rate_hz=12000,clock_id='elapsed')
        self.assertEqual(analyzer.push(block(0,0)),[])
        self.assertEqual(analyzer.push(block(6000,1)),[])  # never join different modes
        rows=analyzer.push(block(12000,1))
        output=to_process_batch(rows)
        self.assertTrue(np.all(output.modes==1)); self.assertEqual(output.metadata['vibration_source']['operating_mode'],1)

    def test_conflicting_declared_mode_refused(self):
        batch=self.batch(); batch=replace(batch,modes=np.zeros(len(batch.time_s)),
            metadata={'vibration_source':{'operating_mode':2}})
        with self.assertRaises(ValueError): from_process_batch(batch,sample_rate_hz=12000,clock_id='elapsed')


if __name__=='__main__': unittest.main()
