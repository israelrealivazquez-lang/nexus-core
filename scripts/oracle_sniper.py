#!/usr/bin/env python3
"""Oracle ARM sniper using OCI CLI only."""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_command(command: str, dry_run: bool) -> tuple[int, str, str]:
    if dry_run:
        logging.info("[DRY-RUN] %s", command)
        return 0, "{}", ""
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def is_capacity_error(message: str) -> bool:
    msg = message.lower()
    return "out of host capacity" in msg or "out of capacity" in msg


def parse_lifecycle_state(raw_output: str) -> str | None:
    try:
        payload = json.loads(raw_output)
    except json.JSONDecodeError:
        return None
    data = payload.get("data", payload)
    if isinstance(data, dict):
        for key in ("lifecycle-state", "lifecycle_state"):
            value = data.get(key)
            if value:
                return str(value)
    return None


def notify_success(webhook_url: str | None, payload: dict[str, Any], dry_run: bool) -> None:
    if not webhook_url:
        return
    if dry_run:
        logging.info("[DRY-RUN] webhook success notification")
        return
    try:
        import requests

        requests.post(webhook_url, json=payload, timeout=15)
    except Exception as exc:  # noqa: BLE001
        logging.warning("webhook notify failed: %s", exc)


def run_attempt(command: str, webhook_url: str | None, dry_run: bool) -> dict[str, Any]:
    code, out, err = run_command(command, dry_run=dry_run)
    result = {
        "at": utc_now_iso(),
        "ok": False,
        "code": code,
        "state": None,
        "message": "",
    }

    if code != 0:
        if is_capacity_error(err):
            result["message"] = "capacity unavailable"
            return result
        result["message"] = f"oci failed: {err or out}"
        return result

    state = parse_lifecycle_state(out)
    result["state"] = state
    if state in {"PROVISIONING", "RUNNING", "STARTING"}:
        result["ok"] = True
        result["message"] = f"oracle instance state={state}"
        notify_success(
            webhook_url=webhook_url,
            payload={
                "event": "oracle_vm_success",
                "state": state,
                "at": result["at"],
            },
            dry_run=dry_run,
        )
        return result

    result["message"] = "command succeeded but provisioning state not detected"
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Oracle OCI sniper")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--interval-minutes", type=int, default=15)
    parser.add_argument(
        "--command",
        default=os.environ.get("OCI_LAUNCH_COMMAND", "oci compute instance launch --from-json file://configs/oracle_launch.json"),
        help="OCI CLI launch command",
    )
    parser.add_argument("--webhook-url", default=os.environ.get("ORACLE_SUCCESS_WEBHOOK_URL"))
    parser.add_argument("--log-file", default="logs/oracle_sniper.log")
    return parser


def configure_logging(log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [ORACLE] %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )


def main() -> int:
    args = build_parser().parse_args()
    configure_logging(Path(args.log_file))

    while True:
        result = run_attempt(args.command, args.webhook_url, args.dry_run)
        if result["ok"]:
            logging.info("%s", result["message"])
            return 0
        logging.info("%s", result["message"])
        if args.once:
            return 1
        time.sleep(max(args.interval_minutes, 1) * 60)


if __name__ == "__main__":
    raise SystemExit(main())
