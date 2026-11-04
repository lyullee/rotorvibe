"""Measurement contracts for edition-pinned, per-location ISO evaluations."""
from dataclasses import dataclass, field, asdict
from numbers import Real,Integral
import math


@dataclass(frozen=True)
class MachineContext:
    asset_id: str
    machine: str
    power_kw: float | None = None
    rated_rpm: float | None = None
    operating_rpm: float | None = None
    max_continuous_rpm: float | None = None
    bearing_type: str | None = None  # fluid_film / rolling
    support: str | None = None      # rigid / flexible, in measurement direction
    shaft_height_mm: float | None = None
    operating_state: str = 'unknown'  # steady / transient / stopped
    location: str = 'unknown'
    condition_id: str = 'unknown'
    thrust_bearing: bool = False
    land_based: bool | None = None
    aero_derivative: bool | None = None
    coupled: bool | None = None
    category: str | None = None     # pump I / II
    impeller_blades: int | None = None
    nominal_clearance_um: float | None = None
    orientation: str | None = None
    reciprocating_class: int | None = None
    hydro_group: int | None = None
    hydro_type: str | None = None   # francis / pelton / kaplan / bulb / pump_turbine / pump
    bearing_position: str | None = None  # T / P / GE-DE / GE-NDE
    runner_blades: int | None = None
    guide_vanes: int | None = None
    load_fraction: float | None = None
    journal_diameter_mm: float | None = None
    smooth_pelton_operation: bool | None = None
    hydraulic_normal_operation: bool | None = None
    pumping_at_rated_capacity: bool | None = None
    geared: bool | None = None
    offshore: bool | None = None
    icing: bool | None = None
    purpose: str = 'monitoring'  # monitoring / site_acceptance / factory_acceptance
    flow_region: str | None = None  # preferred / allowable
    support_design_confirmed: bool | None = None  # hydro arrangement matches clause 4
    hydro_extended_housing_band: bool = False  # Kaplan/bulb Table 1 note a
    exclusions: tuple[str, ...] = ()

    def validate(self):
        if not all(isinstance(getattr(self,n),str) and getattr(self,n) for n in ('asset_id','machine','condition_id','location')):
            raise ValueError('Nonempty asset, machine, condition and location strings required.')
        if self.purpose not in ('monitoring','site_acceptance','factory_acceptance'):
            raise ValueError('Unknown assessment purpose.')
        if self.operating_state not in ('unknown','steady','production','transient','stopped'):
            raise ValueError('Unknown operating state.')
        if not isinstance(self.exclusions,(tuple,list)) or any(not isinstance(x,str) or not x for x in self.exclusions):
            raise ValueError('Exclusions must be a sequence of nonempty strings.')
        for name in ('thrust_bearing','land_based','aero_derivative','coupled','smooth_pelton_operation',
                     'hydraulic_normal_operation','pumping_at_rated_capacity','geared','offshore','icing','support_design_confirmed','hydro_extended_housing_band'):
            v=getattr(self,name)
            if v is not None and not isinstance(v,bool): raise ValueError(f'{name} must be explicitly bool or None.')
        for name in ('power_kw','rated_rpm','operating_rpm','max_continuous_rpm','shaft_height_mm',
                     'nominal_clearance_um','journal_diameter_mm'):
            v=getattr(self,name)
            if v is not None and (isinstance(v,bool) or not isinstance(v,Real) or not math.isfinite(v) or v<=0):
                raise ValueError(f'{name} must be a finite positive number.')
        if self.load_fraction is not None and (isinstance(self.load_fraction,bool) or not isinstance(self.load_fraction,Real) or not math.isfinite(self.load_fraction) or not 0<=self.load_fraction<=1):
            raise ValueError('load_fraction must be within 0..1.')
        for name in ('impeller_blades','runner_blades','guide_vanes','reciprocating_class','hydro_group'):
            v=getattr(self,name)
            if v is not None and (isinstance(v,bool) or not isinstance(v,int) or v<1): raise ValueError(f'{name} must be a positive integer.')
        return self


@dataclass(frozen=True)
class Measurement:
    value: float
    quantity: str
    unit: str
    statistic: str
    frame: str  # housing / structure / shaft_relative / shaft_absolute
    band_hz: tuple[float,float]
    duration_s: float
    axis: str
    point_id: str
    start_s: float = 0
    clock_id: str = 'measurement_clock'
    calibrated: bool = False
    acquisition_verified: bool = False
    valid: bool = True
    averaging: str = 'single_window'
    observations: int = 1
    revolutions_per_observation: float | None = None
    order: float | None = None
    filter_bandwidth_hz: float | None = None
    provenance: dict = field(default_factory=dict)

    def validate(self):
        if not all(isinstance(getattr(self,n),bool) for n in ('valid','calibrated','acquisition_verified')): raise ValueError('Measurement validity/qualification flags must be bool.')
        for name in ('value','duration_s','start_s'):
            v=getattr(self,name)
            if isinstance(v,bool) or not isinstance(v,Real) or not math.isfinite(v): raise ValueError(f'{name} must be finite.')
        if self.value<0 or self.duration_s<=0: raise ValueError('Magnitude >=0 and duration >0 required.')
        if isinstance(self.observations,bool) or not isinstance(self.observations,Integral) or self.observations<1:
            raise ValueError('observations must be a positive integer.')
        for name in ('revolutions_per_observation','order','filter_bandwidth_hz'):
            v=getattr(self,name)
            if v is not None and (isinstance(v,bool) or not isinstance(v,Real) or not math.isfinite(v) or v<=0):
                raise ValueError(f'{name} must be a finite positive number.')
        if self.averaging not in ('single_window','energy_equivalent','mean_peak_to_peak'):
            raise ValueError('Unknown averaging method.')
        if len(self.band_hz)!=2 or not all(isinstance(x,Real) and math.isfinite(x) for x in self.band_hz) or not 0<self.band_hz[0]<self.band_hz[1]:
            raise ValueError('Positive ordered measurement band required.')
        units={'acceleration':{'m/s^2','g'},'velocity':{'m/s','mm/s'},'displacement':{'m','mm','um'}}
        if self.quantity not in units or self.unit not in units[self.quantity]: raise ValueError('Quantity/unit mismatch.')
        if self.statistic not in ('rms','peak_to_peak','smax'): raise ValueError('Unsupported statistic; no automatic RMS/peak conversion.')
        if self.frame not in ('housing','structure','shaft_relative','shaft_absolute'): raise ValueError('Explicit measurement frame required.')
        if not all(isinstance(getattr(self,n),str) and getattr(self,n) for n in ('point_id','axis','clock_id')): raise ValueError('Point, axis and clock strings required.')
        return self

    def canonical_value(self):
        self.validate()
        factors={'m/s^2':1,'g':9.80665,'mm/s':1,'m/s':1000,'um':1,'mm':1000,'m':1e6}
        value=self.value*factors[self.unit]
        if not math.isfinite(value): raise ValueError('Unit conversion overflow.')
        return value


@dataclass(frozen=True)
class Rule:
    standard: str
    key: str
    quantity: str
    statistic: str
    frames: tuple[str,...]
    limits: tuple[float,...]
    band_hz: tuple[float,float]
    source_page: int
    source_clause: str
    zones: tuple[str,...] = ('A','B','C','D')
    authority: str = 'user_supplied_limits'
    minimum_duration_s: float = 0
    minimum_upper_band: bool = False
    notes: tuple[str,...] = ()

    def validate(self):
        if not all(isinstance(getattr(self,n),str) and getattr(self,n) for n in ('standard','key','source_clause','authority')):
            raise ValueError('Rule identity/source strings required.')
        if self.quantity not in ('acceleration','velocity','displacement') or self.statistic not in ('rms','peak_to_peak','smax'):
            raise ValueError('Rule quantity/statistic invalid.')
        if not self.frames or any(x not in ('housing','structure','shaft_relative','shaft_absolute') for x in self.frames):
            raise ValueError('Rule reference frame required.')
        if (not self.limits or not all(not isinstance(x,bool) and isinstance(x,Real) and math.isfinite(x) and x>0 for x in self.limits)
            or any(a>=b for a,b in zip(self.limits,self.limits[1:]))): raise ValueError('Finite positive increasing limits required.')
        if len(self.zones)!=len(self.limits)+1 or len(set(self.zones))!=len(self.zones) or any(not isinstance(x,str) or not x for x in self.zones):
            raise ValueError('Distinct ordered zone names must match limits.')
        if (len(self.band_hz)!=2 or not all(not isinstance(x,bool) and isinstance(x,Real) and math.isfinite(x) for x in self.band_hz)
            or not 0<self.band_hz[0]<self.band_hz[1]): raise ValueError('Rule requires a finite ordered frequency band.')
        if isinstance(self.minimum_duration_s,bool) or not isinstance(self.minimum_duration_s,Real) or not math.isfinite(self.minimum_duration_s) or self.minimum_duration_s<0:
            raise ValueError('Rule minimum duration must be finite and nonnegative.')
        if isinstance(self.source_page,bool) or not isinstance(self.source_page,Integral) or self.source_page<0 or not isinstance(self.minimum_upper_band,bool):
            raise ValueError('Rule page/band policy invalid.')
        return self

    def to_dict(self): return asdict(self)


class NotApplicable(ValueError): pass
class MissingInformation(ValueError): pass

def require(context,*names):
    missing=[n for n in names if getattr(context,n) is None or getattr(context,n)=='unknown']
    if missing: raise MissingInformation('Required context: '+', '.join(missing))

def check(condition,message):
    if not condition: raise NotApplicable(message)

def structural_axis(context,measurement):
    check(measurement.axis=='radial' or (measurement.axis=='axial' and context.thrust_bearing),
          'Housing criteria require radial direction, or axial at a thrust bearing.')
