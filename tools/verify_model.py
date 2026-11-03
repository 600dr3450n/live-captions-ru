#!/usr/bin/env python3
"""Verify the T-one model files against the checksums the release ships.

The model is distributed inside the release package, not downloaded, so this script
only checks what is already on disk. Two callers exist: a developer who dropped the
model into models/t-one, and CI, which has to fail when the file differs from the one
the binaries were built and measured with.

Usage:
    python tools/verify_model.py                    # checks models/t-one
    python tools/verify_model.py --dir build/models/t-one

Exit codes: 0 both files match, 1 a file differs in size or checksum, 2 the directory
or one of the files is absent.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = ROOT / "models" / "t-one"

# fp32 export shipped with the release: 287 475 849 bytes.
FILES = {
    "model.onnx": ("4a3827b04ef683fe0cffbb47161dd146aa19f8db503902e0ba2de5529d82249e", 287475849),
    "tokens.txt": ("27f7b3ba2096c572375fba1a6b29af1f80d86e08a329940612908112695f97e0", 202),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def check(model_dir: Path) -> int:
    if not model_dir.is_dir():
        print(f"missing directory {model_dir}", file=sys.stderr)
        return 2
    failed = 0
    missing = 0
    for name, (expected_sha, expected_size) in FILES.items():
        path = model_dir / name
        if not path.exists():
            print(f"missing {path}", file=sys.stderr)
            missing += 1
            continue
        size = path.stat().st_size
        if size != expected_size:
            print(f"size mismatch {name}: {size} != {expected_size}", file=sys.stderr)
            failed += 1
            continue
        actual = sha256(path)
        if actual != expected_sha:
            print(f"checksum mismatch {name}: {actual} != {expected_sha}", file=sys.stderr)
            failed += 1
            continue
        print(f"ok {name} ({size} bytes)")
    if missing:
        return 2
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the T-one model files")
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR, help="model directory")
    return check(parser.parse_args().dir)


if __name__ == "__main__":
    sys.exit(main())
