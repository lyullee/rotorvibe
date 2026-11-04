"""Bounded producer queue and measured processing times; host owns scheduling."""
from collections import deque
import json,threading,time
import numpy as np
from .contracts import SignalBlock,json_value


class RealtimeProcessor:
    def __init__(self,analyzer,*,max_pending=4,max_chunk_samples=None,max_pending_bytes=64*1024*1024,overflow='reject',latency_budget_seconds=None):
        self.analyzer=analyzer
        for value in (max_pending,max_pending_bytes):
            if isinstance(value,bool) or not isinstance(value,int) or value<=0: raise ValueError('Positive integer queue limits required')
        config=analyzer.config
        if max_chunk_samples is None: max_chunk_samples=min(2_000_000,round(config.sample_rate_hz*config.window_seconds)*4)
        if isinstance(max_chunk_samples,bool) or not isinstance(max_chunk_samples,int) or max_chunk_samples<=0: raise ValueError('Positive chunk limit required')
        if overflow not in ('reject','drop_oldest'): raise ValueError('Unknown overflow policy')
        if latency_budget_seconds is not None and (isinstance(latency_budget_seconds,bool) or not isinstance(latency_budget_seconds,(int,float)) or not np.isfinite(latency_budget_seconds) or latency_budget_seconds<=0):
            raise ValueError('Positive finite latency budget required')
        self.latency_budget=latency_budget_seconds
        self.max_pending=max_pending; self.max_chunk=max_chunk_samples; self.max_bytes=max_pending_bytes; self.overflow=overflow
        self._queue=deque(); self._bytes=0; self._lock=threading.Lock(); self._consumer=threading.Lock()
        self._durations=deque(maxlen=256); self._waits=deque(maxlen=256); self._latencies=deque(maxlen=256)
        self._deadline_misses=0; self._closed=False; self._reset_needed=False
        self._submitted=0; self._processed=0; self._dropped=0; self._rejected=0; self._failed=0; self._windows=0; self._high_water=0

    def submit(self,block):
        if not isinstance(block,SignalBlock): raise ValueError('SignalBlock required')
        config=self.analyzer.config
        if block.sample_rate_hz!=config.sample_rate_hz or block.values.shape[1]!=config.channels:
            raise ValueError('Chunk sampling/channels differ from analyzer')
        expected='V' if config.input_representation=='volts' else config.unit
        if block.unit!=expected: raise ValueError('Chunk unit differs from analyzer')
        # Own a snapshot: a caller can mutate nested metadata despite frozen dataclass.
        if len(json.dumps(json_value(block.metadata),allow_nan=False).encode('utf8'))>65536:
            raise ValueError('Chunk metadata exceeds 64 KiB')
        size=block.values.nbytes+block.valid.nbytes+(block.rpm.nbytes if isinstance(block.rpm,np.ndarray) else 0)
        if len(block.values)>self.max_chunk or size>self.max_bytes: raise ValueError('Chunk exceeds bounded buffer limit')
        snapshot=SignalBlock(block.values,block.sample_rate_hz,block.unit,block.start_time_s,block.clock_id,block.episode_id,
                             block.channels,block.valid,block.rpm,block.sequence,block.metadata)
        with self._lock:
            if self._closed: raise RuntimeError('Processor is closed')
            if self.overflow=='reject' and (len(self._queue)>=self.max_pending or self._bytes+size>self.max_bytes):
                self._rejected+=1
                return {'accepted':False,'reason':'queue_full','pending':len(self._queue)}
            while self._queue and (len(self._queue)>=self.max_pending or self._bytes+size>self.max_bytes):
                _,old_size,_=self._queue.popleft(); self._bytes-=old_size; self._dropped+=1; self._reset_needed=True
            self._queue.append((snapshot,size,time.perf_counter())); self._bytes+=size; self._submitted+=1
            self._high_water=max(self._high_water,len(self._queue))
            return {'accepted':True,'pending':len(self._queue),'dropped_total':self._dropped}

    def process_next(self):
        if not self._consumer.acquire(blocking=False): raise RuntimeError('Only one processing consumer is supported')
        try:
            with self._lock:
                if self._closed: raise RuntimeError('Processor is closed')
                if not self._queue: return []
                block,size,queued_at=self._queue.popleft(); self._bytes-=size
                reset=self._reset_needed; self._reset_needed=False
            start=time.perf_counter()
            wait=start-queued_at
            try:
                if reset: self.analyzer.reset(reset_stages=True)
                results=self.analyzer.push(block)
            except Exception:
                with self._lock: self._failed+=1; self._reset_needed=True
                raise
            elapsed=time.perf_counter()-start
            with self._lock:
                self._durations.append(elapsed); self._processed+=1; self._windows+=len(results)
                self._waits.append(wait); self._latencies.append(wait+elapsed)
                self._deadline_misses+=int(self.latency_budget is not None and wait+elapsed>self.latency_budget)
            return results
        finally: self._consumer.release()

    def drain(self,*,limit=None):
        if limit is not None and (isinstance(limit,bool) or not isinstance(limit,int) or limit<0): raise ValueError('Nonnegative drain limit required')
        with self._lock: limit=min(limit,len(self._queue)) if limit is not None else len(self._queue)
        results=[]; count=0
        # Drain only the initial bounded batch. Concurrent producers cannot turn
        # a single drain() into an endless, unbounded result list.
        while count<limit:
            with self._lock:
                if not self._queue: break
            results.extend(self.process_next()); count+=1
        return results

    def stats(self):
        with self._lock:
            durations=list(self._durations)
            return {'schema':'vibration.realtime.v1','pending':len(self._queue),'pending_bytes':self._bytes,
                'submitted':self._submitted,'processed':self._processed,'dropped':self._dropped,'rejected':self._rejected,
                'failed':self._failed,'windows':self._windows,'high_water':self._high_water,
                'processing_seconds_p50':float(np.quantile(durations,.5)) if durations else None,
                'processing_seconds_p95':float(np.quantile(durations,.95)) if durations else None,
                'processing_seconds_max':max(durations) if durations else None,
                'queue_wait_seconds_max':max(self._waits) if self._waits else None,
                'latency_seconds_p95':float(np.quantile(self._latencies,.95)) if self._latencies else None,
                'latency_seconds_max':max(self._latencies) if self._latencies else None,
                'latency_budget_seconds':self.latency_budget,'deadline_misses':self._deadline_misses,
                'timing_history_capacity':256,'hard_realtime_guarantee':False,'closed':self._closed}

    def close(self):
        if not self._consumer.acquire(blocking=False): raise RuntimeError('Stop the processing consumer before closing')
        try:
            with self._lock:
                self._closed=True; self._dropped+=len(self._queue); self._queue.clear(); self._bytes=0
            self.analyzer.reset(reset_stages=True)
        finally: self._consumer.release()
