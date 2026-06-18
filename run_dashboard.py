#!/usr/bin/env python3
"""
High-Performance Threaded Gzip Server for India Climate Anomaly Atlas
=====================================================================
Serves large GeoJSON and JSON files instantly using on-the-fly Gzip compression.
Forces correct MIME types and auto-launches Google Chrome.
"""

import gzip
import http.server
import socketserver
import os
import sys
import webbrowser
import threading
from io import BytesIO

PORT = 8000
HOST = "127.0.0.1"


class GzipThreadingSimpleHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        if self.should_gzip():
            self.send_header("Content-Encoding", "gzip")
        # Enable CORS for maximum compatibility
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def should_gzip(self):
        # Compress text and JSON/GeoJSON files dynamically
        path = self.translate_path(self.path)
        if not os.path.isfile(path):
            return False

        ext = os.path.splitext(path)[1].lower()
        if ext not in [".html", ".css", ".js", ".json", ".geojson", ".svg", ".txt"]:
            return False

        return "gzip" in self.headers.get("Accept-Encoding", "")

    def send_head(self):
        # Override to add geojson MIME type
        self.extensions_map[".geojson"] = "application/geo+json"
        self.extensions_map[".json"] = "application/json"
        self.extensions_map[".js"] = "application/javascript"
        self.extensions_map[".css"] = "text/css"

        if not self.should_gzip():
            return super().send_head()

        path = self.translate_path(self.path)
        try:
            with open(path, "rb") as f:
                raw_data = f.read()
        except OSError:
            self.send_error(http.HTTPStatus.NOT_FOUND, "File not found")
            return None

        # Dynamic Gzip Compression
        compressed_buffer = BytesIO()
        with gzip.GzipFile(fileobj=compressed_buffer, mode="wb", compresslevel=6) as gzip_file:
            gzip_file.write(raw_data)

        compressed_bytes = compressed_buffer.getvalue()

        # Prepare Response Headers
        self.send_response(http.HTTPStatus.OK)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Length", str(len(compressed_bytes)))
        self.end_headers()

        return BytesIO(compressed_bytes)


class ThreadedTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


def start_server():
    # Make sure we serve from the dashboard directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    handler = GzipThreadingSimpleHTTPRequestHandler
    with ThreadedTCPServer((HOST, PORT), handler) as server:
        print("==========================================================")
        print("   INDIA CLIMATE ANOMALY ATLAS — LOCAL HOST RUNNER")
        print("==========================================================")
        print(f"Server successfully started at: http://{HOST}:{PORT}")
        print("On-the-fly Gzip compression is ENABLED.")
        print("Multi-threaded downloading is ENABLED.")
        print("Press Ctrl+C to stop the server.")
        print("==========================================================")

        # Open browser in a separate thread so it doesn't block the server boot
        def open_browser():
            try:
                webbrowser.open(f"http://{HOST}:{PORT}/index.html")
            except Exception as e:
                print(f"Note: Could not open browser automatically ({e})")

        threading.Thread(target=open_browser, daemon=True).start()

        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down local server. Goodbye!")
            sys.exit(0)


if __name__ == "__main__":
    start_server()
