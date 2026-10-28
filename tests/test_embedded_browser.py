"""Real embedded-browser tests against a loopback fixture, never real accounts.

Set SCRMAPS_QT_TEST=1 to opt in (requires a GUI platform or Qt offscreen).
"""
import os,sys,threading,time,tempfile,json
import unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

FORM='''<!doctype html><meta charset="utf-8"><header><button>로그아웃</button></header>
<h1>Embedded browser test</h1><form><input name="code" minlength="9" maxlength="9"><p id="message"></p><button type="submit">인증 코드 등록</button></form>
<section><p>내 세이브 코드</p><code id="save">AAAAABBBB</code></section>
<script>document.querySelector('form').onsubmit=async e=>{e.preventDefault();
const r=await fetch(location.pathname,{method:'POST',body:document.querySelector('input').value});const d=await r.json();
const m=document.querySelector('#message');if(d.error){m.className='text-red-600';m.textContent=d.error;}
else{m.className='text-emerald-700';m.textContent='제출되었습니다';document.querySelector('#save').textContent=d.save;}};</script>'''
LOGIN='''<!doctype html><meta charset="utf-8"><header><a href="/login">로그인</a></header><h1>Fixture login only</h1><button id="signin" onclick="location.href='/signed-in'">Fake sign in</button>'''


@unittest.skipUnless(os.environ.get('SCRMAPS_QT_TEST')=='1','Enable SCRMAPS_QT_TEST for embedded GUI integration')
class EmbeddedBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
        cls.app=QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def pump(self,condition,timeout=12):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            self.app.processEvents();time.sleep(.015)
            if condition():return
        self.fail('Embedded browser condition timed out')

    def test_review_shows_original_crop_and_observed_candidates_without_submitting(self):
        from desktop import Window
        from recognition import Recognition
        from worker import Worker
        with tempfile.TemporaryDirectory() as directory,patch('desktop.fetch_maps',return_value=[]),patch.object(Worker,'start'):
            window=Window(Path(directory),'http://127.0.0.1:9',quit_on_close=False);window.show()
            try:
                path=Path(__file__).parent/'fixtures'/'ocr-14.png'
                result=Recognition('B8S5Z2G6R',False,.99,['B8S5Z2G6R','B855Z2G6R'],'testmap',(231,133,84,11),'3번째 글자를 확인해 주세요.',[3])
                window.events.put(('recognition',dict(result=result,cfg={'project':'testmap','nickname':'PlayerA'},image_hash='fixture',path=str(path))))
                window.events.put(('stage',dict(phase='review',text=result.message)));window.drain()
                self.app.processEvents()
                self.assertFalse(window.review.isHidden());self.assertFalse(window.ocr_preview.pixmap().isNull())
                self.assertLessEqual(window.ocr_preview.pixmap().width(),680)
                self.assertEqual(window.auth_candidates.count(),2);self.assertFalse(window.auth_candidates.isHidden())
                self.assertEqual(window.auth.text(),'B8S5Z2G6R')
                window.auth_candidates.activated.emit(1)
                self.assertEqual(window.auth.text(),'B855Z2G6R');self.assertFalse(any(c[0]=='submit' for c in list(window.commands.queue)))
            finally:
                window.close();self.pump(lambda:window.browser.disposed,6)

    def test_login_resume_duplicate_guard_and_saved_session(self):
        from desktop import Window
        from PySide6.QtCore import QUrl,QCoreApplication,QEvent
        posts=[];mode={'error':False}
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_args):pass
            def do_GET(self):
                logged='fixture_session=yes' in self.headers.get('Cookie','')
                self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8')
                if self.path=='/signed-in':
                    self.send_header('Set-Cookie','fixture_session=yes; Path=/; HttpOnly');logged=True
                self.end_headers();self.wfile.write((FORM if logged else LOGIN).encode())
            def do_POST(self):
                value=self.rfile.read(int(self.headers.get('Content-Length','0'))).decode();posts.append(value)
                self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
                self.wfile.write(json.dumps({'error':'fixture server rejected'} if mode['error'] else {'save':'9G5C4BA5R'}).encode())
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        with tempfile.TemporaryDirectory() as directory,patch('desktop.fetch_maps',return_value=[]):
            data=Path(directory);window=Window(data,base,quit_on_close=False);window.show()
            def capture(name):
                destination=os.environ.get('SCRMAPS_QT_CAPTURE')
                if destination:
                    path=Path(destination);path.mkdir(parents=True,exist_ok=True);self.app.processEvents();window.grab().save(str(path/(name+'.png')))
            try:
                window.nickname.setText('PlayerA')
                self.pump(lambda:window.browser.login_state is False)
                cfg={'project':'testmap','nickname':'PlayerA','auto':True}
                window.command('submit',{'auth':'ZQWMD4FFZ','cfg':cfg})
                self.pump(lambda:len(window.worker.waiting_login)==1 and window.browser.main.url().path()=='/login')
                self.assertEqual(posts,[])
                self.assertEqual(window.tabs.currentIndex(),1)
                capture('login')
                window.browser.main.page().runJavaScript("document.querySelector('#signin').click()")
                self.pump(lambda:window.code.text()=='9G5C4BA5R',20)
                self.assertEqual(posts,['ZQWMD4FFZ'])
                self.assertEqual(len(window.worker.waiting_login),0)
                capture('saved')
                # Exercise the real queue -> GUI -> sender route while the
                # window is minimized. OS detection/injection is mocked here.
                from test_key_sender import FakeKeyboard
                keyboard=FakeKeyboard();keyboard.describe_target=lambda _: 'StarCraft · fixture'
                window.typer.backend=keyboard;window.showMinimized()
                with patch.object(window.typer,'start',return_value=True) as start:
                    window.events.put(('hotkey',{'key':'F8','target':keyboard.target()}))
                    self.pump(lambda:start.called)
                    start.assert_called_once_with('9G5C4BA5R',expected_target=keyboard.target())
                    self.assertIn('F8 감지',window.hotkey_status.text())
                with patch.object(window.typer,'stop') as stop:
                    window.events.put(('hotkey',{'key':'F9'}));self.pump(lambda:stop.called)
                    stop.assert_called_once()
                window.current_save=None
                window.events.put(('hotkey',{'key':'F8','target':keyboard.target()}))
                self.pump(lambda:'먼저 발급된 코드' in window.typing_status.text())
                window.current_save='9G5C4BA5R';window.showNormal()
                window.command('submit',{'auth':'ZQWMD4FFZ','cfg':cfg})
                self.pump(lambda:window.commands.empty())
                for _ in range(100):self.app.processEvents();time.sleep(.01)
                self.assertEqual(posts,['ZQWMD4FFZ'])
                mode['error']=True
                window.command('submit',{'auth':'ABCDE2345','cfg':cfg})
                self.pump(lambda:'fixture server rejected' in window.status.text())
                for _ in range(200):self.app.processEvents();time.sleep(.01)
                self.assertEqual(posts,['ZQWMD4FFZ','ABCDE2345'])
                self.assertEqual(len(window.worker.waiting_login),0)
                window.close();self.pump(lambda:window.allow_close)
                for _ in range(40):
                    self.app.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);time.sleep(.02)
                # ForcePersistentCookies also retains the fixture's session-only
                # cookie, proving that a second app window can reuse its profile.
                mode['error']=False
                second=Window(data,base,quit_on_close=False);second.show()
                try:
                    self.pump(lambda:second.browser.login_state is True)
                    self.assertEqual(posts,['ZQWMD4FFZ','ABCDE2345'])
                finally:
                    second.close();self.pump(lambda:second.allow_close)
                    for _ in range(20):self.app.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);time.sleep(.02)
            finally:
                if not window.allow_close:
                    window.close();self.pump(lambda:window.allow_close)
                server.shutdown();server.server_close()


if __name__=='__main__':unittest.main()
