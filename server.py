"""Shark HD520 AI Companion REST server, Phase 1.

Standard library only. Binds 127.0.0.1 port 8791 only. No Tailscale,
no public binding, no port forwarding. No machine-control endpoints.

Endpoints:
  GET  /health
  GET  /  (serves ui/index.html)
  POST /api/generate_cabinet
  POST /api/check_job_hd520

Auth: every /api/* call requires header X-API-Token or
Authorization: Bearer matching env HD520_API_TOKEN. If that variable
is unset at startup, a random token is generated, printed once to
stdout with a clear label, and required from then on.

Meta rule: provider "meta" is used only when the caller requests it
AND env HD520_META_API_KEY is set. At startup, when HD520_META_API_KEY
is set, it is mapped to the engine's META_API_KEY variable so the
engine Meta path uses it. When provider "meta" is requested but no
Meta key is set, the server returns HTTP 400 and never silently runs
the local parser and labels it Meta.

No API key is ever accepted in a request body. No token or key is
ever written to a job file, a log line, a cut list, or DXF output.
"""

import hmac
import json
import os
import re
import secrets
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import check_job_hd520, generate_cabinet, scan_for_secrets

APP_ROOT = Path(__file__).resolve().parent
JOBS_DIR = APP_ROOT / "jobs"
UI_FILE = APP_ROOT / "ui" / "index.html"
HOST = "127.0.0.1"
PORT = 8791
VERSION = "1.0-phase1"

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

META_KEY = os.environ.get("HD520_META_API_KEY")
if META_KEY:
    # The engine reads META_API_KEY (or META_MODEL_API_KEY). Map the
    # companion variable to the engine variable once at startup.
    # The key value is never printed or logged.
    os.environ["META_API_KEY"] = META_KEY


def _secrets_to_scan():
    values = [API_TOKEN]
    if META_KEY:
        values.append(META_KEY)
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
    with open(JOBS_DIR / "api_log.jsonl", "a", encoding="utf-8") as handle:
        handle.write(line)


def _save_job(job, params):
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = _slug(params.get("job_name") or params.get("layout"),
                 "job")
    path = JOBS_DIR / ("job-%s-%s.json" % (stamp, slug))
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

    def _auth_ok(self):
        presented = self.headers.get("X-API-Token")
        if not presented:
            auth = self.headers.get("Authorization") or ""
            if auth.lower().startswith("bearer "):
                presented = auth[7:].strip()
        if not presented or not hmac.compare_digest(presented, API_TOKEN):
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
        raw = self.rfile.read(size) if size > 0 else b""
        if not raw:
            return None, "Request body is required and must be JSON."
        try:
            return json.loads(raw.decode("utf-8")), None
        except (ValueError, UnicodeDecodeError):
            return None, "Request body must be valid JSON."

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, {"ok": True, "app": "hd520-companion",
                                  "version": VERSION})
            return
        if self.path == "/":
            if not UI_FILE.exists():
                self._send_json(500, {"error": "UI file is missing."})
                return
            self._send_text(200, UI_FILE.read_text(encoding="utf-8"),
                            "text/html; charset=utf-8")
            return
        self._send_json(404, {"error": "Not found."})

    def do_POST(self):
        if self.path not in ("/api/generate_cabinet", "/api/check_job_hd520"):
            self._send_json(404, {"error": "Not found."})
            return
        tool = self.path.rsplit("/", 1)[-1]
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
                              "accepted in request bodies. Send the token "
                              "in the X-API-Token header and keep keys in "
                              "server environment only."})
            return
        caller = body.get("caller") if isinstance(body.get("caller"), str) else "unknown"
        try:
            if tool == "generate_cabinet":
                params = body.get("params")
                if not isinstance(params, dict):
                    _log_call(caller, tool, None, None, None, None, "400")
                    self._send_json(400, {"error": "Body must contain a params object."})
                    return
                if params.get("provider") == "meta" and not META_KEY:
                    _log_call(caller, tool, None, "meta", None, None, "400")
                    self._send_json(400, {"error": "Meta is not configured. "
                                      "Set HD520_META_API_KEY on the server "
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


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
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
    print("Meta rule: provider meta works only when HD520_META_API_KEY is "
          "set; otherwise a meta request returns HTTP 400.")
    print("Stop: Ctrl-C.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping.")
        server.shutdown()


if __name__ == "__main__":
    main()
