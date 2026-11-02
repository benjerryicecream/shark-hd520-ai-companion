# HD520 Companion Phase 1: Gaps and Decisions Still Needing Chase

Plain copy only. No em dashes are used in this file. Nothing here
is presented as locked unless it says so.

## Provisional values

- Toe-kick recess: provisional 3 in. Source is one pantry note in
  old paperwork only. It is not a confirmed general default.
- Slide clearance: provisional when absent. When the caller does
  not supply slide_clearance_in, the engine uses 0.5 in per side
  and flags it provisional. A caller-supplied slide clearance is
  not flagged.

## Unconfirmed for new builds

- Hinge system: unconfirmed for new builds. The Pahoa rebuild
  reuses its existing doors, drawers, and hinges, so hinge
  selection does not gate the demo or the Pahoa job. A default
  hinge system for new builds is still open.

## Access decision

- Agent access: localhost-only vs Tailscale is undecided. The app
  as built is localhost-only: the REST server binds 127.0.0.1 port
  8791 only, and the MCP server uses stdio only. Do not bind it to
  0.0.0.0, add port forwarding, or put it on Tailscale without
  Chase's decision.

## Job storage

- Job storage folder and naming are provisional: jobs/
  job-YYYYMMDD-HHMMSS-<slug>.json under the app, plus
  jobs/api_log.jsonl with one line per API call. Chase still needs
  to confirm the folder and naming, or choose a different scheme.

## Machine and tool gaps

- Spoilboard replace floor: undecided. No threshold for replacing
  the spoilboard is set yet.
- Tool gaps are out of scope for this build: shanks unknown on all
  catalog rows, duplicate tool numbers (two #9s, two #1s), missing
  physical bits not yet added as catalog rows, the go-to 1/4 in
  up-cut bit unnamed, and cutting data is Hardwood only (no plywood
  data).

## Engine Meta environment mapping note

- The effective Meta key is now, in precedence order: a key stored
  through the Settings page, env HD520_META_API_KEY, env
  META_API_KEY. The stored key wins over both environment variables.
  The REST server re-resolves before every Meta call, so a key saved
  through Settings works without a restart; the MCP server resolves
  at startup. This supersedes the earlier startup-only HD520 mapping
  note.

## Params-only Meta labeling note

- A params-only request with provider meta and a key set records
  provider meta without a model call, because the engine runs the
  Meta parse only when brief_text is present. This was verified in
  the parity test with a fake key and is documented in
  parity_report.md. It is a labeling gap for the next stage: decide
  whether a params-only Meta request should be labeled differently,
  or refused when it carries no brief to parse. It is not a UI vs
  MCP parity failure, because both paths record it the same way.

## Desktop packaging

- Prepared 2026-11-02: keystore.py (Windows Credential Manager, else
  a 0600 file), Settings endpoints and UI Settings section, desktop
  mode with token injection and a Quit button, desktop.py entry,
  hd520-companion.spec, build.bat, run-desktop.bat. Pushed to the
  public repo 2026-11-02 as the second commit; the sync record
  carries the SHA. The onefile exe built on the desktop 2026-11-02
  did not serve the page; see the follow-up bullet.
- 2026-11-02 follow-up, pending push: the onefile exe did not serve
  the page while the from-source run works, so the packaging was
  reworked to onedir (no extraction step, visible files), the UI was
  restyled (screen polish, print stays monochrome), the exe now opens
  a Chrome app-mode window with a 60s first-launch wait, and packaged
  runs log to desktop.log. The Chrome app-mode path is untested here
  (no Chrome on this VM).
- The Windows vault path (Credential Manager via ctypes) is
  untested here: this VM is Linux, so only the file fallback was
  exercised. The first Windows run should confirm the Settings page
  reports source stored-vault.

## Desktop work still to do

- VCarve round-trip: import the demo DXF into VCarve Pro 11 and
  confirm it behaves as expected there. Not done in this stage.
- Public repo creation: owner creates repos himself. No repo was
  created in this stage.
- Scrap confirmation: confirm the demo cuts cleanly on scrap
  before cutting good stock. Not done in this stage.
- Real proof cut: the actual cut on the Shark HD520 is desktop
  work still to do. Nothing in this stage cut anything.
- Binding manual check: confirm from the desktop that nothing
  outside localhost can reach the REST server. Non-local
  reachability testing was out of scope on this VM.
