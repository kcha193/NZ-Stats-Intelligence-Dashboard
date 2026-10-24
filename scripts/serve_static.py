#!/usr/bin/env python3
"""Serve a built static site with the redirects and headers from netlify.toml and _redirects.

For local checks and CI only: it reproduces the documented Netlify rules (first match wins, a real file beats a
non-forced rewrite, status 404 serves the target with that status, unmatched paths get 404.html) so the browser tests
see the same routing and security headers the deployed site will send. Netlify itself is the final authority; the
first deploy is checked against a draft URL (docs/netlify-deployment.md).

    python3 scripts/serve_static.py frontend/dist-static --port 4173 [--toml netlify.toml]
"""

from __future__ import annotations

import argparse
import hashlib
import mimetypes
import tomllib
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

mimetypes.add_type("application/json", ".json")
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("image/svg+xml", ".svg")


@dataclass(frozen=True)
class Rule:
    source: str
    target: str
    status: int
    force: bool = False

    def matches(self, path: str) -> bool:
        src = self.source
        if src.endswith("/*"):
            base = src[:-2]
            return path == base or path.startswith(base + "/")
        return path.rstrip("/") == src.rstrip("/") or path == src


def load_rules(root: Path, toml_path: Path | None) -> list[Rule]:
    rules: list[Rule] = []
    redirects = root / "_redirects"  # Netlify applies _redirects before netlify.toml
    if redirects.exists():
        for line in redirects.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                src, dst, *rest = line.split()
                status = int(rest[0].rstrip("!")) if rest else 301
                rules.append(Rule(src, dst, status, bool(rest) and rest[0].endswith("!")))
    if toml_path:
        for r in tomllib.loads(toml_path.read_text(encoding="utf-8")).get("redirects", []):
            rules.append(Rule(r["from"], r["to"], int(r.get("status", 301)), bool(r.get("force", False))))
    return rules


def load_headers(toml_path: Path | None) -> list[tuple[str, dict[str, str]]]:
    if not toml_path:
        return []
    cfg = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    return [(h["for"], h["values"]) for h in cfg.get("headers", [])]


def header_applies(pattern: str, path: str) -> bool:
    if pattern.endswith("/*"):
        return path.startswith(pattern[:-1]) or path == pattern[:-2]
    return path == pattern


class Handler(BaseHTTPRequestHandler):
    root: Path
    rules: list[Rule]
    header_rules: list[tuple[str, dict[str, str]]]
    server_version = "static-netlify-emulator"

    def log_message(self, fmt, *args):  # noqa: D102 - quiet
        pass

    def _file(self, url_path: str) -> Path | None:
        rel = unquote(url_path).lstrip("/")
        target = (self.root / rel).resolve()
        if self.root not in target.parents and target != self.root:
            return None
        if target.is_dir():
            target = target / "index.html"
        return target if target.is_file() else None

    def resolve(self, path: str) -> tuple[int, Path | None]:
        direct = self._file(path)
        for rule in self.rules:
            if not rule.matches(path):
                continue
            if direct and not rule.force:
                break  # shadowing is off: a real file wins
            if rule.status in (301, 302, 307, 308):
                return rule.status, Path(rule.target)
            return rule.status, self._file(rule.target)
        if direct:
            return 200, direct
        not_found = self._file("/404.html")
        return 404, not_found

    def do_GET(self):  # noqa: N802
        self._respond(send_body=True)

    def do_HEAD(self):  # noqa: N802
        self._respond(send_body=False)

    def _respond(self, *, send_body: bool) -> None:
        path = urlsplit(self.path).path
        status, file = self.resolve(path)
        if status in (301, 302, 307, 308):
            self.send_response(status)
            self.send_header("Location", str(file))
            self.end_headers()
            return
        body = file.read_bytes() if file else b"Not found"
        ctype = (mimetypes.guess_type(file.name)[0] if file else None) or "text/plain"
        etag = '"' + hashlib.sha1(body).hexdigest() + '"'  # noqa: S324 - cache validator, not security
        if status == 200 and self.headers.get("If-None-Match") == etag:
            self.send_response(HTTPStatus.NOT_MODIFIED)
            self.send_header("ETag", etag)
            self.end_headers()
            return
        self.send_response(status)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text/") else ""))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("ETag", etag)
        merged: dict[str, str] = {}
        for pattern, values in self.header_rules:
            if header_applies(pattern, path):
                merged.update(values)
        for name, value in merged.items():
            self.send_header(name, value)
        self.end_headers()
        if send_body:
            self.wfile.write(body)


class Server(ThreadingHTTPServer):
    request_queue_size = 256  # a page opens dozens of connections at once; the default backlog of 5 resets some
    daemon_threads = True


def make_server(root: Path, toml_path: Path | None, port: int) -> ThreadingHTTPServer:
    class Bound(Handler):
        pass

    Bound.root = root.resolve()
    Bound.rules = load_rules(root, toml_path)
    Bound.header_rules = load_headers(toml_path)
    return Server(("127.0.0.1", port), Bound)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", type=Path)
    parser.add_argument("--port", type=int, default=4173)
    parser.add_argument("--toml", type=Path, default=Path(__file__).resolve().parents[1] / "netlify.toml")
    args = parser.parse_args()
    server = make_server(args.root, args.toml if args.toml.exists() else None, args.port)
    print(f"serving {args.root} on http://127.0.0.1:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
