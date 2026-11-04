"""P1 acquisition/reference/lifecycle/queue/evaluation contracts and physical angle checks."""
from dataclasses import replace
from pathlib import Path
import hashlib,json,tempfile,threading,unittest
import numpy as np
from rotorvibe import (AnalysisConfig,SignalBlock,VibrationAnalyzer,AcquisitionInfo,check_acquisition,
    NormalRecording,fit_normal_reference,NormalReferenceBank,ReferenceStage,DecisionStage,AlarmStage,
    GuidanceStage,hold_guidance,RealtimeProcessor,angle_features,angle_resample,
    fit_angle_fault_discriminator,AngleFaultDiscriminator,AngleFaultStage,
    ValidationObservation,evaluate_observations,DatasetRecord,ValidationPlan,FrozenEvaluation,BaselineStage)


def make(*,amplitude=1.,load=.5,asset='rig',installation='mount1',rpm=1200,variable=False,start=0):
    fs=12000; count=fs*2; speed=np.linspace(600,1500,count) if variable else np.full(count,rpm)
    phase=np.r_[0,np.cumsum((speed[:-1]+speed[1:])/(120*fs))]
    wave=amplitude*(np.sin(2*np.pi*phase)+.1*np.cos(4*np.pi*phase))
    info=AcquisitionInfo(asset,'sensor',installation,'cert1','2026-11-04','2027-01-01',
        ('radial',),('radial',),fs,'g',(1,6000),5500,'tachometer' if variable else 'controller_nominal',
        calibrated=True,mounting_verified=True,anti_alias_verified=True)
    config=AnalysisConfig(unit='g',window_seconds=2,hop_seconds=2,load=load,rpm=rpm)
    block=SignalBlock(wave,fs,unit='g',start_time_s=start,rpm=speed if variable else rpm,channels=('radial',),
        metadata={'asset_id':asset,'condition_id':'steady','load_unit':'fraction_rated','acquisition':info.to_dict()})
    return VibrationAnalyzer(config).analyze(block)


def reference(*,representation='time'):
    def record(i,amp): return NormalRecording(str(i),str(i),(make(amplitude=amp,variable=representation=='angle'),),True,
                                             'normal_fit' if i<=2 else 'normal_calibration')
    return fit_normal_reference([record(1,1.),record(2,1.04)],[record(3,1.01),record(4,1.03)],
        name='normal-'+representation,rpm_range=(600,1500) if representation=='angle' else (1188,1212),
        load_range=(.4,.6),representation=representation)


class AcquisitionChecks(unittest.TestCase):
    def test_valid_physical_contract_accepted(self):
        self.assertEqual(check_acquisition(make())['status'],'accepted')

    def test_expiry_missing_mounting_and_sensor_band_hold(self):
        for key,value in [('calibration_due','2020-01-01'),('mounting_verified',False),
                          ('anti_alias_verified',False),('sensor_band_hz',[10,1000]),
                          ('asset_id','wrong'),('unit','V')]:
            result=make(); source=dict(result.metadata['source']); acquisition=dict(source['acquisition']); acquisition[key]=value
            source['acquisition']=acquisition; changed=replace(result,metadata={**result.metadata,'source':source})
            with self.subTest(key=key): self.assertEqual(check_acquisition(changed)['status'],'hold')

    def test_nominal_speed_is_not_a_measured_trace(self):
        self.assertEqual(check_acquisition(make(),require_measured_rpm=True)['status'],'hold')
        self.assertEqual(check_acquisition(make(variable=True),require_measured_rpm=True)['status'],'accepted')

    def test_unknown_units_or_dates_are_not_invented(self):
        result=make(); source=dict(result.metadata['source']); source.pop('acquisition')
        self.assertEqual(check_acquisition(replace(result,metadata={**result.metadata,'source':source}))['status'],'hold')

    def test_incomplete_measurement_and_fabricated_nominal_trace_hold(self):
        result=make(variable=True)
        self.assertEqual(check_acquisition(replace(result,metadata={'source':result.metadata['source']}))['status'],'hold')
        source=dict(result.metadata['source']); source['acquisition']={**source['acquisition'],'rpm_source':'controller_nominal'}
        self.assertEqual(check_acquisition(replace(result,metadata={**result.metadata,'source':source}))['status'],'hold')

    def test_stream_buffer_does_not_upgrade_nominal_rpm_to_measured_trace(self):
        fs=12000; wave=np.sin(2*np.pi*20*np.arange(fs)/fs)
        analyzer=VibrationAnalyzer(AnalysisConfig(rpm=1200))
        result=analyzer.push(SignalBlock(wave,fs,rpm=1200))[0]
        self.assertIsNone(result.rpm_trace)
        self.assertEqual(result.payload['order_spectrum']['mode'],'constant_rpm_reference')

    def test_mixed_scalar_and_measured_speed_cannot_create_qualified_window(self):
        fs=12000; wave=np.sin(2*np.pi*20*np.arange(fs//2)/fs)
        analyzer=VibrationAnalyzer(AnalysisConfig(rpm=1200))
        self.assertEqual(analyzer.push(SignalBlock(wave,fs,rpm=1200)),[])
        result=analyzer.push(SignalBlock(wave,fs,rpm=np.full(fs//2,1200.),start_time_s=.5))[0]
        self.assertFalse(result.valid); self.assertIsNone(result.rpm_trace)


class ReferenceChecks(unittest.TestCase):
    def test_registered_normal_anomaly_and_changed_installation(self):
        bank=NormalReferenceBank([reference()])
        self.assertEqual(bank.analyze(make(amplitude=1.02))['status'],'normal')
        self.assertEqual(bank.analyze(make(amplitude=30))['status'],'anomaly_unknown')
        self.assertEqual(bank.analyze(make(installation='new'))['reason'],'normal_reference_scope_mismatch')

    def test_unseen_load_speed_and_ambiguous_profiles_hold(self):
        p=reference(); bank=NormalReferenceBank([p])
        self.assertEqual(bank.analyze(make(load=.9))['status'],'hold')
        self.assertEqual(bank.analyze(make(rpm=900))['status'],'hold')
        other={**p,'name':'overlap'}; bank.register(other)
        self.assertEqual(bank.analyze(make())['reason'],'reference_ambiguous')

    def test_fit_calibration_group_leakage_rejected(self):
        r=make(); a=NormalRecording('a','groupA',(r,),True,'normal_fit'); b=NormalRecording('b','groupB',(r,),True,'normal_fit')
        c=NormalRecording('c','groupC',(r,),True,'normal_calibration')
        with self.assertRaises(ValueError): fit_normal_reference([a,b],[a,c],name='bad',rpm_range=(1000,1300),load_range=(0,1))
        with self.assertRaises(ValueError): fit_normal_reference([a,b],[replace(c,confirmed_normal=False),replace(c,record_id='d',group_id='d')],name='bad',rpm_range=(1000,1300),load_range=(0,1))

    def test_final_test_and_duplicate_hash_cannot_enter_reference_fit(self):
        result=make(); final=DatasetRecord('held','held','session','mount','newrig','normal','final_test','a'*64)
        with self.assertRaises(ValueError): NormalRecording.from_plan(final,[result],confirmed_normal=True)
        records=[NormalRecording(str(i),str(i),(result,),True,'normal_fit' if i<2 else 'normal_calibration','a'*64) for i in range(4)]
        with self.assertRaises(ValueError): fit_normal_reference(records[:2],records[2:],name='bad',rpm_range=(1188,1212),load_range=(.4,.6))

    def test_profile_roundtrip_and_host_bank_not_mutated_by_stage_reset(self):
        bank=NormalReferenceBank(json.loads(json.dumps([reference()])))
        stage=ReferenceStage(bank); before=bank.export(); stage.reset_state(preserve_profiles=False)
        self.assertEqual(stage(make())['reason'],'normal_reference_disabled'); self.assertEqual(before,bank.export())
        stage.activate(); self.assertEqual(stage(make())['status'],'normal')

    def test_bad_profile_refused_and_duplicated_name_not_replaced(self):
        p=reference(); bank=NormalReferenceBank([p])
        with self.assertRaises(ValueError): bank.register(p)
        p['center'][0]=float('nan')
        with self.assertRaises(ValueError): NormalReferenceBank([p])

    def test_missing_profile_fields_and_changed_filter_scope_refused(self):
        p=reference(); incomplete=dict(p); incomplete.pop('fit_groups')
        with self.assertRaises(ValueError): NormalReferenceBank([incomplete])
        result=make(); source=dict(result.metadata['source'])
        source['acquisition']={**source['acquisition'],'anti_alias_cutoff_hz':5400}
        changed=replace(result,metadata={**result.metadata,'source':source})
        self.assertEqual(NormalReferenceBank([p]).analyze(changed)['status'],'hold')

    def test_angle_reference_refuses_display_decimation_and_wrong_sensor_band(self):
        bank=NormalReferenceBank([reference(representation='angle')]); result=make(variable=True)
        payload={**result.payload,'waveform':{'y':result.payload['waveform']['y'][::2]}}
        self.assertEqual(bank.analyze(replace(result,payload=payload),representation='angle')['status'],'hold')
        source=dict(result.metadata['source']); source['acquisition']={**source['acquisition'],'sensor_band_hz':[8,6000]}
        self.assertEqual(bank.analyze(replace(result,metadata={**result.metadata,'source':source}),representation='angle')['status'],'hold')

    def test_angle_normal_reference_accepts_measured_ramp_only(self):
        bank=NormalReferenceBank([reference(representation='angle')])
        self.assertEqual(bank.analyze(make(variable=True),representation='angle')['status'],'normal')
        self.assertEqual(bank.analyze(make(),representation='angle')['status'],'hold')
        self.assertEqual(bank.analyze(make(variable=True))['status'],'hold')

    def test_real_reference_decision_guidance_alarm_pipeline(self):
        result=make(); bank=NormalReferenceBank([reference()])
        source=ReferenceStage(bank); decision=DecisionStage('reference'); guidance=GuidanceStage('decision')
        payload=dict(result.payload); current=replace(result,payload=payload)
        payload['reference']=source(current); payload['decision']=decision(current); payload['guidance']=guidance(current)
        payload['alarm']=AlarmStage(score_stage='decision',expected_score_name='normal_score',persistence_seconds=0)(current)
        self.assertEqual(payload['decision']['status'],'normal'); self.assertEqual(payload['alarm']['level'],'normal')
        self.assertEqual(payload['guidance']['required_actions'],[]); json.dumps(current.to_dict(),allow_nan=False)


class LifecycleChecks(unittest.TestCase):
    def test_explicit_buffer_only_vs_stage_reset(self):
        alarm=AlarmStage(persistence_seconds=0); analyzer=VibrationAnalyzer(stages={'baseline':lambda _:{'score':10},'alarm':alarm})
        wave=np.sin(2*np.pi*20*np.arange(12000)/12000)
        analyzer.analyze(SignalBlock(wave,12000)); self.assertEqual(alarm.level,'danger')
        analyzer.reset(); self.assertEqual(alarm.level,'danger')
        analyzer.reset(reset_stages=True); self.assertEqual(alarm.level,'unavailable')

    def test_baseline_collection_cancel_and_profile_preservation_are_explicit(self):
        baseline=BaselineStage(AnalysisConfig()); baseline.begin(windows=20)
        analyzer=VibrationAnalyzer(stages={'baseline':baseline}); wave=np.sin(2*np.pi*20*np.arange(12000)/12000)
        analyzer.push(SignalBlock(wave,12000)); self.assertTrue(baseline.baseline.collecting)
        analyzer.reset(reset_stages=True); self.assertFalse(baseline.baseline.collecting)
        baseline.baseline.profile={'source_scope':{'asset_id':'A'},'sentinel':True}
        analyzer.reset(reset_stages=True); self.assertTrue(baseline.export_profile()['sentinel'])
        analyzer.reset(reset_stages=True,preserve_profiles=False); self.assertIsNone(baseline.export_profile())

    def test_gap_and_identity_change_clear_alarm_state(self):
        alarm=AlarmStage(persistence_seconds=10)
        analyzer=VibrationAnalyzer(AnalysisConfig(hop_seconds=1),stages={'baseline':lambda _:{'score':10},'alarm':alarm})
        wave=np.sin(2*np.pi*20*np.arange(12000)/12000)
        analyzer.push(SignalBlock(wave,12000,start_time_s=0,metadata={'asset_id':'A'}))
        self.assertEqual(alarm.since,1)
        analyzer.push(SignalBlock(wave,12000,start_time_s=20,metadata={'asset_id':'B'}))
        self.assertEqual(alarm.since,21); self.assertEqual(alarm.level,'unavailable')


class AngleChecks(unittest.TestCase):
    def test_ramp_order_one_and_half_order_recovered(self):
        fs=12000; speed=np.linspace(600,1500,24000); phase=np.r_[0,np.cumsum((speed[:-1]+speed[1:])/(120*fs))]
        for target in (.5,1,3):
            f=angle_features(np.sin(2*np.pi*target*phase),fs,speed)
            powers={name:value for name,value in zip(f.names,f.values) if '_order_' in name}
            self.assertEqual(max(powers,key=powers.get),f'ch1_order_{target:g}X')
            self.assertAlmostEqual(np.exp(max(powers.values())),1.,delta=.01)

    def test_anti_aliasing_suppresses_out_of_order_band(self):
        fs=12000; speed=np.full(24000,1200.)
        angular,_=angle_resample(np.sin(2*np.pi*4000*np.arange(24000)/fs),fs,speed)
        self.assertLess(float(np.sqrt(np.mean(angular**2))),.01)

    def test_reject_missing_nonpositive_speed_short_record_and_unresolvable_grid(self):
        wave=np.sin(np.arange(24000))
        for speed in (None,np.zeros(24000),np.ones(12),np.full(24000,np.nan)):
            with self.subTest(speed_type=type(speed).__name__),self.assertRaises(ValueError): angle_features(wave,12000,speed)
        with self.assertRaises(ValueError): angle_features(wave,12000,np.full(24000,60.))
        with self.assertRaises(ValueError): angle_features(wave,12000,np.linspace(60,1600,24000),samples_per_revolution=64)

    def test_angle_head_requires_new_profile_measured_source_and_anomaly_gate(self):
        result=make(variable=True); f=angle_features(result.payload['waveform']['y'],12000,result.rpm_trace)
        scope={'asset_id':'rig','condition_id':'steady','unit':'g','channel_names':['radial'],'rpm_source':'tachometer'}
        x=f.values; p=fit_angle_fault_discriminator(np.vstack([x,x+.01,x+3,x+3.01,x-3,x-3.01]),
            ['looseness']*2+['unbalance']*2+['misalignment']*2,[1050]*6,list(range(6)),names=f.names,scope=scope)
        model=AngleFaultDiscriminator(json.loads(json.dumps(p)))
        prediction=model.analyze(result.payload['waveform']['y'],12000,result.rpm_trace,scope=scope)
        self.assertEqual(prediction['label'],'looseness'); json.dumps(prediction,allow_nan=False)
        self.assertEqual(model.analyze(result.payload['waveform']['y'],12000,result.rpm_trace,scope={**scope,'rpm_source':'operator_nominal'})['status'],'hold')
        self.assertEqual(AngleFaultStage(model).analyze_window(result,result.payload['waveform']['y'])['reason'],'angle_experiment_not_enabled')
        self.assertEqual(AngleFaultStage(model,experimental_enabled=True).analyze_window(result,result.payload['waveform']['y'])['reason'],'confirmed_anomaly_gate_required')
        gated=replace(result,payload={**result.payload,'reference':{'anomaly':True}})
        combined=AngleFaultStage(model,experimental_enabled=True).analyze_window(gated,result.payload['waveform']['y'])
        self.assertEqual(combined['label'],'looseness'); self.assertIs(combined['anomaly'],True)
        self.assertEqual(combined['anomaly_source'],'reference')

    def test_physical_synthetic_looseness_unbalance_shapes_at_unseen_speed_ramp(self):
        fs=12000; names=None; rows=[]; labels=[]; groups=[]
        def signal(label,speed,amplitude):
            phase=np.r_[0,np.cumsum((speed[:-1]+speed[1:])/(120*fs))]
            wave=np.sin(2*np.pi*phase)
            if label=='looseness': wave+=.5*np.sin(np.pi*phase)+.3*np.sin(6*np.pi*phase)
            if label=='misalignment': wave+=.8*np.sin(4*np.pi*phase)
            return amplitude*wave
        up=np.linspace(600,1500,24000); down=up[::-1].copy()
        for index,label in enumerate(('looseness','unbalance','misalignment')):
            for repeat,amp in enumerate((.95,1.05)):
                f=angle_features(signal(label,up,amp),fs,up); names=f.names
                rows.append(f.values); labels.append(label); groups.append(f'{index}-{repeat}')
        scope={'asset_id':'synthetic','condition_id':'ramp','unit':'m/s^2','channel_names':['radial'],'rpm_source':'encoder'}
        profile=fit_angle_fault_discriminator(rows,labels,[1050]*6,groups,names=names,scope=scope)
        model=AngleFaultDiscriminator(profile)
        for label in ('looseness','unbalance','misalignment'):
            predicted=model.analyze(signal(label,down,1.),fs,down,scope=scope)
            self.assertEqual(predicted['status'],'fault_candidate'); self.assertEqual(predicted['label'],label)

    def test_boolean_or_out_of_range_sampling_refused(self):
        wave=np.sin(np.arange(24000)); rpm=np.full(24000,1200.)
        for fs in (True,1e-300,1e308):
            with self.assertRaises(ValueError): angle_features(wave,fs,rpm)
        with self.assertRaises(ValueError): angle_features(wave,12000,np.ones(24000,dtype=bool))


class RealtimeChecks(unittest.TestCase):
    def block(self,start=0): return SignalBlock(np.sin(2*np.pi*20*np.arange(12000)/12000),12000,start_time_s=start)

    def test_bounded_reject_queue_and_measured_stats(self):
        processor=RealtimeProcessor(VibrationAnalyzer(AnalysisConfig(hop_seconds=1)),max_pending=1)
        self.assertTrue(processor.submit(self.block())['accepted']); self.assertFalse(processor.submit(self.block(1))['accepted'])
        self.assertEqual(len(processor.process_next()),1)
        stats=processor.stats(); self.assertEqual(stats['rejected'],1); self.assertEqual(stats['windows'],1)
        self.assertIsNotNone(stats['processing_seconds_p95']); self.assertFalse(stats['hard_realtime_guarantee'])
        processor.close()
        with self.assertRaises(RuntimeError): processor.submit(self.block())

    def test_drop_oldest_is_counted_and_clipping_queue_size_rejected(self):
        processor=RealtimeProcessor(VibrationAnalyzer(),max_pending=1,overflow='drop_oldest')
        processor.submit(self.block()); processor.submit(self.block(1))
        self.assertEqual(processor.stats()['dropped'],1); self.assertEqual(processor.process_next()[0].start_time_s,1)
        with self.assertRaises(ValueError): RealtimeProcessor(VibrationAnalyzer(),max_pending=True)
        with self.assertRaises(ValueError): RealtimeProcessor(VibrationAnalyzer(),max_chunk_samples=10).submit(self.block())

    def test_metadata_snapshot_and_failure_propagation(self):
        block=self.block(); block.metadata['asset_id']='A'; processor=RealtimeProcessor(VibrationAnalyzer())
        processor.submit(block); block.metadata['asset_id']='B'
        self.assertEqual(processor.process_next()[0].metadata['source']['asset_id'],'A')
        def fail(_): raise RuntimeError('downstream failure')
        processor=RealtimeProcessor(VibrationAnalyzer(stages={'custom':fail})); processor.submit(self.block())
        with self.assertRaises(RuntimeError): processor.process_next()
        self.assertEqual(processor.stats()['failed'],1)

    def test_consumer_exclusion_and_latency_budget_accounting(self):
        started=threading.Event(); resume=threading.Event()
        def stage(_):
            started.set()
            if not resume.wait(2): raise RuntimeError('test resume timeout')
            return {}
        processor=RealtimeProcessor(VibrationAnalyzer(stages={'pause':stage}),latency_budget_seconds=1e-12)
        processor.submit(self.block()); errors=[]
        def consume():
            try: processor.process_next()
            except Exception as exc: errors.append(exc)
        worker=threading.Thread(target=consume); worker.start()
        try:
            self.assertTrue(started.wait(2))
            with self.assertRaises(RuntimeError): processor.process_next()
            with self.assertRaises(RuntimeError): processor.close()
        finally: resume.set(); worker.join(timeout=3)
        self.assertFalse(worker.is_alive()); self.assertEqual(errors,[])
        self.assertEqual(processor.stats()['deadline_misses'],1); self.assertIsNotNone(processor.stats()['latency_seconds_p95'])


class EvaluationChecks(unittest.TestCase):
    def row(self,start,truth='normal',decision=None,level='unavailable',acquisition='acq'):
        return ValidationObservation('record',acquisition,start,start+2,truth,decision or {'status':'hold'},level)

    def test_all_hold_has_null_fpr_and_zero_coverage(self):
        result=evaluate_observations([self.row(0),self.row(1)])
        self.assertIsNone(result['normal_false_positive_rate']); self.assertEqual(result['normal_decision_coverage'],0)
        self.assertIsNone(result['false_alarm_events_per_normal_hour']); self.assertEqual(result['normal_seconds'],3)

    def test_overlap_union_alarm_episodes_and_unknown_is_not_recovery(self):
        rows=[self.row(0,decision={'status':'normal'},level='normal'),
              self.row(1,decision={'status':'anomaly_unknown','anomaly':True},level='warning'),
              self.row(2),self.row(3,decision={'status':'anomaly_unknown','anomaly':True},level='danger')]
        result=evaluate_observations(rows)
        self.assertEqual(result['normal_seconds'],5); self.assertEqual(result['alarm_events_observed'],1)
        self.assertEqual(result['alarm_duration_confirmed_seconds'],0)
        self.assertAlmostEqual(result['normal_false_positive_rate'],2/3)

    def test_unconditional_type_accuracy_counts_holds_and_unknowns_wrong(self):
        rows=[self.row(0,'looseness',{'status':'fault_candidate','label':'looseness','anomaly':True},'warning'),
              self.row(2,'looseness'),self.row(4,'looseness',{'status':'anomaly_unknown','anomaly':True})]
        result=evaluate_observations(rows,fault_onsets={'record':0})
        self.assertAlmostEqual(result['fault_type_accuracy_unconditional'],1/3)
        self.assertEqual(result['fault_type_accuracy_conditional'],1)
        self.assertEqual(result['detection_delay_seconds']['record'],2)

    def test_duplicate_intervals_and_mixed_acquisition_truth_refused(self):
        row=self.row(0)
        with self.assertRaises(ValueError): evaluate_observations([row,row])
        with self.assertRaises(ValueError): evaluate_observations([row,self.row(2,'unbalance')])

    def test_guidance_never_overrides_scope(self):
        result=hold_guidance({'status':'hold','reason':'normal_reference_scope_mismatch'})
        self.assertTrue(result['required_actions']); self.assertFalse(result['automatic_scope_override'])
        self.assertEqual(hold_guidance({'status':'normal'})['required_actions'],[])

    def test_contradictory_or_nonfinite_ground_truth_decisions_refused(self):
        for decision in ({'status':'normal','anomaly':True},{'status':'normal','score':float('nan')}):
            with self.assertRaises(ValueError): evaluate_observations([self.row(0,decision=decision)])

    def test_alarm_before_fault_onset_is_not_claimed_as_detection(self):
        rows=[self.row(0,'unbalance',{'status':'fault_candidate','anomaly':True,'label':'unbalance'},'warning'),
              self.row(2,'unbalance',{'status':'fault_candidate','anomaly':True,'label':'unbalance'},'danger')]
        result=evaluate_observations(rows,fault_onsets={'record':3})
        self.assertIsNone(result['detection_delay_seconds']['record'])

    def test_standalone_fault_head_is_not_unconditional_pipeline_accuracy(self):
        row=self.row(0,'looseness',{'status':'fault_candidate','label':'looseness','conditional_on_anomaly':True})
        result=evaluate_observations([row])
        self.assertEqual(result['fault_head_accuracy_given_true_fault'],1)
        self.assertEqual(result['fault_type_accuracy_unconditional'],0)
        self.assertEqual(result['fault_type_coverage'],0)


class ValidationPlanChecks(unittest.TestCase):
    def record(self,name,role,rig='old'):
        return DatasetRecord(name,name,name,name,rig,'normal',role,hashlib.sha256(name.encode()).hexdigest())

    def test_role_and_independence_leakage_rejected(self):
        fit=self.record('fit','normal_fit'); test=self.record('test','final_test')
        with self.assertRaises(ValueError): ValidationPlan([fit,replace(test,sha256=fit.sha256)])
        with self.assertRaises(ValueError): ValidationPlan([fit,replace(test,acquisition_id='fit')])
        with self.assertRaises(ValueError): ValidationPlan([fit,test],independent_by='rig')
        ValidationPlan([fit,replace(test,rig_id='new')],independent_by='rig')

    def test_frozen_access_records_before_decode_and_replay_is_not_fresh(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); raw=root/'raw'; raw.write_bytes(b'test')
            plan=ValidationPlan([self.record('fit','normal_fit'),self.record('test','final_test',rig='new')],independent_by='rig')
            checksum=plan.freeze(root/'plan.json',model_sha256='a'*64,preprocessing_sha256='b'*64)
            with self.assertRaises(FileExistsError): plan.freeze(root/'plan.json',model_sha256='a'*64,preprocessing_sha256='b'*64)
            evaluator=FrozenEvaluation(root/'plan.json',plan_sha256=checksum,access_log=root/'access.jsonl')
            def loader(path):
                self.assertTrue((root/'access.jsonl').exists()); return path.read()
            self.assertEqual(evaluator.load_test('test',raw,loader,model_sha256='a'*64,preprocessing_sha256='b'*64),b'test')
            with self.assertRaises(PermissionError): evaluator.load_test('test',raw,loader,model_sha256='a'*64,preprocessing_sha256='b'*64)
            evaluator.load_test('test',raw,loader,model_sha256='a'*64,preprocessing_sha256='b'*64,replay=True)
            with self.assertRaises(ValueError): evaluator.load_test('test',raw,loader,model_sha256='c'*64,preprocessing_sha256='b'*64,replay=True)
            self.assertIn('historical_replay',(root/'access.jsonl').read_text())
            with self.assertRaises(ValueError): plan.fitting_records('final_test')

    def test_snapshot_and_cross_instance_access_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); raw=root/'raw'; raw.write_bytes(b'test')
            plan=ValidationPlan([self.record('test','final_test')])
            checksum=plan.freeze(root/'plan',model_sha256='a'*64,preprocessing_sha256='b'*64)
            evaluator=FrozenEvaluation(root/'plan',plan_sha256=checksum,access_log=root/'access')
            (root/'access.lock').write_text('busy')
            with self.assertRaises(RuntimeError): evaluator.load_test('test',raw,lambda f:f.read(),model_sha256='a'*64,preprocessing_sha256='b'*64)
            (root/'access.lock').unlink()
            def loader(stream):
                raw.write_bytes(b'changed after verification'); return stream.read()
            self.assertEqual(evaluator.load_test('test',raw,loader,model_sha256='a'*64,preprocessing_sha256='b'*64),b'test')
            with self.assertRaises(ValueError): evaluator.load_test('test',raw,loader,model_sha256='a'*64,preprocessing_sha256='b'*64,replay=True)

    def test_bad_snapshot_quota_refused_before_decode(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); raw=root/'raw'; raw.write_bytes(b'test')
            plan=ValidationPlan([self.record('test','final_test')]); checksum=plan.freeze(root/'plan',model_sha256='a'*64,preprocessing_sha256='b'*64)
            evaluator=FrozenEvaluation(root/'plan',plan_sha256=checksum,access_log=root/'log',max_record_bytes=3)
            with self.assertRaises(ValueError): evaluator.load_test('test',raw,lambda _:self.fail('decoded oversized record'),model_sha256='a'*64,preprocessing_sha256='b'*64)


if __name__=='__main__': unittest.main()
