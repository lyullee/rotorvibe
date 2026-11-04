import copy,json,unittest
import numpy as np
from vibration.fault_discrimination import fault_features,fit_fault_discriminator,FaultDiscriminator,FaultDiscriminationStage
from vibration import VibrationAnalyzer,AnalysisConfig,SignalBlock

SCOPE={'asset_id':'rig','condition_id':'steady','unit':'g'}
def fixture():
    x=[[0,0],[.1,0],[3,0],[3.1,0],[0,3],[0,3.1]]
    return fit_fault_discriminator(x,['looseness']*2+['unbalance']*2+['misalignment']*2,[1200]*6,list(range(6)),names=['order_1','order_2'],scope=SCOPE)

class FaultChecks(unittest.TestCase):
    def test_known_half_order_energy(self):
        fs=8000; t=np.arange(fs*2)/fs
        names,x=fault_features(np.sin(2*np.pi*10*t),fs,1200)
        self.assertGreater(x[names.index('order_0.5')],x[names.index('order_1')]+10)
    def test_gain_changes_level_but_not_morphology(self):
        t=np.arange(16000)/8000; a=np.sin(2*np.pi*20*t)+.1*np.sin(2*np.pi*40*t)
        names,x=fault_features(a,8000,1200); _,y=fault_features(3*a,8000,1200)
        self.assertAlmostEqual(y[0]-x[0],np.log(3),places=10); np.testing.assert_allclose(x[1:],y[1:],atol=1e-9)
    def test_impacts_increase_kurtosis(self):
        t=np.arange(16000)/8000; a=np.sin(2*np.pi*20*t); b=a.copy(); b[4000]+=40
        names,x=fault_features(a,8000,1200); _,y=fault_features(b,8000,1200)
        self.assertGreater(y[names.index('log_kurtosis')],x[names.index('log_kurtosis')])
    def test_invalid_raw_inputs(self):
        for a,fs,rpm in [(np.zeros(16000),8000,1200),(np.ones(16000)*np.nan,8000,1200),(np.ones((16000,2)),8000,1200),(np.ones(8000),8000,1200),(np.ones(16000),8000,None)]:
            with self.assertRaises(ValueError): fault_features(a,fs,rpm)
    def test_class_prototypes_and_serialization(self):
        p=fixture(); m=FaultDiscriminator(json.loads(json.dumps(p)))
        for x,label in [([0,0],'looseness'),([3,0],'unbalance'),([0,3],'misalignment')]: self.assertEqual(m.predict(x,1200,scope=SCOPE)['label'],label)
    def test_ties_and_novelty_abstain(self):
        p=fixture(); p['prototypes']=[[0,0]]*6; m=FaultDiscriminator(p)
        self.assertEqual(m.predict([0,0],1200,scope=SCOPE)['status'],'anomaly_unknown')
        self.assertEqual(FaultDiscriminator(fixture()).predict([100,100],1200,scope=SCOPE)['status'],'anomaly_unknown')
    def test_scope_speed_and_nonfinite(self):
        m=FaultDiscriminator(fixture())
        self.assertEqual(m.predict([0,0],1200,scope={**SCOPE,'unit':'m/s^2'})['status'],'hold')
        self.assertEqual(m.predict([0,0],None,scope=SCOPE)['status'],'hold')
        with self.assertRaises(ValueError): m.predict([float('nan'),0],1200,scope=SCOPE)
        p=fixture(); p['scale']=[0,1]
        with self.assertRaises(ValueError): FaultDiscriminator(p)
    def test_recording_roles_cannot_mix_classes(self):
        with self.assertRaises(ValueError): fit_fault_discriminator([[0],[1],[2]],['looseness','unbalance','misalignment'],[1200]*3,[1,1,2],names=['order_1'],scope=SCOPE)
    def test_stage_requires_anomaly_and_preserves_core_composition(self):
        fs=16000; t=np.arange(fs*2)/fs; a=np.sin(2*np.pi*20*t)+.1*np.sin(2*np.pi*40*t)
        names,x=fault_features(a,fs,1200)
        p=fit_fault_discriminator(np.vstack([x,x+.01,x+3,x+3.01,x-3,x-3.01]),['looseness']*2+['unbalance']*2+['misalignment']*2,[1200]*6,list(range(6)),names=names,scope=SCOPE)
        model=FaultDiscriminator(p)
        for anomaly in [False,True]:
            analyzer=VibrationAnalyzer(AnalysisConfig(sample_rate_hz=fs,window_seconds=2,rpm=1200,unit='g'),stages={'conditioned':lambda r:{'anomaly':anomaly},'fault':FaultDiscriminationStage(model)})
            result=analyzer.analyze(SignalBlock(a,fs,unit='g',rpm=1200,metadata={'asset_id':'rig','condition_id':'steady'}))
            expected=model.analyze(a,fs,1200,scope=SCOPE) if anomaly else {'status':'hold','label':None,'reason':'confirmed_anomaly_gate_required','operational_use':False}
            self.assertEqual(result.payload['fault'],expected)

if __name__=='__main__': unittest.main()
