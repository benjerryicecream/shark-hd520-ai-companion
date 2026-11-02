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
LAYOUTS = ("doors", "drawers-over-doors", "drawer-bank", "sink-base", "pantry", "wall")

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
                pw, ph = part["width_in"], part["height_in"]
                if placement.get("rotated"):
                    pw, ph = ph, pw
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
    if part_ids != placed_ids:
        missing = sorted(part_ids - placed_ids)
        extra = sorted(placed_ids - part_ids)
        checks.append(_check("R6-nesting", "fail", "",
                             "Parts list and nesting disagree. Missing from "
                             "nesting: %s. Extra in nesting: %s."
                             % (", ".join(missing) or "none",
                                ", ".join(extra) or "none"),
                             "Re-nest so every part id appears in nesting."))
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
    # Bed containment for untiled placements.
    by_id = {p["id"]: p for p in parts}
    counts = {}
    for placement in placements:
        counts[placement["part_id"]] = counts.get(placement["part_id"], 0) + 1
    outside = []
    for sheet in sheets:
        for placement in sheet.get("placements", []) or []:
            if counts.get(placement["part_id"], 0) > 1:
                continue
            part = by_id.get(placement["part_id"])
            if part is None:
                continue
            pw, ph = part["width_in"], part["height_in"]
            if placement.get("rotated"):
                pw, ph = ph, pw
            if (placement.get("x_in", 0.0) + pw > BED_W_IN + 1e-9
                    or placement.get("y_in", 0.0) + ph > BED_H_IN + 1e-9):
                outside.append(placement["part_id"])
    if outside:
        checks.append(_check("R1-bed", "fail", "",
                             "Placements exceed the 25 x 50 in bed: %s."
                             % ", ".join(sorted(set(outside))),
                             "Re-nest or tile the oversize parts."))
    else:
        checks.append(_check("R1-bed", "pass", "",
                             "All untiled placements fit the 25 x 50 in bed.",
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


# ---------------------------------------------------------------- generate

def generate_cabinet(params):
    """Build a cabinet job from plain params. See module docstring."""
    if not isinstance(params, dict):
        raise ValueError("params must be a dict")
    raw = dict(params)
    layout = raw.get("layout")
    if layout not in LAYOUTS:
        raise ValueError("layout must be one of: %s" % ", ".join(LAYOUTS))
    if raw.get("width_in") is None:
        raise ValueError("width_in is required")
    provider = raw.get("provider", "local")
    if provider not in ("meta", "local"):
        raise ValueError("provider must be 'meta' or 'local'")

    # Brief parsing: explicit params always win over parsed params.
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
        layout = raw.get("layout", layout)

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
    nesting = _nest_parts(parts)
    job = {
        "job_id": "job-" + uuid.uuid4().hex[:12],
        "params": resolved,
        "parts": parts,
        "nesting": nesting,
        "provider_record": {
            "provider": provider,
            "model": META_MODEL if provider == "meta" else "local",
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
    else:
        job["dxf_text"] = ""
        job["cut_list_text"] = ""
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
    if box_h is not None:
        params["height_box_in"] = box_h
    depth = _find_number(r"depth[^0-9]*" + _NUMBER, text)
    if depth is None:
        depth = _find_number(_NUMBER + r"\s*(?:in|inch|inches|\")\s*deep", text)
    if depth is not None:
        params["depth_in"] = depth
    if "wall" in text:
        params["layout"] = "wall"
    elif "drawer bank" in text or "drawer-bank" in text or "drawerbank" in text:
        params["layout"] = "drawer-bank"
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
        "(one of doors, drawers-over-doors, drawer-bank, sink-base, "
        "pantry, wall), material_thickness_in, material_name, "
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
