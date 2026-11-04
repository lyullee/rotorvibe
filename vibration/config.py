from dataclasses import dataclass, asdict, fields
import math
from numbers import Real, Integral


@dataclass
class AnalysisConfig:
    sample_rate_hz: float = 12000
    channels: int = 1
    channel: int = 0
    window_seconds: float = 1
    hop_seconds: float = 0.25
    unit: str = 'unknown'
    input_representation: str = 'physical'
    sensitivity_mv_per_g: list | None = None
    conditioner_gain: float = 1
    bias_voltage_v: float = 0
    calibration_id: str = ''
    rpm: float | None = None
    bearing_id: str | None = None
    condition: str = '기본 운전조건'
    load: float | None = None
    window: str = 'hann'
    envelope_low_hz: float = 500
    envelope_high_hz: float = 5000
    velocity_low_hz: float = 10
    velocity_high_hz: float = 1000
    peak_tolerance_ratio: float = 0.03
    warning_score: float = 3
    danger_score: float = 6
    persistence_seconds: float = 2
    release_seconds: float = 3
    rms_warning: float | None = None
    rms_danger: float | None = None
    clip_abs: float | None = None
    model_enabled: bool = False
    order_tracking: bool = True

    def validate(self):
        numeric=['sample_rate_hz','window_seconds','hop_seconds','conditioner_gain','bias_voltage_v',
                 'envelope_low_hz','envelope_high_hz','velocity_low_hz','velocity_high_hz',
                 'peak_tolerance_ratio','warning_score','danger_score','persistence_seconds','release_seconds']
        optional=['rpm','load','rms_warning','rms_danger','clip_abs']
        for name in numeric+optional:
            v=getattr(self,name)
            if v is None and name in optional: continue
            if isinstance(v,bool) or not isinstance(v,Real) or not math.isfinite(v):
                raise ValueError(f'{name}: 유한한 숫자가 필요합니다.')
            setattr(self,name,float(v))
        for name in ['channels','channel']:
            v=getattr(self,name)
            if isinstance(v,bool) or not isinstance(v,Integral):
                raise ValueError(f'{name}: 정수가 필요합니다.')
            setattr(self,name,int(v))
        for name in ['model_enabled','order_tracking']:
            if not isinstance(getattr(self,name),bool):
                raise ValueError(f'{name}는 true/false여야 합니다.')
        for f in fields(self):
            v = getattr(self, f.name)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and not math.isfinite(v):
                raise ValueError(f'{f.name}: 유한한 값이 필요합니다.')
        if not 100 <= self.sample_rate_hz <= 200000:
            raise ValueError('샘플링률 범위는 100~200000 Hz입니다.')
        if not isinstance(self.channels, int) or not 1 <= self.channels <= 16:
            raise ValueError('채널 수는 1~16 정수여야 합니다.')
        if not isinstance(self.channel, int) or not 0 <= self.channel < self.channels:
            raise ValueError('분석 채널이 채널 수 범위 밖입니다.')
        n = round(self.sample_rate_hz * self.window_seconds)
        if not 256 <= n <= 2_000_000 or not 0.02 <= self.hop_seconds <= self.window_seconds:
            raise ValueError('분석 창은 256~2000000 샘플, 갱신 주기는 0.02초 이상이며 창보다 작아야 합니다.')
        if n * self.channels > 8_000_000:
            raise ValueError('다채널 분석 창의 메모리 한도를 초과했습니다.')
        for lo, hi, label in [(self.envelope_low_hz, self.envelope_high_hz, '엔벨로프'),
                              (self.velocity_low_hz, self.velocity_high_hz, '속도 적분')]:
            if not 0 < lo < hi < self.sample_rate_hz / 2:
                raise ValueError(f'{label} 대역은 0 Hz와 Nyquist 사이여야 합니다.')
        if self.unit not in ['unknown', 'g', 'm/s^2']:
            raise ValueError('지원 진동 단위는 unknown, g, m/s^2입니다.')
        if self.input_representation not in ['physical','volts']:
            raise ValueError('입력 표현은 physical 또는 volts입니다.')
        if self.conditioner_gain<=0:
            raise ValueError('컨디셔너 이득은 양수여야 합니다.')
        if self.sensitivity_mv_per_g is not None:
            s=self.sensitivity_mv_per_g
            if not isinstance(s,list) or len(s) not in [1,self.channels] or not all(not isinstance(v,bool) and isinstance(v,Real) and math.isfinite(v) and v>0 for v in s):
                raise ValueError('감도는 양수 배열이며, 공통 값 1개 또는 채널 수만큼 필요합니다.')
            self.sensitivity_mv_per_g=[float(v) for v in s]
        if self.input_representation=='volts' and (not self.sensitivity_mv_per_g or self.unit=='unknown'):
            raise ValueError('전압 입력에는 교정 감도와 변환 후 단위 g 또는 m/s^2가 필요합니다.')
        if self.window not in ['hann', 'hamming', 'boxcar']:
            raise ValueError('지원하지 않는 FFT 창입니다.')
        if self.rpm is not None and not 1e-6<=self.rpm<=1e9:
            raise ValueError('RPM 지원 범위는 1e-6~1e9입니다.')
        if not 0 < self.peak_tolerance_ratio <= 0.2:
            raise ValueError('주파수 허용오차 비율은 0~0.2 사이여야 합니다.')
        if not 0 < self.warning_score < self.danger_score:
            raise ValueError('이상 점수 경보 기준의 순서가 올바르지 않습니다.')
        if self.persistence_seconds < 0 or self.release_seconds < 0:
            raise ValueError('경보 지속시간은 음수일 수 없습니다.')
        for v in [self.rms_warning, self.rms_danger, self.clip_abs]:
            if v is not None and v <= 0:
                raise ValueError('진폭 기준은 양수여야 합니다.')
        if self.rms_warning and self.rms_danger and self.rms_warning >= self.rms_danger:
            raise ValueError('RMS 주의값은 위험값보다 작아야 합니다.')
        if not isinstance(self.condition, str) or not 1 <= len(self.condition) <= 120:
            raise ValueError('운전조건 이름은 1~120자여야 합니다.')
        return self

    @classmethod
    def create(cls, values=None):
        values = values or {}
        allowed = {f.name for f in fields(cls)}
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f'알 수 없는 설정: {", ".join(sorted(unknown))}')
        return cls(**values).validate()

    def to_dict(self):
        return asdict(self)

    def signature(self):
        names = ['sample_rate_hz','channels','channel','window_seconds','unit','window',
                 'envelope_low_hz','envelope_high_hz','velocity_low_hz','velocity_high_hz',
                 'input_representation','sensitivity_mv_per_g','conditioner_gain','bias_voltage_v','calibration_id','load']
        return {**{k: getattr(self, k) for k in names},'feature_schema':'vibration.features.v2'}

    def for_source(self, fs, channels, duration, unit, rpm, bearing_id):
        d = self.to_dict()
        d.update(sample_rate_hz=float(fs), channels=int(channels), channel=min(self.channel, channels-1),
                 unit=unit, rpm=rpm, bearing_id=bearing_id,input_representation='physical',sensitivity_mv_per_g=None,
                 conditioner_gain=1,bias_voltage_v=0,calibration_id='')
        d['window_seconds'] = max(256/fs, min(self.window_seconds, duration))
        d['hop_seconds'] = max(0.02, min(self.hop_seconds, d['window_seconds']))
        ny = fs/2
        d['envelope_low_hz'] = min(self.envelope_low_hz, ny*0.2)
        d['envelope_high_hz'] = min(self.envelope_high_hz, ny*0.9)
        d['velocity_low_hz'] = min(self.velocity_low_hz, ny*0.05)
        d['velocity_high_hz'] = min(self.velocity_high_hz, ny*0.8)
        d.update(rms_warning=None, rms_danger=None, clip_abs=None, model_enabled=False)
        return self.create(d)

