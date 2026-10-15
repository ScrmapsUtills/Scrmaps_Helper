/* Portable fake Win32 boundary for the real launcher source. No game input. */
#include "windows.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static const char *scenario;
static int messages,called;
static const wchar_t *root=L"C:\\Users\\테스트 폴더\\Programs\\SCRMapsHelper";
static int is(const char *value){return !strcmp(scenario,value);}
DWORD GetModuleFileNameW(void *m,wchar_t *out,DWORD count){
    (void)m;assert(count==32768);swprintf(out,count,L"%ls\\SCRMapsHelper.exe",root);
    return is("truncated")?count:(DWORD)wcslen(out);
}
DWORD GetFileAttributesW(const wchar_t *path){
    if((is("missing-dll")&&wcsstr(path,L"python312.dll")) ||
       (is("missing-pth")&&wcsstr(path,L"python312._pth")) ||
       (is("missing-script")&&wcsstr(path,L"app.py")))return INVALID_FILE_ATTRIBUTES;
    return 0;
}
int MessageBoxW(void *w,const wchar_t *body,const wchar_t *title,unsigned flags){
    (void)w;(void)body;assert(!wcscmp(title,L"SCRMaps Helper"));assert(flags==MB_ICONERROR);messages++;return 1;
}
int SetDefaultDllDirectories(DWORD flags){assert(flags==0x1000);return !is("directories-fail");}
void *AddDllDirectory(const wchar_t *path){
    wchar_t expected[32768];swprintf(expected,32768,L"%ls\\runtime",root);assert(!wcscmp(path,expected));return (void *)1;
}
int SetCurrentDirectoryW(const wchar_t *path){assert(!wcscmp(path,root));return 1;}
HMODULE LoadLibraryExW(const wchar_t *path,void *file,DWORD flags){
    wchar_t expected[32768];swprintf(expected,32768,L"%ls\\runtime\\python312.dll",root);
    assert(!wcscmp(path,expected));assert(!file);assert(flags==0x1100);return is("load-fail")?NULL:(void *)1;
}
static int fake_main(int count,wchar_t **args){
    called++;assert(!wcscmp(args[1],L"-B"));
    wchar_t expected[32768];swprintf(expected,32768,L"%ls\\app\\app.py",root);assert(!wcscmp(args[2],expected));
    if(is("self-test")){
        assert(count==5);assert(!wcscmp(args[3],L"--self-test"));
        assert(!wcscmp(args[4],L"C:\\경로 공백\\report.json"));
    }else assert(count==3);
    assert(args[count]==NULL);
    return is("main-error")?7:0;
}
FARPROC GetProcAddress(HMODULE module,const char *name){
    assert(module==(void *)1);assert(!strcmp(name,"Py_Main"));
    if(is("export-fail"))return NULL;
    int (*typed)(int,wchar_t **)=fake_main;FARPROC raw=NULL;
    _Static_assert(sizeof(raw)==sizeof(typed),"Pointer size");memcpy(&raw,&typed,sizeof(raw));return raw;
}
wchar_t *GetCommandLineW(void){return L"fixture";}
wchar_t **CommandLineToArgvW(const wchar_t *line,int *count){
    (void)line;if(is("argv-fail"))return NULL;
    *count=is("self-test")?3:1;
    wchar_t **args=calloc((size_t)*count+1,sizeof(*args));
    args[0]=L"SCRMapsHelper.exe";
    if(*count==3){args[1]=L"--self-test";args[2]=L"C:\\경로 공백\\report.json";}
    return args;
}
void *GetProcessHeap(void){return (void *)1;}
void *HeapAlloc(void *heap,DWORD flags,SIZE_T size){assert(heap==(void *)1);assert(flags==8);return is("allocation-fail")?NULL:calloc(1,size);}
int HeapFree(void *heap,DWORD flags,void *memory){(void)heap;(void)flags;free(memory);return 1;}
void *LocalFree(void *memory){free(memory);return NULL;}
int wWinMain(HINSTANCE,HINSTANCE,PWSTR,int);
int main(int count,char **args){
    assert(count==2);scenario=args[1];
    int result=wWinMain(NULL,NULL,is("self-test")?L"--self-test report.json":L"",0);
    if(is("ok")||is("self-test")){assert(result==0);assert(called==1);assert(messages==0);}
    else if(is("main-error")){assert(result==7);assert(called==1);assert(messages==1);}
    else {assert(result==1);assert(called==0);}
    return 0;
}
