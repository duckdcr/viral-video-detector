from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import calculate_velocity  # noqa: E402
import calculate_viral_score  # noqa: E402
import deduplicate  # noqa: E402
import normalize_items  # noqa: E402
import upsert_snapshots  # noqa: E402


class NormalizeTests(unittest.TestCase):
    def test_normalizes_aliases_counts_and_tracking_url(self) -> None:
        result = normalize_items.normalize_record(
            {
                "url": "https://www.tiktok.com/@installer/video/123?utm_source=x&lang=en",
                "id": "123",
                "date_posted": "2026-09-16T08:00:00Z",
                "description": "Blackout test",
                "play_count": "1.2M",
                "digg_count": "24.5K",
                "comment_count": "480",
                "share_count": None,
                "followers_count": "35K",
            },
            market="DE",
            language="de",
            captured_at="2026-09-16T10:00:00Z",
        )
        item = result["content_item"]
        snapshot = result["metric_snapshot"]
        self.assertEqual(item["platform"], "tiktok")
        self.assertEqual(item["canonical_url"], "https://www.tiktok.com/@installer/video/123?lang=en")
        self.assertEqual(item["market"], "DE")
        self.assertEqual(snapshot["views"], 1_200_000)
        self.assertEqual(snapshot["likes"], 24_500)
        self.assertIsNone(snapshot["shares"])
        self.assertEqual(snapshot["field_confidence"], "high")

    def test_rejects_record_without_url_or_external_id(self) -> None:
        with self.assertRaises(ValueError):
            normalize_items.normalize_record({"title": "orphan"})


class DeduplicateTests(unittest.TestCase):
    def test_keeps_most_complete_snapshot_and_merges_content(self) -> None:
        first = normalize_items.normalize_record(
            {
                "url": "https://youtube.com/watch?v=abc",
                "video_id": "abc",
                "published_at": "2026-09-16T08:00:00Z",
                "views": 100,
            },
            source="source-a",
            captured_at="2026-09-16T10:00:00Z",
        )
        second = normalize_items.normalize_record(
            {
                "url": "https://youtube.com/watch?v=abc&utm_source=test",
                "video_id": "abc",
                "published_at": "2026-09-16T08:00:00Z",
                "title": "Blackout test",
                "views": 110,
                "likes": 12,
                "comments": 3,
            },
            source="source-b",
            captured_at="2026-09-16T10:02:00Z",
        )
        result = deduplicate.deduplicate([first, second])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["metric_snapshot"]["views"], 110)
        self.assertEqual(result[0]["content_item"]["title"], "Blackout test")
        self.assertEqual(result[0]["normalization"]["duplicate_count"], 1)


class PersistenceTests(unittest.TestCase):
    def test_upsert_preserves_existing_metric_when_new_value_is_missing(self) -> None:
        envelope = normalize_items.normalize_record(
            {
                "url": "https://youtube.com/watch?v=abc",
                "video_id": "abc",
                "published_at": "2026-09-16T08:00:00Z",
                "views": 100,
                "likes": 10,
            },
            captured_at="2026-09-16T10:00:00Z",
        )
        missing = normalize_items.normalize_record(
            {
                "url": "https://youtube.com/watch?v=abc",
                "video_id": "abc",
                "published_at": "2026-09-16T08:00:00Z",
                "likes": 12,
            },
            captured_at="2026-09-16T10:00:00Z",
        )
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "radar.db"
            with closing(sqlite3.connect(db_path)) as connection:
                upsert_snapshots.init_db(connection)
                upsert_snapshots.upsert_envelopes(connection, [envelope])
                upsert_snapshots.upsert_envelopes(connection, [missing])
                row = connection.execute(
                    "SELECT views, likes FROM metric_snapshots"
                ).fetchone()
            self.assertEqual(row, (100, 12))


class VelocityTests(unittest.TestCase):
    def test_calculates_velocity_and_acceleration_from_three_snapshots(self) -> None:
        snapshots = [
            {"item_id": "a", "captured_at": "2026-09-16T08:00:00Z", "views": 100, "likes": 10},
            {"item_id": "a", "captured_at": "2026-09-16T09:00:00Z", "views": 200, "likes": 20},
            {
                "item_id": "a",
                "captured_at": "2026-09-16T10:00:00Z",
                "views": 400,
                "likes": 50,
                "field_confidence": "high",
            },
        ]
        result = calculate_velocity.calculate_item_velocity("a", snapshots)
        self.assertEqual(result["status"], "velocity_ready")
        self.assertEqual(result["view_velocity"], 200)
        self.assertEqual(result["like_velocity"], 30)
        self.assertEqual(result["acceleration"], 2)

    def test_two_snapshots_have_velocity_but_no_acceleration(self) -> None:
        snapshots = [
            {"item_id": "a", "captured_at": "2026-09-16T08:00:00Z", "views": 100},
            {"item_id": "a", "captured_at": "2026-09-16T10:00:00Z", "views": 300},
        ]
        result = calculate_velocity.calculate_item_velocity("a", snapshots)
        self.assertEqual(result["view_velocity"], 100)
        self.assertIsNone(result["acceleration"])

    def test_counter_decrease_becomes_missing_not_negative(self) -> None:
        snapshots = [
            {"item_id": "a", "captured_at": "2026-09-16T08:00:00Z", "views": 300},
            {"item_id": "a", "captured_at": "2026-09-16T10:00:00Z", "views": 200},
        ]
        result = calculate_velocity.calculate_item_velocity("a", snapshots)
        self.assertIsNone(result["view_velocity"])
        self.assertIn("counter_decreased:views", result["warnings"])


class ScoreTests(unittest.TestCase):
    def test_missing_share_renormalizes_weight_and_caps_confidence(self) -> None:
        records = []
        for index in range(20):
            records.append(
                {
                    "item_id": f"item-{index}",
                    "cohort": "youtube-DE-blackout-10k_50k-0_24h",
                    "snapshot_count": 3,
                    "view_velocity": 100 + index,
                    "share_velocity": None,
                    "comment_velocity": 10 + index,
                    "like_velocity": 20 + index,
                    "acceleration": 1 + index / 10,
                    "account_baseline_outlier": 1 + index / 20,
                    "cross_market_replication": 1 + index,
                    "field_confidence": "high",
                }
            )
        result = calculate_viral_score.calculate_all(records)[-1]
        self.assertAlmostEqual(result["available_weight_ratio"], 0.8)
        self.assertEqual(result["confidence"], "medium")
        self.assertEqual(result["alert_tier"], "digest")
        self.assertGreater(result["viral_score"], 95)

    def test_penalties_reduce_score(self) -> None:
        records = [
            {
                "item_id": "a",
                "cohort": "c",
                "snapshot_count": 3,
                "view_velocity": 10,
                "comment_velocity": 10,
                "like_velocity": 10,
                "acceleration": 2,
                "account_baseline_outlier": 2,
                "cross_market_replication": 2,
                "field_confidence": "high",
                "paid_or_pinned_penalty": 10,
                "data_freshness_penalty": 5,
            }
        ]
        result = calculate_viral_score.calculate_all(records)[0]
        self.assertEqual(result["viral_score"], 35.0)


if __name__ == "__main__":
    unittest.main()
