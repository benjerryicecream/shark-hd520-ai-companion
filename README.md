# Shark HD520 AI Companion

A local-first AI companion for the Shark HD520 CNC, built around (never inside)
VCarve Pro 11. The cabinet generator proposes geometry; a deterministic rules
engine, nesting, and preflight decide what may become a file.

## Pre-existing vs built during the hackathon

Pre-existing (built before the hackathon, Oct 20-25): spec v1.1, the
cabinet-generator prototype, and the Phase 0 profile/worksheet.

Built during the hackathon: the real local app in this repo (REST + MCP,
parity-tested), Meta-central brief handling, and the 34-inch base cut package
(DXF + preflight report). The physical proof cut on the Shark HD520 is still
to come; nothing in this repo has cut anything yet.

---

# Shark HD520 AI Companion (Phase 1)

Architecture map: one web page (ui/index.html) talks to one REST server (server.py) and one MCP server (mcp_server.py), and both servers call the same engine (engine/) for every result, so the UI path and the MCP path agree by construction. The engine generates frameless cabinet parts, nests them on the Shark HD520 bed, and runs a deterministic preflight with no model in that path; a brief can be parsed by the local regex parser or, only when the caller asks for Meta and a Meta key is configured, by the Meta Model API, with local parsing as the honest fallback when Meta is not requested. DXF output goes to VCarve by file import only, nothing exports when preflight fails, and there is no machine control anywhere in this app: no start, jog, pause, home, spindle, or export-bypass capability exists.

## Run on the Windows desktop

Prerequisites: Python 3.11 or newer. No pip installs are needed. This app uses the Python standard library only.

Install: none. Copy this folder to the desktop machine as is.

Start: double-click run.bat, or run `py server.py` from this folder.

Stop: press Ctrl-C in the server window.

Port: 8791. The server binds 127.0.0.1 only. It is reachable from the desktop machine itself and from nothing else. Do not bind it to 0.0.0.0, do not add port forwarding, and do not put it on Tailscale: agent access beyond localhost is pending the owner's Tailscale decision and is not enabled.

Token rule: every /api call needs header X-API-Token (or Authorization: Bearer) matching env HD520_API_TOKEN. If HD520_API_TOKEN is unset at startup, the server generates a random token, prints it once to stdout with a clear label, and requires it. No token, no calls, including from localhost. The UI page itself needs no token to load, but every API call from it still needs the token, which the UI holds in sessionStorage only and never writes into a job or an export.

Meta rule: provider "meta" works only when the caller requests provider "meta" AND env HD520_META_API_KEY is set on the server. When Meta is requested but no key is set, the server returns HTTP 400 saying Meta is not configured. It never silently runs the local parser and labels the result Meta. When Meta is requested with a key set, the server maps HD520_META_API_KEY to the engine's META_API_KEY variable once at startup (the engine reads META_API_KEY or META_MODEL_API_KEY). Note: the engine runs the Meta parse only when a brief text is supplied; a params-only request records the requested provider without a model call. See API_NOTES.md.

MCP launch: `python3 mcp_server.py` (on Windows: `py mcp_server.py`). It speaks JSON-RPC over stdio. Its token rule matches the REST rule, except a generated token is printed once to stderr, never stdout, so stdout stays clean JSON-RPC.

## Endpoint and tool inventory

REST (server.py, 127.0.0.1:8791):

- GET /health: returns {"ok": true, "app": "hd520-companion", "version": "1.0-phase1"}. No auth required.
- GET /: serves ui/index.html. No auth required for the page itself.
- POST /api/generate_cabinet: body {"params": {...}, "caller": "name"}. Returns the engine job dict (parts, nesting, preflight, cut_list_text, dxf_text, provider_record). Auth required.
- POST /api/check_job_hd520: body {"job": {...}, "caller": "name"}. Returns the engine preflight dict. Auth required.

MCP (mcp_server.py, stdio): exactly two tools, generate_cabinet and check_job_hd520, with input schemas matching the REST bodies plus a required token field in the call arguments. See API_NOTES.md.

No machine-control verb exists in either inventory. There is no start, jog, pause, home, spindle, or export-bypass endpoint or tool, and there are no export endpoints in Phase 1: export_tap and export_svg_dxf belong to later phases.

## Job storage (provisional)

Each generated job is saved as JSON to jobs/job-YYYYMMDD-HHMMSS-<slug>.json, where the slug comes from params job_name or, when no job name is given, from the layout. One JSON line per API call is appended to jobs/api_log.jsonl with caller, tool, job_id, provider, model, and preflight passed. No token or key is ever written to a job file, a log line, a cut list, or DXF output. This folder and naming are PROVISIONAL, pending the owner's decision on job storage. Do not treat them as final.

## Gaps carried forward

- Hinge default: unconfirmed. The Pahoa rebuild reuses existing hinges, so no hinge selection is needed for that job, but a default hinge system for new builds is still open.
- Slide clearance: provisional. When the caller does not supply slide_clearance_in, 0.5 in per side is used and flagged provisional.
- Toe-kick recess: provisional, 3 in, from one pantry note in old paperwork. It is not a confirmed general default.
- Agent access: localhost only, pending the owner's Tailscale decision. Tailscale is undecided and must not be enabled without that decision.
- Job folder and naming: provisional, as described above.
- Spoilboard replace floor: undecided.
- Pantry envelope: there is no default. A pantry request without a box height (or an overall height it can be derived from) is refused with a plain error.
