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

- The servers map HD520_META_API_KEY to the engine's META_API_KEY
  at startup, overriding a pre-existing META_API_KEY in that server
  process. The owner may prefer the engine variable to win instead.
  This is a decision for the next stage, not a change made here.

## Params-only Meta labeling note

- A params-only request with provider meta and a key set records
  provider meta without a model call, because the engine runs the
  Meta parse only when brief_text is present. This was verified in
  the parity test with a fake key and is documented in
  parity_report.md. It is a labeling gap for the next stage: decide
  whether a params-only Meta request should be labeled differently,
  or refused when it carries no brief to parse. It is not a UI vs
  MCP parity failure, because both paths record it the same way.

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
