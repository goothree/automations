#!/usr/bin/env python3
"""Convert test plan markdown to Testpad-ready tab-indented text."""

import re
import sys
from pathlib import Path
from typing import Optional


def _clean_step(text: str) -> str:
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text.strip()


def _extract_steps(block: str) -> list[str]:
    steps = []
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("| Result"):
            break
        if re.match(r"^#{1,3}\s", stripped):
            break
        if re.match(r"^\*\*Maps to:\*\*", stripped):
            continue
        if re.match(r"^\*\*Preconditions:\*\*", stripped):
            continue
        m = re.match(r"^(\d+)\.\s+(.+)$", stripped)
        if m:
            step = _clean_step(m.group(2))
            if step:
                steps.append(step)
            continue
        if stripped.startswith("- **Expected:**") or stripped.startswith("- **Verify:**"):
            continue
        if stripped.startswith("- "):
            step = _clean_step(stripped[2:])
            if step and not step.lower().startswith("expected:") and not step.lower().startswith("verify:"):
                steps.append(step)
    return steps


def convert_md_to_testpad(md_path: Path, out_path: Optional[Path] = None) -> Path:
    text = md_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    ticket = ""
    summary = ""
    environment = ""
    for line in lines:
        m = re.match(r"^#\s+Test Plan:\s+(\S+)", line)
        if m:
            ticket = m.group(1)
        if line.startswith("**") and line.endswith("**") and not ticket.startswith("**"):
            summary = line.strip("*").strip()
        if "Environment:" in line or "**Environment:**" in line:
            environment = _clean_step(line.split("Environment:")[-1])

    header = []
    if ticket and summary:
        header.append(f"{ticket} — {summary}")
    elif ticket:
        header.append(ticket)
    if environment:
        header.append(f"Environment: {environment.lstrip('| ').strip()}")

    prereq_lines = []
    in_prereq = False
    for line in lines:
        if line.startswith("## Prerequisites"):
            in_prereq = True
            continue
        if in_prereq and line.startswith("## "):
            break
        if in_prereq and line.startswith("### PRE-"):
            prereq_lines.append(_clean_step(line.lstrip("#").strip()))

    if prereq_lines:
        header.append(
            "Prerequisites: " + "; ".join(p[:60] for p in prereq_lines[:4])
        )

    tc_pattern = re.compile(r"^###\s+(TC-\d+:[^\n]+)")
    parts = tc_pattern.split(text)
    # parts[0] is preamble; then alternating title, body, title, body...

    output_lines = header + [""]
    i = 1
    while i < len(parts):
        title = parts[i].strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        steps = _extract_steps(body)
        if not steps:
            i += 2
            continue
        output_lines.append(title)
        for step in steps:
            output_lines.append(f"\t{step}")
        output_lines.append("")
        i += 2

    if len(output_lines) <= len(header) + 1:
        raise ValueError(f"No test cases found in {md_path}")

    out = out_path or md_path.with_name(md_path.stem.replace("_test_plan", "_testpad") + ".txt")
    if out.suffix != ".txt":
        out = out.with_suffix(".txt")
    if "_testpad" not in out.stem and ticket:
        out = out.parent / f"{ticket}_testpad.txt"

    content = "\n".join(output_lines).rstrip() + "\n"
    out.write_text(content, encoding="utf-8")
    return out


def main():
    root = Path(__file__).resolve().parents[1]
    md = root / "reports" / "IDA-5393_test_plan.md"
    out = None
    if len(sys.argv) > 1:
        md = Path(sys.argv[1])
    if len(sys.argv) > 2:
        out = Path(sys.argv[2])
    result = convert_md_to_testpad(md, out)
    print(f"Wrote {result}")


if __name__ == "__main__":
    main()
