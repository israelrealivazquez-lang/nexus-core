#!/usr/bin/env python3
"""Nexus auto-restore for new runtime nodes."""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
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


def restore_git(repo_dir: Path, branch: str, dry_run: bool) -> dict[str, Any]:
    status: dict[str, Any] = {"step": "git", "ok": False, "message": ""}

    commands: list[list[str]] = [
        ["git", "fetch", "origin"],
        ["git", "checkout", branch],
        ["git", "pull", "--ff-only", "origin", branch],
    ]
    for command in commands:
        code, out, err = run_command(command, cwd=repo_dir, dry_run=dry_run)
        if code != 0:
            status["message"] = f"{' '.join(command)} failed: {err or out}"
            return status

    status["ok"] = True
    status["message"] = "git restore complete"
    return status


def restore_huggingface(repo_dir: Path, dry_run: bool) -> dict[str, Any]:
    status: dict[str, Any] = {"step": "huggingface", "ok": True, "message": "skipped"}

    token = os.environ.get("HF_TOKEN")
    dataset_repo = os.environ.get("HF_DATASET_REPO", "israel-nexus/knowledge-base")
    knowledge_dir = repo_dir / os.environ.get("HF_SYNC_DIR", "knowledge")
    knowledge_dir.mkdir(parents=True, exist_ok=True)

    if not token:
        status["message"] = "HF_TOKEN not set"
        return status

    command = [
        "huggingface-cli",
        "download",
        dataset_repo,
        "--repo-type",
        "dataset",
        "--local-dir",
        str(knowledge_dir),
        "--token",
        token,
    ]
    code, _, err = run_command(command, cwd=repo_dir, dry_run=dry_run)
    if code != 0:
        status["ok"] = False
        status["message"] = f"hf download failed: {err}"
        return status

    status["message"] = "hf restore complete"
    return status


def check_supabase(dry_run: bool) -> dict[str, Any]:
    status: dict[str, Any] = {"step": "supabase", "ok": True, "message": "skipped"}
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")

    if not (supabase_url and supabase_key):
        status["message"] = "SUPABASE_URL/SUPABASE_KEY not fully set"
        return status
    if dry_run:
        status["message"] = "[DRY-RUN] supabase connectivity check skipped"
        return status

    try:
        import requests

        endpoint = f"{supabase_url.rstrip('/')}/rest/v1/"
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
        }
        response = requests.get(endpoint, headers=headers, timeout=15)
        if response.status_code >= 300:
            status["ok"] = False
            status["message"] = f"supabase check failed: {response.status_code} {response.text[:160]}"
            return status
    except Exception as exc:  # noqa: BLE001
        status["ok"] = False
        status["message"] = f"supabase check error: {exc}"
        return status

    status["message"] = "supabase reachable"
    return status


def install_requirements(repo_dir: Path, dry_run: bool) -> dict[str, Any]:
    status: dict[str, Any] = {"step": "requirements", "ok": True, "message": "skipped"}
    requirements = repo_dir / "requirements.txt"
    if not requirements.exists():
        status["message"] = "requirements.txt not found"
        return status

    command = [sys.executable, "-m", "pip", "install", "-r", str(requirements)]
    code, _, err = run_command(command, cwd=repo_dir, dry_run=dry_run)
    if code != 0:
        status["ok"] = False
        status["message"] = f"pip install failed: {err}"
        return status

    status["message"] = "requirements installed"
    return status


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Nexus auto-restore")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--branch", default=os.environ.get("GIT_BACKUP_BRANCH", "main"))
    parser.add_argument("--skip-git", action="store_true")
    parser.add_argument("--skip-hf", action="store_true")
    parser.add_argument("--skip-supabase", action="store_true")
    parser.add_argument("--install-requirements", action="store_true")
    return parser


def configure_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [RESTORE] %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def main() -> int:
    args = build_parser().parse_args()
    repo_dir = Path(os.environ.get("NEXUS_DIR", Path(__file__).resolve().parents[1]))
    logs_dir = repo_dir / "logs"
    configure_logging(logs_dir / "restore.log")

    steps: list[dict[str, Any]] = []
    if args.install_requirements:
        steps.append(install_requirements(repo_dir, args.dry_run))
    if not args.skip_git:
        steps.append(restore_git(repo_dir, args.branch, args.dry_run))
    if not args.skip_hf:
        steps.append(restore_huggingface(repo_dir, args.dry_run))
    if not args.skip_supabase:
        steps.append(check_supabase(args.dry_run))

    ok = all(step.get("ok", False) for step in steps)
    snapshot = {
        "started_at": utc_now_iso(),
        "finished_at": utc_now_iso(),
        "repo_dir": str(repo_dir),
        "ok": ok,
        "steps": steps,
    }
    with (logs_dir / "restore_last.json").open("w", encoding="utf-8") as handle:
        json.dump(snapshot, handle, ensure_ascii=True, indent=2)

    for step in steps:
        level = logging.INFO if step.get("ok", False) else logging.ERROR
        logging.log(level, "%s -> %s", step["step"], step["message"])

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
