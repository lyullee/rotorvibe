# Optional profile selection and routing must preserve algorithm/schema/scope identity.
# No downloaded rig-specific model is automatically promoted to operational use.

import threading
import json
import uuid
import time
from collections import defaultdict
import numpy as np
from .dsp import channel_features
from .baseline import Baseline
from .storage import utcnow
from .classifier import fit_gaussian,GaussianClassifier,ALGORITHM
from .two_stage import TwoStageDiagnostic,ALGORITHM as TWO_STAGE_ALGORITHM
from .conditioned import ConditionedDiagnostic,ALGORITHM as CONDITIONED_ALGORITHM


class ModelRegistry:
    def __init__(self, storage, catalog):
        self.storage=storage; self.catalog=catalog; self.active=None
        self.lock=threading.RLock(); self.job={'status':'idle'}
        self.cancel_event=threading.Event(); self.training_thread=None; self._closed=False

    def load(self,name):
        p=self.storage.get('classifier',name)
        if p.get('algorithm')==CONDITIONED_ALGORITHM: ConditionedDiagnostic(p)
        elif p.get('algorithm')==TWO_STAGE_ALGORITHM: TwoStageDiagnostic(p)
        else: GaussianClassifier(p)
        with self.lock: self.active=p
        return p['summary']

    def use_two_stage(self,profile):
        model=TwoStageDiagnostic(profile)
        with self.lock:
            if self._closed: raise RuntimeError('Model registry is closed.')
            self.active=model.profile
        return self.active.get('summary',{'status':'experimental_two_stage','mode':profile['mode']})

    def use_conditioned(self,profile):
        model=ConditionedDiagnostic(profile)
        with self.lock:
            if self._closed: raise RuntimeError('Model registry is closed.')
            self.active=model.profile
        return self.active['summary']

    def classify_window(self,values,config,source,*,vector=None,channel_names=None,rpm=None,rpm_variation_ratio=0.):
        if not config.model_enabled: return {'status':'disabled'}
        with self.lock: p=self.active
        if p is not None and p.get('algorithm') in (TWO_STAGE_ALGORITHM,CONDITIONED_ALGORITHM):
            if not np.isfinite(rpm_variation_ratio) or rpm_variation_ratio>.03:
                return {'status':'hold','label':None,'reason':'variable_speed_requires_angle_domain_features','operational_use':False}
            scope={k:source.get(k) for k in ('asset_id','condition_id')}; scope['unit']=config.unit
            for key in ('calibration_id','sensor_installation_id'):
                if key in source: scope[key]=source[key]
            actual_rpm=rpm if rpm is not None else (source.get('rpm') if config.rpm is None else config.rpm)
            model=ConditionedDiagnostic(p) if p['algorithm']==CONDITIONED_ALGORITHM else TwoStageDiagnostic(p)
            return model.analyze(values,config.sample_rate_hz,actual_rpm,
                scope=scope,channel_names=channel_names if channel_names is not None else source.get('channel_names'))
        if vector is None: _,vector=channel_features(values,config.sample_rate_hz)
        return self.classify(vector,config,source)

    def classify(self, vector, config, source):
        if not config.model_enabled: return {'status':'disabled'}
        with self.lock: p=self.active
        if p is None: return {'status':'missing','reason':'학습 모델을 선택하세요.'}
        if p.get('algorithm') in (TWO_STAGE_ALGORITHM,CONDITIONED_ALGORITHM):
            return {'status':'hold','label':None,'reason':'two_stage_requires_raw_window','operational_use':False}
        if p.get('feature_schema')!='vibration.features.v2':
            return {'status':'incompatible','reason':'특징 계산식 버전이 달라 모델 재학습이 필요합니다.'}
        if source.get('dataset')!='Brito' or config.sample_rate_hz!=25000 or config.channels!=4 or round(config.window_seconds*25000)!=25000:
            return {'status':'outside_domain','reason':'현재 모델은 Brito 4채널·25 kHz·1초 창 전용입니다.'}
        if config.unit!='unknown': return {'status':'outside_domain','reason':'학습 데이터와 진폭 단위 설정이 다릅니다.'}
        vector=np.asarray(vector,dtype=float)
        if vector.ndim!=1 or vector.shape!=np.asarray(p['center']).shape or not np.isfinite(vector).all():
            raise ValueError('Classifier requires a finite vector matching the trained feature schema.')
        if p.get('algorithm')!=ALGORITHM:
            return {'status':'incompatible','reason':'분류 점수 계산식을 수정했습니다. 기존 모델을 재학습하세요.'}
        return GaussianClassifier(p).predict(vector)

    def train(self,name):
        with self.lock:
            if self._closed: raise RuntimeError('Model registry is closed.')
            if self.job.get('status')=='running': raise ValueError('이미 학습 작업이 실행 중입니다.')
            self.job={'status':'running','completed':0,'total':0,'started':utcnow()}
            self.cancel_event.clear()
            self.training_thread=threading.Thread(target=self._fit,args=(name,),daemon=True,name='vibration-model-fit')
            self.training_thread.start()
        return self.job.copy()

    def close(self):
        with self.lock:
            self._closed=True; self.cancel_event.set()
        if self.training_thread is not None: self.training_thread.join(timeout=10)
        if self.training_thread is not None and self.training_thread.is_alive(): raise RuntimeError('Model fitting did not stop within timeout.')

    def _fit(self,name):
        try:
            records=[r for r in self.catalog.rows if r['dataset']=='Brito' and
                     self.catalog.records[r['id']][2]['suggested_split']=='train']
            if not records: raise ValueError('학습용 Brito 기록이 없습니다.')
            self.job['total']=len(records)
            x=[]; y=[]; trial_ids=set(); feature_names=None
            for i,r in enumerate(records):
                if self.cancel_event.is_set():
                    with self.lock: self.job.update(status='cancelled',finished=utcnow())
                    return
                a,meta=self.catalog.load(r['id'])
                feature_names,v=channel_features(a,25000)
                x.append(v); y.append(self.catalog.records[r['id']][2]['fault'])
                trial_ids.add(self.catalog.records[r['id']][2]['trial_id'])
                self.job['completed']=i+1
            x=np.vstack(x)
            groups=[self.catalog.records[r['id']][2]['trial_id'] for r in records]
            p=fit_gaussian(x,y,groups,variance_floor=.25)
            classes=p['classes']
            p.update({'name':name,'created':utcnow(),'feature_names':feature_names,
               'summary':{'records':len(x),'trials':len(trial_ids),
               'dataset':'Brito','status':'trained_only_not_evaluated','classes':classes},
               'evaluation':'No validation/test records were used for fitting. Accuracy depends on the evaluated model snapshot; matches are not calibrated probabilities.'})
            if self.cancel_event.is_set():
                with self.lock: self.job.update(status='cancelled',finished=utcnow())
                return
            self.storage.save('classifier',name,p)
            with self.lock: self.job.update(status='complete',name=name,summary=p['summary'],finished=utcnow())
        except Exception as e:
            with self.lock: self.job.update(status='failed',error=str(e),finished=utcnow())


class LifeEstimator:
    """Experimental reference-life matching. Held-out full lives never enter the library."""
    def __init__(self,catalog):
        self.references=[]
        for id,row in catalog.lives.items():
            if row['role']!='training_complete_life': continue
            rms=np.asarray(row['nominal_rms_series'],dtype=float)
            base=np.maximum(np.median(rms[:20],axis=0),1e-12)
            hi=np.log(np.maximum(rms,1e-12)/base)
            smooth=np.vstack([np.mean(hi[max(0,i-4):i+1],axis=0) for i in range(len(hi))])
            self.references.append({'bearing':row['bearing'],'rpm':row['nominal_rpm'],
                                    'hi':smooth,'seconds_left':np.arange(len(hi)-1,-1,-1)*10})

    def estimate(self, source):
        if source.get('dataset')!='FEMTO':
            return {'status':'outside_domain','reason':'수명 추정은 현재 PRONOSTIA 관측 이력에 한정됩니다.'}
        prefix=source.get('rul_prefix')
        if not prefix:
            return {'status':'insufficient_history','reason':'첫 20개 관측 이후에 과거 구간으로 기준을 잡습니다.'}
        baseline=np.maximum(np.asarray(prefix['baseline_rms']),1e-12)
        recent=np.asarray(prefix['recent_rms'],dtype=float)
        query=np.mean(np.log(np.maximum(recent,1e-12)/baseline),axis=0)
        matches=[]
        for r in self.references:
            if r['bearing']==source['record_id'] or abs(r['rpm']-source['rpm'])>5: continue
            distance=np.sqrt(np.mean((r['hi']-query)**2,axis=1))
            # Earliest points cannot estimate life meaningfully before an observable change.
            distance[:20]=np.inf
            index=int(np.argmin(distance))
            matches.append({'reference_bearing':r['bearing'],'distance':float(distance[index]),
                            'remaining_seconds':int(r['seconds_left'][index])})
        if len(matches)<2: return {'status':'insufficient_references','reason':'동일 RPM의 다른 학습 수명 두 개 이상이 필요합니다.'}
        if float(np.max(query))<0.25:
            return {'status':'no_degradation_evidence','reason':'정상 수준과 구분되는 열화 증가가 부족해 시간 예측을 보류합니다.'}
        values=np.asarray([m['remaining_seconds'] for m in matches])
        return {'status':'experimental','remaining_seconds':float(np.median(values)),
                'reference_range_seconds':[float(values.min()),float(values.max())],'references':matches,
                'method':'같은 RPM의 학습 수명에서 초기 20관측 대비 log RMS 이력 유사도',
                'note':'범위는 참고 수명의 분산이며 검증된 신뢰구간이 아닙니다. 가속시험 종료까지의 벤치 추정입니다.'}
