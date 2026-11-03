"""Regression tests for the 2026-11-02 code-review fixes.

Standard library only. Run from the app root:
    python -m unittest tests.test_review_regressions -v
"""

import copy
import io
import os
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

APP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_ROOT))

os.environ.setdefault("HD520_API_TOKEN", "review-test-token")

from engine import check_job_hd520, generate_cabinet  # noqa: E402

BASE = {"width_in": 34, "height_box_in": 30, "depth_in": 24,
        "layout": "drawer-bank", "provider": "local"}


def demo_job():
    return generate_cabinet(dict(BASE))


class TestNumericValidation(unittest.TestCase):
    def test_nan_width_rejected(self):
        with self.assertRaises(ValueError):
            generate_cabinet(dict(BASE, width_in=float("nan")))

    def test_inf_width_rejected(self):
        with self.assertRaises(ValueError):
            generate_cabinet(dict(BASE, width_in=float("inf")))

    def test_string_width_rejected(self):
        with self.assertRaises(ValueError):
            generate_cabinet(dict(BASE, width_in="34"))

    def test_bool_width_rejected(self):
        with self.assertRaises(ValueError):
            generate_cabinet(dict(BASE, width_in=True))

    def test_drawer_count_variants_rejected(self):
        for bad in (100, 0, -1, "3", True, 2.9, float("nan")):
            with self.assertRaises(ValueError, msg=repr(bad)):
                generate_cabinet(dict(BASE, drawer_count=bad))

    def test_too_narrow_for_drawer_box_rejected(self):
        with self.assertRaises(ValueError):
            generate_cabinet(dict(BASE, width_in=1))

    def test_string_boolean_rejected(self):
        with self.assertRaises(ValueError):
            generate_cabinet(dict(BASE, pin_grid_enabled="false"))


class TestMetaBaseUrl(unittest.TestCase):
    def test_caller_supplied_base_url_rejected(self):
        os.environ["META_API_KEY"] = "fake-key-for-test"
        try:
            with self.assertRaises(ValueError):
                generate_cabinet({
                    "width_in": 34, "layout": "drawer-bank",
                    "provider": "meta", "brief_text": "34 in drawer bank",
                    "base_url": "https://evil.example/v1",
                })
        finally:
            os.environ.pop("META_API_KEY", None)


class TestPreflightPlacementIntegrity(unittest.TestCase):
    def test_duplicate_placement_fails(self):
        job = demo_job()
        sheet = job["nesting"]["sheets"][0]
        sheet["placements"].append(dict(sheet["placements"][0]))
        preflight = check_job_hd520(job)
        self.assertFalse(preflight["passed"])
        self.assertTrue(any(c["rule"] == "R6-nesting"
                            and c["status"] == "fail"
                            for c in preflight["checks"]))

    def test_tiled_placement_outside_bed_fails(self):
        job = demo_job()
        sheet = job["nesting"]["sheets"][0]
        rogue = dict(sheet["placements"][0])
        rogue["x_in"] = 999.0
        rogue["y_in"] = 999.0
        rogue["tile_index"] = 1
        sheet["placements"].append(rogue)
        preflight = check_job_hd520(job)
        self.assertFalse(preflight["passed"])

    def test_negative_placement_fails(self):
        job = demo_job()
        placement = job["nesting"]["sheets"][0]["placements"][0]
        placement["x_in"] = -5.0
        preflight = check_job_hd520(job)
        self.assertFalse(preflight["passed"])
        self.assertTrue(any(c["rule"] == "R1-bed"
                            and c["status"] == "fail"
                            for c in preflight["checks"]))

    def test_generated_job_still_passes(self):
        self.assertTrue(check_job_hd520(demo_job())["passed"])


class TestSvgEscaping(unittest.TestCase):
    def test_material_name_escaped_in_part_svg(self):
        job = generate_cabinet(dict(
            BASE, material_name='Birch</text><script>alert(1)</script>'))
        for entry in job["part_svgs"]:
            self.assertNotIn("<script>alert(1)</script>", entry["svg"])
        self.assertIn("&lt;script&gt;", job["part_svgs"][0]["svg"])


class TestServerHelpers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server
        cls.server = server

    def _handler(self):
        handler = object.__new__(self.server.Handler)
        return handler

    def test_non_ascii_token_does_not_raise(self):
        self.assertFalse(self.server._tokens_match("token-with-umlaut-\u00f6",
                                                   self.server.API_TOKEN))
        self.assertTrue(self.server._tokens_match(self.server.API_TOKEN,
                                                  self.server.API_TOKEN))

    def test_health_route_ignores_query_string(self):
        handler = self._handler()
        handler.path = "/health?probe=1"
        captured = {}
        handler._send_json = lambda status, payload: captured.update(
            status=status, payload=payload)
        handler.do_GET()
        self.assertEqual(captured["status"], 200)
        self.assertTrue(captured["payload"]["ok"])

    def test_oversized_body_rejected(self):
        handler = self._handler()
        handler.headers = {"Content-Length": str(self.server.MAX_BODY_BYTES + 1)}
        handler.rfile = io.BytesIO(b"")
        body, error = handler._read_json_body()
        self.assertIsNone(body)
        self.assertIn("too large", error)

    def test_negative_content_length_rejected(self):
        handler = self._handler()
        handler.headers = {"Content-Length": "-5"}
        handler.rfile = io.BytesIO(b"")
        body, error = handler._read_json_body()
        self.assertIsNone(body)
        self.assertIsNotNone(error)

    def test_probe_detects_live_server_then_rebinds_after_stop(self):
        # The single-bind guard is the /health probe, not the bind:
        # reuse stays on so TIME_WAIT cannot block a fast restart.
        self.assertTrue(self.server.CompanionHTTPServer.allow_reuse_address)
        srv = self.server.CompanionHTTPServer(("127.0.0.1", 0),
                                              self.server.Handler)
        port = srv.server_address[1]
        url = "http://127.0.0.1:%d/health" % port
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        try:
            self.assertTrue(self.server._live_server_answering(url))
        finally:
            srv.shutdown()
            srv.server_close()
            thread.join(timeout=5)
        # Nothing answers now: the probe clears a restart, and the
        # port rebinds immediately (the TIME_WAIT regression).
        self.assertFalse(self.server._live_server_answering(url))
        rebound = self.server.CompanionHTTPServer(("127.0.0.1", port),
                                                  self.server.Handler)
        rebound.server_close()

    def test_main_exits_when_live_server_detected(self):
        with mock.patch.object(self.server, "_live_server_answering",
                               return_value=True):
            with self.assertRaises(SystemExit):
                self.server.main()

    def test_save_job_names_unique_within_same_second(self):
        job = {"job_id": "x"}
        params = {"layout": "doors"}
        first = self.server._save_job(job, params)
        second = self.server._save_job(job, params)
        self.assertNotEqual(first, second)
        for name in (first, second):
            (self.server.JOBS_DIR / name).unlink(missing_ok=True)


class TestMcpHelpers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import mcp_server
        cls.mcp = mcp_server

    def test_non_ascii_token_does_not_raise(self):
        self.assertFalse(self.mcp._tokens_match("token-\u00f6",
                                                self.mcp.API_TOKEN))

    def test_notification_gets_no_response(self):
        self.assertIsNone(self.mcp._handle(
            {"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def test_dispatch_survives_non_object_request(self):
        # main() guards the id lookup; _handle itself must reject cleanly.
        response = self.mcp._handle(["not", "an", "object"])
        self.assertIn("error", response)


if __name__ == "__main__":
    unittest.main(verbosity=2)
