from http.server import HTTPServer, SimpleHTTPRequestHandler
import json
import os

class Handler(SimpleHTTPRequestHandler):

    def send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_cors_headers()
        self.end_headers()

    def do_POST(self):
        if self.path == "/save":
            length = int(self.headers["Content-Length"])
            data = json.loads(self.rfile.read(length))

            with open("settings.json", "w") as f:
                json.dump(data, f, indent=2)

            self.send_response(200)
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')

    def do_GET(self):
        if self.path == "/load":
            if os.path.exists("settings.json"):
                with open("settings.json", "r") as f:
                    content = f.read()
                self.send_response(200)
                self.send_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(content.encode())
            else:
                self.send_response(404)
                self.send_cors_headers()
                self.end_headers()
        else:
            super().do_GET()

httpd = HTTPServer(("localhost", 8000), Handler)
print("Server läuft auf http://localhost:8000")
httpd.serve_forever()