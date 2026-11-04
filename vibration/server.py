"""HTTP/SSE service and device-neutral live input transport."""
import argparse
import csv
import hmac
import io
import json
import mimetypes
import os
import queue
import socket
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
from .bootstrap import PROJECT, RUNTIME
from .storage import Storage
from .datasets import DatasetCatalog, local_path
from .bearings import Bearings
from .models import ModelRegistry
from .engine import Engine


class Application:
    def __init__(self,token=''):
        self.token=token; self.storage=Storage(); self.catalog=DatasetCatalog(); self.bearings=Bearings()
        for saved in self.storage.documents('custom_bearing'):
            try: self.bearings.custom(self.storage.get('custom_bearing',saved['name']))
            except (ValueError,KeyError): pass
        self.models=ModelRegistry(self.storage,self.catalog)
        self.engine=Engine(self.storage,self.catalog,self.bearings,self.models)
        self.udp={'enabled':False,'received':0,'errors':0,'last_error':None}
        self.loading=threading.Lock()
        self.closing=threading.Event(); self._udp_socket=None; self._udp_thread=None

    def start_udp(self,host,port):
        if self.closing.is_set() or self._udp_socket is not None: raise ValueError('UDP service is closed or already started.')
        sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        try: sock.bind((host,port)); sock.settimeout(.2)
        except OSError: sock.close(); raise
        self._udp_socket=sock
        self.udp.update(enabled=True,host=host,port=sock.getsockname()[1])
        def loop():
            try:
                while not self.closing.is_set():
                    try: packet,_=sock.recvfrom(65507)
                    except socket.timeout: continue
                    except OSError:
                        if self.closing.is_set(): break
                        raise
                    try:
                        d=json.loads(packet)
                        if self.token and not hmac.compare_digest(str(d.pop('token','')).encode(),self.token.encode()):
                            raise ValueError('API 키가 일치하지 않습니다.')
                        self.engine.ingest(d); self.udp['received']+=1
                    except Exception as e:
                        self.udp['errors']+=1; self.udp['last_error']=str(e)
            except OSError as e:
                self.udp.update(enabled=False,last_error=str(e))
            finally: self.udp['enabled']=False; sock.close()
        self._udp_thread=threading.Thread(target=loop,daemon=True,name='udp-input')
        self._udp_thread.start()
        return dict(self.udp)

    def close(self):
        if self.closing.is_set(): return
        self.closing.set()
        self.engine.hub.publish('shutdown',{'reason':'service_closed'})
        if self._udp_socket is not None: self._udp_socket.close()
        if self._udp_thread is not None: self._udp_thread.join(timeout=2)
        self.engine.close(); self.models.close(); self.storage.close()


class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    server_version='VibrationWorkbench'

    @property
    def app(self): return self.server.app

    def handle(self):
        try: super().handle()
        except (ConnectionError,TimeoutError): pass  # Normal client disconnect, including SSE teardown.

    def log_message(self,fmt,*args):
        # Never log URL query values, uploaded arrays or transport credentials.
        print(f'[{self.log_date_time_string()}] {self.command} {urlsplit(self.path).path}',flush=True)

    def _json(self,value,status=200):
        data=json.dumps(value,ensure_ascii=False,allow_nan=False).encode()
        self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(data))); self.send_header('Cache-Control','no-store')
        self.end_headers(); self.wfile.write(data)

    def _bytes(self,data,content_type,status=200,filename=None):
        self.send_response(status); self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('X-Content-Type-Options','nosniff')
        if filename: self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
        self.end_headers(); self.wfile.write(data)

    def _auth(self,q):
        if not self.app.token: return True
        supplied=self.headers.get('X-API-Key','') or q.get('token',[''])[0]
        return hmac.compare_digest(str(supplied).encode(),self.app.token.encode())

    def _read(self,limit=8*1024*1024):
        if self.headers.get('Transfer-Encoding'):
            self.close_connection=True
            raise ValueError('Transfer-Encoding is unsupported; use Content-Length.')
        try: n=int(self.headers.get('Content-Length','0'))
        except ValueError: raise ValueError('Content-Length가 올바르지 않습니다.')
        if not 0<n<=limit:
            self.close_connection=True
            raise ValueError(f'요청 크기 제한: {limit//(1024*1024)} MiB')
        data=self.rfile.read(n)
        if len(data)!=n:
            self.close_connection=True
            raise ValueError('Request body shorter than Content-Length.')
        return data

    def do_GET(self):
        try:
            p=urlsplit(self.path); q=parse_qs(p.query)
            if p.path.startswith('/api/'):
                if not self._auth(q): return self._json({'error':'API 키가 필요합니다.'},401)
                return self._get(p.path,q)
            root=Path(__file__).parent/'ui'; path=local_path(root,'index.html' if p.path=='/' else p.path.lstrip('/'))
            if not path.is_file(): return self._json({'error':'파일이 없습니다.'},404)
            return self._bytes(path.read_bytes(),mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
        except (BrokenPipeError,ConnectionResetError): pass
        except (ValueError,KeyError,TypeError) as e: self._json({'error':str(e)},400)
        except Exception as e: self._json({'error':str(e)},500)

    def _get(self,path,q):
        one=lambda k,default='':q.get(k,[default])[0]
        e=self.app.engine
        if path=='/api/state': return self._json({**e.state(),'udp':self.app.udp})
        if path=='/api/latest': return self._json(e.latest)
        if path=='/api/stream': return self._stream()
        if path=='/api/datasets': return self._json(self.app.catalog.search(one('q'),one('dataset'),int(one('offset','0')),int(one('limit','60'))))
        if path=='/api/dataset': return self._json(self.app.catalog.details(one('id')))
        if path=='/api/bearings': return self._json(self.app.bearings.rows)
        if path=='/api/bearing/frequencies': return self._json(self.app.bearings.frequencies(one('id'),float(one('rpm'))))
        if path=='/api/baselines': return self._json(self.app.storage.documents('baseline'))
        if path=='/api/models': return self._json({'items':self.app.storage.documents('classifier'),'job':self.app.models.job,
                                                  'active':self.app.models.active['name'] if self.app.models.active else None})
        if path=='/api/configurations': return self._json(self.app.storage.documents('configuration'))
        if path=='/api/history': return self._json(self.app.storage.history(one('kind','events'),int(one('limit','200')),one('session') or None))
        if path=='/api/trend': return self._json(e.history)
        if path=='/api/lives':
            return self._json([{k:v for k,v in r.items() if not k.endswith('_series')} for r in self.app.catalog.lives.values()])
        if path=='/api/life':
            id=one('id'); row=self.app.catalog.lives.get(id)
            if row is None: raise ValueError('수명 이력을 찾을 수 없습니다.')
            # This endpoint is an explicit offline history viewer, never a model training input.
            return self._json({'bearing':row['bearing'],'role':row['role'],'rms_series':row['nominal_rms_series'],
                               'snapshot_interval_seconds':10,'note':'전체 이력 보기입니다. 미래 구간은 온라인 추정에 사용하지 않습니다.'})
        if path=='/api/export':
            session=one('session') or e.session_id
            rows=self.app.storage.history('frames',20000,session)
            if one('format','json')=='csv':
                output=io.StringIO(); writer=csv.writer(output)
                writer.writerow(['timestamp','sample_end','rms_ac','unit','kurtosis_pearson','velocity_rms_mm_s','anomaly_score','alarm','rpm'])
                for r in reversed(rows):
                    p=r['payload']; m=p['metrics']
                    writer.writerow([r['timestamp'],r['sample_end'],m['rms'],m['unit'],m['kurtosis'],m['velocity_rms_mm_s'],
                                     p['baseline'].get('score'),p['alarm']['level'],p.get('rpm')])
                return self._bytes(output.getvalue().encode('utf-8-sig'),'text/csv; charset=utf-8',filename='vibration-analysis.csv')
            return self._bytes(json.dumps({'session':session,'frames':list(reversed(rows)),
                        'events':self.app.storage.history('events',20000,session)},ensure_ascii=False).encode(),
                        'application/json',filename='vibration-analysis.json')
        if path.startswith('/api/recordings/'):
            name=path.removeprefix('/api/recordings/')
            file=local_path(RUNTIME/'recordings',name)
            if not file.is_file() or file.suffix!='.npz': raise ValueError('저장 파형을 찾을 수 없습니다.')
            return self._bytes(file.read_bytes(),'application/octet-stream',filename=file.name)
        if path=='/api/guide':
            file=PROJECT/'data/gap_supplement/추가자료_기능별판단.txt'
            if not file.is_file(): return self._json({'error':'Optional local dataset guide is not installed.'},404)
            return self._bytes(file.read_bytes(),'text/plain; charset=utf-8')
        return self._json({'error':'알 수 없는 API입니다.'},404)

    def _stream(self):
        q=self.app.engine.hub.subscribe()
        try:
            self.send_response(200); self.send_header('Content-Type','text/event-stream; charset=utf-8')
            self.send_header('Cache-Control','no-cache'); self.send_header('Connection','keep-alive'); self.end_headers()
            initial=json.dumps({'type':'state','data':self.app.engine.state()},ensure_ascii=False)
            self.wfile.write(('data: '+initial+'\n\n').encode()); self.wfile.flush()
            while not self.app.closing.is_set():
                try: message=q.get(timeout=15); content='data: '+message+'\n\n'
                except queue.Empty: content=': heartbeat\n\n'
                self.wfile.write(content.encode()); self.wfile.flush()
        except (BrokenPipeError,ConnectionResetError,TimeoutError): pass
        finally:
            self.close_connection=True
            self.app.engine.hub.unsubscribe(q)

    def do_POST(self):
        try:
            p=urlsplit(self.path); q=parse_qs(p.query)
            if not self._auth(q):
                self.close_connection=True
                return self._json({'error':'API 키가 필요합니다.'},401)
            origin=self.headers.get('Origin')
            if origin and urlsplit(origin).netloc!=self.headers.get('Host'):
                self.close_connection=True
                return self._json({'error':'다른 사이트에서의 변경 요청은 허용하지 않습니다.'},403)
            if p.path=='/api/upload':
                one=lambda k,default='':q.get(k,[default])[0]
                fs=one('fs')
                a,meta=self.app.catalog.imported(one('filename'),self._read(64*1024*1024),
                    float(fs) if fs else None,one('unit','unknown'),int(one('axis','1')),int(one('skip','0')))
                return self._json(self.app.engine.replay(meta['id'],loaded=(a,meta)))
            if not self.headers.get('Content-Type','').startswith('application/json'):
                # Consume a bounded, declared body before closing: Windows may reset
                # a socket with unread bytes before the client receives the 400.
                self._read()
                raise ValueError('Content-Type: application/json이 필요합니다.')
            d=json.loads(self._read())
            if not isinstance(d,dict): raise ValueError('JSON 객체가 필요합니다.')
            e=self.app.engine
            if p.path=='/api/config': result=e.configure(d)
            elif p.path=='/api/live/start': result=e.live(d.get('config'))
            elif p.path=='/api/ingest': result=e.ingest(d)
            elif p.path=='/api/replay':
                if not self.app.loading.acquire(blocking=False): raise ValueError('다른 파일을 불러오는 중입니다.')
                try: result=e.replay(d['id'],d.get('speed',1),d.get('loop',False),d.get('snapshot',0),sequence=bool(d.get('sequence',False)))
                finally: self.app.loading.release()
            elif p.path=='/api/stop': result=e.stop()
            elif p.path=='/api/window/save': result=e.save_window()
            elif p.path=='/api/baseline/start': result=e.baseline_start(str(d.get('name','정상 기준')),d.get('windows',60))
            elif p.path=='/api/baseline/load': result=e.baseline_load(d['name'])
            elif p.path=='/api/baseline/cancel':
                with e.lock: e.baseline.collecting=False
                result=e.state()
            elif p.path=='/api/model/train': result=self.app.models.train(str(d.get('name','Brito 벤치 분류기')))
            elif p.path=='/api/model/load': result=self.app.models.load(d['name'])
            elif p.path=='/api/bearing/custom':
                result=self.app.bearings.custom(d); self.app.storage.save('custom_bearing',result['model'],d)
            elif p.path=='/api/config/save':
                self.app.storage.save('configuration',str(d['name']),{'config':e.config.to_dict(),'summary':{'condition':e.config.condition}})
                result={'saved':True}
            elif p.path=='/api/config/load': result=e.configure(self.app.storage.get('configuration',d['name'])['config'])
            else: return self._json({'error':'알 수 없는 API입니다.'},404)
            return self._json(result)
        except (ValueError,KeyError,TypeError,OverflowError) as ex:
            self.close_connection=True
            self._json({'error':str(ex)},429 if isinstance(ex,OverflowError) else 400)
        except (BrokenPipeError,ConnectionResetError): pass
        except Exception as ex: self._json({'error':str(ex)},500)


def main():
    parser=argparse.ArgumentParser(description='실시간 진동분석 워크벤치')
    parser.add_argument('--host',default='127.0.0.1'); parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--udp-port',type=int,default=0)
    parser.add_argument('--token',default=os.environ.get('VIBRATION_API_TOKEN',''))
    args=parser.parse_args()
    if args.host not in ['127.0.0.1','localhost','::1'] and not args.token:
        parser.error('네트워크 공개 바인딩에는 --token 또는 VIBRATION_API_TOKEN을 지정하세요.')
    app=Application(args.token)
    if args.udp_port: app.start_udp(args.host,args.udp_port)
    server=ThreadingHTTPServer((args.host,args.port),Handler); server.app=app; server.daemon_threads=True
    print(f'Vibration Workbench http://{args.host}:{args.port}',flush=True)
    print(f'공개 기록 {len(app.catalog.rows):,}개 / 베어링 {len(app.bearings.rows)}개',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: app.close(); server.server_close()

if __name__=='__main__': main()

