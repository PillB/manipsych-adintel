#!/usr/bin/env python3
"""O-01: Safe local HTTP server — binds to 127.0.0.1 only.

Replaces the insecure `python3 -m http.server 8765 --bind 0.0.0.0` which
exposed the entire repo (including raw HTML with PII) to the network.
"""

import http.server
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = 8765
HOST = "127.0.0.1"  # localhost only — NOT 0.0.0.0


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        # Add security headers
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main():
    print(f"Starting safe local server on http://{HOST}:{PORT}/")
    print(f"Serving: {ROOT}")
    print("WARNING: This server binds to 127.0.0.1 only (localhost).")
    print("It is NOT accessible from other machines on the network.")
    print("Press Ctrl+C to stop.")
    server = http.server.HTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
