# 구성요소 고지

앱은 Python/Qt와 앱 전용 OCR 런타임을 사용합니다. Windows 실행 호스트는 C로
작성되어 동봉된 Python DLL을 같은 프로세스에 로드합니다. Mac 앱은 PyInstaller로
묶습니다. 구성요소의 라이선스 원문과 저작권 고지는 설치된 런타임 메타데이터 및
`THIRD_PARTY_NOTICES`에 포함합니다. 이를 배포 시 함께 유지하세요.

| 구성요소 | 라이선스 및 원본 |
| --- | --- |
| Python | PSF License — https://www.python.org/ |
| RapidOCR | Apache-2.0 — https://github.com/RapidAI/RapidOCR |
| ONNX Runtime | MIT — https://github.com/microsoft/onnxruntime |
| OpenCV | Apache-2.0 — https://github.com/opencv/opencv |
| NumPy | BSD-3-Clause — https://numpy.org/ |
| Pillow | HPND 및 동봉 고지 — https://python-pillow.github.io/ |
| PySide6 / Qt | LGPLv3/GPLv3 또는 상용 라이선스 — https://doc.qt.io/qtforpython-6/licenses.html |
| Qt WebEngine / Chromium | 구성요소별 동봉 고지 — https://doc.qt.io/qt-6/qtwebengine-index.html |
| PyInstaller | GPLv2 + bootloader exception — https://pyinstaller.org/en/stable/license.html |
| NSIS | zlib/libpng — https://nsis.sourceforge.io/License |

앱 및 빌드 소스는 `SCRMapsHelper_Source.zip`과 GitHub 저장소에서 제공합니다.
Qt 라이브러리는 동적 링크하며 앱 폴더의 DLL 또는 Mac Framework로 구성됩니다.
사용자는 호환되는 라이브러리로 교체하고 제공된 소스로 다시 빌드할 수 있습니다.
앱 아이콘은 이 프로젝트를 위해 이미지 생성 도구로 제작했습니다.

이 고지는 각 구성요소의 라이선스 원문과 배포 의무를 대체하지 않습니다.
