#!/usr/bin/env python3
"""Deliver a test plan: Testpad txt, SharePoint copy, manifest update, Jira comment."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JIRA_DASHBOARD = ROOT / "jira-dashboard"
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(JIRA_DASHBOARD))

from config import TEST_PLAN_ONEDRIVE_SYNC_DIR  # noqa: E402
from jira_client import (  # noqa: E402
    add_test_plan_jira_comment,
    test_plan_sharepoint_file_url,
    _sharepoint_links_manifest_path,
)
from md_to_docx_test_plan import convert_md_to_docx  # noqa: E402
from test_plan_to_testpad import convert_md_to_testpad  # noqa: E402

SHAREPOINT_SYNC_DIR = Path(TEST_PLAN_ONEDRIVE_SYNC_DIR)


def _issue_key(raw: str) -> str:
    key = raw.strip().upper()
    if not key:
        raise ValueError("Issue key is required (e.g. IDA-5296)")
    return key


def _paths(issue_key: str) -> dict[str, Path]:
    reports = ROOT / "reports"
    base = f"{issue_key}_test_plan"
    return {
        "md": reports / f"{base}.md",
        "docx": reports / f"{base}.docx",
        "testpad": reports / f"{issue_key}_testpad.txt",
        "docx_name": f"{base}.docx",
    }


def _register_sharepoint_link(filename: str) -> str:
    manifest = _sharepoint_links_manifest_path()
    manifest.parent.mkdir(parents=True, exist_ok=True)
    links = {}
    if manifest.exists():
        try:
            loaded = json.loads(manifest.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                links = loaded
        except (json.JSONDecodeError, OSError):
            pass
    url = test_plan_sharepoint_file_url(filename)
    links[filename] = url
    manifest.write_text(json.dumps(links, indent=2) + "\n", encoding="utf-8")
    return url


def deliver(
    issue_key: str,
    *,
    skip_sharepoint: bool = False,
    skip_jira: bool = False,
) -> dict:
    paths = _paths(issue_key)
    result: dict = {"issue_key": issue_key, "steps": []}

    if not paths["docx"].exists():
        if not paths["md"].exists():
            raise FileNotFoundError(
                f"Missing {paths['docx']} and {paths['md']}. "
                "Generate the test plan before delivering."
            )
        convert_md_to_docx(paths["md"], paths["docx"])
        result["steps"].append(f"docx: {paths['docx']}")

    if paths["md"].exists():
        convert_md_to_testpad(paths["md"], paths["testpad"])
        result["steps"].append(f"testpad: {paths['testpad']}")
    elif not paths["testpad"].exists():
        raise FileNotFoundError(
            f"Missing {paths['testpad']} and no markdown at {paths['md']} to generate it."
        )

    if not skip_sharepoint:
        SHAREPOINT_SYNC_DIR.mkdir(parents=True, exist_ok=True)
        for src in (paths["docx"], paths["testpad"]):
            dest = SHAREPOINT_SYNC_DIR / src.name
            shutil.copy2(src, dest)
            result["steps"].append(f"sharepoint: {dest}")
        file_url = _register_sharepoint_link(paths["docx_name"])
        result["file_url"] = file_url

    if not skip_jira:
        jira_result = add_test_plan_jira_comment(issue_key, paths["docx_name"])
        result["jira"] = jira_result
        if jira_result.get("error"):
            raise RuntimeError(jira_result["error"])

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Deliver test plan to SharePoint and Jira.")
    parser.add_argument("issue_key", help="Jira issue key, e.g. IDA-5296")
    parser.add_argument("--skip-sharepoint", action="store_true")
    parser.add_argument("--skip-jira", action="store_true")
    args = parser.parse_args()

    try:
        issue_key = _issue_key(args.issue_key)
        result = deliver(
            issue_key,
            skip_sharepoint=args.skip_sharepoint,
            skip_jira=args.skip_jira,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
