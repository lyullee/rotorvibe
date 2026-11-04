# User-declared healthy data fit a robust reference; the code cannot certify health.
# Overlapping windows are correlated, and profile scores are relative distances.

from datetime import datetime, timezone
import numpy as np

def utcnow():
    return datetime.now(timezone.utc).isoformat()


class Baseline:
    def __init__(self):
        self.collecting=False; self.samples=[]; self.profile=None; self.target=60

    def begin(self, name, config, target=60):
        self.name=name; self.signature=config.signature(); self.condition=config.condition
        self.target=max(20,min(5000,int(target))); self.samples=[]; self.collecting=True
        self.profile=None; self.rpms=[]

    def observe(self, vector, names, config, rpm):
        if self.collecting:
            if self.signature!=config.signature() or self.condition!=config.condition:
                self.collecting=False
                return {'status':'cancelled','reason':'설정 또는 운전조건이 변경되어 수집을 취소했습니다.'}
            self.samples.append(vector.copy())
            if rpm: self.rpms.append(float(rpm))
            if len(self.samples)>=self.target:
                a=np.vstack(self.samples); center=np.median(a,axis=0)
                scale=np.maximum(np.median(np.abs(a-center),axis=0)*1.4826,0.15)
                self.profile={'name':self.name,'created':utcnow(),'signature':self.signature,
                              'condition':self.condition,'feature_names':names,'center':center.tolist(),
                              'scale':scale.tolist(),'rpm_range':[min(self.rpms),max(self.rpms)] if self.rpms else None,
                              'summary':{'windows':len(a),'condition':self.condition,'unit':config.unit},
                              'limitation':'사용자가 정상으로 지정한 구간입니다. 겹치는 분석 창은 독립 실험이 아닙니다.'}
                self.collecting=False
                return {'status':'collected','profile':self.profile,'windows':len(a)}
            return {'status':'collecting','windows':len(self.samples),'target':self.target}
        if self.profile is None:
            return {'status':'missing','score':None,'reason':'운전조건별 정상 기준을 수집하거나 불러오세요.'}
        p=self.profile
        if p['signature']!=config.signature() or p['condition']!=config.condition or p['feature_names']!=names:
            return {'status':'incompatible','score':None,'reason':'정상 기준의 분석 설정/운전조건이 현재와 다릅니다.'}
        if p.get('rpm_range'):
            lo,hi=p['rpm_range']; tolerance=max(5,0.05*(lo+hi)/2)
            if rpm is None or not lo-tolerance<=rpm<=hi+tolerance:
                return {'status':'outside_condition','score':None,'reason':'정상 기준에서 관측한 RPM 범위 밖입니다.'}
        z=np.abs((vector-np.asarray(p['center']))/np.asarray(p['scale']))
        indices=np.argsort(z)[-5:][::-1]
        return {'status':'ready','score':float(np.sqrt(np.mean(np.minimum(z,1000)**2))),
                'name':p['name'],'contributions':[{'feature':names[i],'robust_z':float(z[i])} for i in indices],
                'note':'정상 기준 대비 상대 점수이며 고장 확률이 아닙니다.'}


class BaselineStage:
    """Opt-in normal collection/scoring with explicit profile import/export."""
    def __init__(self, config, *, profile=None):
        import copy
        self.config=copy.deepcopy(config).validate()
        self.baseline=Baseline(); self.baseline.profile=copy.deepcopy(profile)
        self.source_scope=copy.deepcopy(profile.get('source_scope')) if profile else None

    def begin(self, name='normal', windows=60):
        self.baseline.begin(name,self.config,windows)
        self.source_scope=None

    def export_profile(self):
        import copy
        return copy.deepcopy(self.baseline.profile)

    def __call__(self, result):
        from .config import AnalysisConfig
        if not result.valid: return {'status':'quality_hold','score':None}
        from .contracts import json_value
        source=result.metadata.get('source',{})
        scope=json_value({k:source[k] for k in ('asset_id','asset','sensor_id','sensor_ids','condition_id','measurement_frame') if k in source})
        if self.source_scope is None:
            if self.baseline.profile is not None and scope:
                return {'status':'incompatible','score':None,'reason':'Saved baseline has no source identity for this asset/sensor.'}
            self.source_scope=scope
        if scope!=self.source_scope:
            self.baseline.collecting=False
            return {'status':'incompatible','score':None,'reason':'Asset, sensor or operating-condition identity differs from baseline.'}
        config=AnalysisConfig.create(result.metadata['measurement'])
        response=self.baseline.observe(result.features,list(result.feature_names),config,result.payload.get('rpm'))
        if self.baseline.profile is not None: self.baseline.profile['source_scope']=self.source_scope
        return response


