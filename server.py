#!/usr/bin/env python3
"""
Footbot proxy server.

Serves the static frontend (index.html / script.js / styles.css) and
proxies all /webhooks/* requests to the Rasa server on localhost:5005.
This lets a single ngrok tunnel expose the entire application.

Usage:
    python3 server.py [port]   # default port: 8080
"""

import http.client
import http.server
import mimetypes
import sys
from pathlib import Path

RASA_HOST = "localhost"
RASA_PORT = 5005
STATIC_DIR = Path(__file__).parent


class FootbotHandler(http.server.BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        print(f"[{self.address_string()}] {fmt % args}")

    # ------------------------------------------------------------------
    # GET — στατικά αρχεία ή health check Rasa
    # ------------------------------------------------------------------

    def do_GET(self):
        if self.path in ("/health", "/health/"):
            self._proxy_to_rasa("GET", "/")
            return

        target = STATIC_DIR / (self.path.lstrip("/") or "index.html")

        if not target.exists() or not target.is_file():
            self.send_error(404, f"Not found: {self.path}")
            return

        mime, _ = mimetypes.guess_type(str(target))
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ------------------------------------------------------------------
    # POST — proxy προς Rasa
    # ------------------------------------------------------------------

    def do_POST(self):
        if self.path.startswith("/webhooks/"):
            self._proxy_to_rasa("POST", self.path)
        else:
            self.send_error(404)

    # ------------------------------------------------------------------
    # OPTIONS — CORS preflight (απαιτείται όταν το ngrok προσθέτει browser checks)
    # ------------------------------------------------------------------

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    # ------------------------------------------------------------------
    # Εσωτερικές μέθοδοι
    # ------------------------------------------------------------------

    def _proxy_to_rasa(self, method, path):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length > 0 else b""

        try:
            conn = http.client.HTTPConnection(RASA_HOST, RASA_PORT, timeout=20)
            conn.request(
                method,
                path,
                body=body,
                headers={
                    "Content-Type": self.headers.get("Content-Type", "application/json"),
                    "Content-Length": str(len(body)),
                },
            )
            resp = conn.getresponse()
            resp_body = resp.read()
            conn.close()

            self.send_response(resp.status)
            for k, v in resp.getheaders():
                if k.lower() not in ("transfer-encoding", "connection"):
                    self.send_header(k, v)
            self._cors_headers()
            self.end_headers()
            self.wfile.write(resp_body)

        except OSError as exc:
            self.send_error(502, f"Rasa server unreachable: {exc}")

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    server = http.server.HTTPServer(("", port), FootbotHandler)
    print(f"Footbot proxy server → http://localhost:{port}")
    print(f"Proxying Rasa requests → http://{RASA_HOST}:{RASA_PORT}")
    print("Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
