#!/usr/bin/env python3
"""Nomad controller: chooses the best available compute node and migrates safely."""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().replace(microsecond=0).isoformat()


def truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def run_external(
    command: list[str] | str,
    cwd: Path,
    dry_run: bool = False,
    timeout_seconds: int = 30,
) -> tuple[int, str, str]:
    if dry_run:
        logging.info("[DRY-RUN] %s", command if isinstance(command, str) else " ".join(command))
        return 0, "", ""

    result = subprocess.run(
        command,
        cwd=str(cwd),
        shell=isinstance(command, str),
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def run_probe(check: dict[str, Any], repo_dir: Path, dry_run: bool) -> tuple[bool, str]:
    check_type = check.get("type", "command")

    if check_type == "command":
        command = check.get("command")
        if not command:
            return False, "missing check.command"
        code, out, err = run_external(command, cwd=repo_dir, dry_run=dry_run, timeout_seconds=20)
        if code == 0:
            return True, out or "command check ok"
        return False, err or out or "command check failed"

    if check_type == "url":
        url = check.get("url")
        if not url:
            return False, "missing check.url"
        if dry_run:
            return True, "[DRY-RUN] url check"
        try:
            import requests

            response = requests.get(url, timeout=10)
            if response.status_code < 300:
                return True, f"url check ok ({response.status_code})"
            return False, f"url check failed ({response.status_code})"
        except Exception as exc:  # noqa: BLE001
            return False, f"url check error: {exc}"

    if check_type == "env":
        env_var = check.get("env")
        if not env_var:
            return False, "missing check.env"
        return truthy(os.environ.get(env_var)), f"env check: {env_var}"

    return False, f"unsupported check.type: {check_type}"


def evaluate_quota(provider: dict[str, Any]) -> tuple[bool, str]:
    quota = provider.get("quota", {})
    if not isinstance(quota, dict) or not quota:
        return True, "no quota rules"

    hours_env = quota.get("hours_env")
    min_hours = quota.get("min_hours")
    if hours_env and min_hours is not None:
        remaining = parse_float(os.environ.get(hours_env))
        if remaining is None:
            return False, f"{hours_env} missing/invalid"
        if remaining < float(min_hours):
            return False, f"{hours_env}={remaining} below min_hours={min_hours}"

    credit_env = quota.get("credit_env")
    min_credit = quota.get("min_credit")
    if credit_env and min_credit is not None:
        remaining = parse_float(os.environ.get(credit_env))
        if remaining is None:
            return False, f"{credit_env} missing/invalid"
        if remaining < float(min_credit):
            return False, f"{credit_env}={remaining} below min_credit={min_credit}"

    return True, "quota ok"


def assess_provider(provider: dict[str, Any], repo_dir: Path, dry_run: bool) -> dict[str, Any]:
    name = provider.get("name", "unknown")
    priority = int(provider.get("priority", 999))
    enabled = provider.get("enabled", True)
    if not enabled:
        return {
            "name": name,
            "priority": priority,
            "available": False,
            "reason": "disabled",
        }

    check = provider.get("check", {})
    check_ok, check_msg = run_probe(check, repo_dir, dry_run)
    if not check_ok:
        return {
            "name": name,
            "priority": priority,
            "available": False,
            "reason": check_msg,
        }

    quota_ok, quota_msg = evaluate_quota(provider)
    if not quota_ok:
        return {
            "name": name,
            "priority": priority,
            "available": False,
            "reason": quota_msg,
        }

    return {
        "name": name,
        "priority": priority,
        "available": True,
        "reason": f"{check_msg}; {quota_msg}",
    }


def choose_provider(assessments: list[dict[str, Any]]) -> dict[str, Any] | None:
    available = [item for item in assessments if item.get("available")]
    if not available:
        return None
    available.sort(key=lambda item: int(item.get("priority", 999)))
    return available[0]


def read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2)


def find_provider(config: dict[str, Any], name: str) -> dict[str, Any] | None:
    for provider in config.get("providers", []):
        if provider.get("name") == name:
            return provider
    return None


def parse_iso_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def can_migrate(state: dict[str, Any], min_gap_minutes: int) -> bool:
    last_at = parse_iso_date(state.get("last_migration_at"))
    if not last_at:
        return True
    if last_at.tzinfo is None:
        last_at = last_at.replace(tzinfo=timezone.utc)
    return utc_now() - last_at >= timedelta(minutes=min_gap_minutes)


def notify_webhook(config: dict[str, Any], event: str, payload: dict[str, Any], dry_run: bool) -> None:
    webhook_url = config.get("notification_webhook_url")
    if not webhook_url:
        return
    if dry_run:
        logging.info("[DRY-RUN] webhook %s -> %s", event, webhook_url)
        return
    try:
        import requests

        requests.post(
            webhook_url,
            json={"event": event, "at": utc_now_iso(), "payload": payload},
            timeout=15,
        )
    except Exception as exc:  # noqa: BLE001
        logging.warning("webhook failed: %s", exc)


def run_migration_sequence(
    repo_dir: Path,
    config: dict[str, Any],
    target_provider: dict[str, Any],
    dry_run: bool,
) -> tuple[bool, list[dict[str, Any]]]:
    sequence_results: list[dict[str, Any]] = []

    def execute(label: str, command: list[str] | str | None, timeout_seconds: int = 300) -> bool:
        if not command:
            sequence_results.append({"step": label, "ok": True, "message": "skipped"})
            return True
        code, out, err = run_external(command, cwd=repo_dir, dry_run=dry_run, timeout_seconds=timeout_seconds)
        ok = code == 0
        sequence_results.append(
            {
                "step": label,
                "ok": ok,
                "message": out or err or ("ok" if ok else "failed"),
            }
        )
        return ok

    backup_command = config.get(
        "backup_command",
        [sys.executable, "scripts/auto_backup.py", "--once"],
    )
    restore_command = config.get(
        "restore_command",
        [sys.executable, "scripts/auto_restore.py"],
    )
    migrate_command = target_provider.get("migrate_command")
    verify_command = target_provider.get("verify_command")

    if not execute("backup_before_migrate", backup_command, timeout_seconds=300):
        return False, sequence_results
    if not execute("provider_migrate", migrate_command, timeout_seconds=900):
        return False, sequence_results
    if not execute("restore_after_migrate", restore_command, timeout_seconds=300):
        return False, sequence_results
    if not execute("verify_target", verify_command, timeout_seconds=120):
        return False, sequence_results

    return True, sequence_results


def run_cycle(
    repo_dir: Path,
    config: dict[str, Any],
    state_path: Path,
    dry_run: bool,
    force_migrate: bool,
) -> dict[str, Any]:
    state = read_json(state_path, default={"active_provider": None, "last_migration_at": None})
    providers = config.get("providers", [])
    assessments = [assess_provider(provider, repo_dir, dry_run) for provider in providers]
    selected = choose_provider(assessments)
    active = state.get("active_provider")

    cycle: dict[str, Any] = {
        "started_at": utc_now_iso(),
        "active_provider": active,
        "selected_provider": selected.get("name") if selected else None,
        "assessments": assessments,
        "migration": {"attempted": False, "ok": True, "details": []},
    }

    sentinel_name = config.get("sentinel_provider")
    if sentinel_name:
        sentinel_assessment = next((a for a in assessments if a.get("name") == sentinel_name), None)
        if sentinel_assessment and not sentinel_assessment.get("available"):
            logging.warning("sentinel provider unavailable: %s", sentinel_assessment.get("reason"))

    if not selected:
        cycle["migration"]["ok"] = False
        cycle["migration"]["details"].append({"step": "selection", "ok": False, "message": "no provider available"})
        cycle["finished_at"] = utc_now_iso()
        return cycle

    target_name = selected["name"]
    if active == target_name:
        cycle["migration"]["details"].append({"step": "selection", "ok": True, "message": "staying on active provider"})
        cycle["finished_at"] = utc_now_iso()
        return cycle

    min_gap = int(config.get("min_migration_gap_minutes", 10))
    if not force_migrate and active and not can_migrate(state, min_gap):
        cycle["migration"]["ok"] = False
        cycle["migration"]["details"].append(
            {
                "step": "migration_gate",
                "ok": False,
                "message": f"min migration gap not reached ({min_gap} min)",
            }
        )
        cycle["finished_at"] = utc_now_iso()
        return cycle

    target_provider = find_provider(config, target_name)
    if not target_provider:
        cycle["migration"]["ok"] = False
        cycle["migration"]["details"].append(
            {"step": "lookup_target", "ok": False, "message": f"provider not found in config: {target_name}"}
        )
        cycle["finished_at"] = utc_now_iso()
        return cycle

    cycle["migration"]["attempted"] = True
    ok, details = run_migration_sequence(repo_dir, config, target_provider, dry_run)
    cycle["migration"]["ok"] = ok
    cycle["migration"]["details"] = details

    if ok:
        state["active_provider"] = target_name
        state["last_migration_at"] = utc_now_iso()
        write_json(state_path, state)
        notify_webhook(config, "migration_success", {"target_provider": target_name}, dry_run=dry_run)
    else:
        notify_webhook(
            config,
            "migration_failed",
            {"target_provider": target_name, "details": details},
            dry_run=dry_run,
        )

    cycle["finished_at"] = utc_now_iso()
    return cycle


def configure_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [NOMAD] %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Nexus nomad controller")
    parser.add_argument(
        "--config",
        default=os.environ.get("NOMAD_CONFIG_PATH", "configs/nomad_config.json"),
        help="Path to nomad config JSON",
    )
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-migrate", action="store_true")
    parser.add_argument("--interval-minutes", type=int, default=None, help="Override config cycle interval")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    repo_dir = Path(os.environ.get("NEXUS_DIR", Path(__file__).resolve().parents[1]))
    configure_logging(repo_dir / "logs" / "nomad_controller.log")

    config_path = repo_dir / args.config if not Path(args.config).is_absolute() else Path(args.config)
    if not config_path.exists():
        fallback = repo_dir / "configs" / "nomad_config.example.json"
        if fallback.exists():
            logging.warning("config not found (%s), using %s", config_path, fallback)
            config_path = fallback
        else:
            logging.error("missing config file: %s", config_path)
            return 2

    with config_path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)

    state_rel = config.get("state_file", "logs/nomad_state.json")
    state_path = repo_dir / state_rel if not Path(state_rel).is_absolute() else Path(state_rel)
    cycle_interval = args.interval_minutes or int(config.get("cycle_minutes", 30))
    cycle_interval = max(cycle_interval, 1)
    snapshot_path = repo_dir / "logs" / "nomad_last_cycle.json"

    while True:
        cycle = run_cycle(
            repo_dir=repo_dir,
            config=config,
            state_path=state_path,
            dry_run=args.dry_run,
            force_migrate=args.force_migrate,
        )
        write_json(snapshot_path, cycle)

        selected = cycle.get("selected_provider")
        migration = cycle.get("migration", {})
        logging.info(
            "active=%s selected=%s migration_attempted=%s migration_ok=%s",
            cycle.get("active_provider"),
            selected,
            migration.get("attempted"),
            migration.get("ok"),
        )
        for detail in migration.get("details", []):
            level = logging.INFO if detail.get("ok", False) else logging.WARNING
            logging.log(level, "%s -> %s", detail.get("step"), detail.get("message"))

        if args.once:
            return 0 if migration.get("ok", True) else 1

        time.sleep(cycle_interval * 60)


if __name__ == "__main__":
    raise SystemExit(main())
