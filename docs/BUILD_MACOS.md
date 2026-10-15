# Mac 설치 파일

일반 사용자는 소스를 빌드하지 않습니다. GitHub의 Mac 서버가 독립 실행 앱과 DMG를 만듭니다.

- Apple Silicon: `macos-15` 서버 / arm64 앱.
- Intel: `macos-15-intel` 서버 / x86_64 앱.
- Python 3.12와 고정된 OCR·Qt 의존성은 빌드 서버에 설치하고 앱 안에 포함합니다.
- 원본과 완성 앱의 오프라인 OCR·브라우저 자체 검사, 앱 서명 구조 검사가 통과해야 DMG를 만듭니다.
- DMG에는 앱과 Applications 바로가기가 있습니다. 개발 설명용 TXT를 넣지 않습니다.
- 생성된 설치본·검사 결과·해시는 Actions의 `installer-macOS-*`에 보관합니다.
- 태그 빌드가 모두 성공하면 초안 Release에도 첨부합니다.

현재 원격 Mac 빌드를 실행하지 않았으므로 이 소스만으로 Mac 설치 완료·게임 동작 검증을
주장하지 않습니다. Mac 최소 OS는 의존성과 빌드 서버의 최소 버전 영향을 받으며 실기 검증이 필요합니다.

실행 사용자는 키 입력 권한을 허용하고 필요한 경우 Fn+F8/F9를 사용합니다.
기록은 `~/Library/Application Support/SCRMapsHelper`에 보관합니다.
서명 인증서·Apple 공증을 적용한 상태는 각 빌드의 `release-status-macOS-*.json`에서 구분합니다.
