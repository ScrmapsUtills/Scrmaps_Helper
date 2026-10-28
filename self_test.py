"""Offline frozen-runtime smoke test; never opens a website or a user profile."""
import json
import socket
import time
import traceback
from pathlib import Path
from unittest.mock import patch

def run(output):
    report={'ok':False,'checks':[]}
    try:
        import cv2
        import numpy as np
        from recognition import Reader
        def offline(*_args, **_kwargs):
            raise OSError('Network access is prohibited during the offline self-test')
        with patch.object(socket.socket,'connect',offline), patch.object(socket,'create_connection',offline):
            reader=Reader()
            sample=np.full((140,760,3),255,dtype=np.uint8)
            cv2.putText(sample,'ABCDE2345',(25,100),cv2.FONT_HERSHEY_DUPLEX,2.8,(0,0,0),3,cv2.LINE_AA)
            result,_=reader.engine(sample,use_det=False,use_cls=False,use_rec=True)
            if not result or not any(str(row[0]).replace(' ','').upper()=='ABCDE2345' for row in result):
                raise RuntimeError('Bundled OCR did not read the offline sample: '+repr(result))
            report['checks'].append('OCR model initialization and recognition without network')
            detailed=reader.observe(sample)
            if detailed.code!='ABCDE2345' or len(detailed.chars)!=9:
                raise RuntimeError('Bundled recognizer did not retain character confidence: '+repr(detailed))
            report['checks'].append('Pinned OCR character-confidence metadata for AUTH verification')
        from PySide6.QtCore import Qt,QUrl,QCoreApplication,QEvent
        from PySide6.QtWidgets import QApplication
        from PySide6.QtWebEngineCore import QWebEngineProfile,QWebEnginePage
        from PySide6.QtWebEngineWidgets import QWebEngineView
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
        app=QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        profile=QWebEngineProfile()
        view=QWebEngineView();view.setPage(QWebEnginePage(profile,view));loaded=[];result=[]
        view.loadFinished.connect(loaded.append)
        view.setHtml('<!doctype html><meta charset="utf-8"><title>Offline helper test</title><p id="ok">bundled</p><section><h3>내 세이브 코드</h3><input readonly value="9G5C4BA5R"></section>',QUrl('about:blank'))
        deadline=time.monotonic()+20
        while not loaded and time.monotonic()<deadline:
            app.processEvents();time.sleep(.01)
        if loaded!=[True]:raise RuntimeError('Bundled WebEngine did not load an offline page')
        view.page().runJavaScript("document.querySelector('#ok').textContent",result.append)
        deadline=time.monotonic()+5
        while not result and time.monotonic()<deadline:
            app.processEvents();time.sleep(.01)
        if result!=['bundled']:raise RuntimeError('Bundled WebEngine JavaScript failed')
        from web_gateway import RESULT_JS
        codes=[];view.page().runJavaScript('JSON.stringify(('+RESULT_JS+')())',codes.append)
        deadline=time.monotonic()+5
        while not codes and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
        if len(codes)!=1 or json.loads(codes[0])!=['9G5C4BA5R']:raise RuntimeError('Bundled save-result reader failed: '+repr(codes))
        report['checks'].append('Save code extraction from a readonly result field')
        view.close();view.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        profile.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        report['checks'].append('Bundled Qt WebEngine subprocess, resources and JavaScript')
        report['ok']=True
    except Exception:
        report['error']=traceback.format_exc()
    path=Path(output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if report['ok'] else 1
