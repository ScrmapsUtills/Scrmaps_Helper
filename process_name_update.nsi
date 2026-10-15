Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"
!include "WinVer.nsh"
Name "SCRMaps Helper 배포 정리 업데이트"
OutFile "@OUTPUT@"
RequestExecutionLevel user
ManifestDPIAware true
SetCompressor /SOLID lzma
BrandingText "SCRMaps Helper 1.4.5"
VIProductVersion "1.4.5.0"
VIAddVersionKey /LANG=1042 "ProductName" "SCRMaps Helper"
VIAddVersionKey /LANG=1042 "FileDescription" "SCRMaps Helper 배포 파일 정리 업데이트"
VIAddVersionKey /LANG=1042 "FileVersion" "1.4.5"
VIAddVersionKey /LANG=1042 "LegalCopyright" "Component copyrights: see installed notices"
!define MUI_ICON "assets/helper.ico"
!define MUI_WELCOMEPAGE_TITLE "SCRMaps Helper 배포 정리 업데이트"
!define MUI_WELCOMEPAGE_TEXT "설치된 1.4.2~1.4.4에 누적 수정을 적용하고 설명용 TXT를 제거합니다.$\r$\n$\r$\nHelper를 종료한 뒤 진행하세요. OCR이나 브라우저를 다시 내려받지 않습니다."
!define MUI_FINISHPAGE_TITLE "업데이트 완료"
!define MUI_FINISHPAGE_TEXT "바탕화면의 SCRMaps Helper를 다시 실행하세요."
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_LANGUAGE "Korean"
Var AppMutex
Var RollbackFailed

Function .onInit
 ${IfNot} ${RunningX64}
  Abort
 ${EndIf}
 ${IfNot} ${AtLeastWin10}
  Abort
 ${EndIf}
 SetRegView 64
 SetShellVarContext current
 ReadRegStr $INSTDIR HKCU "Software\SCRMapsHelper" "InstallDir"
 ReadRegStr $0 HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SCRMapsHelper" "DisplayVersion"
 ${If} $0 != "1.4.2"
 ${AndIf} $0 != "1.4.3"
 ${AndIf} $0 != "1.4.4"
 ${AndIf} $0 != "1.4.5"
  MessageBox MB_OK|MB_ICONSTOP "SCRMaps Helper 1.4.2 Setup을 먼저 설치한 뒤 실행하세요."
  Abort
 ${EndIf}
 ${IfNot} ${FileExists} "$INSTDIR\runtime\python312.dll"
  MessageBox MB_OK|MB_ICONSTOP "동봉된 런타임이 없습니다. 1.4.2 Setup으로 설치를 복구해 주세요."
  Abort
 ${EndIf}
 ${IfNot} ${FileExists} "$INSTDIR\runtime\python312._pth"
  MessageBox MB_OK|MB_ICONSTOP "런타임 경로 설정이 없습니다. 1.4.2 Setup으로 설치를 복구해 주세요."
  Abort
 ${EndIf}
 retry:
 System::Call 'kernel32::CreateMutexW(p 0, i 0, w "Local\SCRMapsHelper_v1") p.r0 ?e'
 Pop $1
 ${If} $0 == 0
  MessageBox MB_OK|MB_ICONSTOP "프로그램 종료 여부를 확인하지 못했습니다."
  Abort
 ${EndIf}
 ${If} $1 == 183
  System::Call 'kernel32::CloseHandle(p r0)'
  MessageBox MB_RETRYCANCEL|MB_ICONINFORMATION "실행 중인 Helper를 종료한 뒤 다시 시도하세요." IDRETRY retry
  Abort
 ${EndIf}
 StrCpy $AppMutex $0
 ; Holding the app's mutex prevents it from starting during replacement.
FunctionEnd

Function .onGUIEnd
 ${If} $AppMutex != ""
  System::Call 'kernel32::CloseHandle(p $AppMutex)'
 ${EndIf}
FunctionEnd

Section "배포 정리 업데이트"
 @CHECKS@
 InitPluginsDir
 @EXTRACT@
 StrCpy $RollbackFailed 0
 @INSTALL@
 ClearErrors
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SCRMapsHelper" "DisplayVersion" "1.4.5"
 IfErrors rollback
 @CLEANUP@
 Goto done
 rollback:
 @ROLLBACK@
 ${If} $RollbackFailed == 1
  MessageBox MB_OK|MB_ICONSTOP "업데이트 복구를 완료하지 못했습니다. Helper를 종료하고 1.4.2 Setup으로 복구하세요. 설치 폴더의 .scrmaps-v145-backup 파일을 보존해 주세요."
 ${Else}
  MessageBox MB_OK|MB_ICONSTOP "파일을 교체하지 못해 기존 버전으로 되돌렸습니다. Helper를 완전히 종료한 뒤 다시 시도하세요."
 ${EndIf}
 SetErrorLevel 1
 Abort
 done:
SectionEnd
