#!/usr/bin/env python3
"""Read-only verification of this source package's manifest. Does not test the website."""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    errors: list[str] = []
    try:
        manifest = json.loads((root / "SHA256SUMS.json").read_text(encoding="utf-8"))
        entries = manifest["files"]
        if not isinstance(entries, list):
            raise ValueError("manifest files must be a list")
    except (OSError, ValueError, KeyError) as exc:
        print(f"FAIL: cannot read manifest: {exc}", file=sys.stderr)
        return 2
    for item in entries:
        try:
            relative = Path(item["path"])
            candidate = root / relative
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("unsafe relative path")
            target = candidate.resolve()
            if not target.is_relative_to(root) or candidate.is_symlink():
                raise ValueError("path escapes root or is a symlink")
            if not target.is_file():
                raise ValueError("file missing")
            if target.stat().st_size != item["bytes"]:
                raise ValueError("size mismatch")
            if sha256(target) != item["sha256"]:
                raise ValueError("SHA-256 mismatch")
        except (OSError, ValueError, KeyError) as exc:
            errors.append(f"{item.get('path', '<invalid entry>')}: {exc}")
    if errors:
        print("FAIL: source package verification", file=sys.stderr)
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(f"PASS: {len(entries)} source package files match the manifest.")
    print("This is a file-integrity result, not website, browser, Windows, or translation testing.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
