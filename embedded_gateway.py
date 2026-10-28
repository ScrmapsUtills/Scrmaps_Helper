"""Submit through the visible Qt page, using form readiness and fresh results."""
from __future__ import annotations
import json,secrets,time,re
from urllib.parse import urlsplit
from core import BASE,project_slug,valid_code
from web_gateway import LoginRequired,SiteError,RESULT_JS,COPY_RESULT_JS

SNAPSHOT_JS=r"""(() => {
const field=document.querySelector('input[name="code"][minlength]');
const form=field?.closest('form');
const visible=e=>e && e.getClientRects().length>0;
const buttons=form?Array.from(form.querySelectorAll('button[type="submit"]')):[];
const messages=form?Array.from(form.querySelectorAll('p,[role="status"],[role="alert"]')).filter(visible):[];
const error=messages.filter(e=>e.matches('[class*="text-red"],[role="alert"]')).map(e=>e.innerText).join('\n');
const success=messages.some(e=>(e.matches('[class*="text-emerald"],[class*="text-green"]')&&e.innerText.trim())||/제출되었습니다|발급\s*완료|저장\s*완료|submitted|successfully/i.test(e.innerText));
return JSON.stringify({url:location.href,host:location.hostname,header:document.querySelector('header')?.innerText||'',
 leaving:window.__scrmapsLeavingDocument||'',ready:document.readyState,field:visible(field),
 min:field?.minLength||0,max:field?.maxLength||64,value:field?.value||'',buttons:buttons.length,disabled:buttons[0]?.disabled||false,
 error,success,title:document.title,numeric:form?!!form.querySelector('input[type="number"],input[name="field"]'):false,
 links:Array.from(document.querySelectorAll('a[href]')).filter(e=>e.origin===location.origin).map(e=>e.pathname),
 codes:(RESULT_FUNCTION)(),copied:window.__scrmapsCopiedCode||null});
})()""".replace('RESULT_FUNCTION',RESULT_JS)

class EmbeddedGateway:
    def __init__(self,bridge,closing=None,base=BASE):
        self.bridge=bridge;self.closing=closing;self.base=base.rstrip('/');self.hosts={urlsplit(self.base).hostname}
    def rpc(self,action,payload=None,timeout=20):return self.bridge.call(action,payload,timeout)
    def peek_login(self):return self.bridge.login_state
    def can_resume(self):return self.peek_login() is True and not self.bridge.auth_in_progress
    def snapshot(self):
        data=self.rpc('evaluate',{'script':SNAPSHOT_JS},10)
        return json.loads(data) if isinstance(data,str) and data else {}
    def open_login(self,slug=''):
        self.rpc('show')
        if self.bridge.auth_in_progress:return
        if not self.bridge.loaded:self.rpc('navigate',{'url':self.base+'/'},30)
        state=self.snapshot()
        import re
        if re.search(r'로그아웃|log\s*out|sign\s*out',state.get('header',''),re.I):return
        self.rpc('navigate',{'url':self.base+'/login'},30)

    def ready_form(self,slug,cancelled,force=False,path=None):
        root='/'+slug;allowed={root,root+'/board'};state=self.snapshot()
        current=urlsplit(state.get('url','')).path.rstrip('/')
        target=path or (current if state.get('host') in self.hosts and current in allowed else root)
        assert target in allowed
        clean=(state.get('host') in self.hosts and current==target and state.get('field')
               and not state.get('success') and not state.get('error'))
        marker=secrets.token_hex(12)
        self.rpc('prepare',{'url':self.base+target,'marker':marker,'force':force or not clean},10)
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            if cancelled():raise SiteError('제출 전에 작업이 중지됐어요.')
            state=self.snapshot()
            if not state or state.get('leaving')==marker:time.sleep(.05);continue
            actual=urlsplit(state.get('url','')).path.rstrip('/')
            if state.get('host') not in self.hosts:raise LoginRequired('앱 안에서 SCRMaps 로그인을 완료해 주세요.')
            if actual==target and state.get('field'):return state,target
            # Current SCRMaps CR2 exposes its save form on /cr2/board.
            if actual==root and root+'/board' in state.get('links',[]) and target!=root+'/board':
                target=root+'/board';marker=secrets.token_hex(12)
                self.rpc('prepare',{'url':self.base+target,'marker':marker,'force':True},10);continue
            if actual=='/login':raise LoginRequired('앱 안에서 로그인과 게임 닉네임 설정을 완료해 주세요.')
            if actual==target and state.get('ready')=='complete':
                if '404' in state.get('title',''):raise SiteError('맵 페이지가 없어요. 맵 주소를 확인해 주세요.')
                h=state.get('header','').lower()
                if any(x in h for x in ['로그인','sign in','log in']) and not any(x in h for x in ['로그아웃','sign out','log out']):
                    raise LoginRequired('앱 안에서 로그인을 완료해 주세요.')
            time.sleep(.05)
        raise SiteError('인증번호 입력창을 찾지 못했어요. 사이트의 맵 화면을 확인해 주세요.')

    def read_current(self,slug,cancelled=lambda:False):
        slug=project_slug(slug)
        if self.bridge.auth_in_progress:raise LoginRequired('로그인을 완료하면 보관된 코드를 읽습니다.')
        state,_=self.ready_form(slug,cancelled,force=True)
        deadline=time.monotonic()+3;token=secrets.token_hex(12);copy_tried=False
        while True:
            codes=state.get('codes',[])
            if not codes and state.get('copied',{}):
                copied=state['copied']
                if copied.get('token')==token:codes=[copied['code']]
            if len(codes)==1:return valid_code(codes[0])
            if len(codes)>1:raise SiteError('보관된 세이브 코드가 여러 개예요.')
            if not copy_tried:copy_tried=bool(self.rpc('evaluate',{'script':COPY_RESULT_JS+'('+json.dumps(token)+')'},10))
            if cancelled() or time.monotonic()>=deadline:raise SiteError('사이트에 보관된 세이브 코드를 찾지 못했어요.')
            time.sleep(.08);state=self.snapshot()

    def submit(self,slug,auth,cancelled=lambda:False):
        self.last_result_existing=False
        slug,auth=project_slug(slug),valid_code(auth)
        if cancelled():raise SiteError('제출 전에 작업이 중지됐어요.')
        if self.bridge.auth_in_progress:raise LoginRequired('앱 안에서 진행 중인 로그인을 완료해 주세요.')
        state,path=self.ready_form(slug,cancelled)
        if state.get('numeric'):raise SiteError('항목별 숫자·코드를 제출하는 맵은 지원하지 않아요.')
        if not state.get('min',5)<=len(auth)<=state.get('max',64):raise SiteError('인증번호 길이가 이 맵과 맞지 않아요.')
        if state.get('buttons')!=1:raise SiteError('등록 버튼을 하나로 찾지 못했어요.')
        baseline=set(state.get('codes',[]))
        args=json.dumps({'auth':auth,'host':next(iter(self.hosts)),'path':path})
        fill=r"""(() => {const a=ARGS;if(location.hostname!==a.host||location.pathname.replace(/\/$/,'')!==a.path)return false;
        const e=document.querySelector('input[name="code"][minlength]');if(!e)return false;
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,a.auth);
        e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));return true;})()""".replace('ARGS',args)
        if not self.rpc('evaluate',{'script':fill},10):raise SiteError('입력 도중 페이지가 바뀌었어요.')
        deadline=time.monotonic()+3
        while True:
            if cancelled():raise SiteError('제출 전에 작업이 중지됐어요.')
            state=self.snapshot()
            if state.get('value')==auth and state.get('buttons')==1 and not state.get('disabled'):break
            if time.monotonic()>=deadline:raise SiteError('인증번호 입력값 또는 등록 버튼을 확인하지 못했어요.')
            time.sleep(.03)
        token=secrets.token_hex(12);self.rpc('arm',{'token':token,'path':path,'host':next(iter(self.hosts))})
        click=r"""(() => {const a=ARGS;if(location.hostname!==a.host||location.pathname.replace(/\/$/,'')!==a.path)return false;
        const e=document.querySelector('input[name="code"][minlength]'),f=e?.closest('form');
        const b=f?Array.from(f.querySelectorAll('button[type="submit"]')):[];
        if(e?.value!==a.auth||b.length!==1||b[0].disabled)return false;b[0].click();return true;})()""".replace('ARGS',args)
        # After clicking, no failure becomes LoginRequired: login resume must
        # never repeat a POST whose server outcome is unknown.
        try:
            if not self.rpc('evaluate',{'script':click},10):raise SiteError('등록 버튼을 누르지 못했어요.')
            deadline=time.monotonic()+30;issued_at=None;refreshed=False;copy_tried=False
            while time.monotonic()<deadline:
                if cancelled():raise SiteError('발급 대기를 중단했어요. 전송 결과는 사이트에서 확인해 주세요.')
                state=self.snapshot()
                if state.get('error'):
                    if re.search(r'이미.*기록.*같|same.*record|already.*recorded',state['error'],re.I):
                        code=self.read_current(slug,cancelled);self.last_result_existing=True;return code
                    raise SiteError(state['error'])
                posted=self.bridge.post_seen(token)
                if posted and state.get('success') and issued_at is None:issued_at=time.monotonic()
                codes=state.get('codes',[])
                copied=state.get('copied') or {}
                if not codes and copied.get('token')==token:codes=[copied['code']]
                fresh=bool(issued_at is not None or set(codes)-baseline)
                if posted and fresh and not state.get('disabled'):
                    if len(codes)==1:return valid_code(codes[0])
                    if len(codes)>1:raise SiteError('발급 코드가 여러 개여서 하나로 구분하지 못했어요.')
                if posted and issued_at is not None and not codes and not copy_tried:
                    copy_tried=bool(self.rpc('evaluate',{'script':COPY_RESULT_JS+'('+json.dumps(token)+')'},10))
                # A successful server action can update the form before the
                # result card is re-rendered. Refresh the GET once, never POST.
                if posted and issued_at is not None and not codes and not refreshed and time.monotonic()-issued_at>=.8:
                    self.ready_form(slug,cancelled,force=True,path=path);refreshed=True;continue
                time.sleep(.08)
            raise SiteError('제출 후 세이브 코드를 읽지 못했어요. 사이트 결과를 확인해 주세요. 중복 전송하지 않았어요.')
        except LoginRequired as exc:raise SiteError('전송 후 로그인 화면으로 바뀌었어요. 사이트에서 결과를 확인해 주세요.') from exc
    def close(self):pass
