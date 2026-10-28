import os,sys,json,queue,sqlite3,subprocess,tempfile,threading,time,unittest
import errno
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

class CacheTemporaryDirectory(tempfile.TemporaryDirectory):
    def cleanup(self):
        for attempt in range(100):
            try:return super().cleanup()
            except OSError as exc:
                if exc.errno!=errno.ENOTEMPTY or attempt==99:raise
                time.sleep(.01)

@unittest.skipUnless(os.environ.get('SCRMAPS_QT_TEST')=='1','Enable SCRMAPS_QT_TEST for real application shutdown tests')
class ShutdownTests(unittest.TestCase):
    def test_real_process_exits_and_immediately_reopens_same_profile(self):
        for mode in ('instant','idle','navigation','post'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as folder:
                data=Path(folder);posts=[];release=threading.Event()
                from test_embedded_browser import FORM
                class Handler(BaseHTTPRequestHandler):
                    def log_message(self,*args):pass
                    def do_GET(self):
                        if self.path=='/navigation':
                            (data/'navigation-received').write_text('received');release.wait(8)
                        self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers()
                        try:self.wfile.write(FORM.encode())
                        except (BrokenPipeError,ConnectionResetError):pass
                    def do_POST(self):
                        posts.append(self.rfile.read(int(self.headers.get('Content-Length',0))))
                        (data/'post-received').write_text('received')
                        release.wait(8)
                        self.send_response(200);self.end_headers()
                        try:self.wfile.write(b'{"save":"9G5C4BA5R"}')
                        except (BrokenPipeError,ConnectionResetError):pass
                server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
                thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                base=f'http://127.0.0.1:{server.server_port}'
                try:
                    for attempt,current_mode in enumerate((mode,'idle')):
                        proc=subprocess.Popen([sys.executable,str(Path(__file__).with_name('shutdown_child.py')),str(data),base,current_mode],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                        start=time.monotonic()
                        try:out,err=proc.communicate(timeout=7)
                        except subprocess.TimeoutExpired:
                            proc.kill();out,err=proc.communicate(timeout=2)
                            self.fail('X did not terminate the app process: '+out+'\n'+err[-2500:])
                        self.assertEqual(proc.returncode,0,err[-2500:])
                        self.assertIn('CLOSE_REQUESTED',out)
                        self.assertLess(time.monotonic()-start,6)
                        self.assertTrue((data/'settings.json').exists())
                    if mode in {'navigation','post'}:
                        with sqlite3.connect(data/'history.sqlite3') as db:
                            status=db.execute('SELECT status FROM runs WHERE project=?',(mode,)).fetchone()[0]
                        self.assertIn(status,{'check','submitting'})
                    self.assertEqual(len(posts),1 if mode=='post' else 0)
                finally:release.set();server.shutdown();server.server_close()

    def test_closing_bridge_wakes_pending_call_and_rejects_queued_work(self):
        from PySide6.QtCore import Qt,QCoreApplication,QEvent
        from PySide6.QtWidgets import QApplication
        from browser_panel import BrowserBridge,BrowserPanel
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
        app=QApplication.instance() or QApplication([]);app.setQuitOnLastWindowClosed(False)
        with CacheTemporaryDirectory() as folder:
            panel=BrowserPanel(Path(folder));bridge=BrowserBridge(panel);result=[]
            def wait_for_browser():
                try:bridge.call('navigate',{'url':'https://www.scrmaps.com/'},30)
                except RuntimeError as exc:result.append(str(exc))
            thread=threading.Thread(target=wait_for_browser);thread.start()
            deadline=time.monotonic()+1
            while not bridge.pending and time.monotonic()<deadline:time.sleep(.005)
            self.assertTrue(bridge.pending)
            bridge.close();thread.join(timeout=.3)
            self.assertFalse(thread.is_alive());self.assertIn('종료',result[0])
            with self.assertRaisesRegex(RuntimeError,'종료'):bridge.call('show')
            panel.dispose();deadline=time.monotonic()+2
            while not panel.disposed and time.monotonic()<deadline:
                app.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
            self.assertTrue(panel.disposed)
            self.assertFalse(panel.load_started)
            panel.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)

if __name__=='__main__':unittest.main()
