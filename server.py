from http.server import HTTPServer, SimpleHTTPRequestHandler
import json

class Handler(SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/save":
            length = int(self.headers["Content-Length"])
            data = json.loads(self.rfile.read(length))
            
            with open("settings.json", "w") as f:
                json.dump(data, f, indent=2)
            
            self.send_response(200)
            self.end_headers()

httpd = HTTPServer(("localhost", 8000), Handler)
print("Server läuft auf http://localhost:8000")
httpd.serve_forever()