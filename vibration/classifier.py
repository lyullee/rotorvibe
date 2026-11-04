# Experimental diagonal-Gaussian baseline with class-dependent log variance term.
# Feature identity and scale are part of the model contract; scores are not field risks.

"""Pure NumPy Gaussian classifier: class-dependent variance needs log determinant."""
import copy
import numpy as np

FEATURE_SCHEMA='vibration.features.v2'
SUPPORTED_SCHEMAS=(FEATURE_SCHEMA,'vibration.rotor_features.v1','vibration.rotor_normal_changes.v1')
ALGORITHM='standardized_diagonal_gaussian_log_density_v3'


def fit_gaussian(x,y,groups,*,variance_floor=.25,feature_schema=FEATURE_SCHEMA):
    if feature_schema not in SUPPORTED_SCHEMAS: raise ValueError('Unsupported feature schema.')
    x=np.asarray(x,dtype=float); y=np.asarray(y); groups=np.asarray(groups)
    if x.ndim!=2 or not len(x) or not x.shape[1] or not np.isfinite(x).all() or np.max(np.abs(x))>1e150:
        raise ValueError('Invalid or numerically out-of-range training features.')
    if y.ndim!=1 or groups.ndim!=1 or len(y)!=len(x) or len(groups)!=len(x): raise ValueError('Training lengths differ.')
    if isinstance(variance_floor,(bool,np.bool_)) or not np.isfinite(variance_floor) or variance_floor<=0: raise ValueError('Variance floor must be positive.')
    weights=np.zeros(len(x))
    for group in set(groups.tolist()):
        mask=groups==group
        if len(set(y[mask].tolist()))!=1: raise ValueError('A trial must have one label.')
        weights[mask]=1/mask.sum()
    center=np.average(x,axis=0,weights=weights)
    scale=np.maximum(np.sqrt(np.average((x-center)**2,axis=0,weights=weights)),.1)
    z=(x-center)/scale; classes=sorted(set(y.tolist())); means=[]; variances=[]; limits=[]
    if len(classes)<2: raise ValueError('At least two classes are required.')
    for label in classes:
        mask=y==label; c=z[mask]; w=weights[mask]; mu=np.average(c,axis=0,weights=w)
        var=np.maximum(np.average((c-mu)**2,axis=0,weights=w),variance_floor)
        distances=np.sqrt(np.mean((c-mu)**2/var,axis=1))
        means.append(mu.tolist()); variances.append(var.tolist())
        limits.append(float(max(2,np.quantile(distances,.995)*1.25)))
    return {'algorithm':ALGORITHM,'feature_schema':feature_schema,'center':center.tolist(),'scale':scale.tolist(),
            'centroids':means,'variances':variances,'classes':classes,'distance_limits':limits,
            'variance_floor':float(variance_floor),'training_trials':sorted(set(groups.tolist())),
            'prior':'uniform classes; equal total weight per physical training trial'}


class GaussianClassifier:
    """Composable immutable snapshot. Relative matches are not calibrated probabilities."""
    def __init__(self,profile):
        if profile.get('algorithm')!=ALGORITHM or profile.get('feature_schema') not in SUPPORTED_SCHEMAS:
            raise ValueError('Legacy classifier requires retraining: Gaussian scoring formula changed.')
        self.profile=copy.deepcopy(profile)
        self.center=np.asarray(profile['center'],dtype=float); self.scale=np.asarray(profile['scale'],dtype=float)
        self.means=np.asarray(profile['centroids'],dtype=float); self.variances=np.asarray(profile['variances'],dtype=float)
        self.limits=np.asarray(profile['distance_limits'],dtype=float); self.classes=tuple(profile['classes'])
        if self.center.ndim!=1 or not len(self.center) or self.scale.shape!=self.center.shape or self.means.shape!=(len(self.classes),len(self.center)) or self.variances.shape!=self.means.shape or self.limits.shape!=(len(self.classes),):
            raise ValueError('Classifier profile dimensions differ.')
        if len(self.classes)<2 or len(set(self.classes))!=len(self.classes): raise ValueError('Invalid classes.')
        if not all(np.isfinite(a).all() for a in (self.center,self.scale,self.means,self.variances,self.limits)) or np.any(self.scale<=0) or np.any(self.variances<=0) or np.any(self.limits<=0):
            raise ValueError('Classifier profile must be finite with positive scales/variances/limits.')

    def scores(self,features):
        a=np.asarray(features,dtype=float); one=a.ndim==1
        if one: a=a[None,:]
        if a.ndim!=2 or a.shape[1:]!=self.center.shape or not np.isfinite(a).all():
            raise ValueError('Classifier requires finite features matching its schema.')
        with np.errstate(over='ignore',invalid='ignore'):
            z=(a-self.center)/self.scale
            squared=np.mean((z[:,None,:]-self.means)**2/self.variances,axis=2)
            costs=.5*(squared+np.mean(np.log(self.variances),axis=1))
        if not np.isfinite(costs).all(): raise ValueError('Classifier feature magnitude exceeds numeric range.')
        return (costs[0],np.sqrt(squared[0])) if one else (costs,np.sqrt(squared))

    def predict_many(self,features,*,reject_unknown=True):
        costs,distances=self.scores(features)
        if costs.ndim==1: costs=costs[None,:]; distances=distances[None,:]
        indices=costs.argmin(axis=1); labels=np.asarray(self.classes,dtype=object)[indices]
        if reject_unknown: labels[distances[np.arange(len(indices)),indices]>self.limits[indices]]='미확인 이상'
        return labels

    def predict(self,features):
        costs,distances=self.scores(features)
        if costs.ndim!=1: raise ValueError('predict requires one vector; use predict_many for batches.')
        index=int(costs.argmin()); known=bool(distances[index]<=self.limits[index])
        weights=np.exp(-(costs-costs.min())); weights/=weights.sum()
        return {'status':'known_candidate' if known else 'unknown','label':self.classes[index] if known else '미확인 이상',
            'relative_matches':[{'label':label,'weight':float(w),'distance':float(d),'negative_log_density_per_feature':float(c)}
                                for label,w,d,c in zip(self.classes,weights,distances,costs)],
            'model':self.profile.get('name','Gaussian classifier'),
            'validation_status':self.profile.get('summary',{}).get('status','trained_only_not_evaluated'),
            'operational_use':False,'note':'실험용 벤치 후보 분류. 상대 일치도는 교정된 확률이 아니며 현장 운전 판단용으로 검증되지 않았습니다.'}
