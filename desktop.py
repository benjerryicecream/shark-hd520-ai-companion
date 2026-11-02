"""Desktop entry point for the HD520 companion. Standard library only.

Modes:
  HD520Companion.exe (no args): desktop server mode. Starts the REST
    server with --desktop (UI page served with the API token injected,
    jobs under the per-user data dir), waits for the server to answer
    /health, then opens the UI in the default browser. Quit from the
    UI Quit button (POST /api/shutdown) or stop the process.
  HD520Companion.exe --mcp: MCP server over stdio (same binary).

Run from source the same way: `py desktop.py` or `py desktop.py
--mcp` (or run-desktop.bat on Windows). No build is needed to try
desktop mode; the build only removes the Python requirement.
"""

import sys
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

URL = "http://127.0.0.1:8791/"


def _wait_for_server(timeout_s=10.0):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(URL + "health", timeout=1) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.2)
    return False


def _open_browser():
    import webbrowser
    _wait_for_server()
    webbrowser.open(URL)


def main():
    args = sys.argv[1:]
    if "--mcp" in args:
        import mcp_server
        mcp_server.main()
        return
    sys.argv = [sys.argv[0], "--desktop"]
    import server
    threading.Thread(target=_open_browser, daemon=True).start()
    server.main()


if __name__ == "__main__":
    main()
