#!/usr/bin/env python3
"""CyberSaarthi desktop importer.

Prepares a signed evidence package from a USB drive / MTP export and submits it
to the server's ``POST /api/v1/import/packages`` endpoint.

The package follows the deterministic layout produced by the Android field agent:

    <package>/
      manifest.json        # signed document (canonical form)
      manifest.sig         # RSA-SHA256 / Ed25519 signature over canonical bytes
      evidence/<n>         # raw evidence files referenced by manifest

This tool is intentionally stdlib-only. Signature generation shells out to the
system ``openssl`` binary; the server re-verifies every package authoritatively
(device binding, signature, per-file SHA-256, replay and duplicate checks), so
this CLI can never bypass validation.

Usage:
    cybersaarthi_importer.py make-manifest <package> --device-serial <s> \
        --case-id <uuid> [--collection "Call Logs"] [--agent <name>]
    cybersaarthi_importer.py sign <package> --key <private_key.pem> [--alg RSA-SHA256|Ed25519]
    cybersaarthi_importer.py verify <package> --key <public_key.pem>
    cybersaarthi_importer.py submit <package> --base-url http://localhost:8000 \
        --token <bearer> --case-id <uuid>
    cybersaarthi_importer.py inspect <package>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"
CANONICAL_KEYS = ["schema_version", "case_id", "device_serial", "collection_name", "evidence_files"]


def _canonical_bytes(manifest: dict[str, Any]) -> bytes:
    canonical = {key: manifest.get(key) for key in CANONICAL_KEYS}
    return json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _discover_evidence(package_dir: Path) -> list[Path]:
    evidence_dir = package_dir / "evidence"
    if not evidence_dir.is_dir():
        return []
    return sorted(p for p in evidence_dir.iterdir() if p.is_file())


def _agent_name() -> str:
    return os.environ.get("CYBERSAARTHI_IMPORTER_AGENT", "desktop-importer")


def cmd_make_manifest(args: argparse.Namespace) -> int:
    package = Path(args.package)
    evidence = _discover_evidence(package)
    if not evidence:
        print(f"error: no files found under {package / 'evidence'}", file=sys.stderr)
        return 2
    entries = [
        {
            "filename": p.name,
            "sha256": sha256_of_file(p),
            "size_bytes": p.stat().st_size,
            "captured_at": datetime.fromtimestamp(p.stat().st_mtime, UTC).isoformat(),
            "source": "usb_import",
        }
        for p in evidence
    ]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "case_id": args.case_id,
        "device_serial": args.device_serial,
        "collection_name": args.collection,
        "evidence_files": entries,
        "generated_at": datetime.now(UTC).isoformat(),
        "generated_by": _agent_name(),
    }
    target = package / "manifest.json"
    target.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote {target} with {len(entries)} evidence file(s)")
    return 0


def _run_openssl(args: list[str], input_data: bytes | None = None) -> bytes:
    process = subprocess.run(args, input=input_data, capture_output=True, check=True)
    return process.stdout


def cmd_sign(args: argparse.Namespace) -> int:
    package = Path(args.package)
    manifest_path = package / "manifest.json"
    if not manifest_path.is_file():
        print(f"error: {manifest_path} missing (run make-manifest first)", file=sys.stderr)
        return 2
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    canonical = _canonical_bytes(manifest)
    key = Path(args.key)
    algorithm = manifest.get("signature_algorithm") or args.alg
    if algorithm == "Ed25519":
        args_list = ["openssl", "pkeyutl", "-sign", "-inkey", str(key), "-rawin"]
    else:
        args_list = ["openssl", "dgst", "-sha256", "-sign", str(key)]  # noqa: S607
    try:
        signature = _run_openssl(args_list, canonical)
    except subprocess.CalledProcessError as exc:
        print(f"error: signing failed: {exc.stderr.decode()}", file=sys.stderr)
        return 2
    (package / "manifest.sig").write_bytes(signature)
    print(f"wrote {package / 'manifest.sig'} ({len(signature)} bytes)")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    package = Path(args.package)
    sig_path = package / "manifest.sig"
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    canonical = _canonical_bytes(manifest)
    for entry in manifest["evidence_files"]:
        candidate = package / "evidence" / entry["filename"]
        if not candidate.is_file():
            print(f"error: missing evidence file {entry['filename']}", file=sys.stderr)
            return 2
        if sha256_of_file(candidate) != entry["sha256"]:
            print(f"error: hash mismatch for {entry['filename']}", file=sys.stderr)
            return 2
    if args.alg == "Ed25519":
        args_list = [
            "openssl", "pkeyutl", "-verify", "-pubin", "-inkey", str(args.key),
            "-signature", str(sig_path), "-rawin",
        ]
    else:
        args_list = [
            "openssl", "dgst", "-sha256", "-verify", str(args.key),
            "-signature", str(sig_path),
        ]
    process = subprocess.run(args_list, input=canonical, capture_output=True)
    if process.returncode == 0 and b"Verified OK" in process.stdout:
        print(process.stdout.decode().strip())
        return 0
    print("error: signature verification failed", file=sys.stderr)
    return 1


def cmd_submit(args: argparse.Namespace) -> int:
    package = Path(args.package)
    for required in ("manifest.json", "manifest.sig"):
        if not (package / required).is_file():
            print(f"error: {required} missing (run make-manifest/sign first)", file=sys.stderr)
            return 2
    boundary = "----cybersaarthi" + uuid.uuid4().hex
    body = bytearray()

    def _append_field(name: str, filename: str | None, content: bytes, content_type: str) -> None:
        body.extend(f"--{boundary}\r\n".encode())
        disposition = f'form-data; name="{name}"'
        if filename is not None:
            disposition += f'; filename="{filename}"'
        body.extend(f"Content-Disposition: {disposition}\r\n".encode())
        body.extend(f"Content-Type: {content_type}\r\n\r\n".encode())
        body.extend(content)
        body.extend(b"\r\n")

    _append_field("manifest", "manifest.json", (package / "manifest.json").read_bytes(), "application/json")
    _append_field("manifest_signature", "manifest.sig", (package / "manifest.sig").read_bytes(), "application/octet-stream")
    for entry in json.loads((package / "manifest.json").read_text(encoding="utf-8"))["evidence_files"]:
        candidate = package / "evidence" / entry["filename"]
        _append_field(
            "files", entry["filename"], candidate.read_bytes(),
            "application/octet-stream",
        )
    body.extend(f"--{boundary}--\r\n".encode())

    url = f"{args.base_url.rstrip('/')}/api/v1/cases/{args.case_id}/import/packages"
    request = urllib.request.Request(
        url,
        data=bytes(body),
        headers={
            "Authorization": f"Bearer {args.token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=args.timeout) as response:  # noqa: S310
            payload = response.read().decode()
            print(f"HTTP {response.status}: {payload}")
            return 0 if response.status == 201 else 1
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.read().decode()}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"error: {exc.reason}", file=sys.stderr)
        return 1


def cmd_inspect(args: argparse.Namespace) -> int:
    package = Path(args.package)
    manifest_path = package / "manifest.json"
    if not manifest_path.is_file():
        print(f"error: {manifest_path} missing", file=sys.stderr)
        return 2
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sig_path = package / "manifest.sig"
    print(f"schema_version : {manifest.get('schema_version')}")
    print(f"case_id        : {manifest.get('case_id')}")
    print(f"device_serial  : {manifest.get('device_serial')}")
    print(f"collection     : {manifest.get('collection_name')}")
    print(f"evidence files : {len(manifest.get('evidence_files', []))}")
    print(
        f"manifest.sig   : present={sig_path.is_file()}, "
        f"bytes={sig_path.stat().st_size if sig_path.is_file() else 0}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="cybersaarthi_importer", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    mk = sub.add_parser("make-manifest", help="build manifest.json for a package directory")
    mk.add_argument("package", help="package directory containing evidence/")
    mk.add_argument("--device-serial", required=True, help="approved FieldDevice serial")
    mk.add_argument("--case-id", required=True, help="target case UUID")
    mk.add_argument("--collection", default=None, help="collection name (optional)")
    mk.set_defaults(func=cmd_make_manifest)

    sign = sub.add_parser("sign", help="sign manifest.json with the device private key")
    sign.add_argument("package")
    sign.add_argument("--key", required=True, help="path to device private key (PEM)")
    sign.add_argument("--alg", choices=["RSA-SHA256", "Ed25519"], default="RSA-SHA256")
    sign.set_defaults(func=cmd_sign)

    verify = sub.add_parser("verify", help="locally verify a package hash + signature")
    verify.add_argument("package")
    verify.add_argument("--key", required=True, help="path to device public key (PEM)")
    verify.add_argument("--alg", choices=["RSA-SHA256", "Ed25519"], default="RSA-SHA256")
    verify.set_defaults(func=cmd_verify)

    submit = sub.add_parser("submit", help="POST the package to the server")
    submit.add_argument("package")
    submit.add_argument("--base-url", required=True, help="e.g. http://localhost:8000")
    submit.add_argument("--token", required=True, help="bearer access token")
    submit.add_argument("--case-id", required=True, help="target case UUID")
    submit.add_argument("--timeout", type=int, default=60)
    submit.set_defaults(func=cmd_submit)

    inspect = sub.add_parser("inspect", help="print package manifest summary")
    inspect.add_argument("package")
    inspect.set_defaults(func=cmd_inspect)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())