# HD520 Companion Phase 1: UI vs MCP Parity Report

Plain copy only. No em dashes are used in this file.

Test file: tests/test_parity.py, run from the app root as
`python3 tests/test_parity.py`. Standard library unittest only.
Result: 14 tests ran, 14 passed, 0 failed.

The test starts the real REST server and the real MCP server as
subprocesses, waits for REST health, runs, stops both servers, and
deletes every job file and log line it created. jobs/ was left empty,
as found. No product code was modified.

## Demo case used

The same JSON the UI sends for the 34 in drawer bank, all defaults,
pin grid OFF, provider local:

- width_in 34, height_box_in 30, overall_height_in 34.5, depth_in 24
- layout drawer-bank, material_thickness_in 0.453
- pin_grid_enabled false, provider local

## Parity verdict: PASS

UI path (POST /api/generate_cabinet) and MCP path (tools/call
generate_cabinet, same params) produce identical results:

- Parts count, REST: 16
- Parts count, MCP: 16
- Parts lists: identical, deep equality on the full parts arrays
- Nesting sheets, REST: 10
- Nesting sheets, MCP: 10
- Preflight, REST: passed true
- Preflight, MCP: passed true
- Preflight dicts: identical
- Parts list SHA-256: b5b5cf9b0680e8ff3af60207e0edb8fef608f0d0c652ab1a145d4341630c924b

Job ids differ by design (REST cut package job job-ae539f29167a,
MCP job job-68272753c0fb in the cut package run). Job ids are not
part of the parts, nesting, or preflight comparison.

## Acceptance figures: PASS

- Demo parts: 16, as required
- Demo nesting sheets: 10, as required
- Preflight: passed
- Pin grid: OFF
- Provider record for the demo: local, model local

## Failure cases

All of these were checked on both paths where applicable.

1. 64 in wide cabinet: FAILS preflight on both paths.
   REST generate and MCP generate both return passed false, with
   dxf_text empty and cut_list_text empty. check_job_hd520 on that
   job returns passed false on both paths. No usable export exists.

2. Nominal thickness 0.750 in with thickness_is_nominal true:
   WARNS and still exports on both paths. Preflight passed true.
   Rule R3 warns with the detail "measured thickness required".
   dxf_text and cut_list_text are both non-empty. The job params
   provisional list includes material_thickness_in.

3. Clamp-zone failure with clamps_enabled true: FAILS on both paths.
   Generate with clamps_enabled true returns passed false with rule
   R4 fail and empty dxf_text on both paths. check_job_hd520 on the
   demo job with clamps_enabled set true also returns passed false
   with rule R4 fail on both paths.

4. Tape small-part warning: WARNS on both check paths. A demo job
   with a 2 x 2 in part added (tabs off) returns rule R5 warn from
   check_job_hd520 on both the REST path and the MCP path.

## Auth: PASS

- REST, no token: HTTP 401
- REST, wrong token: HTTP 401
- MCP, bad token: JSON-RPC error, code -32001
- MCP tools/list: exactly two tools, in order:
  generate_cabinet, check_job_hd520

## Secrets: PASS

- REST body containing an api_key field with the planted fake key
  sk-test-fake-key-123: refused with HTTP 400.
- MCP call arguments containing the same planted fake key in an
  api_key field: refused with a JSON-RPC error.
- No file created by the test in jobs/ contained the planted fake
  key. Note: the literal fake key appears only in the test source
  itself, as the planted value, not in any job file, log line, or
  export.
- Demo DXF and cut list scan clean via the engine scan_for_secrets
  against the planted fake key and the test token: zero hits.

## Meta honesty: PASS, with one labeling note

- Provider meta with NO HD520_META_API_KEY set: REST returns
  HTTP 400 saying Meta is not configured. MCP returns a JSON-RPC
  error saying Meta is not configured. No silent local result was
  ever labeled Meta in this case.
- Provider local with a brief ("34 inch wide drawer bank, PureBond
  birch"): provider record is local, parts 16.

### Meta labeling note (observed behavior, not a parity failure)

Verified and documented, product code unchanged: a params-only
request with provider meta and a key set records provider meta
without a model call. In the keyed test run, with a fake Meta key
set in the server environment only, REST generate with provider
meta and no brief_text returned HTTP 200, provider_record provider
meta, model muse-spark-1.3, parts 16, and a parts list identical to
the local demo parts. No brief was supplied, so there was nothing
for a model to parse, and the engine records the requested provider
without making a model call.

This is a labeling gap for the next stage, not a failure of UI vs
MCP parity: both paths record the same provider in the same way,
but a params-only Meta request is presented as Meta even though no
model ran. The next stage should decide how a params-only Meta
request is labeled, for example recording that no model call was
made, or refusing a Meta request that carries no brief to parse.

## No-machine-control audit: PASS

Audited by asserting on discovered route and tool lists, not by
reading prose:

- REST allowed routes confirmed working: GET /health (200),
  GET / (200, UI page), POST /api/generate_cabinet (200),
  POST /api/check_job_hd520 (200).
- REST probes for forbidden verbs returned 404: GET and POST for
  /api/start, /api/jog, /api/home, /api/pause, /api/spindle, and
  POST for /api/export_start, /api/export_jog, /api/export_home,
  /api/export_pause, /api/export_spindle.
- MCP tools/list returned exactly generate_cabinet and
  check_job_hd520.
- MCP tools/call for each of start, jog, home, pause, spindle
  returned a JSON-RPC error (unknown tool).

No start, jog, home, pause, or spindle verb exists as a REST route
or an MCP tool.

## Binding: PASS on localhost, with a manual desktop check still open

- The REST server answers on 127.0.0.1 port 8791. A direct socket
  connection to 127.0.0.1:8791 succeeded, and GET /health returned
  the app record for hd520-companion.
- Testing reachability from a non-local interface is out of scope
  on this VM. It is listed as a manual desktop check in gaps.md:
  confirm from the desktop that nothing outside localhost can reach
  the server.

## Cut package produced

- outputs/dxfs/34in-base.dxf: cut-ready DXF from the passing REST
  job, byte content equal to that job dxf_text (4453 bytes).
- outputs/preflight-34in-base.json: full preflight dict for that
  job, plus job id, params, parts count 16, sheets count 10.
- Cut list for the same job: 1797 characters (kept in the job
  record; no separate cut list file was requested).

## Cleanup and server state

After the test run and the cut package run, jobs/ is empty and no
servers are running. The outputs/ files above are deliverables, not
job files, and were not deleted.
