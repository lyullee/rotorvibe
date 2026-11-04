"""Common, inert JSON envelopes. Hashes detect changes, not author authenticity.

Algorithm-specific loaders still own numerical validation. A matching envelope
does not certify the model or authorize a new installation/operating scope.
"""
import hashlib
import json
from datetime import date
from collections.abc import Mapping
from .contracts import json_value

SCHEMA='vibration.profile-envelope.v1'
_KINDS={'normal_reference','fault_model','preprocessing','life_reference','user_rule'}


def _json(value):
    try: return json.dumps(json_value(value),sort_keys=True,separators=(',',':'),allow_nan=False)
    except (TypeError,ValueError) as exc: raise ValueError('Finite JSON profile data required.') from exc


def profile_digest(value):
    """SHA-256 of canonical finite JSON (NumPy arrays become JSON lists)."""
    return hashlib.sha256(_json(value).encode('utf8')).hexdigest()


def _text(value,name):
    if not isinstance(value,str) or not value.strip(): raise ValueError(name+' must be nonempty text.')


def create_profile(payload,*,profile_id,kind,algorithm,feature_schema,preprocessing,
                   training_groups,calibration_history,scope):
    """Wrap an existing payload without changing its model or feature definition.

    Calibration entries require calibration_id, group_id, reviewed_on and method.
    An empty history explicitly means no calibration has been recorded.
    """
    result={'schema':SCHEMA,'profile_id':profile_id,'kind':kind,
            'contract':{'algorithm':algorithm,'feature_schema':feature_schema,
                        'preprocessing_sha256':profile_digest(preprocessing)},
            'preprocessing':preprocessing,'training_groups':list(training_groups),
            'calibration_history':list(calibration_history),'scope':scope,'payload':payload,
            'payload_sha256':profile_digest(payload)}
    result=json.loads(_json(result))
    result['envelope_sha256']=profile_digest(result)
    return validate_profile(result)


def validate_profile(envelope,*,expected_contract=None,expected_scope=None):
    """Check integrity and exact caller-supplied compatibility requirements.

    Return a detached JSON copy. Call the algorithm loader after unwrapping.
    Integrity is not a cryptographic signature or a validation-accuracy claim.
    """
    if not isinstance(envelope,Mapping): raise ValueError('Profile envelope mapping required.')
    row=json.loads(_json(envelope))
    required={'schema','profile_id','kind','contract','preprocessing','training_groups',
              'calibration_history','scope','payload','payload_sha256','envelope_sha256'}
    if set(row)!=required or row['schema']!=SCHEMA: raise ValueError('Unknown profile envelope schema/fields.')
    _text(row['profile_id'],'profile_id')
    if row['kind'] not in _KINDS: raise ValueError('Unknown profile kind.')
    c=row['contract']
    if not isinstance(c,dict) or set(c)!={'algorithm','feature_schema','preprocessing_sha256'}:
        raise ValueError('Explicit algorithm/feature/preprocessing contract required.')
    for k in ('algorithm','feature_schema'): _text(c[k],k)
    if not isinstance(row['preprocessing'],dict) or not row['preprocessing']:
        raise ValueError('Explicit preprocessing description required.')
    if c['preprocessing_sha256']!=profile_digest(row['preprocessing']): raise ValueError('Preprocessing hash differs.')
    if not isinstance(row['payload'],dict) or not row['payload']: raise ValueError('Nonempty model payload required.')
    if row['payload_sha256']!=profile_digest(row['payload']): raise ValueError('Payload hash differs.')
    for k in ('algorithm','feature_schema'):
        if k in row['payload'] and row['payload'][k]!=c[k]: raise ValueError('Payload '+k+' differs from contract.')
    if not isinstance(row['scope'],dict) or not row['scope']: raise ValueError('Explicit scope required.')
    if 'scope' in row['payload'] and row['payload']['scope']!=row['scope']:
        raise ValueError('Payload scope differs from envelope.')
    groups=row['training_groups']
    if not isinstance(groups,list) or (not groups and row['kind'] in ('normal_reference','fault_model','life_reference')) or any(not isinstance(x,str) or not x for x in groups) or len(set(groups))!=len(groups):
        raise ValueError('Distinct original training group IDs required.')
    payload_groups=row['payload'].get('fit_groups',row['payload'].get('groups'))
    if payload_groups is not None and set(payload_groups)!=set(groups):
        raise ValueError('Payload original fit groups differ from envelope.')
    history=row['calibration_history']
    if not isinstance(history,list): raise ValueError('Calibration history list required.')
    ids=set()
    for item in history:
        if not isinstance(item,dict) or set(item)!={'calibration_id','group_id','reviewed_on','method'}:
            raise ValueError('Calibration provenance fields required.')
        for k,v in item.items(): _text(v,k)
        if item['calibration_id'] in ids or item['group_id'] in groups:
            raise ValueError('Duplicate calibration ID or fit/calibration group leakage.')
        ids.add(item['calibration_id'])
        try: date.fromisoformat(item['reviewed_on'])
        except ValueError as exc: raise ValueError('ISO calibration review date required.') from exc
    if 'calibration_groups' in row['payload'] and set(row['payload']['calibration_groups'])!={x['group_id'] for x in history}:
        raise ValueError('Payload calibration groups differ from envelope history.')
    digest=row.pop('envelope_sha256')
    if digest!=profile_digest(row): raise ValueError('Envelope integrity differs.')
    row['envelope_sha256']=digest
    if expected_contract is not None:
        if not isinstance(expected_contract,Mapping) or set(expected_contract)!=set(c) or dict(expected_contract)!=c:
            raise ValueError('Algorithm, feature or preprocessing contract is incompatible.')
    if expected_scope is not None and json.loads(_json(expected_scope))!=row['scope']:
        raise ValueError('Profile application scope differs.')
    return row


class ProfileRegistry:
    """Host-owned registry; no files, pickle execution, implicit replacement or training."""
    def __init__(self): self._profiles={}

    def register(self,envelope):
        row=validate_profile(envelope); key=row['profile_id']
        if key in self._profiles: raise ValueError('Profile ID already registered; use a new revision ID.')
        self._profiles[key]=row
        return row['envelope_sha256']

    def get(self,profile_id,*,expected_contract,expected_scope):
        return validate_profile(self._profiles[profile_id],expected_contract=expected_contract,expected_scope=expected_scope)

    def load(self,profile_id,loader,*,expected_contract,expected_scope):
        """Pass detached payload through an explicit algorithm-specific loader."""
        if not callable(loader): raise TypeError('Algorithm-specific loader required.')
        return loader(self.get(profile_id,expected_contract=expected_contract,expected_scope=expected_scope)['payload'])

    def remove(self,profile_id): del self._profiles[profile_id]

    def list(self):
        return [{'profile_id':k,'kind':v['kind'],'contract':dict(v['contract']),
                 'envelope_sha256':v['envelope_sha256']} for k,v in self._profiles.items()]
