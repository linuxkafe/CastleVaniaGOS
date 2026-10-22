#!/usr/bin/env python3
"""Mock license server that returns a valid license response."""
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import os
import sys

class MockLicenseHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Return a mock license response
        response = {
            "version": "0",
            "message": "LICENSE_OK",
            "nonce": "mock_nonce",
            "token": "mock_token",
            "signature": "mock_signature"
        }
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())
    
    def do_POST(self):
        # Handle POST requests (license check uses POST)
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else b''
        
        # Return a mock license response
        response = {
            "version": "0",
            "message": "LICENSE_OK",
            "nonce": "mock_nonce",
            "token": "mock_token",
            "signature": "mock_signature"
        }
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())
    
    def log_message(self, format, *args):
        pass  # Suppress logging

if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 80
    # Bind to loopback by default. Override with BIND_HOST env var only when the
    # emulator (10.0.2.2) must reach this server, and document the exposure.
    bind_host = os.environ.get('BIND_HOST', '127.0.0.1')
    server = HTTPServer((bind_host, port), MockLicenseHandler)
    print(f"Mock license server running on {bind_host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass