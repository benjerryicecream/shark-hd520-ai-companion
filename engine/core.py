"""Shark HD520 cabinet generator engine, Phase 1.

Plain Python standard library only. No model calls anywhere in the
preflight, nesting, DXF, or cut-list paths. Cloud parsing lives only in
parse_brief_meta, and only when the caller explicitly asks for it.

Locked values used here (see ENGINE_NOTES.md for the full list):
- Machine bed 25 x 50 in (X x Y), Z travel 7 in.
- Frameless construction only, v1. Measured material thickness drives joinery.
- Base cabinet box height 30 in, overall 34.5 in with toe kick, depth 24 in.
- Toe kick: 4.5 in high, 0.25 in board, a SEPARATE ladder-pack base the
  cabinets sit on, NOT part of the cabinet box.
- Toe-kick recess 3 in is PROVISIONAL only (one pantry note in old
  paperwork, not a confirmed general default). It is flagged provisional
  everywhere it appears and never presented as locked.
- Pin grid: optional toggle, 5 mm grid when enabled.
- Slides: side-mount ball-bearing. Default slide clearance per side is
  0.5 in when the caller does not pass slide_clearance_in; that default
  is flagged provisional (prototype parity, not a confirmed slide model).
- Spoilboard 0.75 in, touch puck Z-zero 0.37 in, safe Z 1.5 in.
- Workholding: painter's tape primary, clamps backup only.
- Spindle: Next Wave 2HP (1.5kW) water-cooled, SKU 20157, ER11,
  collets 1/4 in and 1/8 in, 6000-24000 RPM, per-tool RPM/feed only.
- Tool cutting data is Hardwood only; there is no plywood data.
- Provider: Meta Model API, base URL https://api.meta.ai/v1, model
  muse-spark-1.3, Standard tier, first cloud provider, active.
  Local-only (regex parser, no model) is the fallback. Cloud is used
  ONLY when explicitly configured (env key present AND caller requests
  meta); there is never a silent fallback to cloud, and a failed cloud
  call raises instead of falling back to local.
"""

import json
import math
import os
import re
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from xml.sax.saxutils import escape as _xml_escape


def _xml(value):
    """Escape a value for XML text or a double-quoted attribute."""
    return _xml_escape(str(value), {'"': "&quot;"})

BED_W_IN = 25.0
BED_H_IN = 50.0
Z_TRAVEL_IN = 7.0
CLAMP_MARGIN_IN = 1.0
DRY_FIT_TOL_IN = 1.0 / 32.0
DEFAULT_BOX_HEIGHT_IN = 30.0
DEFAULT_DEPTH_IN = 24.0
DEFAULT_THICKNESS_IN = 0.453
DEFAULT_TOE_KICK_HEIGHT_IN = 4.5
DEFAULT_TOE_KICK_BOARD_IN = 0.25
PROVISIONAL_TOE_KICK_RECESS_IN = 3.0
PROTOTYPE_SLIDE_CLEARANCE_IN = 0.5
PIN_GRID_MM = 5
META_BASE_URL = "https://api.meta.ai/v1"
META_MODEL = "muse-spark-1.3"
LAYOUTS = ("doors", "drawers-over-doors", "drawer-over-door", "drawer-bank", "sink-base", "pantry", "wall")

# ---------------------------------------------------------------- tools


def load_tools():
    """Load the cleaned tool catalog from tools_data.json next to this file."""
    path = Path(__file__).resolve().parent / "tools_data.json"
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


# ---------------------------------------------------------------- parts

def _part(part_id, name, group, material, thickness, width, height, grain, edge):
    return {
        "id": part_id,
        "name": name,
        "group": group,
        "material": material,
        "thickness_in": round(float(thickness), 6),
        "width_in": round(float(width), 6),
        "height_in": round(float(height), 6),
        "grain": grain,
        "edge_banding": edge,
        "quantity": 1,
    }


def _carcass(width, box_h, depth, t, material):
    """Frameless carcass: 2 sides, bottom, back, 2 top stretchers."""
    inner_w = width - 2.0 * t
    return [
        _part("side-left", "Side left", "carcass", material, t, depth, box_h,
              "vertical", "front edge"),
        _part("side-right", "Side right", "carcass", material, t, depth, box_h,
              "vertical", "front edge"),
        _part("bottom", "Bottom", "carcass", material, t, inner_w, depth,
              "horizontal", "none"),
        _part("back", "Back", "carcass", material, t, inner_w, box_h - t,
              "horizontal", "none"),
        _part("stretcher-front", "Top stretcher front", "carcass", material, t,
              inner_w, 4.0, "horizontal", "none"),
        _part("stretcher-back", "Top stretcher back", "carcass", material, t,
              inner_w, 4.0, "horizontal", "none"),
    ]


def _drawer_box(drawer_no, front_h, box_w, box_depth, t, material):
    """One drawer box: 2 sides, back, bottom (dado-housed bottom)."""
    side_h = front_h - 5.5
    back_w = box_w - 2.0 * t
    prefix = "drawer-%d-box" % drawer_no
    return [
        _part(prefix + "-side-left", "Drawer %d box side left" % drawer_no,
              "drawer-box", material, t, box_depth, side_h,
              "horizontal", "top edge"),
        _part(prefix + "-side-right", "Drawer %d box side right" % drawer_no,
              "drawer-box", material, t, box_depth, side_h,
              "horizontal", "top edge"),
        _part(prefix + "-back", "Drawer %d box back" % drawer_no,
              "drawer-box", material, t, back_w, side_h,
              "horizontal", "top edge"),
        _part(prefix + "-bottom", "Drawer %d box bottom" % drawer_no,
              "drawer-box", material, t, back_w, box_depth - 2.0 * t,
              "horizontal", "none"),
    ]


def _build_parts(params):
    width = params["width_in"]
    box_h = params["height_box_in"]
    depth = params["depth_in"]
    t = params["material_thickness_in"]
    material = params["material_name"]
    layout = params["layout"]
    slide = params["slide_clearance_in"]
    box_w = width - 2.0 * t - 2.0 * slide
    box_depth = depth - 2.0
    front_w = width - 0.125
    parts = _carcass(width, box_h, depth, t, material)
    if layout == "doors":
        door_w = (width - 0.25) / 2.0
        door_h = box_h - 0.25
        parts.append(_part("door-left", "Door left", "door", material, t,
                           door_w, door_h, "vertical", "all edges"))
        parts.append(_part("door-right", "Door right", "door", material, t,
                           door_w, door_h, "vertical", "all edges"))
    elif layout == "drawer-bank":
        count = params["drawer_count"]
        front_h = (box_h - 0.5) / float(count)
        for i in range(1, count + 1):
            parts.append(_part("drawer-%d-front" % i,
                               "Drawer %d front" % i, "drawer-front",
                               material, t, front_w, front_h,
                               "horizontal", "all edges"))
            parts.extend(_drawer_box(i, front_h, box_w, box_depth, t, material))
    elif layout == "drawers-over-doors":
        front_h = box_h / 3.0
        door_h = box_h - front_h - 0.5
        door_w = (width - 0.25) / 2.0
        parts.append(_part("drawer-1-front", "Drawer front",
                           "drawer-front", material, t, front_w, front_h,
                           "horizontal", "all edges"))
        parts.extend(_drawer_box(1, front_h, box_w, box_depth, t, material))
        parts.append(_part("door-left", "Door left", "door", material, t,
                           door_w, door_h, "vertical", "all edges"))
        parts.append(_part("door-right", "Door right", "door", material, t,
                           door_w, door_h, "vertical", "all edges"))
    elif layout == "drawer-over-door":
        front_h = box_h / 3.0
        door_h = box_h - front_h - 0.5
        parts.append(_part("drawer-1-front", "Drawer front",
                           "drawer-front", material, t, front_w, front_h,
                           "horizontal", "all edges"))
        parts.extend(_drawer_box(1, front_h, box_w, box_depth, t, material))
        parts.append(_part("door", "Door", "door", material, t,
                           front_w, door_h, "vertical", "all edges"))
    elif layout == "sink-base":
        front_h = box_h / 3.0
        door_h = box_h - front_h - 0.5
        door_w = (width - 0.25) / 2.0
        parts.append(_part("false-front", "False drawer front",
                           "drawer-front", material, t, front_w, front_h,
                           "horizontal", "all edges"))
        parts.append(_part("door-left", "Door left", "door", material, t,
                           door_w, door_h, "vertical", "all edges"))
        parts.append(_part("door-right", "Door right", "door", material, t,
                           door_w, door_h, "vertical", "all edges"))
    elif layout == "pantry":
        inner_w = width - 2.0 * t
        parts.append(_part("top", "Top", "carcass", material, t,
                           inner_w, depth, "horizontal", "none"))
        for i in range(1, 4):
            parts.append(_part("shelf-%d" % i, "Shelf %d" % i, "carcass",
                               material, t, inner_w, depth - 1.0,
                               "horizontal", "front edge"))
        door_w = (width - 0.25) / 2.0
        door_h = box_h - 0.25
        parts.append(_part("door-left", "Door left", "door",
                           material, t, door_w, door_h, "vertical",
                           "all edges"))
        parts.append(_part("door-right", "Door right", "door",
                           material, t, door_w, door_h, "vertical",
                           "all edges"))
        # Pantry back spans the full inner width and height minus top/bottom.
        for part in parts:
            if part["id"] == "back":
                part["height_in"] = round(box_h - 2.0 * t, 6)
    elif layout == "wall":
        # Wall cabinet: hangs, no toe kick, no drawers, no slides.
        # Doors: one door under 24 in wide, two doors at 24 in and over.
        # Shelves: one shelf at 24 in high or under, two shelves over
        # 24 in. Both rules are PROVISIONAL shop rules, not numbers
        # from the drawings; the drawings give widths and heights only.
        inner_w = width - 2.0 * t
        shelf_count = 1 if box_h <= 24.0 else 2
        for i in range(1, shelf_count + 1):
            parts.append(_part("shelf-%d" % i, "Shelf %d" % i, "carcass",
                               material, t, inner_w, depth - 1.0,
                               "horizontal", "front edge"))
        door_h = box_h - 0.25
        if width < 24.0:
            parts.append(_part("door", "Door", "door", material, t,
                               front_w, door_h, "vertical", "all edges"))
        else:
            door_w = (width - 0.25) / 2.0
            parts.append(_part("door-left", "Door left", "door", material, t,
                               door_w, door_h, "vertical", "all edges"))
            parts.append(_part("door-right", "Door right", "door", material, t,
                               door_w, door_h, "vertical", "all edges"))
    return parts


# ---------------------------------------------------------------- nesting

def _oriented_dims(part):
    """Return (w, h, rotated) fitting the bed width, else None.

    Prefer unrotated. Rotation only changes bed orientation; grain
    follows the part, so rotation is always allowed for rectangular
    panels. Returns None when neither orientation fits (tile it).
    """
    w = part["width_in"]
    h = part["height_in"]
    if w <= BED_W_IN and h <= BED_H_IN:
        return (w, h, False)
    if h <= BED_W_IN and w <= BED_H_IN:
        return (h, w, True)
    return None


def _tiles(part):
    """Return a list of (tile_w, tile_h, rotated, tile_index) for one part.

    Rectangular panels tile automatically: split the exceeding
    dimension into equal tiles that fit the bed. Untiled parts return
    a single tile with tile_index 0.
    """
    oriented = _oriented_dims(part)
    if oriented is not None:
        w, h, rotated = oriented
        return [(w, h, rotated, 0)]
    w = part["width_in"]
    h = part["height_in"]
    n_w = int(math.ceil(w / BED_W_IN)) if w > BED_W_IN else 1
    n_h = int(math.ceil(h / BED_H_IN)) if h > BED_H_IN else 1
    tile_w = w / float(n_w)
    tile_h = h / float(n_h)
    tiles = []
    index = 0
    for _row in range(n_h):
        for _col in range(n_w):
            tiles.append((tile_w, tile_h, False, index))
            index += 1
    return tiles


def _partition_key(part):
    return (part["group"], "")


def _nest_parts(parts):
    """First-fit shelf packer, sheets separated by part group.

    Shop rules (documented in ENGINE_NOTES.md):
    - Sheets are never shared across part groups (carcass, drawer
      fronts, drawer boxes, doors). Drawer boxes are not separated
      by drawer: every drawer box in a drawer bank has identical
      dimensions by construction, so their parts nest together.
    - Grain direction is fixed per part (grain follows the part);
      bed rotation is recorded in the rotated flag.
    - Within a partition, tiles are packed tallest first, narrowest
      first on height ties, first-fit into an existing shelf, else
      a new shelf on an existing sheet, else a new sheet. A shelf
      holds parts side by side across the 25 in bed width; shelves
      stack along the 50 in bed length.
    """
    partitions = {}
    order = []
    for part in parts:
        key = _partition_key(part)
        if key not in partitions:
            partitions[key] = []
            order.append(key)
        partitions[key].append(part)
    sheets = []
    sheet_counter = [0]

    def new_sheet():
        sheet_counter[0] += 1
        sheet = {"sheet_id": "setup-%d" % sheet_counter[0],
                 "bed_w_in": BED_W_IN, "bed_h_in": BED_H_IN,
                 "placements": [], "shelves": []}
        sheets.append(sheet)
        return sheet

    for key in order:
        items = []
        for part in partitions[key]:
            for (tw, th, rotated, tile_index) in _tiles(part):
                items.append((part["id"], tw, th, rotated, tile_index))
        items.sort(key=lambda item: (-item[2], item[1], item[0], item[4]))
        for (part_id, tw, th, rotated, tile_index) in items:
            placed = False
            for sheet in sheets:
                if sheet.get("_group") != key:
                    continue
                for shelf in sheet["shelves"]:
                    if th <= shelf["height"] and shelf["used"] + tw <= BED_W_IN:
                        sheet["placements"].append(
                            {"part_id": part_id, "x_in": round(shelf["used"], 6),
                             "y_in": round(shelf["y"], 6), "rotated": rotated,
                             "tile_index": tile_index})
                        shelf["used"] += tw
                        placed = True
                        break
                if placed:
                    break
                used_h = sum(s["height"] for s in sheet["shelves"])
                if used_h + th <= BED_H_IN:
                    y = used_h
                    sheet["shelves"].append(
                        {"y": y, "height": th, "used": tw})
                    sheet["placements"].append(
                        {"part_id": part_id, "x_in": 0.0,
                         "y_in": round(y, 6), "rotated": rotated,
                         "tile_index": tile_index})
                    placed = True
                    break
            if not placed:
                sheet = new_sheet()
                sheet["_group"] = key
                sheet["shelves"].append({"y": 0.0, "height": th, "used": tw})
                sheet["placements"].append(
                    {"part_id": part_id, "x_in": 0.0, "y_in": 0.0,
                     "rotated": rotated, "tile_index": tile_index})
    for sheet in sheets:
        sheet.pop("shelves", None)
        sheet.pop("_group", None)
    return {"sheets": sheets}


# ---------------------------------------------------------------- dry fit

def _dry_fit_dims(parts, thickness):
    """Outside dims derived from named parts, or None if parts missing."""
    by_id = {p["id"]: p for p in parts}
    side = by_id.get("side-left")
    bottom = by_id.get("bottom")
    if side is None or bottom is None:
        return None
    width = bottom["width_in"] + 2.0 * thickness
    depth = side["width_in"]
    height = side["height_in"]
    return {"width_in": width, "depth_in": depth, "height_in": height}


# ---------------------------------------------------------------- preflight

def _check(rule, status, part, detail, fix=""):
    return {"rule": rule, "status": status, "part": part,
            "detail": detail, "fix": fix}


def _placement_dims(part, placement):
    """Placed (w, h) in inches for one placement, or None if unusable.

    Tiled placements use the tile size from _tiles; a single placement
    uses the part dims, swapped when the placement is rotated. NaN or
    infinite dims, a bad tile_index, and missing keys all give None
    instead of raising, so a malformed job fails preflight cleanly.
    """
    try:
        tile_index = placement.get("tile_index", 0)
        if isinstance(tile_index, bool) or not isinstance(tile_index, int):
            return None
        tiles = _tiles(part)
        if tile_index < 0 or tile_index >= len(tiles):
            return None
        if len(tiles) > 1 or tile_index > 0:
            w, h = tiles[tile_index][0], tiles[tile_index][1]
        else:
            w, h = part["width_in"], part["height_in"]
            if placement.get("rotated"):
                w, h = h, w
        w, h = float(w), float(h)
        if not (math.isfinite(w) and math.isfinite(h)):
            return None
        return (w, h)
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def check_job_hd520(job):
    """Deterministic, model-free preflight. No model anywhere in this path."""
    params = job.get("params", {}) or {}
    parts = job.get("parts", []) or []
    nesting = job.get("nesting", {}) or {}
    sheets = nesting.get("sheets", []) or []
    placements = []
    for sheet in sheets:
        placements.extend(sheet.get("placements", []) or [])
    checks = []
    width = params.get("width_in")
    depth = params.get("depth_in")
    box_h = params.get("height_box_in")
    thickness = params.get("material_thickness_in", DEFAULT_THICKNESS_IN)
    clamps_enabled = bool(job.get("clamps_enabled") or
                          params.get("clamps_enabled", False))
    tabs_enabled = bool(params.get("tabs_enabled", False))

    # R1 travel.
    if width is not None and width > 50.0:
        checks.append(_check("R1", "fail", "",
                             "Cabinet width %.3f in exceeds 50 in travel." % width,
                             "Reduce width to 50 in or less, or split the run."))
    elif depth is not None and depth > 25.0:
        checks.append(_check("R1", "fail", "",
                             "Cabinet depth %.3f in exceeds 25 in travel." % depth,
                             "Reduce depth to 25 in or less."))
    else:
        checks.append(_check("R1", "pass", "",
                             "Cabinet fits 25 x 50 in travel.", ""))
    tiled_ids = sorted({p["part_id"] for p in placements
                        if p.get("tile_index", 0) > 0})
    multi_ids = sorted({pid for pid in
                        {p["part_id"] for p in placements}
                        if sum(1 for p in placements
                               if p["part_id"] == pid) > 1})
    if tiled_ids or multi_ids:
        checks.append(_check("R1-tile", "pass", "",
                             "Tiled parts: %s. Rectangular panels tile "
                             "automatically with index marks."
                             % ", ".join(sorted(set(tiled_ids + multi_ids))),
                             "Cut tiles in tile_index order and join on index marks."))

    # R2 Z.
    if thickness is not None and thickness > Z_TRAVEL_IN:
        checks.append(_check("R2", "fail", "",
                             "Material thickness %.3f in exceeds 7 in Z travel."
                             % thickness,
                             "Use material 7 in or thinner."))
    else:
        checks.append(_check("R2", "pass", "",
                             "Material thickness fits 7 in Z travel.", ""))

    # R3 nominal thickness warning.
    if params.get("thickness_is_nominal"):
        checks.append(_check("R3", "warn", "",
                             "Thickness %.3f in is nominal: measured thickness "
                             "required." % thickness,
                             "Measure the actual stock and re-run with the "
                             "measured thickness."))
    else:
        checks.append(_check("R3", "pass", "",
                             "Thickness is a measured value.", ""))

    # R4 clamp zones: 1 in perimeter margins on the bed.
    if not clamps_enabled:
        checks.append(_check("R4", "pass", "",
                             "Tape mode: clamp zones disabled. Painter's tape "
                             "is primary, clamps are backup only.", ""))
    else:
        by_id = {p["id"]: p for p in parts}
        failures = []
        for sheet in sheets:
            for placement in sheet.get("placements", []) or []:
                part = by_id.get(placement["part_id"])
                if part is None:
                    continue
                dims = _placement_dims(part, placement)
                if dims is None:
                    continue
                pw, ph = dims
                x = placement.get("x_in", 0.0)
                y = placement.get("y_in", 0.0)
                if (x < CLAMP_MARGIN_IN or y < CLAMP_MARGIN_IN
                        or x + pw > BED_W_IN - CLAMP_MARGIN_IN
                        or y + ph > BED_H_IN - CLAMP_MARGIN_IN):
                    failures.append(placement["part_id"])
        if failures:
            checks.append(_check("R4", "fail", "",
                                 "Clamps enabled: placements cross the 1 in "
                                 "clamp zone: %s." % ", ".join(sorted(set(failures))),
                                 "Move placements clear of the 1 in bed "
                                 "perimeter or switch to tape mode."))
        else:
            checks.append(_check("R4", "pass", "",
                                 "No placement crosses the clamp zone.", ""))

    # R5 tape small parts.
    small = [p["id"] for p in parts
             if p["width_in"] < 3.0 and p["height_in"] < 3.0]
    if small and not tabs_enabled:
        checks.append(_check("R5", "warn", "",
                             "Small parts under 3 x 3 in with tabs off: %s. "
                             "These need tabs or an onion-skin final pass."
                             % ", ".join(small),
                             "Enable tabs or plan an onion-skin final pass."))
    else:
        checks.append(_check("R5", "pass", "",
                             "No small-part tape warning.", ""))

    # R6 geometry: dims, one-for-one, dry fit.
    bad_dims = [p["id"] for p in parts
                if p["width_in"] <= 0 or p["height_in"] <= 0
                or p["thickness_in"] <= 0]
    if bad_dims:
        checks.append(_check("R6-dims", "fail", "",
                             "Parts with non-positive dims: %s."
                             % ", ".join(bad_dims),
                             "Fix part dimensions to positive values."))
    else:
        checks.append(_check("R6-dims", "pass", "",
                             "All part dims are positive.", ""))
    part_ids = {p["id"] for p in parts}
    placed_ids = {p["part_id"] for p in placements}
    # Count-aware agreement: each part must be placed exactly once per
    # tile _tiles cuts for it, with tile_index values 0..n-1. A plain
    # set comparison let a duplicated (or dropped duplicate) placement
    # pass, and a tiled part placed with the wrong indexes passed too.
    placed_indexes = {}
    for placement in placements:
        placed_indexes.setdefault(placement["part_id"], []).append(
            placement.get("tile_index", 0))
    count_bad = []
    for part in parts:
        try:
            expected_count = len(_tiles(part))
        except (KeyError, TypeError, ValueError, OverflowError):
            count_bad.append(part["id"])
            continue
        got = sorted(placed_indexes.get(part["id"], []),
                     key=lambda v: (not isinstance(v, int), v))
        if got != list(range(expected_count)):
            count_bad.append(part["id"])
    if part_ids != placed_ids or count_bad:
        missing = sorted(part_ids - placed_ids)
        extra = sorted(placed_ids - part_ids)
        checks.append(_check("R6-nesting", "fail", "",
                             "Parts list and nesting disagree. Missing from "
                             "nesting: %s. Extra in nesting: %s. Wrong "
                             "placement count or tile indexes: %s."
                             % (", ".join(missing) or "none",
                                ", ".join(extra) or "none",
                                ", ".join(sorted(set(count_bad))) or "none"),
                             "Re-nest so every part appears exactly once "
                             "per tile, with tile_index values in order."))
    else:
        checks.append(_check("R6-nesting", "pass", "",
                             "Parts list and nesting agree one-for-one: every "
                             "part id appears in nesting placements.", ""))
    dry = _dry_fit_dims(parts, thickness) if thickness is not None else None
    if dry is None:
        checks.append(_check("R6-dryfit", "fail", "",
                             "Cannot compute dry-fit dims: side or bottom "
                             "panel missing.",
                             "Include side and bottom panels."))
    elif width is None or depth is None or box_h is None:
        checks.append(_check("R6-dryfit", "fail", "",
                             "Cannot compute dry-fit dims: width, depth, or "
                             "box height missing from params.",
                             "Provide width_in, depth_in, and height_box_in."))
    else:
        diffs = [abs(dry["width_in"] - width),
                 abs(dry["depth_in"] - depth),
                 abs(dry["height_in"] - box_h)]
        if max(diffs) > DRY_FIT_TOL_IN:
            checks.append(_check("R6-dryfit", "fail", "",
                                 "Dry-fit dims disagree with params by more "
                                 "than 1/32 in: parts give %.4f x %.4f x %.4f "
                                 "in (W x D x H), params give %.4f x %.4f x "
                                 "%.4f in."
                                 % (dry["width_in"], dry["depth_in"],
                                    dry["height_in"], width, depth, box_h),
                                 "Fix part dimensions so outside dims agree "
                                 "within 1/32 in."))
        else:
            checks.append(_check("R6-dryfit", "pass", "",
                                 "Dry-fit dims agree with params within "
                                 "1/32 in: %.4f x %.4f x %.4f in (W x D x H)."
                                 % (dry["width_in"], dry["depth_in"],
                                    dry["height_in"]), ""))
    # Bed containment for every placement, tiled tiles included.
    # (Previously any part placed more than once was skipped entirely,
    # so a tiled tile could sit anywhere and still pass.)
    by_id = {p["id"]: p for p in parts}
    outside = []
    for sheet in sheets:
        for placement in sheet.get("placements", []) or []:
            part = by_id.get(placement["part_id"])
            if part is None:
                continue
            dims = _placement_dims(part, placement)
            x = placement.get("x_in", 0.0)
            y = placement.get("y_in", 0.0)
            if (dims is None or isinstance(x, bool)
                    or isinstance(y, bool)
                    or not isinstance(x, (int, float))
                    or not isinstance(y, (int, float))
                    or not math.isfinite(float(x))
                    or not math.isfinite(float(y))):
                outside.append(placement["part_id"])
                continue
            pw, ph = dims
            if (x < 0.0 or y < 0.0
                    or x + pw > BED_W_IN + 1e-9
                    or y + ph > BED_H_IN + 1e-9):
                outside.append(placement["part_id"])
    if outside:
        checks.append(_check("R1-bed", "fail", "",
                             "Placements exceed the 25 x 50 in bed: %s."
                             % ", ".join(sorted(set(outside))),
                             "Re-nest or tile the oversize parts."))
    else:
        checks.append(_check("R1-bed", "pass", "",
                             "All placements fit the 25 x 50 in bed.",
                             ""))
    passed = all(c["status"] != "fail" for c in checks)
    return {"passed": passed, "checks": checks}


# ---------------------------------------------------------------- exports

def _fmt(value):
    text = "%.3f" % float(value)
    return text.rstrip("0").rstrip(".") if "." in text else text


def export_dxf(job):
    """ASCII DXF, inches, layers Profile and Drill. Refuses on failed preflight."""
    stored = (job.get("preflight") or {}).get("passed")
    fresh = check_job_hd520(job)
    if stored is False or not fresh["passed"]:
        raise ValueError("Export refused: preflight did not pass.")
    parts = job.get("parts", []) or []
    params = job.get("params", {}) or {}
    lines = []
    lines.append("0")
    lines.append("SECTION")
    lines.append("2")
    lines.append("TABLES")
    lines.append("0")
    lines.append("TABLE")
    lines.append("2")
    lines.append("LAYER")
    for layer in ("Profile", "Drill"):
        lines.append("0")
        lines.append("LAYER")
        lines.append("2")
        lines.append(layer)
        lines.append("70")
        lines.append("0")
        lines.append("62")
        lines.append("7")
        lines.append("6")
        lines.append("Continuous")
    lines.append("0")
    lines.append("ENDTAB")
    lines.append("0")
    lines.append("ENDSEC")
    lines.append("0")
    lines.append("SECTION")
    lines.append("2")
    lines.append("ENTITIES")
    x_cursor = 0.0
    for part in parts:
        w = part["width_in"]
        h = part["height_in"]
        x0 = x_cursor
        lines.append("0")
        lines.append("TEXT")
        lines.append("8")
        lines.append("Profile")
        lines.append("10")
        lines.append(_fmt(x0))
        lines.append("20")
        lines.append(_fmt(h + 1.0))
        lines.append("40")
        lines.append("0.25")
        lines.append("1")
        lines.append(part["id"])
        corners = [(x0, 0.0), (x0 + w, 0.0), (x0 + w, h), (x0, h)]
        for i in range(4):
            x1, y1 = corners[i]
            x2, y2 = corners[(i + 1) % 4]
            lines.extend(["0", "LINE", "8", "Profile",
                          "10", _fmt(x1), "20", _fmt(y1),
                          "11", _fmt(x2), "21", _fmt(y2)])
        if part["id"] in ("side-left", "side-right"):
            for y in (5.0, h - 5.0):
                if 0.0 < y < h:
                    lines.extend(["0", "POINT", "8", "Drill",
                                  "10", _fmt(x0 + 2.0), "20", _fmt(y)])
        x_cursor += w + 1.0
    lines.append("0")
    lines.append("ENDSEC")
    lines.append("0")
    lines.append("EOF")
    _ = params
    return "\n".join(lines) + "\n"


def export_cut_list(job):
    """Monochrome printable plain text cut list. Refuses on failed preflight."""
    stored = (job.get("preflight") or {}).get("passed")
    fresh = check_job_hd520(job)
    if stored is False or not fresh["passed"]:
        raise ValueError("Export refused: preflight did not pass.")
    params = job.get("params", {}) or {}
    parts = job.get("parts", []) or []
    nesting = job.get("nesting", {}) or {}
    sheets = nesting.get("sheets", []) or []
    setup_of = {}
    for sheet in sheets:
        for placement in sheet.get("placements", []) or []:
            setup_of.setdefault(placement["part_id"], sheet["sheet_id"])
    out = []
    out.append("Tide & Tool Handyman Services")
    out.append("Cut List")
    out.append("Job: %s" % job.get("job_id", ""))
    out.append("Cabinet: %s in wide, %s in box height, %s in deep, layout %s"
               % (_fmt(params.get("width_in", 0)),
                  _fmt(params.get("height_box_in", 0)),
                  _fmt(params.get("depth_in", 0)),
                  params.get("layout", "")))
    out.append("Material: %s, %s in thick"
               % (params.get("material_name", ""),
                  _fmt(params.get("material_thickness_in", 0))))
    if params.get("layout") == "wall":
        out.append("Wall cabinet: hangs, no toe kick.")
    else:
        out.append("Toe kick: separate ladder-pack base, %s in high, %s in board, "
                   "recess %s in PROVISIONAL (one pantry note only, not a "
                   "confirmed general default)"
                   % (_fmt(params.get("toe_kick_height_in",
                                      DEFAULT_TOE_KICK_HEIGHT_IN)),
                      _fmt(DEFAULT_TOE_KICK_BOARD_IN),
                      _fmt(params.get("toe_kick_recess_in",
                                      PROVISIONAL_TOE_KICK_RECESS_IN))))
    out.append("Pin grid: %s"
               % ("ON, 5 mm grid" if params.get("pin_grid_enabled")
                  else "OFF"))
    out.append("Machine: Shark HD520, 25 x 50 in bed, Next Wave .tap post")
    out.append("Setups (nested sheets): %d" % len(sheets))
    out.append("")
    out.append("Qty  Part                          W (in)    H (in)    Setup")
    out.append("---  ----------------------------  --------  --------  -----")
    for part in parts:
        out.append("%-4d %-28s  %-8s  %-8s  %s"
                   % (part["quantity"], part["name"][:28],
                      _fmt(part["width_in"]), _fmt(part["height_in"]),
                      setup_of.get(part["id"], "")))
    out.append("")
    out.append("Notes:")
    out.append("- Panels are cut from the material listed above.")
    out.append("- Tiled parts are cut in tile_index order and joined on "
               "index marks.")
    out.append("- Spoilboard 0.75 in, touch puck Z-zero 0.37 in, safe Z "
               "1.5 in.")
    out.append("- Workholding: painter's tape primary, clamps backup only.")
    return "\n".join(out) + "\n"


def _front_rects(params):
    """Front-elevation rectangles (inches) from the layout rules.

    Returns (rects, toe_h): rects are (x, y, w, h, label) with y down
    from the top of the box; toe_h is 0 for walls, else the toe-kick
    height. Rect sizes match the front parts _build_parts emits.
    """
    width = params["width_in"]
    box_h = params["height_box_in"]
    layout = params["layout"]
    front_w = width - 0.125
    rects = []
    if layout == "doors":
        door_w = (width - 0.25) / 2.0
        door_h = box_h - 0.25
        rects.append((0.125, 0.125, door_w, door_h, "door left"))
        rects.append((0.125 + door_w, 0.125, door_w, door_h, "door right"))
    elif layout == "drawer-bank":
        count = params["drawer_count"]
        front_h = (box_h - 0.5) / float(count)
        for i in range(count):
            rects.append((0.0625, i * front_h, front_w, front_h,
                          "drawer %d" % (i + 1)))
    elif layout in ("drawers-over-doors", "drawer-over-door", "sink-base"):
        front_h = box_h / 3.0
        door_h = box_h - front_h - 0.5
        label = "drawer" if layout != "sink-base" else "false front"
        rects.append((0.0625, 0.0, front_w, front_h, label))
        if layout == "drawer-over-door":
            rects.append((0.0625, front_h, front_w, door_h, "door"))
        else:
            door_w = (width - 0.25) / 2.0
            rects.append((0.125, front_h, door_w, door_h, "door left"))
            rects.append((0.125 + door_w, front_h, door_w, door_h,
                          "door right"))
    elif layout == "pantry":
        door_w = (width - 0.25) / 2.0
        door_h = box_h - 0.25
        rects.append((0.125, 0.125, door_w, door_h, "door left"))
        rects.append((0.125 + door_w, 0.125, door_w, door_h, "door right"))
    elif layout == "wall":
        door_h = box_h - 0.25
        if width < 24.0:
            rects.append((0.0625, 0.125, front_w, door_h, "door"))
        else:
            door_w = (width - 0.25) / 2.0
            rects.append((0.125, 0.125, door_w, door_h, "door left"))
            rects.append((0.125 + door_w, 0.125, door_w, door_h,
                          "door right"))
    toe_h = 0.0 if layout == "wall" else params.get(
        "toe_kick_height_in", DEFAULT_TOE_KICK_HEIGHT_IN)
    return rects, toe_h


def export_front_svg(job):
    """Front-elevation SVG of the generated cabinet (schematic).

    Drawn from the job's params and layout rules, so rect sizes match
    the front parts in the parts list. Monochrome, no external refs,
    no user text. Gaps and hardware are not shown.
    """
    params = job.get("params", {}) or {}
    width = params["width_in"]
    box_h = params["height_box_in"]
    layout = params.get("layout", "")
    rects, toe_h = _front_rects(params)
    total_h = box_h + toe_h
    s = 10.0
    ox, oy = 34.0, 20.0
    vb_w = width * s + 42.0
    vb_h = total_h * s + 28.0
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %s %s" '
           'role="img" aria-label="Front view of the generated cabinet">'
           % (_fmt(vb_w), _fmt(vb_h))]
    out.append('<title>Front view: %s, %s x %s in</title>'
               % (_xml(layout), _fmt(width), _fmt(box_h)))
    out.append('<text x="%s" y="%s" font-size="11" text-anchor="middle" '
               'fill="#1a1a1a">%s in wide</text>'
               % (_fmt(ox + width * s / 2.0), _fmt(oy - 6.0), _fmt(width)))
    cy = oy + box_h * s / 2.0
    out.append('<text x="10" y="%s" font-size="11" text-anchor="middle" '
               'fill="#1a1a1a" transform="rotate(-90 10 %s)">%s in box '
               'height</text>' % (_fmt(cy), _fmt(cy), _fmt(box_h)))
    if layout == "wall":
        yline = oy - 8.0
        out.append('<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="#1a1a1a" '
                   'stroke-width="1.5"/>'
                   % (_fmt(ox - 6.0), _fmt(yline),
                      _fmt(ox + width * s + 6.0), _fmt(yline)))
        for frac in (0.25, 0.75):
            tx = ox + width * s * frac
            out.append('<line x1="%s" y1="%s" x2="%s" y2="%s" '
                       'stroke="#1a1a1a" stroke-width="1.5"/>'
                       % (_fmt(tx), _fmt(yline - 3.0),
                          _fmt(tx), _fmt(yline + 3.0)))
    out.append('<rect x="%s" y="%s" width="%s" height="%s" fill="#ffffff" '
               'stroke="#1a1a1a" stroke-width="2"/>'
               % (_fmt(ox), _fmt(oy), _fmt(width * s), _fmt(box_h * s)))
    for (x, y, w, h, label) in rects:
        rx, ry = ox + x * s, oy + y * s
        rw, rh = w * s, h * s
        out.append('<rect x="%s" y="%s" width="%s" height="%s" '
                   'fill="#f4f4f2" stroke="#1a1a1a" stroke-width="1.5">'
                   '<title>%s</title></rect>'
                   % (_fmt(rx), _fmt(ry), _fmt(rw), _fmt(rh), label))
        if label == "door left":
            out.append('<circle cx="%s" cy="%s" r="3" fill="#1a1a1a"/>'
                       % (_fmt(rx + rw - 10.0), _fmt(ry + rh / 2.0)))
        elif label == "door right":
            out.append('<circle cx="%s" cy="%s" r="3" fill="#1a1a1a"/>'
                       % (_fmt(rx + 10.0), _fmt(ry + rh / 2.0)))
        elif label == "door":
            out.append('<circle cx="%s" cy="%s" r="3" fill="#1a1a1a"/>'
                       % (_fmt(rx + rw / 2.0), _fmt(ry + rh / 2.0)))
        else:
            bar_w = min(40.0, rw / 2.0)
            out.append('<rect x="%s" y="%s" width="%s" height="3" '
                       'fill="#1a1a1a"/>'
                       % (_fmt(rx + rw / 2.0 - bar_w / 2.0),
                          _fmt(ry + rh / 2.0 - 1.5), _fmt(bar_w)))
    if toe_h > 0:
        ty = oy + box_h * s
        out.append('<rect x="%s" y="%s" width="%s" height="%s" '
                   'fill="#e8e8e8" stroke="#1a1a1a" stroke-width="1.5"/>'
                   % (_fmt(ox), _fmt(ty), _fmt(width * s),
                      _fmt(toe_h * s)))
        if toe_h * s >= 16.0:
            out.append('<text x="%s" y="%s" font-size="11" '
                       'text-anchor="middle" fill="#1a1a1a">toe kick '
                       '(separate ladder pack)</text>'
                       % (_fmt(ox + width * s / 2.0),
                          _fmt(ty + toe_h * s / 2.0 + 4.0)))
    out.append('</svg>')
    return "\n".join(out) + "\n"


def export_part_svgs(job):
    """One SVG per part (schematic).

    Each drawing shows the part at its true proportions (scaled to
    fit), its size, material, thickness, grain direction, and edge
    banding as text. Edge positions are not drawn: the part record
    names the banded edge but not its orientation on the panel.
    Returns a list of {part_id, name, svg}.
    """
    drawings = []
    for part in job.get("parts", []) or []:
        w = part["width_in"]
        h = part["height_in"]
        s = min(10.0, 420.0 / w, 300.0 / h)
        ox, oy = 40.0, 28.0
        vb_w = w * s + 48.0
        vb_h = h * s + 56.0
        out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %s %s" '
               'role="img" aria-label="Drawing of %s">'
               % (_fmt(vb_w), _fmt(vb_h), _xml(part["name"]))]
        out.append('<title>%s: %s x %s in</title>'
                   % (_xml(part["name"]), _fmt(w), _fmt(h)))
        out.append('<text x="%s" y="%s" font-size="11" text-anchor="middle" '
                   'fill="#1a1a1a">%s in wide</text>'
                   % (_fmt(ox + w * s / 2.0), _fmt(oy - 8.0), _fmt(w)))
        cy = oy + h * s / 2.0
        out.append('<text x="12" y="%s" font-size="11" text-anchor="middle" '
                   'fill="#1a1a1a" transform="rotate(-90 12 %s)">%s in tall'
                   '</text>' % (_fmt(cy), _fmt(cy), _fmt(h)))
        out.append('<rect x="%s" y="%s" width="%s" height="%s" '
                   'fill="#f4f4f2" stroke="#1a1a1a" stroke-width="1.5"/>'
                   % (_fmt(ox), _fmt(oy), _fmt(w * s), _fmt(h * s)))
        for i in range(1, 6):
            if part["grain"] == "vertical":
                gx = ox + w * s * i / 6.0
                out.append('<line x1="%s" y1="%s" x2="%s" y2="%s" '
                           'stroke="#bbbbbb" stroke-width="1"/>'
                           % (_fmt(gx), _fmt(oy), _fmt(gx),
                              _fmt(oy + h * s)))
            else:
                gy = oy + h * s * i / 6.0
                out.append('<line x1="%s" y1="%s" x2="%s" y2="%s" '
                           'stroke="#bbbbbb" stroke-width="1"/>'
                           % (_fmt(ox), _fmt(gy),
                              _fmt(ox + w * s), _fmt(gy)))
        out.append('<text x="%s" y="%s" font-size="11" fill="#1a1a1a">'
                   '%s, %s in thick, grain %s, edge banding: %s, qty %d'
                   '</text>'
                   % (_fmt(ox), _fmt(oy + h * s + 20.0), _xml(part["material"]),
                      _fmt(part["thickness_in"]), _xml(part["grain"]),
                      _xml(part["edge_banding"]), part["quantity"]))
        out.append('</svg>')
        drawings.append({"part_id": part["id"], "name": part["name"],
                         "svg": "\n".join(out) + "\n"})
    return drawings


def export_sheet_svgs(job):
    """One SVG per nesting sheet, from placements (schematic).

    Each placement rect is the placed tile's actual size; labels
    show part id, R when rotated, T<n> for tile index. Monochrome.
    """
    parts = {p["id"]: p for p in (job.get("parts", []) or [])}
    svgs = []
    sheets = ((job.get("nesting", {}) or {}).get("sheets", []) or [])
    for sheet in sheets:
        bw = sheet.get("bed_w_in", BED_W_IN)
        bh = sheet.get("bed_h_in", BED_H_IN)
        s = 10.0
        out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %s %s" '
               'role="img" aria-label="Nesting sheet %s">'
               % (_fmt(bw * s + 8.0), _fmt(bh * s + 8.0),
                  _xml(sheet.get("sheet_id", "")))]
        out.append('<title>%s: %d placements</title>'
                   % (_xml(sheet.get("sheet_id", "")),
                      len(sheet.get("placements", []) or [])))
        out.append('<rect x="4" y="4" width="%s" height="%s" fill="#ffffff" '
                   'stroke="#1a1a1a" stroke-width="2"/>'
                   % (_fmt(bw * s), _fmt(bh * s)))
        for pl in sheet.get("placements", []) or []:
            part = parts.get(pl["part_id"])
            if part is None:
                continue
            tiles = _tiles(part)
            ti = pl.get("tile_index", 0)
            if ti >= len(tiles):
                continue
            tw, th, _rotated, _idx = tiles[ti]
            x = 4.0 + pl["x_in"] * s
            y = 4.0 + pl["y_in"] * s
            w, h = tw * s, th * s
            out.append('<rect x="%s" y="%s" width="%s" height="%s" '
                       'fill="#f4f4f2" stroke="#1a1a1a" '
                       'stroke-width="1"><title>%s</title></rect>'
                       % (_fmt(x), _fmt(y), _fmt(w), _fmt(h),
                          _xml(pl["part_id"])))
            if w >= 42.0 and h >= 14.0:
                label = pl["part_id"]
                if pl.get("rotated"):
                    label += " R"
                if ti > 0:
                    label += " T%d" % ti
                out.append('<text x="%s" y="%s" font-size="10" '
                           'fill="#1a1a1a">%s</text>'
                           % (_fmt(x + 3.0), _fmt(y + 13.0), _xml(label)))
        out.append('</svg>')
        svgs.append("\n".join(out) + "\n")
    return svgs


# ---------------------------------------------------------------- generate

_NUMERIC_FIELDS = ("width_in", "height_box_in", "overall_height_in",
                   "depth_in", "material_thickness_in",
                   "toe_kick_height_in", "toe_kick_recess_in",
                   "slide_clearance_in")
_BOOLEAN_FIELDS = ("pin_grid_enabled", "thickness_is_nominal",
                   "tabs_enabled", "clamps_enabled")


def _validate_param_types(raw):
    """Reject non-numeric, NaN/infinite, and mistyped params early.

    Without this, a string width crashed with TypeError (HTTP 500 on
    the servers), NaN sailed through every comparison in preflight
    and was exported into the DXF, and the string "false" counted as
    True for the boolean toggles.
    """
    for field in _NUMERIC_FIELDS:
        value = raw.get(field)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("%s must be a number" % field)
        if not math.isfinite(float(value)):
            raise ValueError("%s must be a finite number" % field)
    for field in _BOOLEAN_FIELDS:
        value = raw.get(field)
        if value is not None and not isinstance(value, bool):
            raise ValueError("%s must be true or false" % field)
    if raw.get("material_name") is not None \
            and not isinstance(raw.get("material_name"), str):
        raise ValueError("material_name must be a string")
    count = raw.get("drawer_count")
    if count is not None:
        if isinstance(count, bool) or not isinstance(count, (int, float)) \
                or not math.isfinite(float(count)) \
                or int(count) != count:
            raise ValueError("drawer_count must be a positive integer")
        raw["drawer_count"] = int(count)


def generate_cabinet(params):
    """Build a cabinet job from plain params. See module docstring."""
    if not isinstance(params, dict):
        raise ValueError("params must be a dict")
    raw = dict(params)
    provider = raw.get("provider", "local")
    if provider not in ("meta", "local"):
        raise ValueError("provider must be 'meta' or 'local'")
    _validate_param_types(raw)
    if provider == "meta" and raw.get("base_url") is not None:
        # Never send the Meta key to a caller-supplied URL: a token
        # holder who does not know the key could otherwise point
        # base_url at their own server and collect the Bearer key.
        if str(raw["base_url"]).rstrip("/") != META_BASE_URL:
            raise ValueError("base_url must be %s" % META_BASE_URL)

    # Brief parsing: explicit params always win over parsed params.
    # Layout and width are validated AFTER this block, so a brief
    # alone can supply them (the "let the description decide" path).
    brief_text = raw.get("brief_text")
    if brief_text:
        if provider == "meta":
            api_key = (os.environ.get("META_API_KEY")
                       or os.environ.get("META_MODEL_API_KEY"))
            if not api_key:
                raise ValueError(
                    "Meta provider requested but no Meta API key is "
                    "configured. Set META_API_KEY and retry; no silent "
                    "fallback to local is made.")
            parsed = parse_brief_meta(brief_text, api_key,
                                      raw.get("base_url", META_BASE_URL),
                                      raw.get("model", META_MODEL))
        else:
            parsed = parse_brief_local(brief_text)
        merged = dict(parsed)
        for key, value in raw.items():
            if key not in ("brief_text", "provider", "base_url", "model"):
                merged[key] = value
        raw = merged
        # The parser (regex or model) can return mistyped values too.
        _validate_param_types(raw)
    layout = raw.get("layout")
    if layout not in LAYOUTS:
        raise ValueError("layout must be one of: %s" % ", ".join(LAYOUTS))
    if raw.get("width_in") is None:
        raise ValueError("width_in is required")

    if layout == "pantry" and raw.get("height_box_in") is None:
        if raw.get("overall_height_in") is not None:
            toe = raw.get("toe_kick_height_in", DEFAULT_TOE_KICK_HEIGHT_IN)
            raw["height_box_in"] = (raw["overall_height_in"] - toe)
        else:
            raise ValueError(
                "Pantry height is required. Provide height_box_in in inches. "
                "No default pantry envelope is used.")

    provisional = []
    if raw.get("toe_kick_recess_in") is None:
        raw["toe_kick_recess_in"] = PROVISIONAL_TOE_KICK_RECESS_IN
    provisional.append("toe_kick_recess_in")
    slide_defaulted = raw.get("slide_clearance_in") is None
    if slide_defaulted:
        raw["slide_clearance_in"] = PROTOTYPE_SLIDE_CLEARANCE_IN
        provisional.append("slide_clearance_in")
    if raw.get("thickness_is_nominal"):
        provisional.append("material_thickness_in")

    box_h = raw.get("height_box_in", DEFAULT_BOX_HEIGHT_IN)
    toe_h = raw.get("toe_kick_height_in", DEFAULT_TOE_KICK_HEIGHT_IN)
    resolved = {
        "width_in": raw["width_in"],
        "height_box_in": box_h,
        "overall_height_in": raw.get("overall_height_in", box_h + toe_h),
        "depth_in": raw.get("depth_in", DEFAULT_DEPTH_IN),
        "layout": layout,
        "material_thickness_in": raw.get("material_thickness_in",
                                         DEFAULT_THICKNESS_IN),
        "material_name": raw.get("material_name", "PureBond birch"),
        "pin_grid_enabled": bool(raw.get("pin_grid_enabled", False)),
        "drawer_count": int(raw.get("drawer_count", 2)),
        "toe_kick_height_in": toe_h,
        "toe_kick_recess_in": raw["toe_kick_recess_in"],
        "slide_clearance_in": raw["slide_clearance_in"],
        "thickness_is_nominal": bool(raw.get("thickness_is_nominal", False)),
        "tabs_enabled": bool(raw.get("tabs_enabled", False)),
        "provisional": provisional,
    }
    for key in ("clamps_enabled",):
        if key in raw:
            resolved[key] = raw[key]
    if layout == "wall":
        # Wall cabinets hang: no toe kick, so overall height is box
        # height and the toe-kick values are not applicable.
        resolved["overall_height_in"] = box_h
        resolved["toe_kick_height_in"] = 0.0
        resolved["toe_kick_recess_in"] = 0.0
        if "toe_kick_recess_in" in resolved["provisional"]:
            resolved["provisional"].remove("toe_kick_recess_in")
    if resolved["width_in"] <= 0 or resolved["depth_in"] <= 0 \
            or resolved["height_box_in"] <= 0 \
            or resolved["material_thickness_in"] <= 0 \
            or resolved["drawer_count"] < 1:
        raise ValueError("width, depth, box height, thickness, and drawer "
                         "count must be positive")

    parts = _build_parts(resolved)
    bad_parts = [p["id"] for p in parts
                 if not (math.isfinite(p["width_in"])
                         and math.isfinite(p["height_in"])
                         and math.isfinite(p["thickness_in"]))
                 or p["width_in"] <= 0 or p["height_in"] <= 0
                 or p["thickness_in"] <= 0]
    if bad_parts:
        raise ValueError(
            "These dimensions produce a non-positive part (%s). Check "
            "width, depth, box height, thickness, and drawer count: a "
            "cabinet this small cannot contain the carcass and drawer "
            "boxes the layout needs." % ", ".join(bad_parts[:3]))
    nesting = _nest_parts(parts)
    job = {
        "job_id": "job-" + uuid.uuid4().hex[:12],
        "params": resolved,
        "parts": parts,
        "nesting": nesting,
        "provider_record": {
            "provider": provider,
            "model": META_MODEL if provider == "meta" else "none",
        },
    }
    if raw.get("job_name"):
        job["job_name"] = raw["job_name"]
    if raw.get("clamps_enabled"):
        job["clamps_enabled"] = True
    preflight = check_job_hd520(job)
    job["preflight"] = preflight
    if preflight["passed"]:
        job["dxf_text"] = export_dxf(job)
        job["cut_list_text"] = export_cut_list(job)
        job["preview_svg"] = export_front_svg(job)
        job["sheet_svgs"] = export_sheet_svgs(job)
        job["part_svgs"] = export_part_svgs(job)
    else:
        job["dxf_text"] = ""
        job["cut_list_text"] = ""
        job["preview_svg"] = ""
        job["sheet_svgs"] = []
        job["part_svgs"] = []
    return job


# ---------------------------------------------------------------- brief parsing

_NUMBER = r"(\d+(?:\.\d+)?)"

def _find_number(pattern, text):
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1))
        except (IndexError, ValueError):
            return None
    return None


def parse_brief_local(brief_text):
    """Regex/keyword brief parser. No model is used here."""
    if not isinstance(brief_text, str):
        raise ValueError("brief_text must be a string")
    text = brief_text.lower()
    params = {}
    width = _find_number(r"width[^0-9]*" + _NUMBER, text)
    if width is None:
        width = _find_number(_NUMBER + r"\s*(?:in|inch|inches|\")\s*wide", text)
    if width is None:
        width = _find_number(_NUMBER + r"\s*wide", text)
    if width is not None:
        params["width_in"] = width
    box_h = _find_number(r"box[^0-9]*height[^0-9]*" + _NUMBER, text)
    if box_h is None:
        box_h = _find_number(r"box[^0-9]*" + _NUMBER, text)
    if box_h is None:
        box_h = _find_number(_NUMBER + r"\s*(?:in|inch|inches|\")\s*tall", text)
    if box_h is None:
        box_h = _find_number(_NUMBER + r"\s*tall", text)
    if box_h is None:
        box_h = _find_number(_NUMBER + r"\s*(?:in|inch|inches|\")?\s*high", text)
    if box_h is None:
        box_h = _find_number(r"height[^0-9]*" + _NUMBER, text)
    if box_h is not None:
        params["height_box_in"] = box_h
    depth = _find_number(r"depth[^0-9]*" + _NUMBER, text)
    if depth is None:
        depth = _find_number(_NUMBER + r"\s*(?:in|inch|inches|\")\s*deep", text)
    if depth is None:
        depth = _find_number(_NUMBER + r"\s*deep", text)
    if depth is not None:
        params["depth_in"] = depth
    if "wall" in text:
        params["layout"] = "wall"
    elif "drawer bank" in text or "drawer-bank" in text or "drawerbank" in text:
        params["layout"] = "drawer-bank"
    elif "drawer over door" in text or "drawer on top" in text:
        params["layout"] = "drawer-over-door"
    elif "drawers over doors" in text or "drawers-over-doors" in text:
        params["layout"] = "drawers-over-doors"
    elif "sink" in text:
        params["layout"] = "sink-base"
    elif "pantry" in text:
        params["layout"] = "pantry"
    elif "drawer" in text:
        params["layout"] = "drawer-bank"
    elif "door" in text:
        params["layout"] = "doors"
    if "purebond" in text:
        params["material_name"] = "PureBond birch"
        if "3/4" in text or "0.703" in text:
            params["material_thickness_in"] = 0.703
        elif "1/2" in text or "0.453" in text:
            params["material_thickness_in"] = 0.453
        elif "0.625" in text:
            params["material_thickness_in"] = 0.625
    elif "0.625" in text:
        params["material_thickness_in"] = 0.625
    elif "0.703" in text:
        params["material_thickness_in"] = 0.703
    if "pin grid on" in text or "pin grid enabled" in text:
        params["pin_grid_enabled"] = True
    elif "pin grid off" in text or "pin grid disabled" in text \
            or "no pin grid" in text:
        params["pin_grid_enabled"] = False
    count = _find_number(r"(\d+)\s*-?\s*drawer", text)
    if count is not None and "drawer" in text:
        # Only treat a leading count as drawer_count for drawer-bank briefs.
        if params.get("layout") == "drawer-bank":
            params["drawer_count"] = int(count)
    return params


def _build_meta_request(brief_text, base_url, model):
    system = (
        "You are a cabinet parameter extractor. Reply with JSON only, no "
        "other text. Keys: width_in, height_box_in, depth_in, layout "
        "(one of doors, drawers-over-doors, drawer-over-door, drawer-bank, "
        "sink-base, pantry, wall), material_thickness_in, material_name, "
        "pin_grid_enabled, drawer_count. Use numbers for dimensions in "
        "inches."
    )
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": brief_text},
        ],
    }
    url = base_url.rstrip("/") + "/chat/completions"
    return url, payload


def parse_brief_meta(brief_text, api_key, base_url, model):
    """OpenAI-compatible Meta call via urllib only, 30s timeout.

    On any failure this raises. It never retries on another provider,
    never falls back to local parsing, and never logs the key.
    """
    if not api_key:
        raise ValueError("api_key is required for the Meta provider")
    url, payload = _build_meta_request(brief_text, base_url, model)
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + api_key})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except Exception as exc:
        raise RuntimeError("Meta brief parse failed: %s"
                           % exc.__class__.__name__) from exc
    try:
        parsed_body = json.loads(body)
        content = parsed_body["choices"][0]["message"]["content"]
        try:
            result = json.loads(content)
        except ValueError:
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if not match:
                raise ValueError("No JSON object in model reply")
            result = json.loads(match.group(0))
        if not isinstance(result, dict):
            raise ValueError("Model reply was not a JSON object")
        return result
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        raise RuntimeError("Meta brief parse returned an unusable reply") \
            from exc


# ---------------------------------------------------------------- secrets

def scan_for_secrets(text, secrets):
    """Return the secrets found as substrings of text; empty means clean."""
    if not text or not secrets:
        return []
    found = []
    for secret in secrets:
        if secret and secret in text and secret not in found:
            found.append(secret)
    return found
