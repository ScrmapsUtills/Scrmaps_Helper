from __future__ import annotations
import copy, queue, threading, time
from pathlib import Path
from core import History, project_slug, sha256_file, valid_code
from web_gateway import Gateway, LoginRequired, fetch_maps
from paths import DATA

class Worker(threading.Thread):
    def __init__(self, events, commands, closing, gateway=None, nickname=''):
        super().__init__(daemon=True)
        self.events, self.commands, self.closing = events, commands, closing
        self.reader = None
        self.history = None
        self.gateway = gateway or Gateway(DATA / "browser_profile")
        self.session_state = "unchecked"
        self.last_session_poll = 0
        self.waiting_login={}
        self.active_nickname=nickname.strip()

    def remember_login(self,auth,cfg,image_hash,cancel):
        key=(cfg['project'],cfg['nickname'],auth)
        self.waiting_login[key]={'auth':auth,'cfg':copy.deepcopy(cfg),'image_hash':image_hash,'cancel':cancel,'next':time.monotonic()+2}

    def restore_login(self):
        if not self.active_nickname:return
        for row in self.history.list():
            if row['status']=='login' and row['nickname']==self.active_nickname:
                key=(row['project'],row['nickname'],row['auth'])
                if key not in self.waiting_login:
                    self.remember_login(row['auth'],{'project':row['project'],'nickname':row['nickname'],'auto':True},row['image_hash'],threading.Event())

    def resume_login(self):
        for key,job in list(self.waiting_login.items()):
            if job['cancel'].is_set():
                self.history.put(*key,'paused',image_hash=job['image_hash'])
                self.waiting_login.pop(key,None)
        if self.closing.is_set():return
        ready=self.gateway.can_resume() if hasattr(self.gateway,'can_resume') else self.gateway.peek_login() is True
        if not ready:return
        now=time.monotonic()
        for key,job in list(self.waiting_login.items()):
            if job['cfg']['nickname']!=self.active_nickname or now<job['next']:continue
            row=self.history.get(*key)
            if not row or row['status']!='login':
                self.waiting_login.pop(key,None);continue
            self.waiting_login.pop(key,None)
            self.log('로그인이 확인되어 대기 중인 인증번호를 자동으로 처리합니다.')
            self.submit(job['auth'],job['cfg'],job['image_hash'],cancel=job['cancel'],resuming=True)
            return

    def emit(self, kind, **payload):
        self.events.put((kind, payload))

    def log(self, text):
        self.emit("log", text=text)

    def request_stop(self):
        self.closing.set()
        try:self.commands.put_nowait(('shutdown',None))
        except queue.Full:pass

    def run(self):
        try:
            self.history = History(getattr(self,'data_path',DATA) / "history.sqlite3")
            # A previous process may have exited during a network request. Such
            # rows are intentionally retained and are never automatically retried.
            self.emit("history", rows=self.history.list())
            self.restore_login()
            while not self.closing.is_set():
                try:
                    command, payload = self.commands.get(timeout=.25)
                except queue.Empty:
                    if time.monotonic()-self.last_session_poll>1:
                        self.last_session_poll=time.monotonic()
                        try:
                            state=self.gateway.peek_login()
                            if state!=self.session_state:
                                self.session_state=state
                                self.emit("connection",connected=state)
                            self.resume_login()
                        except Exception:
                            pass
                    continue
                if self.closing.is_set():break
                try:
                    if command == "maps":
                        maps = fetch_maps()
                        if not maps:
                            raise ValueError("목록을 읽지 못했습니다. 맵 주소를 직접 입력할 수 있습니다.")
                        self.emit("maps", maps=maps)
                        self.log(f"맵 목록 {len(maps)}개를 불러왔습니다.")
                    elif command == "login":
                        self.log("전용 브라우저를 여는 중입니다…")
                        self.gateway.open_login(payload["project"])
                        self.log("브라우저에서 로그인하세요. 기존 일반 브라우저와 별도 로그인 상태를 사용합니다.")
                    elif command == "image":
                        self.process_image(**payload)
                    elif command == "submit":
                        self.submit(**payload)
                    elif command == "history":
                        self.emit("history", rows=self.history.list())
                    elif command == "close_browser":
                        self.gateway.close()
                        self.log("전용 브라우저를 닫았습니다. 로그인 정보는 다음 실행에 재사용됩니다.")
                    elif command=='account':
                        self.active_nickname=str(payload).strip()
                        self.restore_login()
                except Exception as exc:
                    self.log(f"처리 중단: {exc}")
                    self.emit("stage",phase="review",text=str(exc))
                finally:
                    self.emit("idle")
        except Exception as exc:
            self.emit("fatal", text=str(exc))
        finally:
            for key,job in self.waiting_login.items():
                if job['cancel'].is_set() and self.history:
                    self.history.put(*key,'paused',image_hash=job['image_hash'])
            self.gateway.close()
            if self.history:
                self.history.close()

    def process_image(self, path, cfg, cancel):
        if cancel.is_set() or self.closing.is_set():
            return
        self.log(f"스크린샷 인식 중: {Path(path).name}")
        self.emit("stage",phase="reading",text="사진에서 인증번호와 맵을 찾고 있어요…")
        if self.reader is None:
            self.log("문자 인식 엔진을 처음 불러오는 중입니다…")
            from recognition import Reader
            self.reader = Reader()
        before_hash = sha256_file(path)
        result = self.reader.read(path)
        if sha256_file(path) != before_hash:
            raise ValueError("인식 중 사진이 변경되었습니다. 저장이 끝난 파일을 다시 불러오세요.")
        cfg=copy.deepcopy(cfg)
        if cfg.get("project") and result.project and cfg["project"]!=result.project:
            result.confident=False
            result.message=f"선택한 맵 /{cfg['project']}와 사진의 맵 /{result.project}가 달라요. 확인 후 제출해 주세요."
        elif not cfg.get("project"):
            cfg["project"]=result.project
        self.emit("recognition", result=result, cfg=cfg, image_hash=before_hash, path=str(path))
        if not result.code:
            self.log(result.message)
            self.emit("stage",phase="review",text=result.message)
            return
        self.log(f"인식: {result.code} / 신뢰 점수 {result.score:.1%}")
        if cancel.is_set() or self.closing.is_set():
            self.log("감지가 중지되어 자동 제출하지 않았습니다.")
            return
        if cfg["auto"] and result.confident:
            self.submit(result.code, cfg, before_hash, cancel=cancel)
        else:
            self.log("확인 대기: 인증번호를 확인한 뒤 ‘이 번호 제출’을 누르세요.")
            self.emit("stage",phase="review",text=result.message or "인식한 번호를 확인해 주세요.")

    def submit(self, auth, cfg, image_hash="", retry=False, cancel=None, resuming=False):
        cancel = cancel or threading.Event()
        slug, nick, auth = project_slug(cfg["project"]), cfg["nickname"].strip(), valid_code(auth)
        if not nick:
            raise ValueError("게임 닉네임을 입력하세요. 닉네임은 이 프로그램의 기록 구분에 사용됩니다.")
        if cancel.is_set() or self.closing.is_set():
            if resuming:
                self.history.put(slug,nick,auth,'paused',image_hash=image_hash)
            return
        previous = self.history.get(slug, nick, auth)
        if not self.active_nickname:self.active_nickname=nick
        safe_resume=resuming and previous and previous['status']=='login'
        if previous and not retry and not safe_resume:
            if previous["status"] == "ok":
                self.emit("save", code=previous["save"], project=slug, nickname=nick)
                self.log("이미 처리한 인증번호입니다. 보관된 세이브 코드를 표시했습니다.")
            elif previous['status']=='login':
                self.remember_login(auth,cfg,image_hash,cancel)
                self.emit('stage',phase='login',text='앱 안에서 로그인하면 대기 중인 번호를 자동으로 처리해요.')
                self.emit('browser')
            else:
                self.log("이 번호는 처리 이력이 있어 자동 재제출하지 않았습니다. 브라우저 결과 확인 후 ‘재시도’를 사용하세요.")
                self.emit("pending",auth=auth,cfg=cfg,image_hash=image_hash)
                self.emit("stage",phase="review",text="이전에 처리하던 번호예요. 사이트 결과를 확인한 뒤 재시도해 주세요.")
            return
        self.history.put(slug, nick, auth, "submitting", image_hash=image_hash)
        self.log(f"/{slug}에 인증번호를 제출하는 중입니다…")
        self.emit("stage",phase="submitting",text=f"/{slug}에서 세이브 코드를 가져오고 있어요…")
        try:
            code = self.gateway.submit(slug, auth, lambda: cancel.is_set() or self.closing.is_set())
        except LoginRequired as exc:
            self.history.put(slug, nick, auth, "login", detail=str(exc), image_hash=image_hash)
            self.remember_login(auth,cfg,image_hash,cancel)
            self.emit("pending", auth=auth, cfg=cfg, image_hash=image_hash)
            self.log(str(exc) + " 로그인 완료 후 자동으로 이어서 처리합니다.")
            self.emit("connection",connected=False)
            self.emit("stage",phase="login",text="앱 안에서 로그인을 완료해 주세요. 대기 중인 번호는 자동으로 처리돼요.")
            self.emit('browser')
            if hasattr(self.gateway,'open_login'):
                try:self.gateway.open_login(slug)
                except Exception as login_error:self.log(str(login_error))
        except Exception as exc:
            self.history.put(slug, nick, auth, "check", detail=str(exc), image_hash=image_hash)
            self.emit("pending", auth=auth, cfg=cfg, image_hash=image_hash)
            self.log(f"결과 확인 필요: {exc}")
            self.emit("stage",phase="review",text=str(exc))
        else:
            self.history.put(slug, nick, auth, "ok", save=code, image_hash=image_hash)
            self.emit("save", code=code, project=slug, nickname=nick)
            self.emit("connection",connected=True)
            self.log("발급된 세이브 코드를 보관했습니다.")
        finally:
            self.emit("history", rows=self.history.list())

