"""Shark HD520 AI Companion MCP server, Phase 1.

Standard library only. JSON-RPC over stdio: read one JSON object per
line from stdin, write one JSON object per line to stdout. All logs
go to stderr only, never stdout, so stdout stays clean JSON-RPC.

Tools (exactly two, Phase 1 only):
  generate_cabinet: same engine function as the REST endpoint.
  check_job_hd520: same engine function as the REST endpoint.

Auth: tools/call arguments must include a "token" field matching env
HD520_API_TOKEN. If that variable is unset at startup, a random
token is generated, printed once to stderr with a clear label, and
required from then on.

Meta rule: provider "meta" is used only when the caller requests it
AND env HD520_META_API_KEY is set. When provider "meta" is requested
but no Meta key is set, tools/call returns a JSON-RPC error and never
silently runs the local parser and labels it Meta.

No API key is ever accepted in call arguments. No token or key is
ever written to a job file, a log line, a cut list, or DXF output.
No machine-control tool exists.
"""

import hmac
import json
import os
import re
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import check_job_hd520, generate_cabinet, scan_for_secrets

APP_ROOT = Path(__file__).resolve().parent
JOBS_DIR = APP_ROOT / "jobs"
VERSION = "1.0-phase1"

API_KEY_ARG_KEYS = {
    "api_key", "apikey", "api-key", "meta_api_key", "meta-model-api-key",
    "hd520_meta_api_key", "hd520_api_key", "hd520_api_token",
}


def _load_token():
    token = os.environ.get("HD520_API_TOKEN")
    if token:
        return token
    token = secrets.token_urlsafe(32)
    sys.stderr.write("HD520_API_TOKEN (generated, required for every "
                     "tools/call): " + token + "\n")
    sys.stderr.flush()
    return token


API_TOKEN = _load_token()

META_KEY = os.environ.get("HD520_META_API_KEY")
if META_KEY:
    # The engine reads META_API_KEY (or META_MODEL_API_KEY). Map the
    # companion variable to the engine variable once at startup.
    # The key value is never printed or logged.
    os.environ["META_API_KEY"] = META_KEY


def _log(text):
    sys.stderr.write(text + "\n")
    sys.stderr.flush()


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
    with open(JOBS_DIR / "api_log.jsonl", "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def _save_job(job, params):
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = _slug(params.get("job_name") or params.get("layout"), "job")
    path = JOBS_DIR / ("job-%s-%s.json" % (stamp, slug))
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(job, handle, indent=2)
    return path.name


def _find_key_arg_key(obj):
    if isinstance(obj, dict):
        for key in obj:
            if str(key).lower() in API_KEY_ARG_KEYS:
                return str(key)
            found = _find_key_arg_key(obj[key])
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_key_arg_key(item)
            if found is not None:
                return found
    return None


def _exports_clean(job):
    values = [v for v in (API_TOKEN, META_KEY) if v]
    for field in ("dxf_text", "cut_list_text"):
        text = job.get(field) or ""
        if text and scan_for_secrets(text, values):
            return False
    return True


TOOLS = [
    {
        "name": "generate_cabinet",
        "description": "Generate a frameless cabinet job for the Shark HD520: parts list, nesting sheets, deterministic preflight, cut list text, and DXF text. Runs the same engine as the REST endpoint. Nothing exports when preflight fails.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "params": {
                    "type": "object",
                    "description": "Cabinet parameters: width_in, height_box_in, overall_height_in, depth_in, layout, material_thickness_in, material_name, pin_grid_enabled, drawer_count, brief_text, job_name, provider (local or meta).",
                },
                "caller": {"type": "string",
                           "description": "Optional caller name for the log."},
                "token": {"type": "string",
                          "description": "API token matching env HD520_API_TOKEN. Required."},
            },
            "required": ["params", "token"],
        },
    },
    {
        "name": "check_job_hd520",
        "description": "Run the deterministic Shark HD520 preflight checks on a cabinet job and return the pass or fail result with per-rule detail and fix text. Runs the same engine as the REST endpoint.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job": {"type": "object",
                        "description": "A cabinet job object as returned by generate_cabinet."},
                "caller": {"type": "string",
                           "description": "Optional caller name for the log."},
                "token": {"type": "string",
                          "description": "API token matching env HD520_API_TOKEN. Required."},
            },
            "required": ["job", "token"],
        },
    },
]


def _error(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id,
            "error": {"code": code, "message": message}}


def _result(request_id, result):
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _handle_tools_call(request_id, arguments):
    if not isinstance(arguments, dict):
        return _error(request_id, -32602, "tools/call arguments must be an object.")
    name = arguments.get("name")
    args = arguments.get("arguments")
    if not isinstance(args, dict):
        return _error(request_id, -32602, "tools/call arguments.arguments must be an object.")
    # The token may sit inside the tool arguments (the documented
    # place) or at the top level of the call. Either is accepted,
    # and it is never passed to the engine.
    token = args.get("token") if isinstance(args.get("token"), str) else arguments.get("token")
    if not isinstance(token, str) or not hmac.compare_digest(token, API_TOKEN):
        _log("MCP auth failed for tools/call: missing or wrong token.")
        return _error(request_id, -32001, "Missing or wrong API token.")
    caller = args.get("caller") if isinstance(args.get("caller"), str) else "unknown"
    bad_key = _find_key_arg_key(args)
    if bad_key is not None:
        return _error(request_id, -32602, "API keys are not accepted in call arguments. Keep keys in server environment only.")
    try:
        if name == "generate_cabinet":
            params = args.get("params")
            if not isinstance(params, dict):
                return _error(request_id, -32602, "generate_cabinet requires a params object.")
            if params.get("provider") == "meta" and not META_KEY:
                _log_call(caller, name, None, "meta", None, None, "error-meta-unconfigured")
                return _error(request_id, -32602, "Meta is not configured. Set HD520_META_API_KEY on the server and retry, or use provider local.")
            job = generate_cabinet(params)
            provider = (job.get("provider_record") or {}).get("provider")
            model = (job.get("provider_record") or {}).get("model")
            passed = (job.get("preflight") or {}).get("passed")
            if not _exports_clean(job):
                _log("Secret scan hit on export for MCP generate_cabinet; refusing result.")
                _log_call(caller, name, job.get("job_id"), provider, model, passed, "error-secret-scan")
                return _error(request_id, -32603, "Export failed a secret scan and was withheld.")
            _save_job(job, params)
            _log_call(caller, name, job.get("job_id"), provider, model, passed, "ok")
            return _result(request_id, {"content": [{"type": "text", "text": json.dumps(job)}], "structuredContent": job})
        if name == "check_job_hd520":
            job_in = args.get("job")
            if not isinstance(job_in, dict):
                return _error(request_id, -32602, "check_job_hd520 requires a job object.")
            preflight = check_job_hd520(job_in)
            provider = (job_in.get("provider_record") or {}).get("provider")
            model = (job_in.get("provider_record") or {}).get("model")
            _log_call(caller, name, job_in.get("job_id"), provider, model, preflight.get("passed"), "ok")
            return _result(request_id, {"content": [{"type": "text", "text": json.dumps(preflight)}], "structuredContent": preflight})
        return _error(request_id, -32602, "Unknown tool: %s." % (name,))
    except ValueError as exc:
        return _error(request_id, -32602, str(exc))
    except RuntimeError as exc:
        return _error(request_id, -32603, str(exc))
    except Exception as exc:
        _log("MCP internal error on %s: %s" % (name, exc.__class__.__name__))
        return _error(request_id, -32603, "Internal server error.")


def _handle(request):
    if not isinstance(request, dict):
        return _error(None, -32600, "Request must be a JSON object.")
    method = request.get("method")
    request_id = request.get("id")
    params = request.get("params") or {}
    if method == "initialize":
        return _result(request_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "hd520-companion", "version": VERSION},
        })
    if method == "tools/list":
        return _result(request_id, {"tools": TOOLS})
    if method == "tools/call":
        if not isinstance(params, dict):
            return _error(request_id, -32602, "tools/call params must be an object.")
        return _handle_tools_call(request_id, params)
    if method == "ping":
        return _result(request_id, {})
    if method is not None and method.startswith("notifications/"):
        return None
    return _error(request_id, -32601, "Method not found: %s." % (method,))


def main():
    _log("HD520 companion MCP server started (stdio).")
    _log("Token rule: every tools/call needs a token field matching env HD520_API_TOKEN.")
    _log("Meta rule: provider meta works only when HD520_META_API_KEY is set.")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError:
            response = _error(None, -32700, "Parse error: input must be one JSON object per line.")
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
            continue
        try:
            response = _handle(request)
        except Exception as exc:
            _log("MCP dispatch error: %s" % exc.__class__.__name__)
            response = _error(request.get("id"), -32603, "Internal server error.")
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
