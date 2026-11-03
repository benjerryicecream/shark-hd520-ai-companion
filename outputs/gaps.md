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

## Provider honesty fix (2026-11-02, pending push)
- Local never runs a model: there is no local LLM backend in
  this app, and none is needed. The local path is a keyword
  parser plus the deterministic engine. The provider record
  used to say model "local", which read as if a local model
  ran. It now says model "none", and the UI provider record
  for a local job reads "no model call" with that explanation.
- The provider dropdown now preselects Meta when a key is
  saved (Settings reports meta_configured), and Local when no
  key is saved. Before this, a fresh page always defaulted to
  Local even with a key in the vault, so a saved key alone
  never switched providers.
- The page header now says the Meta part out loud: the page
  talks to the server on this machine only, and with provider
  Meta that server sends the brief to Meta's API.
- Mirror gap still open: with provider Meta selected but no
  brief typed, the record says Meta even though no call ran,
  because there is nothing to parse. Documented, not yet fixed.

## Result previews (2026-11-02, pending push)
- Every passing job now carries a front-elevation SVG
  (preview_svg) and one SVG per nesting sheet (sheet_svgs).
  The front drawing is built from the job's params and layout
  rules, so rect sizes match the front parts in the parts list;
  walls show a mount line and no toe kick, base cabinets show
  the toe kick as a separate ladder pack. Sheet drawings show
  each placed tile at actual size, labeled with part id, R when
  rotated, T<n> for tile index. Both are monochrome schematics,
  not photos: gaps and hardware are not shown. Deliberately
  not AI-generated pictures, which would invent details and
  mismatch the parts list.
- The UI results show the front preview first, then sheet
  buttons (one per setup) that swap the sheet drawing. The
  preview box is screen-only: print stays cut-list-only.
- The layout picker and live sketch gained the drawer-over-door
  card and branch (one drawer top third, one door below).

## Full visualizer + brief decides (2026-11-02, pending push)
- "Let the description decide" checkbox under the brief box.
  When checked, the form sends only the description (plus
  provider), and the description sets width, height, depth,
  layout, and thickness. Checked with an empty description
  refuses with a plain message instead of submitting. While
  checked, the form's live sketch hides, since it cannot know
  the description's dims; the result preview after Generate
  shows the actual job.
- Engine fix the checkbox required: layout and width used to
  be validated before the brief was read, so a brief alone
  could never work. Validation now runs after brief parsing.
  Calls without a brief behave exactly as before.
- Local reader hardened for real phrasing: height now accepts
  "high" and bare "height N" alongside "tall" and "box height";
  depth and height accept a bare number ("12 deep", "21 tall")
  as well as a unit ("12 inch deep"). Width already had a
  bare fallback.
- Part drawings: every passing job carries one SVG per part
  (part_svgs), each at true proportions with size, material,
  thickness, grain direction lines, and edge banding as text.
  Edge positions are not drawn, since the part record names
  the banded edge but not its orientation. The UI Preview box
  gained a Part drawings row of buttons that swap the drawing.
  The visualizer now covers the cabinet front, every part, and
  every nesting sheet. Print stays cut-list-only.

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
