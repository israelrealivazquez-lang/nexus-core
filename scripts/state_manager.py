#!/usr/bin/env python3
"""Supabase lock manager for distributed Nexus workers."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import requests


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().replace(microsecond=0).isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


class SupabaseClient:
    def __init__(self, url: str, key: str, lock_table: str, dlq_table: str) -> None:
        self.url = url.rstrip("/")
        self.key = key
        self.lock_table = lock_table
        self.dlq_table = dlq_table
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        payload: Any | None = None,
        prefer: str | None = None,
    ) -> requests.Response:
        headers = dict(self.headers)
        if prefer:
            headers["Prefer"] = prefer
        endpoint = f"{self.url}/rest/v1/{path.lstrip('/')}"
        response = requests.request(
            method=method,
            url=endpoint,
            headers=headers,
            params=params,
            json=payload,
            timeout=20,
        )
        return response

    def get_lock(self, task_id: str) -> dict[str, Any] | None:
        params = {
            "task_id": f"eq.{task_id}",
            "select": "task_id,node_id,status,lock_ttl",
            "limit": "1",
        }
        response = self._request("GET", self.lock_table, params=params)
        if response.status_code >= 300:
            raise RuntimeError(f"get_lock failed: {response.status_code} {response.text[:200]}")
        rows = response.json()
        if not rows:
            return None
        return rows[0]

    def upsert_lock(self, row: dict[str, Any]) -> None:
        response = self._request(
            "POST",
            self.lock_table,
            payload=row,
            prefer="resolution=merge-duplicates,return=minimal",
        )
        if response.status_code >= 300:
            raise RuntimeError(f"upsert_lock failed: {response.status_code} {response.text[:200]}")

    def delete_lock(self, task_id: str, node_id: str) -> None:
        params = {
            "task_id": f"eq.{task_id}",
            "node_id": f"eq.{node_id}",
        }
        response = self._request("DELETE", self.lock_table, params=params, prefer="return=minimal")
        if response.status_code >= 300:
            raise RuntimeError(f"delete_lock failed: {response.status_code} {response.text[:200]}")

    def insert_dlq(self, row: dict[str, Any]) -> None:
        response = self._request("POST", self.dlq_table, payload=row, prefer="return=minimal")
        if response.status_code >= 300:
            raise RuntimeError(f"insert_dlq failed: {response.status_code} {response.text[:200]}")


def is_lock_active(lock_row: dict[str, Any] | None) -> bool:
    if not lock_row:
        return False
    lock_ttl = lock_row.get("lock_ttl")
    expiry = parse_iso(lock_ttl) if isinstance(lock_ttl, str) else None
    if expiry is None:
        # If the row exists but has no parseable TTL, treat as active for safety.
        return True
    return expiry > utc_now()


def acquire_lock(client: SupabaseClient, task_id: str, node_id: str, ttl_minutes: int) -> tuple[bool, str]:
    existing = client.get_lock(task_id)
    if existing and is_lock_active(existing) and existing.get("node_id") != node_id:
        return False, f"locked by {existing.get('node_id')} until {existing.get('lock_ttl')}"

    expires = (utc_now() + timedelta(minutes=ttl_minutes)).replace(microsecond=0).isoformat()
    row = {
        "task_id": task_id,
        "node_id": node_id,
        "status": "locked",
        "lock_ttl": expires,
    }
    client.upsert_lock(row)
    return True, f"lock acquired until {expires}"


def heartbeat_lock(client: SupabaseClient, task_id: str, node_id: str, ttl_minutes: int) -> tuple[bool, str]:
    existing = client.get_lock(task_id)
    if not existing:
        return False, "lock does not exist"
    if existing.get("node_id") != node_id:
        return False, f"lock owned by {existing.get('node_id')}"

    expires = (utc_now() + timedelta(minutes=ttl_minutes)).replace(microsecond=0).isoformat()
    row = {
        "task_id": task_id,
        "node_id": node_id,
        "status": "locked",
        "lock_ttl": expires,
    }
    client.upsert_lock(row)
    return True, f"heartbeat ok until {expires}"


def release_lock(client: SupabaseClient, task_id: str, node_id: str) -> tuple[bool, str]:
    existing = client.get_lock(task_id)
    if not existing:
        return True, "lock already released"
    if existing.get("node_id") != node_id:
        return False, f"lock owned by {existing.get('node_id')}"
    client.delete_lock(task_id, node_id)
    return True, "lock released"


def send_dlq(client: SupabaseClient, task_id: str, node_id: str, error_message: str, payload: str) -> tuple[bool, str]:
    row = {
        "task_id": task_id,
        "node_id": node_id,
        "error_message": error_message[:2000],
        "payload": payload[:16000],
        "status": "pending",
        "created_at": utc_now_iso(),
    }
    client.insert_dlq(row)
    return True, "dlq entry inserted"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Nexus distributed lock manager (Supabase)")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--node-id", default=os.environ.get("NEXUS_NODE_ID", os.environ.get("COMPUTERNAME", "local-node")))
    parser.add_argument("--ttl-minutes", type=int, default=60)
    parser.add_argument("--action", choices=["acquire", "heartbeat", "release", "status", "dlq"], required=True)
    parser.add_argument("--error-message", default="")
    parser.add_argument("--payload", default="")
    parser.add_argument("--lock-table", default=os.environ.get("SUPABASE_LOCK_TABLE", "nexus_locks"))
    parser.add_argument("--dlq-table", default=os.environ.get("SUPABASE_DLQ_TABLE", "dead_letter_queue"))
    return parser


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [STATE] %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def main() -> int:
    configure_logging()
    args = build_parser().parse_args()

    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    if not (supabase_url and supabase_key):
        logging.error("SUPABASE_URL and SUPABASE_KEY are required")
        return 2

    client = SupabaseClient(
        url=supabase_url,
        key=supabase_key,
        lock_table=args.lock_table,
        dlq_table=args.dlq_table,
    )

    try:
        if args.action == "acquire":
            ok, message = acquire_lock(client, args.task_id, args.node_id, args.ttl_minutes)
        elif args.action == "heartbeat":
            ok, message = heartbeat_lock(client, args.task_id, args.node_id, args.ttl_minutes)
        elif args.action == "release":
            ok, message = release_lock(client, args.task_id, args.node_id)
        elif args.action == "status":
            lock = client.get_lock(args.task_id)
            output = {"task_id": args.task_id, "lock": lock, "active": is_lock_active(lock)}
            print(json.dumps(output, ensure_ascii=True))
            return 0
        else:
            ok, message = send_dlq(client, args.task_id, args.node_id, args.error_message, args.payload)
    except Exception as exc:  # noqa: BLE001
        logging.error("%s", exc)
        return 1

    if ok:
        logging.info("%s", message)
        return 0
    logging.warning("%s", message)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
