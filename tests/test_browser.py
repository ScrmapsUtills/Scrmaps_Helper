"""Fixture-only browser test. No real submissions or user sessions are used."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from web_gateway import Gateway, SiteError, LoginRequired, RESULT_JS

HTML='''<!doctype html><meta charset="utf-8"><h1>Fixture</h1>
<form><input name="code" minlength="9" maxlength="9"><p id="message"></p><button type="submit">인증 코드 등록</button></form>
<section><p>내 세이브 코드</p><p id="save">AAAAABBBB</p><p>다음 게임에서 입력하세요</p></section>
<script>document.querySelector('form').onsubmit=async e=>{e.preventDefault();
 const r=await fetch(location.pathname,{method:'POST',body:document.querySelector('input').value});
 const data=await r.json(); const m=document.querySelector('#message');
 if(data.error){m.className='text-red-600';m.textContent=data.error;}
 else{document.querySelector('#save').textContent=data.save;m.className='text-emerald-700';m.textContent='제출되었습니다';}};</script>'''


class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=sync_playwright().start()
        try:
            cls.browser=cls.p.chromium.launch(headless=True)
        except Exception as exc:
            cls.p.stop()
            raise unittest.SkipTest("Chromium launch unavailable: "+str(exc).splitlines()[0])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close();cls.p.stop()

    def setUp(self):
        self.context=self.browser.new_context()
        self.page=self.context.new_page()
        self.posts=[]
        self.post_error=None
        self.get_html=HTML
        def route(request_route):
            req=request_route.request
            if req.method=="POST":
                self.posts.append(req.post_data)
                request_route.fulfill(status=200,content_type="application/json",body=json.dumps({"error":self.post_error} if self.post_error else {"save":"9G5C4BA5R"}))
            else:
                request_route.fulfill(status=200,content_type="text/html",body=self.get_html)
        self.page.route("https://www.scrmaps.com/**",route)
        self.g=Gateway("unused")
        self.g.context=self.context;self.g.page=self.page

    def tearDown(self): self.context.close()

    def test_new_result_after_real_form_post(self):
        self.assertEqual(self.g.submit("testmap","ZQWMD4FFZ"),"9G5C4BA5R")
        self.assertEqual(self.posts,["ZQWMD4FFZ"])

    def test_length_mismatch_never_posts(self):
        with self.assertRaises(SiteError): self.g.submit("testmap","ABCDE")
        self.assertEqual(self.posts,[])

    def test_server_error_does_not_return_old_code(self):
        self.post_error="인증번호가 올바르지 않습니다"
        with self.assertRaisesRegex(SiteError,"올바르지"):
            self.g.submit("testmap","ZQWMD4FFZ")

    def test_result_selector_ignores_unrelated_code(self):
        self.page.set_content('<p>ZZZZZ9999</p><section><p>내 세이브 코드</p><p>9 G5C 4BA5R</p></section>')
        self.assertEqual(self.page.evaluate(RESULT_JS),["9G5C4BA5R"])

    def test_result_selector_handles_inline_code_chunks(self):
        self.page.set_content('<section><p>내 세이브 코드</p><p><span>9G5C4</span> <span>BA5RZ</span> <span>ABCDE</span></p></section>')
        self.assertEqual(self.page.evaluate(RESULT_JS),["9G5C4BA5RZABCDE"])

    def test_cancel_before_click_never_posts(self):
        with self.assertRaises(SiteError): self.g.submit("testmap","ZQWMD4FFZ",lambda:True)
        self.assertEqual(self.posts,[])

    def test_login_badge_uses_observed_page_state(self):
        self.page.goto("https://www.scrmaps.com/testmap")
        self.page.set_content('<header><a href="/login">로그인</a></header>')
        self.assertFalse(self.g.peek_login())
        self.page.set_content('<header><button>로그아웃</button></header>')
        self.assertTrue(self.g.peek_login())


if __name__ == "__main__": unittest.main()
