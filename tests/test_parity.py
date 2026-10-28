"""Parity test: REST (UI path) vs MCP path for the HD520 companion.

Standard library only. Run from the app root:
    python3 tests/test_parity.py

Starts the real REST and MCP servers as subprocesses, runs, stops
both, and deletes every job file and log line it created, leaving
jobs/ as it was found. No em dashes are used in this file.
"""

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_ROOT))

from engine import scan_for_secrets  # noqa: E402

TEST_TOKEN = "parity-test-token-001"
FAKE_KEY = "sk-test-fake-key-123"
FAKE_META_KEY = "meta-test-fake-key-456"
REST_URL = "http://127.0.0.1:8791"

# The same JSON the UI sends for the 34 in drawer bank, all defaults,
# pin grid OFF, provider local.
UI_PARAMS = {
    "width_in": 34,
    "height_box_in": 30,
    "overall_height_in": 34.5,
    "depth_in": 24,
    "layout": "drawer-bank",
    "material_thickness_in": 0.453,
    "pin_grid_enabled": False,
    "provider": "local",
}

FORBIDDEN_VERBS = ("start", "jog", "home", "pause", "spindle")


def parts_hash(parts):
    text = json.dumps(parts, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def check_status(checks, rule, status):
    return any(c.get("rule") == rule and c.get("status") == status
               for c in checks)


def check_detail_contains(checks, rule, text):
    return any(c.get("rule") == rule and text in c.get("detail", "")
               for c in checks)


class ServerPair:
    """A running REST server plus an MCP server, both on one token."""

    def __init__(self, meta_key=None):
        self.meta_key = meta_key
        self.rest = None
        self.mcp = None
        self.rest_out = None
        self.mcp_err = None
        self._request_id = 0

    def _env(self):
        env = dict(os.environ)
        for key in ("HD520_META_API_KEY", "META_API_KEY",
                    "META_MODEL_API_KEY"):
            env.pop(key, None)
        env["HD520_API_TOKEN"] = TEST_TOKEN
        env["PYTHONUNBUFFERED"] = "1"
        if self.meta_key:
            env["HD520_META_API_KEY"] = self.meta_key
        return env

    def start(self):
        env = self._env()
        self.rest_out = tempfile.TemporaryFile(mode="w+")
        self.rest = subprocess.Popen(
            [sys.executable, "server.py"], cwd=str(APP_ROOT), env=env,
            stdout=self.rest_out, stderr=subprocess.STDOUT)
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                status, _ = rest_get("/health", token=None)
                if status == 200:
                    break
            except Exception:
                pass
            if self.rest.poll() is not None:
                raise RuntimeError("REST server exited early")
            time.sleep(0.2)
        else:
            raise RuntimeError("REST server did not become healthy")
        self.mcp_err = tempfile.TemporaryFile(mode="w+")
        self.mcp = subprocess.Popen(
            [sys.executable, "mcp_server.py"], cwd=str(APP_ROOT), env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self.mcp_err, text=True, bufsize=1)
        resp = self.mcp_call("initialize", {"protocolVersion": "2024-11-05",
                                            "capabilities": {},
                                            "clientInfo": {"name": "parity-test",
                                                           "version": "1"}})
        if "error" in resp:
            raise RuntimeError("MCP initialize failed: %s" % resp["error"])

    def stop(self):
        if self.mcp is not None:
            try:
                self.mcp.stdin.close()
            except Exception:
                pass
            try:
                self.mcp.wait(timeout=5)
            except Exception:
                self.mcp.kill()
            try:
                self.mcp.stdout.close()
            except Exception:
                pass
            self.mcp = None
        if self.rest is not None:
            self.rest.terminate()
            try:
                self.rest.wait(timeout=5)
            except Exception:
                self.rest.kill()
            self.rest = None
        for handle in (self.rest_out, self.mcp_err):
            if handle is not None:
                try:
                    handle.close()
                except Exception:
                    pass
        self.rest_out = None
        self.mcp_err = None

    def mcp_call(self, method, params):
        self._request_id += 1
        request = {"jsonrpc": "2.0", "id": self._request_id,
                   "method": method, "params": params}
        self.mcp.stdin.write(json.dumps(request) + "\n")
        self.mcp.stdin.flush()
        line = self.mcp.stdout.readline()
        if not line:
            raise RuntimeError("MCP server closed stdout")
        return json.loads(line)

    def mcp_tool(self, name, args):
        resp = self.mcp_call("tools/call", {"name": name, "arguments": args})
        return resp

    def mcp_tool_result(self, name, args):
        resp = self.mcp_tool(name, args)
        if "error" in resp:
            raise AssertionError("MCP tool %s failed: %s" % (name, resp["error"]))
        return resp["result"]["structuredContent"]


def rest_request(method, path, body=None, token=TEST_TOKEN):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token is not None:
        headers["X-API-Token"] = token
    request = urllib.request.Request(REST_URL + path, data=data,
                                     headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            if not raw:
                return resp.status, {}
            try:
                return resp.status, json.loads(raw)
            except ValueError:
                return resp.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            payload = json.loads(raw) if raw else {}
        except ValueError:
            payload = {"raw": raw}
        return exc.code, payload


def rest_get(path, token=TEST_TOKEN):
    return rest_request("GET", path, body=None, token=token)


def rest_post(path, body, token=TEST_TOKEN):
    return rest_request("POST", path, body=body, token=token)


def rest_generate(params, caller="ui"):
    status, job = rest_post("/api/generate_cabinet",
                            {"params": copy.deepcopy(params), "caller": caller})
    if status != 200:
        raise AssertionError("REST generate failed %s: %s" % (status, job))
    return job


def rest_check(job, caller="ui"):
    status, preflight = rest_post("/api/check_job_hd520",
                                  {"job": copy.deepcopy(job), "caller": caller})
    if status != 200:
        raise AssertionError("REST check failed %s: %s" % (status, preflight))
    return preflight


class TestParity(unittest.TestCase):
    pair = None
    jobs_before = set()

    @classmethod
    def setUpClass(cls):
        jobs_dir = APP_ROOT / "jobs"
        jobs_dir.mkdir(parents=True, exist_ok=True)
        cls.jobs_before = {p.name for p in jobs_dir.iterdir()}
        cls.pair = ServerPair(meta_key=None)
        cls.pair.start()

    @classmethod
    def tearDownClass(cls):
        if cls.pair is not None:
            cls.pair.stop()
            cls.pair = None
        jobs_dir = APP_ROOT / "jobs"
        if jobs_dir.exists():
            for path in jobs_dir.iterdir():
                if path.name not in cls.jobs_before:
                    path.unlink()

    def mcp_generate(self, params, caller="ui"):
        return self.pair.mcp_tool_result(
            "generate_cabinet",
            {"params": copy.deepcopy(params), "caller": caller,
             "token": TEST_TOKEN})

    def mcp_check(self, job, caller="ui"):
        return self.pair.mcp_tool_result(
            "check_job_hd520",
            {"job": copy.deepcopy(job), "caller": caller, "token": TEST_TOKEN})

    def test_parity_gate(self):
        rest_job = rest_generate(UI_PARAMS)
        mcp_job = self.mcp_generate(UI_PARAMS)
        self.assertEqual(rest_job["parts"], mcp_job["parts"])
        self.assertEqual(len(rest_job["nesting"]["sheets"]), 10)
        self.assertEqual(len(mcp_job["nesting"]["sheets"]), 10)
        self.assertTrue(rest_job["preflight"]["passed"])
        self.assertTrue(mcp_job["preflight"]["passed"])
        self.assertEqual(rest_job["preflight"], mcp_job["preflight"])
        print("PARITY: parts=%d sheets=%d parts_hash=%s"
              % (len(rest_job["parts"]),
                 len(rest_job["nesting"]["sheets"]),
                 parts_hash(rest_job["parts"])))

    def test_acceptance_figures(self):
        job = rest_generate(UI_PARAMS)
        self.assertEqual(len(job["parts"]), 16)
        self.assertEqual(len(job["nesting"]["sheets"]), 10)
        self.assertTrue(job["preflight"]["passed"])
        self.assertFalse(job["params"]["pin_grid_enabled"])
        self.assertEqual(job["provider_record"]["provider"], "local")

    def test_failure_64_wide_both_paths(self):
        params = dict(UI_PARAMS, width_in=64)
        rest_job = rest_generate(params)
        mcp_job = self.mcp_generate(params)
        for job in (rest_job, mcp_job):
            self.assertFalse(job["preflight"]["passed"])
            self.assertFalse(job.get("dxf_text"))
            self.assertFalse(job.get("cut_list_text"))
        rest_pre = rest_check(rest_job)
        mcp_pre = self.mcp_check(mcp_job)
        self.assertFalse(rest_pre["passed"])
        self.assertFalse(mcp_pre["passed"])

    def test_failure_nominal_thickness_warns_and_exports(self):
        params = dict(UI_PARAMS, material_thickness_in=0.750,
                      thickness_is_nominal=True)
        for job in (rest_generate(params), self.mcp_generate(params)):
            self.assertTrue(job["preflight"]["passed"])
            self.assertTrue(check_detail_contains(
                job["preflight"]["checks"], "R3",
                "measured thickness required"))
            self.assertTrue(job.get("dxf_text"))
            self.assertTrue(job.get("cut_list_text"))
            self.assertIn("material_thickness_in",
                          job["params"].get("provisional", []))

    def test_failure_clamp_zone_both_paths(self):
        params = dict(UI_PARAMS, clamps_enabled=True)
        rest_job = rest_generate(params)
        mcp_job = self.mcp_generate(params)
        for job in (rest_job, mcp_job):
            self.assertFalse(job["preflight"]["passed"])
            self.assertTrue(check_status(job["preflight"]["checks"],
                                         "R4", "fail"))
            self.assertFalse(job.get("dxf_text"))
        demo = rest_generate(UI_PARAMS)
        clamped = copy.deepcopy(demo)
        clamped["clamps_enabled"] = True
        for preflight in (rest_check(clamped), self.mcp_check(clamped)):
            self.assertFalse(preflight["passed"])
            self.assertTrue(check_status(preflight["checks"], "R4", "fail"))

    def test_failure_tape_small_part_warning(self):
        demo = rest_generate(UI_PARAMS)
        tiny = {"id": "tiny-test", "name": "Tiny test", "group": "carcass",
                "material": "PureBond birch", "thickness_in": 0.453,
                "width_in": 2.0, "height_in": 2.0, "grain": "horizontal",
                "edge_banding": "none", "quantity": 1}
        job = copy.deepcopy(demo)
        job["parts"] = job["parts"] + [tiny]
        job["nesting"]["sheets"][0]["placements"].append(
            {"part_id": "tiny-test", "x_in": 0.0, "y_in": 40.0,
             "rotated": False, "tile_index": 0})
        for preflight in (rest_check(job), self.mcp_check(job)):
            self.assertTrue(check_status(preflight["checks"], "R5", "warn"))

    def test_auth(self):
        status, _ = rest_post("/api/generate_cabinet",
                              {"params": copy.deepcopy(UI_PARAMS)},
                              token=None)
        self.assertEqual(status, 401)
        status, _ = rest_post("/api/generate_cabinet",
                              {"params": copy.deepcopy(UI_PARAMS)},
                              token="wrong-token")
        self.assertEqual(status, 401)
        resp = self.pair.mcp_tool(
            "generate_cabinet",
            {"params": copy.deepcopy(UI_PARAMS), "token": "wrong-token"})
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32001)

    def test_mcp_tools_list_exact(self):
        resp = self.pair.mcp_call("tools/list", {})
        names = [t["name"] for t in resp["result"]["tools"]]
        self.assertEqual(names, ["generate_cabinet", "check_job_hd520"])

    def test_secrets_refused_and_files_clean(self):
        body = {"params": dict(UI_PARAMS, api_key=FAKE_KEY), "caller": "ui"}
        status, _ = rest_post("/api/generate_cabinet", body)
        self.assertEqual(status, 400)
        resp = self.pair.mcp_tool(
            "generate_cabinet",
            {"params": dict(UI_PARAMS, api_key=FAKE_KEY),
             "token": TEST_TOKEN})
        self.assertIn("error", resp)
        jobs_dir = APP_ROOT / "jobs"
        for path in jobs_dir.iterdir():
            if path.is_file():
                self.assertNotIn(FAKE_KEY, path.read_text(encoding="utf-8"))
                self.assertNotIn(FAKE_META_KEY,
                                 path.read_text(encoding="utf-8"))
        demo = rest_generate(UI_PARAMS)
        self.assertEqual(scan_for_secrets(demo["dxf_text"],
                                          [FAKE_KEY, TEST_TOKEN]), [])
        self.assertEqual(scan_for_secrets(demo["cut_list_text"],
                                          [FAKE_KEY, TEST_TOKEN]), [])

    def test_meta_no_key_refused_never_silent_local(self):
        params = dict(UI_PARAMS, provider="meta")
        status, payload = rest_post("/api/generate_cabinet",
                                    {"params": params, "caller": "ui"})
        self.assertEqual(status, 400)
        self.assertIn("Meta", payload.get("error", ""))
        resp = self.pair.mcp_tool(
            "generate_cabinet",
            {"params": copy.deepcopy(params), "token": TEST_TOKEN})
        self.assertIn("error", resp)
        self.assertIn("Meta", resp["error"]["message"])

    def test_meta_params_only_labeling_with_key_set(self):
        # Observed behavior only, not a parity failure. This test stops
        # the no-key servers, starts a keyed pair, checks the
        # params-only Meta record, then restores the no-key pair.
        self.__class__.pair.stop()
        keyed = ServerPair(meta_key=FAKE_META_KEY)
        try:
            keyed.start()
            params = dict(UI_PARAMS, provider="meta")
            status, job = rest_post("/api/generate_cabinet",
                                    {"params": copy.deepcopy(params),
                                     "caller": "ui"})
            self.assertEqual(status, 200)
            self.assertEqual(job["provider_record"]["provider"], "meta")
            local_job = rest_generate(UI_PARAMS)
            self.assertEqual(job["parts"], local_job["parts"])
            print("META-LABELING: params-only meta recorded provider=%s "
                  "model=%s parts=%d parts_equal_to_local=%s"
                  % (job["provider_record"]["provider"],
                     job["provider_record"].get("model"),
                     len(job["parts"]),
                     job["parts"] == local_job["parts"]))
        finally:
            keyed.stop()
            jobs_dir = APP_ROOT / "jobs"
            for path in jobs_dir.iterdir():
                if path.name not in self.__class__.jobs_before:
                    path.unlink()
            restored = ServerPair(meta_key=None)
            restored.start()
            self.__class__.pair = restored

    def test_local_provider_with_brief(self):
        params = dict(UI_PARAMS,
                      brief_text="34 inch wide drawer bank, PureBond birch",
                      provider="local")
        job = rest_generate(params)
        self.assertEqual(job["provider_record"]["provider"], "local")
        self.assertEqual(len(job["parts"]), 16)

    def test_no_machine_control_audit(self):
        status, health = rest_get("/health", token=None)
        self.assertEqual(status, 200)
        self.assertTrue(health.get("ok"))
        status, page = rest_get("/", token=None)
        self.assertEqual(status, 200)
        self.assertIn("HD520", page if isinstance(page, str) else "")
        self.assertEqual(rest_generate(UI_PARAMS)["preflight"]["passed"],
                         True)
        self.assertTrue(rest_check(rest_generate(UI_PARAMS))["passed"])
        for verb in FORBIDDEN_VERBS:
            status, _ = rest_get("/api/" + verb, token=None)
            self.assertEqual(status, 404)
            status, _ = rest_post("/api/" + verb, {}, token=TEST_TOKEN)
            self.assertEqual(status, 404)
            status, _ = rest_post("/api/export_" + verb, {}, token=TEST_TOKEN)
            self.assertEqual(status, 404)
        resp = self.pair.mcp_call("tools/list", {})
        names = [t["name"] for t in resp["result"]["tools"]]
        self.assertEqual(names, ["generate_cabinet", "check_job_hd520"])
        for verb in FORBIDDEN_VERBS:
            resp = self.pair.mcp_tool(verb, {"token": TEST_TOKEN})
            self.assertIn("error", resp)

    def test_binding_localhost(self):
        import socket
        sock = socket.create_connection(("127.0.0.1", 8791), timeout=5)
        sock.close()
        status, health = rest_get("/health", token=None)
        self.assertEqual(status, 200)
        self.assertEqual(health.get("app"), "hd520-companion")


if __name__ == "__main__":
    unittest.main(verbosity=2)
