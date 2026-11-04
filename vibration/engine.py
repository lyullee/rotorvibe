import json
import queue
import threading
import time
import uuid
from pathlib import Path
import numpy as np
from .bootstrap import RUNTIME
from .config import AnalysisConfig
from .dsp import analyze
from .models import Baseline, LifeEstimator
from .storage import utcnow


class EventHub:
    def __init__(self):
        self.lock=threading.Lock(); self.clients=set()

    def subscribe(self):
        q=queue.Queue(maxsize=4)
        with self.lock: self.clients.add(q)
        return q

    def unsubscribe(self,q):
        with self.lock: self.clients.discard(q)

    def publish(self,kind,payload):
        message=json.dumps({'type':kind,'data':payload},ensure_ascii=False,allow_nan=False)
        with self.lock:
            for q in tuple(self.clients):
                if q.full():
                    try: q.get_nowait()
                    except queue.Empty: pass
                try: q.put_nowait(message)
                except queue.Full: pass


class Ring:
    def __init__(self,n,channels):
        self.a=np.zeros((n,channels),dtype=float)
        self.rpm=np.full(n,np.nan); self.position=0; self.count=0

    def append(self,a,rpm):
        n=len(self.a)
        if len(a)>=n:
            self.a[:]=a[-n:]; self.rpm[:]=rpm[-n:]; self.position=0; self.count=n
            return
        end=min(len(a),n-self.position)
        self.a[self.position:self.position+end]=a[:end]
        self.rpm[self.position:self.position+end]=rpm[:end]
        if end<len(a):
            self.a[:len(a)-end]=a[end:]; self.rpm[:len(a)-end]=rpm[end:]
        self.position=(self.position+len(a))%n; self.count=min(n,self.count+len(a))

    def snapshot(self):
        if self.count<len(self.a): return self.a[:self.count].copy(),self.rpm[:self.count].copy()
        return (np.concatenate([self.a[self.position:],self.a[:self.position]]),
                np.concatenate([self.rpm[self.position:],self.rpm[:self.position]]))


class Engine:
    def __init__(self,storage,catalog,bearings,models):
        self.storage=storage; self.catalog=catalog; self.bearings=bearings; self.models=models
        self.hub=EventHub(); self.lock=threading.RLock(); self.config=AnalysisConfig().validate()
        self.baseline=Baseline(); self.life=LifeEstimator(catalog)
        self.inbox=queue.Queue(maxsize=16); self.stop_event=threading.Event()
        self.generation=0; self.mode='idle'; self.source={}; self.session_id=None
        self.latest=None; self.history=[]; self.replay_progress={}; self.counters={}
        self._reset_buffer()
        self._closed=False
        self.worker_thread=threading.Thread(target=self._worker,daemon=True,name='vibration-analysis')
        self.worker_thread.start()

    def _reset_buffer(self):
        self.ring=Ring(round(self.config.sample_rate_hz*self.config.window_seconds),self.config.channels)
        self.samples=0; self.since_analysis=0; self.previous_sequence=None; self.invalid_remaining=0
        self.counters={'packets':0,'samples':0,'sequence_gaps':0,'queue_rejections':0,'analysis_frames':0}
        self.alarm={'level':'unavailable','reason':'아직 분석 창이 없습니다.'}
        self.pending_alarm=None; self.pending_since=0; self.pending_samples=0; self.latest=None

    def state(self):
        with self.lock:
            return {'config':self.config.to_dict(),'mode':self.mode,'source':self.source,'generation':self.generation,
                    'session_id':self.session_id,'counters':dict(self.counters),'replay':dict(self.replay_progress),
                    'buffer_samples':self.ring.count,'required_samples':len(self.ring.a),
                    'baseline':{'collecting':self.baseline.collecting,'windows':len(self.baseline.samples),
                                'target':self.baseline.target,'loaded':self.baseline.profile.get('name') if self.baseline.profile else None},
                    'alarm':self.alarm,'model_job':dict(self.models.job)}

    def _new(self,mode,source,config=None):
        if self._closed: raise RuntimeError('Analysis engine is closed.')
        self.stop_event.set(); self.generation+=1
        self.stop_event=threading.Event()
        if config: self.config=config.validate()
        self.mode=mode; self.source=source; self.session_id=uuid.uuid4().hex
        self.baseline.collecting=False
        self.history=[]; self.replay_progress={}; self._reset_buffer()
        self.storage.start_session(self.session_id,source,self.config.to_dict())
        self.storage.event(self.session_id,'info','session_started',{'mode':mode,'source':source})
        self.hub.publish('state',self.state())
        return self.generation,self.stop_event

    def configure(self,values):
        with self.lock:
            c=AnalysisConfig.create({**self.config.to_dict(),**values})
            if c.bearing_id and c.bearing_id not in self.bearings.by_id: raise ValueError('베어링 항목을 찾을 수 없습니다.')
            previous=self.mode
            source={**self.source,'name':'설정 변경 후 입력 대기','previous_mode':previous,'user_configured':True}
            self._new('idle',source,c)
            return self.state()

    def live(self,values=None):
        with self.lock:
            c=AnalysisConfig.create({**self.config.to_dict(),**(values or {})})
            self._new('live',{'dataset':'live','name':'실시간 입력','unit_provenance':'사용자 측정 설정'},c)
            return self.state()

    def stop(self):
        with self.lock:
            self.stop_event.set(); self.generation+=1; self.mode='idle'
            self.baseline.collecting=False
            self.storage.event(self.session_id,'info','stopped',{})
            self.hub.publish('state',self.state())
            return self.state()

    def replay(self,id,speed=1,loop=False,snapshot=0,loaded=None,sequence=False):
        speed=float(speed)
        if not 0.1<=speed<=8: raise ValueError('재생 속도는 0.1~8배입니다.')
        a,meta=loaded if loaded is not None else self.catalog.load(id,snapshot)
        playlist=self.catalog.trial_ids(id) if sequence and loaded is None else [id]
        if len(playlist)>1:
            meta={**meta,'sequence_records':len(playlist),'duration_seconds':len(a)*len(playlist)/meta['sample_rate_hz']}
        with self.lock:
            c=self.config.for_source(meta['sample_rate_hz'],a.shape[1],meta['duration_seconds'],
                                     meta.get('unit','unknown'),meta.get('rpm'),meta.get('bearing_id'))
            if self.source.get('id')==meta.get('id') and self.source.get('user_configured'):
                changed={k:getattr(self.config,k) for k in ['unit','rpm','bearing_id','model_enabled','rms_warning','rms_danger','clip_abs']}
                c=AnalysisConfig.create({**c.to_dict(),**changed})
                meta={**meta,'unit':c.unit,'rpm':c.rpm,'bearing_id':c.bearing_id,'user_configured':True,
                      'unit_provenance':'사용자 적용 설정. 원본 단위 선언은 자료 상세에서 확인하세요.'}
            generation,stop=self._new('replay',meta,c)
            self.replay_progress={'position_seconds':0,'duration_seconds':meta['duration_seconds'],'speed':speed,'loop':bool(loop),'status':'playing'}
        threading.Thread(target=self._replay,args=(a,generation,stop,speed,bool(loop),playlist),daemon=True,name='file-replay').start()
        return self.state()

    def _enqueue(self,packet,replay=False,stop=None):
        while True:
            if self._closed: raise RuntimeError('Analysis engine is closed.')
            try:
                self.inbox.put(packet,timeout=0.1 if replay else 0.01)
                return
            except queue.Full:
                if replay:
                    if stop.is_set(): return
                else:
                    with self.lock: self.counters['queue_rejections']+=1
                    raise OverflowError('입력 대기열이 가득 찼습니다. 전송률을 낮추거나 패킷을 작게 나누세요.')

    def ingest(self,payload):
        with self.lock:
            if self.mode!='live': raise ValueError('먼저 실시간 입력 세션을 시작하세요.')
            generation=self.generation; cfg=self.config
        a=np.asarray(payload.get('samples'),dtype=float)
        if a.ndim==1: a=a[:,None]
        if a.ndim!=2 or not 1<=len(a)<=50000 or a.shape[1]!=cfg.channels:
            raise ValueError('samples는 1~50000행의 samples × channels 배열이어야 합니다.')
        if not np.isfinite(a).all() or np.max(np.abs(a))>1e12: raise ValueError('비정상 수치 또는 수치 범위를 초과한 패킷입니다.')
        if payload.get('sample_rate_hz',cfg.sample_rate_hz)!=cfg.sample_rate_hz:
            raise ValueError('세션과 패킷의 샘플링률이 다릅니다.')
        input_unit='V' if cfg.input_representation=='volts' else cfg.unit
        if payload.get('unit',input_unit)!=input_unit: raise ValueError('세션과 패킷의 입력 단위가 다릅니다.')
        if cfg.input_representation=='volts':
            sensitivity=np.asarray(cfg.sensitivity_mv_per_g,dtype=float)/1000
            a=(a-cfg.bias_voltage_v)/cfg.conditioner_gain/sensitivity
            if cfg.unit=='m/s^2': a*=9.80665
            if not np.isfinite(a).all() or np.max(np.abs(a))>1e12:
                raise ValueError('감도 변환 후 수치가 올바르지 않습니다.')
        seq=payload.get('sequence')
        if seq is not None and (not isinstance(seq,int) or isinstance(seq,bool) or seq<0): raise ValueError('sequence는 음수가 아닌 정수여야 합니다.')
        trace=payload.get('rpm_trace')
        if trace is not None:
            trace=np.asarray(trace,dtype=float)
            if trace.shape!=(len(a),) or not np.isfinite(trace).all() or np.min(trace)<1e-6 or np.max(trace)>1e9:
                raise ValueError('rpm_trace는 샘플과 동기화된 양수 1차원 배열이어야 합니다.')
        else:
            rpm=payload.get('rpm',cfg.rpm)
            if rpm is not None and (isinstance(rpm,bool) or not isinstance(rpm,(int,float)) or not np.isfinite(rpm) or not 1e-6<=rpm<=1e9): raise ValueError('RPM 값이 올바르지 않습니다.')
            trace=np.full(len(a),float(rpm) if rpm is not None else np.nan)
        self._enqueue({'generation':generation,'samples':a,'rpm':trace,'sequence':seq,
                       'source_timestamp':payload.get('timestamp'),'received':utcnow()})
        return {'accepted_samples':len(a),'queue_depth':self.inbox.qsize()}

    def _replay(self,a,generation,stop,speed,loop,playlist):
        try:
            fs=self.config.sample_rate_hz; chunk=max(1,round(fs*self.config.hop_seconds)); seq=0
            while not stop.is_set():
                started=time.monotonic()
                total_samples=0; previous_file_time=None
                for index,record_id in enumerate(playlist):
                    if stop.is_set(): return
                    segment=a if index==0 else self.catalog.load(record_id)[0]
                    if len(playlist)>1:
                        from datetime import datetime
                        member=self.catalog.records[record_id][2]['member_path']
                        file_time=datetime.strptime(Path(member).stem,'%Y%m%d-%H%M%S')
                        if previous_file_time and abs((file_time-previous_file_time).total_seconds()-1)>0.1:
                            self._enqueue({'generation':generation,'boundary':True},True,stop)
                        previous_file_time=file_time
                    for offset in range(0,len(segment),chunk):
                        if stop.is_set(): return
                        block=segment[offset:offset+chunk]
                        trace=np.full(len(block),self.config.rpm if self.config.rpm else np.nan)
                        self._enqueue({'generation':generation,'samples':block,'rpm':trace,'sequence':seq,'received':utcnow()},True,stop)
                        seq+=1
                        with self.lock:
                            if generation!=self.generation: return
                            self.replay_progress['position_seconds']=(total_samples+offset+len(block))/fs
                        delay=started+(total_samples+offset+len(block))/fs/speed-time.monotonic()
                        if delay>0 and stop.wait(delay): return
                    total_samples+=len(segment)
                if not loop: break
                self._enqueue({'generation':generation,'boundary':True},True,stop)
            # A FIFO sentinel marks completion only after the final analysis packet is consumed.
            self._enqueue({'generation':generation,'complete':True},True,stop)
        except Exception as e:
            self.hub.publish('error',{'message':str(e)})
            with self.lock:
                if generation==self.generation: self.replay_progress.update(status='failed',error=str(e))

    def _worker(self):
        while True:
            packet=self.inbox.get()
            try:
                if packet is None: return
                with self.lock:
                    if packet['generation']!=self.generation: continue
                    if packet.get('boundary'):
                        self.ring=Ring(len(self.ring.a),self.config.channels); self.since_analysis=0
                        self.storage.event(self.session_id,'info','replay_loop_boundary',{})
                        continue
                    if packet.get('complete'):
                        self.replay_progress['status']='complete'; self.hub.publish('state',self.state()); continue
                    seq=packet.get('sequence')
                    if seq is not None and self.previous_sequence is not None and seq!=self.previous_sequence+1:
                        self.counters['sequence_gaps']+=1; self.invalid_remaining=len(self.ring.a)
                        self.storage.event(self.session_id,'warning','sequence_gap',{'previous':self.previous_sequence,'received':seq})
                    self.previous_sequence=seq
                    self.counters['packets']+=1
                    a=packet['samples']; rpm=packet['rpm']
                    hop=max(1,round(self.config.hop_seconds*self.config.sample_rate_hz))
                    for offset in range(0,len(a),hop):
                        block=a[offset:offset+hop]; trace=rpm[offset:offset+hop]
                        self.ring.append(block,trace); self.samples+=len(block); self.since_analysis+=len(block)
                        self.invalid_remaining=max(0,self.invalid_remaining-len(block))
                        self.counters['samples']=self.samples
                        if self.ring.count==len(self.ring.a) and self.since_analysis>=hop:
                            data,speed=self.ring.snapshot(); self.since_analysis=0
                            self._analyze(data,speed,packet)
            except Exception as e:
                self.storage.event(self.session_id,'error','analysis_error',{'message':str(e)})
                self.hub.publish('error',{'message':str(e)})
            finally: self.inbox.task_done()

    def close(self):
        with self.lock:
            if self._closed: return
            self.stop(); self._closed=True
        self.inbox.put(None,timeout=10)
        self.worker_thread.join(timeout=10)
        if self.worker_thread.is_alive(): raise RuntimeError('Analysis worker did not close within timeout.')

    def _alarm(self,baseline,metrics,flags):
        if flags: desired='unavailable'; reason='신호 품질 확인 필요: '+', '.join(flags)
        else:
            score=baseline.get('score'); desired='normal' if score is not None else 'unavailable'
            reason='정상 기준 범위' if score is not None else baseline.get('reason','정상 기준 수집 중')
            if score is not None:
                if score>=self.config.danger_score: desired='danger'; reason='정상 기준 대비 큰 변화'
                elif score>=self.config.warning_score: desired='warning'; reason='정상 기준 대비 변화'
            if self.config.rms_warning and metrics['rms']>=self.config.rms_warning:
                if desired!='danger': desired='warning'; reason='사용자 RMS 주의 기준 초과'
            if self.config.rms_danger and metrics['rms']>=self.config.rms_danger:
                desired='danger'; reason='사용자 RMS 위험 기준 초과'
        if desired!=self.pending_alarm:
            self.pending_alarm=desired; self.pending_samples=self.samples
        elapsed=(self.samples-self.pending_samples)/self.config.sample_rate_hz
        required=self.config.persistence_seconds if desired in ['warning','danger'] else self.config.release_seconds
        if desired=='unavailable' or (desired=='normal' and self.alarm['level']=='unavailable'): required=0
        changed=desired!=self.alarm['level'] and elapsed>=required
        if changed:
            self.alarm={'level':desired,'reason':reason,'changed':utcnow()}
            self.storage.event(self.session_id,desired,'alarm_changed',dict(self.alarm))
        elif desired==self.alarm['level']:
            self.alarm['reason']=reason
        return {**self.alarm,'pending':desired if desired!=self.alarm['level'] else None,
                'pending_elapsed_seconds':elapsed,'required_seconds':required},changed

    def _analyze(self,data,speed,packet):
        started=time.perf_counter(); rpm=float(np.mean(speed)) if np.isfinite(speed).all() else self.config.rpm
        bf=self.bearings.frequencies(self.config.bearing_id,rpm) if self.config.bearing_id and rpm else {}
        frame=analyze(data,self.config,speed if np.isfinite(speed).all() else None,bf)
        vector=frame.pop('_features'); names=frame.pop('_feature_names')
        flags=[]
        if self.invalid_remaining: flags.append('packet_discontinuity_in_window')
        if self.config.clip_abs and np.any(np.abs(data)>=self.config.clip_abs): flags.append('clipping')
        if np.std(data[:,self.config.channel])<1e-12: flags.append('flat_selected_channel')
        if not flags:
            baseline=self.baseline.observe(vector,names,self.config,rpm)
        else: baseline={'status':'quality_hold','score':None,'reason':'품질 이상 구간은 정상 기준 수집에서 제외합니다.'}
        if baseline['status']=='collected':
            self.storage.save('baseline',baseline['profile']['name'],baseline['profile'])
            self.storage.event(self.session_id,'info','baseline_saved',{'name':baseline['profile']['name']})
        frame['baseline']={k:v for k,v in baseline.items() if k!='profile'}
        frame['quality']={'flags':flags,'unit_confirmed':self.config.unit!='unknown',
                          'rpm_available':rpm is not None,'timestamp_provenance':'analysis receipt time',
                          'source_timestamp':packet.get('source_timestamp')}
        variation=float(np.ptp(speed)/rpm) if rpm and np.isfinite(speed).all() else 0.
        frame['classification']=self.models.classify_window(data,self.config,self.source,vector=vector,rpm=rpm,rpm_variation_ratio=variation) if not flags else {'status':'quality_hold'}
        frame['rul']=self.life.estimate(self.source) if not flags else {'status':'quality_hold'}
        frame['alarm'],changed=self._alarm(baseline,frame['metrics'],flags)
        frame.update(timestamp=utcnow(),sample_end=self.samples,source_elapsed_seconds=self.samples/self.config.sample_rate_hz,
                     session_id=self.session_id,analysis_ms=(time.perf_counter()-started)*1000)
        if changed and frame['alarm']['level'] in ['warning','danger']:
            frame['evidence_recording']=self._save_window(data,speed,frame)
        self.latest=frame; self.counters['analysis_frames']+=1
        self.history.append({'time':frame['source_elapsed_seconds'],'rms':frame['metrics']['rms'],
                             'kurtosis':frame['metrics']['kurtosis'],'score':baseline.get('score')})
        self.history=self.history[-600:]
        self.storage.frame(self.session_id,frame)
        self.hub.publish('frame',frame)

    def _save_window(self,data,speed,frame=None):
        path=RUNTIME/'recordings'; path.mkdir(parents=True,exist_ok=True)
        name=f'{self.session_id}_{self.samples}_{uuid.uuid4().hex[:6]}.npz'
        np.savez_compressed(path/name,vibration=data,rpm_trace=speed,
                            sample_rate_hz=np.array(self.config.sample_rate_hz),unit=np.array(self.config.unit),
                            measurement_config_json=np.array(json.dumps(self.config.to_dict(),ensure_ascii=False)),
                            representation=np.array('analysis_input_after_optional_voltage_conversion'))
        self.storage.event(self.session_id,'info','raw_window_saved',{'filename':name,'sample_end':self.samples})
        return {'filename':name,'download_url':'/api/recordings/'+name}

    def save_window(self):
        with self.lock:
            if self.ring.count<256: raise ValueError('저장할 파형이 부족합니다.')
            a,s=self.ring.snapshot(); return self._save_window(a,s)

    def baseline_start(self,name,target):
        with self.lock:
            self.baseline.begin(name,self.config,target)
            self.hub.publish('state',self.state()); return self.state()

    def baseline_load(self,name):
        with self.lock:
            p=self.storage.get('baseline',name)
            if p['signature']!=self.config.signature() or p['condition']!=self.config.condition:
                raise ValueError('기준의 분석 설정/운전조건이 다릅니다. 동일 설정으로 변경한 뒤 불러오세요.')
            self.baseline.profile=p; self.baseline.collecting=False
            return {'name':name,'summary':p['summary']}

