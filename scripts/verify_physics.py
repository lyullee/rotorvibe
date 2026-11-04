"""Independent physical reference problems; not hardware/field validation."""
import sys, json, time, traceback, warnings, math
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import replace
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
import vibration.bootstrap
import numpy as np
from scipy.integrate import solve_ivp
from scipy.signal import fftconvolve
from vibration import AnalysisConfig, SignalBlock, VibrationAnalyzer, BearingGeometry, BearingMap
from vibration.bearings import Bearings

OUT=ROOT/'output/physics_verification'; OUT.mkdir(parents=True,exist_ok=True)
ROWS=[]; FS=12000; T=np.arange(FS)/FS; G=9.80665

def check(group,name,fn):
    start=time.perf_counter()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',RuntimeWarning); detail=fn()
        row={'group':group,'name':name,'status':'pass','detail':detail}
    except Exception:
        row={'group':group,'name':name,'status':'fail','traceback':traceback.format_exc()}
    row['seconds']=time.perf_counter()-start; ROWS.append(row)
    print(f"{row['status'].upper()} [{group}] {name}",flush=True)
    if row['status']=='fail': print(row['traceback'],flush=True)

def near(actual,expected,rtol=1e-8,atol=1e-11):
    np.testing.assert_allclose(actual,expected,rtol=rtol,atol=atol)
    return {'actual':float(actual),'expected':float(expected),'relative_error':float(abs(actual-expected)/max(abs(expected),1e-30)),'rtol':rtol}

def config(**kw):
    return replace(AnalysisConfig(unit='m/s^2',window='boxcar'),**kw)

def analyze(a,c=None,rpm=None):
    c=c or config()
    return VibrationAnalyzer(c).analyze(SignalBlock(a,c.sample_rate_hz,
        unit='V' if c.input_representation=='volts' else c.unit,rpm=rpm,
        metadata={'origin':'synthetic_physical_reference','not_field_measurement':True}))

def rejects(fn):
    try: fn()
    except ValueError: return 'rejected'
    raise AssertionError('Physically inadmissible geometry accepted.')

def motion():
    def displacement():
        f=50; x_peak=20e-6; omega=2*np.pi*f
        a=-x_peak*omega**2*np.cos(omega*T)
        r=analyze(a)
        return {'acceleration_rms':near(r.metrics['rms'],x_peak*omega**2/np.sqrt(2)),
                'velocity_rms_mm_s':near(r.metrics['velocity_rms_mm_s'],x_peak*omega/np.sqrt(2)*1000)}
    check('motion','displacement_acceleration_velocity_consistency',displacement)
    def fixed_displacement():
        values=[]
        for f in (50,100):
            w=2*np.pi*f; r=analyze(-20e-6*w*w*np.cos(w*T)); values.append(r.metrics)
        near(values[1]['rms']/values[0]['rms'],4)
        return near(values[1]['velocity_rms_mm_s']/values[0]['velocity_rms_mm_s'],2)
    check('motion','frequency_doubling_fixed_displacement',fixed_displacement)
    def fixed_acceleration():
        a=analyze(2*np.cos(2*np.pi*50*T)); b=analyze(2*np.cos(2*np.pi*100*T))
        near(a.metrics['rms'],b.metrics['rms'])
        return near(a.metrics['velocity_rms_mm_s']/b.metrics['velocity_rms_mm_s'],2)
    check('motion','frequency_doubling_fixed_acceleration',fixed_acceleration)
    def multi_frequency():
        frequencies=np.array([30.,120.,400.]); amplitudes=np.array([1.2,3.,.8])
        a=sum(A*np.cos(2*np.pi*f*T) for A,f in zip(amplitudes,frequencies))
        r=analyze(a)
        near(r.metrics['rms'],np.sqrt(np.sum(amplitudes**2)/2))
        return near(r.metrics['velocity_rms_mm_s'],np.sqrt(np.sum((amplitudes/(2*np.pi*frequencies))**2)/2)*1000)
    check('motion','orthogonal_components_velocity_energy',multi_frequency)
    def unit_equivalence():
        a=2*np.cos(2*np.pi*80*T)
        si=analyze(a); g=analyze(a/G,config(unit='g'))
        near(g.metrics['rms']*G,si.metrics['rms'])
        return near(g.metrics['velocity_rms_mm_s'],si.metrics['velocity_rms_mm_s'])
    check('motion','g_and_SI_equivalent_motion',unit_equivalence)
    def sensor_chain():
        physical=np.column_stack((2*np.cos(2*np.pi*80*T),3*np.sin(2*np.pi*120*T)))
        sensitivity=np.array([100.,250.]); gain=4.; bias=2.5
        volts=physical/G*sensitivity/1000*gain+bias
        c=config(channels=2,input_representation='volts',sensitivity_mv_per_g=sensitivity.tolist(),conditioner_gain=gain,bias_voltage_v=bias)
        outputs=[]
        for ch in range(2):
            measured=analyze(volts,replace(c,channel=ch)); expected=analyze(physical,config(channels=2,channel=ch))
            near(measured.metrics['rms'],expected.metrics['rms'])
            outputs.append(near(measured.metrics['velocity_rms_mm_s'],expected.metrics['velocity_rms_mm_s']))
        return outputs
    check('motion','two_sensor_voltage_gain_bias_chain',sensor_chain)
    def rotation_invariance():
        x=np.column_stack((np.cos(2*np.pi*50*T),2*np.sin(2*np.pi*80*T)))
        angle=.73; rot=np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
        energies=[]
        for a in (x,x@rot.T):
            energies.append(sum(analyze(a,config(channels=2,channel=ch)).metrics['rms']**2 for ch in range(2)))
        return near(energies[0],energies[1])
    check('motion','axis_rotation_preserves_total_mean_square',rotation_invariance)

def energy():
    def parseval():
        rng=np.random.default_rng(20261103); x=rng.normal(size=FS)
        r=analyze(x); p=r.payload['psd']
        return near(np.sum(p['y'])*(p['x'][1]-p['x'][0]),np.var(x))
    check('energy','parseval_random_signal',parseval)
    def band_additivity():
        frequencies=[50,200,1000,3000]; amplitudes=[1,2,3,4]
        r=analyze(sum(A*np.cos(2*np.pi*f*T) for f,A in zip(frequencies,amplitudes)))
        powers=[b['power'] for b in r.metrics['band_power']]
        np.testing.assert_allclose(powers,np.array(amplitudes)**2/2,rtol=1e-10)
        return near(sum(powers),r.metrics['rms']**2)
    check('energy','nonoverlapping_band_power_additivity',band_additivity)
    def scaling():
        a=np.cos(2*np.pi*80*T); base=analyze(a); scaled=analyze(7*a)
        near(scaled.metrics['rms']/base.metrics['rms'],7)
        return near(np.sum(scaled.payload['psd']['y'])/np.sum(base.payload['psd']['y']),49)
    check('energy','amplitude_linear_power_quadratic',scaling)
    def bandwidth():
        low=analyze(np.cos(2*np.pi*5*T)); high=analyze(np.cos(2*np.pi*100*T))
        combined=analyze(np.cos(2*np.pi*5*T)+np.cos(2*np.pi*100*T))
        assert low.metrics['velocity_rms_mm_s']<1e-10
        return near(combined.metrics['velocity_rms_mm_s'],high.metrics['velocity_rms_mm_s'])
    check('energy','velocity_lower_cutoff_not_unbounded_DC_integral',bandwidth)

def sdof():
    """Independent time-domain ODE vs analytic steady-state transfer function."""
    responses=[]
    m=10.; fn=80.; wn=2*np.pi*fn; zeta=.03; k=m*wn*wn; damping=2*zeta*m*wn; unbalance=.001
    for forcing_hz in (30.,80.,120.):
        def forced(forcing_hz=forcing_hz):
            omega=2*np.pi*forcing_hz; force_peak=unbalance*omega**2
            def ode(t,y): return [y[1],(force_peak*np.cos(omega*t)-damping*y[1]-k*y[0])/m]
            t=2+T
            sol=solve_ivp(ode,(0,3),[0,0],t_eval=t,method='DOP853',rtol=1e-10,atol=1e-12,max_step=1/(50*max(fn,forcing_hz)))
            assert sol.success
            x,v=sol.y; force=force_peak*np.cos(omega*t); acc=(force-damping*v-k*x)/m
            expected_x=force_peak/np.sqrt((k-m*omega**2)**2+(damping*omega)**2)
            r=analyze(acc)
            a_error=near(r.metrics['rms'],expected_x*omega**2/np.sqrt(2),rtol=.002)
            v_error=near(r.metrics['velocity_rms_mm_s'],expected_x*omega/np.sqrt(2)*1000,rtol=.002)
            power=near(np.mean(force*v),damping*np.mean(v*v),rtol=.002)
            responses.append((forcing_hz,r.metrics['rms']/force_peak))
            return {'frequency_hz':forcing_hz,'mass_kg':m,'natural_frequency_hz':fn,'damping_ratio':zeta,
                    'acceleration':a_error,'velocity':v_error,'input_vs_dissipated_power':power}
        check('sdof','unbalance_forced_response_'+str(forcing_hz),forced)
    def resonance():
        assert len(responses)==3 and responses[1][1]>max(responses[0][1],responses[2][1])*5
        return {'acceleration_per_force':responses,'note':'SDOF resonance is not by itself a bearing fault.'}
    check('sdof','resonance_amplification',resonance)
    def free_decay():
        t=np.arange(FS)/FS; wd=wn*np.sqrt(1-zeta*zeta); x0=20e-6
        x=x0*np.exp(-zeta*wn*t)*(np.cos(wd*t)+zeta/np.sqrt(1-zeta*zeta)*np.sin(wd*t))
        v=-x0*wn/np.sqrt(1-zeta*zeta)*np.exp(-zeta*wn*t)*np.sin(wd*t)
        a=(-damping*v-k*x)/m
        e=.5*m*v*v+.5*k*x*x
        assert np.max(np.diff(e))<1e-12
        c=config(window_seconds=.25,hop_seconds=.25)
        rms=[analyze(a[i:i+3000],c).metrics['rms'] for i in range(0,FS,3000)]
        assert np.all(np.diff(rms)<0)
        np.testing.assert_allclose(np.array(rms[1:])/rms[:-1],np.exp(-zeta*wn*.25),rtol=.02)
        return {'rms_windows':rms,'expected_decay_per_window':float(np.exp(-zeta*wn*.25)),
                'initial_energy_J':float(e[0]),'final_energy_J':float(e[-1])}
    check('sdof','unforced_damped_energy_and_acceleration_decay',free_decay)

def bearings():
    def identities():
        cases=0; worst=0.
        for n in (4,8,12,20):
            for angle in (0,15,35):
                for rpm in (600,1800,6000):
                    b=BearingGeometry(n,5,50,angle); f=b.frequencies(rpm); fr=rpm/60
                    near(f['BPFI']+f['BPFO'],n*fr); near(f['BPFO'],n*f['FTF']); near(f['BPFI'],n*(fr-f['FTF']))
                    near(f['2BSF'],2*f['BSF']); assert 0<f['FTF']<fr/2 and f['BPFI']>=f['BPFO']
                    doubled=b.frequencies(2*rpm)
                    for label in f: near(doubled[label],2*f[label])
                    cases+=1
        return {'geometries_speed_angle_cases':cases,'identities':['BPFI+BPFO=N*fr','BPFO=N*FTF','BPFI=N*(fr-FTF)','2BSF=2*BSF'],'assumptions':'stationary outer race, rotating inner race, pure rolling'}
    check('bearing','kinematic_identities_36_cases',identities)
    def units():
        a=BearingGeometry(9,.3126,1.537).frequencies(1800)
        b=BearingGeometry(9,.3126*25.4,1.537*25.4).frequencies(1800)
        for label in a: near(a[label],b[label])
        return 'Equal scaling of both diameters leaves frequencies invariant.'
    check('bearing','inch_mm_geometric_equivalence',units)
    def contact_angle():
        a=BearingGeometry(8,5,50,0).frequencies(1800); b=BearingGeometry(8,5,50,35).frequencies(1800)
        assert b['BPFI']<a['BPFI'] and b['BPFO']>a['BPFO'] and b['FTF']>a['FTF'] and b['BSF']>a['BSF']
        return {'zero_degree':a,'35_degree':b}
    check('bearing','contact_angle_trends',contact_angle)
    def catalog():
        registry=Bearings(); comparisons=[]
        for row in registry.rows:
            a=registry.frequencies(row['id'],1800); b=registry.frequencies(row['id'],3600)
            assert all(np.isfinite(v) and v>0 for v in a.values())
            for label in a: near(b[label],2*a[label])
            if 'BSF' in a and '2BSF' in a: near(a['2BSF'],2*a['BSF'])
            if 'geometry' in row:
                geometry=BearingGeometry(**row['geometry']).frequencies(1800)
                errors={label:abs(a[label]/geometry[label]-1) for label in a if label in geometry}
                assert max(errors.values())<.005,errors
                comparisons.append({'id':row['id'],'maximum_relative_difference':max(errors.values())})
        return {'catalog_rows':len(registry.rows),'published_vs_geometry':comparisons,'geometry_tolerance':.005,'note':'Published frequencies take precedence over rounded geometry.'}
    check('bearing','all_catalog_frequency_units_and_geometry_crosscheck',catalog)
    for name,g in [('fractional_count',BearingGeometry(8.5,5,50)),('boolean_count',BearingGeometry(True,5,50)),
                   ('one_element',BearingGeometry(1,5,50)),('overlapping_elements',BearingGeometry(20,20,50)),
                   ('negative_angle',BearingGeometry(8,5,50,-1)),('angle_90',BearingGeometry(8,5,50,90))]:
        check('bearing','reject_'+name,lambda g=g:rejects(lambda:g.frequencies(1800)))
    def custom_geometry():
        registry=Bearings()
        for kw in ({'rolling_elements':8.5},{'contact_angle_deg':100},{'rolling_elements':20,'rolling_diameter':20}):
            values={'rolling_elements':8,'rolling_diameter':5,'pitch_diameter':50,'contact_angle_deg':0,**kw}
            rejects(lambda:registry.custom(values))
        return 'HTTP/catalog custom bearing route enforces same geometry as Python API.'
    check('bearing','reject_impossible_custom_catalog_geometry',custom_geometry)

def diagnosis_and_sampling():
    def impact_resonance():
        n=2*FS; impulse=np.zeros(n); impulse[::120]=1
        t=np.arange(2400)/FS; fn=2500.; zeta=.04
        h=np.exp(-zeta*2*np.pi*fn*t)*np.sin(2*np.pi*fn*np.sqrt(1-zeta*zeta)*t)
        a=fftconvolve(impulse,h)[:n][-FS:]
        c=config(envelope_low_hz=2000,envelope_high_hz=3000,rpm=1875,bearing_id='reference')
        provider=BearingMap({'reference':BearingGeometry(8,10,50)})
        r=VibrationAnalyzer(c,bearing_provider=provider).analyze(SignalBlock(a,FS,unit=c.unit))
        hits=[m for m in r.payload['bearing_markers'] if m['label']=='BPFO' and m['detected']]
        assert len(hits)>=2
        for hit in hits: near(hit['observed_hz'],100*hit['harmonic'],rtol=.015)
        wrong=analyze(a,replace(c,bearing_id=None,envelope_low_hz=500,envelope_high_hz=900))
        ratio=wrong.metrics['envelope_rms']/r.metrics['envelope_rms']; assert ratio<.2
        assert r.payload['diagnosis']['status']=='candidate_only'
        return {'input':'100 Hz impulse train exciting damped 2500 Hz resonance, synthetic','BPFO_matches':hits,
                'wrong_band_to_correct_envelope_rms_ratio':ratio,'diagnostic_scope':'periodic impacts are compatible with bearing defect but do not uniquely identify cause'}
    check('diagnosis','periodic_impacts_resonance_envelope_and_band_choice',impact_resonance)
    def unresolved():
        c=config(rpm=30)
        r=analyze(np.cos(2*np.pi*2*T),c)
        # One 2 Hz spectral line must not become several independent shaft harmonics.
        candidates=r.payload['diagnosis']['candidates']
        assert not any(d['kind']=='mechanical' for d in candidates),candidates
        return {'shaft_hz':.5,'resolution_hz':r.payload['frequency_resolution_hz'],'candidates':candidates}
    check('diagnosis','unresolved_harmonics_not_multiple_physical_evidence',unresolved)
    def longer_observation():
        c=config(rpm=30,window_seconds=9)
        t=np.arange(9*FS)/FS
        r=analyze(np.cos(2*np.pi*2*t),c)
        detected=[m['order'] for m in r.payload['rotation_markers'] if m['detected']]
        assert detected==[4],detected
        assert not r.payload['diagnosis']['candidates'] and not r.payload['diagnosis']['limitations']
        return {'duration_seconds':9,'shaft_hz':.5,'input_hz':2,'detected_orders':detected,
                'bin_spacing_hz':r.payload['frequency_resolution_hz']}
    check('diagnosis','longer_window_recovers_one_resolved_fourth_order',longer_observation)
    def aliasing():
        original=np.cos(2*np.pi*7000*T); alias=np.cos(2*np.pi*5000*T)
        np.testing.assert_allclose(original,alias,atol=1e-10)
        r=analyze(original); s=r.payload['spectrum']; observed=s['x'][np.argmax(s['y'])]
        near(observed,5000)
        return {'analogue_input_hz':7000,'sample_rate_hz':FS,'observed_hz':float(observed),
                'finding':'Already sampled waveform cannot disambiguate true 5000 Hz from aliased 7000 Hz; upstream anti-alias filtering required.'}
    check('sampling','aliasing_indistinguishability_negative_control',aliasing)
    def short_record():
        c=config(window_seconds=.1,hop_seconds=.05)
        r=analyze(np.cos(2*np.pi*100*np.arange(1200)/FS)+np.cos(2*np.pi*104*np.arange(1200)/FS),c)
        near(r.payload['frequency_resolution_hz'],10)
        return {'actual_separation_hz':4,'FFT_bin_spacing_hz':10,'finding':'No claim to resolve the two causes from one short-window peak.'}
    check('sampling','finite_observation_resolution_limit',short_record)

if __name__=='__main__':
    started=datetime.now(timezone.utc).isoformat()
    motion(); energy(); sdof(); bearings(); diagnosis_and_sampling()
    result={'started_utc':started,'finished_utc':datetime.now(timezone.utc).isoformat(),
            'python':sys.version,'numpy':np.__version__,'checks':ROWS,
            'passed':sum(r['status']=='pass' for r in ROWS),'failed':sum(r['status']=='fail' for r in ROWS),
            'scope':'Physics-based numerical verification with analytic signals, independent ODE and kinematic invariants; not physical hardware validation.'}
    (OUT/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f"RESULT: {result['passed']} passed / {result['failed']} failed",flush=True)
    sys.exit(bool(result['failed']))
