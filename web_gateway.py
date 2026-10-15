"""Interact with SCRMaps' visible form using a dedicated browser profile.

No private API calls, password collection or CAPTCHA/2FA handling.
"""
from __future__ import annotations

import re
import time
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from core import BASE, project_slug, valid_code


class LoginRequired(RuntimeError):
    pass


class SiteError(RuntimeError):
    pass


class MapParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.cards, self.current = {}, None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a":
            self.current = attrs.get("href", "")
        if tag == "img" and self.current and attrs.get("alt"):
            try:
                slug = project_slug(self.current)
                if attrs["alt"] != "SCRMaps":
                    self.cards[slug] = attrs["alt"]
            except ValueError:
                pass

    def handle_endtag(self, tag):
        if tag == "a":
            self.current = None


def fetch_maps():
    request = urllib.request.Request(BASE + "/", headers={"User-Agent":"SCRMapsHelper/1.0 (personal desktop helper)"})
    with urllib.request.urlopen(request, timeout=15) as response:
        html = response.read(3_000_000).decode("utf-8")
    parser = MapParser()
    parser.feed(html)
    return [{"slug":slug,"name":name} for slug,name in parser.cards.items()]


# Kept separate to test against DOM fixtures reconstructed from the observed form.
RESULT_JS = r"""() => {
  const labels = new Set(['내 세이브 코드','Your save code','YOUR SAVE CODE','My save code']);
  const out = new Set();
  for (const label of document.querySelectorAll('p,h2,h3,h4,span,div')) {
    if (!labels.has(label.textContent.trim())) continue;
    let box = label.parentElement;
    for (let depth=0; box && depth<2; depth++,box=box.parentElement) {
      if (box.textContent.length > 1600) break;
      for (const e of box.querySelectorAll('p,code,pre,span,div')) {
        if (e.querySelector('input,button')) continue;
        const parent=e.parentElement;
        if (parent && box.contains(parent) && !parent.querySelector('input,button') && /^[A-HJ-NP-Z2-9]{5,64}$/.test(parent.textContent.replace(/\s+/g,'').toUpperCase())) continue;
        const text=e.textContent.replace(/\s+/g,'').toUpperCase();
        if (/^[A-HJ-NP-Z2-9]{5,64}$/.test(text)) out.add(text);
      }
      if (out.size) break;
    }
  }
  return Array.from(out);
}"""


class Gateway:
    def __init__(self, profile):
        self.profile = str(profile)
        self.playwright = self.context = self.page = None

    def ensure(self):
        if self.context is not None:
            try:
                if self.page and not self.page.is_closed():
                    return
            except Exception:
                pass
            self.close()
        from playwright.sync_api import sync_playwright
        self.playwright = sync_playwright().start()
        failures = []
        for channel in ("msedge", "chrome", None):
            try:
                opts = dict(user_data_dir=self.profile, headless=False, viewport={"width":1100,"height":850}, locale="ko-KR")
                if channel:
                    opts["channel"] = channel
                self.context = self.playwright.chromium.launch_persistent_context(**opts)
                self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
                self.page.set_default_timeout(10_000)
                return
            except Exception as exc:
                failures.append(str(exc).splitlines()[0])
        self.close()
        raise SiteError("브라우저를 열지 못했습니다. Edge 또는 Chrome을 설치하고 재시도하세요. " + " / ".join(failures))

    def open_login(self, slug):
        self.ensure()
        self.page.goto(BASE + "/" + (project_slug(slug) if slug else ""), wait_until="domcontentloaded", timeout=25_000)
        self.page.bring_to_front()

    def peek_login(self):
        if self.page is None or self.page.is_closed():
            return None
        if urlsplit(self.page.url).hostname not in {"www.scrmaps.com","scrmaps.com"}:
            return None
        text=" ".join(self.page.locator('header').all_text_contents())
        if re.search(r"로그아웃|log\s*out|sign\s*out",text,re.I):
            return True
        if re.search(r"로그인|sign\s*in|log\s*in",text,re.I):
            return False
        return None

    def form(self, slug):
        self.ensure()
        url = BASE + "/" + project_slug(slug)
        response = self.page.goto(url, wait_until="domcontentloaded", timeout=25_000)
        if response and response.status >= 400:
            raise SiteError(f"맵 페이지를 열 수 없습니다 (HTTP {response.status}). 맵 주소를 확인하세요.")
        if urlsplit(self.page.url).hostname not in {"www.scrmaps.com", "scrmaps.com"}:
            raise LoginRequired("사이트 로그인 화면에서 로그인을 완료한 뒤 다시 제출하세요.")
        try:
            field = self.page.locator('input[name="code"][minlength]').first
            field.wait_for(state="visible", timeout=10_000)
        except Exception as exc:
            body = self.page.locator("body").inner_text()
            if re.search(r"로그인|Sign in|nickname|닉네임", body, re.I):
                raise LoginRequired("전용 브라우저에서 Battle.net 로그인과 사이트 닉네임 설정을 완료하세요.") from exc
            raise SiteError("인증번호 입력창을 찾지 못했습니다. 이 맵의 코드 방식 또는 사이트 화면이 변경되었을 수 있습니다.") from exc
        form = field.locator("xpath=ancestor::form[1]")
        if form.locator('input[type="number"],input[name="field"]').count():
            raise SiteError("항목별 코드를 입력하는 맵은 이 버전의 자동 제출 대상이 아닙니다.")
        return field, form

    def submit(self, slug, auth, cancelled=lambda:False):
        auth = valid_code(auth)
        field, form = self.form(slug)
        length = int(field.get_attribute("maxlength") or 64)
        minimum = int(field.get_attribute("minlength") or 5)
        if not minimum <= len(auth) <= length:
            raise SiteError(f"인증번호 길이가 맵의 입력 길이와 다릅니다 ({minimum}~{length}자). 인식 영역과 맵 선택을 확인하세요.")
        field.fill(auth)
        if field.input_value() != auth:
            raise SiteError("사이트 입력값이 인식한 인증번호와 다릅니다. 제출하지 않았습니다.")
        if cancelled():
            raise SiteError("제출 전에 작업이 중단되었습니다.")
        button = form.locator('button[type="submit"]')
        if button.count() != 1:
            raise SiteError("등록 버튼을 하나로 특정할 수 없습니다. 제출하지 않았습니다.")
        # The observed Next.js form uses a server action. Wait for its actual POST;
        # a save code already rendered before the click is not evidence of success.
        with self.page.expect_response(lambda r: r.request.method == "POST" and urlsplit(r.url).hostname in {"www.scrmaps.com","scrmaps.com"} and urlsplit(r.url).path.rstrip("/") == "/" + project_slug(slug), timeout=25_000) as event:
            button.click()
        response = event.value
        if response.status >= 400:
            raise SiteError(f"등록 응답 오류 (HTTP {response.status}). 반복 제출하지 말고 브라우저 결과를 확인하세요.")
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            self.page.wait_for_timeout(200)
            if self.page.is_closed():
                raise SiteError("브라우저가 닫혔습니다. 제출 결과를 확인한 뒤 재시도하세요.")
            error = form.locator('p[class*="text-red"], [role="alert"]')
            if error.count() and error.first.is_visible():
                raise SiteError(error.first.inner_text())
            success = form.locator('p[class*="text-emerald"]')
            if not success.count() or not success.first.is_visible():
                continue
            codes = self.page.evaluate(RESULT_JS)
            if len(codes) == 1:
                return valid_code(codes[0])
            if len(codes) > 1:
                raise SiteError("세이브 코드가 여러 개 발견되었습니다. 브라우저에서 확인하세요.")
        raise SiteError("제출 후 세이브 코드를 확인하지 못했습니다. 브라우저 결과를 확인하세요. 자동 재제출은 하지 않습니다.")

    def close(self):
        try:
            if self.context:
                self.context.close()
        except Exception:
            pass
        try:
            if self.playwright:
                self.playwright.stop()
        except Exception:
            pass
        self.context = self.playwright = self.page = None
