#!/usr/bin/env python3
"""Normalize Bright Data-style social records into the radar envelope schema."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, TextIO
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "ttclid",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def nested_get(record: dict[str, Any], path: str) -> Any:
    value: Any = record
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def first(record: dict[str, Any], *paths: str) -> Any:
    for path in paths:
        value = nested_get(record, path)
        if value not in (None, ""):
            return value
    return None


def parse_count(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return max(0, int(value))
    text = str(value).strip().lower().replace(",", "").replace(" ", "")
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)([kmb]|万|亿)?", text)
    if not match:
        return None
    number = float(match.group(1))
    multiplier = {
        None: 1,
        "k": 1_000,
        "m": 1_000_000,
        "b": 1_000_000_000,
        "万": 10_000,
        "亿": 100_000_000,
    }[match.group(2)]
    return max(0, int(number * multiplier))


def parse_duration(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return max(0, int(value))
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    parts = text.split(":")
    if all(part.isdigit() for part in parts) and 2 <= len(parts) <= 3:
        seconds = 0
        for part in parts:
            seconds = seconds * 60 + int(part)
        return seconds
    return None


def parse_timestamp(value: Any) -> str | None:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)) or str(value).strip().isdigit():
            numeric = float(value)
            if numeric > 10_000_000_000:
                numeric /= 1000
            return datetime.fromtimestamp(numeric, tz=timezone.utc).isoformat().replace(
                "+00:00", "Z"
            )
        text = str(value).strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except (ValueError, TypeError, OSError):
        return None


def canonicalize_url(value: Any) -> str | None:
    if value is None or value == "":
        return None
    text = str(value).strip()
    if text.startswith("urn:"):
        return text
    if not re.match(r"^https?://", text, flags=re.IGNORECASE):
        return None
    parts = urlsplit(text)
    query = [
        (key, val)
        for key, val in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_QUERY_KEYS
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, urlencode(sorted(query)), "")
    )


def detect_platform(url: str | None, explicit: Any = None) -> str:
    if explicit:
        normalized = str(explicit).strip().lower()
        aliases = {"twitter": "x", "yt": "youtube", "ig": "instagram"}
        return aliases.get(normalized, normalized)
    host = urlsplit(url).netloc.lower() if url and url.startswith("http") else ""
    mappings = {
        "youtube.com": "youtube",
        "youtu.be": "youtube",
        "instagram.com": "instagram",
        "tiktok.com": "tiktok",
        "reddit.com": "reddit",
        "x.com": "x",
        "twitter.com": "x",
        "facebook.com": "facebook",
    }
    for domain, platform in mappings.items():
        if host == domain or host.endswith(f".{domain}"):
            return platform
    return "web" if host else "unknown"


def make_item_id(platform: str, external_id: Any, url: str) -> str:
    identity = f"{platform}:{external_id}" if external_id else f"{platform}:{url}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def normalize_record(
    record: dict[str, Any],
    *,
    source: str = "brightdata",
    default_platform: str | None = None,
    market: str | None = None,
    language: str | None = None,
    captured_at: str | None = None,
    index: int = 0,
) -> dict[str, Any]:
    warnings: list[str] = []
    raw_url = first(record, "url", "link", "video_url", "post_url", "web_url")
    url = canonicalize_url(raw_url)
    external_id = first(
        record,
        "external_id",
        "video_id",
        "post_id",
        "aweme_id",
        "shortcode",
        "id",
    )
    platform = detect_platform(url, first(record, "platform") or default_platform)
    if not url and external_id:
        url = f"urn:{platform}:{external_id}"
        warnings.append("missing_source_url")
    if not url:
        raise ValueError("record has neither a valid URL nor an external ID")

    published_at = parse_timestamp(
        first(
            record,
            "published_at",
            "date_posted",
            "upload_date",
            "created_at",
            "create_time",
            "timestamp",
        )
    )
    if not published_at:
        warnings.append("missing_or_invalid_published_at")

    captured = parse_timestamp(
        captured_at
        or first(record, "captured_at", "collected_at", "scraped_at", "fetched_at")
    ) or utc_now()

    metrics = {
        "views": parse_count(
            first(record, "views", "view_count", "play_count", "video_views", "stats.views")
        ),
        "likes": parse_count(
            first(record, "likes", "like_count", "digg_count", "stats.likes")
        ),
        "comments": parse_count(
            first(record, "comments", "comment_count", "comments_count", "stats.comments")
        ),
        "shares": parse_count(
            first(record, "shares", "share_count", "repost_count", "stats.shares")
        ),
        "saves": parse_count(
            first(record, "saves", "save_count", "collect_count", "bookmark_count")
        ),
        "followers": parse_count(
            first(
                record,
                "followers",
                "followers_count",
                "follower_count",
                "author.followers",
            )
        ),
    }
    available_metrics = sum(value is not None for value in metrics.values())
    field_confidence = (
        "high"
        if external_id and published_at and available_metrics >= 2
        else "medium"
        if available_metrics >= 1
        else "low"
    )
    if available_metrics == 0:
        warnings.append("missing_engagement_metrics")

    item_id = make_item_id(platform, external_id, url)
    topic_tags = first(record, "topic_tags", "topics", "hashtags") or []
    if isinstance(topic_tags, str):
        topic_tags = [tag.strip().lstrip("#") for tag in topic_tags.split(",") if tag.strip()]
    elif not isinstance(topic_tags, list):
        topic_tags = []

    content_item = {
        "id": item_id,
        "platform": platform,
        "external_id": str(external_id) if external_id is not None else None,
        "canonical_url": url,
        "author_id": first(record, "author_id", "channel_id", "user_id", "owner_id", "author.id"),
        "author_name": first(
            record, "author_name", "channel_name", "username", "owner_name", "author.name"
        ),
        "market": first(record, "market", "country_code") or market,
        "language": first(record, "language", "language_code") or language,
        "published_at": published_at,
        "title": first(record, "title", "video_title", "name"),
        "caption": first(record, "caption", "description", "text", "content"),
        "duration_seconds": parse_duration(
            first(record, "duration_seconds", "duration", "video_duration")
        ),
        "topic_tags": topic_tags,
        "commercial_flag": first(record, "commercial_flag", "is_ad", "is_sponsored"),
        "pinned_flag": first(record, "pinned_flag", "is_pinned"),
        "source": source,
    }
    snapshot = {
        "item_id": item_id,
        "captured_at": captured,
        **metrics,
        "source": source,
        "freshness_seconds": parse_count(first(record, "freshness_seconds")),
        "field_confidence": field_confidence,
    }
    return {
        "content_item": content_item,
        "metric_snapshot": snapshot,
        "normalization": {
            "schema_version": "0.1",
            "warnings": warnings,
            "source_record_index": index,
        },
    }


def load_records(stream: TextIO) -> list[dict[str, Any]]:
    text = stream.read()
    if not text.strip():
        return []
    try:
        payload = json.loads(text)
        if isinstance(payload, list):
            records = payload
        elif isinstance(payload, dict):
            for key in ("data", "results", "items", "records"):
                if isinstance(payload.get(key), list):
                    records = payload[key]
                    break
            else:
                records = [payload]
        else:
            raise ValueError("top-level JSON must be an object or array")
    except json.JSONDecodeError:
        records = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not all(isinstance(item, dict) for item in records):
        raise ValueError("every input record must be a JSON object")
    return records


def open_input(path: str) -> TextIO:
    return sys.stdin if path == "-" else Path(path).open("r", encoding="utf-8")


def open_output(path: str) -> TextIO:
    return sys.stdout if path == "-" else Path(path).open("w", encoding="utf-8", newline="\n")


def emit_jsonl(records: Iterable[dict[str, Any]], stream: TextIO) -> None:
    for record in records:
        stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", "-i", default="-", help="JSON/JSONL input path; default stdin")
    parser.add_argument("--output", "-o", default="-", help="JSONL output path; default stdout")
    parser.add_argument("--source", default="brightdata")
    parser.add_argument("--platform")
    parser.add_argument("--market")
    parser.add_argument("--language")
    parser.add_argument("--captured-at")
    parser.add_argument("--keep-invalid", action="store_true")
    args = parser.parse_args()

    with open_input(args.input) as input_stream:
        raw_records = load_records(input_stream)

    normalized: list[dict[str, Any]] = []
    rejected = 0
    for index, record in enumerate(raw_records):
        try:
            normalized.append(
                normalize_record(
                    record,
                    source=args.source,
                    default_platform=args.platform,
                    market=args.market,
                    language=args.language,
                    captured_at=args.captured_at,
                    index=index,
                )
            )
        except ValueError as exc:
            rejected += 1
            if args.keep_invalid:
                normalized.append(
                    {
                        "content_item": None,
                        "metric_snapshot": None,
                        "normalization": {
                            "schema_version": "0.1",
                            "warnings": [f"invalid_record:{exc}"],
                            "source_record_index": index,
                        },
                    }
                )

    with open_output(args.output) as output_stream:
        emit_jsonl(normalized, output_stream)
    print(
        json.dumps({"received": len(raw_records), "normalized": len(normalized), "rejected": rejected}),
        file=sys.stderr,
    )
    return 0 if normalized or not raw_records else 2


if __name__ == "__main__":
    raise SystemExit(main())

