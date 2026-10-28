# Shark HD520 AI Companion - Engine Notes (Phase 1, cabinet generator)

Plain copy only. No em dashes are used in this file, in code strings,
or in job output.

## What this engine is

A Python standard library only package. It generates frameless cabinet
part lists, nests them on the Shark HD520 bed, runs deterministic
preflight checks, and exports ASCII DXF and plain text cut lists. It
does not build a server, a UI, or a web artifact. It does not touch
VCarve itself (file import route only). It has no machine-control
capability and it generates no toolpaths: the DXF is flat profiles
plus drill points, and the .tap post step belongs to a later stage.

## Definitions

- Panel: one entry in the job parts list. One panel is one cut piece.
  A panel that must tile still counts as one panel; its nesting
  placements carry tile_index values (0, 1, ...) and are cut in
  tile_index order and joined on index marks.
- Setup: one nested sheet in job nesting sheets. Setups = number of
  nested sheets = len(nesting sheets). A setup is one bed load on the
  25 x 50 in bed, not one plywood sheet and not one sheet of stock.
- Outside dims: width = bottom width + 2 x material thickness,
  depth = side panel width, box height = side panel height. Dry fit
  passes when all three agree with params within 1/32 in.

## Locked values used

- Machine: Shark HD520, travel 25 x 50 x 7 in (X x Y x Z),
  table 28 x 63 in, Next Wave CNC (.tap) post, VCarve Pro 11.
- Construction: frameless only, v1. Measured material thickness
  drives dado/rabbet joinery.
- Base cabinet defaults: box height 30 in, overall height 34.5 in
  with toe kick, depth 24 in. Demo width 34 in.
- Toe kick: 4.5 in high, board 0.25 in thick, a SEPARATE ladder-pack
  base the cabinets sit on. It is NOT part of the cabinet box and it
  is NOT counted as a panel.
- Spoilboard 0.75 in, verified flat. Touch puck Z-zero 0.37 in.
  Safe Z 1.5 in.
- Workholding: painter's tape primary, clamps backup only. Clamp
  zones are 1 in perimeter margins on the bed and are disabled in
  tape mode (the default).
- Spindle: Next Wave 2HP (1.5kW) water-cooled, SKU 20157, ER11,
  collets 1/4 in and 1/8 in, 6000-24000 RPM. RPM and feed are per
  tool, never a global overwrite.
- Materials: PureBond birch nominal 1/2 in = 0.453 in actual
  (default), original Pahoa stock 0.625 in, PureBond nominal
  3/4 in = 0.703 in actual.
- Slides: side-mount ball-bearing.
- Provider: Meta Model API, base URL https://api.meta.ai/v1, model
  muse-spark-1.3, Standard tier, first cloud provider, active.
  Local-only (regex parser, no model) is the fallback. Cloud is used
  ONLY when explicitly configured (env key present AND caller
  requests meta). A failed cloud call raises; it never silently
  falls back to local and never retries on another provider.

## Provisional values (flagged, never presented as locked)

Every job params dict carries a "provisional" list naming each
provisional value actually used.

1. toe_kick_recess_in = 3.0 in. PROVISIONAL only. Source: one pantry
   note in old paperwork. It is NOT a confirmed general default.
   It appears in code comments, in job output (cut list text says
   PROVISIONAL), and in this file. It is listed as provisional even
   when the caller passes 3.0 explicitly, because no confirmation
   mechanism exists yet.
2. slide_clearance_in = 0.5 in per side, used ONLY when the caller
   does not pass slide_clearance_in. This is prototype parity, not
   a confirmed slide model, so it is flagged provisional when
   defaulted. A caller-supplied slide clearance is not flagged.
3. material_thickness_in, when the caller passes
   thickness_is_nominal=True. Preflight rule R3 warns "measured
   thickness required" (warn, not fail) and the thickness is added
   to the provisional list.

## Demo acceptance case (exact)

generate_cabinet with width_in 34, layout "drawer-bank", all other
defaults, pin grid OFF, produces exactly 16 parts (panels) and
exactly 10 nesting sheets (setups). Thickness 0.453 in, box height
30 in, depth 24 in, slide clearance defaulted to 0.5 in per side
(flagged provisional), toe-kick recess 3.0 in (flagged provisional).

### Demo bill of materials (all dims in inches, thickness 0.453 in)

Carcass, 6 panels:
- side-left: 24 wide x 30 high
- side-right: 24 wide x 30 high
- bottom: 33.094 wide x 24 high (width = 34 - 2 x 0.453)
- back: 33.094 wide x 29.547 high (height = 30 - 0.453)
- stretcher-front: 33.094 wide x 4 high
- stretcher-back: 33.094 wide x 4 high

Drawer fronts, 2 panels (front height = (30 - 0.5) / 2 = 14.75):
- drawer-1-front: 33.875 wide x 14.75 high (width = 34 - 0.125)
- drawer-2-front: 33.875 wide x 14.75 high

Drawer boxes, 8 panels (per drawer: 2 sides, back, bottom).
Drawer box outside width = 34 - 2 x 0.453 - 2 x 0.5 = 32.094.
Drawer box depth = 24 - 2 = 22. Box side height = 14.75 - 5.5 = 9.25.
Back width = 32.094 - 2 x 0.453 = 31.188. Bottom = 31.188 x 21.094
(depth 22 - 2 x 0.453, dado-housed):
- drawer-1-box-side-left: 22 x 9.25
- drawer-1-box-side-right: 22 x 9.25
- drawer-1-box-back: 31.188 x 9.25
- drawer-1-box-bottom: 31.188 x 21.094
- drawer-2-box-side-left: 22 x 9.25
- drawer-2-box-side-right: 22 x 9.25
- drawer-2-box-back: 31.188 x 9.25
- drawer-2-box-bottom: 31.188 x 21.094

Total: 6 + 2 + 8 = 16 panels. No dummy parts are used.

### Demo nesting sheets (10 setups)

- setup-1: stretcher-back, stretcher-front, back tile 0
- setup-2: bottom
- setup-3: side-left
- setup-4: side-right
- setup-5: back tile 1
- setup-6: drawer-1-front
- setup-7: drawer-2-front
- setup-8: drawer-1-box-back, drawer-2-box-back,
  drawer-1-box-side-left, drawer-1-box-side-right
- setup-9: drawer-1-box-bottom, drawer-2-box-side-left,
  drawer-2-box-side-right
- setup-10: drawer-2-box-bottom

The back panel (33.094 x 29.547) fits neither bed orientation
(33.094 > 25 and 29.547 > 25), so it tiles widthwise into two
16.547 x 29.547 tiles. That is the only tiled panel in the demo.

## Nesting shop rules (the rules that produce exactly 10 sheets)

1. Sheets are never shared across part groups: carcass, drawer
   fronts, drawer boxes, doors are nested separately.
2. Drawer boxes are NOT separated by drawer. Every drawer box in a
   drawer bank has identical dimensions by construction, so their
   parts nest together. This is what lets the two drawer-box backs
   share setup-8 and the bottoms pack across setup-9 and setup-10.
3. Grain direction is fixed per part and follows the part. The
   rotated flag records bed orientation only; rotation is allowed
   for rectangular panels.
4. Orientation rule: use the part unrotated if it fits the 25 in
   bed width; else rotate it if the rotated form fits; else tile
   it (split the exceeding dimension into equal tiles).
5. Packing rule: first-fit shelf packer, tallest first, narrowest
   first on height ties. A part joins an existing shelf if it fits
   the remaining shelf width and its height fits the shelf height;
   else it starts a new shelf on an existing sheet of the same
   group if vertical room remains; else it starts a new sheet.
   A shelf spans the 25 in bed width; shelves stack along the
   50 in bed length.
6. No padding, no dummy parts, no artificial splitting. Only parts
   that fit neither bed orientation are tiled, and only along the
   exceeding dimension.

## Layouts (all five implemented)

- doors: carcass 6 + 2 doors (door width = (W - 0.25) / 2,
  height = box height - 0.25). 8 panels at 34 in wide.
- drawers-over-doors: carcass 6 + 1 drawer front (height =
  box height / 3) + 1 drawer box (4 panels) + 2 doors (height =
  box height - front height - 0.5). 13 panels at 34 in wide.
- drawer-bank: carcass 6 + drawer_count fronts + drawer_count
  drawer boxes of 4 panels. drawer_count defaults to 2. 16 panels
  at 34 in wide with 2 drawers.
- sink-base: carcass 6 + 1 false drawer front (height =
  box height / 3) + 2 doors. 9 panels at 34 in wide. No drawer box.
- pantry: carcass 6 + top panel + 3 shelves (depth = depth - 1)
  + 2 full-height doors. Pantry height comes from params only.
  A pantry without an explicit height_box_in (or an
  overall_height_in it can be derived from) raises ValueError
  asking for height_box_in. No default pantry envelope is used,
  and the unverified 35 x 86.5 x 18 envelope is never used.

## Preflight rules (deterministic, model-free)

- R1 travel: width > 50 in or depth > 25 in FAILS. A 64 in wide
  cabinet fails, its job carries empty exports, and export_dxf /
  export_cut_list raise ValueError. Rectangular panels that exceed
  the bed tile automatically; a non-tileable part would fail, but
  this generator only produces rectangular panels.
- R2 Z: material thickness > 7 in FAILS.
- R3: thickness_is_nominal=True WARNS "measured thickness
  required" and still exports, with the warning recorded.
- R4 clamp zones: 1 in perimeter margins. Tape mode (default,
  clamps disabled) passes with a note. check_job_hd520 accepts a
  clamps_enabled=True override in the job dict (or in job params);
  with clamps enabled, any placement crossing a clamp zone FAILS
  and blocks export.
- R5 tape small parts: any part with both dims under 3 in, with
  tabs off, WARNS (needs tabs or an onion-skin final pass).
- R6 geometry: all part dims > 0; parts list and nesting agree
  one-for-one (every part id appears in nesting placements; a
  tiled part appears once per tile); dry-fit dims from parts
  agree with params within 1/32 in, else FAIL.
- Export gate: export_dxf and export_cut_list refuse (raise
  ValueError) when preflight passed is False. They check both the
  stored preflight and a fresh deterministic re-check, so a
  clamps_enabled override blocks export even if the stored
  preflight was computed in tape mode. generate_cabinet still
  returns the job with the failed preflight and empty exports.

## Tool catalog (engine/tools_data.json)

Built from the two parsed files:
vtdb-my-tools-2-parsed.json (8 tools) and
vtdb-my-tools-3-parsed.json (the tapered ball nose renumbered to
tool #8). The cleaned catalog has 8 tools: the 7 non-tapered rows
from file 2 plus the file 3 tapered row. The file 2 tapered row
(tool #1) is superseded, not duplicated.

- Every row: shank = "unknown". The .vtdb stores no shank, so none
  is invented.
- Duplicate tool numbers are flagged, not renumbered: two #9s
  (60 degree V-bit and 90 degree 1/4 in V-bit) and two #1s (30
  degree V-bit and 90 degree 2/3 V-bit). Renumbering without owner
  confirmation would invent tool identities.
- Tapered ball nose (tool #8) stepdown/stepover units are flagged
  ambiguous. Raw source values are carried unchanged, never
  converted or trusted as inches.
- Cutting data is Hardwood only. There is no plywood data, and
  that is recorded in the file rather than filled in.
- All per-tool spindle speeds in the catalog fall inside the
  6000-24000 RPM spindle range; no value is clamped.

## Public API (plain dicts in and out, JSON-able)

- generate_cabinet(params) -> job dict
- check_job_hd520(job) -> preflight dict
- export_dxf(job) -> str (ASCII DXF, inches, layers Profile and
  Drill, no key material, no stray construction geometry; side
  panels carry drill points for slide screws)
- export_cut_list(job) -> str (monochrome printable plain text:
  parts, sizes, quantities, material, setup number per part,
  Tide & Tool style header)
- parse_brief_local(brief_text) -> params dict (regex/keyword,
  no model; understands width, height, depth, layout words like
  doors/drawers/sink/pantry, material words like PureBond, pin
  grid on/off)
- parse_brief_meta(brief_text, api_key, base_url, model) -> params
  dict (OpenAI-compatible POST to {base_url}/chat/completions
  via urllib only, 30s timeout, system prompt asking for cabinet
  parameters as JSON; on any failure raises, never retries on
  another provider, never logs the key)
- scan_for_secrets(text, secrets) -> list of hits (empty = clean)

## Honest limitations (things not claimed)

- Pin grid: v1 records pin_grid_enabled as a flag and a cut-list
  note ("ON, 5 mm grid" / "OFF"). 5 mm grid hole positions are NOT
  emitted in DXF v1, because hole start/end margins are
  unconfirmed. The DXF Drill layer in v1 carries only side-panel
  slide-screw pilot points.
- Pantry shelf count is a fixed v1 choice (3 shelves), not a
  measured value.
- Drawer box side height is a v1 shop rule (front height minus
  5.5 in), documented in the demo BOM above. It is a construction
  choice, not a measured standard.
- The Meta provider path is tested for request shape and for
  raising (not falling back) on an unreachable URL. It has NOT
  been live-tested against the real Meta API in this task, because
  that requires an owner-configured env key. generate_cabinet with
  provider "meta" and a brief but no env key raises instead of
  silently using local parsing.
- Tall parts (for example pantry doors taller than 50 in) tile
  automatically per R1. Joining a tiled tall door is a shop
  decision; tiles are marked by tile_index.
- No gate required by the task failed. The demo case, the 64 in
  failure case, the nominal-thickness warning case, the clamp-zone
  failure case, the small-part warning case, the secrets-scan
  case, and the Meta failure case all pass in the test suite.
