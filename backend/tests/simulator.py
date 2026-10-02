"""Test-only RAW TCP receiver with an HTTP readout. Never run in production."""

import json
import socketserver
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

records = []
lock = threading.Lock()


class Receiver(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(10)
        payload = bytearray()
        while chunk := self.request.recv(4096):
            payload.extend(chunk)
        if payload:
            with lock:
                records.append(payload.decode("utf-8"))


class Readout(BaseHTTPRequestHandler):
    def do_GET(self):
        with lock:
            content = json.dumps(records).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


class TCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


if __name__ == "__main__":
    tcp = TCPServer(("0.0.0.0", 9100), Receiver)
    threading.Thread(target=tcp.serve_forever, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 9191), Readout).serve_forever()
