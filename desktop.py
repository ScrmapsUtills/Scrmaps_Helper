from __future__ import annotations
import copy,json,queue,sys,threading,time
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QUrl,QLockFile
from PySide6.QtGui import QDesktopServices,QFont,QIcon,QPixmap,QImageReader
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
 QTabWidget,QComboBox,QLineEdit,QFrame,QFileDialog,QMessageBox,QCheckBox,QPlainTextEdit,QTableWidget,QTableWidgetItem,QHeaderView,QScrollArea)
from core import NewFiles,project_slug,valid_code,valid_save_code,verified_save,write_json,IMAGE_EXTS,APP_VERSION
from paths import ROOT,DATA,default_folder
from worker import Worker
from web_gateway import fetch_maps
from browser_panel import BrowserPanel,BrowserBridge
from embedded_gateway import EmbeddedGateway
from key_sender import CodeTyper,HotkeyMonitor,make_keyboard
from theme import STYLE

AUTO='자동 인식 · 사진에서 맵 찾기'
DEFAULTS={'folder':'','project':'','auto_map':True,'nickname':'','auto':True,'auto_submit_policy':1,'recursive':True,'maps':[]}

LEGACY_STYLE='''
QWidget { background:#101722; color:#e9f1fc; font-family:"Malgun Gothic","Noto Sans CJK KR"; font-size:14px; }
QLabel#brand { font-size:28px; font-weight:700; color:#67d5ed; }
QLabel#hint { color:#99aec6; font-size:12px; }
QLabel#phase { font-size:20px; font-weight:700; color:#67d5ed; }
QFrame#card { background:#182332; border:1px solid #27374b; border-radius:10px; }
QFrame#card QLabel { background:transparent; }
QPushButton { background:#243449; border:0; border-radius:6px; padding:11px 18px; }
QPushButton:hover { background:#324b65; }
QPushButton:disabled { color:#668095; background:#1b2939; }
QPushButton#primary { background:#087e99; font-weight:700; padding:13px 24px; }
QPushButton#primary:hover { background:#0999af; }
QLineEdit,QComboBox { background:#202f43; border:1px solid #384c65; border-radius:5px; padding:9px; }
QLineEdit:disabled,QComboBox:disabled { color:#9ab0c8; }
QLineEdit#code { font-family:Consolas; font-size:33px; font-weight:700; padding:15px; }
QTabWidget::pane { border:0; }
QTabBar::tab { padding:12px 22px; color:#9fb3ca; background:#101722; }
QTabBar::tab:selected { color:#67d5ed; background:#1b293b; border-bottom:2px solid #43b9d7; }
QTableWidget,QPlainTextEdit { background:#141f2e; border:1px solid #2c4059; border-radius:5px; }
QHeaderView::section { background:#243449; color:#b3c5dc; padding:9px; border:0; }
QScrollArea { border:0; }
'''


def button(text,callback,primary=False):
    item=QPushButton(text);item.clicked.connect(callback)
    if primary:item.setObjectName('primary')
    return item


def label(text='',name=None):
    item=QLabel(text);item.setWordWrap(True)
    if name:item.setObjectName(name)
    return item


def card(layout):
    frame=QFrame();frame.setObjectName('card');body=QVBoxLayout(frame);body.setContentsMargins(20,18,20,18);body.setSpacing(12);layout.addWidget(frame)
    return frame,body


class Window(QMainWindow):
    def __init__(self,data=DATA,base=None,quit_on_close=True):
        super().__init__()
        self.data=Path(data);self.data.mkdir(parents=True,exist_ok=True)
        self.cfg=copy.deepcopy(DEFAULTS)
        try:
            saved=json.loads((self.data/'settings.json').read_text(encoding='utf-8'))
            self.cfg.update({k:v for k,v in saved.items() if k in DEFAULTS})
            if saved.get('auto_submit_policy')!=1:self.cfg['auto']=True
            self.cfg['auto_submit_policy']=1
        except (OSError,ValueError,TypeError):pass
        if not self.cfg['folder'] or not Path(self.cfg['folder']).is_dir():self.cfg['folder']=default_folder()
        self.events=queue.Queue();self.commands=queue.Queue(maxsize=80);self.closing=threading.Event()
        self.watch_cancel=None;self.pending_cfg=None;self.pending_hash='';self.current_save=None;self.rows=[]
        self.allow_close=False
        self.quit_on_close=quit_on_close
        self.shutdown_started=False
        self.typer=CodeTyper(self.events);self.hotkeys=None
        self.setWindowTitle('SCRMaps Helper');self.resize(1060,840);self.setMinimumSize(900,720)
        self.setWindowIcon(QIcon(str(ROOT/'assets'/'helper.png')));self.setAcceptDrops(True)
        self.setStyleSheet(STYLE)
        outer=QWidget();body=QVBoxLayout(outer);body.setContentsMargins(28,24,28,24);body.setSpacing(18);self.setCentralWidget(outer)
        header=QHBoxLayout();header.setSpacing(14)
        logo=QLabel();logo.setFixedSize(52,52);logo.setPixmap(QPixmap(str(ROOT/'assets'/'helper.png')).scaled(52,52,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation));header.addWidget(logo)
        brand=QVBoxLayout();brand.setSpacing(3);brand.addWidget(label('SCRMaps Helper','brand'));brand.addWidget(label('스크린샷으로 저장하고, F8로 간편하게 입력하세요.','hint'));header.addLayout(brand,1)
        header.addWidget(label('v'+APP_VERSION,'badge'));self.login_button=button('앱에서 로그인',self.login);header.addWidget(self.login_button);body.addLayout(header)
        self.tabs=QTabWidget();body.addWidget(self.tabs,1)
        save_page=QWidget();save_layout=QVBoxLayout(save_page);save_layout.setContentsMargins(0,16,0,0);save_layout.setSpacing(14)
        scroll=QScrollArea();self.save_scroll=scroll;scroll.setWidgetResizable(True);scroll.setWidget(save_page);self.tabs.addTab(scroll,'자동 저장')
        choices=QHBoxLayout();choices.setSpacing(16);left=QVBoxLayout();left.addWidget(label('플레이할 맵','hint'));self.project=QComboBox();self.project.setEditable(True);left.addWidget(self.project);choices.addLayout(left,3)
        right=QVBoxLayout();right.addWidget(label('게임 닉네임','hint'));self.nickname=QLineEdit(self.cfg['nickname']);self.nickname.setPlaceholderText('스타에서 사용하는 닉네임');right.addWidget(self.nickname);choices.addLayout(right,2);save_layout.addLayout(choices)
        self.set_maps(self.cfg['maps']);self.project.setCurrentText(AUTO if self.cfg['auto_map'] else self.cfg['project'])
        _,state=card(save_layout)
        steps=QHBoxLayout();steps.setSpacing(10);self.steps=[]
        for title in ('01  스크린샷 대기','02  번호 인식','03  코드 발급'):
            chip=label(title,'step');steps.addWidget(chip,1);self.steps.append(chip)
        state.addLayout(steps);self.phase=label('스크린샷을 기다릴 준비가 됐어요','phase');self.status=label('자동 저장을 시작하고 스타에서 인증번호 화면을 찍어 주세요.','hint');state.addWidget(self.phase);state.addWidget(self.status)
        actions=QHBoxLayout();self.watch_button=button('자동 저장 시작',self.toggle_watch,True);actions.addWidget(self.watch_button);actions.addWidget(button('사진 불러오기',self.import_image));actions.addStretch();state.addLayout(actions)
        _,result=card(save_layout);self.save_label=label('세이브 코드','section');result.addWidget(self.save_label);self.code=QLineEdit();self.code.setReadOnly(True);self.code.setAlignment(Qt.AlignmentFlag.AlignCenter);self.code.setObjectName('code');self.code.setPlaceholderText('발급된 코드가 여기에 표시됩니다');result.addWidget(self.code)
        actions=QHBoxLayout();self.copy_button=button('코드 복사',self.copy_code,True);self.typer_button=button('입력 안내',self.open_typer);self.copy_button.setEnabled(False);self.typer_button.setEnabled(False);actions.addWidget(self.copy_button);actions.addWidget(self.typer_button);actions.addStretch();actions.addWidget(label('F8 입력   ·   F9 중단','badge'));result.addLayout(actions)
        self.typing_status=label('스타의 코드 입력 칸에서 F8을 누르면 코드 입력 후 Enter를 두 번 누릅니다.','hint');result.addWidget(self.typing_status)
        self.hotkey_status=label('F8/F9 감지 확인 중…','hint');result.addWidget(self.hotkey_status)
        self.review,review=card(save_layout);self.review_label=label('인식 결과 확인','hint');review.addWidget(self.review_label)
        self.ocr_preview=QLabel();self.ocr_preview.setAlignment(Qt.AlignmentFlag.AlignCenter);self.ocr_preview.setMaximumHeight(130);review.addWidget(self.ocr_preview)
        self.auth_candidates=QComboBox();self.auth_candidates.setToolTip('실제로 인식된 후보입니다. 확대 원본과 비교한 뒤 선택하세요.');self.auth_candidates.activated.connect(lambda index:self.auth.setText(self.auth_candidates.itemText(index)));review.addWidget(self.auth_candidates);self.auth_candidates.hide()
        row=QHBoxLayout();self.auth=QLineEdit();self.auth.setPlaceholderText('인증번호');self.review_project=QLineEdit();self.review_project.setPlaceholderText('맵 주소');row.addWidget(self.auth,2);row.addWidget(self.review_project,2);row.addWidget(button('확인 후 제출',lambda:self.manual_submit(False)));row.addWidget(button('결과 확인 후 재제출',lambda:self.manual_submit(True)));review.addLayout(row);self.review.hide()
        self.last_image=label('사진을 이 창으로 끌어다 놓아도 인식할 수 있어요. 영역 지정은 필요하지 않습니다.','hint');save_layout.addWidget(self.last_image);save_layout.addStretch()
        kwargs={'base':base} if base else {}
        self.browser=BrowserPanel(self.data/'embedded_profile',**kwargs);self.browser.reveal.connect(self.show_browser);self.tabs.addTab(self.browser,'SCRMaps · 로그인')
        history=QWidget();layout=QVBoxLayout(history);layout.addWidget(label('맵·닉네임별 보관 기록'))
        self.table=QTableWidget(0,5);self.table.setHorizontalHeaderLabels(['시간','맵','닉네임','세이브 코드','상태']);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows);self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers);self.table.cellClicked.connect(self.select_history);layout.addWidget(self.table,1);layout.addWidget(button('선택한 코드 보기',lambda:self.tabs.setCurrentIndex(0)));self.tabs.addTab(history,'보관 기록')
        self.table.setAlternatingRowColors(True);self.table.verticalHeader().hide();self.table.verticalHeader().setDefaultSectionSize(42);self.table.setShowGrid(False)
        settings=QWidget();layout=QVBoxLayout(settings);layout.addWidget(label('스크린샷 저장 폴더'));row=QHBoxLayout();self.folder=QLineEdit(self.cfg['folder']);row.addWidget(self.folder,1);self.folder_button=button('변경',self.choose_folder);row.addWidget(self.folder_button);layout.addLayout(row)
        self.auto=QCheckBox('사진에서 읽은 번호를 확인 없이 바로 제출');self.auto.setChecked(self.cfg['auto']);layout.addWidget(self.auto)
        self.recursive=QCheckBox('스크린샷 하위 폴더도 확인');self.recursive.setChecked(self.cfg['recursive']);layout.addWidget(self.recursive)
        layout.addWidget(label('로그인 전 번호는 기다렸다가 로그인 완료 후 자동 처리합니다. 전송 후 결과가 불확실한 번호는 반복 제출하지 않습니다.','hint'))
        layout.addWidget(label('이 버전에서는 앱 안에서 최초 한 번 로그인하세요. 일반 크롬·엣지 로그인은 자동으로 가져오지 않습니다.','hint'))
        row=QHBoxLayout();row.addWidget(button('맵 목록 새로고침',self.refresh_maps));row.addWidget(button('기록 폴더 열기',lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.data)))));row.addStretch();layout.addLayout(row)
        layout.addWidget(button('키 입력 권한 확인',self.keyboard_permissions))
        layout.addWidget(label('Helper '+APP_VERSION+' · OCR과 내장 브라우저가 설치 파일에 포함됩니다.','hint'))
        self.logs=QPlainTextEdit();self.logs.setReadOnly(True);self.logs.setMaximumBlockCount(500);layout.addWidget(self.logs,1);self.tabs.addTab(settings,'설정')
        self.config_widgets=[self.project,self.nickname,self.folder,self.folder_button,self.auto,self.recursive]
        for widget in (self.nickname,self.folder,self.code,self.auth,self.review_project,self.project.lineEdit()):widget.setAcceptDrops(False)
        self.project.currentTextChanged.connect(self.changed);self.nickname.textChanged.connect(self.changed)
        self.bridge=BrowserBridge(self.browser);self.gateway=EmbeddedGateway(self.bridge,self.closing,**kwargs)
        self.worker=Worker(self.events,self.commands,self.closing,self.gateway,self.cfg['nickname'])
        # Give the worker a user-data path without changing the application's
        # storage global in tests or embedding private browser data in exports.
        self.worker.data_path=self.data
        self.worker.start()
        self.command('warmup')
        self.timer=QTimer(self);self.timer.timeout.connect(self.drain);self.timer.start(50)
        self.log('내장 브라우저로 로그인과 코드 발급을 처리합니다. 로그인 대기는 자동으로 이어집니다.')
        if sys.platform in {'win32','darwin'}:QTimer.singleShot(0,self.register_hotkeys)
        else:self.hotkey_status.setText('이 운영체제의 자동 입력은 지원하지 않습니다.')
        self.refresh_maps()
        self.browser.load_started=True
        QTimer.singleShot(0,lambda:self.browser.main.load(QUrl(self.browser.base+'/')) if not self.closing.is_set() else None)

    def command(self,name,payload=None):
        try:self.commands.put_nowait((name,payload))
        except queue.Full:self.events.put(('log',{'text':'작업이 쌓여 있어요. 잠시 기다려 주세요.'}))

    def log(self,text):self.logs.appendPlainText(time.strftime('%H:%M:%S  ')+text)
    def selected(self):
        value=self.project.currentText().strip()
        return '' if value in {'',AUTO} else project_slug(value.split(' | ')[-1])

    def config(self):
        cfg=copy.deepcopy(self.cfg);slug=self.selected();nick=self.nickname.text().strip()
        if not nick:raise ValueError('게임 닉네임을 입력해 주세요.')
        cfg.update(project=slug,auto_map=not bool(slug),nickname=nick,folder=self.folder.text().strip(),auto=self.auto.isChecked(),recursive=self.recursive.isChecked())
        return cfg

    def persist(self):
        self.cfg.update(folder=self.folder.text().strip(),nickname=self.nickname.text().strip(),auto=self.auto.isChecked(),recursive=self.recursive.isChecked())
        try:self.cfg.update(project=self.selected(),auto_map=not bool(self.selected()))
        except ValueError:pass
        write_json(self.data/'settings.json',self.cfg)

    def changed(self,*_args):
        self.pending_cfg=None;self.pending_hash='';self.auth.clear();self.review.hide();self.clear_code()
        self.command('account',self.nickname.text())

    def set_maps(self,maps):
        current=self.project.currentText();self.project.blockSignals(True);self.project.clear();self.project.addItem(AUTO)
        for item in maps:self.project.addItem(f"{item['name']}  |  {item['slug']}")
        self.project.setCurrentText(current or AUTO);self.project.blockSignals(False);self.cfg['maps']=maps

    def refresh_maps(self):
        def run():
            try:self.events.put(('maps',{'maps':fetch_maps()}))
            except Exception:self.events.put(('log',{'text':'맵 목록을 불러오지 못했어요. 사진에서 맵 주소를 찾는 기능은 사용할 수 있어요.'}))
        threading.Thread(target=run,daemon=True).start()

    def clear_code(self):
        self.typer.stop()
        self.current_save=None;self.code.clear();self.copy_button.setEnabled(False);self.typer_button.setEnabled(False)

    def stage(self,phase,text):
        names={'ready':'준비','watching':'스크린샷 대기 중','reading':'사진을 읽고 있어요','submitting':'세이브 코드를 가져오는 중','login':'로그인 대기 · 완료 후 자동 처리','review':'확인이 필요해요','done':'저장이 완료됐어요','stopped':'자동 저장 중지'}
        self.phase.setText(names.get(phase,'준비'));self.status.setText(text);self.review.setVisible(phase=='review')
        if phase=='review':QTimer.singleShot(0,lambda:self.save_scroll.ensureWidgetVisible(self.review))
        active={'ready':0,'watching':0,'reading':1,'submitting':2,'done':2}.get(phase,-1)
        for index,chip in enumerate(self.steps):
            chip.setProperty('active',index==active);chip.style().unpolish(chip);chip.style().polish(chip)

    def show_browser(self):self.tabs.setCurrentIndex(1)
    def login(self):
        try:self.command('login',{'project':self.selected()});self.show_browser()
        except ValueError as exc:QMessageBox.information(self,'맵 확인',str(exc))

    def choose_folder(self):
        path=QFileDialog.getExistingDirectory(self,'스타크래프트 스크린샷 폴더',self.folder.text())
        if path:self.folder.setText(path);self.persist()

    def toggle_watch(self):
        if self.watch_cancel:
            self.watch_cancel.set();self.watch_cancel=None;self.watch_button.setText('자동 저장 시작')
            for widget in self.config_widgets:widget.setEnabled(True)
            self.stage('stopped','새 사진 감지를 중지했어요. 이미 보낸 요청은 결과를 확인합니다.');return
        try:
            cfg=self.config()
            if not cfg['folder'] or not Path(cfg['folder']).is_dir():
                self.tabs.setCurrentIndex(3);raise ValueError('설정에서 스크린샷 폴더를 한 번 선택해 주세요.')
            watch=NewFiles(Path(cfg['folder']),cfg['recursive']);self.persist()
        except Exception as exc:QMessageBox.information(self,'설정 확인',str(exc));return
        cancel=threading.Event();self.watch_cancel=cancel
        self.watch_button.setText('자동 저장 중지')
        for widget in self.config_widgets:widget.setEnabled(False)
        self.stage('watching','스타에서 인증번호 화면을 띄우고 스크린샷 키만 눌러 주세요.')
        def run():
            while not cancel.wait(.25) and not self.closing.is_set():
                try:
                    for job in watch.poll():self.command('image',{'path':job.path,'cfg':copy.deepcopy(cfg),'cancel':cancel})
                except Exception as exc:self.events.put(('log',{'text':str(exc)}));return
        threading.Thread(target=run,daemon=True).start()

    def import_image(self):
        try:cfg=self.config()
        except ValueError as exc:QMessageBox.information(self,'닉네임',str(exc));return
        path,_=QFileDialog.getOpenFileName(self,'인증번호 스크린샷','','이미지 (*.png *.jpg *.jpeg *.bmp *.pcx *.tga *.webp)')
        if path:self.persist();self.command('image',{'path':Path(path),'cfg':cfg,'cancel':threading.Event()})

    def drop_path(self,mime):
        if not mime.hasUrls() or len(mime.urls())!=1:return None
        url=mime.urls()[0]
        if not url.isLocalFile():return None
        path=Path(url.toLocalFile())
        return path if path.is_file() and path.suffix.lower() in IMAGE_EXTS else None

    def dragEnterEvent(self,event):
        if self.drop_path(event.mimeData()):event.acceptProposedAction()
        else:event.ignore()

    def dropEvent(self,event):
        path=self.drop_path(event.mimeData())
        if not path:event.ignore();return
        try:cfg=self.config()
        except ValueError as exc:QMessageBox.information(self,'닉네임',str(exc));event.ignore();return
        self.persist();self.command('image',{'path':path,'cfg':cfg,'cancel':threading.Event()});event.acceptProposedAction()

    def manual_submit(self,retry):
        try:
            auth=valid_code(self.auth.text());cfg=copy.deepcopy(self.pending_cfg) if self.pending_cfg else self.config()
            cfg['project']=project_slug(self.review_project.text() or cfg.get('project') or self.selected())
            if retry and QMessageBox.question(self,'전송 결과 확인','SCRMaps 탭에서 이전 요청 결과를 확인했나요?\n이미 전송됐을 수 있는 번호를 다시 제출합니다.')!=QMessageBox.StandardButton.Yes:return
            self.clear_code();self.command('submit',{'auth':auth,'cfg':cfg,'image_hash':self.pending_hash,'retry':retry})
        except ValueError as exc:QMessageBox.information(self,'번호 확인',str(exc))

    def display_save(self,code,project,nickname,source='issued'):
        code=valid_save_code(code,project)
        self.typer.stop()
        title='사이트에 보관된 세이브 코드' if source=='existing' else '발급된 세이브 코드'
        self.current_save=code;self.code.setText(code);self.save_label.setText(f'{title} · /{project} · {nickname}')
        self.code.setToolTip(code)
        self.copy_button.setEnabled(True);self.typer_button.setEnabled(True);self.stage('done','사이트의 최근 코드를 읽었어요.' if source=='existing' else '발급된 코드를 보관했어요. 다음 스크린샷도 계속 처리합니다.');self.tabs.setCurrentIndex(0)

    def copy_code(self):
        if self.current_save:
            QApplication.clipboard().setText(self.current_save);self.copy_button.setText('복사했어요')
            QTimer.singleShot(1300,lambda:self.copy_button.setText('코드 복사'))

    def open_typer(self):
        text='스타에서 입력 칸을 열고 한/영을 영문으로 바꾼 뒤 F8을 누르세요. 코드 뒤에 Enter를 두 번 누릅니다. F9로 중단합니다.'
        if sys.platform=='darwin':text+=' 맥에서 F8이 미디어 키라면 Fn(지구본)+F8을 누르세요.'
        self.typing_status.setText(text)

    def register_hotkeys(self):
        if self.closing.is_set():return
        try:
            keyboard=make_keyboard();self.typer.backend=keyboard
            self.hotkeys=HotkeyMonitor(self.events,keyboard);self.hotkeys.start()
        except OSError as exc:self.hotkey_status.setText(str(exc));self.log(str(exc))

    def keyboard_permissions(self):
        if self.typer.backend is None:
            self.register_hotkeys()
        if self.typer.backend is None:return
        text=self.typer.backend.request_permissions()
        if sys.platform=='win32':text='F8/F9 감지 중입니다. 스타와 Helper를 같은 일반 권한으로 실행하세요. F8을 누르면 감지 시각이 표시됩니다.'
        self.hotkey_status.setText(text or '키보드 권한이 준비됐어요. 맥에서는 필요하면 Fn+F8을 사용하세요.')
        self.log(self.hotkey_status.text())

    def hotkey_pressed(self,payload):
        if self.closing.is_set():return
        key=payload['key'];text=time.strftime('%H:%M:%S')+' · '+key+' 감지'
        self.hotkey_status.setText(text);self.log(text)
        if key=='F9':self.typer.stop();return
        try:
            keyboard=self.typer.backend
            self.log('입력 대상: '+keyboard.describe_target(payload['target']))
        except OSError as exc:self.typing_status.setText(str(exc));self.log(str(exc));return
        if self.current_save:self.typer.start(self.current_save,expected_target=payload['target'])
        else:
            text='F8 감지됨 · 먼저 발급된 코드나 보관 기록의 코드를 선택해 주세요.'
            self.typing_status.setText(text);self.log(text)

    def select_history(self,row,_column):
        if not 0<=row<len(self.rows):return
        self.ocr_preview.clear();self.auth_candidates.clear();self.auth_candidates.hide()
        item=self.rows[row];self.auth.setText(item['auth']);self.review_project.setText(item['project']);self.pending_hash=item['image_hash'];self.pending_cfg={'project':item['project'],'nickname':item['nickname']}
        if verified_save(item):self.display_save(item['save'],item['project'],item['nickname'],source='existing' if item['status']=='recovered' else 'issued')
        elif item['status'] in {'ok','recovered','check','submitting'}:
            self.clear_code();self.pending_cfg['auto']=True
            self.command('submit',{'auth':item['auth'],'cfg':self.pending_cfg,'image_hash':item['image_hash']})
        elif item['status'] in {'login','recover_login'}:self.stage('login','로그인이 끝나면 이 번호를 자동으로 처리해요.');self.show_browser()
        else:self.clear_code();self.stage('review',item['detail'] or '사이트의 이전 처리 결과를 확인해 주세요.')

    def drain(self):
        try:
            while True:
                kind,p=self.events.get_nowait()
                if kind=='log':self.log(p['text'])
                elif kind=='hotkey':self.hotkey_pressed(p)
                elif kind=='hotkey_state':self.hotkey_status.setText(p['text']);self.log(p['text'])
                elif kind=='typing':self.typing_status.setText(p['text']);self.log(p['text'])
                elif kind=='stage':self.stage(p['phase'],p['text'])
                elif kind=='connection':self.login_button.setText('로그인됨 · SCRMaps' if p['connected'] is True else '앱에서 로그인' if p['connected'] is False else 'SCRMaps 열기')
                elif kind=='browser':self.show_browser()
                elif kind=='maps':self.set_maps(p['maps']);self.persist()
                elif kind=='recognition':
                    result=p['result'];self.clear_code();self.pending_cfg=p['cfg'];self.pending_hash=p['image_hash'];self.auth.setText(result.code);self.review_project.setText(p['cfg'].get('project',''));self.review_label.setText(result.message or '번호와 맵을 확인해 주세요.');self.last_image.setText(f"최근 사진: {Path(p['path']).name} · 번호: {result.code or '확인 필요'} · 맵: {result.project or '확인 필요'}")
                    self.ocr_preview.clear();self.auth_candidates.clear();self.auth_candidates.addItems(result.alternatives);self.auth_candidates.setVisible(len(result.alternatives)>1)
                    if result.box:
                        image_reader=QImageReader(p['path']);image_reader.setAutoTransform(True);image=QPixmap.fromImage(image_reader.read())
                        if not image.isNull():
                            x,y,w,h=result.box;crop=image.copy(max(0,x-4),max(0,y-4),w+8,h+8)
                            self.ocr_preview.setPixmap(crop.scaled(680,120,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.FastTransformation))
                elif kind=='pending':self.pending_cfg=p['cfg'];self.pending_hash=p['image_hash'];self.auth.setText(p['auth']);self.review_project.setText(p['cfg'].get('project',''))
                elif kind=='save':self.display_save(**p)
                elif kind=='history':
                    self.rows=p['rows'];self.table.setRowCount(len(self.rows));names={'ok':'발급 완료','recovered':'사이트 코드 복구','recover_login':'코드 복구 · 로그인 대기','login':'로그인 대기','check':'결과 확인','submitting':'처리 확인','paused':'중지됨'}
                    for i,item in enumerate(self.rows):
                        for j,key in enumerate(['created','project','nickname','save','status']):
                            value=names.get(item[key],item[key]) if key=='status' else item[key]
                            if item['status'] in {'ok','recovered'} and not verified_save(item):
                                if key=='save':value='사이트에서 다시 확인'
                                elif key=='status':value='이전 버전 코드 · 재확인'
                            self.table.setItem(i,j,QTableWidgetItem(value))
                elif kind=='fatal':QMessageBox.critical(self,'프로그램 오류',p['text'])
        except queue.Empty:pass

    def closeEvent(self,event):
        if self.allow_close:event.accept();return
        event.ignore()
        if self.shutdown_started:return
        self.shutdown_started=True
        self.closing.set();self.timer.stop()
        try:self.persist()
        except OSError as exc:self.log('설정 저장 오류: '+str(exc))
        if self.hotkeys:self.hotkeys.cancel.set()
        self.typer.stop()
        if self.watch_cancel:self.watch_cancel.set()
        self.bridge.close();self.browser.stop_loading();self.worker.request_stop()
        self.hide();self.shutdown_deadline=time.monotonic()+2
        def closed():
            self.allow_close=True
            self.close()
            # A hidden window does not reliably emit lastWindowClosed. Always
            # quit explicitly after the persistent browser profile is destroyed.
            if self.quit_on_close:QApplication.instance().quit()
        def finish():
            keyboard_busy=bool(self.typer.thread and self.typer.thread.is_alive())
            hotkey_busy=bool(self.hotkeys and self.hotkeys.thread and self.hotkeys.thread.is_alive())
            if (self.worker.is_alive() or keyboard_busy or hotkey_busy) and time.monotonic()<self.shutdown_deadline:
                QTimer.singleShot(20,finish);return
            self.browser.dispose(closed)
        finish()


def main():
    if sys.platform=='win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('SCRMaps.Helper')
        ctypes.windll.kernel32.CreateMutexW.restype=ctypes.c_void_p
        mutex=ctypes.windll.kernel32.CreateMutexW(None,False,'Local\\SCRMapsHelper_v1')
        if ctypes.windll.kernel32.GetLastError()==183:
            ctypes.windll.user32.MessageBoxW(None,'이미 실행 중인 SCRMaps Helper를 사용해 주세요.','SCRMaps Helper',0x40);return
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app=QApplication(sys.argv);app.setQuitOnLastWindowClosed(False);app.setApplicationName('SCRMaps Helper');app.setWindowIcon(QIcon(str(ROOT/'assets'/'helper.png')))
    if sys.platform=='darwin':
        DATA.mkdir(parents=True,exist_ok=True)
        instance_lock=QLockFile(str(DATA/'instance.lock'));instance_lock.setStaleLockTime(0)
        if not instance_lock.tryLock(0):
            QMessageBox.information(None,'SCRMaps Helper','이미 실행 중인 SCRMaps Helper를 사용해 주세요.');return
    window=Window();window.show();status=app.exec()
    # Destroy Qt while its Python wrappers/runtime are still alive, rather than
    # leaving browser/application teardown to CPython interpreter finalization.
    import shiboken6
    shiboken6.delete(window);shiboken6.delete(app)
    sys.exit(status)
