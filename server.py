"""Shark HD520 AI Companion REST server, Phase 1.

Standard library only. Binds 127.0.0.1 port 8791 only. No Tailscale,
no public binding, no port forwarding. No machine-control endpoints.

Endpoints:
  GET  /health
  GET  /  (serves ui/index.html)
  GET  /api/settings (token required; reports Meta key status, never the key)
  POST /api/generate_cabinet
  POST /api/check_job_hd520
  POST /api/settings/meta-key (token required; the one body that may carry a key)
  DELETE /api/settings/meta-key (token required; removes the stored key)
  POST /api/shutdown (desktop mode only, token required; quits the app)

Auth: every /api/* call requires header X-API-Token or
Authorization: Bearer matching env HD520_API_TOKEN. If that variable
is unset at startup, a random token is generated, printed once to
stdout with a clear label, and required from then on.

Meta rule: provider "meta" is used only when the caller requests it
AND a Meta key is configured. The effective key, in precedence
order, is: a key stored through the Settings page (see keystore.py:
Windows Credential Manager, else a 0600 file under the per-user
config dir), env HD520_META_API_KEY, env META_API_KEY. The resolved
key is mapped to the engine's META_API_KEY variable before every
Meta call, so a key saved through Settings works without a restart.
When provider "meta" is requested but no Meta key is configured, the
server returns HTTP 400 and never silently runs the local parser and
labels it Meta.

The one exception to "no key in a request body": POST
/api/settings/meta-key accepts a Meta key in its body, localhost
only, with a valid API token. That is the Settings page's save path.
Every other endpoint still refuses api_key style body fields. No
token or key is ever written to a job file, a log line, a cut list,
or DXF output.

Desktop mode (--desktop, or the packaged exe): the UI page is served
with the API token injected, so the desktop user never types it.
That trade is deliberate and single-user only: the server still
binds 127.0.0.1, and the token still gates every API call from any
other client. Desktop mode also serves POST /api/shutdown (token
required), which quits the app, and stores jobs under the per-user
data dir instead of the app folder (the packaged exe runs from a
temporary extraction dir, so the app folder is not writable).
"""

import hmac
import json
import os
import re
import secrets
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import check_job_hd520, generate_cabinet, scan_for_secrets
from keystore import (delete_meta_key, get_meta_key, meta_key_source,
                      set_meta_key, user_data_dir)

APP_ROOT = Path(__file__).resolve().parent
UI_FILE = APP_ROOT / "ui" / "index.html"
DESKTOP_MODE = "--desktop" in sys.argv or os.environ.get("HD520_DESKTOP") == "1"
FROZEN = bool(getattr(sys, "frozen", False))
# In desktop mode or in the packaged exe, jobs go under the per-user
# data dir: the exe runs from a temporary extraction dir that is
# wiped on exit, so the app folder is not a safe job store.
JOBS_DIR = ((user_data_dir() / "jobs") if (DESKTOP_MODE or FROZEN)
            else (APP_ROOT / "jobs"))
HOST = "127.0.0.1"
PORT = 8791
VERSION = "1.0-phase1"
# check_job_hd520 bodies carry a whole generated job (DXF + SVGs), so
# the cap is generous, but a body is never read unbounded into memory.
MAX_BODY_BYTES = 5_000_000
_JOB_WRITE_LOCK = threading.Lock()

API_KEY_BODY_KEYS = {
    "api_key", "apikey", "api-key", "meta_api_key", "meta-model-api-key",
    "hd520_meta_api_key", "hd520_api_key", "hd520_api_token", "token",
}


def _load_token():
    token = os.environ.get("HD520_API_TOKEN")
    if token:
        return token, False
    token = secrets.token_urlsafe(32)
    print("HD520_API_TOKEN (generated, required for every /api call): "
          + token, flush=True)
    return token, True


API_TOKEN, _TOKEN_GENERATED = _load_token()


def _tokens_match(presented, expected):
    """Constant-time token compare that never raises on odd input.

    hmac.compare_digest on str rejects non-ASCII, so a token header
    with an accented character used to crash the handler thread and
    drop the connection instead of returning 401.
    """
    if not isinstance(presented, str) or not presented:
        return False
    return hmac.compare_digest(presented.encode("utf-8"),
                               str(expected).encode("utf-8"))

def _resolve_meta_key():
    """Effective Meta key: stored key, then original env keys.

    The original env values are captured at import, because
    _apply_meta_key writes the resolved key into os.environ for the
    engine: reading the live META_API_KEY back would mistake a saved
    (and later deleted) key for an environment key.
    """
    stored = get_meta_key()
    if stored:
        return stored
    return _HD520_ENV_KEY or _META_ENV_KEY


def _apply_meta_key():
    """Map the resolved key onto the engine variable. Returns key or None."""
    key = _resolve_meta_key()
    if key:
        os.environ["META_API_KEY"] = key
    elif _META_ENV_KEY:
        os.environ["META_API_KEY"] = _META_ENV_KEY
    else:
        os.environ.pop("META_API_KEY", None)
    return key


def _meta_source():
    """Where the effective key comes from, without revealing it."""
    source = meta_key_source()
    if source:
        return "stored-" + source
    if _HD520_ENV_KEY or _META_ENV_KEY:
        return "env"
    return "none"


# Original environment keys, captured before _apply_meta_key ever
# writes to os.environ. See _resolve_meta_key.
_HD520_ENV_KEY = os.environ.get("HD520_META_API_KEY")
_META_ENV_KEY = os.environ.get("META_API_KEY")

META_KEY = _apply_meta_key()


def _secrets_to_scan():
    values = [API_TOKEN]
    key = _resolve_meta_key()
    if key:
        values.append(key)
    return [v for v in values if v]


def _slug(value, fallback):
    text = re.sub(r"[^a-z0-9]+", "-", str(value or fallback).lower()).strip("-")
    return text or fallback


def _log_call(caller, tool, job_id, provider, model, passed, status):
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "caller": caller or "unknown",
        "tool": tool,
        "job_id": job_id,
        "provider": provider,
        "model": model,
        "preflight_passed": passed,
        "status": status,
    }
    line = json.dumps(record) + "\n"
    with _JOB_WRITE_LOCK:
        with open(JOBS_DIR / "api_log.jsonl", "a", encoding="utf-8") as handle:
            handle.write(line)


def _save_job(job, params):
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = _slug(params.get("job_name") or params.get("layout"),
                 "job")
    # Second-resolution stamps collided: two generations in the same
    # second with the same slug overwrote each other's job file.
    unique = secrets.token_hex(3)
    path = JOBS_DIR / ("job-%s-%s-%s.json" % (stamp, unique, slug))
    with _JOB_WRITE_LOCK:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(job, handle, indent=2)
    return path.name


def _find_key_body_key(obj):
    """Return a rejected body key name, or None. Values are never read."""
    if isinstance(obj, dict):
        for key in obj:
            if str(key).lower() in API_KEY_BODY_KEYS:
                return str(key)
            found = _find_key_body_key(obj[key])
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_key_body_key(item)
            if found is not None:
                return found
    return None


def _check_exports_clean(job):
    """Scan every export string. Return True when clean."""
    values = _secrets_to_scan()
    for field in ("dxf_text", "cut_list_text"):
        text = job.get(field) or ""
        if text and scan_for_secrets(text, values):
            return False
    return True


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, status, text, content_type):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _route(self):
        """Path without the query string, for route matching."""
        return urlsplit(self.path).path

    def _auth_ok(self):
        presented = self.headers.get("X-API-Token")
        if not presented:
            auth = self.headers.get("Authorization") or ""
            if auth.lower().startswith("bearer "):
                presented = auth[7:].strip()
        if not _tokens_match(presented, API_TOKEN):
            sys.stderr.write("Auth failed for %s %s: missing or wrong "
                             "token.\n" % (self.command, self.path))
            return False
        return True

    def _read_json_body(self):
        length = self.headers.get("Content-Length")
        if length is None:
            return None, "Request body is required and must be JSON."
        try:
            size = int(length)
        except ValueError:
            return None, "Invalid Content-Length header."
        if size < 0:
            return None, "Invalid Content-Length header."
        if size > MAX_BODY_BYTES:
            return None, "Request body is too large."
        raw = self.rfile.read(size) if size > 0 else b""
        if not raw:
            return None, "Request body is required and must be JSON."
        try:
            return json.loads(raw.decode("utf-8")), None
        except (ValueError, UnicodeDecodeError):
            return None, "Request body must be valid JSON."

    def do_GET(self):
        route = self._route()
        if route == "/health":
            self._send_json(200, {"ok": True, "app": "hd520-companion",
                                  "version": VERSION,
                                  "desktop": DESKTOP_MODE})
            return
        if route == "/api/settings":
            if not self._auth_ok():
                self._send_json(401, {"error": "Missing or wrong API token."})
                return
            self._send_json(200, {
                "meta_configured": _resolve_meta_key() is not None,
                "meta_source": _meta_source(),
                "desktop": DESKTOP_MODE,
                "version": VERSION,
            })
            return
        if route == "/":
            if not UI_FILE.exists():
                self._send_json(500, {"error": "UI file is missing."})
                return
            page = UI_FILE.read_text(encoding="utf-8")
            if DESKTOP_MODE:
                # Single-user desktop trade, documented in the module
                # docstring: the page is served to localhost only, and
                # the token still gates every API call from any other
                # client. The token is URL-safe, but escape it anyway.
                # The token script must run BEFORE the page's own
                # script: the page reads window.HD520_TOKEN at init
                # time, so injecting before </body> landed too late
                # and the token row never hid (found 2026-11-02).
                safe = API_TOKEN.replace("\\", "\\\\").replace('"', '\\"')
                token_script = ('<script>window.HD520_TOKEN="%s";</script>'
                                % safe)
                if "<script>" in page:
                    page = page.replace("<script>",
                                        token_script + "<script>", 1)
                else:
                    page = page.replace("</body>",
                                        token_script + "</body>", 1)
            self._send_text(200, page, "text/html; charset=utf-8")
            return
        self._send_json(404, {"error": "Not found."})

    def do_POST(self):
        route = self._route()
        if route == "/api/settings/meta-key":
            if not self._auth_ok():
                self._send_json(401, {"error": "Missing or wrong API token."})
                return
            body, error = self._read_json_body()
            if error is not None or not isinstance(body, dict):
                self._send_json(400, {"error": error or "Request body must be a JSON object."})
                return
            key = body.get("key")
            if not isinstance(key, str) or not key.strip() or len(key) > 1000:
                self._send_json(400, {"error": "Body must contain a non-empty key string."})
                return
            try:
                set_meta_key(key)
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
                return
            except OSError:
                self._send_json(500, {"error": "Could not store the Meta key."})
                return
            _apply_meta_key()
            sys.stderr.write("Settings: Meta key saved (source: %s).\n"
                             % _meta_source())
            self._send_json(200, {"meta_configured": True,
                                  "meta_source": _meta_source()})
            return
        if route == "/api/shutdown":
            if not DESKTOP_MODE:
                self._send_json(404, {"error": "Not found."})
                return
            if not self._auth_ok():
                self._send_json(401, {"error": "Missing or wrong API token."})
                return
            self._send_json(200, {"ok": True})
            sys.stderr.write("Desktop shutdown requested from the UI.\n")
            threading.Timer(0.3, lambda: os._exit(0)).start()
            return
        if route not in ("/api/generate_cabinet", "/api/check_job_hd520"):
            self._send_json(404, {"error": "Not found."})
            return
        tool = route.rsplit("/", 1)[-1]
        if not self._auth_ok():
            _log_call("unknown", tool, None, None, None, None, "401")
            self._send_json(401, {"error": "Missing or wrong API token."})
            return
        body, error = self._read_json_body()
        if error is not None:
            _log_call("unknown", tool, None, None, None, None, "400")
            self._send_json(400, {"error": error})
            return
        if not isinstance(body, dict):
            _log_call("unknown", tool, None, None, None, None, "400")
            self._send_json(400, {"error": "Request body must be a JSON object."})
            return
        bad_key = _find_key_body_key(body)
        if bad_key is not None:
            _log_call(body.get("caller") if isinstance(body.get("caller"), str) else "unknown",
                      tool, None, None, None, None, "400")
            self._send_json(400, {"error": "API keys and tokens are not "
                              "accepted in tool request bodies. Send the token "
                              "in the X-API-Token header, and store a Meta key "
                              "through POST /api/settings/meta-key."})
            return
        caller = body.get("caller") if isinstance(body.get("caller"), str) else "unknown"
        try:
            if tool == "generate_cabinet":
                params = body.get("params")
                if not isinstance(params, dict):
                    _log_call(caller, tool, None, None, None, None, "400")
                    self._send_json(400, {"error": "Body must contain a params object."})
                    return
                if params.get("provider") == "meta":
                    if not _apply_meta_key():
                        _log_call(caller, tool, None, "meta", None, None, "400")
                        self._send_json(400, {"error": "Meta is not configured. "
                                          "Save a key on the Settings page or set "
                                          "HD520_META_API_KEY on the server "
                                          "and retry, or use provider local."})
                        return
                job = generate_cabinet(params)
                provider = (job.get("provider_record") or {}).get("provider")
                model = (job.get("provider_record") or {}).get("model")
                passed = (job.get("preflight") or {}).get("passed")
                if not _check_exports_clean(job):
                    sys.stderr.write("Secret scan hit on export for tool "
                                     "generate_cabinet; refusing response.\n")
                    _log_call(caller, tool, job.get("job_id"), provider,
                              model, passed, "500-secret-scan")
                    self._send_json(500, {"error": "Export failed a secret scan and was withheld."})
                    return
                _save_job(job, params)
                _log_call(caller, tool, job.get("job_id"), provider,
                          model, passed, "200")
                self._send_json(200, job)
                return
            job_in = body.get("job")
            if not isinstance(job_in, dict):
                _log_call(caller, tool, None, None, None, None, "400")
                self._send_json(400, {"error": "Body must contain a job object."})
                return
            preflight = check_job_hd520(job_in)
            provider = (job_in.get("provider_record") or {}).get("provider")
            model = (job_in.get("provider_record") or {}).get("model")
            _log_call(caller, tool, job_in.get("job_id"), provider, model,
                      preflight.get("passed"), "200")
            self._send_json(200, preflight)
            return
        except ValueError as exc:
            _log_call(caller, tool, None, None, None, None, "400")
            self._send_json(400, {"error": str(exc)})
            return
        except RuntimeError as exc:
            _log_call(caller, tool, None, None, None, None, "502")
            self._send_json(502, {"error": str(exc)})
            return
        except Exception as exc:
            sys.stderr.write("Internal error on %s: %s\n"
                             % (tool, exc.__class__.__name__))
            _log_call(caller, tool, None, None, None, None, "500")
            self._send_json(500, {"error": "Internal server error."})
            return

    def do_DELETE(self):
        if self._route() == "/api/settings/meta-key":
            if not self._auth_ok():
                self._send_json(401, {"error": "Missing or wrong API token."})
                return
            delete_meta_key()
            _apply_meta_key()
            sys.stderr.write("Settings: Meta key removed.\n")
            self._send_json(200, {
                "meta_configured": _resolve_meta_key() is not None,
                "meta_source": _meta_source(),
            })
            return
        self._send_json(404, {"error": "Not found."})


class CompanionHTTPServer(ThreadingHTTPServer):
    # ThreadingHTTPServer inherits allow_reuse_address=1, which on
    # Windows lets a SECOND instance bind the same port: two desktop
    # processes were found listening on 8791 at once, each with its
    # own random token, so UI calls failed auth at random depending
    # on which process took the connection. Refuse the second bind.
    allow_reuse_address = False
    daemon_threads = True


def main():
    try:
        server = CompanionHTTPServer((HOST, PORT), Handler)
    except OSError:
        sys.stderr.write(
            "HD520 companion: port %d is already in use. Another copy "
            "of the app is probably running; close it and retry.\n" % PORT)
        raise SystemExit(1)
    print("HD520 companion REST server listening on %s:%d" % (HOST, PORT))
    print("UI: http://%s:%d/ (page is public; API calls still need the token)"
          % (HOST, PORT))
    if os.environ.get("HD520_API_TOKEN"):
        print("Token rule: every /api call needs header X-API-Token or "
              "Authorization Bearer matching env HD520_API_TOKEN.")
    else:
        print("Token rule: a token was generated at startup (printed once "
              "above). Every /api call needs it in header X-API-Token or "
              "Authorization Bearer.")
    print("Meta rule: provider meta works only when a Meta key is "
          "configured (Settings page, HD520_META_API_KEY, or "
          "META_API_KEY); otherwise a meta request returns HTTP 400.")
    if DESKTOP_MODE:
        print("Desktop mode: the UI page is served with the API token "
              "injected (localhost only); quit from the UI Quit button. "
              "Jobs are stored under the per-user data dir, not the app "
              "folder.")
    print("Stop: Ctrl-C (or the UI Quit button in desktop mode).")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping.")
        server.shutdown()


if __name__ == "__main__":
    main()
