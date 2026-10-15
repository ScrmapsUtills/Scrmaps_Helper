#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#include <string.h>
#include <wchar.h>

typedef int (__cdecl *python_main_fn)(int, wchar_t **);

/* Run CPython inside this branded process. Never start python[w].exe.
 * python312._pth beside the DLL pins the app-local import paths. */
int WINAPI wWinMain(HINSTANCE instance,HINSTANCE previous,PWSTR args,int show) {
    (void)instance;(void)previous;(void)show;
    wchar_t executable[32768],root[32768],runtime[32768],library[32768],script[32768],pth[32768];
    DWORD length=GetModuleFileNameW(NULL,executable,32768);
    if(!length||length>=32768)return 1;
    wcscpy(root,executable);
    wchar_t *slash=wcsrchr(root,L'\\');if(!slash)return 1;*slash=0;
    if(_snwprintf(runtime,32768,L"%ls\\runtime",root)<0 ||
       _snwprintf(library,32768,L"%ls\\python312.dll",runtime)<0 ||
       _snwprintf(pth,32768,L"%ls\\python312._pth",runtime)<0 ||
       _snwprintf(script,32768,L"%ls\\app\\app.py",root)<0)return 1;
    if(GetFileAttributesW(library)==INVALID_FILE_ATTRIBUTES ||
       GetFileAttributesW(pth)==INVALID_FILE_ATTRIBUTES ||
       GetFileAttributesW(script)==INVALID_FILE_ATTRIBUTES){
        MessageBoxW(NULL,L"프로그램 파일이 누락됐습니다.\nSCRMaps Helper Setup을 다시 실행해 설치를 복구해 주세요.",L"SCRMaps Helper",MB_ICONERROR);return 1;
    }
    if(!SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_DEFAULT_DIRS) ||
       !AddDllDirectory(runtime) || !SetCurrentDirectoryW(root)){
        MessageBoxW(NULL,L"앱 전용 런타임 폴더를 준비하지 못했습니다.",L"SCRMaps Helper",MB_ICONERROR);return 1;
    }
    HMODULE python=LoadLibraryExW(library,NULL,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
    FARPROC entry=python?GetProcAddress(python,"Py_Main"):NULL;
    if(!entry){
        MessageBoxW(NULL,L"동봉된 Python 런타임을 불러오지 못했습니다.\nSetup을 다시 실행해 설치를 복구해 주세요.",L"SCRMaps Helper",MB_ICONERROR);return 1;
    }
    python_main_fn python_main=NULL;
    _Static_assert(sizeof(python_main)==sizeof(entry),"Windows function pointer size");
    memcpy(&python_main,&entry,sizeof(python_main));
    int count=0;
    wchar_t **original=CommandLineToArgvW(GetCommandLineW(),&count);
    if(!original || count<1)return 1;
    wchar_t **arguments=HeapAlloc(GetProcessHeap(),HEAP_ZERO_MEMORY,((SIZE_T)count+3)*sizeof(*arguments));
    if(!arguments){LocalFree(original);return 1;}
    arguments[0]=executable;arguments[1]=L"-B";arguments[2]=script;
    for(int i=1;i<count;i++)arguments[i+2]=original[i];
    int status=python_main(count+2,arguments);
    HeapFree(GetProcessHeap(),0,arguments);LocalFree(original);
    /* Keep the DLL loaded until process exit, including Qt/static teardown. */
    if(status && (!args || !wcsstr(args,L"--self-test"))){
        MessageBoxW(NULL,L"실행 중 오류가 발생했습니다.\n%LOCALAPPDATA%\\SCRMapsHelper\\crash.log를 확인해 주세요.",L"SCRMaps Helper",MB_ICONERROR);
    }
    return (int)status;
}
