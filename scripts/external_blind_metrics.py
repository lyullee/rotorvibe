"""Offline evaluation only. Scope bypass is explicit; never a deployable adapter."""
import numpy as np
from vibration.conditioned import reference_at

def shadow_gate(feature_values,rpm,profile):
    """Identical frozen normal math, but intentionally NO asset/layout applicability claim."""
    ref=reference_at(profile['references'],rpm,interpolate=profile['interpolate'],max_gap=profile['max_rpm_gap'],uncertainty=profile['interpolation_uncertainty'])
    base={'offline_scope_bypass':True,'operational_use':False,'label':None}
    if ref is None: return dict(base,status='hold',anomaly=None,reason='normal_reference_speed_unavailable')
    v=np.asarray(feature_values)[profile['selected_indices']]; z=(v-ref[0])/ref[1]; score=float(np.sqrt(np.mean(z*z)))
    if score<=profile['normal_accept_limit']: return dict(base,status='normal',label='normal',anomaly=False,normal_score=score)
    if score<=profile['anomaly_limit']: return dict(base,status='hold',anomaly=None,reason='normal_gate_borderline',normal_score=score)
    return dict(base,status='anomaly',anomaly=True,normal_score=score)

def shadow_fault(feature_values,rpm,profile):
    """Frozen feature distance/radius/margin; no metadata falsification in real API."""
    v=np.asarray(feature_values); z=(v[profile['indices']]-profile['center'])/profile['scale']
    distances=np.sqrt(np.mean((np.asarray(profile['prototypes'])-z)**2,axis=1)+profile['rpm_penalty']*(np.log(np.asarray(profile['rpms'])/rpm)/.2)**2)
    by=np.array([distances[np.asarray(profile['labels'])==c].min() for c in profile['classes']]); order=np.argsort(by); winner=order[0]; margin=float(by[order[1]]-by[winner])
    unknown=by[winner]>profile['limits'][winner] or margin<=max(profile['margin'],1e-12)
    return dict(status='anomaly_unknown' if unknown else 'fault_candidate',label=None if unknown else profile['classes'][winner],
        anomaly=True,offline_scope_bypass=True,operational_use=False,margin=margin)

def summarize(items,key):
    normal=[r for r in items if r['truth']=='normal']; faults=[r for r in items if r['truth']!='normal']
    def result(r): return r[key]
    false=sum(result(r).get('anomaly') is True for r in normal)
    accepted=sum(result(r).get('label')=='normal' for r in normal)
    eligible_normal=[r for r in normal if result(r).get('anomaly') is not None]
    correct=sum(result(r).get('label')==r['truth'] for r in faults)
    eligible_fault=[r for r in faults if result(r).get('status')=='fault_candidate']
    recordings={}
    for r in items:
        row=recordings.setdefault(r['recording'],dict(truth=r['truth'],windows=0,false_anomaly=0,correct_type=0,predictions={}))
        p=result(r); guessed=p.get('label') or p['status']; row['windows']+=1
        row['false_anomaly']+=int(r['truth']=='normal' and p.get('anomaly') is True); row['correct_type']+=int(r['truth']!='normal' and p.get('label')==r['truth'])
        row['predictions'][guessed]=row['predictions'].get(guessed,0)+1
    confusion={}
    for r in faults:
        row=confusion.setdefault(r['truth'],{}); p=result(r); guess=p.get('label') or p['status']; row[guess]=row.get(guess,0)+1
    normal_records=[r for r in recordings.values() if r['truth']=='normal']
    return dict(windows=len(items),original_recordings=len(recordings),normal_windows=len(normal),fault_windows=len(faults),
        normal_false_anomalies=false,normal_false_anomaly_fraction_all_windows=false/len(normal) if normal else None,
        normal_decision_windows=len(eligible_normal),normal_decision_coverage=len(eligible_normal)/len(normal) if normal else None,
        normal_false_anomaly_fraction_decided=false/len(eligible_normal) if eligible_normal else None,
        normal_accepted=accepted,normal_acceptance_rate=accepted/len(normal) if normal else None,
        normal_holds=len(normal)-false-accepted,normal_original_recordings=len(normal_records),normal_recordings_with_any_false_anomaly=sum(r['false_anomaly']>0 for r in normal_records),
        fault_type_correct=correct,fault_type_accuracy_holds_wrong=correct/len(faults) if faults else None,
        fault_type_decisions=len(eligible_fault),fault_type_decision_coverage=len(eligible_fault)/len(faults) if faults else None,
        fault_type_accuracy_decided=sum(result(r).get('label')==r['truth'] for r in eligible_fault)/len(eligible_fault) if eligible_fault else None,
        confusion=confusion,per_recording=recordings)
