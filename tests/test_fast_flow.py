"""Real Qt/HTTP fixtures for automatic submit and result capture; no accounts."""
import os,sys,json,time,threading,tempfile,unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

@unittest.skipUnless(os.environ.get('SCRMAPS_QT_TEST')=='1','Enable SCRMAPS_QT_TEST for Qt/HTTP fixtures')
class FastFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
        cls.app=QApplication.instance() or QApplication([]);cls.app.setQuitOnLastWindowClosed(False)
    def pump(self,condition,timeout=8):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            self.app.processEvents();time.sleep(.005)
            if condition():return
        self.fail('Local fixture timed out')
    def scenario(self,kind):
        from desktop import Window
        from worker import Worker
        from core import History
        from recognition import Recognition
        from PySide6.QtCore import QCoreApplication,QEvent
        from PySide6.QtWebEngineCore import QWebEngineProfile
        posts=[];gets=[];release=threading.Event();state={'code':'AAAAABBBB'}
        if kind=='recover':state['code']='9G5C4BA5R'
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                gets.append(self.path)
                if self.path=='/slow.svg':
                    release.wait(5);body=b'<svg xmlns="http://www.w3.org/2000/svg"/>';mime='image/svg+xml'
                elif self.path=='/cr2':
                    body=b'<header>Logged in</header><a href="/cr2/board">Board</a>';mime='text/html; charset=utf-8'
                else:
                    result=('' if kind=='refresh' and not posts else
                            '<section><div><h3><span>내 세이브 코드</span></h3></div><div><div><input readonly id="save" value="'+state['code']+'"></div></div></section>')
                    if kind=='copy':result='<section><h3>내 세이브 코드</h3><p>•••••••••</p><button id="copy" onclick="navigator.clipboard.writeText(window.latestCode)">복사</button></section>'
                    html='''<!doctype html><meta charset="utf-8"><header><button>로그아웃</button></header>
<form><input name="code" minlength="9" maxlength="9"><p id="message"></p><button type="submit">등록</button></form>'''+result+'''
<img src="/slow.svg"><script>window.latestCode='AAAAABBBB';document.querySelector('form').onsubmit=async e=>{e.preventDefault();const button=e.target.querySelector('button');button.disabled=true;
const r=await fetch(location.pathname,{method:'POST',body:e.target.querySelector('input').value}),d=await r.json();
const message=document.querySelector('#message');if(d.error){message.className='text-red-600';message.textContent=d.error;}
else{window.latestCode=d.save;message.className='text-green-600';message.textContent='제출되었습니다';const out=document.querySelector('#save');if(out)out.value=d.save;}
button.disabled=false;};</script>'''
                    body=html.encode();mime='text/html; charset=utf-8'
                self.send_response(200);self.send_header('Content-Type',mime);self.end_headers()
                try:self.wfile.write(body)
                except (BrokenPipeError,ConnectionResetError):pass
            def do_POST(self):
                posts.append(self.rfile.read(int(self.headers.get('Content-Length',0))).decode());time.sleep(.08)
                state['code']='9G5C4BA5R';self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
                response=({'error':'fixture rejected'} if kind=='error' else {'error':'이미 순위표에 올라가 있는 기록과 같은 코드입니다.'} if kind=='recorded' else {'save':state['code']})
                self.wfile.write(json.dumps(response).encode())
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
        base=f'http://127.0.0.1:{server.server_port}'
        class FakeReader:
            def read(self,path):raise AssertionError('Detailed OCR should not gate automatic submit')
            def read_fast(self,path):return Recognition('ZQWMD4FFZ',False,.82,[],'CR2')
        with tempfile.TemporaryDirectory() as folder,patch('desktop.fetch_maps',return_value=[]),patch.object(Worker,'prepare_reader',lambda self:None):
            data=Path(folder)
            if kind=='recover':
                history=History(data/'history.sqlite3');history.put('cr2','PlayerA','ZQWMD4FFZ','check',detail='Old result timeout');history.close()
            # Upgrading an old manual setting should enable the requested policy.
            (data/'settings.json').write_text(json.dumps({'nickname':'PlayerA','auto':False}))
            window=Window(data,base,quit_on_close=False);window.browser.profile.setHttpCacheType(QWebEngineProfile.NoCache)
            window.browser.profile.setPersistentCookiesPolicy(QWebEngineProfile.NoPersistentCookies);window.show();window.worker.reader=FakeReader()
            try:
                self.assertTrue(window.auto.isChecked())
                cfg={'project':'','nickname':'PlayerA','auto':True};start=time.monotonic()
                with patch.object(window,'stage',wraps=window.stage) as stages:
                    window.command('image',dict(path=Path(__file__).parent/'fixtures/ocr-18.png',cfg=cfg,cancel=threading.Event()))
                    if kind=='error':
                        self.pump(lambda:'fixture rejected' in window.status.text());self.assertEqual(window.code.text(),'')
                    else:
                        self.pump(lambda:window.code.text()=='9G5C4BA5R',7)
                        self.assertEqual(window.current_save,'9G5C4BA5R');self.assertTrue(window.copy_button.isEnabled())
                        self.assertFalse(any(c.args[0]=='review' for c in stages.call_args_list))
                        if kind=='normal':self.assertLess(time.monotonic()-start,4.,'Full asset loading delayed the form workflow')
                        if kind in {'recover','recorded'}:self.assertIn('사이트에 보관된',window.save_label.text())
                self.assertEqual(posts,[] if kind=='recover' else ['ZQWMD4FFZ'])
                self.assertIn('/cr2/board',gets)
                if kind=='refresh':self.assertGreaterEqual(gets.count('/cr2/board'),2)
            finally:
                release.set();window.close();self.pump(lambda:window.allow_close,6)
                for _ in range(30):self.app.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);time.sleep(.01)
                server.shutdown();server.server_close()
    def test_auto_submit_ignores_ocr_review_and_displays_readonly_result_before_assets_finish(self):self.scenario('normal')
    def test_copy_only_result_is_captured_without_system_clipboard_read(self):self.scenario('copy')
    def test_confirmed_issue_refreshes_get_without_repeating_post(self):self.scenario('refresh')
    def test_previous_unread_result_is_recovered_with_no_post(self):self.scenario('recover')
    def test_server_error_never_displays_the_old_result(self):self.scenario('error')
    def test_already_recorded_response_reads_saved_code_without_another_post(self):self.scenario('recorded')

    def test_result_layouts_exclude_auth_input_and_keep_multiple_results_distinct(self):
        from PySide6.QtCore import QUrl,QCoreApplication,QEvent
        from PySide6.QtWebEngineCore import QWebEngineProfile,QWebEnginePage
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from web_gateway import RESULT_JS
        profile=QWebEngineProfile();view=QWebEngineView();page=QWebEnginePage(profile,view);view.setPage(page);view.resize(800,600)
        cases=[
            ('<p>ZZZZZ9999</p><section><p>내 세이브 코드</p><p>9 G5C 4BA5R</p></section>',['9G5C4BA5R']),
            ('<section><h3><span>내 세이브 코드</span></h3><div><div><textarea readonly>9G5C4BA5R</textarea></div></div></section>',['9G5C4BA5R']),
            ('<section><p>내 세이브 코드</p><p><span>9G5C4</span> <span>BA5RZ</span> <span>ABCDE</span><button>복사</button></p></section>',['9G5C4BA5RZABCDE']),
            ('<section><h4>발급된 세이브 코드</h4><pre>9G5C4BA5R</pre></section>',['9G5C4BA5R']),
            ('<section><h3>내 세이브 코드</h3><code>9G5C4BA5R</code><code>ABCDE2345</code></section>',['9G5C4BA5R','ABCDE2345']),
            ('<section><h3>내 세이브 코드</h3><input name="code" minlength="9" value="ZQWMD4FFZ"><code>9G5C4BA5R</code></section>',['9G5C4BA5R']),
        ]
        try:
            for html,expected in cases:
                loaded=[];callback=loaded.append;page.loadFinished.connect(callback);page.setHtml('<!doctype html><meta charset="utf-8">'+html,QUrl('http://127.0.0.1/'))
                self.pump(lambda:bool(loaded));page.loadFinished.disconnect(callback);result=[]
                page.runJavaScript('JSON.stringify(('+RESULT_JS+')())',0,result.append);self.pump(lambda:bool(result))
                self.assertEqual(json.loads(result[0]),expected)
        finally:
            page.deleteLater();view.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
            profile.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

if __name__=='__main__':unittest.main()
