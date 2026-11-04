"""Original generic interval assessment, with all limits supplied by the caller.

No copyrighted table, machine-class selector, alarm multiplier or standard's
acceptance matrix is present. The three illustrative values in tests are invented.
"""
from .contracts import Rule,MissingInformation

def available_standards():
    """No built-in normative profiles are distributed in this edition."""
    return ()

def select_rule(standard,context,measurement):
    context.validate(); measurement.validate()
    raise MissingInformation('No standard tables bundled: provide a lawful, reviewed custom Rule.')

def evaluate(standard,context,measurement,*,custom_rule=None):
    """Compare one qualified observation to caller limits, without machine certification.

    No unit changes imply statistic changes: RMS, peak-to-peak and Smax remain
    separate quantities. Exact equality stays in the lower interval, before any
    display rounding. Missing calibration, condition or rule produces a hold.
    """
    c=context.validate(); m=measurement.validate()
    if custom_rule is not None:
        if not isinstance(custom_rule,Rule): raise ValueError('Expected Rule instance.')
        custom_rule.validate()
        if custom_rule.standard!=standard: raise ValueError('Rule identifier differs from requested provenance.')
    base=dict(schema='vibration.user-rule-evaluation.v1',standard=standard,asset_id=c.asset_id,
        condition_id=c.condition_id,point_id=m.point_id,axis=m.axis,zone=None,
        whole_machine_compliance=False,automatic_shutdown=False,authority='user_supplied_limits')
    if custom_rule is None: return dict(base,status='indeterminate',reason='user_rule_required; normative tables are not distributed')
    r=custom_rule
    if not m.valid: return dict(base,status='quality_hold',reason='Observation marked invalid')
    if c.exclusions or c.operating_state!='steady' or c.condition_id=='unknown' or c.location=='unknown':
        return dict(base,status='indeterminate',reason='Explicit steady operating condition and location required')
    if not (m.calibrated and m.acquisition_verified): return dict(base,status='indeterminate',reason='Calibration/acquisition not confirmed')
    if (m.quantity,m.statistic)!=(r.quantity,r.statistic) or m.frame not in r.frames:
        return dict(base,status='indeterminate',reason='Quantity/statistic/frame mismatch')
    low,high=r.band_hz
    if abs(m.band_hz[0]-low)>1e-8 or (m.band_hz[1]<high-1e-8 if r.minimum_upper_band else abs(m.band_hz[1]-high)>1e-8):
        return dict(base,status='indeterminate',reason='Band mismatch')
    if m.duration_s+1e-8<r.minimum_duration_s: return dict(base,status='indeterminate',reason='Insufficient observation duration')
    value=m.canonical_value(); zone=next((z for limit,z in zip(r.limits,r.zones) if value<=limit),r.zones[-1])
    return dict(base,status='evaluated',zone=zone,value=value,rule=r.to_dict(),canonical_unit={'velocity':'mm/s','displacement':'um','acceleration':'m/s^2'}[r.quantity])

def aggregate(results):
    """Preserve point results; coverage does not imply whole-machine compliance."""
    rows=list(results)
    if not rows: raise ValueError('At least one observation required.')
    if len({(r['asset_id'],r['standard'],r['condition_id']) for r in rows})!=1: raise ValueError('Mixed asset, condition or rule provenance.')
    return dict(status='evaluated_points' if all(r.get('zone') for r in rows) else 'partial',results=rows,whole_machine_compliance=False)
