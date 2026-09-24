#!/usr/bin/env python3
"""Calculate engagement velocity and view acceleration from metric snapshots."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, TextIO


METRICS = ("views", "likes", "comments", "shares", "saves")


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_jsonl(stream: TextIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream if line.strip()]


def load_db(path: str) -> list[dict[str, Any]]:
    with closing(sqlite3.connect(path)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT item_id, captured_at, views, likes, comments, shares, saves,
                   followers, source, freshness_seconds, field_confidence
            FROM metric_snapshots
            ORDER BY item_id, captured_at
            """
        ).fetchall()
    return [dict(row) for row in rows]


def metric_velocity(
    newer: dict[str, Any], older: dict[str, Any], metric: str, hours: float, warnings: list[str]
) -> float | None:
    current = newer.get(metric)
    previous = older.get(metric)
    if current is None or previous is None:
        return None
    delta = current - previous
    if delta < 0:
        warnings.append(f"counter_decreased:{metric}")
        return None
    return delta / hours


def calculate_item_velocity(
    item_id: str, snapshots: list[dict[str, Any]], acceleration_cap: float = 10.0
) -> dict[str, Any]:
    warnings: list[str] = []
    valid: list[tuple[datetime, dict[str, Any]]] = []
    for snapshot in snapshots:
        try:
            valid.append((parse_timestamp(snapshot["captured_at"]), snapshot))
        except (KeyError, TypeError, ValueError):
            warnings.append("invalid_captured_at")
    valid.sort(key=lambda pair: pair[0])
    result: dict[str, Any] = {
        "item_id": item_id,
        "snapshot_count": len(valid),
        "latest_captured_at": valid[-1][1].get("captured_at") if valid else None,
        "window_hours": None,
        "view_velocity": None,
        "like_velocity": None,
        "comment_velocity": None,
        "share_velocity": None,
        "save_velocity": None,
        "acceleration": None,
        "status": "potential_candidate",
        "warnings": warnings,
    }
    if len(valid) < 2:
        return result

    latest_time, latest = valid[-1]
    previous_time, previous = valid[-2]
    hours = (latest_time - previous_time).total_seconds() / 3600
    if hours <= 0:
        warnings.append("non_positive_latest_window")
        result["status"] = "invalid"
        return result
    result["window_hours"] = round(hours, 6)
    for metric in METRICS:
        result[f"{metric[:-1] if metric.endswith('s') else metric}_velocity"] = metric_velocity(
            latest, previous, metric, hours, warnings
        )

    if len(valid) >= 3:
        earlier_time, earlier = valid[-3]
        previous_hours = (previous_time - earlier_time).total_seconds() / 3600
        if previous_hours > 0:
            current_view_velocity = result.get("view_velocity")
            previous_view_velocity = metric_velocity(
                previous, earlier, "views", previous_hours, warnings
            )
            if current_view_velocity is not None and previous_view_velocity is not None:
                if previous_view_velocity > 0:
                    result["acceleration"] = min(
                        acceleration_cap, current_view_velocity / previous_view_velocity
                    )
                elif current_view_velocity > 0:
                    result["acceleration"] = acceleration_cap
                else:
                    result["acceleration"] = 1.0
        else:
            warnings.append("non_positive_previous_window")

    result["status"] = "velocity_ready"
    result["field_confidence"] = latest.get("field_confidence") or "low"
    result["freshness_seconds"] = latest.get("freshness_seconds")
    return result


def calculate_all(snapshots: Iterable[dict[str, Any]], acceleration_cap: float = 10.0) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for snapshot in snapshots:
        item_id = snapshot.get("item_id")
        if item_id:
            grouped.setdefault(item_id, []).append(snapshot)
    return [
        calculate_item_velocity(item_id, rows, acceleration_cap)
        for item_id, rows in sorted(grouped.items())
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", "-i", help="metric snapshot JSONL")
    source.add_argument("--db", help="SQLite database created by upsert_snapshots.py")
    parser.add_argument("--output", "-o", default="-")
    parser.add_argument("--acceleration-cap", type=float, default=10.0)
    args = parser.parse_args()

    if args.db:
        snapshots = load_db(args.db)
    else:
        input_stream = sys.stdin if args.input == "-" else Path(args.input).open("r", encoding="utf-8")
        try:
            snapshots = load_jsonl(input_stream)
        finally:
            if input_stream is not sys.stdin:
                input_stream.close()
    results = calculate_all(snapshots, args.acceleration_cap)
    output_stream = sys.stdout if args.output == "-" else Path(args.output).open("w", encoding="utf-8", newline="\n")
    try:
        for result in results:
            output_stream.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
    finally:
        if output_stream is not sys.stdout:
            output_stream.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
