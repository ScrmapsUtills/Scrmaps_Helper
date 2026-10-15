from pathlib import Path
import os,sys
ROOT=Path(__file__).resolve().parent
def data_folder(platform=None,home=None,environ=None):
    platform=platform or sys.platform;home=Path(home or Path.home());environ=os.environ if environ is None else environ
    if platform=='darwin':return home/'Library'/'Application Support'/'SCRMapsHelper'
    if platform=='win32':return Path(environ.get('LOCALAPPDATA',str(home/'AppData'/'Local')))/'SCRMapsHelper'
    return Path(environ.get('XDG_DATA_HOME',str(home/'.local'/'share')))/'SCRMapsHelper'

DATA=data_folder()

def default_folder():
    homes = [Path.home() / "Documents", Path.home() / "OneDrive" / "Documents"]
    if sys.platform=='darwin':homes.insert(0,Path.home()/'Library'/'Application Support'/'Blizzard')
    if sys.platform == "win32":
        try:
            import ctypes
            out = ctypes.create_unicode_buffer(32768)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, out) == 0:
                homes.insert(0, Path(out.value))
        except Exception:
            pass
    for parent in homes:
        path = parent / "StarCraft" / "Screenshots"
        if path.is_dir():
            return str(path)
    return ""

