"""
Single-port reverse proxy: serves static files AND proxies /webhooks/* to Rasa.
Use with ngrok: expose only this server (port 8080).
"""
import http.server
import urllib.request
import urllib.error
import os
import mimetypes

RASA_URL = "http://localhost:5005"
STATIC_DIR = os.path.dirname(os.path.abspath(__file__))


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress per-request logging

    def _proxy_to_rasa(self):
        target = RASA_URL + self.path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else None

        req = urllib.request.Request(
            target,
            data=body,
            method=self.command,
            headers={
                k: v for k, v in self.headers.items()
                if k.lower() not in ("host", "content-length")
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() not in ("transfer-encoding",):
                        self.send_header(k, v)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(resp.read())
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            self.send_response(502)
            self.end_headers()
            self.wfile.write(str(e).encode())

    def _serve_static(self):
        path = self.path.split("?")[0]
        if path == "/":
            path = "/index.html"
        file_path = os.path.join(STATIC_DIR, path.lstrip("/"))
        if not os.path.isfile(file_path):
            self.send_response(404)
            self.end_headers()
            return
        mime, _ = mimetypes.guess_type(file_path)
        with open(file_path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path.startswith("/webhooks/"):
            self._proxy_to_rasa()
        else:
            self._serve_static()

    def do_POST(self):
        if self.path.startswith("/webhooks/"):
            self._proxy_to_rasa()
        else:
            self.send_response(405)
            self.end_headers()


if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    server = http.server.HTTPServer(("0.0.0.0", port), ProxyHandler)
    print(f"Proxy server running on http://localhost:{port}")
    print(f"  Static files: {STATIC_DIR}")
    print(f"  Proxying /webhooks/* → {RASA_URL}")
    server.serve_forever()
