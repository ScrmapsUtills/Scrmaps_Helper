"""Assemble Windows app-local DLLs and compile the offline NSIS installer.

Build hosts need Python, x64 MinGW (gcc/windres) and NSIS. Windows execution is
not required for assembly. See BUILD_OFFLINE_ko.txt for runtime validation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import zipfile
from core import APP_VERSION as VERSION
from release_files import LEGACY_DOCS,SOURCE_ROOT_FILES

ROOT=Path(__file__).resolve().parent
MODULES=('app.py','desktop.py','browser_panel.py','embedded_gateway.py','worker.py',
         'core.py','paths.py','recognition.py','web_gateway.py','key_sender.py','mac_keyboard.py','theme.py','self_test.py')

def digest(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):result.update(chunk)
    return result.hexdigest()

def safe_extract(archive,destination,wheel=False):
    """Wheel .data/purelib and .data/platlib obey normal installation layout."""
    destination=Path(destination)
    with zipfile.ZipFile(archive) as z:
        if z.testzip():raise RuntimeError('Corrupt archive: '+str(archive))
        for member in z.infolist():
            parts=PurePosixPath(member.filename).parts
            if not parts or member.filename.startswith('/') or any(p in {'..',''} or ':' in p or '\\' in p for p in parts):
                raise ValueError('Unsafe archive member: '+member.filename)
            if wheel and len(parts)>2 and parts[0].endswith('.data'):
                if parts[1] not in {'purelib','platlib','data'}:continue
                parts=parts[2:]
            target=destination.joinpath(*parts)
            if member.is_dir():target.mkdir(parents=True,exist_ok=True);continue
            target.parent.mkdir(parents=True,exist_ok=True)
            with z.open(member) as source,target.open('wb') as output:shutil.copyfileobj(source,output)

def sources_zip(destination,root=None):
    root=Path(root or ROOT)
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(root.rglob('*')):
            relative=p.relative_to(root)
            if not p.is_file() or '__pycache__' in relative.parts:continue
            if len(relative.parts)==1:
                if p.name in SOURCE_ROOT_FILES:z.write(p,relative.as_posix())
            elif relative.parts[0] in {'tests','assets','.github','docs'} and p.suffix.lower() in {
                    '.py','.c','.h','.ps1','.ico','.png','.icns','.md','.yml','.yaml'}:
                z.write(p,relative.as_posix())

def inventory(stage):
    report=stage/'runtime-trim.json'
    omitted=set(LEGACY_DOCS)
    if report.is_file():
        omitted.update('runtime/'+x['path'] for x in json.loads(report.read_text(encoding='utf-8'))['removed'])
    return [{'path':p.relative_to(stage).as_posix(),'bytes':p.stat().st_size,'sha256':digest(p)}
            for p in sorted(stage.rglob('*')) if p.is_file() and p.name!='payload-manifest.json'
            and p.relative_to(stage).as_posix() not in omitted]

def write_manifest(stage):
    manifest={'version':VERSION,'python':'3.12.10','architecture':'Windows x64',
              'files':inventory(stage),'windows_runtime_tested':False}
    (stage/'payload-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    files=[stage/x['path'] for x in manifest['files']]+[stage/'payload-manifest.json']
    install=[];uninstall=[];directories=set();current=None
    for p in sorted(files):
        relative=p.relative_to(stage);parent=relative.parent
        target='$INSTDIR'+('\\'+str(parent).replace('/','\\') if parent!=Path('.') else '')
        if target!=current:install.append('SetOutPath "'+target.replace('$INSTDIR','@INSTDIR@').replace('$','$$').replace('@INSTDIR@','$INSTDIR')+'"');current=target
        install.append('File "/oname='+p.name.replace('$','$$')+'" "'+str(p.resolve()).replace('$','$$')+'"')
        uninstall.append('Delete "$INSTDIR\\'+relative.as_posix().replace('/','\\').replace('$','$$')+'"')
        directories.update(x for x in relative.parents if x!=Path('.'))
    for p in sorted(directories,key=lambda x:(len(x.parts),str(x)),reverse=True):
        uninstall.append('RMDir "$INSTDIR\\'+p.as_posix().replace('/','\\').replace('$','$$')+'"')
    (ROOT/'install_files.nsh').write_text('\n'.join(install)+'\n',encoding='utf-8')
    (ROOT/'uninstall_files.nsh').write_text('\n'.join(uninstall)+'\n',encoding='utf-8')
    return manifest

def prepare(args):
    stage=args.payload.resolve()
    if stage==ROOT or ROOT in stage.parents and stage.name in {'assets','tests'}:
        raise ValueError('Payload must be a dedicated staging directory')
    marker=stage/'.scrmaps-payload'
    if stage.exists() and any(stage.iterdir()):
        if not marker.is_file():raise ValueError('Refusing to replace a nonempty directory without a payload marker')
        shutil.rmtree(stage)
    stage.mkdir(parents=True,exist_ok=True);marker.write_text(VERSION,encoding='ascii')
    runtime=stage/'runtime';site=runtime/'Lib'/'site-packages';site.mkdir(parents=True)
    wheels=sorted(args.wheel_dir.glob('*.whl'))
    if not wheels:raise ValueError('No wheels in --wheel-dir')
    lock_path=ROOT/'offline-inputs.json'
    if lock_path.is_file():
        expected=json.loads(lock_path.read_text(encoding='utf-8'))['files']
        for p in [args.python_zip,*wheels]:
            if p.name not in expected or digest(p)!=expected[p.name]['sha256']:
                raise ValueError('Input hash does not match offline-inputs.json: '+p.name)
    safe_extract(args.python_zip,runtime)
    if not (runtime/'python312.dll').is_file():raise ValueError('Use the official Python 3.12 x64 embeddable ZIP')
    for wheel in wheels:
        if not (wheel.name.endswith('win_amd64.whl') or wheel.name.endswith('none-any.whl')):
            raise ValueError('Only Windows x64 and pure Python wheels are accepted: '+wheel.name)
        if '-cp313-' in wheel.name or '-cp311-cp311-' in wheel.name:raise ValueError('Wrong Python ABI: '+wheel.name)
        print('Unpacking',wheel.name,flush=True);safe_extract(wheel,site,wheel=True)
    (runtime/'python312._pth').write_text('python312.zip\n.\n../app\nLib/site-packages\nimport site\n',encoding='ascii')
    # The CRTs are shipped app-locally, not installed system-wide. Qt's wheel
    # includes the matching redistributable DLLs and notices.
    for source in (site/'PySide6').glob('*.dll'):
        if source.name.lower().startswith(('vcruntime','msvcp','concrt')):shutil.copy2(source,runtime/source.name)
    if not getattr(args,'full_runtime',False):
        from slim_runtime import trim_windows
        report=trim_windows(runtime)
        print('Removed unused runtime files:',round(report['bytes_removed']/1024**2,1),'MiB',flush=True)
    app=stage/'app';app.mkdir()
    for filename in MODULES:shutil.copy2(ROOT/filename,app/filename)
    shutil.copytree(ROOT/'assets',app/'assets')
    notices=stage/'THIRD_PARTY_NOTICES';notices.mkdir()
    shutil.copy2(ROOT/'THIRD_PARTY.md',notices/'THIRD_PARTY.md')
    shutil.copy2(runtime/'LICENSE.txt',notices/'Python-LICENSE.txt')
    for p in sorted(site.rglob('*')):
        if p.is_file() and any(word in p.name.lower() for word in ('license','licence','notice','copying','copyright')):
            target=notices/p.relative_to(site);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    sources_zip(stage/'SCRMapsHelper_Source.zip')
    resources=args.output.parent/'launcher-res.o';resources.parent.mkdir(parents=True,exist_ok=True)
    environment=os.environ.copy()
    if args.tool_dir:environment['PATH']=str(args.tool_dir.resolve())+os.pathsep+environment.get('PATH','')
    run([args.windres,'-I',ROOT,'-i',ROOT/'offline_launcher.rc','-O','coff','-o',resources],env=environment)
    run([args.gcc,'-std=c11','-Wall','-Wextra','-Werror','-O2','-municode','-mwindows',
         '-static','-static-libgcc','-finput-charset=UTF-8',ROOT/'offline_launcher.c',resources,
         '-o',stage/'SCRMapsHelper.exe','-luser32','-lshell32'],env=environment)
    required=[runtime/'pythonw.exe',runtime/'python312.dll',runtime/'msvcp140.dll',
              site/'PySide6'/'QtWebEngineProcess.exe',site/'PySide6'/'Qt6WebEngineCore.dll',
              site/'PySide6'/'resources'/'qtwebengine_resources.pak',
              site/'rapidocr_onnxruntime'/'config.yaml',
              site/'rapidocr_onnxruntime'/'models'/'ch_PP-OCRv4_rec_infer.onnx']
    for p in required:
        if not p.is_file():raise RuntimeError('Missing required offline file: '+str(p))
    write_manifest(stage)
    return stage

def run(command,**kwargs):
    command=[str(x) for x in command];print('+',subprocess.list2cmdline(command),flush=True)
    subprocess.run(command,check=True,cwd=ROOT,**kwargs)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--python-zip',type=Path,required=True);p.add_argument('--wheel-dir',type=Path,required=True)
    p.add_argument('--payload',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--gcc',default='x86_64-w64-mingw32-gcc');p.add_argument('--windres',default='x86_64-w64-mingw32-windres')
    p.add_argument('--makensis',default='makensis');p.add_argument('--nsis-dir',type=Path);p.add_argument('--tool-dir',type=Path)
    p.add_argument('--full-runtime',action='store_true',help='Diagnostic build: retain all vendor tools/modules')
    args=p.parse_args()
    for key in ('python_zip','wheel_dir','payload','output'):setattr(args,key,getattr(args,key).resolve())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    stage=prepare(args)
    env=os.environ.copy()
    if args.nsis_dir:env['NSISDIR']=str(args.nsis_dir.resolve())
    run([args.makensis,'-V3','-DPAYLOAD='+str(stage),'-DOUTPUT='+str(args.output),ROOT/'installer.nsi'],env=env)
    print('Built:',args.output,args.output.stat().st_size,'bytes',digest(args.output),flush=True)
    print('Windows installation, keyboard input and account login still require Windows testing.',flush=True)

if __name__=='__main__':main()
