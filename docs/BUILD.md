# 설치 파일 자동 생성

일반 사용자는 빌드하지 않습니다. GitHub가 Windows와 Mac 설치 파일을 생성합니다.

1. 소스의 내용물과 `.github` 폴더를 저장소 루트에 커밋합니다.
2. `main`/`master` push 또는 Actions의 **Installers → Run workflow**로 시작합니다.
3. Mac arm64와 Intel 작업은 GitHub Mac 서버에서 `.app`과 `.dmg`를 생성합니다.
4. Windows는 고정된 공식 Python ZIP과 Windows 휠을 해시 검사하여 오프라인 Setup을 만듭니다.
5. Windows 서버에서 Setup을 설치하고, 동봉된 OCR·브라우저 자체 검사를 실행합니다.
6. Actions 결과의 `installer-*`를 내려받습니다. Mac DMG 안의 앱을 Applications로 옮겨 실행합니다.
7. 앱 버전과 동일한 `v1.4.7` 태그를 올리면 성공한 결과로 초안 Release를 만듭니다.
   게임·로그인·권한 동작을 확인한 후 Publish합니다.

이 작업 파일은 다른 저장소에 게시하거나 실행한 상태가 아닙니다.
계정 연결과 대상 저장소가 있어야 이 대화에서 원격 실행을 진행할 수 있습니다.

빌드용 파일 다운로드는 GitHub 빌드 서버에서만 수행합니다. 사용자 앱의 최초 실행에서
Python/OCR을 다운로드하지 않습니다. Mac 빌드에는 서명 인증서를 넣지 않았고
PyInstaller의 로컬 ad-hoc 서명을 사용합니다. 배포자 서명·공증은 별도 출시 단계입니다.

설명용 TXT는 설치 폴더에서 제거합니다. 라이선스 고지와 Python 런타임 파일은 유지합니다.
AppData의 세이브·로그인 데이터는 소스에 넣지 않습니다. 소스 내보내기는 명시된 파일만 허용합니다.

상세 내부 빌드 참고: [Windows](BUILD_WINDOWS.md), [Mac](BUILD_MACOS.md).
