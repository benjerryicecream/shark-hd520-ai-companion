"""Tests for the Shark HD520 cabinet generator engine.

Run from the app root: python3 tests/test_engine.py
Standard library only (unittest).
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import (  # noqa: E402
    check_job_hd520,
    export_cut_list,
    export_dxf,
    generate_cabinet,
    load_tools,
    parse_brief_local,
    parse_brief_meta,
    scan_for_secrets,
)
from engine.core import _build_meta_request  # noqa: E402


def demo_job():
    return generate_cabinet({"width_in": 34, "layout": "drawer-bank"})


def dxf_rectangles(dxf_text):
    """Parse DXF TEXT labels and following LINE rectangles.

    Reads proper code/value pairs (a value of "0" is not an entity
    boundary; only code "0" is). Returns {part_id: (width, height)}
    computed from line extents.
    """
    lines = [ln.strip() for ln in dxf_text.splitlines()]
    pairs = [(lines[i], lines[i + 1]) for i in range(0, len(lines) - 1, 2)]
    rects = {}
    current = None
    points = []
    entity = None
    vals = {}
    for code, value in pairs:
        if code == "0":
            if entity == "LINE" and current is not None and "10" in vals:
                points.append((vals["10"], vals["20"]))
                points.append((vals["11"], vals["21"]))
            entity = value
            vals = {}
            if entity == "TEXT":
                if current is not None and points:
                    xs = [p[0] for p in points]
                    ys = [p[1] for p in points]
                    rects[current] = (max(xs) - min(xs), max(ys) - min(ys))
                points = []
                current = None
            continue
        if entity == "TEXT" and code == "1":
            current = value
        elif entity == "LINE" and code in ("10", "20", "11", "21"):
            vals[code] = float(value)
    if entity == "LINE" and current is not None and "10" in vals:
        points.append((vals["10"], vals["20"]))
        points.append((vals["11"], vals["21"]))
    if current is not None and points:
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        rects[current] = (max(xs) - min(xs), max(ys) - min(ys))
    return rects


class TestDemo(unittest.TestCase):
    def test_demo_16_parts_10_sheets(self):
        job = demo_job()
        self.assertTrue(job["preflight"]["passed"])
        self.assertEqual(len(job["parts"]), 16)
        self.assertEqual(len(job["nesting"]["sheets"]), 10)

    def test_demo_defaults_and_provisional_flags(self):
        job = demo_job()
        params = job["params"]
        self.assertEqual(params["height_box_in"], 30)
        self.assertEqual(params["overall_height_in"], 34.5)
        self.assertEqual(params["depth_in"], 24)
        self.assertEqual(params["material_thickness_in"], 0.453)
        self.assertFalse(params["pin_grid_enabled"])
        self.assertIn("toe_kick_recess_in", params["provisional"])
        self.assertEqual(params["toe_kick_recess_in"], 3.0)
        self.assertIn("slide_clearance_in", params["provisional"])
        self.assertEqual(params["slide_clearance_in"], 0.5)
        self.assertEqual(job["provider_record"]["provider"], "local")

    def test_parts_nesting_one_for_one(self):
        job = demo_job()
        part_ids = {p["id"] for p in job["parts"]}
        placed_ids = set()
        for sheet in job["nesting"]["sheets"]:
            for placement in sheet["placements"]:
                placed_ids.add(placement["part_id"])
                self.assertGreaterEqual(placement["x_in"], 0.0)
                self.assertGreaterEqual(placement["y_in"], 0.0)
                self.assertLessEqual(placement["x_in"], 25.0)
                self.assertLessEqual(placement["y_in"], 50.0)
        self.assertEqual(part_ids, placed_ids)

    def test_dry_fit_three_ways_within_1_32(self):
        job = demo_job()
        params = job["params"]
        t = params["material_thickness_in"]
        tol = 1.0 / 32.0
        # Way 1: params.
        w1 = params["width_in"]
        d1 = params["depth_in"]
        h1 = params["height_box_in"]
        # Way 2: parts list (side + bottom).
        by_id = {p["id"]: p for p in job["parts"]}
        w2 = by_id["bottom"]["width_in"] + 2.0 * t
        d2 = by_id["side-left"]["width_in"]
        h2 = by_id["side-left"]["height_in"]
        # Way 3: DXF rectangles for the same named parts.
        rects = dxf_rectangles(job["dxf_text"])
        self.assertIn("bottom", rects)
        self.assertIn("side-left", rects)
        w3 = rects["bottom"][0] + 2.0 * t
        d3 = rects["side-left"][0]
        h3 = rects["side-left"][1]
        for a, b in ((w1, w2), (w1, w3), (d1, d2), (d1, d3), (h1, h2), (h1, h3)):
            self.assertLessEqual(abs(a - b), tol)
        # Nesting way: every part id in nesting is already covered by
        # the one-for-one test; here check the nesting sheets reference
        # the same side and bottom ids used above.
        placed = {p["part_id"] for s in job["nesting"]["sheets"]
                  for p in s["placements"]}
        self.assertIn("bottom", placed)
        self.assertIn("side-left", placed)

    def test_dxf_layers_and_ascii(self):
        job = demo_job()
        dxf = job["dxf_text"]
        self.assertIn("Profile", dxf)
        self.assertIn("Drill", dxf)
        dxf.encode("ascii")
        self.assertNotIn("sk-", dxf)

    def test_cut_list_header_and_no_em_dash(self):
        job = demo_job()
        text = job["cut_list_text"]
        self.assertIn("Tide & Tool", text)
        self.assertIn("Setups", text)
        self.assertNotIn("\u2014", text)
        self.assertNotIn("\u2014", job["dxf_text"])


class TestPreflight(unittest.TestCase):
    def test_64_wide_fails_and_export_refused(self):
        job = generate_cabinet({"width_in": 64, "layout": "drawer-bank"})
        self.assertFalse(job["preflight"]["passed"])
        self.assertEqual(job["dxf_text"], "")
        self.assertEqual(job["cut_list_text"], "")
        with self.assertRaises(ValueError):
            export_dxf(job)
        with self.assertRaises(ValueError):
            export_cut_list(job)

    def test_nominal_thickness_warns_and_exports(self):
        job = generate_cabinet({"width_in": 34, "layout": "drawer-bank",
                                "material_thickness_in": 0.750,
                                "thickness_is_nominal": True})
        self.assertTrue(job["preflight"]["passed"])
        warns = [c for c in job["preflight"]["checks"]
                 if c["status"] == "warn"]
        self.assertTrue(any("measured thickness required" in c["detail"]
                            for c in warns))
        self.assertTrue(any(c["rule"] == "R3" for c in warns))
        self.assertTrue(job["dxf_text"])
        self.assertTrue(job["cut_list_text"])

    def test_clamp_zone_failure_with_clamps_enabled(self):
        job = demo_job()
        job["clamps_enabled"] = True
        preflight = check_job_hd520(job)
        self.assertFalse(preflight["passed"])
        self.assertTrue(any(c["rule"] == "R4" and c["status"] == "fail"
                            for c in preflight["checks"]))
        job["preflight"] = preflight
        with self.assertRaises(ValueError):
            export_dxf(job)

    def test_tape_mode_passes_clamp_check(self):
        job = demo_job()
        self.assertTrue(any(c["rule"] == "R4" and c["status"] == "pass"
                            for c in job["preflight"]["checks"]))

    def test_tape_small_part_warning(self):
        job = demo_job()
        tiny = {"id": "tiny-test", "name": "Tiny test", "group": "carcass",
                "material": "PureBond birch", "thickness_in": 0.453,
                "width_in": 2.0, "height_in": 2.0, "grain": "horizontal",
                "edge_banding": "none", "quantity": 1}
        job["parts"] = job["parts"] + [tiny]
        job["nesting"]["sheets"][0]["placements"].append(
            {"part_id": "tiny-test", "x_in": 0.0, "y_in": 40.0,
             "rotated": False, "tile_index": 0})
        preflight = check_job_hd520(job)
        self.assertTrue(any(c["rule"] == "R5" and c["status"] == "warn"
                            for c in preflight["checks"]))

    def test_z_travel_failure(self):
        job = generate_cabinet({"width_in": 34, "layout": "doors",
                                "material_thickness_in": 8.0})
        self.assertFalse(job["preflight"]["passed"])
        self.assertTrue(any(c["rule"] == "R2" and c["status"] == "fail"
                            for c in job["preflight"]["checks"]))


class TestLayouts(unittest.TestCase):
    def test_all_layouts_pass(self):
        for layout in ("doors", "drawers-over-doors", "drawer-over-door",
                       "drawer-bank", "sink-base", "wall"):
            job = generate_cabinet({"width_in": 34, "layout": layout})
            self.assertTrue(job["preflight"]["passed"], layout)
            self.assertGreater(len(job["parts"]), 0, layout)

    def test_pantry_requires_explicit_height(self):
        with self.assertRaises(ValueError) as ctx:
            generate_cabinet({"width_in": 34, "layout": "pantry"})
        self.assertIn("height", str(ctx.exception).lower())
        job = generate_cabinet({"width_in": 34, "layout": "pantry",
                                "height_box_in": 72})
        self.assertTrue(job["preflight"]["passed"])
        self.assertNotIn("35", str(job["params"]["height_box_in"]))

    def test_pantry_never_uses_unverified_envelope(self):
        job = generate_cabinet({"width_in": 30, "layout": "pantry",
                                "height_box_in": 60, "depth_in": 20})
        self.assertEqual(job["params"]["height_box_in"], 60)
        self.assertEqual(job["params"]["depth_in"], 20)


class TestBriefParsing(unittest.TestCase):
    def test_parse_brief_local(self):
        params = parse_brief_local(
            "Build a 34 in wide drawer bank, box height 30 in, "
            "depth 24 in, PureBond birch, pin grid off")
        self.assertEqual(params["width_in"], 34)
        self.assertEqual(params["layout"], "drawer-bank")
        self.assertEqual(params["depth_in"], 24)
        self.assertEqual(params["height_box_in"], 30)
        self.assertEqual(params["material_name"], "PureBond birch")
        self.assertFalse(params["pin_grid_enabled"])

    def test_parse_brief_local_layout_words(self):
        self.assertEqual(parse_brief_local("sink base cabinet")["layout"],
                         "sink-base")
        self.assertEqual(parse_brief_local("tall pantry cabinet")["layout"],
                         "pantry")
        self.assertEqual(parse_brief_local("cabinet with doors")["layout"],
                         "doors")
        self.assertEqual(parse_brief_local("pin grid on")["pin_grid_enabled"],
                         True)


class TestMetaClient(unittest.TestCase):
    def test_meta_request_shape(self):
        url, payload = _build_meta_request(
            "34 in drawer bank", "https://api.meta.ai/v1", "muse-spark-1.3")
        self.assertEqual(url, "https://api.meta.ai/v1/chat/completions")
        self.assertEqual(payload["model"], "muse-spark-1.3")
        self.assertEqual(payload["messages"][1]["content"],
                         "34 in drawer bank")
        self.assertIn("JSON", payload["messages"][0]["content"])
        self.assertIn("drawer-bank", payload["messages"][0]["content"])

    def test_meta_unreachable_raises_not_falls_back(self):
        with self.assertRaises(Exception):
            parse_brief_meta("34 in drawer bank", "fake-key-for-test",
                             "http://127.0.0.1:1", "muse-spark-1.3")

    def test_meta_requires_key(self):
        with self.assertRaises(ValueError):
            parse_brief_meta("34 in drawer bank", "",
                             "https://api.meta.ai/v1", "muse-spark-1.3")


class TestSecrets(unittest.TestCase):
    def test_scan_detects_planted_keys(self):
        fake1 = "sk-test-fake-key-111"
        fake2 = "meta-test-token-222"
        text = "key one %s and key two %s" % (fake1, fake2)
        hits = scan_for_secrets(text, [fake1, fake2])
        self.assertEqual(hits, [fake1, fake2])

    def test_demo_exports_clean(self):
        job = demo_job()
        fake_keys = ["sk-test-fake-key-111", "meta-test-token-222",
                     "AKIAFAKEKEY1234567"]
        self.assertEqual(scan_for_secrets(job["dxf_text"], fake_keys), [])
        self.assertEqual(scan_for_secrets(job["cut_list_text"], fake_keys), [])
        self.assertEqual(scan_for_secrets("", fake_keys), [])


class TestTools(unittest.TestCase):
    def test_tool_catalog(self):
        data = load_tools()
        self.assertEqual(len(data["tools"]), 8)
        for tool in data["tools"]:
            self.assertEqual(tool["shank"], "unknown")
        numbers = sorted(t["tool_number"] for t in data["tools"])
        self.assertEqual(numbers, [1, 1, 2, 4, 8, 9, 9, 205])
        tapered = [t for t in data["tools"]
                   if t["tool_number"] == 8][0]
        self.assertEqual(tapered["type"], "Tapered")
        self.assertIn("ambiguous", " ".join(tapered["flags"]))
        self.assertIn("no plywood data", data["cutting_data"])


class TestWall(unittest.TestCase):
    def test_wall_wide_two_doors_one_shelf(self):
        # W3621: 36 in wide, 21 in high, 12 in deep.
        job = generate_cabinet({"width_in": 36, "height_box_in": 21,
                                "depth_in": 12, "layout": "wall"})
        self.assertTrue(job["preflight"]["passed"])
        ids = [p["id"] for p in job["parts"]]
        self.assertIn("door-left", ids)
        self.assertIn("door-right", ids)
        self.assertNotIn("door", ids)
        self.assertEqual([i for i in ids if i.startswith("shelf")],
                         ["shelf-1"])
        self.assertNotIn("drawer", " ".join(ids))
        self.assertEqual(job["params"]["overall_height_in"], 21)
        self.assertEqual(job["params"]["toe_kick_height_in"], 0.0)

    def test_wall_narrow_one_door_two_shelves(self):
        # W18.539R: 18.5 in wide, 39 in high, 12 in deep.
        job = generate_cabinet({"width_in": 18.5, "height_box_in": 39,
                                "depth_in": 12, "layout": "wall"})
        self.assertTrue(job["preflight"]["passed"])
        ids = [p["id"] for p in job["parts"]]
        self.assertIn("door", ids)
        self.assertNotIn("door-left", ids)
        self.assertEqual([i for i in ids if i.startswith("shelf")],
                         ["shelf-1", "shelf-2"])

    def test_wall_cut_list_has_no_toe_kick(self):
        job = generate_cabinet({"width_in": 30, "height_box_in": 21,
                                "depth_in": 12, "layout": "wall"})
        text = export_cut_list(job)
        self.assertIn("hangs, no toe kick", text)
        self.assertNotIn("ladder-pack", text)

    def test_wall_brief_keyword(self):
        params = parse_brief_local("36 inch wall cabinet, 21 high, 12 deep")
        self.assertEqual(params.get("layout"), "wall")


class TestProviderRecord(unittest.TestCase):
    def test_local_job_records_no_model(self):
        # Local never runs a model: no local LLM backend exists or
        # is needed. The record must say none, not "local" as if a
        # local model ran.
        job = generate_cabinet({"width_in": 34, "layout": "drawer-bank"})
        self.assertEqual(job["provider_record"]["provider"], "local")
        self.assertEqual(job["provider_record"]["model"], "none")


class TestDrawerOverDoor(unittest.TestCase):
    def test_one_drawer_one_door(self):
        job = generate_cabinet({"width_in": 34, "height_box_in": 30,
                                "layout": "drawer-over-door"})
        self.assertTrue(job["preflight"]["passed"])
        ids = [p["id"] for p in job["parts"]]
        # Carcass 6 + 1 drawer front + 1 drawer box of 4 + 1 door.
        self.assertEqual(len(job["parts"]), 12)
        self.assertIn("drawer-1-front", ids)
        self.assertIn("door", ids)
        self.assertNotIn("door-left", ids)
        front = [p for p in job["parts"] if p["id"] == "drawer-1-front"][0]
        door = [p for p in job["parts"] if p["id"] == "door"][0]
        self.assertAlmostEqual(front["width_in"], 33.875)
        self.assertAlmostEqual(front["height_in"], 10.0)
        self.assertAlmostEqual(door["width_in"], 33.875)
        self.assertAlmostEqual(door["height_in"], 19.5)

    def test_drawer_over_door_brief_phrases(self):
        self.assertEqual(
            parse_brief_local("drawer over door, 34 wide").get("layout"),
            "drawer-over-door")
        self.assertEqual(
            parse_brief_local(
                "one door and one drawer on top, 30 wide").get("layout"),
            "drawer-over-door")


class TestPreview(unittest.TestCase):
    def test_front_svg_matches_drawer_over_door_parts(self):
        job = generate_cabinet({"width_in": 34, "height_box_in": 30,
                                "layout": "drawer-over-door"})
        svg = job["preview_svg"]
        # Drawer rect 33.875 x 10 in, door rect 33.875 x 19.5 in, at
        # 10 px per inch.
        self.assertIn('width="338.75"', svg)
        self.assertIn('height="100"', svg)
        self.assertIn('height="195"', svg)
        self.assertIn("toe kick", svg)

    def test_wall_front_svg_has_no_toe_kick(self):
        job = generate_cabinet({"width_in": 36, "height_box_in": 21,
                                "depth_in": 12, "layout": "wall"})
        self.assertNotIn("toe kick", job["preview_svg"])
        self.assertIn("<line", job["preview_svg"])

    def test_sheet_svgs_cover_demo_job(self):
        job = demo_job()
        self.assertEqual(len(job["sheet_svgs"]), 10)
        joined = "\n".join(job["sheet_svgs"])
        self.assertIn("side-left", joined)
        for svg in job["sheet_svgs"]:
            self.assertIn("<rect", svg)


class TestBriefDecides(unittest.TestCase):
    def test_brief_only_drives_the_job(self):
        # The shape the UI sends when "let the description decide"
        # is checked: only a brief, no form values.
        job = generate_cabinet(
            {"brief_text": "36 inch wide wall cabinet, 21 high, 12 deep"})
        self.assertTrue(job["preflight"]["passed"])
        self.assertEqual(job["params"]["layout"], "wall")
        self.assertEqual(job["params"]["width_in"], 36)
        self.assertEqual(job["params"]["height_box_in"], 21)
        self.assertEqual(job["params"]["depth_in"], 12)


class TestPartDrawings(unittest.TestCase):
    def test_one_drawing_per_part(self):
        job = demo_job()
        self.assertEqual(len(job["part_svgs"]), len(job["parts"]))
        self.assertEqual(len(job["part_svgs"]), 16)
        by_id = {d["part_id"]: d for d in job["part_svgs"]}
        side = by_id["side-left"]
        self.assertEqual(side["name"], "Side left")
        self.assertIn("Side left: 24 x 30 in", side["svg"])
        self.assertIn("grain vertical", side["svg"])
        self.assertIn("<rect", side["svg"])
        for drawing in job["part_svgs"]:
            self.assertIn("<svg", drawing["svg"])


if __name__ == "__main__":
    unittest.main()
