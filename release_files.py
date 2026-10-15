"""Explicit public-source and installed-document policy. Never scan AppData."""
LEGACY_DOCS=(
    'README_ko.txt','BUILD_OFFLINE_ko.txt','BUILD_MACOS_ko.txt',
    'VALIDATION.txt','DISTRIBUTION_ko.txt','THIRD_PARTY.txt',
)
SOURCE_ROOT_FILES={
    'app.py','desktop.py','browser_panel.py','embedded_gateway.py','worker.py',
    'core.py','paths.py','recognition.py','web_gateway.py','key_sender.py','mac_keyboard.py',
    'theme.py','self_test.py','build_offline.py','build_windows.py','build_macos.py',
    'build_name_update.py','slim_runtime.py','release_files.py','fetch_windows_inputs.py',
    'offline_launcher.c','offline_launcher.rc','offline_launcher.manifest',
    'installer.nsi','process_name_update.nsi','offline-inputs.json','requirements.txt',
    'README.md','THIRD_PARTY.md','.gitignore',
}
