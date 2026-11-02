"""Desktop entry point for the HD520 companion. Standard library only.

Modes:
  HD520Companion.exe (no args): desktop server mode. Starts the REST
    server with --desktop (UI page served with the API token injected,
    jobs under the per-user data dir), waits for the server to answer
    /health, then opens the UI in its own app window: Chrome app mode
    when Chrome is found (a chromeless window, no tabs or address
    bar), otherwise the default browser. Quit from the UI Quit button
    (POST /api/shutdown) or stop the process.
  HD520Companion.exe --mcp: MCP server over stdio (same binary).

Run from source the same way: `py desktop.py` or `py desktop.py
--mcp` (or run-desktop.bat on Windows). No build is needed to try
desktop mode; the build only removes the Python requirement.

Packaged runs write stdout/stderr to a log file under the per-user
data dir (Windows: %APPDATA%\\HD520Companion\\desktop.log). A windowed
exe has no console, so without this a startup failure would leave
no evidence at all; with it, the log says what happened.
"""

import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

URL = "http://127.0.0.1:8791/"


def _wait_for_server(timeout_s=60.0):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(URL + "health", timeout=1) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.2)
    return False


def _find_chrome():
    candidates = []
    if sys.platform == "win32":
        for base in (os.environ.get("PROGRAMFILES"),
                     os.environ.get("PROGRAMW6432"),
                     os.environ.get("LOCALAPPDATA")):
            if base:
                candidates.append(os.path.join(
                    base, "Google", "Chrome", "Application", "chrome.exe"))
    for name in ("google-chrome", "chrome", "chromium"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def _open_browser():
    import webbrowser
    _wait_for_server()
    chrome = _find_chrome()
    if chrome:
        try:
            subprocess.Popen([chrome, "--app=" + URL])
            return
        except Exception:
            pass
    webbrowser.open(URL)


def _redirect_output_to_log():
    """Send stdout/stderr to a log file. Packaged runs only."""
    try:
        from keystore import user_data_dir
        path = user_data_dir()
        path.mkdir(parents=True, exist_ok=True)
        log = open(path / "desktop.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = log
        sys.stderr = log
    except Exception:
        pass


def main():
    args = sys.argv[1:]
    if "--mcp" in args:
        import mcp_server
        mcp_server.main()
        return
    if getattr(sys, "frozen", False):
        _redirect_output_to_log()
    sys.argv = [sys.argv[0], "--desktop"]
    import server
    threading.Thread(target=_open_browser, daemon=True).start()
    server.main()


if __name__ == "__main__":
    main()
