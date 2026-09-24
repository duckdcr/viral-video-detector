#!/usr/bin/env python3
"""Persist normalized radar items and metric snapshots in a local SQLite MVP store."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, TextIO


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS content_items (
    id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    external_id TEXT,
    canonical_url TEXT NOT NULL,
    author_id TEXT,
    author_name TEXT,
    market TEXT,
    language TEXT,
    published_at TEXT,
    title TEXT,
    caption TEXT,
    duration_seconds INTEGER,
    topic_tags_json TEXT NOT NULL DEFAULT '[]',
    commercial_flag INTEGER,
    pinned_flag INTEGER,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_content_platform_external
    ON content_items(platform, external_id)
    WHERE external_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_content_market_platform
    ON content_items(market, platform, published_at);

CREATE TABLE IF NOT EXISTS metric_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT NOT NULL REFERENCES content_items(id) ON DELETE CASCADE,
    captured_at TEXT NOT NULL,
    views INTEGER,
    likes INTEGER,
    comments INTEGER,
    shares INTEGER,
    saves INTEGER,
    followers INTEGER,
    source TEXT NOT NULL,
    freshness_seconds INTEGER,
    field_confidence TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(item_id, captured_at, source)
);
CREATE INDEX IF NOT EXISTS idx_snapshot_item_time
    ON metric_snapshots(item_id, captured_at);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def init_db(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)


def as_db_bool(value: Any) -> int | None:
    if value is None:
        return None
    return 1 if bool(value) else 0


def upsert_envelopes(connection: sqlite3.Connection, envelopes: Iterable[dict[str, Any]]) -> tuple[int, int]:
    item_count = 0
    snapshot_count = 0
    now = utc_now()
    with connection:
        for envelope in envelopes:
            item = envelope.get("content_item")
            snapshot = envelope.get("metric_snapshot")
            if not item or not snapshot:
                continue
            connection.execute(
                """
                INSERT INTO content_items (
                    id, platform, external_id, canonical_url, author_id, author_name,
                    market, language, published_at, title, caption, duration_seconds,
                    topic_tags_json, commercial_flag, pinned_flag, source, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    external_id=COALESCE(excluded.external_id, content_items.external_id),
                    canonical_url=COALESCE(excluded.canonical_url, content_items.canonical_url),
                    author_id=COALESCE(excluded.author_id, content_items.author_id),
                    author_name=COALESCE(excluded.author_name, content_items.author_name),
                    market=COALESCE(excluded.market, content_items.market),
                    language=COALESCE(excluded.language, content_items.language),
                    published_at=COALESCE(excluded.published_at, content_items.published_at),
                    title=COALESCE(excluded.title, content_items.title),
                    caption=COALESCE(excluded.caption, content_items.caption),
                    duration_seconds=COALESCE(excluded.duration_seconds, content_items.duration_seconds),
                    topic_tags_json=CASE WHEN excluded.topic_tags_json='[]' THEN content_items.topic_tags_json ELSE excluded.topic_tags_json END,
                    commercial_flag=COALESCE(excluded.commercial_flag, content_items.commercial_flag),
                    pinned_flag=COALESCE(excluded.pinned_flag, content_items.pinned_flag),
                    source=excluded.source,
                    updated_at=excluded.updated_at
                """,
                (
                    item["id"],
                    item["platform"],
                    item.get("external_id"),
                    item["canonical_url"],
                    item.get("author_id"),
                    item.get("author_name"),
                    item.get("market"),
                    item.get("language"),
                    item.get("published_at"),
                    item.get("title"),
                    item.get("caption"),
                    item.get("duration_seconds"),
                    json.dumps(item.get("topic_tags") or [], ensure_ascii=False),
                    as_db_bool(item.get("commercial_flag")),
                    as_db_bool(item.get("pinned_flag")),
                    item.get("source") or "unknown",
                    now,
                    now,
                ),
            )
            item_count += 1
            cursor = connection.execute(
                """
                INSERT INTO metric_snapshots (
                    item_id, captured_at, views, likes, comments, shares, saves,
                    followers, source, freshness_seconds, field_confidence, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(item_id, captured_at, source) DO UPDATE SET
                    views=COALESCE(excluded.views, metric_snapshots.views),
                    likes=COALESCE(excluded.likes, metric_snapshots.likes),
                    comments=COALESCE(excluded.comments, metric_snapshots.comments),
                    shares=COALESCE(excluded.shares, metric_snapshots.shares),
                    saves=COALESCE(excluded.saves, metric_snapshots.saves),
                    followers=COALESCE(excluded.followers, metric_snapshots.followers),
                    freshness_seconds=COALESCE(excluded.freshness_seconds, metric_snapshots.freshness_seconds),
                    field_confidence=excluded.field_confidence
                """,
                (
                    snapshot["item_id"],
                    snapshot["captured_at"],
                    snapshot.get("views"),
                    snapshot.get("likes"),
                    snapshot.get("comments"),
                    snapshot.get("shares"),
                    snapshot.get("saves"),
                    snapshot.get("followers"),
                    snapshot.get("source") or "unknown",
                    snapshot.get("freshness_seconds"),
                    snapshot.get("field_confidence") or "low",
                    now,
                ),
            )
            if cursor.rowcount:
                snapshot_count += 1
    return item_count, snapshot_count


def read_jsonl(stream: TextIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", "-i", default="-")
    parser.add_argument("--db", required=True, help="SQLite database path")
    args = parser.parse_args()
    input_stream = sys.stdin if args.input == "-" else Path(args.input).open("r", encoding="utf-8")
    try:
        envelopes = read_jsonl(input_stream)
    finally:
        if input_stream is not sys.stdin:
            input_stream.close()
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as connection:
        init_db(connection)
        items, snapshots = upsert_envelopes(connection, envelopes)
    print(json.dumps({"items_upserted": items, "snapshots_upserted": snapshots}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
