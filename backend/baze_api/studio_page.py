"""The dummy page served from the Studio Invoices container."""

from __future__ import annotations

from pathlib import Path

from baze_api.app_favicon import ensure_favicon_link, render_app_favicon

PAGE_PORT = 8080
HARNESS_OFFSET = 100
PAGE_MARKER = 'data-baze-app="studio-invoices" data-baze-build="2"'

_RUN = """#!/bin/sh
# The harness stays in this container. This process is the page.
hermes gateway run >>/opt/data/app/gateway.log 2>&1 &
exec /opt/hermes/.venv/bin/python3 /opt/data/app/server.py
"""

_SERVER = """from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TYPES = {".html": "text/html; charset=utf-8", ".svg": "image/svg+xml"}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/health":
            body = b'{"status":"ok"}'
            self._send(200, "application/json", body)
            return
        name = "index.html" if path in ("/", "/index.html") else path.lstrip("/")
        file = (ROOT / name).resolve()
        if ROOT not in file.parents or not file.is_file():
            self._send(404, "text/plain; charset=utf-8", b"Not found")
            return
        self._send(200, TYPES.get(file.suffix, "application/octet-stream"), file.read_bytes())

    def _send(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
"""

def _page(_app_id: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Studio Invoices</title>
  <link rel="icon" href="favicon.svg" type="image/svg+xml">
  <style>
    :root {{ color-scheme: light; }}
    body {{
      margin: 0;
      background: #f4f7f2;
      color: #14210f;
      font: 16px/1.45 "Red Hat Text", "Segoe UI", sans-serif;
    }}
    main {{ max-width: 40rem; margin: 0 auto; padding: 2.5rem 1.25rem; }}
    h1 {{ margin: 0 0 0.35rem; font-size: 1.8rem; letter-spacing: -0.02em; }}
    p {{ margin: 0 0 1.5rem; color: #3d5344; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 0.75rem; overflow: hidden; }}
    th, td {{ text-align: left; padding: 0.75rem 1rem; border-bottom: 1px solid #e4ece6; }}
    th {{ font-size: 0.75rem; letter-spacing: 0.04em; text-transform: uppercase; color: #5c7264; }}
    tr:last-child td {{ border-bottom: 0; }}
    .paid {{ color: #15803d; }}
  </style>
</head>
<body {PAGE_MARKER}>
  <main>
    <h1>Studio Invoices</h1>
    <p>A sample page served from this app’s container.</p>
    <table>
      <thead><tr><th>Invoice</th><th>Client</th><th>Status</th></tr></thead>
      <tbody>
        <tr><td>INV-1042</td><td>Sample client</td><td class="paid">Paid</td></tr>
        <tr><td>INV-1048</td><td>Another sample</td><td>Due</td></tr>
      </tbody>
    </table>
  </main>
</body>
</html>
"""


PLACEHOLDER_MARKER = 'data-baze-build="placeholder"'


def refresh_app_favicon(data_dir: str, color: str, icon: str) -> None:
    """Write the shelf icon beside an app that already exists, without touching its page."""
    root = Path(data_dir)
    if not root.is_dir():
        return
    page = root / "app"
    page.mkdir(parents=True, exist_ok=True)
    (page / "favicon.svg").write_text(render_app_favicon(color, icon))
    index = page / "index.html"
    if not index.is_file():
        return
    text = index.read_text(encoding="utf-8", errors="replace")
    updated = ensure_favicon_link(text)
    if updated != text:
        index.write_text(updated)


def write_host_files(data_dir: str, index_html: str, *, color: str, icon: str) -> None:
    """The page server and the harness launcher. The agent replaces index.html."""
    root = Path(data_dir) / "app"
    root.mkdir(parents=True, exist_ok=True)
    (root / "index.html").write_text(index_html)
    (root / "favicon.svg").write_text(render_app_favicon(color, icon))
    (root / "server.py").write_text(_SERVER)
    script = root / "run.sh"
    script.write_text(_RUN)
    script.chmod(0o755)


def placeholder_page(app_id: str, name: str) -> str:
    title = (
        name.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    return f"""<!doctype html>
<html lang="en">
<head><link rel="icon" href="favicon.svg" type="image/svg+xml"></head>
<body data-baze-app="{app_id}" {PLACEHOLDER_MARKER}>
<main><h1>{title}</h1><p>This app is being written.</p></main>
</body></html>
"""


def page_file_ready(data_dir: str) -> bool:
    path = Path(data_dir) / "app" / "index.html"
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8", errors="replace")
    return PLACEHOLDER_MARKER not in text and "<html" in text.lower()


def extract_html(reply: str) -> str | None:
    text = reply.strip()
    fence = text.find("```")
    if fence != -1:
        rest = text[fence + 3 :]
        if rest.lower().startswith("html"):
            rest = rest[4:]
        end = rest.rfind("```")
        if end != -1:
            text = rest[:end].strip()
    lowered = text.lower()
    start = lowered.find("<!doctype html")
    if start == -1:
        start = lowered.find("<html")
    if start == -1:
        return None
    end = lowered.rfind("</html>")
    if end == -1:
        return None
    return text[start : end + len("</html>")]


def save_reply_page(data_dir: str, reply: str) -> bool:
    if page_file_ready(data_dir):
        return True
    html = extract_html(reply)
    if not html:
        return False
    (Path(data_dir) / "app" / "index.html").write_text(ensure_favicon_link(html))
    return page_file_ready(data_dir)


def write_studio_page(data_dir: str, app_id: str, *, color: str, icon: str) -> None:
    write_host_files(data_dir, _page(app_id), color=color, icon=icon)
