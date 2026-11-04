"""Analytic density checks, group weighting, schema migration and pipeline parity."""
import copy,json,unittest
from types import SimpleNamespace
import numpy as np
from vibration import AnalysisConfig,VibrationAnalyzer,SignalBlock,GaussianClassifier
from vibration.classifier import fit_gaussian,ALGORITHM,FEATURE_SCHEMA
from vibration.dsp import channel_features
from vibration.models import ModelRegistry
from vibration.stages import ClassifierStage


def profile(dimensions=1):
    return dict(algorithm=ALGORITHM,feature_schema=FEATURE_SCHEMA,center=[0.]*dimensions,scale=[1.]*dimensions,
                centroids=[[0.]*dimensions,[0.]*dimensions],variances=[[1.]*dimensions,[100.]*dimensions],
                classes=['narrow','broad'],distance_limits=[2.,2.],name='analytic')


class ClassifierChecks(unittest.TestCase):
    def test_gaussian_density_includes_log_determinant(self):
        model=GaussianClassifier(profile()); costs,distances=model.scores([1.])
        np.testing.assert_allclose(costs,[.5,.5*(.01+np.log(100))])
        self.assertEqual(int(distances.argmin()),1)  # The original bug picks broad.
        self.assertEqual(model.predict([1.])['label'],'narrow')

    def test_equal_variances_reduce_to_nearest_mean(self):
        p=profile(); p['centroids']=[[0.],[4.]]; p['variances']=[[1.],[1.]]
        self.assertEqual(GaussianClassifier(p).predict([3.])['label'],'broad')

    def test_unknown_is_counted_instead_of_forced_label(self):
        result=GaussianClassifier(profile()).predict([100.])
        self.assertEqual(result['status'],'unknown'); self.assertEqual(result['label'],'미확인 이상')
        self.assertFalse(result['operational_use'])

    def test_batch_and_scalar_scores_match(self):
        model=GaussianClassifier(profile()); a=np.array([[0.],[1.],[100.]])
        self.assertEqual(model.predict_many(a).tolist(),[model.predict(x)['label'] for x in a])

    def test_training_trial_weight_does_not_depend_on_duplicate_windows(self):
        x=np.array([[0.],[1.],[3.],[4.]]); y=np.array(['a','a','b','b']); groups=np.array([1,2,3,4])
        a=fit_gaussian(x,y,groups); rows=np.r_[np.arange(4),np.zeros(30,dtype=int)]
        b=fit_gaussian(x[rows],y[rows],groups[rows])
        for key in ('center','scale','centroids','variances'): np.testing.assert_allclose(a[key],b[key],atol=1e-14)

    def test_trial_cannot_have_mixed_labels(self):
        with self.assertRaises(ValueError): fit_gaussian([[0],[1]],['a','b'],[1,1])

    def test_invalid_profiles_and_features_rejected(self):
        for samples in ([[1e308],[0.]],np.empty((2,0))):
            with self.assertRaises(ValueError): fit_gaussian(samples,['a','b'],[1,2])
        for field in ('scale','variances','distance_limits'):
            p=profile(); p[field]=np.zeros_like(p[field]).tolist()
            with self.subTest(field=field),self.assertRaises(ValueError): GaussianClassifier(p)
        for vector in ([np.nan],[np.inf],[1e308],[1,2]):
            with self.subTest(vector=vector),self.assertRaises(ValueError): GaussianClassifier(profile()).predict(vector)

    def test_legacy_profile_requires_retraining(self):
        p=profile(); p['algorithm']='standardized_diagonal_gaussian_centroid'
        with self.assertRaisesRegex(ValueError,'retraining'): GaussianClassifier(p)

    def test_snapshot_and_json_roundtrip(self):
        p=profile(); model=GaussianClassifier(p); p['variances'][0][0]=1e9
        self.assertEqual(model.predict([1.]),GaussianClassifier(json.loads(json.dumps(model.profile))).predict([1.]))

    def test_signal_pipeline_registry_and_pure_api_match_without_label_input(self):
        t=np.arange(25000)/25000
        a=np.column_stack([np.sin(2*np.pi*(20+i)*t) for i in range(4)])
        names,features=channel_features(a,25000); p=profile(len(features)); p['center']=features.tolist()
        registry=ModelRegistry(None,None); registry.active=p
        config=AnalysisConfig(sample_rate_hz=25000,channels=4,model_enabled=True)
        analyzer=VibrationAnalyzer(config,stages={'classification':ClassifierStage(registry)})
        first=analyzer.analyze(SignalBlock(a,25000,metadata={'dataset':'Brito','fault':'wrong label'}))
        second=analyzer.analyze(SignalBlock(a,25000,metadata={'dataset':'Brito','fault':'different label','trial_id':999}))
        self.assertEqual(first.payload['classification'],second.payload['classification'])
        self.assertEqual(first.payload['classification'],GaussianClassifier(p).predict(features))
        self.assertEqual(registry.classify(features,config,{'dataset':'Other'})['status'],'outside_domain')

if __name__=='__main__': unittest.main()
