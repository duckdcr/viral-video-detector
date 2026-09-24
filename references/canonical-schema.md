# Canonical schema

Use these shapes between collection, deterministic scripts, storage, and Agent analysis. Fields not supplied by a source are null, never inferred as zero.

## Normalized envelope

`normalize_items.py` emits one envelope per source record:

```json
{
  "content_item": {},
  "metric_snapshot": {},
  "normalization": {
    "schema_version": "0.1",
    "warnings": [],
    "source_record_index": 0
  }
}
```

## content_item

Required: `id`, `platform`, `canonical_url`, `published_at` or an explicit warning, and `source`.

```json
{
  "id": "sha256:...",
  "platform": "youtube|instagram|tiktok|reddit|x|facebook|web|unknown",
  "external_id": "...",
  "canonical_url": "https://...",
  "author_id": "...",
  "author_name": "...",
  "market": "DE",
  "language": "de",
  "published_at": "2026-09-16T08:00:00Z",
  "title": "...",
  "caption": "...",
  "duration_seconds": 42,
  "topic_tags": ["blackout-test"],
  "commercial_flag": null,
  "pinned_flag": null,
  "source": "brightdata"
}
```

## metric_snapshot

```json
{
  "item_id": "sha256:...",
  "captured_at": "2026-09-16T10:00:00Z",
  "views": 110000,
  "likes": 6200,
  "comments": 480,
  "shares": null,
  "saves": null,
  "followers": 35000,
  "source": "brightdata",
  "freshness_seconds": null,
  "field_confidence": "high|medium|low"
}
```

Counts are non-negative integers or null. `captured_at` describes this observation; `published_at` describes the content.

## velocity_feature

```json
{
  "item_id": "sha256:...",
  "snapshot_count": 3,
  "latest_captured_at": "...",
  "window_hours": 2.0,
  "view_velocity": 32500.0,
  "like_velocity": 820.0,
  "comment_velocity": 75.0,
  "share_velocity": null,
  "save_velocity": null,
  "acceleration": 1.7,
  "status": "velocity_ready|potential_candidate|invalid"
}
```

## score_feature

The score script accepts velocity fields plus:

```json
{
  "item_id": "...",
  "cohort": "youtube-DE-blackout-test-10k_50k-0_24h",
  "snapshot_count": 3,
  "account_baseline_outlier": 2.8,
  "cross_market_replication": 3,
  "paid_or_pinned_penalty": 0,
  "data_freshness_penalty": 0,
  "field_confidence": "high"
}
```

## viral_assessment

```json
{
  "item_id": "...",
  "algorithm_version": "0.1",
  "cohort": "...",
  "viral_score": 82.0,
  "confidence": "high",
  "available_weight_ratio": 1.0,
  "percentiles": {},
  "penalties": {},
  "calculated_at": "..."
}
```

## review_feedback

Allowed decisions: `worth_replicating`, `watch`, `false_positive`, `non_compliant`.

Recommended reason codes: `strong_hook`, `strong_evidence`, `market_relevant`, `cross_market_repeat`, `pure_entertainment`, `paid_signal`, `stale_data`, `wrong_market`, `weak_evidence`, `compliance_risk`, `duplicate`, `other`.

