from paths import DATA

if __name__ == "__main__":
    import sys
    if len(sys.argv)==3 and sys.argv[1]=='--self-test':
        from self_test import run
        sys.exit(run(sys.argv[2]))
    try:
        from desktop import main
        main()
    except Exception:
        import traceback,sys
        DATA.mkdir(parents=True,exist_ok=True)
        (DATA/"crash.log").write_text(traceback.format_exc(),encoding="utf-8")
        if sys.platform=="win32":
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,"실행 오류가 발생했습니다. %LOCALAPPDATA%\\SCRMapsHelper\\crash.log를 확인해 주세요.","SCRMaps Helper",0x10)
        raise
