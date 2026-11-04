"""Loopback transport, lifecycle and hostile-file regressions; no datasets needed."""
import io,json,math,socket,threading,time,tempfile,unittest,http.client
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode
import numpy as np
from vibration.config import AnalysisConfig
from vibration import storage,datasets,engine
from vibration.server import Application,Handler
from http.server import ThreadingHTTPServer

class ServiceContracts(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)/'nested'/'runtime'
        self.patches=[patch.object(m,'RUNTIME',self.root) for m in (storage,datasets,engine)]
        for p in self.patches: p.start()
        self.app=Application('local-test-key')
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler); self.server.app=self.app; self.server.daemon_threads=True
        self.server_errors=[]
        self.server.handle_error=lambda *_:self.server_errors.append('unhandled request thread error')
        self.thread=threading.Thread(target=lambda:self.server.serve_forever(poll_interval=.01),daemon=True); self.thread.start()
        self.port=self.server.server_address[1]

    def tearDown(self):
        self.app.close(); self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2)
        for p in reversed(self.patches): p.stop()
        self.tmp.cleanup()
        self.assertEqual(self.server_errors,[])

    def request(self,path,body=None,*,headers=None,method=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=3)
        supplied={'X-API-Key':'local-test-key'}
        if body is not None: body=json.dumps(body).encode(); supplied['Content-Type']='application/json'
        supplied.update(headers or {})
        try:
            connection.request(method or ('POST' if body is not None else 'GET'),path,body,headers=supplied)
            response=connection.getresponse(); data=response.read()
            return response.status,data
        finally: connection.close()

    def start(self):
        c=AnalysisConfig(unit='m/s^2',window_seconds=.25,hop_seconds=.25)
        status,_=self.request('/api/live/start',{'config':c.to_dict()}); self.assertEqual(status,200)

    def test_service_closes_worker_and_port(self):
        self.app.start_udp('127.0.0.1',0); self.app.close(); self.app.close()
        self.assertFalse(self.app.engine.worker_thread.is_alive())
        self.assertFalse(self.app._udp_thread.is_alive())

    def test_auth_origin_and_content_type_are_enforced(self):
        self.assertEqual(self.request('/api/state',headers={'X-API-Key':'bad'})[0],401)
        self.assertEqual(self.request('/api/live/start',{},headers={'Origin':'https://unrelated.invalid'})[0],403)
        self.assertEqual(self.request('/api/live/start',{},headers={'Content-Type':'text/plain'})[0],400)

    def test_unicode_token_can_be_checked_without_server_error(self):
        self.app.token='검증키'
        self.assertEqual(self.request('/api/state?'+urlencode({'token':'검증키'}),headers={'X-API-Key':''})[0],200)

    def test_api_roundtrip_and_unknown_routes(self):
        self.assertEqual(self.request('/')[0],200)
        self.assertEqual(self.request('/api/no_such_endpoint')[0],404)
        self.assertEqual(self.request('/api/no_such_endpoint',{})[0],404)
        self.start(); self.assertEqual(self.request('/api/ingest',{'samples':[1,2],'unit':'g'})[0],400)

    def test_UDP_data_and_invalid_auth(self):
        self.start(); info=self.app.start_udp('127.0.0.1',0)
        a=np.sin(2*np.pi*100*np.arange(3000)/12000)
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
            bad=json.dumps({'token':'bad','samples':[0]}).encode(); sock.sendto(bad,('127.0.0.1',info['port']))
            for i in range(2):
                packet={'token':'local-test-key','samples':a[i*1500:(i+1)*1500].tolist(),'unit':'m/s^2','sequence':i}
                sock.sendto(json.dumps(packet).encode(),('127.0.0.1',info['port']))
        deadline=time.monotonic()+3
        while time.monotonic()<deadline and self.app.engine.latest is None: time.sleep(.01)
        self.assertIsNotNone(self.app.engine.latest)
        self.assertAlmostEqual(self.app.engine.latest['metrics']['rms'],1/math.sqrt(2),places=10)
        self.assertEqual(self.app.udp['received'],2); self.assertEqual(self.app.udp['errors'],1)

    def test_SSE_receives_state_then_analysis(self):
        self.start(); connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=3)
        try:
            connection.request('GET','/api/stream',headers={'X-API-Key':'local-test-key'})
            response=connection.getresponse(); self.assertEqual(response.status,200)
            initial=response.readline(); self.assertEqual(json.loads(initial[6:])['type'],'state'); response.readline()
            a=np.sin(2*np.pi*100*np.arange(3000)/12000)
            self.assertEqual(self.request('/api/ingest',{'samples':a.tolist(),'unit':'m/s^2'})[0],200)
            message=json.loads(response.readline()[6:]); self.assertEqual(message['type'],'frame')
            self.assertAlmostEqual(message['data']['metrics']['rms'],1/math.sqrt(2),places=10)
            self.app.close()
        finally: connection.close()

    def test_truncated_body_and_chunked_request_rejected(self):
        for headers,body in [(b'Content-Length: 100\r\n',b'{}'),(b'Transfer-Encoding: chunked\r\n',b'0\r\n\r\n')]:
            with self.subTest(headers=headers),socket.create_connection(('127.0.0.1',self.port),timeout=3) as sock:
                sock.sendall(b'POST /api/config HTTP/1.1\r\nHost: localhost\r\nX-API-Key: local-test-key\r\nContent-Type: application/json\r\n'+headers+b'\r\n'+body)
                sock.shutdown(socket.SHUT_WR); reply=sock.recv(4096)
                self.assertIn(b' 400 ',reply.split(b'\r\n',1)[0])

    def test_sequence_gap_holds_quality(self):
        self.start(); a=np.sin(2*np.pi*100*np.arange(1500)/12000)
        for sequence in (0,2): self.request('/api/ingest',{'samples':a.tolist(),'unit':'m/s^2','sequence':sequence})
        deadline=time.monotonic()+3
        while time.monotonic()<deadline and self.app.engine.latest is None: time.sleep(.01)
        self.assertIn('packet_discontinuity_in_window',self.app.engine.latest['quality']['flags'])

    def test_new_generation_cannot_reuse_old_packets(self):
        self.start(); self.app.engine.ingest({'samples':(100*np.sin(2*np.pi*100*np.arange(3000)/12000)).tolist(),'unit':'m/s^2'})
        self.start(); target_session=self.app.engine.session_id
        self.app.engine.ingest({'samples':np.sin(2*np.pi*100*np.arange(3000)/12000).tolist(),'unit':'m/s^2'})
        deadline=time.monotonic()+3
        while time.monotonic()<deadline and self.app.engine.latest is None: time.sleep(.01)
        self.assertEqual(self.app.engine.latest['session_id'],target_session)
        self.assertAlmostEqual(self.app.engine.latest['metrics']['rms'],1/math.sqrt(2),places=10)

class FileContracts(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)/'runtime'
        self.patch=patch.object(datasets,'RUNTIME',self.root); self.patch.start()
        self.catalog=object.__new__(datasets.DatasetCatalog)

    def tearDown(self): self.patch.stop(); self.tmp.cleanup()

    def test_invalid_imports_leave_no_uploaded_files(self):
        for name,data in [('empty.csv',b'\n'),('bad.npz',b'not zip'),('bad.npy',b'not numpy')]:
            with self.subTest(name=name),self.assertRaises(ValueError): self.catalog.imported(name,data,12000)
        self.assertFalse((self.root/'uploads').exists())

    def test_pickle_object_and_allocation_header_rejected(self):
        obj=io.BytesIO(); np.save(obj,np.array([{'not':'numeric'}],dtype=object))
        huge=io.BytesIO(); np.lib.format.write_array_header_1_0(huge,{'descr':'<f8','fortran_order':False,'shape':(10**9,1)})
        for data in (obj.getvalue(),huge.getvalue()):
            with self.subTest(size=len(data)),self.assertRaises(ValueError): self.catalog.imported('unsafe.npy',data,12000)

    def test_NPZ_and_header_CSV_roundtrip(self):
        a=np.arange(1000,dtype=float)[:,None]; buffer=io.BytesIO()
        np.savez_compressed(buffer,vibration=a,sample_rate_hz=12000,unit='m/s^2')
        x,meta=self.catalog.imported('measured.npz',buffer.getvalue()); np.testing.assert_array_equal(x,a)
        self.assertEqual(meta['unit'],'m/s^2')
        x,_=self.catalog.imported('one.csv',b'a\n1\n2\n3\n',12000)
        self.assertEqual(x.shape,(3,1))

    def test_invalid_axis_skip_and_zero_channels_rejected(self):
        for opts in ({'channels_axis':2},{'skip_columns':-1},{'skip_columns':2}):
            with self.subTest(opts=opts),self.assertRaises(ValueError): self.catalog.imported('a.csv',b'1,2\n3,4\n',12000,**opts)

    def test_path_traversal_is_rejected(self):
        for path in ('../outside','..\\outside','C:/Windows/win.ini'):
            with self.subTest(path=path),self.assertRaises(ValueError): datasets.local_path(self.root,path)

if __name__=='__main__': unittest.main()
