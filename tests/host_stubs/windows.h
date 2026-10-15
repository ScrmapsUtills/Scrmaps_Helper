#ifndef HOST_TEST_WINDOWS_H
#define HOST_TEST_WINDOWS_H
#include <stddef.h>
#include <wchar.h>
#define WINAPI
#define __cdecl
#define _snwprintf swprintf
typedef void *HINSTANCE;
typedef void *HMODULE;
typedef wchar_t *PWSTR;
typedef unsigned long DWORD;
typedef size_t SIZE_T;
typedef void (*FARPROC)(void);
#define INVALID_FILE_ATTRIBUTES ((DWORD)-1)
#define LOAD_LIBRARY_SEARCH_DEFAULT_DIRS 0x1000
#define LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR 0x100
#define MB_ICONERROR 0x10
#define HEAP_ZERO_MEMORY 8
DWORD GetModuleFileNameW(void *,wchar_t *,DWORD);
DWORD GetFileAttributesW(const wchar_t *);
int MessageBoxW(void *,const wchar_t *,const wchar_t *,unsigned);
int SetDefaultDllDirectories(DWORD);
void *AddDllDirectory(const wchar_t *);
int SetCurrentDirectoryW(const wchar_t *);
HMODULE LoadLibraryExW(const wchar_t *,void *,DWORD);
FARPROC GetProcAddress(HMODULE,const char *);
wchar_t *GetCommandLineW(void);
void *GetProcessHeap(void);
void *HeapAlloc(void *,DWORD,SIZE_T);
int HeapFree(void *,DWORD,void *);
void *LocalFree(void *);
#endif
