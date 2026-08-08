#!/usr/bin/env python3
"""Ingest pipeline: vault + chat history → structured extracts → letta source.

Usage:
    python3 scripts/ingest.py --vault ~/ObsidianVault --days 90 --source personal_kb --create
    python3 scripts/ingest.py --vault ~/ObsidianVault --days 90 --source personal_kb  # reuse existing source
"""
import argparse
import os
import sys
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone

from scripts.lib.letta_client import LettaClient
from scripts.lib.extract import split_sessions, extract_success_path, render_markdown


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("ingest")


DEFAULT_AGENT_ID = "agent-d622b194-88c6-4972-8421-fda92c1753a0"
DEFAULT_SOURCE = "personal_kb"
EMBEDDING_HANDLE = "litellm/text-embedding-3-large"
EMBEDDING_DIM = 3072
EMBEDDING_CHUNK_SIZE = 300


def _read_vault_files(vault_path: Path) -> list[Path]:
    files = []
    for md_file in vault_path.rglob("*.md"):
        if any(part.startswith(".obsidian") for part in md_file.parts):
            continue
        files.append(md_file)
    return sorted(files)


def _filter_messages(messages: list[dict], days: int) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = []
    for m in messages:
        date_str = m.get("date", "")
        if not date_str:
            continue
        try:
            msg_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            continue
        if msg_date >= cutoff:
            result.append(m)
    return result


def _upload_vault_files(client: LettaClient, source_id: str, vault_files: list[Path]) -> int:
    uploaded = 0
    for md_file in vault_files:
        try:
            client.upload_file(source_id, str(md_file))
            uploaded += 1
            log.info(f"  uploaded vault file: {md_file.relative_to(md_file.parts[0])}")
        except Exception as e:
            log.warning(f"  failed to upload {md_file}: {e}")
    return uploaded


def _process_chats(client: LettaClient, source_id: str, agent_id: str, days: int) -> int:
    log.info(f"fetching messages for agent {agent_id} (last {days} days)...")
    raw = client.list_messages(agent_id, limit=2000)
    recent = _filter_messages(raw, days)
    log.info(f"  {len(recent)} recent messages")
    if len(recent) < 2:
        return 0
    sessions = split_sessions(recent)
    log.info(f"  {len(sessions)} sessions identified")
    uploaded = 0
    for i, session in enumerate(sessions):
        extracted = extract_success_path(session)
        if not extracted:
            log.debug(f"  session {i}: no success path, skipping")
            continue
        md = render_markdown(extracted)
        tmp_path = Path("/tmp") / f"extract_{agent_id}_{i}.md"
        tmp_path.write_text(md)
        try:
            client.upload_file(source_id, str(tmp_path), name=extracted["frontmatter"].get("session_topic", f"session_{i}"))
            uploaded += 1
            log.info(f"  uploaded extract: {extracted['frontmatter'].get('session_topic', f'session_{i}')}")
        except Exception as e:
            log.warning(f"  failed to upload extract for session {i}: {e}")
        finally:
            tmp_path.unlink(missing_ok=True)
    return uploaded


def run_ingest(vault: str, days: int, source_name: str, create: bool, agent_id: str) -> int:
    client = LettaClient()
    vault_path = Path(vault).expanduser()
    if not vault_path.is_dir():
        log.error(f"vault not found: {vault_path}")
        return 1
    if create:
        log.info(f"creating source {source_name!r}...")
        source_id = client.create_source(source_name, EMBEDDING_HANDLE, EMBEDDING_DIM, EMBEDDING_CHUNK_SIZE)
        log.info(f"  source id: {source_id}")
    else:
        existing = client.get_source_by_name(source_name)
        if not existing:
            log.error(f"source {source_name!r} not found and --create not set")
            return 1
        source_id = existing["id"]
        log.info(f"reusing source {source_name!r} (id={source_id})")
    log.info("clearing existing files...")
    existing_files = client.list_source_files(source_id)
    for f in existing_files:
        client.delete_source_file(source_id, f["id"])
    log.info(f"  deleted {len(existing_files)} files")
    log.info(f"reading vault: {vault_path}")
    vault_files = _read_vault_files(vault_path)
    log.info(f"  found {len(vault_files)} markdown files")
    uploaded_vault = _upload_vault_files(client, source_id, vault_files)
    log.info(f"  uploaded {uploaded_vault}/{len(vault_files)} vault files")
    uploaded_chats = _process_chats(client, source_id, agent_id, days)
    log.info(f"  uploaded {uploaded_chats} chat extracts")
    log.info(f"done. source_id={source_id}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Ingest vault + chats into letta source")
    parser.add_argument("--vault", required=True, help="Path to Obsidian vault")
    parser.add_argument("--days", type=int, default=90, help="Look back N days for chat messages")
    parser.add_argument("--source", default=DEFAULT_SOURCE, help="Source name (default: personal_kb)")
    parser.add_argument("--create", action="store_true", help="Create new source (default: reuse existing)")
    parser.add_argument("--agent-id", default=os.environ.get("LETTA_AGENT_ID", DEFAULT_AGENT_ID))
    args = parser.parse_args()
    sys.exit(run_ingest(args.vault, args.days, args.source, args.create, args.agent_id))


if __name__ == "__main__":
    main()
