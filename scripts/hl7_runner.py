"""Run care.ai HL7 message templates from the command line.

Examples:
    python scripts/hl7_runner.py list
    python scripts/hl7_runner.py admit --facility vinelandqa --unit testrack01 --room slot04
    python scripts/hl7_runner.py --env qa admit --facility vinelandqa --unit testrack01 --room slot04
    python scripts/hl7_runner.py run a01 --facility vinelandqa --unit testrack01 --room slot04 --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import string
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

import requests
from dotenv import load_dotenv

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from postman_runner import (
    AdmitState,
    clear_admit_state,
    generate_random_patient_name,
    load_admit_state,
    save_admit_state,
)

REPO_ROOT = SCRIPTS_DIR.parent
DEFAULT_CATALOG = REPO_ROOT / "scripts/hl7/messages.json"
DEFAULT_ADMIT_STATE = REPO_ROOT / "scripts/hl7/admit_state.json"
ENVIRONMENTS = {
    "lab": {"host": "34.74.235.204", "port": "2575"},
    "qa": {"host": "136.107.162.112", "port": "2575"},
}
ENV_FILES = (
    REPO_ROOT / "scripts/hl7/.env",
    REPO_ROOT / "scripts/postman/.env",
    REPO_ROOT / ".env",
)

MLLP_START = b"\x0b"
MLLP_END = b"\x1c\x0d"
RANDOM_PATIENT = "__random__"
IN_TRANSIT_VC_REMINDER = (
    "Please check for messaging in VC by placing a call to this room."
)
ACCOUNT_ID_LENGTH = 9
MRN_ID_LENGTH = 7
ID_CHARS = string.ascii_uppercase + string.digits


@dataclass(frozen=True)
class Hl7Message:
    group: str
    slug: str
    name: str
    event: str
    template: str
    description: str
    aliases: tuple[str, ...] = ()


RunHandler = Callable[[Hl7Message, argparse.Namespace, dict[str, str]], int]


def load_env() -> None:
    for env_file in ENV_FILES:
        if env_file.exists():
            load_dotenv(env_file, override=True)


def load_config() -> dict[str, str]:
    load_env()
    return {
        "hl7_env": "lab",
        "hl7_host": os.getenv("HL7_HOST", "").strip(),
        "hl7_port": os.getenv("HL7_PORT", "2575").strip(),
        "hl7_url": os.getenv("HL7_URL", "").strip(),
        "hl7_timeout": os.getenv("HL7_TIMEOUT", "30").strip(),
        "catalog_path": os.getenv("HL7_CATALOG", str(DEFAULT_CATALOG)),
        "admit_state_path": os.getenv(
            "ADMIT_STATE_PATH", str(DEFAULT_ADMIT_STATE)
        ),
    }


def extract_hl7_env(argv: list[str]) -> tuple[str, list[str]]:
    """Pull --env lab|qa from anywhere in argv. Default is lab."""
    env_name = "lab"
    remaining: list[str] = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--env":
            if index + 1 >= len(argv):
                raise ValueError("--env requires lab or qa")
            env_name = argv[index + 1]
            index += 2
            continue
        if arg.startswith("--env="):
            env_name = arg.split("=", 1)[1]
            index += 1
            continue
        remaining.append(arg)
        index += 1

    if env_name not in ENVIRONMENTS:
        choices = ", ".join(ENVIRONMENTS)
        raise ValueError(f"--env must be one of: {choices}")
    return env_name, remaining


def apply_hl7_env(config: dict[str, str], env_name: str) -> dict[str, str]:
    selected = ENVIRONMENTS[env_name]
    updated = dict(config)
    updated["hl7_env"] = env_name
    updated["hl7_host"] = selected["host"]
    updated["hl7_port"] = selected["port"]
    updated["hl7_url"] = ""
    return updated


def resolve_admit_state_path(config: dict[str, str]) -> Path:
    path = Path(config["admit_state_path"])
    return path if path.is_absolute() else REPO_ROOT / path


def resolve_catalog_path(config: dict[str, str]) -> Path:
    path = Path(config["catalog_path"])
    return path if path.is_absolute() else REPO_ROOT / path


def load_catalog(path: Path) -> list[Hl7Message]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)

    messages: list[Hl7Message] = []
    for entry in data.get("messages", []):
        messages.append(
            Hl7Message(
                group=entry.get("group", ""),
                slug=entry["slug"].lower(),
                name=entry.get("name", entry["slug"]),
                event=entry.get("event", ""),
                template=entry["template"],
                description=entry.get("description", ""),
                aliases=tuple(alias.lower() for alias in entry.get("aliases", [])),
            )
        )
    return messages


def resolve_target(messages: list[Hl7Message], target: str) -> Hl7Message:
    normalized = target.lower().strip()
    by_slug = {msg.slug: msg for msg in messages}
    alias_map = {
        alias: msg for msg in messages for alias in (msg.slug, *msg.aliases)
    }

    if normalized in alias_map:
        return alias_map[normalized]

    matches = [
        msg
        for msg in messages
        if normalized in msg.slug
        or normalized in msg.name.lower()
        or any(normalized in alias for alias in msg.aliases)
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        names = ", ".join(msg.slug for msg in matches)
        raise ValueError(f"Ambiguous target '{target}'. Matches: {names}")

    available = ", ".join(sorted({msg.slug for msg in messages} | set(alias_map)))
    raise ValueError(f"Unknown target '{target}'. Available: {available}")


def resolve_template_path(message: Hl7Message) -> Path:
    template = Path(message.template)
    if template.is_absolute():
        return template
    return REPO_ROOT / "scripts/hl7" / template


def generate_random_account_id(length: int = ACCOUNT_ID_LENGTH) -> str:
    return "".join(secrets.choice(ID_CHARS) for _ in range(length))


def generate_random_mrn(length: int = MRN_ID_LENGTH) -> str:
    return "".join(secrets.choice(ID_CHARS) for _ in range(length))


def hl7_now(fmt: str) -> str:
    return datetime.now().strftime(fmt)


def hl7_mrn(mrn: str) -> str:
    clean = mrn.strip().upper()
    if clean.startswith("MRN-"):
        return clean
    return f"MRN-{clean}"


def hl7_account(account: str) -> str:
    clean = account.strip().upper()
    if clean.startswith("ACT-"):
        return clean
    return f"ACT-{clean}-J76-0"


def hl7_patient_name(first: str, last: str) -> str:
    family = (last or "Patient").strip()
    given = (first or "Unknown").strip()
    return f"{family}^{given}^^^^"


def set_field(segment: list[str], index: int, value: str) -> None:
    while len(segment) <= index:
        segment.append("")
    segment[index] = value


def build_location(unit: str, room: str, facility: str) -> str:
    return f"{unit}^{room}^^{facility}^D^^^^^^DEPID"


def apply_admit_fields(
    lines: list[str],
    *,
    mrn: str,
    account: str,
    first_name: str,
    last_name: str,
    facility: str,
    unit: str,
    room: str,
    message_id: str | None = None,
    admit_time: str | None = None,
) -> tuple[list[str], str]:
    message_id = message_id or str(secrets.randbelow(900000) + 100000)
    msh_time = hl7_now("%Y%m%d%H%M")
    evn_time = hl7_now("%Y%m%d%H%M")
    evn_recorded = hl7_now("%Y%m%d%H%M%S")
    admit_time = admit_time or hl7_now("%Y%m%d%H%M")

    updated: list[str] = []
    for line in lines:
        line = line.strip("\r\n")
        if not line:
            continue

        fields = line.split("|")
        segment = fields[0]

        if segment == "MSH":
            set_field(fields, 6, msh_time)
            set_field(fields, 9, message_id)
        elif segment == "EVN":
            set_field(fields, 2, evn_time)
            set_field(fields, 6, evn_recorded)
        elif segment == "PID":
            set_field(fields, 3, f"{hl7_mrn(mrn)}^^^Hospital^MR")
            set_field(fields, 5, hl7_patient_name(first_name, last_name))
            set_field(fields, 18, hl7_account(account))
        elif segment == "PV1":
            set_field(fields, 3, build_location(unit, room, facility))
            set_field(fields, 44, admit_time)

        updated.append("|".join(fields))

    return updated, admit_time


def apply_discharge_fields(
    lines: list[str],
    *,
    mrn: str,
    account: str,
    first_name: str,
    last_name: str,
    facility: str,
    unit: str,
    room: str,
    admitted_at: str = "",
    message_id: str | None = None,
) -> list[str]:
    message_id = message_id or str(secrets.randbelow(900000) + 100000)
    msh_time = hl7_now("%Y%m%d%H%M%S")
    evn_time = hl7_now("%Y%m%d%H%M%S")
    evn_recorded = hl7_now("%Y%m%d%H%M%S")
    discharge_time = hl7_now("%Y%m%d%H%M%S")

    updated: list[str] = []
    for line in lines:
        line = line.strip("\r\n")
        if not line:
            continue

        fields = line.split("|")
        segment = fields[0]

        if segment == "MSH":
            set_field(fields, 6, msh_time)
            set_field(fields, 9, message_id)
        elif segment == "EVN":
            set_field(fields, 2, evn_time)
            set_field(fields, 6, evn_recorded)
        elif segment == "PID":
            # Match admit identifiers so the downstream system can find the patient.
            set_field(fields, 3, f"{hl7_mrn(mrn)}^^^Hospital^MR")
            set_field(fields, 5, hl7_patient_name(first_name, last_name))
            set_field(fields, 18, hl7_account(account))
        elif segment == "PV1":
            set_field(fields, 3, build_location(unit, room, facility))
            if admitted_at:
                set_field(fields, 44, admitted_at)
            set_field(fields, 45, discharge_time)

        updated.append("|".join(fields))

    return updated


def apply_transfer_fields(
    lines: list[str],
    *,
    mrn: str,
    account: str,
    first_name: str,
    last_name: str,
    dest_facility: str,
    dest_unit: str,
    dest_room: str,
    prior_facility: str,
    prior_unit: str,
    prior_room: str,
    admitted_at: str = "",
    message_id: str | None = None,
) -> list[str]:
    message_id = message_id or str(secrets.randbelow(900000) + 100000)
    msh_time = hl7_now("%Y%m%d%H%M")
    evn_time = hl7_now("%Y%m%d%H%M")
    evn_recorded = hl7_now("%Y%m%d%H%M%S")

    updated: list[str] = []
    for line in lines:
        line = line.strip("\r\n")
        if not line:
            continue

        fields = line.split("|")
        segment = fields[0]

        if segment == "MSH":
            set_field(fields, 6, msh_time)
            set_field(fields, 8, "ADT^A02")
            set_field(fields, 9, message_id)
        elif segment == "EVN":
            set_field(fields, 1, "A02")
            set_field(fields, 2, evn_time)
            set_field(fields, 6, evn_recorded)
        elif segment == "PID":
            set_field(fields, 3, f"{hl7_mrn(mrn)}^^^Hospital^MR")
            set_field(fields, 5, hl7_patient_name(first_name, last_name))
            set_field(fields, 18, hl7_account(account))
        elif segment == "PV1":
            set_field(fields, 3, build_location(dest_unit, dest_room, dest_facility))
            set_field(fields, 6, build_location(prior_unit, prior_room, prior_facility))
            if admitted_at:
                set_field(fields, 44, admitted_at)

        updated.append("|".join(fields))

    return updated


def apply_in_transit_fields(
    lines: list[str],
    *,
    mrn: str,
    account: str,
    first_name: str,
    last_name: str,
    facility: str,
    unit: str,
    room: str,
    admitted_at: str = "",
    message_id: str | None = None,
) -> list[str]:
    message_id = message_id or str(secrets.randbelow(900000) + 100000)
    msh_time = hl7_now("%Y%m%d%H%M")
    evn_time = hl7_now("%Y%m%d%H%M")
    evn_recorded = hl7_now("%Y%m%d%H%M%S")
    transit_time = hl7_now("%Y%m%d%H%M")

    updated: list[str] = []
    for line in lines:
        line = line.strip("\r\n")
        if not line:
            continue

        fields = line.split("|")
        segment = fields[0]

        if segment == "MSH":
            set_field(fields, 6, msh_time)
            set_field(fields, 9, message_id)
        elif segment == "EVN":
            set_field(fields, 1, "A09")
            set_field(fields, 2, evn_time)
            set_field(fields, 6, evn_recorded)
        elif segment == "PID":
            set_field(fields, 3, f"{hl7_mrn(mrn)}^^^Hospital^MR")
            set_field(fields, 5, hl7_patient_name(first_name, last_name))
            set_field(fields, 18, hl7_account(account))
        elif segment == "PV1":
            set_field(fields, 3, build_location(unit, room, facility))
            set_field(fields, 44, admitted_at or transit_time)

        updated.append("|".join(fields))

    return updated


def apply_back_in_room_fields(
    lines: list[str],
    *,
    mrn: str,
    account: str,
    first_name: str,
    last_name: str,
    facility: str,
    unit: str,
    room: str,
    admitted_at: str = "",
    message_id: str | None = None,
) -> list[str]:
    message_id = message_id or str(secrets.randbelow(900000) + 100000)
    msh_time = hl7_now("%Y%m%d%H%M")
    evn_time = hl7_now("%Y%m%d%H%M")
    evn_recorded = hl7_now("%Y%m%d%H%M%S")

    updated: list[str] = []
    for line in lines:
        line = line.strip("\r\n")
        if not line:
            continue

        fields = line.split("|")
        segment = fields[0]

        if segment == "MSH":
            set_field(fields, 6, msh_time)
            set_field(fields, 8, "ADT^A10")
            set_field(fields, 9, message_id)
        elif segment == "EVN":
            set_field(fields, 1, "A10")
            set_field(fields, 2, evn_time)
            set_field(fields, 6, evn_recorded)
        elif segment == "PID":
            set_field(fields, 3, f"{hl7_mrn(mrn)}^^^Hospital^MR")
            set_field(fields, 5, hl7_patient_name(first_name, last_name))
            set_field(fields, 18, hl7_account(account))
        elif segment == "PV1":
            set_field(fields, 3, build_location(unit, room, facility))
            if admitted_at:
                set_field(fields, 44, admitted_at)

        updated.append("|".join(fields))

    return updated


def apply_update_fields(
    lines: list[str],
    *,
    mrn: str,
    account: str,
    first_name: str,
    last_name: str,
    facility: str,
    unit: str,
    room: str,
    admitted_at: str = "",
    message_id: str | None = None,
) -> list[str]:
    message_id = message_id or str(secrets.randbelow(900000) + 100000)
    msh_time = hl7_now("%Y%m%d%H%M%S")
    evn_time = hl7_now("%Y%m%d%H%M%S")
    evn_recorded = hl7_now("%Y%m%d%H%M%S")

    updated: list[str] = []
    for line in lines:
        line = line.strip("\r\n")
        if not line:
            continue

        fields = line.split("|")
        segment = fields[0]

        if segment == "MSH":
            set_field(fields, 6, msh_time)
            set_field(fields, 8, "ADT^A08")
            set_field(fields, 9, message_id)
        elif segment == "EVN":
            set_field(fields, 1, "A08")
            set_field(fields, 2, evn_time)
            set_field(fields, 6, evn_recorded)
        elif segment == "PID":
            set_field(fields, 3, f"{hl7_mrn(mrn)}^^^Hospital^MR")
            set_field(fields, 5, hl7_patient_name(first_name, last_name))
            set_field(fields, 18, hl7_account(account))
        elif segment == "PV1":
            set_field(fields, 3, build_location(unit, room, facility))
            if admitted_at:
                set_field(fields, 44, admitted_at)

        updated.append("|".join(fields))

    return updated


def hl7_order_timing(timestamp: str) -> str:
    return f"^^^{timestamp}^^R^^"


def generate_order_id(length: int = 10) -> str:
    return "".join(secrets.choice(string.digits) for _ in range(length))


def apply_discharge_order_fields(
    lines: list[str],
    *,
    mrn: str,
    account: str,
    first_name: str,
    last_name: str,
    facility: str,
    unit: str,
    room: str,
    admitted_at: str = "",
    message_id: str | None = None,
    order_control: str = "NW",
    placer_order_id: str | None = None,
) -> tuple[list[str], str]:
    message_id = message_id or str(secrets.randbelow(900000) + 100000)
    msh_time = hl7_now("%Y%m%d%H%M")
    evn_time = hl7_now("%Y%m%d%H%M")
    evn_recorded = hl7_now("%Y%m%d%H%M%S")
    order_time = hl7_now("%Y%m%d%H%M%S")
    placer_order_id = placer_order_id or generate_order_id()

    updated: list[str] = []
    for line in lines:
        line = line.strip("\r\n")
        if not line:
            continue

        fields = line.split("|")
        segment = fields[0]

        if segment == "MSH":
            set_field(fields, 6, msh_time)
            set_field(fields, 8, "ORM^O01")
            set_field(fields, 9, message_id)
        elif segment == "EVN":
            set_field(fields, 2, evn_time)
            set_field(fields, 6, evn_recorded)
        elif segment == "PID":
            set_field(fields, 3, f"{hl7_mrn(mrn)}^^^Hospital^MR")
            set_field(fields, 5, hl7_patient_name(first_name, last_name))
            set_field(fields, 18, hl7_account(account))
        elif segment == "PV1":
            set_field(fields, 3, build_location(unit, room, facility))
            if admitted_at:
                set_field(fields, 44, admitted_at)
        elif segment == "ORC":
            set_field(fields, 1, order_control)
            set_field(fields, 2, f"{placer_order_id}^EPC")
            set_field(fields, 7, hl7_order_timing(order_time))
            set_field(fields, 9, order_time)
        elif segment == "OBR":
            set_field(fields, 2, f"{placer_order_id}^EPC")
            set_field(fields, 6, order_time)
            set_field(fields, 27, hl7_order_timing(order_time))
            set_field(fields, 36, order_time)

        updated.append("|".join(fields))

    return updated, placer_order_id


def format_hl7_message(lines: list[str]) -> str:
    return "\r".join(lines) + "\r"


def wrap_mllp(message: str) -> bytes:
    return MLLP_START + message.encode("utf-8") + MLLP_END


def send_mllp(message: str, host: str, port: int, timeout: float) -> str:
    payload = wrap_mllp(message)
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.sendall(payload)
        sock.shutdown(socket.SHUT_WR)
        chunks: list[bytes] = []
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
    raw = b"".join(chunks)
    if raw.startswith(MLLP_START):
        raw = raw[1:]
    if raw.endswith(MLLP_END):
        raw = raw[: -len(MLLP_END)]
    return raw.decode("utf-8", errors="replace").strip()


def send_http(message: str, url: str, timeout: float) -> tuple[int, str]:
    response = requests.post(
        url,
        data=message.encode("utf-8"),
        headers={"Content-Type": "application/hl7-v2; charset=utf-8"},
        timeout=timeout,
    )
    return response.status_code, response.text.strip()


def resolve_admit_identity(
    args: argparse.Namespace,
) -> tuple[str, str, str, str, str, str, str]:
    if not args.facility or not args.unit or not args.room:
        raise ValueError(
            "Admit requires --facility, --unit, and --room "
            '(e.g. --facility vinelandqa --unit testrack01 --room slot04)'
        )

    facility = args.facility.strip()
    unit = args.unit.strip()
    room = args.room.strip()

    if not args.patient or args.patient == RANDOM_PATIENT:
        first_name, last_name = generate_random_patient_name()
    else:
        parts = args.patient.strip().split(None, 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""

    account = (args.account or generate_random_account_id()).strip()
    mrn = (args.mrn or generate_random_mrn()).strip()

    return mrn, account, first_name, last_name, facility, unit, room


def pick_override(override: str, saved: str) -> str:
    return override.strip() if override else saved.strip()


def resolve_discharge_identity(
    args: argparse.Namespace,
    config: dict[str, str],
) -> tuple[str, str, str, str, str, str, str, str]:
    saved = load_admit_state(resolve_admit_state_path(config))

    if args.patient and args.patient != RANDOM_PATIENT:
        parts = args.patient.strip().split(None, 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""
    elif saved and (saved.patient_first_name or saved.patient_last_name):
        first_name = saved.patient_first_name
        last_name = saved.patient_last_name
    else:
        raise ValueError(
            "Discharge requires saved admit patient data or --patient "
            '(e.g. --patient "Jane Doe")'
        )

    account = pick_override(getattr(args, "account", "") or "", saved.account_number if saved else "")
    mrn = pick_override(getattr(args, "mrn", "") or "", saved.medical_record_number if saved else "")
    facility = pick_override(getattr(args, "facility", "") or "", saved.facility if saved else "")
    unit = pick_override(getattr(args, "unit", "") or "", saved.unit if saved else "")
    room = pick_override(getattr(args, "room", "") or "", saved.room if saved else "")

    if not account or not mrn:
        raise ValueError(
            "Discharge requires saved admit account/MRN. Run ./run_hl7 admit first, "
            "or pass --account and --mrn."
        )
    if not facility or not unit or not room:
        raise ValueError(
            "Discharge requires location from saved admit state or "
            "--facility, --unit, and --room."
        )

    admitted_at = saved.admitted_at if saved else ""

    return mrn, account, first_name, last_name, facility, unit, room, admitted_at


def resolve_update_identity(
    args: argparse.Namespace,
    config: dict[str, str],
) -> tuple[str, str, str, str, str, str, str, str]:
    if not args.patient or args.patient == RANDOM_PATIENT:
        raise ValueError(
            'Update requires --patient "First Last" '
            '(e.g. --patient "Jane Doe")'
        )

    saved = load_admit_state(resolve_admit_state_path(config))

    parts = args.patient.strip().split(None, 1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) > 1 else ""

    account = pick_override(getattr(args, "account", "") or "", saved.account_number if saved else "")
    mrn = pick_override(getattr(args, "mrn", "") or "", saved.medical_record_number if saved else "")
    facility = pick_override(getattr(args, "facility", "") or "", saved.facility if saved else "")
    unit = pick_override(getattr(args, "unit", "") or "", saved.unit if saved else "")
    room = pick_override(getattr(args, "room", "") or "", saved.room if saved else "")

    if not account or not mrn:
        raise ValueError(
            "Update requires saved admit account/MRN. Run ./run_hl7 admit first, "
            "or pass --account and --mrn."
        )
    if not facility or not unit or not room:
        raise ValueError(
            "Update requires location from saved admit state or "
            "--facility, --unit, and --room."
        )

    admitted_at = saved.admitted_at if saved else ""

    return mrn, account, first_name, last_name, facility, unit, room, admitted_at


def resolve_transfer_identity(
    args: argparse.Namespace,
    config: dict[str, str],
) -> tuple[str, str, str, str, str, str, str, str, str, str, str]:
    if not args.facility or not args.unit or not args.room:
        raise ValueError(
            "Transfer requires --facility, --unit, and --room for the new location "
            '(e.g. --facility vinelandqa --unit testrack02 --room slot05)'
        )

    saved = load_admit_state(resolve_admit_state_path(config))
    if not saved:
        raise ValueError(
            "Transfer requires saved admit state. Run ./run_hl7 admit first."
        )

    dest_facility = args.facility.strip()
    dest_unit = args.unit.strip()
    dest_room = args.room.strip()

    if args.patient and args.patient != RANDOM_PATIENT:
        parts = args.patient.strip().split(None, 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""
    elif saved.patient_first_name or saved.patient_last_name:
        first_name = saved.patient_first_name
        last_name = saved.patient_last_name
    else:
        raise ValueError(
            "Transfer requires saved admit patient data or --patient "
            '(e.g. --patient "Jane Doe")'
        )

    account = pick_override(getattr(args, "account", "") or "", saved.account_number)
    mrn = pick_override(getattr(args, "mrn", "") or "", saved.medical_record_number)

    if not saved.facility or not saved.unit or not saved.room:
        raise ValueError(
            "Saved admit state is missing prior location. Run ./run_hl7 admit first."
        )

    prior_facility = saved.facility
    prior_unit = saved.unit
    prior_room = saved.room
    admitted_at = saved.admitted_at

    return (
        mrn,
        account,
        first_name,
        last_name,
        dest_facility,
        dest_unit,
        dest_room,
        prior_facility,
        prior_unit,
        prior_room,
        admitted_at,
    )


def resolve_in_transit_identity(
    args: argparse.Namespace,
    config: dict[str, str],
) -> tuple[str, str, str, str, str, str, str, str]:
    if not args.facility or not args.unit or not args.room:
        raise ValueError(
            "In-transit requires --facility, --unit, and --room "
            '(e.g. --facility vinelandqa --unit testrack01 --room slot04)'
        )

    saved = load_admit_state(resolve_admit_state_path(config))
    facility = args.facility.strip()
    unit = args.unit.strip()
    room = args.room.strip()

    if args.patient and args.patient != RANDOM_PATIENT:
        parts = args.patient.strip().split(None, 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""
    elif saved and (saved.patient_first_name or saved.patient_last_name):
        first_name = saved.patient_first_name
        last_name = saved.patient_last_name
    else:
        raise ValueError(
            "In-transit requires saved admit patient data or --patient "
            '(e.g. --patient "Jane Doe")'
        )

    account = pick_override(getattr(args, "account", "") or "", saved.account_number if saved else "")
    mrn = pick_override(getattr(args, "mrn", "") or "", saved.medical_record_number if saved else "")

    if not account or not mrn:
        raise ValueError(
            "In-transit requires saved admit account/MRN. Run ./run_hl7 admit first, "
            "or pass --account and --mrn."
        )

    admitted_at = saved.admitted_at if saved else ""

    return mrn, account, first_name, last_name, facility, unit, room, admitted_at


def print_message_summary(
    *,
    message: Hl7Message,
    mrn: str,
    account: str,
    first_name: str,
    last_name: str,
    facility: str,
    unit: str,
    room: str,
    transport: str,
    destination: str,
    outcome: str,
    environment: str = "",
    detail: str = "",
    mrn_display: str | None = None,
    account_display: str | None = None,
    prior_facility: str = "",
    prior_unit: str = "",
    prior_room: str = "",
) -> None:
    print(f"\n{message.name} ({message.event})")
    print(f"  Outcome:   {outcome}")
    if environment:
        print(f"  Environment: {environment}")
    print(f"  Transport: {transport}")
    print(f"  Target:    {destination}")
    print(f"  Facility:  {facility}")
    print(f"  Location:  {unit} / {room}")
    if prior_unit or prior_room:
        prior_parts = [part for part in (prior_facility, prior_unit, prior_room) if part]
        print(f"  Prior:     {' / '.join(prior_parts)}")
    patient = " ".join(part for part in (first_name, last_name) if part)
    print(f"  Patient:   {patient}")
    print(f"  MRN:       {mrn_display or mrn}")
    print(f"  Account:   {account_display or account}")
    if detail:
        print(f"  Detail:    {detail}")


def save_admit_result(
    config: dict[str, str],
    *,
    account: str,
    mrn: str,
    facility: str,
    unit: str,
    room: str,
    first_name: str,
    last_name: str,
    admitted_at: str = "",
    no_save_state: bool,
) -> None:
    if no_save_state:
        return
    admit_state_path = resolve_admit_state_path(config)
    save_admit_state(
        admit_state_path,
        AdmitState(
            account_number=account,
            medical_record_number=mrn,
            facility=facility,
            unit=unit,
            room=room,
            patient_first_name=first_name,
            patient_last_name=last_name,
            admitted_at=admitted_at,
        ),
    )
    print(f"  Saved admit state: {admit_state_path}")


def save_last_order_id(config: dict[str, str], order_id: str) -> None:
    if not order_id:
        return
    admit_state_path = resolve_admit_state_path(config)
    saved = load_admit_state(admit_state_path)
    if not saved:
        return
    save_admit_state(
        admit_state_path,
        AdmitState(
            account_number=saved.account_number,
            medical_record_number=saved.medical_record_number,
            facility=saved.facility,
            unit=saved.unit,
            room=saved.room,
            coid=saved.coid,
            patient_first_name=saved.patient_first_name,
            patient_last_name=saved.patient_last_name,
            admitted_at=saved.admitted_at,
            last_order_id=order_id,
            saved_at=saved.saved_at,
        ),
    )


def resolve_cancel_discharge_order_identity(
    args: argparse.Namespace,
    config: dict[str, str],
) -> tuple[str, str, str, str, str, str, str, str, str]:
    mrn, account, first_name, last_name, facility, unit, room, admitted_at = (
        resolve_discharge_identity(args, config)
    )
    saved = load_admit_state(resolve_admit_state_path(config))
    order_id = pick_override(getattr(args, "order_id", "") or "", saved.last_order_id if saved else "")
    if not order_id:
        raise ValueError(
            "Cancel discharge order requires a saved order ID from ./run_hl7 discharge-order "
            "or --order-id"
        )
    return mrn, account, first_name, last_name, facility, unit, room, admitted_at, order_id


def transport_destination(config: dict[str, str]) -> tuple[str, str, int, float]:
    hl7_url = config["hl7_url"]
    hl7_host = config["hl7_host"]
    hl7_port = int(config["hl7_port"])
    timeout = float(config["hl7_timeout"])
    return hl7_url, hl7_host, hl7_port, timeout


def write_hl7_output(hl7_message: str, args: argparse.Namespace) -> None:
    if args.print_message:
        sys.stdout.write(hl7_message)

    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = REPO_ROOT / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(hl7_message, encoding="utf-8")
        print(f"Wrote HL7 message: {output_path}")


def deliver_hl7_message(
    message: Hl7Message,
    args: argparse.Namespace,
    config: dict[str, str],
    *,
    hl7_message: str,
    mrn: str,
    account: str,
    first_name: str,
    last_name: str,
    facility: str,
    unit: str,
    room: str,
    mrn_display: str,
    account_display: str,
    admitted_at: str = "",
    save_state: bool,
    prior_facility: str = "",
    prior_unit: str = "",
    prior_room: str = "",
) -> int:
    write_hl7_output(hl7_message, args)

    hl7_url, hl7_host, hl7_port, timeout = transport_destination(config)
    destination = hl7_url or (f"{hl7_host}:{hl7_port}" if hl7_host else "(not configured)")

    summary_kwargs = {
        "message": message,
        "mrn": mrn,
        "account": account,
        "first_name": first_name,
        "last_name": last_name,
        "facility": facility,
        "unit": unit,
        "room": room,
        "mrn_display": mrn_display,
        "account_display": account_display,
        "prior_facility": prior_facility,
        "prior_unit": prior_unit,
        "prior_room": prior_room,
        "environment": config.get("hl7_env", ""),
    }

    if args.dry_run:
        print_message_summary(
            **summary_kwargs,
            transport="dry-run",
            destination=destination,
            outcome="OK (not sent)",
        )
        if save_state:
            save_admit_result(
                config,
                account=account,
                mrn=mrn,
                facility=facility,
                unit=unit,
                room=room,
                first_name=first_name,
                last_name=last_name,
                admitted_at=admitted_at,
                no_save_state=args.no_save_state,
            )
        return 0

    if not hl7_url and not hl7_host:
        print(
            "Error: Set HL7_URL for HTTP or HL7_HOST (+ optional HL7_PORT) for MLLP "
            "in scripts/hl7/.env",
            file=sys.stderr,
        )
        return 1

    try:
        if hl7_url:
            status, body = send_http(hl7_message, hl7_url, timeout)
            if status >= 400:
                print_message_summary(
                    **summary_kwargs,
                    transport="http",
                    destination=hl7_url,
                    outcome=f"FAILED ({status})",
                    detail=body[:500],
                )
                return 1
            print_message_summary(
                **summary_kwargs,
                transport="http",
                destination=hl7_url,
                outcome=f"OK ({status})",
                detail=body[:500],
            )
        else:
            ack = send_mllp(hl7_message, hl7_host, hl7_port, timeout)
            print_message_summary(
                **summary_kwargs,
                transport="mllp",
                destination=f"{hl7_host}:{hl7_port}",
                outcome="OK",
                detail=ack[:500],
            )
    except OSError as exc:
        print_message_summary(
            **summary_kwargs,
            transport="mllp" if hl7_host else "http",
            destination=destination,
            outcome="FAILED",
            detail=str(exc),
        )
        return 1
    except requests.RequestException as exc:
        print_message_summary(
            **summary_kwargs,
            transport="http",
            destination=hl7_url,
            outcome="FAILED",
            detail=str(exc),
        )
        return 1

    if save_state:
        save_admit_result(
            config,
            account=account,
            mrn=mrn,
            facility=facility,
            unit=unit,
            room=room,
            first_name=first_name,
            last_name=last_name,
            admitted_at=admitted_at,
            no_save_state=args.no_save_state,
        )
    return 0


def run_admit(message: Hl7Message, args: argparse.Namespace, config: dict[str, str]) -> int:
    template_path = resolve_template_path(message)
    if not template_path.exists():
        print(f"Error: HL7 template not found: {template_path}", file=sys.stderr)
        return 1

    try:
        mrn, account, first_name, last_name, facility, unit, room = resolve_admit_identity(
            args
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    template_lines = template_path.read_text(encoding="utf-8").splitlines()
    message_lines, admitted_at = apply_admit_fields(
        template_lines,
        mrn=mrn,
        account=account,
        first_name=first_name,
        last_name=last_name,
        facility=facility,
        unit=unit,
        room=room,
    )
    hl7_message = format_hl7_message(message_lines)

    return deliver_hl7_message(
        message,
        args,
        config,
        hl7_message=hl7_message,
        mrn=mrn,
        account=account,
        first_name=first_name,
        last_name=last_name,
        facility=facility,
        unit=unit,
        room=room,
        mrn_display=hl7_mrn(mrn),
        account_display=hl7_account(account),
        admitted_at=admitted_at,
        save_state=True,
    )


def run_discharge(message: Hl7Message, args: argparse.Namespace, config: dict[str, str]) -> int:
    template_path = resolve_template_path(message)
    if not template_path.exists():
        print(f"Error: HL7 template not found: {template_path}", file=sys.stderr)
        return 1

    try:
        mrn, account, first_name, last_name, facility, unit, room, admitted_at = (
            resolve_discharge_identity(args, config)
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    template_lines = template_path.read_text(encoding="utf-8").splitlines()
    message_lines = apply_discharge_fields(
        template_lines,
        mrn=mrn,
        account=account,
        first_name=first_name,
        last_name=last_name,
        facility=facility,
        unit=unit,
        room=room,
        admitted_at=admitted_at,
    )
    hl7_message = format_hl7_message(message_lines)

    return deliver_hl7_message(
        message,
        args,
        config,
        hl7_message=hl7_message,
        mrn=mrn,
        account=account,
        first_name=first_name,
        last_name=last_name,
        facility=facility,
        unit=unit,
        room=room,
        mrn_display=hl7_mrn(mrn),
        account_display=hl7_account(account),
        admitted_at=admitted_at,
        save_state=False,
    )


def run_transfer(message: Hl7Message, args: argparse.Namespace, config: dict[str, str]) -> int:
    template_path = resolve_template_path(message)
    if not template_path.exists():
        print(f"Error: HL7 template not found: {template_path}", file=sys.stderr)
        return 1

    try:
        (
            mrn,
            account,
            first_name,
            last_name,
            dest_facility,
            dest_unit,
            dest_room,
            prior_facility,
            prior_unit,
            prior_room,
            admitted_at,
        ) = resolve_transfer_identity(args, config)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    template_lines = template_path.read_text(encoding="utf-8").splitlines()
    message_lines = apply_transfer_fields(
        template_lines,
        mrn=mrn,
        account=account,
        first_name=first_name,
        last_name=last_name,
        dest_facility=dest_facility,
        dest_unit=dest_unit,
        dest_room=dest_room,
        prior_facility=prior_facility,
        prior_unit=prior_unit,
        prior_room=prior_room,
        admitted_at=admitted_at,
    )
    hl7_message = format_hl7_message(message_lines)

    return deliver_hl7_message(
        message,
        args,
        config,
        hl7_message=hl7_message,
        mrn=mrn,
        account=account,
        first_name=first_name,
        last_name=last_name,
        facility=dest_facility,
        unit=dest_unit,
        room=dest_room,
        mrn_display=hl7_mrn(mrn),
        account_display=hl7_account(account),
        admitted_at=admitted_at,
        save_state=True,
        prior_facility=prior_facility,
        prior_unit=prior_unit,
        prior_room=prior_room,
    )


def run_in_transit(message: Hl7Message, args: argparse.Namespace, config: dict[str, str]) -> int:
    template_path = resolve_template_path(message)
    if not template_path.exists():
        print(f"Error: HL7 template not found: {template_path}", file=sys.stderr)
        return 1

    try:
        mrn, account, first_name, last_name, facility, unit, room, admitted_at = (
            resolve_in_transit_identity(args, config)
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    template_lines = template_path.read_text(encoding="utf-8").splitlines()
    message_lines = apply_in_transit_fields(
        template_lines,
        mrn=mrn,
        account=account,
        first_name=first_name,
        last_name=last_name,
        facility=facility,
        unit=unit,
        room=room,
        admitted_at=admitted_at,
    )
    hl7_message = format_hl7_message(message_lines)

    result = deliver_hl7_message(
        message,
        args,
        config,
        hl7_message=hl7_message,
        mrn=mrn,
        account=account,
        first_name=first_name,
        last_name=last_name,
        facility=facility,
        unit=unit,
        room=room,
        mrn_display=hl7_mrn(mrn),
        account_display=hl7_account(account),
        admitted_at=admitted_at,
        save_state=True,
    )
    if result == 0:
        print(f"\n  Note: {IN_TRANSIT_VC_REMINDER}")
    return result


def run_back_in_room(message: Hl7Message, args: argparse.Namespace, config: dict[str, str]) -> int:
    template_path = resolve_template_path(message)
    if not template_path.exists():
        print(f"Error: HL7 template not found: {template_path}", file=sys.stderr)
        return 1

    try:
        mrn, account, first_name, last_name, facility, unit, room, admitted_at = (
            resolve_discharge_identity(args, config)
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    template_lines = template_path.read_text(encoding="utf-8").splitlines()
    message_lines = apply_back_in_room_fields(
        template_lines,
        mrn=mrn,
        account=account,
        first_name=first_name,
        last_name=last_name,
        facility=facility,
        unit=unit,
        room=room,
        admitted_at=admitted_at,
    )
    hl7_message = format_hl7_message(message_lines)

    return deliver_hl7_message(
        message,
        args,
        config,
        hl7_message=hl7_message,
        mrn=mrn,
        account=account,
        first_name=first_name,
        last_name=last_name,
        facility=facility,
        unit=unit,
        room=room,
        mrn_display=hl7_mrn(mrn),
        account_display=hl7_account(account),
        admitted_at=admitted_at,
        save_state=True,
    )


def run_update(message: Hl7Message, args: argparse.Namespace, config: dict[str, str]) -> int:
    template_path = resolve_template_path(message)
    if not template_path.exists():
        print(f"Error: HL7 template not found: {template_path}", file=sys.stderr)
        return 1

    try:
        mrn, account, first_name, last_name, facility, unit, room, admitted_at = (
            resolve_update_identity(args, config)
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    template_lines = template_path.read_text(encoding="utf-8").splitlines()
    message_lines = apply_update_fields(
        template_lines,
        mrn=mrn,
        account=account,
        first_name=first_name,
        last_name=last_name,
        facility=facility,
        unit=unit,
        room=room,
        admitted_at=admitted_at,
    )
    hl7_message = format_hl7_message(message_lines)

    return deliver_hl7_message(
        message,
        args,
        config,
        hl7_message=hl7_message,
        mrn=mrn,
        account=account,
        first_name=first_name,
        last_name=last_name,
        facility=facility,
        unit=unit,
        room=room,
        mrn_display=hl7_mrn(mrn),
        account_display=hl7_account(account),
        admitted_at=admitted_at,
        save_state=True,
    )


def run_discharge_order(message: Hl7Message, args: argparse.Namespace, config: dict[str, str]) -> int:
    template_path = resolve_template_path(message)
    if not template_path.exists():
        print(f"Error: HL7 template not found: {template_path}", file=sys.stderr)
        return 1

    try:
        mrn, account, first_name, last_name, facility, unit, room, admitted_at = (
            resolve_discharge_identity(args, config)
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    template_lines = template_path.read_text(encoding="utf-8").splitlines()
    message_lines, placer_order_id = apply_discharge_order_fields(
        template_lines,
        mrn=mrn,
        account=account,
        first_name=first_name,
        last_name=last_name,
        facility=facility,
        unit=unit,
        room=room,
        admitted_at=admitted_at,
    )
    hl7_message = format_hl7_message(message_lines)

    result = deliver_hl7_message(
        message,
        args,
        config,
        hl7_message=hl7_message,
        mrn=mrn,
        account=account,
        first_name=first_name,
        last_name=last_name,
        facility=facility,
        unit=unit,
        room=room,
        mrn_display=hl7_mrn(mrn),
        account_display=hl7_account(account),
        admitted_at=admitted_at,
        save_state=False,
    )
    if result == 0 and not args.dry_run:
        save_last_order_id(config, placer_order_id)
        print(f"  Saved order ID: {placer_order_id}")
    elif result == 0 and args.dry_run:
        print(f"  Order ID: {placer_order_id}")
    return result


def run_cancel_discharge_order(
    message: Hl7Message, args: argparse.Namespace, config: dict[str, str]
) -> int:
    template_path = resolve_template_path(message)
    if not template_path.exists():
        print(f"Error: HL7 template not found: {template_path}", file=sys.stderr)
        return 1

    try:
        (
            mrn,
            account,
            first_name,
            last_name,
            facility,
            unit,
            room,
            admitted_at,
            order_id,
        ) = resolve_cancel_discharge_order_identity(args, config)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    template_lines = template_path.read_text(encoding="utf-8").splitlines()
    message_lines, _ = apply_discharge_order_fields(
        template_lines,
        mrn=mrn,
        account=account,
        first_name=first_name,
        last_name=last_name,
        facility=facility,
        unit=unit,
        room=room,
        admitted_at=admitted_at,
        order_control="OC",
        placer_order_id=order_id,
    )
    hl7_message = format_hl7_message(message_lines)

    result = deliver_hl7_message(
        message,
        args,
        config,
        hl7_message=hl7_message,
        mrn=mrn,
        account=account,
        first_name=first_name,
        last_name=last_name,
        facility=facility,
        unit=unit,
        room=room,
        mrn_display=hl7_mrn(mrn),
        account_display=hl7_account(account),
        admitted_at=admitted_at,
        save_state=False,
    )
    if result == 0:
        print(f"  Cancelled order ID: {order_id}")
    return result


HANDLERS: dict[str, RunHandler] = {
    "admit": run_admit,
    "transfer": run_transfer,
    "discharge": run_discharge,
    "in-transit": run_in_transit,
    "back-in-room": run_back_in_room,
    "update": run_update,
    "discharge-order": run_discharge_order,
    "cancel-discharge-order": run_cancel_discharge_order,
}


def cmd_list(messages: list[Hl7Message]) -> None:
    current_group = None
    for msg in messages:
        if msg.group != current_group:
            current_group = msg.group
            print(f"\n[{current_group}]")
        alias_text = ""
        if msg.aliases:
            alias_text = f"  ({', '.join(msg.aliases)})"
        print(f"  {msg.slug:12}  {msg.event:4}  {msg.name}{alias_text}")


def cmd_help() -> None:
    print(
        """care.ai HL7 runner — help

COMMANDS
  help                         Show this help
  list                         List runnable HL7 messages from the catalog
  clear-admit                  Clear saved admit state
  run <target>                 Build and send an HL7 message
  <target>                     Shorthand for: run <target>

TARGETS
  admit, a01, hl7-admit        ADT A01 admit (requires --facility, --unit, --room)
  transfer, a02, a02b          ADT A02 transfer (new location required; prior from admit)
  in-transit, a09, a09b        ADT A09 in transit (requires --facility, --unit, --room)
  back-in-room, a10, a10b      ADT A10 back in room (defaults to saved admit state)
  update, a08, a08b            ADT A08 update patient (requires --patient)
  discharge, a03, a03b         ADT A03 discharge (defaults to saved admit state)
  discharge-order, disch       ORM O01 discharge task order (defaults to saved admit state)
  cancel-discharge-order, disch-cancel, cancel
                               Cancel ORM discharge task order (uses saved order ID)

TYPICAL WORKFLOW
  ./run_hl7 admit --facility vinelandqa --unit testrack01 --room slot04
                               Admit patient (random account, MRN, patient name)
  ./run_hl7 transfer --facility vinelandqa --unit testrack02 --room slot05
                               Transfer to new location; prior location from admit
  ./run_hl7 in-transit --facility vinelandqa --unit testrack02 --room slot05
                               Move patient in transit to new location
  ./run_hl7 back-in-room       Patient back in room using saved admit data
  ./run_hl7 discharge-order    Send ORM discharge task order using saved admit data
  ./run_hl7 cancel-discharge-order
                               Cancel discharge order using saved order ID
  ./run_hl7 discharge          Discharge using saved admit data
  ./run_hl7 clear-admit        Reset saved admit state

ADMIT OPTIONS
  --facility CODE              Facility mnemonic (required)
  --unit UNIT                  Unit (required)
  --room ROOM                  Room (required)
  --patient [NAME]             Random name by default; pass a name to override
  --account ID                 9-char account (default: random)
  --mrn ID                     7-char MRN (default: random)

TRANSFER OPTIONS
  Requires saved admit state. New destination location is required:
  --facility CODE              Destination facility mnemonic (required)
  --unit UNIT                  Destination unit (required)
  --room ROOM                  Destination room (required)
  Prior location comes from saved admit state.
  Optional overrides: --account, --mrn, --patient

DISCHARGE OPTIONS
  Uses saved admit state by default. Override any field as needed:
  --account ID                 Account number
  --mrn ID                     MRN
  --facility CODE              Facility mnemonic
  --unit UNIT                  Unit
  --room ROOM                  Room
  --patient "First Last"       Patient name

IN-TRANSIT OPTIONS
  Requires saved admit state for patient/account/MRN.
  Destination location is required:
  --facility CODE              Facility mnemonic (required)
  --unit UNIT                  Unit (required)
  --room ROOM                  Room (required)
  Optional overrides: --account, --mrn, --patient

BACK-IN-ROOM OPTIONS
  Uses saved admit state by default. Override any field as needed:
  --account ID                 Account number
  --mrn ID                     MRN
  --facility CODE              Facility mnemonic
  --unit UNIT                  Unit
  --room ROOM                  Room
  --patient "First Last"       Patient name

UPDATE OPTIONS
  Requires --patient and saved admit state for account/MRN/location:
  --patient "First Last"       Updated patient name (required)
  --account ID                 Account number override
  --mrn ID                     MRN override
  --facility CODE              Facility mnemonic override
  --unit UNIT                  Unit override
  --room ROOM                  Room override

DISCHARGE ORDER OPTIONS
  Uses saved admit state by default. Override any field as needed:
  --account ID                 Account number
  --mrn ID                     MRN
  --facility CODE              Facility mnemonic
  --unit UNIT                  Unit
  --room ROOM                  Room
  --patient "First Last"       Patient name

CANCEL DISCHARGE ORDER OPTIONS
  Uses saved admit state and order ID from discharge-order:
  --order-id ID                Placer order ID override (default: saved last_order_id)

SHARED OPTIONS
  --env lab|qa                 Target environment (default: lab)
                               lab  34.74.235.204:2575
                               qa   136.107.162.112:2575
  --dry-run                    Build message and report without sending
  --print                      Print HL7 message to stdout
  --output PATH                Write HL7 message to a file
  --no-save-state              Do not save admit state JSON

EXAMPLES
  ./run_hl7 help
  ./run_hl7 list
  ./run_hl7 admit --facility vinelandqa --unit testrack01 --room slot04
  ./run_hl7 --env qa admit --facility vinelandqa --unit testrack01 --room slot04
  ./run_hl7 a01 --facility vinelandqa --unit testrack01 --room slot04 --dry-run --print
  ./run_hl7 transfer --facility vinelandqa --unit testrack02 --room slot05
  ./run_hl7 discharge --dry-run
  ./run_hl7 a03
  ./run_hl7 in-transit --facility vinelandqa --unit testrack02 --room slot05
  ./run_hl7 back-in-room --dry-run
  ./run_hl7 update --patient "Jane Doe" --dry-run
  ./run_hl7 discharge-order --dry-run
  ./run_hl7 cancel-discharge-order --dry-run
  ./run_hl7 cancel

SETUP
  --env selects the HL7 host. lab is the default.
  lab  34.74.235.204:2575
  qa   136.107.162.112:2575

CATALOG
  scripts/hl7/messages.json

STATE
  Admit saves: scripts/hl7/admit_state.json
  Fields: account, MRN, facility, unit, room, patient name
"""
    )


def add_run_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "target",
        help="Message slug (admit, transfer, discharge-order, disch, discharge, update, etc.)",
    )
    parser.add_argument(
        "--facility",
        metavar="CODE",
        help="Facility mnemonic (required for admit/transfer/in-transit; optional on discharge)",
    )
    parser.add_argument(
        "--unit",
        metavar="UNIT",
        help="Unit (required for admit/transfer/in-transit; optional on discharge)",
    )
    parser.add_argument(
        "--room",
        metavar="ROOM",
        help="Room (required for admit/transfer/in-transit; optional on discharge)",
    )
    parser.add_argument(
        "--patient",
        nargs="?",
        const=RANDOM_PATIENT,
        default=RANDOM_PATIENT,
        metavar="NAME",
        help="Patient name (default: random). Use alone for random.",
    )
    parser.add_argument(
        "--account",
        metavar="ID",
        help="Account number, 9 alphanumeric chars (default: random)",
    )
    parser.add_argument(
        "--mrn",
        metavar="ID",
        help="Medical record number, 7 alphanumeric chars (default: random)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build the message and print summary without sending",
    )
    parser.add_argument(
        "--print",
        dest="print_message",
        action="store_true",
        help="Print the HL7 message to stdout",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        help="Write the HL7 message to a file",
    )
    parser.add_argument(
        "--no-save-state",
        action="store_true",
        help="Do not save admit state for follow-up messages",
    )
    parser.add_argument(
        "--order-id",
        metavar="ID",
        help="Placer order ID for cancel-discharge-order (default: saved last_order_id)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run care.ai HL7 message templates.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("help", help="Show usage help")
    subparsers.add_parser("list", help="List runnable HL7 messages")
    subparsers.add_parser(
        "clear-admit",
        help="Clear saved admit state",
    )

    run_parser = subparsers.add_parser("run", help="Build and send an HL7 message")
    add_run_arguments(run_parser)

    return parser


def normalize_argv(argv: list[str] | None) -> list[str]:
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        return argv

    commands = {"help", "list", "run", "clear-admit"}
    if argv[0] not in commands and not argv[0].startswith("-"):
        return ["run", *argv]
    return argv


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    try:
        env_name, raw_argv = extract_hl7_env(raw_argv)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    argv = normalize_argv(raw_argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    config = apply_hl7_env(load_config(), env_name)

    if args.command == "help":
        cmd_help()
        return 0

    catalog_path = resolve_catalog_path(config)
    if not catalog_path.exists():
        print(f"Error: HL7 catalog not found: {catalog_path}", file=sys.stderr)
        return 1

    messages = load_catalog(catalog_path)

    if args.command == "list":
        cmd_list(messages)
        return 0

    if args.command == "clear-admit":
        admit_state_path = resolve_admit_state_path(config)
        clear_admit_state(admit_state_path)
        print(f"Cleared admit state: {admit_state_path}")
        return 0

    if args.command == "run":
        try:
            message = resolve_target(messages, args.target)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

        handler = HANDLERS.get(message.slug)
        if not handler:
            print(
                f"Error: No handler implemented for '{message.slug}' yet.",
                file=sys.stderr,
            )
            return 1
        return handler(message, args, config)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
