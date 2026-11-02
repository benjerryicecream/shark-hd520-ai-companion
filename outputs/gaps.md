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
- 2026-11-02 follow-up, pushed the same day as the third commit: the onefile exe did not serve
  the page while the from-source run works, so the packaging was
  reworked to onedir (no extraction step, visible files), the UI was
  restyled (screen polish, print stays monochrome), the exe now opens
  a Chrome app-mode window with a 60s first-launch wait, and packaged
  runs log to desktop.log. The Chrome app-mode path is untested here
  (no Chrome on this VM).

## Visual layout picker (2026-11-02, pushed as commit 4)
- The layout dropdown is replaced by picture cards, each with a
  front-elevation SVG diagram of what the layout builds: doors (two
  doors), drawers over doors (one drawer, two doors), drawer bank
  (two drawers, the engine default count), sink base (sink basin
  outline, false front, two doors), pantry (tall, two doors), wall
  (wide short cabinet, two doors, hanging line above). The
  diagrams match the engine's actual divisions.
- A live schematic front view below the picker redraws from the
  width, box height, and selected layout inputs. It is labeled as
  schematic: gaps and hardware are not shown. Print output is
  unchanged, because the form (picker and preview included) is
  hidden in print.
- The Windows vault path (Credential Manager via ctypes) was
  confirmed on Windows 2026-11-02: Hermes saved the Meta key and
  Settings reported source stored-vault.

## Wall cabinets (2026-11-02, pending push)
- New layout "wall": carcass 6 + shelves + doors, hangs, no toe
  kick. Overall height resolves to box height; toe-kick params
  resolve to 0; the cut list says "hangs, no toe kick" instead
  of the ladder-pack block. Covers the five rectangular wall
  cabinets from the 2017 drawings: W3621, W3021, W17.7539R,
  W29.539, W18.539R.
- PROVISIONAL rules, not from the drawings: doors 1 under 24 in
  wide, 2 at 24 in and over; shelves 1 at 24 in high or under,
  2 over 24 in. Wall depth comes from params only: the drawing
  labels give widths and heights but no depth, so the user
  enters it from tape (no default invented).
- NOT covered by wall: stepped-corner WSC2439R (corner
  geometry) and microwave WMF3018 (cabinet with an opening).
  Both are separate modules, still to build.
- Brief parsing: local parser maps the word "wall" to layout
  wall; the Meta extractor prompt lists wall among layouts.
  Live Meta brief parsing for a wall cabinet is still unproven
  (needs a run on the desktop with the vault key).

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
