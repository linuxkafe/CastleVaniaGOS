#!/usr/bin/env python3
"""
Simple HTTP server that serves Unity asset bundles for Castlevania: Grimoire of Souls.
Bypasses the need for external CDN by serving assets locally.
"""

import http.server
import socketserver
import os
import sys
from pathlib import Path

# Use absolute path to assets
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ASSETS_DIR = os.path.join(SCRIPT_DIR, "assets")

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
ASSETS_DIR = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_ASSETS_DIR
# Bind to loopback by default. Override with BIND_HOST env var only when the
# emulator (10.0.2.2) must reach this server, and document the exposure.
BIND_HOST = os.environ.get('BIND_HOST', '127.0.0.1')

# Ensure assets dir exists
if not os.path.isdir(ASSETS_DIR):
    print(f"[ERROR] Assets directory not found: {ASSETS_DIR}")
    print(f"[INFO] Trying default: {DEFAULT_ASSETS_DIR}")
    ASSETS_DIR = DEFAULT_ASSETS_DIR

if not os.path.isdir(ASSETS_DIR):
    print(f"[ERROR] Assets directory not found: {ASSETS_DIR}")
    sys.exit(1)

class UnityAssetHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ASSETS_DIR, **kwargs)
    
    def log_message(self, format, *args):
        print(f"[ASSET-SERVER] {format % args}")

def main():
    os.chdir(ASSETS_DIR)
    
    with socketserver.TCPServer((BIND_HOST, PORT), UnityAssetHandler) as httpd:
        print(f"[ASSET-SERVER] Serving assets from: {ASSETS_DIR}")
        print(f"[ASSET-SERVER] Listening on {BIND_HOST}:{PORT}")
        print(f"[ASSET-SERVER] Available files:")
        for f in sorted(os.listdir(ASSETS_DIR)):
            size = os.path.getsize(os.path.join(ASSETS_DIR, f))
            print(f"  - {f} ({size / 1024 / 1024:.2f} MB)")
        
        print(f"[ASSET-SERVER] Ready to serve!")
        httpd.serve_forever()

if __name__ == "__main__":
    main()
