#!/usr/bin/env python3
"""
Generate lab device apps report from MongoDB careai.devices.

Output: one CSV row per active device with location hierarchy, firmware,
selected installed apps (sensorData.installedApps), and capabilities.

Usage:
  export MONGODB_URI='mongodb+srv://...'
  python scripts/generate_lab_device_apps_report.py

Or place MONGODB_URI in .env at the project root.
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from pathlib import Path

try:
    from pymongo import MongoClient
except ImportError:
    print("Error: pymongo is required. Install with: pip install pymongo", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT / "reports" / "lab_device_apps_report.csv"

AI_CARE_PREFIX = re.compile(r"^ai\.care\.", re.IGNORECASE)
R2O_RELEASE_SUFFIX = re.compile(r"\.?r2o\.release$", re.IGNORECASE)

APPS_OF_INTEREST = [
    "am.release",
    "ipm",
    "nlp",
    "r2c_upgrade",
    "r2u_upgrade",
    "r2x_upgrade",
    "reg",
    "sen",
    "tuner",
    "tv",
    "vc",
]

IDENTITY_COLS = [
    "tenant",
    "device_id",
    "device_type",
    "location",
    "facility",
    "area",
]


def load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def normalize_app_name(name: str) -> str:
    name = (name or "").strip()
    name = AI_CARE_PREFIX.sub("", name)
    name = R2O_RELEASE_SUFFIX.sub("", name)
    return name.rstrip(".")


def device_firmware(dev: dict) -> str:
    fv = dev.get("firmwareVersion")
    if fv:
        return str(fv).strip()
    fw = dev.get("firmware")
    if isinstance(fw, dict):
        v = fw.get("version") or fw.get("code")
        if v:
            return str(v).strip()
    elif fw:
        return str(fw).strip()
    return ""


def flatten_capabilities(caps) -> list[str]:
    out: list[str] = []
    for item in caps or []:
        if isinstance(item, list):
            out.extend(flatten_capabilities(item))
        elif item is not None:
            out.append(str(item).strip())
    return out


def extract_installed_apps(dev: dict) -> dict[str, str]:
    apps: dict[str, str] = {}
    for entry in (dev.get("sensorData") or {}).get("installedApps") or []:
        if not isinstance(entry, dict):
            continue
        raw_name = (
            entry.get("name")
            or entry.get("appName")
            or entry.get("packageName")
            or ""
        ).strip()
        if not raw_name:
            continue
        name = normalize_app_name(raw_name)
        if name not in APPS_OF_INTEREST:
            continue
        ver = entry.get("version")
        apps[name] = "" if ver is None else str(ver).strip()
    return apps


def hierarchy_value(dev: dict, name_key: str, id_key: str) -> str:
    return (dev.get(name_key) or dev.get(id_key) or "").strip()


def build_report(uri: str, active_only: bool = True) -> tuple[list[dict], list[str]]:
    client = MongoClient(uri, serverSelectionTimeoutMS=30_000)
    db = client["careai"]

    query = {"isActive": True} if active_only else {}
    projection = {
        "deviceId": 1,
        "customer": 1,
        "type": 1,
        "unit": 1,
        "unitName": 1,
        "location": 1,
        "locationName": 1,
        "area": 1,
        "areaName": 1,
        "sensorData": 1,
        "capabilities": 1,
        "firmwareVersion": 1,
        "firmware": 1,
        "isActive": 1,
    }

    all_capabilities: set[str] = set()
    device_rows: list[dict] = []

    for dev in db.devices.find(query, projection):
        caps = flatten_capabilities(dev.get("capabilities"))
        all_capabilities.update(caps)
        device_rows.append(
            {
                "tenant": dev.get("customer") or "",
                "device_id": dev.get("deviceId") or "",
                "device_type": dev.get("type") or "",
                "location": hierarchy_value(dev, "locationName", "location"),
                "facility": hierarchy_value(dev, "unitName", "unit"),
                "area": hierarchy_value(dev, "areaName", "area"),
                "firmware_version": device_firmware(dev),
                "apps": extract_installed_apps(dev),
                "capabilities": set(caps),
            }
        )

    client.close()

    app_cols = [col for app in APPS_OF_INTEREST for col in (app, f"{app}_version")]
    cap_cols = [f"capability_{c}" for c in sorted(all_capabilities)]
    fieldnames = IDENTITY_COLS + ["firmware_version"] + app_cols + cap_cols

    return device_rows, fieldnames


def write_csv(device_rows: list[dict], fieldnames: list[str], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in sorted(
            device_rows,
            key=lambda r: (r["tenant"], r["location"], r["facility"], r["area"], r["device_id"]),
        ):
            out = {col: "" for col in fieldnames}
            for key in IDENTITY_COLS:
                out[key] = row[key]
            out["firmware_version"] = row["firmware_version"]
            for app, ver in row["apps"].items():
                out[app] = "Yes"
                out[f"{app}_version"] = ver
            for cap in row["capabilities"]:
                out[f"capability_{cap}"] = "Yes"
            writer.writerow(out)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate lab device apps report CSV from MongoDB."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output CSV path (default: {DEFAULT_OUTPUT.relative_to(ROOT)})",
    )
    parser.add_argument(
        "--mongo-uri",
        default=os.environ.get("MONGODB_URI", ""),
        help="MongoDB connection URI (default: MONGODB_URI env var)",
    )
    parser.add_argument(
        "--include-inactive",
        action="store_true",
        help="Include devices where isActive is not true",
    )
    return parser.parse_args()


def main() -> int:
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / "reports" / ".env")

    args = parse_args()
    uri = (args.mongo_uri or "").strip()
    if not uri:
        print(
            "Error: MongoDB URI required. Set MONGODB_URI in the environment or .env file,\n"
            "       or pass --mongo-uri.",
            file=sys.stderr,
        )
        return 1

    print("Querying MongoDB...")
    device_rows, fieldnames = build_report(uri, active_only=not args.include_inactive)

    with_tracked_apps = sum(1 for row in device_rows if row["apps"])
    write_csv(device_rows, fieldnames, args.output)

    print(f"Devices written: {len(device_rows)}")
    print(f"Devices with tracked apps: {with_tracked_apps}")
    print(f"Columns: {len(fieldnames)}")
    print(f"Output: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
