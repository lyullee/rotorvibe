"""Bridges to the optional local supervised and reference-life modules."""

class ClassifierStage:
    """Registry injected by host; construction never starts training."""
    def __init__(self, registry): self.registry=registry

    def __call__(self,result):
        from .config import AnalysisConfig
        if not result.valid: return {'status':'quality_hold'}
        return self.registry.classify(result.features,
                                      AnalysisConfig.create(result.metadata['measurement']),
                                      result.metadata.get('source',{}))

    def analyze_window(self,result,values):
        from .config import AnalysisConfig
        if not result.valid: return {'status':'quality_hold'}
        method=getattr(self.registry,'classify_window',None)
        if not callable(method): return self(result)  # Existing feature-only injected registries.
        return method(values,AnalysisConfig.create(result.metadata['measurement']),
            result.metadata.get('source',{}),vector=result.features,channel_names=result.channels,
            rpm=result.payload.get('rpm'),rpm_variation_ratio=result.payload.get('rpm_variation_ratio',0.))


class LifeStage:
    """Source metadata must contain only observations available at window end."""
    def __init__(self, estimator): self.estimator=estimator

    def __call__(self,result):
        if not result.valid: return {'status':'quality_hold'}
        return self.estimator.estimate(result.metadata.get('source',{}))
