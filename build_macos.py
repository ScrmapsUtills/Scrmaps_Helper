"""Run on a Mac: python3.12 build_macos.py. Produces a bundled .app and DMG.

The build is a release candidate until tested on the target Mac in StarCraft.
The builder downloads dependencies; the resulting app bundles Python/OCR/Qt.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from build_windows import prepare_notices
from core import APP_VERSION as VERSION

ROOT=Path(__file__).resolve().parent

def run(args,**kwargs):
    print('+',subprocess.list2cmdline([str(x) for x in args]),flush=True)
    subprocess.run([str(x) for x in args],check=True,cwd=ROOT,**kwargs)

def spec_text(work,arch,notices,sources):
    # PyInstaller's Qt hooks collect only imported Qt modules, including the
    # WebEngine helper/resources. Do not collect the entire Qt development tree.
    return f'''from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs
datas = collect_data_files('rapidocr_onnxruntime') + [
    ({str(ROOT/'assets')!r}, 'assets'),
    ({str(notices)!r}, 'THIRD_PARTY_NOTICES'),
    ({str(sources)!r}, '.')]
a = Analysis([{str(ROOT/'app.py')!r}], pathex=[{str(ROOT)!r}],
    binaries=collect_dynamic_libs('onnxruntime'), datas=datas,
    hiddenimports=['self_test','mac_keyboard','onnxruntime.capi.onnxruntime_pybind11_state'],
    excludes=['playwright','tkinter','sympy','mpmath','pytest','onnxruntime.tools',
              'onnxruntime.quantization','onnxruntime.transformers'])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='SCRMapsHelper',
    debug=False, strip=False, upx=False, console=False, target_arch={arch!r})
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='SCRMapsHelper')
app = BUNDLE(coll, name='SCRMapsHelper.app', icon={str(work/'helper.icns')!r},
    bundle_identifier='io.scrmapshelper.desktop',
    info_plist={{'CFBundleDisplayName':'SCRMaps Helper',
                'CFBundleShortVersionString':{VERSION!r}, 'CFBundleVersion':{VERSION!r},
                'LSMinimumSystemVersion':'13.0', 'NSHighResolutionCapable':True}})
'''

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inside',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    if sys.platform!='darwin':raise SystemExit('macOS build requires a real Mac build host; this is not a cross compiler.')
    if sys.version_info[:2]!=(3,12):raise SystemExit('Build with Python 3.12, matching the pinned OCR dependencies.')
    arch=platform.machine()
    if arch not in {'arm64','x86_64'}:raise SystemExit('Supported Mac build architectures: arm64 and x86_64')
    if int(platform.mac_ver()[0].split('.')[0])<13:raise SystemExit('Build on macOS 13 or later.')
    work=ROOT/'build_macos'/arch;work.mkdir(parents=True,exist_ok=True)
    python=work/'venv'/'bin'/'python'
    if not args.inside:
        if not python.is_file():run([sys.executable,'-m','venv',work/'venv'])
        run([python,'-m','pip','install','--disable-pip-version-check','--only-binary=:all:',
             '-r',ROOT/'requirements.txt','pyinstaller==6.22.3','pyinstaller-hooks-contrib==2026.8'])
        run([python,__file__,'--inside']);return
    from PIL import Image
    from build_offline import sources_zip,digest
    Image.open(ROOT/'assets'/'helper.png').save(work/'helper.icns',format='ICNS')
    # Fail closed if source or bundled OCR/browser cannot run on this host.
    run([sys.executable,ROOT/'app.py','--self-test',work/'source-smoke.json'],timeout=120)
    notices=work/'notices';prepare_notices(notices)
    sources=work/'SCRMapsHelper_Source.zip';sources_zip(sources)
    spec=work/'SCRMapsHelper.spec';spec.write_text(spec_text(work,arch,notices,sources),encoding='utf-8')
    release=ROOT/'release'/'macos'/arch;release.mkdir(parents=True,exist_ok=True)
    run([sys.executable,'-m','PyInstaller','--noconfirm','--clean',
         '--distpath',release,'--workpath',work/'pyinstaller',spec])
    app=release/'SCRMapsHelper.app'
    exe=app/'Contents'/'MacOS'/'SCRMapsHelper'
    if not exe.is_file():raise RuntimeError('Expected app bundle was not created')
    run(['codesign','--verify','--deep','--strict','--verbose=2',app])
    report=release/f'offline-smoke-macOS-{arch}.json'
    run([exe,'--self-test',report],timeout=180)
    if not json.loads(report.read_text(encoding='utf-8')).get('ok'):
        raise RuntimeError('Bundled offline OCR/browser failed; do not distribute this build.')
    package=work/'dmg-root'
    if package.exists():shutil.rmtree(package)
    package.mkdir();run(['ditto',app,package/app.name])
    (package/'Applications').symlink_to('/Applications',target_is_directory=True)
    dmg=release/f'SCRMapsHelper_{VERSION}_macOS_{arch}.dmg'
    if dmg.exists():dmg.unlink()
    run(['hdiutil','create','-volname','SCRMaps Helper','-srcfolder',package,'-ov','-format','UDZO',dmg])
    (release/f'SHA256SUMS-macOS-{arch}.txt').write_text(digest(dmg)+'  '+dmg.name+'\n',encoding='ascii')
    (release/f'release-status-macOS-{arch}.json').write_text(json.dumps({
        'version':VERSION,'architecture':arch,'offline_ocr_browser_tested':True,
        'macos_keyboard_game_tested':False,'developer_id_signed':False,'notarized':False
    },indent=2),encoding='utf-8')
    print('Created installer:',dmg,'\nGame F8/F9, permissions, login and minimum OS still require Mac testing.')

if __name__=='__main__':main()
