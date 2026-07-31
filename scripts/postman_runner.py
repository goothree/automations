"""Run care.ai dev Postman collection requests from the command line.

Examples:
    python scripts/postman_runner.py list
    python scripts/postman_runner.py run a01
    python scripts/postman_runner.py run adt --patient "Miguel Indurain"
    python scripts/postman_runner.py run all --patient "Miguel Indurain"
    python scripts/postman_runner.py run bed-movement --device-id "CAI240418489" --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import string
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COLLECTION = REPO_ROOT / "scripts/postman/care.ai_dev.postman_collection.json"
DEFAULT_POSTMAN_ENV = REPO_ROOT / "scripts/postman/Inbound_Dev.postman_environment.json"
DEFAULT_ADMIT_STATE = REPO_ROOT / "scripts/postman/admit_state.json"
DEVICE_ID_PREFIX = "cai:"
ACCOUNT_ID_LENGTH = 9
ACCOUNT_ID_CHARS = string.ascii_uppercase + string.digits
MRN_ID_LENGTH = 7
MRN_ID_CHARS = string.digits
RANDOM_FIRST_NAMES = (
    "James", "Maria", "Robert", "Linda", "Michael", "Patricia", "David", "Jennifer",
    "William", "Elizabeth", "Richard", "Barbara", "Joseph", "Susan", "Thomas", "Jessica",
    "Charles", "Sarah", "Christopher", "Karen", "Daniel", "Nancy", "Matthew", "Lisa",
)
RANDOM_LAST_NAMES = (
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Wilson", "Anderson", "Thomas", "Taylor",
    "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson", "White", "Harris",
)
ENV_FILES = (
    REPO_ROOT / "scripts/postman/.env",
    REPO_ROOT / ".env",
)


@dataclass(frozen=True)
class PostmanRequest:
    group: str
    name: str
    slug: str
    method: str
    url: str
    body: str | None
    needs_auth: bool


@dataclass
class AdmitState:
    account_number: str
    medical_record_number: str
    facility: str
    unit: str
    room: str
    coid: str = ""
    patient_first_name: str = ""
    patient_last_name: str = ""
    admitted_at: str = ""
    last_order_id: str = ""
    saved_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


@dataclass
class AdmitStateOverrides:
    account_number: str = ""
    medical_record_number: str = ""
    facility: str = ""
    unit: str = ""
    room: str = ""
    patient_first_name: str = ""
    patient_last_name: str = ""


@dataclass
class RunResult:
    action: str
    group: str
    slug: str
    method: str
    url: str
    tenant: str = ""
    facility: str = ""
    patient_name: str = ""
    account_number: str = ""
    medical_record_number: str = ""
    unit: str = ""
    room: str = ""
    bed: str = ""
    device_id: str = ""
    module: str = ""
    event_type: str = ""
    http_status: int | None = None
    outcome: str = "pending"
    error: str = ""
    dry_run: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def summary_lines(self) -> list[str]:
        lines = [
            f"{self.action} ({self.method}) — {self.outcome}",
        ]
        if self.facility:
            lines.append(f"  Facility:  {self.facility}")
        if self.tenant:
            lines.append(f"  Tenant:    {self.tenant}")
        if self.patient_name:
            lines.append(f"  Patient:   {self.patient_name}")
        if self.account_number:
            lines.append(f"  Account:   {self.account_number}")
        if self.medical_record_number:
            lines.append(f"  MRN:       {self.medical_record_number}")
        location_parts = [part for part in (self.unit, self.room, self.bed) if part]
        if location_parts:
            lines.append(f"  Location:  {' / '.join(location_parts)}")
        if self.device_id:
            lines.append(f"  Device:    {self.device_id}")
        if self.module:
            lines.append(f"  Module:    {self.module}")
        if self.event_type:
            lines.append(f"  Event:     {self.event_type}")
        if self.http_status is not None:
            lines.append(f"  HTTP:      {self.http_status}")
        if self.error:
            lines.append(f"  Error:     {self.error}")
        if self.dry_run:
            lines.append("  Note:      dry run (request not sent)")
        return lines


def load_postman_environment(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return {
        entry["key"]: str(entry.get("value", ""))
        for entry in data.get("values", [])
        if entry.get("enabled", True) and entry.get("key")
    }


def resolve_postman_env_path() -> Path | None:
    configured = os.getenv("POSTMAN_ENV_PATH")
    if configured:
        path = Path(configured)
        return path if path.is_absolute() else REPO_ROOT / path
    if DEFAULT_POSTMAN_ENV.exists():
        return DEFAULT_POSTMAN_ENV
    return None


def load_config() -> dict[str, str]:
    postman_vars: dict[str, str] = {}
    postman_env_path = resolve_postman_env_path()
    if postman_env_path and postman_env_path.exists():
        postman_vars = load_postman_environment(postman_env_path)

    for env_file in ENV_FILES:
        if env_file.exists():
            load_dotenv(env_file, override=True)

    def get(postman_key: str, env_key: str, default: str = "") -> str:
        return os.getenv(env_key) or postman_vars.get(postman_key, default)

    return {
        "client_id": get("client_id", "CLIENT_ID"),
        "client_secret": get("client_secret", "CLIENT_SECRET"),
        "audience": get("audience", "AUDIENCE"),
        "dev_inbound_url": get(
            "dev_inbound_url", "DEV_INBOUND_URL", "dev-inbound.care.ai"
        ),
        "dev_tenant": get("dev_tenant", "DEV_TENANT", "lab"),
        "HcaFacilityMnemonic": get("HcaFacilityMnemonic", "HCA_FACILITY_MNEMONIC"),
        "auth_url": os.getenv("AUTH_URL", "https://dev-auth.care.ai/oauth/token"),
        "collection_path": os.getenv("COLLECTION_PATH", str(DEFAULT_COLLECTION)),
        "admit_state_path": os.getenv("ADMIT_STATE_PATH", str(DEFAULT_ADMIT_STATE)),
    }


def substitute_variables(text: str, variables: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in variables or variables[key] == "":
            raise ValueError(f"Missing required variable: {key}")
        return variables[key]

    return re.sub(r"\{\{([^}]+)\}\}", replace, text)


def slugify(name: str) -> str:
    bracket = re.match(r"^\[([^\]]+)\]", name)
    if bracket:
        return bracket.group(1).lower()

    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug


def walk_items(items: list[dict[str, Any]], group: str = "") -> list[PostmanRequest]:
    requests_list: list[PostmanRequest] = []

    for item in items:
        if "item" in item:
            folder_name = item.get("name", group)
            requests_list.extend(walk_items(item["item"], folder_name))
            continue

        request = item.get("request")
        if not request:
            continue

        name = item.get("name", "Unnamed")
        url_obj = request.get("url")
        if not url_obj:
            continue

        raw_url = url_obj.get("raw")
        if not raw_url:
            continue

        method = request.get("method", "GET").upper()
        auth = request.get("auth") or {}
        needs_auth = auth.get("type") != "noauth"

        body = None
        body_obj = request.get("body") or {}
        if body_obj.get("mode") == "raw":
            body = body_obj.get("raw")

        requests_list.append(
            PostmanRequest(
                group=group,
                name=name,
                slug=slugify(name),
                method=method,
                url=raw_url,
                body=body,
                needs_auth=needs_auth,
            )
        )

    return requests_list


def load_collection(path: Path) -> list[PostmanRequest]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return walk_items(data.get("item", []))


def fetch_access_token(config: dict[str, str]) -> str:
    missing = [
        key
        for key in ("client_id", "client_secret", "audience")
        if not config.get(key)
    ]
    if missing:
        env_names = {
            "client_id": "CLIENT_ID",
            "client_secret": "CLIENT_SECRET",
            "audience": "AUDIENCE",
        }
        raise ValueError(
            "Missing OAuth credentials: "
            + ", ".join(env_names[key] for key in missing)
            + ". Copy scripts/postman/.env.example to scripts/postman/.env and fill in values."
        )

    response = requests.post(
        config["auth_url"],
        json={
            "grant_type": "client_credentials",
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "audience": config["audience"],
        },
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    token = response.json().get("access_token")
    if not token:
        raise RuntimeError(f"No access_token in auth response: {response.text}")
    return token


def resolve_targets(
    requests_list: list[PostmanRequest], target: str
) -> list[PostmanRequest]:
    normalized = target.lower().strip()

    if normalized == "all":
        return requests_list

    by_slug = {req.slug: req for req in requests_list}
    by_group: dict[str, list[PostmanRequest]] = {}
    for req in requests_list:
        group_key = req.group.lower()
        by_group.setdefault(group_key, []).append(req)

    if normalized in by_slug:
        return [by_slug[normalized]]

    if normalized in by_group:
        return by_group[normalized]

    matches = [
        req
        for req in requests_list
        if normalized in req.slug or normalized in req.name.lower()
    ]
    if len(matches) == 1:
        return matches
    if len(matches) > 1:
        names = ", ".join(req.slug for req in matches)
        raise ValueError(f"Ambiguous target '{target}'. Matches: {names}")

    available = ", ".join(sorted({req.slug for req in requests_list} | set(by_group)))
    raise ValueError(f"Unknown target '{target}'. Available: {available}, adt, orm, all")


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _patient_name(first: Any, last: Any) -> str:
    return " ".join(part for part in (_clean(first), _clean(last)) if part)


def generate_random_account_id(length: int = ACCOUNT_ID_LENGTH) -> str:
    return "".join(secrets.choice(ACCOUNT_ID_CHARS) for _ in range(length))


def generate_random_mrn(length: int = MRN_ID_LENGTH) -> str:
    return "".join(secrets.choice(MRN_ID_CHARS) for _ in range(length))


def generate_random_patient_name() -> tuple[str, str]:
    return secrets.choice(RANDOM_FIRST_NAMES), secrets.choice(RANDOM_LAST_NAMES)


def apply_ids_to_body(json_body: dict[str, Any], account: str, mrn: str) -> None:
    if account:
        json_body["AccountNumber"] = account
    payload_items = json_body.get("Payload") or []
    if payload_items and isinstance(payload_items[0], dict):
        payload = payload_items[0]
        if account:
            payload["AccountNumber"] = account
        if mrn:
            payload["MedicalRecordNumber"] = mrn


def apply_patient_name_to_body(
    json_body: dict[str, Any], first_name: str, last_name: str
) -> None:
    payload_items = json_body.get("Payload") or []
    if not payload_items or not isinstance(payload_items[0], dict):
        return

    payload = payload_items[0]
    if "FirstName" in payload or "LastName" in payload:
        payload["FirstName"] = first_name
        payload["LastName"] = last_name


def is_admit_request(req: PostmanRequest, json_body: dict[str, Any] | None) -> bool:
    if req.slug == "a01":
        return True
    if not json_body:
        return False
    payload_items = json_body.get("Payload") or []
    if payload_items and isinstance(payload_items[0], dict):
        return _clean(payload_items[0].get("AdtTriggerEvent")) == "A01"
    return False


def request_needs_patient(req: PostmanRequest) -> bool:
    if req.slug in {"a01", "a02", "a03"}:
        return False
    return bool(req.body and '"FirstName"' in req.body)


def parse_patient_name(patient: str) -> tuple[str, str]:
    patient = patient.strip()
    if not patient:
        raise ValueError("Patient name cannot be empty")
    parts = patient.split()
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def resolve_patient_name(args: argparse.Namespace) -> tuple[str, str]:
    if getattr(args, "patient", None):
        return parse_patient_name(args.patient)
    first = os.getenv("PATIENT_FIRST_NAME", "").strip()
    last = os.getenv("PATIENT_LAST_NAME", "").strip()
    if first or last:
        return first, last
    return "", ""


def request_needs_device_id(req: PostmanRequest) -> bool:
    return req.slug == "bed-movement" or "deviceId=" in req.url


def apply_device_id_to_url(url: str, device_id: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query["deviceId"] = [device_id.strip()]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def format_device_id(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Device ID cannot be empty")
    lower = value.lower()
    if lower.startswith(DEVICE_ID_PREFIX):
        value = value[len(DEVICE_ID_PREFIX) :]
    value = value.strip()
    if not value:
        raise ValueError("Device ID cannot be empty")
    return f"{DEVICE_ID_PREFIX}{value}"


def resolve_device_id(args: argparse.Namespace) -> str:
    raw = ""
    if getattr(args, "device_id", None):
        raw = args.device_id.strip()
    elif os.getenv("DEVICE_ID", "").strip():
        raw = os.getenv("DEVICE_ID", "").strip()
    if not raw:
        return ""
    return format_device_id(raw)


def generate_admit_ids(json_body: dict[str, Any]) -> tuple[str, str]:
    account = generate_random_account_id()
    mrn = generate_random_mrn()
    apply_ids_to_body(json_body, account, mrn)
    return account, mrn


def resolve_admit_state_path(config: dict[str, str]) -> Path:
    path = Path(config["admit_state_path"])
    return path if path.is_absolute() else REPO_ROOT / path


def extract_admit_state(json_body: dict[str, Any]) -> AdmitState:
    payload_items = json_body.get("Payload") or []
    payload = payload_items[0] if payload_items and isinstance(payload_items[0], dict) else {}
    location = payload.get("Location") or {}
    return AdmitState(
        account_number=_clean(json_body.get("AccountNumber") or payload.get("AccountNumber")),
        medical_record_number=_clean(payload.get("MedicalRecordNumber")),
        facility=_clean(json_body.get("HcaFacilityMnemonic")),
        unit=_clean(location.get("Unit")) if isinstance(location, dict) else "",
        room=_clean(location.get("Room")) if isinstance(location, dict) else "",
        coid=_clean(location.get("Coid")) if isinstance(location, dict) else "",
        patient_first_name=_clean(payload.get("FirstName")),
        patient_last_name=_clean(payload.get("LastName")),
    )


def load_admit_state(path: Path) -> AdmitState | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    account = _clean(data.get("account_number"))
    if not account:
        return None
    return AdmitState(
        account_number=account,
        medical_record_number=_clean(data.get("medical_record_number")),
        facility=_clean(data.get("facility")),
        unit=_clean(data.get("unit")),
        room=_clean(data.get("room")),
        coid=_clean(data.get("coid")),
        patient_first_name=_clean(data.get("patient_first_name")),
        patient_last_name=_clean(data.get("patient_last_name")),
        admitted_at=_clean(data.get("admitted_at")),
        last_order_id=_clean(data.get("last_order_id")),
        saved_at=_clean(data.get("saved_at")),
    )


def save_admit_state(path: Path, state: AdmitState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")


def clear_admit_state(path: Path) -> None:
    if path.exists():
        path.unlink()


def uses_admit_state(req: PostmanRequest) -> bool:
    return req.slug in {"a02", "a03"}


def is_transfer_request(req: PostmanRequest) -> bool:
    return req.slug == "a02"


def transfer_location_complete(overrides: AdmitStateOverrides) -> bool:
    return bool(overrides.facility and overrides.unit and overrides.room)


def has_admit_location_overrides(overrides: AdmitStateOverrides) -> bool:
    return bool(overrides.facility or overrides.unit or overrides.room)


def merge_admit_state(base: AdmitState, overrides: AdmitStateOverrides) -> AdmitState:
    def pick(override: str, default: str) -> str:
        return override if override else default

    return AdmitState(
        account_number=pick(overrides.account_number, base.account_number),
        medical_record_number=pick(overrides.medical_record_number, base.medical_record_number),
        facility=pick(overrides.facility, base.facility),
        unit=pick(overrides.unit, base.unit),
        room=pick(overrides.room, base.room),
        patient_first_name=pick(overrides.patient_first_name, base.patient_first_name),
        patient_last_name=pick(overrides.patient_last_name, base.patient_last_name),
        saved_at=base.saved_at,
    )


def build_transfer_state(base: AdmitState, destination: AdmitStateOverrides) -> AdmitState:
    def pick(override: str, default: str) -> str:
        return override if override else default

    return AdmitState(
        account_number=pick(destination.account_number, base.account_number),
        medical_record_number=pick(destination.medical_record_number, base.medical_record_number),
        facility=destination.facility,
        unit=destination.unit,
        room=destination.room,
        patient_first_name=pick(destination.patient_first_name, base.patient_first_name),
        patient_last_name=pick(destination.patient_last_name, base.patient_last_name),
        saved_at=base.saved_at,
    )


def resolve_admit_overrides(args: argparse.Namespace) -> AdmitStateOverrides:
    patient_first_name = ""
    patient_last_name = ""
    if getattr(args, "patient", None):
        patient_first_name, patient_last_name = parse_patient_name(args.patient)

    return AdmitStateOverrides(
        account_number=_clean(getattr(args, "account", None) or ""),
        medical_record_number=_clean(getattr(args, "mrn", None) or ""),
        facility=_clean(getattr(args, "facility", None) or ""),
        unit=_clean(getattr(args, "unit", None) or ""),
        room=_clean(getattr(args, "room", None) or ""),
        patient_first_name=patient_first_name,
        patient_last_name=patient_last_name,
    )


def _location_dict(unit: str, room: str, *, coid: str = "", bed: str = "") -> dict[str, str]:
    return {
        "Bed": bed,
        "Coid": coid,
        "Room": room,
        "Unit": unit,
    }


def apply_admit_state_to_body(json_body: dict[str, Any], state: AdmitState) -> None:
    apply_ids_to_body(json_body, state.account_number, state.medical_record_number)
    if state.facility:
        json_body["HcaFacilityMnemonic"] = state.facility
    payload_items = json_body.get("Payload") or []
    if not payload_items or not isinstance(payload_items[0], dict):
        return
    payload = payload_items[0]
    if state.patient_first_name or state.patient_last_name:
        apply_patient_name_to_body(
            json_body, state.patient_first_name, state.patient_last_name
        )
    location = payload.get("Location")
    if not isinstance(location, dict):
        return
    if state.unit:
        location["Unit"] = state.unit
    if state.room:
        location["Room"] = state.room


def apply_transfer_to_body(
    json_body: dict[str, Any],
    base: AdmitState,
    destination: AdmitStateOverrides,
) -> None:
    identity = build_transfer_state(base, destination)
    apply_ids_to_body(json_body, identity.account_number, identity.medical_record_number)
    apply_patient_name_to_body(
        json_body, identity.patient_first_name, identity.patient_last_name
    )

    json_body["HcaFacilityMnemonic"] = destination.facility

    payload_items = json_body.get("Payload") or []
    if not payload_items or not isinstance(payload_items[0], dict):
        return
    payload = payload_items[0]

    coid = base.coid or _clean((payload.get("Location") or {}).get("Coid"))
    prior_location = _location_dict(base.unit, base.room, coid=coid)
    destination_location = _location_dict(
        destination.unit, destination.room, coid=coid
    )

    payload["PriorHcaFacilityMnemonic"] = base.facility
    payload["DestinationHcaFacilityMnemonic"] = destination.facility
    payload["PriorLocation"] = prior_location
    payload["DestinationLocation"] = destination_location
    payload["Location"] = destination_location


def extract_run_result(
    req: PostmanRequest,
    *,
    url: str,
    json_body: dict[str, Any] | None,
    config: dict[str, str],
    dry_run: bool,
) -> RunResult:
    result = RunResult(
        action=req.name,
        group=req.group,
        slug=req.slug,
        method=req.method,
        url=url,
        tenant=config.get("dev_tenant", ""),
        dry_run=dry_run,
    )

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if query.get("deviceId"):
        result.device_id = query["deviceId"][0]
    if query.get("module"):
        result.module = query["module"][0].replace("%20", " ")

    tenant_match = re.search(r"/tenants/([^/]+)/", parsed.path)
    if tenant_match:
        result.tenant = tenant_match.group(1)

    if not json_body:
        return result

    result.facility = _clean(json_body.get("HcaFacilityMnemonic")) or _clean(
        config.get("HcaFacilityMnemonic", "")
    )
    result.account_number = _clean(json_body.get("AccountNumber"))

    payload_items = json_body.get("Payload") or []
    if not payload_items:
        return result

    payload = payload_items[0] if isinstance(payload_items[0], dict) else {}
    result.patient_name = _patient_name(payload.get("FirstName"), payload.get("LastName"))
    result.medical_record_number = _clean(payload.get("MedicalRecordNumber"))
    result.event_type = _clean(payload.get("AdtTriggerEvent") or payload.get("EventType"))
    event_name = _clean(payload.get("EventName"))
    if event_name:
        result.event_type = (
            f"{result.event_type} ({event_name})"
            if result.event_type
            else event_name
        )

    if not result.account_number:
        result.account_number = _clean(payload.get("AccountNumber"))

    location = payload.get("Location") or {}
    if isinstance(location, dict):
        result.unit = _clean(location.get("Unit"))
        result.room = _clean(location.get("Room"))
        result.bed = _clean(location.get("Bed"))

    if req.slug == "a02":
        destination = payload.get("DestinationLocation") or {}
        prior = payload.get("PriorLocation") or {}
        if isinstance(destination, dict):
            result.facility = _clean(
                payload.get("DestinationHcaFacilityMnemonic")
                or json_body.get("HcaFacilityMnemonic")
            )
            result.unit = _clean(destination.get("Unit")) or result.unit
            result.room = _clean(destination.get("Room")) or result.room
            result.bed = _clean(destination.get("Bed")) or result.bed
        if isinstance(prior, dict) and (prior.get("Unit") or prior.get("Room")):
            prior_parts = [
                _clean(payload.get("PriorHcaFacilityMnemonic")),
                _clean(prior.get("Unit")),
                _clean(prior.get("Room")),
            ]
            prior_text = " / ".join(part for part in prior_parts if part)
            if prior_text:
                result.event_type = (
                    f"{result.event_type} (from {prior_text})"
                    if result.event_type
                    else f"from {prior_text}"
                )

    return result


def print_run_report(results: list[RunResult]) -> None:
    if not results:
        return

    print("\n" + "=" * 60)
    print("Run Report")
    print("=" * 60)
    for index, result in enumerate(results, start=1):
        print(f"\n{index}. " + result.summary_lines()[0])
        for line in result.summary_lines()[1:]:
            print(line)
    print("\n" + "=" * 60)
    successes = sum(1 for result in results if result.outcome.startswith("OK"))
    failures = sum(1 for result in results if result.outcome.startswith("FAILED"))
    skipped = sum(1 for result in results if result.dry_run)
    print(
        f"Total: {len(results)} | OK: {successes} | Failed: {failures} | Dry run: {skipped}"
    )
    print("=" * 60)


def save_run_report(results: list[RunResult], report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "results": [asdict(result) for result in results],
    }
    if report_path.suffix.lower() == ".json":
        report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return

    lines = [f"Run Report — {payload['generated_at']}", "=" * 60, ""]
    for index, result in enumerate(results, start=1):
        lines.append(f"{index}. " + result.summary_lines()[0])
        lines.extend(result.summary_lines()[1:])
        lines.append("")
    lines.extend(
        [
            "=" * 60,
            f"Total: {len(results)}",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")


def run_request(
    req: PostmanRequest,
    config: dict[str, str],
    *,
    dry_run: bool = False,
    verbose: bool = False,
    generate_ids: bool = True,
    patient_first_name: str = "",
    patient_last_name: str = "",
    device_id: str = "",
    saved_admit_state: AdmitState | None = None,
    admit_overrides: AdmitStateOverrides | None = None,
    admit_state_path: Path | None = None,
) -> RunResult:
    variables = {
        "client_id": config["client_id"],
        "client_secret": config["client_secret"],
        "audience": config["audience"],
        "dev_inbound_url": config["dev_inbound_url"],
        "dev_tenant": config["dev_tenant"],
        "HcaFacilityMnemonic": config["HcaFacilityMnemonic"],
    }

    url = substitute_variables(req.url, variables)
    if device_id and request_needs_device_id(req):
        url = apply_device_id_to_url(url, device_id)
    headers: dict[str, str] = {}
    json_body: dict[str, Any] | None = None

    if req.body:
        body_text = substitute_variables(req.body.replace("\r\n", "\n"), variables)
        json_body = json.loads(body_text)
        headers["Content-Type"] = "application/json"
        if generate_ids and is_admit_request(req, json_body):
            generate_admit_ids(json_body)
        if is_admit_request(req, json_body):
            overrides = admit_overrides or AdmitStateOverrides()
            if overrides.patient_first_name or overrides.patient_last_name:
                apply_patient_name_to_body(
                    json_body,
                    overrides.patient_first_name,
                    overrides.patient_last_name,
                )
            else:
                admit_first, admit_last = generate_random_patient_name()
                apply_patient_name_to_body(json_body, admit_first, admit_last)
            if has_admit_location_overrides(overrides):
                state = merge_admit_state(extract_admit_state(json_body), overrides)
                apply_admit_state_to_body(json_body, state)
        elif uses_admit_state(req) and saved_admit_state:
            overrides = admit_overrides or AdmitStateOverrides()
            if is_transfer_request(req):
                apply_transfer_to_body(json_body, saved_admit_state, overrides)
            else:
                state = merge_admit_state(saved_admit_state, overrides)
                apply_admit_state_to_body(json_body, state)
        elif patient_first_name or patient_last_name:
            apply_patient_name_to_body(
                json_body,
                patient_first_name,
                patient_last_name,
            )

    result = extract_run_result(
        req, url=url, json_body=json_body, config=config, dry_run=dry_run
    )

    if req.needs_auth:
        if dry_run and not all(
            config.get(k) for k in ("client_id", "client_secret", "audience")
        ):
            variables["access_token"] = "dry-run-token"
        else:
            try:
                variables["access_token"] = fetch_access_token(config)
            except Exception as exc:
                result.outcome = "FAILED"
                result.error = str(exc)
                print(f"\n==> {req.group} / {req.name} ({req.method})")
                if result.patient_name:
                    print(f"    Patient: {result.patient_name}")
                if result.facility:
                    print(f"    Facility: {result.facility}")
                print(f"    ERROR: {exc}", file=sys.stderr)
                return result
        headers["Authorization"] = f"Bearer {variables['access_token']}"

    print(f"\n==> {req.group} / {req.name} ({req.method})")
    print(f"    {url}")
    if result.account_number:
        print(f"    Account: {result.account_number}")
    if result.medical_record_number:
        print(f"    MRN: {result.medical_record_number}")
    if result.patient_name:
        print(f"    Patient: {result.patient_name}")
    if is_transfer_request(req) and json_body:
        payload = (json_body.get("Payload") or [{}])[0]
        prior = payload.get("PriorLocation") or {}
        dest = payload.get("DestinationLocation") or {}
        if prior:
            print(
                "    Prior: "
                + " / ".join(
                    part
                    for part in (
                        payload.get("PriorHcaFacilityMnemonic", ""),
                        prior.get("Unit", ""),
                        prior.get("Room", ""),
                    )
                    if part
                )
            )
        if dest:
            print(
                "    Destination: "
                + " / ".join(
                    part
                    for part in (
                        payload.get("DestinationHcaFacilityMnemonic", ""),
                        dest.get("Unit", ""),
                        dest.get("Room", ""),
                    )
                    if part
                )
            )
    elif result.facility:
        print(f"    Facility: {result.facility}")
    location_parts = [part for part in (result.unit, result.room, result.bed) if part]
    if location_parts and not is_transfer_request(req):
        print(f"    Location: {' / '.join(location_parts)}")
    if result.device_id:
        print(f"    Device: {result.device_id}")

    if dry_run:
        print("    (dry run — request not sent)")
        if verbose and json_body is not None:
            print(json.dumps(json_body, indent=2)[:2000])
        result.outcome = "DRY RUN"
        return result

    try:
        response = requests.request(
            req.method,
            url,
            headers=headers,
            json=json_body,
            timeout=60,
        )
        result.http_status = response.status_code
        print(f"    Status: {response.status_code}")
        if verbose or not response.ok:
            print(f"    Body: {response.text[:2000]}")
        response.raise_for_status()
        result.outcome = f"OK {response.status_code}"
        if (
            is_admit_request(req, json_body)
            and admit_state_path is not None
            and json_body is not None
        ):
            saved = extract_admit_state(json_body)
            save_admit_state(admit_state_path, saved)
            print(f"    Saved admit state: {admit_state_path}")
    except Exception as exc:
        result.error = str(exc)
        if result.http_status is not None:
            result.outcome = f"FAILED {result.http_status}"
        else:
            result.outcome = "FAILED"
        print(f"    ERROR: {exc}", file=sys.stderr)

    return result


def cmd_list(requests_list: list[PostmanRequest]) -> None:
    current_group = None
    for req in requests_list:
        if req.group != current_group:
            current_group = req.group
            print(f"\n[{current_group}]")
        print(f"  {req.slug:12}  {req.method:6}  {req.name}")


def cmd_help() -> None:
    print(
        """care.ai Postman runner — help

COMMANDS
  help                         Show this help
  list                         List runnable requests from the collection
  clear-admit                  Clear saved admit state (transfer/discharge defaults)
  run <target>                 Run one or more collection requests
  <target>                     Shorthand for: run <target>

TARGETS
  a01                          Admit (A01)
  a02                          Transfer (A02) — new location required; account/MRN from admit
  a03                          Discharge (A03) — defaults to saved admit state
  a08, a13                     Other ADT updates
  disch                        ORM discharge order
  bed-movement                 Bed movement simulation (PATCH)
  adt, orm                     Run all requests in a folder
  all                          Run all requests

TYPICAL WORKFLOW
  ./run_postman a01            Admit patient (auto-generates account, MRN, patient name)
  ./run_postman a02 --facility CODE --unit UNIT --room ROOM
                               Transfer to new location; account/MRN/patient from admit
  ./run_postman a03            Discharge using saved admit data
  ./run_postman clear-admit    Reset saved admit state

ADMIT (a01) OVERRIDES
  Defaults: facility from env (HcaFacilityMnemonic); unit/room from collection template.
  Optional overrides:
    --facility CODE            Facility mnemonic
    --unit UNIT                Unit
    --room ROOM                Room
    --patient "First Last"     Patient name (otherwise random)

TRANSFER (a02)
  Requires new destination location (--facility, --unit, --room):
    Sets DestinationHcaFacilityMnemonic, DestinationLocation, and Location
  Preserves prior admit location in PriorHcaFacilityMnemonic and PriorLocation
  Account, MRN, and patient name default to saved admit state
  Optional overrides: --account, --mrn, --patient

DISCHARGE (a03) OVERRIDES
  Saved admit data is the default. Override any field as needed:
    --account ID               Account number
    --mrn ID                   MRN
    --facility CODE            Facility mnemonic
    --unit UNIT                Unit
    --room ROOM                Room
    --patient "First Last"     Patient name

OTHER OPTIONS
  --device-id ID               Bed movement device suffix (cai: added automatically)
  --dry-run                    Build request and report without sending
  --verbose, -v                Print response bodies
  --report PATH                Save report to PATH (.txt or .json)
  --no-report-file             Skip default report file
  --no-generate-ids            Use collection account/MRN on admit instead of random

EXAMPLES
  ./run_postman help
  ./run_postman list
  ./run_postman a01
  ./run_postman a01 --facility COCQA1A --unit "J.1W" --room "J.119"
  ./run_postman a02 --facility COCQA1A --unit "J.2W" --room "J.205"
  ./run_postman a03 --patient "Jane Doe"
  ./run_postman bed-movement --device-id "CAI240418489"
  ./run_postman a01 --dry-run

SETUP
  Copy Inbound_Dev.postman_environment.json to scripts/postman/
  Optional: cp scripts/postman/.env.example scripts/postman/.env

REPORTS
  Saved to reports/postman/run_<timestamp>.txt by default

STATE
  Admit saves: scripts/postman/admit_state.json
  Fields: account, MRN, facility, unit, room, patient name
"""
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run care.ai dev Postman collection requests."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("help", help="Show usage help")
    subparsers.add_parser("list", help="List runnable requests from the collection")
    subparsers.add_parser(
        "clear-admit",
        help="Clear saved admit state used by transfer/discharge",
    )

    run_parser = subparsers.add_parser("run", help="Run one or more collection requests")
    run_parser.add_argument(
        "target",
        help="Request slug (a01, disch, bed-movement), folder (adt, orm), or all",
    )
    run_parser.add_argument(
        "--patient",
        metavar="NAME",
        help="Override patient name (optional on admit; transfer/discharge default to saved admit; required for a08/a13)",
    )
    run_parser.add_argument(
        "--account",
        metavar="ID",
        help="Override account number on transfer/discharge (default: saved admit)",
    )
    run_parser.add_argument(
        "--mrn",
        metavar="ID",
        help="Override MRN on transfer/discharge (default: saved admit)",
    )
    run_parser.add_argument(
        "--facility",
        metavar="CODE",
        help="Facility mnemonic; optional on admit/discharge; required destination on transfer (a02)",
    )
    run_parser.add_argument(
        "--unit",
        metavar="UNIT",
        help="Unit; optional on admit/discharge; required destination on transfer (a02)",
    )
    run_parser.add_argument(
        "--room",
        metavar="ROOM",
        help="Room; optional on admit/discharge; required destination on transfer (a02)",
    )
    run_parser.add_argument(
        "--device-id",
        metavar="ID",
        help='Device suffix for bed-movement; cai: is added automatically (e.g. "CAI240418489")',
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve URL/body and print without sending the request",
    )
    run_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print response bodies (always printed on error)",
    )
    run_parser.add_argument(
        "--report",
        metavar="PATH",
        help="Write run report to this file (.txt or .json). Default: reports/postman/run_<timestamp>.txt",
    )
    run_parser.add_argument(
        "--no-report-file",
        action="store_true",
        help="Skip writing the default report file",
    )
    run_parser.add_argument(
        "--no-generate-ids",
        action="store_true",
        help="Use collection Account/MRN values instead of generating random IDs on admit",
    )

    return parser


def default_report_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return REPO_ROOT / "reports" / "postman" / f"run_{stamp}.txt"


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
    argv = normalize_argv(argv)
    parser = build_parser()
    args = parser.parse_args(argv)

    config = load_config()
    collection_path = Path(config["collection_path"])
    if not collection_path.is_absolute():
        collection_path = REPO_ROOT / collection_path

    if not collection_path.exists():
        print(f"Collection not found: {collection_path}", file=sys.stderr)
        return 1

    requests_list = load_collection(collection_path)
    if not requests_list:
        print("No runnable requests found in collection.", file=sys.stderr)
        return 1

    if args.command == "help":
        cmd_help()
        return 0

    if args.command == "list":
        cmd_list(requests_list)
        return 0

    admit_state_path = resolve_admit_state_path(config)
    if args.command == "clear-admit":
        clear_admit_state(admit_state_path)
        print(f"Cleared admit state: {admit_state_path}")
        return 0

    try:
        targets = resolve_targets(requests_list, args.target)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    saved_admit_state = load_admit_state(admit_state_path)
    if any(uses_admit_state(req) for req in targets) and not saved_admit_state:
        print(
            "Error: No saved admit state. Run ./run_postman a01 first, "
            f"or clear with ./run_postman clear-admit if stale. Expected: {admit_state_path}",
            file=sys.stderr,
        )
        return 1

    admit_overrides = resolve_admit_overrides(args)

    needs_patient = any(request_needs_patient(req) for req in targets)
    needs_device = any(request_needs_device_id(req) for req in targets)
    if any(is_transfer_request(req) for req in targets) and not transfer_location_complete(
        admit_overrides
    ):
        print(
            "Error: transfer requires --facility, --unit, and --room for the new location",
            file=sys.stderr,
        )
        return 1

    patient_first_name, patient_last_name = resolve_patient_name(args)
    device_id = resolve_device_id(args)
    if needs_patient and not patient_first_name and not patient_last_name:
        print(
            'Error: --patient is required for non-admit ADT requests (e.g. --patient "Miguel Indurain")',
            file=sys.stderr,
        )
        return 1
    if needs_device and not device_id:
        print(
            'Error: --device-id is required for bed-movement (e.g. --device-id "CAI240418489")',
            file=sys.stderr,
        )
        return 1

    failures = 0
    results: list[RunResult] = []
    for req in targets:
        try:
            result = run_request(
                req,
                config,
                dry_run=args.dry_run,
                verbose=args.verbose,
                generate_ids=not args.no_generate_ids,
                patient_first_name=patient_first_name,
                patient_last_name=patient_last_name,
                device_id=device_id,
                saved_admit_state=saved_admit_state,
                admit_overrides=admit_overrides,
                admit_state_path=admit_state_path,
            )
        except Exception as exc:
            result = RunResult(
                action=req.name,
                group=req.group,
                slug=req.slug,
                method=req.method,
                url=req.url,
                tenant=config.get("dev_tenant", ""),
                facility=config.get("HcaFacilityMnemonic", ""),
                outcome="FAILED",
                error=str(exc),
                dry_run=args.dry_run,
            )
            print(f"    ERROR: {exc}", file=sys.stderr)
        results.append(result)
        if result.outcome.startswith("FAILED"):
            failures += 1

    print_run_report(results)

    if args.command == "run" and not args.no_report_file:
        report_path = Path(args.report) if args.report else default_report_path()
        if not report_path.is_absolute():
            report_path = REPO_ROOT / report_path
        save_run_report(results, report_path)
        print(f"\nReport saved: {report_path}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
