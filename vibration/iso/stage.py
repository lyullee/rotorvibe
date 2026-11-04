"""Raw-window integration of independently supplied engineering rules."""
from .measurements import measure_waveform
from .evaluation import evaluate
from .providers import resolve_document

class IsoStage:
    """Compatibility name for a user-rule stage, with no built-in ISO limits.

    Pass an explicit Rule. Its quantity, band and reference frame determine the
    numerical measurement. The host owns lawful rule sourcing and applicability.
    """
    def __init__(self,standard,context,*,custom_rule=None,rule_provider=None,point_id,axis='radial',calibrated=False,acquisition_verified=False):
        self.standard=standard; self.context=context; self.rule=custom_rule; self.point_id=point_id; self.axis=axis
        self.calibrated=calibrated; self.acquisition_verified=acquisition_verified
        if custom_rule is not None and rule_provider is not None: raise ValueError('Choose custom_rule or rule_provider.')
        self.provider=rule_provider
        if custom_rule is not None: custom_rule.validate()
    def __call__(self,result):
        raise RuntimeError('Use VibrationAnalyzer raw-window stage hook.')
    def analyze_window(self,result,values):
        if not result.valid: return dict(status='quality_hold',zone=None,whole_machine_compliance=False)
        if self.provider is not None:
            source=result.metadata.get('source',{})
            if (any(source.get(k)!=getattr(self.context,k) for k in ('asset_id','condition_id','location','operating_state'))
                or result.payload.get('rpm_variation_ratio',0)>.03
                or (self.context.operating_rpm is not None and result.payload.get('rpm')!=self.context.operating_rpm)):
                return dict(status='indeterminate',zone=None,reason='live_measurement_context_mismatch',whole_machine_compliance=False)
        document=resolve_document(self.provider,self.standard,self.context) if self.provider is not None else None
        rule=document.rule if document is not None else (self.rule if self.provider is None else None)
        if rule is None: return dict(status='indeterminate',zone=None,reason='reviewed_rule_scope_unavailable' if self.provider is not None else 'user_rule_required',whole_machine_compliance=False)
        if len(rule.frames)!=1: raise ValueError('Raw-window measurement requires one explicit rule frame.')
        if values.ndim==2 and values.shape[1]!=1: raise ValueError('Create one named measurement stage per channel.')
        config=result.metadata['measurement']; r=rule
        measurement=measure_waveform(values,sample_rate_hz=config['sample_rate_hz'],input_unit=config['unit'],
            quantity=r.quantity,statistic=r.statistic,frame=r.frames[0],band_hz=r.band_hz,point_id=self.point_id,axes=(self.axis,),
            calibrated=self.calibrated,acquisition_verified=self.acquisition_verified,start_s=result.start_time_s,clock_id=result.clock_id)[0]
        output=evaluate(self.standard,self.context,measurement,custom_rule=r)
        if document is not None: output['rule_provenance']=document.provenance()
        return output
