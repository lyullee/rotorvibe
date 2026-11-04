"""Forward an existing measured NPZ to the live transport. This is not a signal generator."""
import argparse
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vibration import bootstrap
from vibration.client import VibrationClient
import numpy as np


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('file',type=Path); p.add_argument('--url',default='http://127.0.0.1:8765')
    p.add_argument('--token',default=''); p.add_argument('--fs',type=float)
    p.add_argument('--unit',choices=['unknown','g','m/s^2'],default=None)
    p.add_argument('--udp-port',type=int,default=0)
    p.add_argument('--chunk-seconds',type=float,default=0.1)
    args=p.parse_args()
    with np.load(args.file,allow_pickle=False) as d:
        a=d['vibration']; fs=args.fs or float(d['sample_rate_hz'])
        unit=args.unit or (str(d['unit'].item()) if 'unit' in d else 'unknown')
        rpm=float(d['rpm']) if 'rpm' in d else None
    if a.ndim==1: a=a[:,None]
    if not 0<args.chunk_seconds<=1: p.error('--chunk-seconds 범위는 0~1초입니다.')
    client=VibrationClient(args.url,args.token)
    client.start(fs,a.shape[1],unit,rpm)
    chunk=min(50000,max(1,int(fs*args.chunk_seconds))); started=time.monotonic()
    for i in range(0,len(a),chunk):
        block=a[i:i+chunk]
        if args.udp_port: client.push_udp(block,port=args.udp_port,rpm=rpm)
        else: client.push(block,rpm=rpm)
        delay=started+(i+len(block))/fs-time.monotonic()
        if delay>0: time.sleep(delay)
    print(f'전송 완료: {len(a)} measured samples, {fs} Hz, {a.shape[1]} channels')

if __name__=='__main__': main()
