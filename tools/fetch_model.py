#!/usr/bin/env python
"""Download the T-one acoustic model used by Live Captions RU.

The model is not stored in the repository (100 MB git limit). It is downloaded
from the sherpa-onnx Hugging Face repository and verified by SHA-256.

Usage:
    python tools/fetch_model.py            # into models/t-one
    python tools/fetch_model.py --check    # only verify the existing file
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "models" / "t-one"
BASE = "https://huggingface.co/csukuangfj/sherpa-onnx-streaming-t-one-russian-2025-09-08/resolve/main"
FILES = {
    "model.onnx": "5ded080e2a6c86ecc11bcb0902d77524eb3e8b0844cb0c0754347f5aafb4dabc",
    "tokens.txt": None,  # small text file, no published hash
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def download(name: str, expected: str | None) -> int:
    target = TARGET / name
    if target.exists() and (expected is None or sha256(target) == expected):
        print(f"ok {name} (already present)")
        return 0
    url = f"{BASE}/{name}"
    print(f"downloading {name} from {url}")
    partial = target.with_suffix(target.suffix + ".part")
    with urllib.request.urlopen(url) as response, partial.open("wb") as out:
        total = int(response.headers.get("Content-Length", 0))
        done = 0
        while True:
            block = response.read(1 << 20)
            if not block:
                break
            out.write(block)
            done += len(block)
            if total:
                print(f"\r  {done / 1048576:.1f} / {total / 1048576:.1f} MB", end="")
    print()
    if expected and sha256(partial) != expected:
        partial.unlink()
        print(f"checksum mismatch for {name}", file=sys.stderr)
        return 3
    partial.replace(target)
    print(f"ok {name}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch T-one model files")
    parser.add_argument("--check", action="store_true", help="verify local files only")
    args = parser.parse_args()

    TARGET.mkdir(parents=True, exist_ok=True)
    for name, expected in FILES.items():
        if args.check:
            path = TARGET / name
            if not path.exists():
                print(f"missing {name}", file=sys.stderr)
                return 2
            if expected and sha256(path) != expected:
                print(f"checksum mismatch for {name}", file=sys.stderr)
                return 3
            print(f"ok {name}")
            continue
        code = download(name, expected)
        if code:
            return code
    return 0


if __name__ == "__main__":
    sys.exit(main())
