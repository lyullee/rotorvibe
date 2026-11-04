"""Declared acquisition evidence. Software checks cannot certify sensor mounting."""
from dataclasses import dataclass,asdict
from datetime import date
from numbers import Real
import math


@dataclass(frozen=True)
class AcquisitionInfo:
    asset_id: str
    sensor_id: str
    sensor_installation_id: str
    calibration_id: str
    measured_on: str
    calibration_due: str
    channel_names: tuple[str,...]
    axes: tuple[str,...]
    sample_rate_hz: float
    unit: str
    sensor_band_hz: tuple[float,float]
    anti_alias_cutoff_hz: float
    rpm_source: str
    frame: str = 'housing'
    calibrated: bool = False
    mounting_verified: bool = False
    anti_alias_verified: bool = False

    def validate(self):
        for key in ('asset_id','sensor_id','sensor_installation_id','calibration_id','frame'):
            value=getattr(self,key)
            if not isinstance(value,str) or not value.strip(): raise ValueError(key+' required')
        if self.frame not in ('housing','structure','shaft_relative','shaft_absolute'): raise ValueError('Unknown frame')
        for key in ('calibrated','mounting_verified','anti_alias_verified'):
            if not isinstance(getattr(self,key),bool): raise ValueError(key+' must be bool')
        if self.unit not in ('g','m/s^2'): raise ValueError('Calibrated acceleration unit required')
        for key in ('sample_rate_hz','anti_alias_cutoff_hz'):
            value=getattr(self,key)
            if isinstance(value,bool) or not isinstance(value,Real) or not math.isfinite(value) or value<=0:
                raise ValueError(key+' must be finite and positive')
        if self.anti_alias_cutoff_hz>=self.sample_rate_hz/2: raise ValueError('Anti-alias cutoff must be below Nyquist')
        band=self.sensor_band_hz
        if len(band)!=2 or any(isinstance(x,bool) or not isinstance(x,Real) or not math.isfinite(x) for x in band) or not 0<=band[0]<band[1]:
            raise ValueError('Ordered finite sensor band required')
        if not self.channel_names or len(self.axes)!=len(self.channel_names) or len(set(self.channel_names))!=len(self.channel_names):
            raise ValueError('Unique channel names and one axis per channel required')
        if any(not isinstance(x,str) or not x.strip() for x in (*self.channel_names,*self.axes)): raise ValueError('Channel/axis names required')
        if self.rpm_source not in ('tachometer','encoder','controller_nominal','operator_nominal','unavailable'):
            raise ValueError('Explicit RPM provenance required')
        try:
            measured=date.fromisoformat(self.measured_on); due=date.fromisoformat(self.calibration_due)
        except (TypeError,ValueError) as exc: raise ValueError('ISO calibration/measurement dates required') from exc
        if measured>due: raise ValueError('Calibration expired at measurement date')
        return self

    def to_dict(self):
        value=asdict(self); value['channel_names']=list(self.channel_names); value['axes']=list(self.axes)
        value['sensor_band_hz']=list(self.sensor_band_hz)
        return value


def check_acquisition(result,*,required_band_hz=None,require_measured_rpm=False):
    """Check host declarations against actual result settings; never infer evidence."""
    base={'schema':'vibration.acquisition.v1','declared_evidence_only':True}
    if not result.valid: return dict(base,status='quality_hold',reason='invalid_samples',issues=['numeric_window_invalid'])
    source=result.metadata.get('source',{}); configuration=result.metadata.get('measurement',{})
    required=('unit','sample_rate_hz','velocity_low_hz','velocity_high_hz','envelope_low_hz','envelope_high_hz')
    if not isinstance(source,dict) or not isinstance(configuration,dict) or any(k not in configuration for k in required):
        return dict(base,status='hold',reason='acquisition_contract_invalid',issues=['measurement_metadata_required'])
    try:
        info=AcquisitionInfo(**source.get('acquisition',{})).validate()
    except (TypeError,ValueError,KeyError) as exc:
        return dict(base,status='hold',reason='acquisition_contract_invalid',issues=[str(exc)])
    issues=[]
    if source.get('asset_id')!=info.asset_id: issues.append('asset_identity_mismatch')
    if info.unit!=configuration.get('unit'): issues.append('unit_provenance_mismatch')
    if info.sample_rate_hz!=configuration.get('sample_rate_hz'): issues.append('sampling_rate_mismatch')
    if configuration.get('calibration_id') and configuration['calibration_id']!=info.calibration_id: issues.append('calibration_identity_mismatch')
    if tuple(info.channel_names)!=result.channels: issues.append('channel_order_mismatch')
    for name in ('calibrated','mounting_verified','anti_alias_verified'):
        if not getattr(info,name): issues.append(name+'_required')
    band=required_band_hz or (min(configuration['velocity_low_hz'],configuration['envelope_low_hz']),
                              max(configuration['velocity_high_hz'],configuration['envelope_high_hz']))
    if (len(band)!=2 or not all(isinstance(x,Real) and not isinstance(x,bool) and math.isfinite(x) for x in band)
        or not 0<band[0]<band[1]): raise ValueError('Positive ordered analysis band required')
    if info.sensor_band_hz[0]>band[0] or info.sensor_band_hz[1]<band[1] or info.anti_alias_cutoff_hz<band[1]:
        issues.append('sensor_or_acquisition_band_insufficient')
    if require_measured_rpm and (info.rpm_source not in ('encoder','tachometer') or result.rpm_trace is None):
        issues.append('measured_rpm_trace_required')
    if result.payload.get('rpm') is not None and info.rpm_source=='unavailable': issues.append('rpm_provenance_required')
    if result.rpm_trace is not None and info.rpm_source not in ('encoder','tachometer'): issues.append('measured_rpm_trace_required')
    return dict(base,status='accepted' if not issues else 'hold',reason='acquisition_accepted' if not issues else 'acquisition_evidence_incomplete',issues=issues)


class AcquisitionQualityStage:
    def __init__(self,*,required_band_hz=None,require_measured_rpm=False):
        if not isinstance(require_measured_rpm,bool): raise ValueError('require_measured_rpm must be bool')
        self.band=required_band_hz; self.measured_rpm=require_measured_rpm

    def __call__(self,result):
        return check_acquisition(result,required_band_hz=self.band,require_measured_rpm=self.measured_rpm)
