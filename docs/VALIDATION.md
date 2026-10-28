SCRMaps Helper 1.4.5 - validation (2026-10-15)

PASS: 64 unit checks: core 7, recognition decisions 11, worker 14,
      keyboard sender/global polling 18, macOS key mapping/cleanup/path 5,
      Windows builder 3, archive safety 3, macOS builder/export safety 3.
PASS: Actual Qt WebEngine loopback integration: login wait -> sign-in ->
      one POST -> save shown; duplicate prevention; no automatic server-error
      retry; persistent login cookie reused by a second app window.
PASS: All input archives (official Python ZIP and Windows wheels) pass ZIP CRC.
PASS: C offline launcher compiles for Windows x64 with warnings as errors,
      icon, version resource and asInvoker manifest, without PowerShell/pip.
PASS: Python compilation. Generated icon converted into multiresolution ICO.

Setup is assembled on Linux from the official app-local Python distribution
and Windows x64 wheels. DLLs, local ONNX models, Qt WebEngine process/resources
and component notices are included. This is an actual NSIS installer build,
not a first-run download bootstrap. See payload-manifest.json and inputs lock.

INDEPENDENT WINDOWS TESTING STILL REQUIRED:
- Actual Setup installation/removal, desktop shortcut and clean-PC app launch.
- Native F8/F9 hotkeys and physical keyboard input inside StarCraft.
- Windows offline self-test and photo recognition.
- Real SCRMaps/Battle.net login/issuance and embedded-browser compatibility.
- Final antivirus scan, code signing and SmartScreen reputation.

Keyboard unit tests use a fake Windows API backend. Linux Qt tests use a local
fixture with no real account or leaderboard submission. Test-only Linux
sandbox/offscreen settings are not enabled in the Windows product.

The installer/launcher are unsigned. No claim of warning-free distribution is
made. Internal app implementation remains Python/Qt with a native C launcher;
users do not separately install Python, OCR or a VC redistributable.

No private screenshots, logs, browser profiles, test fonts or build-host runtimes
are included in the source ZIP. Runtime wheels and their notices are included
only in the Setup payload. Source archive includes the generated app icon.

1.4.1 trimming verification:
- Qt Python extension references + recursive Windows DLL import/delay-import
  closure select the shipped Qt modules. Debug resources, unused modules/tools,
  excess translations, QML, development/test files and optional video tooling
  are omitted. All OCR models and normal WebEngine resources remain local.
- The Linux analogue with the same 8 Qt Python modules passes the offline OCR /
  actual WebEngine smoke test. Imports of omitted sympy/mpmath are blocked.
- Windows-native execution remains unverified. Linux needs additional ICU/DBus
  libraries not required by the Windows build; they are test-only additions.
- Upgrade runs the previous app's exact-file uninstaller before installing the
  slim payload, preserving data outside the installation folder. Actual Windows
  upgrade/repair must still be checked on Windows.

1.4.2 F8 fix and macOS preparation:
- Global F8/F9 detection uses an independent 10ms thread, no HWND hotkey
  registration or Qt nativeEvent dispatch. It records detection and reports
  missing code, incorrect foreground app and process/input errors separately.
- Tests cover key held on launch/permission grant, repeats, simultaneous F9,
  stale foreground target, and operation without a Qt HWND/message loop.
- GUI queue -> sender and F9 cancellation routing are tested while minimized
  using a fake OS keyboard; this does not prove native game injection.
- macOS backend calls CoreGraphics/AppKit via ctypes. Permission checks,
  mapping, flags, event release and platform data paths have simulated tests.
- macOS .app/DMG builder and GitHub workflow are included; neither was run on
  a real Mac. NO MAC BINARY IS INCLUDED. macOS support is not release-validated.
- Windows native F8 detection and StarCraft input still need retesting on the
  user's PC. The observed older failure has no captured OS trace, so its exact
  cause cannot be asserted from these tests.

1.4.5 process name update:
- The branded Win32 GUI EXE loads the existing app-local python312.dll and calls
  Py_Main in-process. No python.exe/pythonw.exe child is launched.
- The DLL-local python312._pth still isolates bundled import paths. User Python
  installations and registry import paths are not used or modified.
- The main EXE contains SCRMaps Helper FileDescription/ProductName/icon and
  SCRMapsHelper.exe OriginalFilename. QtWebEngineProcess remains a browser helper.
- The small updater requires an existing 1.4.2 (or already updated 1.4.5) install,
  holds the app mutex, stages files before changes, renames originals to backup,
  rolls back failed replacements, and updates only existing tracked app files.
- PASS: production C host compiled and executed against simulated Win32/Py_Main
  boundaries: 12 startup/argument/exit/failure cases including Korean/spaced paths.
- PASS: Windows x64 native compilation with warnings as errors; PE description,
  icon, imports and actual CPython DLL Py_Main export verified at build time.
- These are not real Windows execution tests. Windows loader initialization,
  native Task Manager display, updater rollback and actual game use still need
  Windows testing. No claim of Windows runtime validation is made.

1.4.5 close/restart regression (Linux Qt with real subprocesses):
- Reproduced: old X path left the Qt event loop alive even with the worker stopped
  and the main window closed/hidden. An external quit was needed in the fixture.
- Closing explicitly cancels bridge RPCs and navigation, wakes the worker queue,
  deletes pages before the persistent profile and explicitly quits QApplication.
  Qt objects are destroyed before Python interpreter finalization.
- Real application subprocesses exited without an external quit/kill and reopened
  the same data/profile immediately: idle, stalled navigation, POST in flight.
- Pending browser calls woke on cancellation; queued operations were rejected.
- POST in flight was never duplicated during the subsequent launch.
- Existing actual-browser login/save/duplicate/cookie persistence test passed.
- These are Linux runtime tests; the Windows EXE/update/native game remain
  unexecuted in this build environment. Windows retesting is still required.
- The startup-immediate repeated-close case also exited and reopened successfully.

## 1.4.5 GitHub and document packaging

- Public source export uses an explicit root allowlist. Private root JSON,
  history, AppData folders, profiles and explanation TXT are not exported.
- Known old application documentation TXT files are removed by the transactional
  updater; runtime and component license/notice files are retained.
- Packaging/fetch tests: 17 passed. Exact-download integrity failures preserve
  the previous destination. Version consistency is checked for the Mac bundle.
- Workflow YAML and job dependencies were parsed and checked locally. Windows
  Setup + two Mac DMGs are configured to build automatically on main/master or
  manual dispatch. Version tags attach successful output to a draft Release.
- GitHub remote jobs have NOT run. No Mac DMG is supplied with this source ZIP.
  Actual Mac/Windows installer execution and signing status require the remote
  jobs and target-machine validation.


## 1.4.6 OCR regression checks (2026-10-28 KST)

- Source regression suite: 96 test cases, 95 passed, 1 skipped. The skipped case
  is the legacy external Playwright browser suite because its Chromium binary
  was not installed. The real Qt embedded-browser, review UI, login-resume and
  close/reopen tests passed against local fixture pages.
- Actual RapidOCR 1.4.4 inference: synthetic fixtures plus the externally supplied
  game screenshot passed. OCR did not use the network during fixture inference.
- Supplied screenshot: the 25-character code and CR2 map slug matched at original,
  75% and 125% size. Ambiguous chunk confidence keeps this case review-only.
  No authentication code was sent to the live site.
- Limited 24-image synthetic comparison: old source read 21/24 correctly and
  auto-approved 2 wrong codes; patched source read 24/24 correctly and
  auto-approved 0 wrong codes. This is a small generated test set, not a general
  accuracy rate or a guarantee on other game fonts/screenshots.
- Offline self-test passed OCR model initialization, character-confidence metadata,
  Qt WebEngine resource/subprocess use and local JavaScript evaluation.
- Windows/macOS installers were not rebuilt or executed in this revision.
  Source and an existing-offline-install file patch are provided. Registry and
  old installer manifest changes require a proper rebuilt Setup upgrade.
- No personal screenshot, actual code, browser profile, history database,
  AppData files or new OCR model is included in the source or patch ZIP.


## 1.4.7 automatic submit and result capture (2026-10-28 KST)

108 source tests ran: 107 passed, one legacy Playwright/Chromium suite skipped.
The Qt browser/loopback HTTP end-to-end tests passed automatic submission of
review-flagged OCR, nested board navigation, readonly code display, copy-only
result capture, GET refresh after confirmed success, recovery of prior unread
results with no new POST, and rejection without displaying an old code.
Six DOM result layouts were checked. Real-model OCR read the supplied 25-character
image correctly on three detailed/fast comparisons; measured fast OCR 0.31-0.34s
versus detailed 0.87-1.01s on this host. This does not include live server time.
The local offline model and browser self-test passed, including a readonly
save-code result field. No personal screenshot or real code is shipped.
Actual SCRMaps account submission and native Windows installation/execution,
macOS packaging and production code signing were not performed.

An already-recorded server response also reads the saved code with a GET rather than sending another POST.

## 1.4.8 결과 추출 회귀 검사

결과 영역 범위, 링크/일반 문구/숨긴 값 제외, 링크 복사 버튼 미실행, 복수 후보 처리, 이전 결과 버전 표시와 GET 재확인, 성공 문구와 코드 본문 갱신 순서가 다른 경우를 추가했습니다. Qt/로컬 HTTP 통합 검사를 실행합니다. 실제 계정 발급 및 Windows 실기는 수행하지 않았습니다.

## 1.4.9 묶음 코드 검사

사이트 전용 코드 영역의 세 글자 묶음과 표시용 하이픈을 재현합니다. DOM 읽기·복사 결과·Python 결과 검증의 구분자 처리를 검사하고 앱과 기록에는 구분자가 없는 값이 전달되는지 확인합니다. 인증번호의 기존 엄격한 검증은 유지합니다.
