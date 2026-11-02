#!/usr/bin/env python3
"""Publish kellypage.app to Cloudflare Pages from this PC (stdlib only).

  python publish.py [--env PATH_TO_.env] [--dry]

Builds _site/: the site files, plus the Kelly Page release named in latest.json unzipped into app/ (downloaded from
downloads.kellypage.app and checked against its SHA-256). Then uploads it with Cloudflare's Pages direct-upload API
and makes it the live deployment of the "kellypage" project.

Credentials: CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID from the environment, else from the .env file given with
--env (default: ../P25X-Radio-Project/.env). They are never written into this repo or printed.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import mimetypes
import os
import shutil
import sys
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = "kellypage"
API = "https://api.cloudflare.com/client/v4"
SITE = ["index.html", "download.html", "raspberry-pi.html", "mesh-buddy.html", "guides.html", "tips.html", "about.html",
        "404.html", "latest.json", "robots.txt", "sitemap.xml", "_headers", ".well-known", "css", "js", "assets", "guides"]
mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("text/javascript", ".js")


def creds(env_path: Path) -> tuple[str, str]:
    tok, acc = os.environ.get("CLOUDFLARE_API_TOKEN"), os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    if not (tok and acc) and env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            k, _, v = line.partition("=")
            v = v.strip().strip('"').strip("'")
            if k.strip() == "CLOUDFLARE_API_TOKEN" and not tok:
                tok = v
            if k.strip() == "CLOUDFLARE_ACCOUNT_ID" and not acc:
                acc = v
    if not (tok and acc):
        sys.exit("publish: CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID not found (environment or --env file)")
    return tok, acc


def call(method, url, token, body=None, ctype="application/json"):
    data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
    r = urllib.request.Request(url, data=data, method=method, headers={"Authorization": "Bearer " + token, "Content-Type": ctype})
    try:
        with urllib.request.urlopen(r, timeout=300) as x:
            return json.loads(x.read())
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return json.loads(raw)
        except ValueError:
            return {"success": False, "errors": [{"message": f"HTTP {e.code}: {raw[:200]!r}"}]}


def must(res, what):
    if not res.get("success"):
        sys.exit(f"publish: {what} failed: {res.get('errors')}")
    return res.get("result")


def build() -> Path:
    out = HERE / "_site"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir()
    for item in SITE:
        src = HERE / item
        (shutil.copytree if src.is_dir() else shutil.copy2)(src, out / item)
    latest = json.loads((HERE / "latest.json").read_text(encoding="utf-8"))
    req = urllib.request.Request(latest["files"]["zip"], headers={"User-Agent": "kellypage-publish/1.0"})   # Python's default UA gets a 403
    with urllib.request.urlopen(req, timeout=300) as x:
        zdata = x.read()
    if hashlib.sha256(zdata).hexdigest() != latest["sha256"]:
        sys.exit("publish: the release zip on downloads.kellypage.app doesn't match latest.json's sha256")
    with zipfile.ZipFile(io.BytesIO(zdata)) as z:
        for n in z.namelist():
            if n.endswith("/") or not n.startswith("Kelly Page/"):
                continue
            dest = out / "app" / n[len("Kelly Page/"):]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(z.read(n))
    print(f"publish: built _site with Kelly Page {latest['version']} in app/")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--env", default=str(HERE.parent / "P25X-Radio-Project" / ".env"))
    ap.add_argument("--dry", action="store_true", help="build _site only")
    a = ap.parse_args()
    site = build()
    files = {}
    for p in sorted(site.rglob("*")):
        if p.is_file() and p.name != "_headers":
            rel = "/" + p.relative_to(site).as_posix()
            data = p.read_bytes()
            if len(data) > 25 * 1024 * 1024:
                sys.exit(f"publish: {rel} is over Pages' 25 MiB file limit")
            b64 = base64.b64encode(data).decode()
            h = hashlib.sha256((b64 + p.suffix.lstrip(".")).encode()).hexdigest()[:32]
            files[rel] = (h, b64, mimetypes.guess_type(p.name)[0] or "application/octet-stream")
    print(f"publish: {len(files)} files, {sum(len(v[1]) for v in files.values()) * 3 // 4 // 1024} KB")
    if a.dry:
        return
    tok, acc = creds(Path(a.env))
    jwt = must(call("GET", f"{API}/accounts/{acc}/pages/projects/{PROJECT}/upload-token", tok), "upload token")["jwt"]
    hashes = sorted({v[0] for v in files.values()})
    missing = set(must(call("POST", f"{API}/pages/assets/check-missing", jwt, {"hashes": hashes}), "check-missing"))
    todo = [v for v in {v[0]: v for v in files.values()}.values() if v[0] in missing]
    batch, size = [], 0
    for i, (h, b64, ct) in enumerate(todo):
        batch.append({"key": h, "value": b64, "metadata": {"contentType": ct}, "base64": True})
        size += len(b64)
        if i == len(todo) - 1 or size > 40 * 1024 * 1024 or len(batch) >= 1000:
            must(call("POST", f"{API}/pages/assets/upload", jwt, batch), "upload")
            batch, size = [], 0
    must(call("POST", f"{API}/pages/assets/upsert-hashes", jwt, {"hashes": hashes}), "upsert-hashes")
    print(f"publish: uploaded {len(todo)} new files ({len(hashes) - len(todo)} already there)")
    manifest = {k: v[0] for k, v in files.items()}
    bnd = uuid.uuid4().hex
    parts = [("manifest", json.dumps(manifest).encode(), None), ("branch", b"main", None),
             ("commit_message", b"publish.py", None), ("commit_dirty", b"true", None),
             ("_headers", (site / "_headers").read_bytes(), "_headers")]
    body = b""
    for name, val, fname in parts:
        body += f"--{bnd}\r\nContent-Disposition: form-data; name=\"{name}\"".encode()
        body += (f"; filename=\"{fname}\"\r\nContent-Type: application/octet-stream" if fname else "").encode()
        body += b"\r\n\r\n" + val + b"\r\n"
    body += f"--{bnd}--\r\n".encode()
    d = must(call("POST", f"{API}/accounts/{acc}/pages/projects/{PROJECT}/deployments", tok, body,
                  f"multipart/form-data; boundary={bnd}"), "deployment")
    print(f"publish: deployed {d.get('id', '?')[:8]} -> {d.get('url')} (live at https://kellypage.app once it's ready)")


if __name__ == "__main__":
    main()
