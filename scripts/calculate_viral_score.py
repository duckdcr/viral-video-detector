#!/usr/bin/env python3
"""Calculate cohort-relative viral scores from feature JSONL."""

from __future__ import annotations

import argparse
import bisect
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO


ALGORITHM_VERSION = "0.1"
WEIGHTS = {
    "view_velocity": 0.30,
    "share_velocity": 0.20,
    "comment_velocity": 0.15,
    "like_velocity": 0.10,
    "acceleration": 0.10,
    "account_baseline_outlier": 0.10,
    "cross_market_replication": 0.05,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def numeric(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed >= 0 else None


def percentile(value: float, population: list[float]) -> float:
    if len(population) <= 1:
        return 0.5
    ordered = sorted(population)
    left = bisect.bisect_left(ordered, value)
    right = bisect.bisect_right(ordered, value)
    midrank = (left + right - 1) / 2
    return midrank / (len(ordered) - 1)


def build_populations(records: list[dict[str, Any]]) -> dict[str, dict[str, list[float]]]:
    populations: dict[str, dict[str, list[float]]] = {}
    for record in records:
        cohort = str(record.get("cohort") or "unassigned")
        bucket = populations.setdefault(cohort, {feature: [] for feature in WEIGHTS})
        for feature in WEIGHTS:
            value = numeric(record.get(feature))
            if value is not None:
                bucket[feature].append(value)
    return populations


def calculate_score(
    record: dict[str, Any],
    populations: dict[str, dict[str, list[float]]],
    *,
    immediate_threshold: float = 80,
    digest_threshold: float = 60,
) -> dict[str, Any]:
    cohort = str(record.get("cohort") or "unassigned")
    cohort_values = populations.get(cohort, {})
    percentiles: dict[str, float | None] = {}
    weighted_sum = 0.0
    available_weight = 0.0
    for feature, weight in WEIGHTS.items():
        value = numeric(record.get(feature))
        population = cohort_values.get(feature, [])
        if value is None or not population:
            percentiles[feature] = None
            continue
        rank = percentile(value, population)
        percentiles[feature] = round(rank, 6)
        weighted_sum += rank * weight
        available_weight += weight

    paid_penalty = min(20.0, numeric(record.get("paid_or_pinned_penalty")) or 0.0)
    freshness_penalty = min(15.0, numeric(record.get("data_freshness_penalty")) or 0.0)
    base_score = (weighted_sum / available_weight * 100) if available_weight else 0.0
    final_score = max(0.0, min(100.0, base_score - paid_penalty - freshness_penalty))

    snapshot_count = int(numeric(record.get("snapshot_count")) or 0)
    field_confidence = str(record.get("field_confidence") or "low").lower()
    cohort_count = max((len(values) for values in cohort_values.values()), default=0)
    available_ratio = available_weight / sum(WEIGHTS.values())
    if (
        snapshot_count >= 3
        and available_ratio >= 0.85
        and field_confidence == "high"
        and cohort_count >= 20
    ):
        confidence = "high"
    elif snapshot_count >= 2 and available_ratio >= 0.65 and field_confidence in {"high", "medium"}:
        confidence = "medium"
    else:
        confidence = "low"

    if snapshot_count < 2:
        status = "potential_candidate"
        alert_tier = "watch"
    else:
        status = "scored"
        if final_score >= immediate_threshold and confidence == "high":
            alert_tier = "immediate"
        elif final_score >= digest_threshold and confidence != "low":
            alert_tier = "digest"
        else:
            alert_tier = "watch"

    return {
        "item_id": record.get("item_id"),
        "algorithm_version": ALGORITHM_VERSION,
        "cohort": cohort,
        "cohort_count": cohort_count,
        "viral_score": round(final_score, 2),
        "confidence": confidence,
        "status": status,
        "alert_tier": alert_tier,
        "available_weight_ratio": round(available_ratio, 4),
        "percentiles": percentiles,
        "penalties": {
            "paid_or_pinned": paid_penalty,
            "data_freshness": freshness_penalty,
        },
        "calculated_at": utc_now(),
    }


def calculate_all(
    records: list[dict[str, Any]], immediate_threshold: float = 80, digest_threshold: float = 60
) -> list[dict[str, Any]]:
    populations = build_populations(records)
    return [
        calculate_score(
            record,
            populations,
            immediate_threshold=immediate_threshold,
            digest_threshold=digest_threshold,
        )
        for record in records
    ]


def load_jsonl(stream: TextIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", "-i", default="-")
    parser.add_argument("--output", "-o", default="-")
    parser.add_argument("--immediate-threshold", type=float, default=80)
    parser.add_argument("--digest-threshold", type=float, default=60)
    args = parser.parse_args()
    input_stream = sys.stdin if args.input == "-" else Path(args.input).open("r", encoding="utf-8")
    try:
        records = load_jsonl(input_stream)
    finally:
        if input_stream is not sys.stdin:
            input_stream.close()
    results = calculate_all(records, args.immediate_threshold, args.digest_threshold)
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

