#!/usr/bin/env python3
"""Nexus auto-backup for GitHub, HuggingFace, Supabase marker and optional rclone."""

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


def run_command(
    command: list[str] | str,
    cwd: Path,
    dry_run: bool = False,
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
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def git_backup(repo_dir: Path, branch: str, dry_run: bool) -> dict[str, Any]:
    status: dict[str, Any] = {"step": "git", "ok": False, "message": ""}

    code, _, err = run_command(["git", "add", "-A"], cwd=repo_dir, dry_run=dry_run)
    if code != 0:
        status["message"] = f"git add failed: {err}"
        return status

    code, out, err = run_command(["git", "status", "--porcelain"], cwd=repo_dir, dry_run=dry_run)
    if code != 0:
        status["message"] = f"git status failed: {err}"
        return status
    if not out and not dry_run:
        status["ok"] = True
        status["message"] = "no changes"
        return status

    message = f"auto-backup {utc_now_iso()}"
    code, out, err = run_command(["git", "commit", "-m", message], cwd=repo_dir, dry_run=dry_run)
    if code != 0 and "nothing to commit" not in (out + err).lower():
        status["message"] = f"git commit failed: {err or out}"
        return status

    code, _, err = run_command(["git", "push", "origin", branch], cwd=repo_dir, dry_run=dry_run)
    if code != 0:
        status["message"] = f"git push failed: {err}"
        return status

    status["ok"] = True
    status["message"] = "git backup complete"
    return status


def huggingface_backup(repo_dir: Path, dry_run: bool) -> dict[str, Any]:
    status: dict[str, Any] = {"step": "huggingface", "ok": True, "message": "skipped"}

    token = os.environ.get("HF_TOKEN")
    dataset_repo = os.environ.get("HF_DATASET_REPO", "israel-nexus/knowledge-base")
    knowledge_dir = os.environ.get("HF_SYNC_DIR", "knowledge")
    local_path = repo_dir / knowledge_dir

    if not token:
        status["message"] = "HF_TOKEN not set"
        return status
    if not local_path.exists():
        status["message"] = f"missing local path: {local_path}"
        return status

    command = [
        "huggingface-cli",
        "upload",
        dataset_repo,
        str(local_path),
        ".",
        "--repo-type",
        "dataset",
        "--token",
        token,
    ]
    code, _, err = run_command(command, cwd=repo_dir, dry_run=dry_run)
    if code != 0:
        status["ok"] = False
        status["message"] = f"hf upload failed: {err}"
        return status

    status["message"] = "hf backup complete"
    return status


def supabase_marker(repo_dir: Path, dry_run: bool) -> dict[str, Any]:
    status: dict[str, Any] = {"step": "supabase_marker", "ok": True, "message": "skipped"}

    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    backup_table = os.environ.get("SUPABASE_BACKUP_TABLE")

    if not (supabase_url and supabase_key and backup_table):
        status["message"] = "SUPABASE_URL/SUPABASE_KEY/SUPABASE_BACKUP_TABLE not fully set"
        return status

    payload = {
        "node_id": os.environ.get("NEXUS_NODE_ID", os.environ.get("COMPUTERNAME", "local-node")),
        "run_at": utc_now_iso(),
        "status": "ok",
        "source": "auto_backup.py",
    }

    if dry_run:
        status["message"] = f"[DRY-RUN] would insert into {backup_table}"
        return status

    try:
        import requests

        endpoint = f"{supabase_url.rstrip('/')}/rest/v1/{backup_table}"
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }
        response = requests.post(endpoint, headers=headers, json=payload, timeout=20)
        if response.status_code >= 300:
            status["ok"] = False
            status["message"] = f"supabase marker failed: {response.status_code} {response.text[:180]}"
            return status
    except Exception as exc:  # noqa: BLE001
        status["ok"] = False
        status["message"] = f"supabase marker error: {exc}"
        return status

    status["message"] = "supabase marker inserted"
    return status


def rclone_sync(repo_dir: Path, dry_run: bool) -> dict[str, Any]:
    status: dict[str, Any] = {"step": "rclone", "ok": True, "message": "skipped"}

    remote = os.environ.get("RCLONE_REMOTE")
    if not remote:
        status["message"] = "RCLONE_REMOTE not set"
        return status

    source = os.environ.get("RCLONE_SOURCE", "thesis_chapters")
    source_path = repo_dir / source
    if not source_path.exists():
        status["message"] = f"source path missing: {source_path}"
        return status

    command = ["rclone", "sync", str(source_path), remote, "--create-empty-src-dirs"]
    code, _, err = run_command(command, cwd=repo_dir, dry_run=dry_run)
    if code != 0:
        status["ok"] = False
        status["message"] = f"rclone sync failed: {err}"
        return status

    status["message"] = "rclone sync complete"
    return status


def run_cycle(repo_dir: Path, args: argparse.Namespace) -> dict[str, Any]:
    cycle_result: dict[str, Any] = {
        "started_at": utc_now_iso(),
        "repo_dir": str(repo_dir),
        "steps": [],
    }

    if not args.skip_git:
        cycle_result["steps"].append(git_backup(repo_dir, args.branch, args.dry_run))
    if not args.skip_hf:
        cycle_result["steps"].append(huggingface_backup(repo_dir, args.dry_run))
    if not args.skip_supabase:
        cycle_result["steps"].append(supabase_marker(repo_dir, args.dry_run))
    if not args.skip_rclone:
        cycle_result["steps"].append(rclone_sync(repo_dir, args.dry_run))

    failures = [step for step in cycle_result["steps"] if not step.get("ok", False)]
    cycle_result["ok"] = len(failures) == 0
    cycle_result["finished_at"] = utc_now_iso()
    return cycle_result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Nexus auto-backup loop")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    parser.add_argument("--dry-run", action="store_true", help="Do not execute external commands")
    parser.add_argument("--branch", default=os.environ.get("GIT_BACKUP_BRANCH", "main"))
    parser.add_argument("--interval-minutes", type=int, default=30)
    parser.add_argument("--skip-git", action="store_true")
    parser.add_argument("--skip-hf", action="store_true")
    parser.add_argument("--skip-supabase", action="store_true")
    parser.add_argument("--skip-rclone", action="store_true")
    return parser


def configure_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [BACKUP] %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def main() -> int:
    args = build_parser().parse_args()
    repo_dir = Path(os.environ.get("NEXUS_DIR", Path(__file__).resolve().parents[1]))
    logs_dir = repo_dir / "logs"
    configure_logging(logs_dir / "backup.log")
    summary_path = logs_dir / "backup_last.json"

    while True:
        result = run_cycle(repo_dir, args)
        with summary_path.open("w", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=True, indent=2)

        for step in result["steps"]:
            level = logging.INFO if step.get("ok", False) else logging.ERROR
            logging.log(level, "%s -> %s", step["step"], step["message"])

        if args.once:
            return 0 if result["ok"] else 1

        sleep_seconds = max(args.interval_minutes, 1) * 60
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
