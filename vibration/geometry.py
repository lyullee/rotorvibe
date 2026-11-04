# Ideal single-row no-slip bearing kinematics; not a manufacturer dimensions database.
# Use one common diameter unit and an independently supplied positive shaft RPM.
# The packing inequality is a necessary geometric check, not bearing design approval.

from dataclasses import dataclass
import math
from numbers import Real, Integral

@dataclass(frozen=True)
class BearingGeometry:
    rolling_elements: int
    rolling_diameter: float
    pitch_diameter: float
    contact_angle_deg: float = 0

    def validate(self):
        if (isinstance(self.rolling_elements,bool) or not isinstance(self.rolling_elements,Integral) or self.rolling_elements<2 or
            not all(not isinstance(x,bool) and isinstance(x,Real) and math.isfinite(x)
                    for x in (self.rolling_diameter,self.pitch_diameter,self.contact_angle_deg)) or
            not 0<self.rolling_diameter<self.pitch_diameter or not 0<=self.contact_angle_deg<90):
            raise ValueError('Invalid single-row bearing geometry; count >=2, common diameter unit and angle 0..90 required.')
        # Adjacent element centres on one pitch circle are D*sin(pi/N) apart.
        # This is a necessary clearance constraint, not a full bearing design check.
        if self.rolling_diameter/self.pitch_diameter>math.sin(math.pi/self.rolling_elements)*(1+1e-12):
            raise ValueError('Rolling elements overlap on the specified single-row pitch circle.')
        return self

    def frequencies(self, rpm):
        self.validate()
        if isinstance(rpm,bool) or not isinstance(rpm,Real) or not math.isfinite(rpm) or not 1e-6<=rpm<=1e9:
            raise ValueError('RPM must be finite within 1e-6..1e9.')
        r=self.rolling_diameter/self.pitch_diameter; q=r*math.cos(math.radians(self.contact_angle_deg)); f=rpm/60
        bsf=(1-q*q)/(2*r)*f
        return {'BPFI':self.rolling_elements*(1+q)*f/2,'BPFO':self.rolling_elements*(1-q)*f/2,
                'FTF':(1-q)*f/2,'BSF':bsf,'2BSF':2*bsf}

class BearingMap:
    def __init__(self, geometries): self.geometries=dict(geometries)
    def frequencies(self, id, rpm): return self.geometries[id].frequencies(rpm)
