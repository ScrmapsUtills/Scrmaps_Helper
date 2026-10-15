"""Build on Windows x64 with Python 3.12: python build_windows.py [--layout onedir]."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parent
BUILD_TOOLS=['pyinstaller==6.22.3','pyinstaller-hooks-contrib==2026.8']

def run(args, **kwargs):
    print('+',subprocess.list2cmdline([str(a) for a in args]),flush=True)
    subprocess.run([str(a) for a in args],check=True,cwd=ROOT,**kwargs)

def prepare_notices(folder):
    folder.mkdir(parents=True,exist_ok=True)
    shutil.copy2(ROOT/'THIRD_PARTY.md',folder/'THIRD_PARTY.md')
    for dist in metadata.distributions():
        name=dist.metadata.get('Name','unknown')
        if name.lower() in {'pip','setuptools','pyinstaller','pyinstaller-hooks-contrib','altgraph','pefile','pywin32-ctypes'}:
            continue
        for relative in dist.files or []:
            text=str(relative).lower()
            if any(word in text for word in ('license','licence','copying','notice','copyright')):
                source=Path(dist.locate_file(relative))
                if not source.is_file():continue
                # Use only safe relative names; wheel paths can include ../Scripts.
                pieces=[p for p in Path(str(relative)).parts if p not in {'..','.','/','\\'}]
                target=folder/name/Path(*pieces)
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    for source in (Path(sys.base_prefix)/'LICENSE.txt',Path(sys.base_prefix)/'LICENSE'):
        if source.is_file():shutil.copy2(source,folder/'Python-LICENSE.txt');break

def source_archive(destination):
    """Ship editable app/build sources; never include sessions or private screenshots."""
    from build_offline import sources_zip
    sources_zip(destination,root=ROOT)

def options(python,layout,release,work,notices,sources):
    return [python,'-m','PyInstaller','--noconfirm','--clean','--'+layout,'--windowed',
        '--noupx','--name','SCRMapsHelper','--distpath',release,'--workpath',work/'pyinstaller',
        '--specpath',work,'--paths',ROOT,
        '--hidden-import','self_test',
        '--collect-all','rapidocr_onnxruntime','--collect-all','onnxruntime',
        '--recursive-copy-metadata','rapidocr_onnxruntime',
        '--copy-metadata','PySide6','--copy-metadata','PySide6_Addons',
        '--copy-metadata','PySide6_Essentials','--copy-metadata','shiboken6',
        '--collect-data','PySide6',
        '--exclude-module','playwright','--exclude-module','tkinter',
        '--add-data',str(notices)+os.pathsep+'THIRD_PARTY_NOTICES',
        '--add-data',str(sources)+os.pathsep+'.',ROOT/'app.py']

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--layout',choices=['onefile','onedir'],default='onefile')
    parser.add_argument('--inside',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    if sys.platform!='win32' or sys.maxsize<=2**32 or sys.version_info[:2]!=(3,12):
        raise SystemExit('Build requires Windows x64 and Python 3.12 x64. Users of the resulting EXE do not need Python.')
    work=ROOT/'build_windows';work.mkdir(exist_ok=True)
    python=work/'venv'/'Scripts'/'python.exe'
    if not args.inside:
        if not python.is_file():run([sys.executable,'-m','venv',work/'venv'])
        run([python,'-m','pip','install','--disable-pip-version-check','--only-binary=:all:',
             '-r',ROOT/'requirements.txt',*BUILD_TOOLS])
        run([python,__file__,'--inside','--layout',args.layout]);return
    import rapidocr_onnxruntime
    package=Path(rapidocr_onnxruntime.__file__).parent
    required=['config.yaml','models/ch_PP-OCRv4_det_infer.onnx',
              'models/ch_ppocr_mobile_v2.0_cls_infer.onnx','models/ch_PP-OCRv4_rec_infer.onnx']
    for filename in required:
        if not (package/filename).is_file():raise RuntimeError('Missing bundled OCR resource: '+filename)
    run([sys.executable,ROOT/'app.py','--self-test',work/'source-smoke.json'],timeout=120)
    notices=work/'notices';prepare_notices(notices)
    sources=work/'SCRMapsHelper_Source.zip';source_archive(sources)
    release=ROOT/'release'/args.layout;release.mkdir(parents=True,exist_ok=True)
    run(options(sys.executable,args.layout,release,work,notices,sources))
    exe=release/'SCRMapsHelper.exe' if args.layout=='onefile' else release/'SCRMapsHelper'/'SCRMapsHelper.exe'
    if not exe.is_file():raise RuntimeError('Expected EXE was not created')
    report=release/'offline-smoke.json'
    run([exe,'--self-test',report],timeout=180)
    if not json.loads(report.read_text(encoding='utf-8')).get('ok'):
        raise RuntimeError('Packaged offline smoke test failed. Do not distribute this build.')
    shutil.copytree(notices,release/'THIRD_PARTY_NOTICES',dirs_exist_ok=True)
    shutil.copy2(sources,release/sources.name)
    run([sys.executable,'-m','pip','freeze','--all'],stdout=(release/'build-environment.txt').open('w',encoding='utf-8'))
    digest=hashlib.sha256(exe.read_bytes()).hexdigest()
    (release/'SHA256SUMS.txt').write_text(digest+'  '+str(exe.relative_to(release))+'\n',encoding='ascii')
    print('\nCreated:',exe,'\nOffline OCR/browser smoke test passed.\nWindows keyboard/game interaction, account login and antivirus reputation still require release testing.')

if __name__=='__main__':main()
