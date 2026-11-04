"""Device-neutral HTTP/UDP writer. Use measured arrays; no generated signals."""
import json
import socket
from urllib.request import Request, urlopen
import numpy as np


class VibrationClient:
    def __init__(self,base_url='http://127.0.0.1:8765',token='',timeout=30):
        self.base_url=base_url.rstrip('/'); self.token=token; self.timeout=timeout
        self.sequence=0; self.unit='unknown'; self.fs=None

    def request(self,path,payload=None):
        headers={'X-API-Key':self.token} if self.token else {}
        data=None
        if payload is not None:
            headers['Content-Type']='application/json'
            data=json.dumps(payload,allow_nan=False).encode('utf-8')
        req=Request(self.base_url+path,data=data,headers=headers)
        with urlopen(req,timeout=self.timeout) as response:
            return json.load(response)

    def start(self,sample_rate_hz,channels,unit='unknown',rpm=None,**configuration):
        fs=float(sample_rate_hz); ny=fs/2
        config={'sample_rate_hz':fs,'channels':int(channels),'channel':0,'unit':unit,'rpm':rpm,'bearing_id':None,
                'window_seconds':max(1,256/fs),'hop_seconds':0.25,
                'envelope_low_hz':min(500,ny*0.2),'envelope_high_hz':min(5000,ny*0.9),
                'velocity_low_hz':min(10,ny*0.05),'velocity_high_hz':min(1000,ny*0.8),**configuration}
        result=self.request('/api/live/start',{'config':config})
        self.sequence=0; self.fs=fs
        self.unit='V' if config.get('input_representation')=='volts' else unit
        return result

    def packet(self,samples,rpm=None,rpm_trace=None,timestamp=None):
        a=np.asarray(samples,dtype=float)
        if a.ndim==1: a=a[:,None]
        packet={'sequence':self.sequence,'sample_rate_hz':self.fs,'unit':self.unit,'samples':a.tolist()}
        if rpm is not None: packet['rpm']=float(rpm)
        if rpm_trace is not None: packet['rpm_trace']=np.asarray(rpm_trace,dtype=float).tolist()
        if timestamp is not None: packet['timestamp']=timestamp
        return packet

    def push(self,samples,**kwargs):
        packet=self.packet(samples,**kwargs)
        result=self.request('/api/ingest',packet)
        self.sequence+=1
        return result

    def push_udp(self,samples,host='127.0.0.1',port=9001,**kwargs):
        packet=self.packet(samples,**kwargs)
        if self.token: packet['token']=self.token
        payload=json.dumps(packet,allow_nan=False).encode('utf-8')
        if len(payload)>65507: raise ValueError('UDP 한도보다 큽니다. 실제 파형을 더 작은 패킷으로 나누세요.')
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock: sock.sendto(payload,(host,port))
        self.sequence+=1

    def stop(self): return self.request('/api/stop',{})

