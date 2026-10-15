"""Build-only trimming based on Qt Python references and Windows PE imports.

Required Windows system DLLs remain supplied by Windows. All local Qt DLLs
in the import closure are retained. No inference model is removed or changed.
"""
from __future__ import annotations
import json
from pathlib import Path
import re
import shutil

QT_SEEDS={'QtCore','QtGui','QtWidgets','QtNetwork','QtWebEngineCore','QtWebEngineWidgets','QtWebChannel'}
PLUGIN_DIRS={'platforms','imageformats','iconengines','styles','tls','networkinformation','printsupport'}

def qt_plan(qt):
    import pefile
    qt=Path(qt)
    modules=set(QT_SEEDS);todo=list(modules)
    while todo:
        name=todo.pop();path=qt/(name+'.pyd')
        if not path.is_file():raise RuntimeError('Missing Qt Python module: '+name)
        for dependency in set(s.decode('ascii') for s in re.findall(rb'PySide6\.(Qt[A-Za-z0-9]+)',path.read_bytes())):
            if dependency not in modules:modules.add(dependency);todo.append(dependency)
    keep={qt/(name+'.pyd') for name in modules}
    keep.add(qt/'QtWebEngineProcess.exe')
    keep.add(qt/'opengl32sw.dll')  # Keep software graphics fallback for older PCs.
    for directory in PLUGIN_DIRS:
        keep.update((qt/'plugins'/directory).glob('*.dll'))
    lookup={p.name.lower():p for p in qt.rglob('*.dll')}
    # Root Qt libraries win over plugins with a coincidental duplicate basename.
    lookup.update({p.name.lower():p for p in qt.glob('*.dll')})
    visited=set();todo=list(keep)
    while todo:
        path=todo.pop()
        if path in visited:continue
        if not path.is_file():raise RuntimeError('Missing Qt binary: '+str(path))
        visited.add(path)
        pe=pefile.PE(str(path),fast_load=True)
        pe.parse_data_directories(directories=[1,13])
        for entry in list(getattr(pe,'DIRECTORY_ENTRY_IMPORT',[]))+list(getattr(pe,'DIRECTORY_ENTRY_DELAY_IMPORT',[])):
            dependency=lookup.get(entry.dll.decode('ascii').lower())
            if dependency and dependency not in keep:keep.add(dependency);todo.append(dependency)
        pe.close()
    return modules,keep

def trim_windows(runtime):
    runtime=Path(runtime);site=runtime/'Lib'/'site-packages';qt=site/'PySide6'
    modules,keep=qt_plan(qt);removed=[]
    def remove(path):
        if not path.exists():return
        paths=[path] if path.is_file() else sorted(p for p in path.rglob('*') if p.is_file())
        for p in paths:removed.append({'path':p.relative_to(runtime).as_posix(),'bytes':p.stat().st_size})
        if path.is_dir():shutil.rmtree(path)
        else:path.unlink()
    for p in list(qt.rglob('*')):
        if not p.is_file():continue
        relative=p.relative_to(qt);parts=relative.parts
        if p.suffix.lower() in {'.pyd','.dll','.exe'}:
            if p not in keep:remove(p)
        elif parts[0] in {'qml','include','metatypes','typesystems','glue','scripts','doc','QtAsyncio'}:
            remove(p)
        elif p.suffix.lower() in {'.pyi','.lib','.pdb'}:
            remove(p)
        elif parts[0]=='resources' and '.debug.' in p.name:
            remove(p)
        elif parts[0]=='translations':
            if p.suffix=='.pak' and p.stem not in {'ko','en-US','en-GB'}:remove(p)
            elif p.suffix=='.qm' and not (p.stem.endswith('_ko') or p.stem.endswith('_en')):remove(p)
    for path in ('sympy','mpmath','cv2/data','numpy/f2py','numpy/_pyinstaller','numpy/doc',
                 'onnxruntime/tools','onnxruntime/transformers','onnxruntime/quantization',
                 'onnxruntime/datasets','onnxruntime/backend','onnxruntime/capi/onnxruntime.dll',
                 'cv2/opencv_videoio_ffmpeg4120_64.dll'):
        remove(site/path)
    for p in list(site.rglob('*')):
        if p.is_dir() and p.name in {'tests','test','__pycache__'}:remove(p)
        elif p.is_file() and p.suffix.lower() in {'.pyi','.pdb','.lib','.h','.hpp'}:remove(p)
    # Empty directories are irrelevant to imports and may be dropped.
    for p in sorted((p for p in site.rglob('*') if p.is_dir()),key=lambda x:len(x.parts),reverse=True):
        if not any(p.iterdir()):p.rmdir()
    report={'bytes_removed':sum(x['bytes'] for x in removed),
            'qt_python_modules':sorted(modules),
            'qt_binaries':[p.relative_to(qt).as_posix() for p in sorted(keep)],
            'removed':removed}
    (runtime.parent/'runtime-trim.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report
