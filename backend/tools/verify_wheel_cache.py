"""Verify the platform-specific offline wheels against the release manifest."""

import argparse
import hashlib
import json
from pathlib import Path


def verify(root, manifest):
    root = Path(root).resolve()
    entries = json.loads(Path(manifest).read_text(encoding="utf-8"))["files"]
    for entry in entries:
        name = entry["name"]
        if Path(name).name != name or not name.endswith(".whl"):
            raise ValueError("Invalid wheel filename")
        target = root / name
        if (
            not target.is_file()
            or hashlib.sha256(target.read_bytes()).hexdigest() != entry["sha256"]
        ):
            raise ValueError("Offline wheel checksum mismatch: " + name)
    return entries


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()
    print(json.dumps({"verified": len(verify(args.root, args.manifest))}))
