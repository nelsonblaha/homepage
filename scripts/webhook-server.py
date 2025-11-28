#!/usr/bin/env python3
"""
Simple webhook server for GitHub Actions deployment.

Listens on port 9000 and verifies HMAC-SHA256 signature before
running the deploy script.

Usage:
    DEPLOY_WEBHOOK_SECRET=your-secret python scripts/webhook-server.py

Or run as a systemd service (see webhook-server.service).
"""

import hashlib
import hmac
import os
import subprocess
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler


WEBHOOK_SECRET = os.environ.get("DEPLOY_WEBHOOK_SECRET", "")
DEPLOY_SCRIPT = "/home/ben/docker/blaha-homepage/deploy.sh"
PORT = 9002


class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/deploy":
            self.send_error(404, "Not Found")
            return

        # Read body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        # Verify signature
        signature_header = self.headers.get("X-Hub-Signature-256", "")
        if not signature_header.startswith("sha256="):
            self.send_error(403, "Missing signature")
            return

        expected_signature = signature_header[7:]
        computed_signature = hmac.new(
            WEBHOOK_SECRET.encode(),
            body,
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(expected_signature, computed_signature):
            self.send_error(403, "Invalid signature")
            return

        # Run deploy script
        print(f"Webhook received, running deploy script...")
        try:
            result = subprocess.run(
                ["bash", DEPLOY_SCRIPT],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            print(f"Deploy stdout: {result.stdout}")
            if result.stderr:
                print(f"Deploy stderr: {result.stderr}")

            if result.returncode == 0:
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"Deploy successful\n")
            else:
                self.send_response(500)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(f"Deploy failed: {result.stderr}\n".encode())
        except subprocess.TimeoutExpired:
            self.send_error(504, "Deploy timed out")
        except Exception as e:
            self.send_error(500, f"Deploy error: {e}")

    def log_message(self, format, *args):
        print(f"[webhook] {args[0]}")


def main():
    if not WEBHOOK_SECRET:
        print("ERROR: DEPLOY_WEBHOOK_SECRET environment variable not set")
        sys.exit(1)

    server = HTTPServer(("0.0.0.0", PORT), WebhookHandler)
    print(f"Webhook server listening on port {PORT}")
    print(f"Endpoint: POST /deploy")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
