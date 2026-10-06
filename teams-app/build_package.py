"""Build the Teams app package (manifest + icons) that grants chat-level read access via RSC.

Usage:
    uv run python teams-app/build_package.py --app-id <Graph app (client) ID> [--version 1.0.0]

Output: teams-app/build/pmo-intelligence-teams-app.zip
"""

import argparse
import json
import pathlib
import re
import sys
import zipfile

HERE = pathlib.Path(__file__).resolve().parent
GUID = re.compile(r"^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$", re.IGNORECASE)
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--app-id", required=True, help="Entra application (client) ID of 'PMO Intelligence Graph'")
    parser.add_argument("--version", default="1.0.0", help="Package version; bump it for every re-upload")
    args = parser.parse_args()

    if not GUID.match(args.app_id):
        sys.exit(f"--app-id must be a GUID, got {args.app_id!r}")
    if not SEMVER.match(args.version):
        sys.exit(f"--version must look like 1.0.0, got {args.version!r}")

    template = (HERE / "manifest.template.json").read_text(encoding="utf-8")
    manifest = json.loads(template.replace("{{ENTRA_APP_ID}}", args.app_id).replace("{{VERSION}}", args.version))
    if "{{" in json.dumps(manifest):
        sys.exit("Unfilled placeholder left in manifest.template.json")

    out_dir = HERE / "build"
    out_dir.mkdir(exist_ok=True)
    zip_path = out_dir / "pmo-intelligence-teams-app.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        zf.write(HERE / "color.png", "color.png")
        zf.write(HERE / "outline.png", "outline.png")

    perms = [p["name"] for p in manifest["authorization"]["permissions"]["resourceSpecific"]]
    print(f"Built {zip_path}")
    print(f"  Teams app ID: {manifest['id']}  version {manifest['version']}")
    print(f"  Entra app ID: {args.app_id}")
    print(f"  RSC permissions: {', '.join(perms)}")


if __name__ == "__main__":
    main()
