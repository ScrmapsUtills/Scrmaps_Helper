"""Browser automation through a native Qt message bridge, without a debug port."""
from __future__ import annotations
import json
import secrets
import time
from urllib.parse import urlsplit
from core import BASE, project_slug, valid_code
from web_gateway import LoginRequired, SiteError, RESULT_JS

SNAPSHOT_JS = r"""(() => {
const host=location.hostname;
const field=document.querySelector('input[name="code"][minlength]');
const form=field?.closest('form');
const visible=e=>e && e.getClientRects().length>0;
const header=document.querySelector('header')?.innerText||'';
const buttons=form?Array.from(form.querySelectorAll('button[type="submit"]')):[];
const error=form?Array.from(form.querySelectorAll('p[class*="text-red"],[role="alert"]')).filter(visible).map(e=>e.innerText).join('\n'):'';
const success=form?Array.from(form.querySelectorAll('p[class*="text-emerald"]')).some(e=>visible(e)&&e.innerText.trim()):false;
return JSON.stringify({url:location.href,host,header,field:visible(field),min:field?.minLength||0,max:field?.maxLength||64,
 value:field?.value||'',buttons:buttons.length,disabled:buttons[0]?.disabled||false,error,success,
 title:document.title,numeric:form?!!form.querySelector('input[type="number"],input[name="field"]'):false,
 codes:success?((RESULT_FUNCTION)()):[]});
})()""".replace('RESULT_FUNCTION',RESULT_JS)


class EmbeddedGateway:
    def __init__(self, bridge, closing=None, base=BASE):
        self.bridge=bridge
        self.closing=closing
        self.base=base.rstrip('/')
        self.hosts={urlsplit(self.base).hostname}

    def rpc(self,action,payload=None,timeout=20):
        return self.bridge.call(action,payload,timeout)

    def peek_login(self):
        return self.bridge.login_state

    def can_resume(self):
        return self.peek_login() is True and not self.bridge.auth_in_progress

    def snapshot(self):
        data=self.rpc('evaluate',{'script':SNAPSHOT_JS},10)
        return json.loads(data) if isinstance(data,str) and data else {}

    def open_login(self,slug=''):
        self.rpc('show')
        if self.bridge.auth_in_progress:
            return
        if not self.bridge.loaded:
            self.rpc('navigate',{'url':self.base+'/'},30)
        state=self.snapshot()
        import re
        if re.search(r'로그아웃|log\s*out|sign\s*out',state.get('header',''),re.I):
            return
        self.rpc('navigate',{'url':self.base+'/login'},30)

    def submit(self,slug,auth,cancelled=lambda:False):
        slug,auth=project_slug(slug),valid_code(auth)
        if cancelled(): raise SiteError('제출 전에 작업이 중지됐어요.')
        if self.bridge.auth_in_progress:
            raise LoginRequired('앱 안에서 진행 중인 로그인을 완료해 주세요.')
        self.rpc('navigate',{'url':self.base+'/'+slug},30)
        deadline=time.monotonic()+12
        state={}
        while time.monotonic()<deadline:
            if cancelled(): raise SiteError('제출 전에 작업이 중지됐어요.')
            state=self.snapshot()
            if state.get('host') not in self.hosts:
                raise LoginRequired('앱 안에서 SCRMaps 로그인을 완료해 주세요.')
            if state.get('field'): break
            header=state.get('header','').lower()
            if any(t in header for t in ('로그인','sign in','log in')) and not any(t in header for t in ('로그아웃','log out','sign out')):
                raise LoginRequired('앱 안에서 SCRMaps 로그인을 완료해 주세요.')
            if '404' in state.get('title',''):
                raise SiteError('맵 페이지가 없어요. 인식한 맵 주소를 확인해 주세요.')
            time.sleep(.15)
        if not state.get('field'):
            if self.peek_login() is True:
                raise SiteError('로그인은 확인됐지만 인증번호 입력창이 없어요. SCRMaps 닉네임 설정과 이 맵의 저장 방식을 확인해 주세요.')
            raise LoginRequired('앱 안에서 로그인과 게임 닉네임 설정을 완료해 주세요.')
        if state.get('numeric'):
            raise SiteError('항목별 숫자·코드를 제출하는 맵은 지원하지 않아요.')
        if not state.get('min',5)<=len(auth)<=state.get('max',64):
            raise SiteError('인증번호 길이가 이 맵과 맞지 않아요. 번호와 맵을 확인해 주세요.')
        if state.get('buttons')!=1:
            raise SiteError('등록 버튼을 하나로 찾지 못했어요. 사이트 화면을 확인해 주세요.')
        args=json.dumps({'auth':auth,'host':next(iter(self.hosts)),'path':'/'+slug})
        fill=r"""(() => {const a=ARGS;if(location.hostname!==a.host||location.pathname.replace(/\/$/,'')!==a.path)return false;
        const e=document.querySelector('input[name="code"][minlength]');if(!e)return false;
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,a.auth);
        e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));return true;})()""".replace('ARGS',args)
        if not self.rpc('evaluate',{'script':fill},10):
            raise SiteError('입력 도중 페이지가 바뀌었어요. 제출하지 않았어요.')
        time.sleep(.20)
        state=self.snapshot()
        if state.get('value')!=auth:
            raise SiteError('입력값을 확인하지 못했어요. 제출하지 않았어요.')
        if cancelled():raise SiteError('제출 전에 작업이 중지됐어요.')
        token=secrets.token_hex(12)
        self.rpc('arm',{'token':token,'path':'/'+slug,'host':next(iter(self.hosts))})
        click=r"""(() => {const a=ARGS;if(location.hostname!==a.host||location.pathname.replace(/\/$/,'')!==a.path)return false;
        const e=document.querySelector('input[name="code"][minlength]'),f=e?.closest('form');
        const buttons=f?Array.from(f.querySelectorAll('button[type="submit"]')):[];
        if(e?.value!==a.auth||buttons.length!==1||buttons[0].disabled)return false;
        buttons[0].click();return true;})()""".replace('ARGS',args)
        # After dispatching a click, every failure is an uncertain result, never
        # LoginRequired. Automatic login resume must not repeat a possible POST.
        try:
            if not self.rpc('evaluate',{'script':click},10):
                raise SiteError('등록 버튼을 누르지 못했어요. 사이트 결과를 확인해 주세요.')
            deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                if cancelled():raise SiteError('종료 요청으로 응답 대기를 중단했어요. 전송 결과는 사이트에서 확인해 주세요.')
                state=self.snapshot()
                if state.get('error'):raise SiteError(state['error'])
                if state.get('success') and self.bridge.post_seen(token):
                    codes=state.get('codes',[])
                    if len(codes)==1:return valid_code(codes[0])
                    if len(codes)>1:raise SiteError('발급 코드가 여러 개예요. 사이트 결과를 확인해 주세요.')
                time.sleep(.2)
            raise SiteError('발급 응답을 확인하지 못했어요. 사이트 결과를 확인해 주세요. 중복 제출하지 않았어요.')
        except LoginRequired as exc:
            raise SiteError('전송 후 로그인 상태가 바뀌었어요. 사이트에서 제출 결과를 확인해 주세요.') from exc

    def close(self):
        # The main window owns the persistent profile and closes it on exit.
        pass
