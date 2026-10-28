import queue
import sys
import tempfile
import threading
import unittest
import copy
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from worker import Worker
from core import History
from web_gateway import LoginRequired
from recognition import Recognition
from PIL import Image


class FakeGateway:
    def __init__(self): self.calls=0; self.error=None;self.logged_in=False
    def peek_login(self):return self.logged_in
    def can_resume(self):return self.logged_in
    def submit(self, project, auth, cancelled):
        if cancelled(): raise RuntimeError("cancelled")
        self.calls+=1
        if self.error: raise self.error
        return "9G5C4BA5R"


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.w=Worker(queue.Queue(),queue.Queue(),threading.Event())
        self.w.history=History(Path(self.temp.name)/"history.db")
        self.w.gateway=FakeGateway()
        self.cfg={"project":"testmap","nickname":"PlayerA"}

    def tearDown(self):
        self.w.history.close(); self.temp.cleanup()

    def test_success_is_idempotent(self):
        self.w.submit("ZQWMD4FFZ",self.cfg)
        self.w.submit("ZQWMD4FFZ",self.cfg)
        self.assertEqual(self.w.gateway.calls,1)
        self.assertEqual(self.w.history.get("testmap","PlayerA","ZQWMD4FFZ")["status"],"ok")

    def test_uncertain_result_is_not_retried_automatically(self):
        self.w.gateway.error=RuntimeError("response unknown")
        self.w.submit("ZQWMD4FFZ",self.cfg)
        self.w.submit("ZQWMD4FFZ",self.cfg)
        self.assertEqual(self.w.gateway.calls,1)
        self.assertEqual(self.w.history.get("testmap","PlayerA","ZQWMD4FFZ")["status"],"check")
        self.w.gateway.error=None
        self.w.submit("ZQWMD4FFZ",self.cfg,retry=True)
        self.assertEqual(self.w.gateway.calls,2)

    def test_login_failure_can_be_retried_explicitly(self):
        self.w.gateway.error=LoginRequired("login")
        self.w.submit("ZQWMD4FFZ",self.cfg)
        self.assertEqual(self.w.history.get("testmap","PlayerA","ZQWMD4FFZ")["status"],"login")
        self.w.gateway.error=None
        self.w.submit("ZQWMD4FFZ",self.cfg,retry=True)
        self.assertEqual(self.w.gateway.calls,2)

    def test_cancel_before_submit(self):
        cancel=threading.Event();cancel.set()
        self.w.submit("ZQWMD4FFZ",self.cfg,cancel=cancel)
        self.assertEqual(self.w.gateway.calls,0)
        self.assertIsNone(self.w.history.get("testmap","PlayerA","ZQWMD4FFZ"))

    def test_cancelled_image_does_not_load_or_read_file(self):
        cancel=threading.Event();cancel.set()
        self.w.process_image(Path(self.temp.name)/'missing.png',self.cfg,cancel)
        self.assertEqual(self.w.gateway.calls,0)

    def test_cancel_at_resume_boundary_is_persisted_as_paused(self):
        self.w.history.put('testmap','PlayerA','ZQWMD4FFZ','login')
        cancel=threading.Event();cancel.set()
        self.w.submit('ZQWMD4FFZ',self.cfg,cancel=cancel,resuming=True)
        self.assertEqual(self.w.history.get('testmap','PlayerA','ZQWMD4FFZ')['status'],'paused')
        self.assertEqual(self.w.gateway.calls,0)

    def test_crash_marker_prevents_second_post(self):
        self.w.history.put("testmap","PlayerA","ZQWMD4FFZ","submitting")
        self.w.submit("ZQWMD4FFZ",self.cfg)
        self.assertEqual(self.w.gateway.calls,0)

    def process(self,result,selected=""):
        class FakeReader:
            def read(self,_path): return copy.deepcopy(result)
        self.w.reader=FakeReader()
        path=Path(self.temp.name)/"image.png"
        Image.new("RGB",(100,100)).save(path)
        cfg={"project":selected,"nickname":"PlayerA","auto":True}
        self.w.process_image(path,cfg,threading.Event())

    def test_map_can_come_from_image(self):
        self.process(Recognition("ZQWMD4FFZ",True,.98,[],"testmap"))
        self.assertEqual(self.w.gateway.calls,1)
        self.assertEqual(self.w.history.get("testmap","PlayerA","ZQWMD4FFZ")["status"],"ok")

    def test_selected_map_mismatch_never_posts(self):
        self.process(Recognition("ZQWMD4FFZ",True,.98,[],"differentmap"),"testmap")
        self.assertEqual(self.w.gateway.calls,0)

    def test_uncertain_recognition_submits_immediately_when_auto_is_enabled(self):
        self.process(Recognition("ZQWMD4FFZ",False,.86,[],"testmap"))
        self.assertEqual(self.w.gateway.calls,1)

    def test_missing_map_never_posts_an_unrouted_code(self):
        self.process(Recognition('ZQWMD4FFZ',False,.8,[],''))
        self.assertEqual(self.w.gateway.calls,0)

    def test_missing_code_does_not_submit(self):
        self.process(Recognition(project='testmap'))
        self.assertEqual(self.w.gateway.calls,0)

    def test_auto_uses_fast_reader(self):
        class FastReader:
            def read(self,path):raise AssertionError('Slow verification path was used')
            def read_fast(self,path):return Recognition('ZQWMD4FFZ',False,.8,[],'testmap')
        self.w.reader=FastReader();path=Path(self.temp.name)/'fast.png';Image.new('RGB',(50,50)).save(path)
        self.w.process_image(path,dict(project='',nickname='PlayerA',auto=True),threading.Event())
        self.assertEqual(self.w.gateway.calls,1)

    def test_previous_unread_issue_reads_current_code_without_another_submit(self):
        self.w.history.put('testmap','PlayerA','ZQWMD4FFZ','check')
        self.w.gateway.read_current=lambda slug,cancelled:'9G5C4BA5R'
        self.w.submit('ZQWMD4FFZ',dict(self.cfg,auto=True))
        self.assertEqual(self.w.gateway.calls,0)
        self.assertEqual(self.w.history.get('testmap','PlayerA','ZQWMD4FFZ')['status'],'recovered')

    def test_login_recovery_resumes_only_the_get_not_a_new_submission(self):
        self.w.history.put('testmap','PlayerA','ZQWMD4FFZ','check')
        def read_current(slug,cancelled):
            if not self.w.gateway.logged_in:raise LoginRequired('login')
            return '9G5C4BA5R'
        self.w.gateway.read_current=read_current;self.w.gateway.open_login=lambda slug:None
        self.w.submit('ZQWMD4FFZ',dict(self.cfg,auto=True))
        self.assertEqual(self.w.history.get('testmap','PlayerA','ZQWMD4FFZ')['status'],'recover_login')
        self.w.gateway.logged_in=True;self.w.resume_login()
        self.assertEqual(self.w.gateway.calls,0)
        self.assertEqual(self.w.history.get('testmap','PlayerA','ZQWMD4FFZ')['status'],'recovered')

    def test_old_success_cache_is_read_again_without_a_new_post(self):
        self.w.history.put('testmap','PlayerA','ZQWMD4FFZ','recovered',save='ASDDSA')
        reads=[]
        self.w.gateway.read_current=lambda slug,cancelled:reads.append(slug) or '9G5C4BA5R'
        self.w.submit('ZQWMD4FFZ',dict(self.cfg,auto=True))
        self.assertEqual(reads,['testmap'])
        self.assertEqual(self.w.gateway.calls,0)
        row=self.w.history.get('testmap','PlayerA','ZQWMD4FFZ')
        self.assertEqual(row['save'],'9G5C4BA5R')
        from core import verified_save
        self.assertTrue(verified_save(row))

    def test_grouped_save_is_stored_and_emitted_as_typable_code(self):
        self.w.gateway.submit=lambda *args:'9G5 - C4B - A5R'
        self.w.submit('ZQWMD4FFZ',self.cfg)
        self.assertEqual(self.w.history.get('testmap','PlayerA','ZQWMD4FFZ')['save'],'9G5C4BA5R')
        events=[]
        while not self.w.events.empty():events.append(self.w.events.get())
        self.assertEqual([p['code'] for kind,p in events if kind=='save'],['9G5C4BA5R'])

    def test_map_address_and_auth_are_never_saved_as_result_data(self):
        for bad in ['https://www.scrmaps.com/testmap','TESTMAP','ZQWMD4FFZ']:
            with self.subTest(bad=bad):
                self.w.gateway.submit=lambda *args:bad
                self.w.submit('ZQWMD4FFZ',self.cfg,retry=True)
                row=self.w.history.get('testmap','PlayerA','ZQWMD4FFZ')
                self.assertEqual(row['status'],'check')
                self.assertEqual(row['save'],'')
        events=[]
        while not self.w.events.empty():events.append(self.w.events.get())
        self.assertFalse(any(kind=='save' for kind,payload in events))

    def test_bad_current_result_does_not_replace_or_display_an_old_cache(self):
        self.w.history.put('testmap','PlayerA','ZQWMD4FFZ','recovered',save='ASDDSA')
        self.w.gateway.read_current=lambda *args:'TESTMAP'
        self.w.submit('ZQWMD4FFZ',dict(self.cfg,auto=True))
        events=[]
        while not self.w.events.empty():events.append(self.w.events.get())
        self.assertFalse(any(kind=='save' for kind,payload in events))
        self.assertEqual(self.w.gateway.calls,0)

    def test_login_completion_automatically_resumes_once(self):
        self.w.gateway.error=LoginRequired('login')
        self.w.submit('ZQWMD4FFZ',self.cfg)
        self.assertEqual(self.w.gateway.calls,1)
        self.assertEqual(len(self.w.waiting_login),1)
        self.w.gateway.error=None;self.w.gateway.logged_in=True
        for job in self.w.waiting_login.values():job['next']=0
        self.w.resume_login();self.w.resume_login()
        self.assertEqual(self.w.gateway.calls,2)
        self.assertEqual(self.w.history.get('testmap','PlayerA','ZQWMD4FFZ')['status'],'ok')

    def test_uncertain_post_is_never_auto_resumed(self):
        self.w.gateway.error=RuntimeError('post result unknown')
        self.w.submit('ZQWMD4FFZ',self.cfg)
        self.w.gateway.logged_in=True
        self.w.resume_login();self.w.resume_login()
        self.assertEqual(self.w.gateway.calls,1)
        self.assertEqual(len(self.w.waiting_login),0)

    def test_cancelled_login_job_stays_paused(self):
        cancel=threading.Event();self.w.gateway.error=LoginRequired('login')
        self.w.submit('ZQWMD4FFZ',self.cfg,cancel=cancel)
        cancel.set();self.w.resume_login()
        self.assertEqual(self.w.history.get('testmap','PlayerA','ZQWMD4FFZ')['status'],'paused')
        self.assertEqual(len(self.w.waiting_login),0)

    def test_restart_restores_only_safe_login_jobs_for_current_nickname(self):
        self.w.history.put('testmap','PlayerA','ZQWMD4FFZ','login')
        self.w.history.put('testmap','PlayerA','ABCDE2345','check')
        self.w.history.put('testmap','PlayerB','BCDEF2345','login')
        self.w.active_nickname='PlayerA';self.w.restore_login()
        self.assertEqual(list(self.w.waiting_login),[('testmap','PlayerA','ZQWMD4FFZ')])


if __name__ == "__main__": unittest.main()
