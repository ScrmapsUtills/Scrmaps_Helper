Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"
!include "WinVer.nsh"

!ifndef PAYLOAD
 !error "Pass -DPAYLOAD=path to the prepared offline app folder"
!endif
!ifndef OUTPUT
 !define OUTPUT "SCRMapsHelper_Setup_1.4.5.exe"
!endif
Name "SCRMaps Helper"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\SCRMapsHelper"
InstallDirRegKey HKCU "Software\SCRMapsHelper" "InstallDir"
RequestExecutionLevel user
ManifestDPIAware true
SetCompressor /SOLID lzma
SetCompressorDictSize 32
BrandingText "SCRMaps Helper 1.4.5"
VIProductVersion "1.4.5.0"
VIAddVersionKey /LANG=1042 "ProductName" "SCRMaps Helper"
VIAddVersionKey /LANG=1042 "FileDescription" "SCRMaps Helper 오프라인 설치 프로그램"
VIAddVersionKey /LANG=1042 "FileVersion" "1.4.5"
VIAddVersionKey /LANG=1042 "LegalCopyright" "Component copyrights: see THIRD_PARTY_NOTICES"
Var PreviousInstallDir

!define MUI_ICON "assets/helper.ico"
!define MUI_UNICON "assets/helper.ico"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "SCRMaps Helper 설치"
!define MUI_WELCOMEPAGE_TEXT "스크린샷 인식과 코드 입력을 한 프로그램에서 사용하세요.$\r$\n$\r$\nOCR 모델과 내장 브라우저가 모두 포함되어 있어 설치 중 추가 다운로드가 필요하지 않습니다.$\r$\n$\r$\n웹사이트 로그인과 코드 발급에는 인터넷이 필요합니다."
!define MUI_FINISHPAGE_RUN "$INSTDIR\SCRMapsHelper.exe"
!define MUI_FINISHPAGE_RUN_TEXT "SCRMaps Helper 실행"
!define MUI_FINISHPAGE_RUN_NOTCHECKED
!insertmacro MUI_PAGE_WELCOME
!define MUI_PAGE_CUSTOMFUNCTION_PRE DirectoryPre
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Korean"

!macro RequireClosed prefix
Function ${prefix}RequireClosed
 retry:
 System::Call 'kernel32::OpenMutexW(i 0x100000, i 0, w "Local\SCRMapsHelper_v1") p.r0'
 ${If} $0 != 0
  System::Call 'kernel32::CloseHandle(p r0)'
  MessageBox MB_RETRYCANCEL|MB_ICONINFORMATION "실행 중인 SCRMaps Helper를 종료한 뒤 다시 시도해 주세요." IDRETRY retry
  Abort
 ${EndIf}
FunctionEnd
!macroend
!insertmacro RequireClosed ""
!insertmacro RequireClosed "un."

Function .onInit
 ${IfNot} ${RunningX64}
  MessageBox MB_OK|MB_ICONSTOP "Windows 10/11 64비트가 필요합니다."
  Abort
 ${EndIf}
 ${IfNot} ${AtLeastWin10}
  MessageBox MB_OK|MB_ICONSTOP "Windows 10/11 64비트가 필요합니다."
  Abort
 ${EndIf}
 Call RequireClosed
 SetRegView 64
 SetShellVarContext current
 ReadRegStr $PreviousInstallDir HKCU "Software\SCRMapsHelper" "InstallDir"
 ${If} $PreviousInstallDir != ""
  StrCpy $INSTDIR $PreviousInstallDir
 ${EndIf}
FunctionEnd

Function DirectoryPre
 ${If} $PreviousInstallDir != ""
  ; Updates reuse the existing folder so the previous payload can be removed.
  Abort
 ${EndIf}
FunctionEnd

Function un.onInit
 Call un.RequireClosed
 SetRegView 64
 SetShellVarContext current
FunctionEnd

Section "SCRMaps Helper" Main
 SectionIn RO
 Call RequireClosed
 ${If} $PreviousInstallDir != ""
 ${AndIf} ${FileExists} "$INSTDIR\Uninstall.exe"
 ${AndIf} ${FileExists} "$INSTDIR\.scrmaps-payload"
  ; The previous exact-file uninstaller preserves settings and unknown files.
  ; _?= runs it in place so ExecWait waits for the complete removal.
  ExecWait '$\"$INSTDIR\Uninstall.exe$\" /S _?=$INSTDIR' $0
  ${If} $0 != 0
   MessageBox MB_OK|MB_ICONSTOP "기존 프로그램 정리를 완료하지 못했습니다. Helper를 종료한 뒤 다시 설치해 주세요."
   Abort
  ${EndIf}
 ${EndIf}
 SetOutPath "$INSTDIR"
 !include "install_files.nsh"
 WriteUninstaller "$INSTDIR\Uninstall.exe"
 CreateDirectory "$SMPROGRAMS\SCRMaps Helper"
 CreateShortCut "$SMPROGRAMS\SCRMaps Helper\SCRMaps Helper.lnk" "$INSTDIR\SCRMapsHelper.exe" "" "$INSTDIR\SCRMapsHelper.exe" 0
 CreateShortCut "$SMPROGRAMS\SCRMaps Helper\제거.lnk" "$INSTDIR\Uninstall.exe"
 CreateShortCut "$DESKTOP\SCRMaps Helper.lnk" "$INSTDIR\SCRMapsHelper.exe" "" "$INSTDIR\SCRMapsHelper.exe" 0
 WriteRegStr HKCU "Software\SCRMapsHelper" "InstallDir" "$INSTDIR"
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SCRMapsHelper" "DisplayName" "SCRMaps Helper"
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SCRMapsHelper" "DisplayVersion" "1.4.5"
 SectionGetSize ${Main} $0
 WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SCRMapsHelper" "EstimatedSize" $0
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SCRMapsHelper" "InstallLocation" "$INSTDIR"
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SCRMapsHelper" "DisplayIcon" "$INSTDIR\SCRMapsHelper.exe,0"
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SCRMapsHelper" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SCRMapsHelper" "QuietUninstallString" '$\"$INSTDIR\Uninstall.exe$\" /S'
 WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SCRMapsHelper" "NoModify" 1
 WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SCRMapsHelper" "NoRepair" 1
SectionEnd

Section "Uninstall"
 ; Remove only the installed payload. User settings/history/profile are elsewhere.
 !include "uninstall_files.nsh"
 Delete "$INSTDIR\Uninstall.exe"
 RMDir "$INSTDIR"
 Delete "$DESKTOP\SCRMaps Helper.lnk"
 Delete "$SMPROGRAMS\SCRMaps Helper\SCRMaps Helper.lnk"
 Delete "$SMPROGRAMS\SCRMaps Helper\제거.lnk"
 RMDir "$SMPROGRAMS\SCRMaps Helper"
 DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SCRMapsHelper"
 DeleteRegKey HKCU "Software\SCRMapsHelper"
SectionEnd
