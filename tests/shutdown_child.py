"""Real application entry-point fixture; exits only through the window's X path."""
import sys,time
from pathlib import Path
from PySide6.QtCore import QTimer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import desktop

data,base,mode=Path(sys.argv[1]),sys.argv[2],sys.argv[3]
OriginalWindow=desktop.Window
class ClosingWindow(OriginalWindow):
    def __init__(self):
        super().__init__(data=data,base=base)
        self.test_started=time.monotonic();self.test_submitted=False
        self.test_timer=QTimer(self);self.test_timer.timeout.connect(self.tick);self.test_timer.start(20)
        if mode=='instant':
            self.test_timer.stop();print('CLOSE_REQUESTED',flush=True);self.close();self.close()
    def tick(self):
        if self.closing.is_set():return
        ready=self.browser.login_state is True
        if mode!='idle' and ready and not self.test_submitted:
            self.test_submitted=True
            self.command('submit',{'auth':'ABCDE2345','cfg':{'project':mode,'nickname':'ShutdownPlayer','auto':True}})
        if ((mode=='idle' and ready) or
            (mode=='navigation' and self.browser.nav_call is not None) or
            (mode=='post' and (data/'post-received').exists())):
            self.test_timer.stop()
            print('CLOSE_REQUESTED',flush=True)
            self.close()
desktop.Window=ClosingWindow
desktop.DATA=data
desktop.fetch_maps=lambda:[]
desktop.main()
