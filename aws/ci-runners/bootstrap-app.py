#!/usr/bin/env python3
"""Register the dedicated GitHub App and send its credentials directly to SSM.

The browser must confirm the app registration and install it on the one repository.
No personal GitHub token or app private key is written to this repository or logs.
"""

import argparse
import base64
import html
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import urllib.parse
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--webhook-url", required=True)
    parser.add_argument("--profile", default="i2g-ci-admin")
    parser.add_argument("--port", type=int, default=8897)
    args = parser.parse_args()
    state = secrets.token_urlsafe(32)
    result = {}
    manifest = {
        "name": "I2G AWS CI Runners",
        "url": "https://github.com/Innovate-To-Grow/Innovate-To-Grow-Website",
        "description": "Launch and retire dedicated, ephemeral AWS CI runners for the Innovate To Grow website.",
        "hook_attributes": {"url": args.webhook_url, "active": True},
        "redirect_url": f"http://127.0.0.1:{args.port}/callback",
        "public": False,
        "default_permissions": {"actions": "read", "checks": "read", "administration": "write", "metadata": "read"},
        "default_events": ["workflow_job"],
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Callback URLs contain one-use credentials.

        def respond(self, status, body):
            data = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            request = urllib.parse.urlparse(self.path)
            if request.path == "/":
                action = "https://github.com/organizations/Innovate-To-Grow/settings/apps/new?" + urllib.parse.urlencode({"state": state})
                self.respond(200, '<!doctype html><meta charset="utf-8"><title>I2G AWS Runner Setup</title>'
                             '<h1>I2G AWS Runner Setup</h1><p>Create a private GitHub App, then install it only on Innovate-To-Grow-Website.</p>'
                             '<p>Permissions: repository administration read/write (runner registration), Actions and Checks read-only.</p>'
                             '<p>Credentials are stored in encrypted AWS SSM parameters in account 394167325273, Oregon.</p>'
                             f'<form method="post" action="{html.escape(action, quote=True)}">'
                             f'<input type="hidden" name="manifest" value="{html.escape(json.dumps(manifest), quote=True)}">'
                             '<button type="submit">Review GitHub App</button></form>')
                return
            if request.path == "/status":
                self.respond(200, html.escape(json.dumps(result or {"status": "pending"})))
                return
            query = urllib.parse.parse_qs(request.query)
            if request.path != "/callback" or not secrets.compare_digest(query.get("state", [""])[0], state) or result:
                self.respond(400, "Invalid or already completed setup request.")
                return
            code = query.get("code", [""])[0]
            if not code or not code.isalnum():
                self.respond(400, "Missing manifest code.")
                return
            try:
                conversion = urllib.request.Request(
                    f"https://api.github.com/app-manifests/{code}/conversions", data=b"", method="POST",
                    headers={"Accept": "application/vnd.github+json", "User-Agent": "i2g-ci-setup", "X-GitHub-Api-Version": "2022-11-28"},
                )
                with urllib.request.urlopen(conversion, timeout=30) as response:
                    app = json.load(response)
                # Preserve one-use conversion results if an AWS write fails.
                pending = Path.home() / ".aws/i2g-ci-app-pending.json"
                descriptor = os.open(pending, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
                with os.fdopen(descriptor, "w") as recovery:
                    json.dump(app, recovery)
                parameters = {
                    "id": str(app["id"]),
                    "key-base64": base64.b64encode(app["pem"].encode()).decode(),
                    "webhook-secret": app["webhook_secret"],
                }
                for key, value in parameters.items():
                    with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as parameter:
                        json.dump({"Name": f"/i2g-ci/github-app/{key}", "Type": "SecureString", "Value": value, "Overwrite": True}, parameter)
                        parameter.flush()
                        subprocess.run(
                            ["aws", "--profile", args.profile, "ssm", "put-parameter", "--region", "us-west-2", "--cli-input-json", "file://" + parameter.name],
                            capture_output=True, text=True, check=True,
                        )
                pending.unlink()
                result.update({"id": app["id"], "slug": app["slug"], "html_url": app["html_url"], "status": "stored-in-ssm"})
                print(json.dumps(result), flush=True)
                installation = f'https://github.com/apps/{app["slug"]}/installations/new'
                self.respond(200, '<!doctype html><meta charset="utf-8"><title>GitHub App ready</title>'
                             '<h1>GitHub App created</h1><p>Credentials were stored securely in AWS.</p>'
                             f'<p><a href="{html.escape(installation, quote=True)}">Install only on Innovate-To-Grow-Website</a></p>')
            except Exception as error:
                print(f"Setup failed: {type(error).__name__}", flush=True)
                self.respond(500, "Setup failed. Review the local server status before retrying.")

    print(f"Open http://127.0.0.1:{args.port}/ to review the GitHub App.", flush=True)
    HTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
