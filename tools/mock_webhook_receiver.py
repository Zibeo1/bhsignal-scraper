import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length).decode("utf-8")
        payload = json.loads(raw_body)

        print("--- webhook received ---")
        print(f"path: {self.path}")
        print(f"x-event-id: {self.headers.get('X-Event-Id')}")
        print(f"x-signature-256: {self.headers.get('X-Signature-256')}")
        print(f"eventType: {payload.get('eventType')}")
        print(f"sourceArticleId: {payload.get('data', {}).get('sourceArticleId')}")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 8090), Handler)
    print("Mock webhook receiver listening on http://0.0.0.0:8090")
    server.serve_forever()
