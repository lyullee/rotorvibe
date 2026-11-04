"""Artificial rule examples, intentionally unrelated to any standard's tables."""
import unittest
from dataclasses import replace
from vibration.iso import MachineContext,Measurement,Rule,evaluate,available_standards

class PublicRuleChecks(unittest.TestCase):
    def setUp(self):
        self.context=MachineContext('demo','motor',operating_state='steady',condition_id='rated',location='housing')
        self.m=Measurement(2.0,'velocity','mm/s','rms','housing',(12.,850.),2.,'radial','DE',calibrated=True,acquisition_verified=True)
        self.rule=Rule('example-only','invented','velocity','rms',('housing',),(1.1,2.2,3.3),(12.,850.),0,'invented demonstration values')
    def test_no_normative_profiles_shipped(self): self.assertEqual(available_standards(),())
    def test_absent_rule_never_returns_zone(self): self.assertIsNone(evaluate('10816-3:2009',self.context,self.m)['zone'])
    def test_caller_rule_and_units(self):
        a=evaluate('example-only',self.context,self.m,custom_rule=self.rule)
        b=evaluate('example-only',self.context,replace(self.m,value=.002,unit='m/s'),custom_rule=self.rule)
        self.assertEqual(a['zone'],'B'); self.assertEqual(a['value'],b['value'])
    def test_exact_boundary_stays_lower(self):
        self.assertEqual(evaluate('example-only',self.context,replace(self.m,value=2.2),custom_rule=self.rule)['zone'],'B')
    def test_unqualified_measurement_holds(self):
        self.assertIsNone(evaluate('example-only',self.context,replace(self.m,calibrated=False),custom_rule=self.rule)['zone'])
    def test_statistic_mismatch_never_converts(self):
        self.assertIsNone(evaluate('example-only',self.context,replace(self.m,statistic='peak_to_peak'),custom_rule=self.rule)['zone'])
    def test_facade_retains_core_identity(self):
        from rotorvibe import VibrationAnalyzer
        from vibration import VibrationAnalyzer as Original
        self.assertIs(VibrationAnalyzer,Original)
