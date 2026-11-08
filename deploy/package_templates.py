"""Build a reproducible PUBLIC example pack; never reads runtime school materials."""
import argparse
import hashlib
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "testTemp" / "release" / "AwardCollection-starter-templates.zip")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    files = [ROOT / "examples/README.md", ROOT / "LICENSE", *sorted((ROOT / "examples/templates").glob("*.json"))]
    if len(files) != 5:
        raise SystemExit("Expected exactly three reviewed public templates")
    with zipfile.ZipFile(args.output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            name = "LICENSE" if path.name == "LICENSE" else path.relative_to(ROOT / "examples").as_posix()
            entry = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, path.read_bytes())
    with args.output.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    args.output.with_suffix(".zip.sha256").write_text(checksum + "  " + args.output.name + "\n", encoding="utf8")
    print(f"{args.output.name}: {checksum}")


if __name__ == "__main__":
    main()
