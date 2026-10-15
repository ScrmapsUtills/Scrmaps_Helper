SCRMaps Helper 1.4.5 · 오프라인 Setup 빌드
============================================================
산출물: SCRMapsHelper_Setup_1.4.5.exe
설치 폴더: SCRMapsHelper.exe + app + runtime + 구성요소 고지/소스
런처는 C/Win32, 앱은 기존 Python/Qt입니다. Python을 따로 설치하지 않고
SCRMapsHelper.exe 프로세스가 앱 전용 python312.dll을 직접 로드하고
Py_Main을 호출합니다. 별도 pythonw.exe 자식 프로세스를 생성하지 않습니다.
DLL 옆 python312._pth의 격리 경로와 동봉된 패키지를 사용합니다.
전용 _pth로 앱 경로를 제한하고 사용자 Python 패키지는 사용하지 않습니다.

Linux 빌드 환경
Python 3, MinGW x64 gcc/windres, NSIS 3 Unicode가 필요합니다.
Ubuntu 패키지: gcc-mingw-w64-x86-64, binutils-mingw-w64-x86-64,
mingw-w64-x86-64-dev, nsis.
다운로드는 제작 단계에서만 필요합니다. 사용자 설치/실행에는 없습니다.

1. 공식 Python 3.12.10 x64 embeddable ZIP을 준비합니다.
   https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip
2. requirements.txt의 Windows x64 / CPython 3.12 휠을 준비합니다.
   python -m pip download --only-binary=:all: --platform win_amd64 --python-version 312 --implementation cp --abi cp312 --dest wheels -r requirements.txt
   같은 옵션으로 colorama==0.4.6 및 pyreadline3도 포함합니다.
   cross-platform pip이 Windows 환경 마커를 놓칠 수 있어 별도로 포함합니다.
3. offline-inputs.json의 모든 입력 파일 해시를 맞춥니다. 다른 버전으로
   갱신할 때에는 의존성 호환성과 새 입력 해시를 먼저 검증하세요.
   기존 RapidOCR 1.4.5는 Python <3.13을 요구합니다.
4. 소스 폴더에서 실행:
   python build_offline.py --python-zip python-3.12.10-embed-amd64.zip --wheel-dir wheels --payload stage --output SCRMapsHelper_Setup_1.4.5.exe
   로컬 MinGW/NSIS는 --gcc, --windres, --tool-dir, --makensis,
   --nsis-dir 옵션으로 지정할 수 있습니다.
5. 빌더가 앱 전용 런타임·VC 런타임 DLL·OCR 모델·Qt WebEngine을
   폴더에 풀고 C 런처를 컴파일합니다. 정확한 제거 목록을 생성한 뒤
   NSIS로 하나의 오프라인 설치 파일을 만듭니다.
   pip/PowerShell/Python 설치 프로그램을 사용자 PC에서 실행하지 않습니다.

입력/구성 검증
- offline-inputs.json: 공식 Python ZIP과 배포 휠의 SHA-256
- payload-manifest.json: 설치된 개별 파일의 크기·SHA-256
- SHA256SUMS.txt: 최종 배포 파일의 해시(서명하면 다시 생성)
- 모델 3개/config.yaml, Qt WebEngine 실행 파일/리소스, app-local
  CRT DLL, x64 런처와 아이콘·매니페스트 포함을 확인합니다.
- 설치 파일 아카이브를 풀어 payload-manifest.json과 비교합니다.

Windows에서 최종 확인할 항목
Python/OCR이 설치되지 않은 Windows 10/11 x64 환경에서 인터넷을 끊고
Setup 설치 → 앱 실행 → 사진 인식이 되는지 확인하세요.
설치 폴더에서 다음 명령으로 별도 프로필을 사용하지 않는 자체 검사를 합니다.
  SCRMapsHelper.exe --self-test "%TEMP%\scrmaps-offline.json"
보고서의 ok:true가 성공입니다. 이 검사는 실제 게임 키를 누르지 않습니다.
이후 네트워크 연결 후 공식 로그인, 인증번호 발급, 스타에서 F8/F9,
재실행 로그인 유지, 제거/재설치를 확인하세요.

설치/업데이트/제거는 앱 종료를 요구합니다. 설치와 바로가기는 현재
사용자 범위에 생성하고 시스템 Python/PATH/다른 프로그램 DLL은 변경하지
않습니다. 제거는 생성된 설치 파일 목록만 삭제하고 개인 기록은 남깁니다.
코드 서명/백신·SmartScreen 검사는 별도로 수행해야 합니다.

고지
THIRD_PARTY_NOTICES 및 SCRMapsHelper_Source.zip을 설치 폴더에 포함합니다.
Qt DLL과 앱 소스는 교체·수정 가능한 파일로 설치합니다.
컴포넌트 버전과 라이선스는 THIRD_PARTY.txt 및 동봉된 고지를 확인하세요.

아이콘
imagegen 내장 도구로 단일 앱 아이콘을 생성했습니다.
원본 assets/helper.png, Windows 다중 해상도 assets/helper.ico.
프롬프트: dark navy/cyan save/archive glyph with screenshot scanning corners,
rounded square, no text, transparent outer background, readable small silhouette.

1.4.5 기본 빌드는 slim_runtime.py로 필요한 Qt Python 모듈과 PE DLL
의존성을 따라 남깁니다. 제작 환경에 pefile이 필요합니다(pip install pefile).
Qt WebEngine 런타임 리소스/프로세스 및 소프트웨어 그래픽 대체 DLL은
유지하고 디버그 리소스와 개발 도구는 제외합니다. 진단용 전체 패키지는
--full-runtime으로 생성할 수 있습니다. runtime-trim.json에 제외 목록과
제외 용량을 기록합니다. 예전 크기의 설치 파일로 되돌리지 않도록 확인하세요.
