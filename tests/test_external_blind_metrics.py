import unittest
import numpy as np
from scripts.external_blind_metrics import shadow_gate,shadow_fault,summarize
from vibration.fault_discrimination import fit_fault_discriminator,FaultDiscriminator

class ExternalMetricChecks(unittest.TestCase):
    def test_all_holds_are_not_successful_normal_validation(self):
        items=[dict(recording='healthy',truth='normal',p=dict(status='hold',label=None)),dict(recording='fault',truth='looseness',p=dict(status='hold',label=None))]
        r=summarize(items,'p')
        self.assertEqual(r['normal_false_anomaly_fraction_all_windows'],0)
        self.assertIsNone(r['normal_false_anomaly_fraction_decided'])
        self.assertEqual(r['normal_acceptance_rate'],0); self.assertEqual(r['fault_type_accuracy_holds_wrong'],0)
    def test_window_and_recording_alarm_counts_differ(self):
        items=[dict(recording='healthy',truth='normal',p=dict(status='normal',label='normal',anomaly=False)),dict(recording='healthy',truth='normal',p=dict(status='anomaly',label=None,anomaly=True))]
        r=summarize(items,'p'); self.assertEqual(r['normal_false_anomaly_fraction_all_windows'],.5)
        self.assertEqual(r['normal_recordings_with_any_false_anomaly'],1); self.assertEqual(r['normal_original_recordings'],1)
    def test_analytic_normal_gate_and_missing_speed(self):
        p=dict(references=[dict(rpm=1200,center=[1.,2.],scale=[2.,4.])],interpolate=False,max_rpm_gap=800,interpolation_uncertainty=1,selected_indices=[0,1],normal_accept_limit=1,anomaly_limit=2)
        self.assertEqual(shadow_gate([1.,2.],1200,p)['status'],'normal')
        self.assertAlmostEqual(shadow_gate([7.,14.],1200,p)['normal_score'],3.)
        self.assertEqual(shadow_gate([7.,14.],1000,p)['status'],'hold')
    def test_frozen_fault_math_matches_scoped_model(self):
        scope=dict(asset_id='rig',condition_id='steady',unit='g')
        p=fit_fault_discriminator([[0,0],[.1,0],[3,0],[3.1,0],[0,3],[0,3.1]],['looseness']*2+['unbalance']*2+['misalignment']*2,[1200]*6,list(range(6)),names=['order_1','order_2'],scope=scope)
        model=FaultDiscriminator(p)
        for x in [[0,0],[3,0],[0,3],[100,100]]:
            a=model.predict(x,1200,scope=scope); b=shadow_fault(x,1200,p)
            self.assertEqual((a['label'],a['status']),(b['label'],b['status']))

if __name__=='__main__': unittest.main()
