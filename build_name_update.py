"""Build a small process-name update for the installed offline 1.4.2 layout.

Changes only known app files; reuses all existing offline runtime dependencies.
"""
from __future__ import annotations
import argparse
import copy
import json
import os
from pathlib import Path
import shutil
from build_offline import ROOT,VERSION,digest,run,sources_zip
from release_files import LEGACY_DOCS

FILES=('SCRMapsHelper.exe','app/desktop.py','app/browser_panel.py','app/embedded_gateway.py',
       'app/worker.py','app/core.py','app/recognition.py','app/web_gateway.py','app/self_test.py','SCRMapsHelper_Source.zip','.scrmaps-payload','payload-manifest.json')
REMOVED_FILES=LEGACY_DOCS

def updated_manifest(original,patch):
    if original.get('version')!='1.4.2':raise ValueError('Use the verified offline 1.4.2 base payload')
    result=copy.deepcopy(original);result['version']=VERSION
    result['files']=[x for x in result['files'] if x['path'] not in REMOVED_FILES]
    result['launcher']='in-process Py_Main host; no pythonw.exe child'
    entries={x['path']:x for x in result['files']}
    for name in FILES:
        if name=='payload-manifest.json':continue
        if name not in entries:raise ValueError('Patch cannot introduce an untracked file: '+name)
        path=patch/name
        entries[name].update(bytes=path.stat().st_size,sha256=digest(path))
    return result

def install_commands():
    lines=[]
    for name in FILES:
        path=name.replace('/','\\');parent=str(Path(name).parent).replace('/','\\')
        destination='$INSTDIR'+('\\'+parent if parent!='.' else '')
        lines.extend([
            'ClearErrors',
            'Rename "$INSTDIR\\'+path+'" "$INSTDIR\\'+path+'.scrmaps-v147-backup"',
            'IfErrors rollback',
            'CopyFiles /SILENT "$PLUGINSDIR\\new\\'+path+'" "'+destination+'"',
            'IfErrors rollback'])
    for name in REMOVED_FILES:
        path=name.replace('/','\\')
        lines.extend(['${If} ${FileExists} "$INSTDIR\\'+path+'"',' ClearErrors',
                      ' Rename "$INSTDIR\\'+path+'" "$INSTDIR\\'+path+'.scrmaps-v147-backup"',
                      ' IfErrors rollback','${EndIf}'])
    return '\n'.join(lines)

def rollback_commands():
    lines=[]
    for name in reversed(FILES+REMOVED_FILES):
        path=name.replace('/','\\');backup='$INSTDIR\\'+path+'.scrmaps-v147-backup'
        lines.extend(['${If} ${FileExists} "'+backup+'"',
                      ' ClearErrors',' Delete "$INSTDIR\\'+path+'"',' ClearErrors',
                      ' Rename "'+backup+'" "$INSTDIR\\'+path+'"',
                      ' ${If} ${Errors}','  StrCpy $RollbackFailed 1',' ${EndIf}','${EndIf}'])
    return '\n'.join(lines)

def make_script(patch,output):
    template=(ROOT/'process_name_update.nsi').read_text(encoding='utf-8')
    extract=[];checks=[];cleanup=[]
    for name in FILES:
        path=name.replace('/','\\');parent=str(Path(name).parent).replace('/','\\')
        target='$PLUGINSDIR\\new'+('\\'+parent if parent!='.' else '')
        extract.extend(['SetOutPath "'+target+'"','File "'+str((patch/name).resolve()).replace('$','$$')+'"'])
        checks.extend([
            '${IfNot} ${FileExists} "$INSTDIR\\'+path+'"',
            ' MessageBox MB_OK|MB_ICONSTOP "기존 설치 파일이 누락됐습니다. 1.4.2 Setup으로 복구한 뒤 다시 실행하세요."',
            ' Abort','${EndIf}'])
    for name in FILES+REMOVED_FILES:
        path=name.replace('/','\\')
        checks.extend(['${If} ${FileExists} "$INSTDIR\\'+path+'.scrmaps-v147-backup"',
            ' MessageBox MB_OK|MB_ICONSTOP "이전 업데이트 백업이 남아 있습니다. 설치 폴더의 백업을 확인한 뒤 복구하세요."',
            ' Abort','${EndIf}'])
        cleanup.append('Delete "$INSTDIR\\'+path+'.scrmaps-v147-backup"')
    return (template.replace('@OUTPUT@',str(output.resolve()).replace('$','$$'))
            .replace('@CHECKS@','\n'.join(checks)).replace('@EXTRACT@','\n'.join(extract))
            .replace('@INSTALL@',install_commands()).replace('@CLEANUP@','\n'.join(cleanup))
            .replace('@ROLLBACK@',rollback_commands()))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-payload',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--tool-dir',type=Path,required=True)
    parser.add_argument('--nsis-dir',type=Path,required=True)
    args=parser.parse_args()
    base=args.base_payload.resolve();work=args.work.resolve();work.mkdir(parents=True,exist_ok=True)
    patch=work/'patch';patch.mkdir(exist_ok=True);(patch/'app').mkdir(exist_ok=True)
    original=json.loads((base/'payload-manifest.json').read_text(encoding='utf-8'))
    if original['version']!='1.4.2':raise ValueError('Expected verified 1.4.2 base')
    lookup={x['path']:x for x in original['files']}
    for name in FILES:
        if name=='payload-manifest.json':continue
        if digest(base/name)!=lookup[name]['sha256']:raise ValueError('Base payload changed: '+name)
    env=os.environ.copy();tools=args.tool_dir.resolve();env['PATH']=str(tools)+os.pathsep+env.get('PATH','')
    resource=work/'host-resource.o'
    run([tools/'x86_64-w64-mingw32-windres','-I',ROOT,'-i',ROOT/'offline_launcher.rc','-O','coff','-o',resource],env=env)
    run([tools/'x86_64-w64-mingw32-gcc-posix','-std=c11','-Wall','-Wextra','-Werror','-O2',
         '-municode','-mwindows','-static','-static-libgcc','-finput-charset=UTF-8',
         ROOT/'offline_launcher.c',resource,'-o',patch/'SCRMapsHelper.exe','-luser32','-lshell32'],env=env)
    for name in ('desktop.py','browser_panel.py','embedded_gateway.py','worker.py','core.py','recognition.py','web_gateway.py','self_test.py'):
        shutil.copy2(ROOT/name,patch/'app'/name)
    (patch/'.scrmaps-payload').write_text(VERSION,encoding='ascii')
    sources_zip(patch/'SCRMapsHelper_Source.zip')
    manifest=updated_manifest(original,patch)
    (patch/'payload-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    script=ROOT/'generated_name_update.nsi';script.write_text(make_script(patch,args.output),encoding='utf-8')
    env['NSISDIR']=str(args.nsis_dir.resolve());args.output.parent.mkdir(parents=True,exist_ok=True)
    run([tools/'makensis','-V3',script],env=env)
    args.output.with_suffix('.sha256.txt').write_text(digest(args.output)+'  '+args.output.name+'\n',encoding='ascii')
    print('Created update:',args.output,args.output.stat().st_size,'bytes')

if __name__=='__main__':main()
