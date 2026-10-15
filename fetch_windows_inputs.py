"""Fetch the exact public Windows inputs in offline-inputs.json on the CI host."""
import argparse,hashlib,json
from pathlib import Path
import urllib.request

ROOT=Path(__file__).resolve().parent

def file_hash(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(65536),b''):h.update(block)
    return h.hexdigest()

def download(url,path,expected):
    if path.is_file() and path.stat().st_size==expected['bytes'] and file_hash(path)==expected['sha256']:return
    temp=path.with_suffix(path.suffix+'.part');path.parent.mkdir(parents=True,exist_ok=True)
    with urllib.request.urlopen(url,timeout=60) as source,temp.open('wb') as output:
        while block:=source.read(65536):output.write(block)
    if temp.stat().st_size!=expected['bytes'] or file_hash(temp)!=expected['sha256']:
        temp.unlink(missing_ok=True);raise ValueError('Input hash/size mismatch: '+path.name)
    temp.replace(path)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--destination',type=Path,required=True)
    args=parser.parse_args();lock=json.loads((ROOT/'offline-inputs.json').read_text(encoding='utf-8'))
    for name,expected in lock['files'].items():
        if name.endswith('.whl'):
            package,version=name.split('-')[:2]
            with urllib.request.urlopen(f'https://pypi.org/pypi/{package}/{version}/json',timeout=30) as response:
                metadata=json.load(response)
            record=next((x for x in metadata['urls'] if x['filename']==name),None)
            if not record or record['digests']['sha256']!=expected['sha256']:raise ValueError('Unknown pinned wheel: '+name)
            url=record['url'];path=args.destination/'wheels'/name
        elif name=='python-3.12.10-embed-amd64.zip':url=lock['python_url'];path=args.destination/name
        else:raise ValueError('Unsupported locked input: '+name)
        download(url,path,expected);print('Verified',name,flush=True)

if __name__=='__main__':main()
