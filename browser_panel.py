"""A real embedded Chromium browser. No external browser or debug socket."""
from __future__ import annotations
import json
import re
import threading
import time
from dataclasses import dataclass,field
from urllib.parse import urlsplit
from PySide6.QtCore import QObject,QTimer,QUrl,Signal,Slot,Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QTabWidget,QTabBar,QPushButton,QLineEdit,QLabel,QFileDialog
from PySide6.QtWebEngineCore import QWebEngineProfile,QWebEnginePage,QWebEngineUrlRequestInterceptor,QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from core import BASE


@dataclass
class Call:
    action:str
    payload:dict
    deadline:float
    event:threading.Event=field(default_factory=threading.Event)
    value:object=None
    error:str=''
    cancelled:bool=False

    def finish(self,value=None,error=''):
        if not self.event.is_set():
            self.value,self.error=value,error
            self.event.set()


class RequestWatch(QWebEngineUrlRequestInterceptor):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.lock=threading.Lock()
        self.token=self.host=self.path=''
        self.seen=set()

    def arm(self,token,host,path):
        with self.lock:self.token,self.host,self.path=token,host,path

    def interceptRequest(self,info):
        if bytes(info.requestMethod())!=b'POST':return
        url=info.requestUrl()
        with self.lock:
            if self.token and url.host()==self.host and url.path().rstrip('/')==self.path:
                self.seen.add(self.token)
                # Keep only the current request marker, never headers or bodies.
                if len(self.seen)>100:self.seen={self.token}

    def post_seen(self,token):
        with self.lock:return token in self.seen


class BrowserPage(QWebEnginePage):
    def __init__(self,profile,panel,parent=None):
        super().__init__(profile,parent)
        self.panel=panel

    def createWindow(self,_kind):
        if self.panel.disposing:return None
        view=self.panel.add_view('로그인')
        self.panel.tabs.setCurrentWidget(view)
        self.panel.reveal.emit()
        return view.page()


class BrowserPanel(QWidget):
    reveal=Signal()
    def __init__(self,storage,parent=None,base=BASE):
        super().__init__(parent)
        self.base=base
        self.disposing=False
        self.disposed=False
        self.dispose_callbacks=[]
        self.allowed_hosts={urlsplit(base).hostname}
        self.profile=QWebEngineProfile('SCRMapsEmbedded',self)
        self.profile.setPersistentStoragePath(str(storage))
        self.profile.setCachePath(str(storage/'cache'))
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        self.profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
        self.watch=RequestWatch(self.profile)
        self.profile.setUrlRequestInterceptor(self.watch)
        self.profile.downloadRequested.connect(self.download)
        self.states={}
        self.login_state=None
        self.auth_in_progress=False
        self.nav_call=None
        self.nav_started=False
        outer=QVBoxLayout(self)
        bar=QHBoxLayout()
        for title,callback in [('뒤로',lambda:self.current().back()),('새로고침',lambda:self.current().reload()),('SCRMaps',lambda:self.main.load(QUrl(self.base))),('로그인',self.login)]:
            button=QPushButton(title);button.clicked.connect(callback);bar.addWidget(button)
        self.address=QLineEdit();self.address.setReadOnly(True);bar.addWidget(self.address,1)
        outer.addLayout(bar)
        self.tabs=QTabWidget();self.tabs.setTabsClosable(True);self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self.update_address);outer.addWidget(self.tabs,1)
        self.main=self.add_view('SCRMaps')
        self.tabs.tabBar().setTabButton(0,QTabBar.ButtonPosition.RightSide,None)
        self.tabs.tabBar().setTabButton(0,QTabBar.ButtonPosition.LeftSide,None)
        self.main.loadFinished.connect(self.navigation_finished)
        self.main.loadStarted.connect(self.navigation_started)
        hint=QLabel('이 창에서 SCRMaps·Battle.net에 로그인하세요. 로그인 완료 후 대기 중인 번호가 자동으로 처리됩니다.')
        hint.setWordWrap(True);hint.setObjectName('hint');outer.addWidget(hint)
        self.timer=QTimer(self);self.timer.timeout.connect(self.poll);self.timer.start(1000)
        self.load_started=False

    def current(self):return self.tabs.currentWidget() or self.main

    def download(self,request):
        if self.disposing:request.cancel();return
        path,_=QFileDialog.getSaveFileName(self,'파일 저장',request.downloadFileName())
        if not path:request.cancel();return
        from pathlib import Path
        target=Path(path);request.setDownloadDirectory(str(target.parent));request.setDownloadFileName(target.name);request.accept()

    def add_view(self,title):
        view=QWebEngineView()
        page=BrowserPage(self.profile,self,view);view.setPage(page)
        page.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows,True)
        self.tabs.addTab(view,title)
        view.urlChanged.connect(lambda _url,v=view:self.url_changed(v))
        view.titleChanged.connect(lambda text,v=view:self.tabs.setTabText(self.tabs.indexOf(v),text[:22] or title))
        view.loadFinished.connect(lambda _ok,v=view:self.poll_view(v))
        page.windowCloseRequested.connect(lambda v=view:self.close_view(v))
        return view

    def update_address(self,*_args):
        if self.disposing:return
        view=self.current()
        if view:self.address.setText(view.url().toString())
        self.update_state()

    def url_changed(self,view):
        self.states.pop(id(view),None)
        self.update_address()

    def update_state(self):
        if self.disposing:return
        values=list(self.states.values())
        self.login_state=True if True in values else False if False in values else None
        active=self.current().url().host()
        # Also leave third-party identity-provider tabs undisturbed while the
        # user completes an official sign-in flow.
        self.auth_in_progress=bool(active and active not in self.allowed_hosts)

    def poll_view(self,view):
        if self.disposing:return
        if view.url().host() not in self.allowed_hosts:return
        def result(value):
            if self.disposing:return
            if self.tabs.indexOf(view)<0:return
            self.states[id(view)]=True if value=='yes' else False if value=='no' else None
            self.update_state()
        view.page().runJavaScript("(() => {const h=document.querySelector('header')?.innerText||'';return /로그아웃|log\\s*out|sign\\s*out/i.test(h)?'yes':/로그인|sign\\s*in|log\\s*in/i.test(h)?'no':'unknown';})()",0,result)

    def poll(self):
        for i in range(self.tabs.count()):self.poll_view(self.tabs.widget(i))

    def login(self):
        if self.disposing:return
        self.reveal.emit()
        if self.auth_in_progress:return
        if self.login_state is True:
            if not self.load_started:self.main.load(QUrl(self.base))
        else:
            self.main.load(QUrl(self.base+'/login'))
        self.load_started=True

    def navigation_started(self):
        if self.nav_call:self.nav_started=True

    def navigation_finished(self,ok):
        call=self.nav_call
        if call and not self.nav_started and not ok:return
        self.nav_call=None
        if call and not call.cancelled:
            # HTTP errors / network errors are preflight failures. No code click
            # has been issued at this point.
            call.finish({'url':self.main.url().toString()},'' if ok else '사이트 페이지를 불러오지 못했어요. 내장 브라우저의 주소와 연결 상태를 확인해 주세요.')

    def close_tab(self,index):
        view=self.tabs.widget(index)
        if view is self.main:return
        self.close_view(view)

    def close_view(self,view):
        if self.disposing:return
        if view is self.main:return
        index=self.tabs.indexOf(view)
        if index>=0:self.tabs.removeTab(index)
        self.states.pop(id(view),None)
        view.page().deleteLater();view.deleteLater();self.update_state()

    def stop_loading(self):
        self.timer.stop()
        call,self.nav_call=self.nav_call,None
        if call:call.cancelled=True;call.finish(error='프로그램을 종료합니다.')
        for i in range(self.tabs.count()):self.tabs.widget(i).stop()

    def dispose(self,on_finished=None):
        if self.disposed:
            if on_finished:QTimer.singleShot(0,on_finished)
            return
        if on_finished:self.dispose_callbacks.append(on_finished)
        if self.disposing:return
        self.disposing=True
        self.stop_loading()
        # The profile owns persistent cookies/cache. Delete every page first,
        # then wait for actual profile destruction before quitting the event loop.
        views=[self.tabs.widget(i) for i in range(self.tabs.count())]
        remaining=[len(views)]
        def page_destroyed(*_args):
            remaining[0]-=1
            if remaining[0]==0:self.profile.deleteLater()
        def profile_destroyed(*_args):
            self.disposed=True
            callbacks,self.dispose_callbacks=self.dispose_callbacks,[]
            for callback in callbacks:QTimer.singleShot(0,callback)
        self.profile.destroyed.connect(profile_destroyed)
        self.tabs.blockSignals(True)
        for i in reversed(range(self.tabs.count())):
            view=self.tabs.widget(i);self.tabs.removeTab(i)
            page=view.page();page.destroyed.connect(page_destroyed)
            view.blockSignals(True);page.blockSignals(False)
            page.deleteLater();view.deleteLater()
        if not views:self.profile.deleteLater()


class BrowserBridge(QObject):
    request=Signal(object)
    def __init__(self,panel):
        super().__init__(panel)
        self.panel=panel
        self.lock=threading.Lock()
        self.closed=False
        self.pending={}
        self.request.connect(self.execute,Qt.ConnectionType.QueuedConnection)

    @property
    def login_state(self):return self.panel.login_state
    @property
    def auth_in_progress(self):return self.panel.auth_in_progress
    @property
    def loaded(self):return self.panel.load_started
    def post_seen(self,token):return self.panel.watch.post_seen(token)

    def call(self,action,payload=None,timeout=20):
        call=Call(action,payload or {},time.monotonic()+timeout)
        with self.lock:
            if self.closed:raise RuntimeError('프로그램을 종료합니다.')
            self.pending[id(call)]=call
            self.request.emit(call)
        try:
            if not call.event.wait(timeout):
                call.cancelled=True
                raise RuntimeError('내장 브라우저 응답 시간이 초과됐어요. 사이트 화면을 확인해 주세요.')
            if call.error:raise RuntimeError(call.error)
            return call.value
        finally:
            with self.lock:self.pending.pop(id(call),None)

    def close(self):
        with self.lock:
            self.closed=True
            for call in self.pending.values():
                call.cancelled=True;call.finish(error='프로그램을 종료합니다.')

    @Slot(object)
    def execute(self,call):
        if self.closed or call.cancelled or time.monotonic()>call.deadline:
            call.finish(error='브라우저 작업이 만료됐어요.');return
        try:
            p=self.panel
            if call.action=='show':p.reveal.emit();call.finish(True)
            elif call.action=='navigate':
                url=QUrl(call.payload['url'])
                if url.scheme() not in {'https','http'} or url.host() not in p.allowed_hosts:
                    raise ValueError('허용되지 않은 사이트 주소예요.')
                if p.nav_call:p.nav_call.finish(error='이전 페이지 이동을 중단했어요.')
                p.nav_call=call;p.nav_started=False;p.load_started=True;p.main.load(url)
            elif call.action=='evaluate':
                if p.main.url().host() not in p.allowed_hosts:
                    call.finish('');return
                p.main.page().runJavaScript(call.payload['script'],0,lambda result:call.finish(result))
            elif call.action=='arm':
                p.watch.arm(call.payload['token'],call.payload['host'],call.payload['path']);call.finish(True)
            else:raise ValueError('지원하지 않는 브라우저 작업이에요.')
        except Exception as exc:call.finish(error=str(exc))
