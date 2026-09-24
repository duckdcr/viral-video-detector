#!/usr/bin/env python3
"""Deduplicate one scan batch of normalized radar envelopes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, TextIO


def read_jsonl(stream: TextIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream if line.strip()]


def metric_completeness(envelope: dict[str, Any]) -> int:
    snapshot = envelope.get("metric_snapshot") or {}
    return sum(snapshot.get(key) is not None for key in ("views", "likes", "comments", "shares", "saves", "followers"))


def merge_non_null(primary: dict[str, Any], secondary: dict[str, Any]) -> dict[str, Any]:
    merged = dict(primary)
    for key, value in secondary.items():
        if merged.get(key) in (None, "", []) and value not in (None, "", []):
            merged[key] = value
    return merged


def deduplicate(envelopes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for envelope in envelopes:
        item = envelope.get("content_item") or {}
        item_id = item.get("id")
        if not item_id:
            continue
        grouped.setdefault(item_id, []).append(envelope)

    output: list[dict[str, Any]] = []
    for item_id, group in grouped.items():
        ranked = sorted(
            group,
            key=lambda row: (
                metric_completeness(row),
                (row.get("metric_snapshot") or {}).get("captured_at") or "",
            ),
            reverse=True,
        )
        winner = json.loads(json.dumps(ranked[0]))
        sources: set[str] = set()
        warnings: set[str] = set(winner.get("normalization", {}).get("warnings", []))
        for row in ranked:
            source = (row.get("metric_snapshot") or {}).get("source")
            if source:
                sources.add(source)
            winner["content_item"] = merge_non_null(
                winner.get("content_item") or {}, row.get("content_item") or {}
            )
            winner["metric_snapshot"] = merge_non_null(
                winner.get("metric_snapshot") or {}, row.get("metric_snapshot") or {}
            )
            warnings.update(row.get("normalization", {}).get("warnings", []))
        winner.setdefault("normalization", {})["warnings"] = sorted(warnings)
        winner["normalization"]["duplicate_count"] = len(group) - 1
        winner["normalization"]["duplicate_sources"] = sorted(sources)
        winner["metric_snapshot"]["item_id"] = item_id
        output.append(winner)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", "-i", default="-")
    parser.add_argument("--output", "-o", default="-")
    args = parser.parse_args()
    input_stream = sys.stdin if args.input == "-" else Path(args.input).open("r", encoding="utf-8")
    try:
        records = read_jsonl(input_stream)
    finally:
        if input_stream is not sys.stdin:
            input_stream.close()
    result = deduplicate(records)
    output_stream = sys.stdout if args.output == "-" else Path(args.output).open("w", encoding="utf-8", newline="\n")
    try:
        for row in result:
            output_stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    finally:
        if output_stream is not sys.stdout:
            output_stream.close()
    print(json.dumps({"received": len(records), "unique": len(result)}), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

