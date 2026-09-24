from __future__ import annotations

import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path


RUN_DIR = Path(__file__).resolve().parent
SKILL_DIR = RUN_DIR.parents[1]
SCRIPT_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import calculate_velocity  # noqa: E402
import calculate_viral_score  # noqa: E402
import deduplicate  # noqa: E402
import normalize_items  # noqa: E402
import upsert_snapshots  # noqa: E402


CAPTURE_TIMES = (
    "2026-09-16T08:00:00Z",
    "2026-09-16T09:00:00Z",
    "2026-09-16T10:00:00Z",
)
COHORT = "youtube-DE-de-blackout-test-10k_50k-0_24h"


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def make_record(index: int, snapshot_index: int) -> dict:
    external_id = f"synthetic-{index:03d}"
    first_views = 1_500 + index * 210
    first_velocity = 300 + index * 35
    second_velocity = 340 + index * 45
    if index == 19:
        first_views = 8_000
        first_velocity = 4_000
        second_velocity = 32_000

    views = (
        first_views,
        first_views + first_velocity,
        first_views + first_velocity + second_velocity,
    )[snapshot_index]
    likes = int(views * (0.045 + index * 0.0004))
    comments = int(views * (0.004 + index * 0.00008))
    shares = int(views * (0.0025 + index * 0.00012))
    saves = int(views * 0.0015)

    return {
        "platform": "youtube",
        "video_id": external_id,
        "url": f"https://example.invalid/mock/youtube/{external_id}?utm_source=synthetic",
        "channel_id": f"synthetic-channel-{index:03d}",
        "channel_name": f"Synthetic Installer {index:02d}",
        "title": (
            "Stromausfall-Test: Licht bleibt an, Uhr läuft weiter"
            if index == 19
            else f"Heimspeicher Notstrom-Test #{index:02d}"
        ),
        "description": "Synthetic fixture only: grid switch-off and backup handover demonstration.",
        "published_at": "2026-09-16T06:30:00Z",
        "captured_at": CAPTURE_TIMES[snapshot_index],
        "views": views,
        "likes": likes,
        "comments": comments,
        "shares": shares,
        "saves": saves,
        "followers": 12_000 + index * 1_500,
        "topic_tags": ["blackout-test", "battery-backup"],
        "commercial_flag": False,
        "pinned_flag": False,
        "synthetic": True,
    }


def main() -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    db_path = RUN_DIR / "radar.sqlite"
    if db_path.exists():
        db_path.unlink()

    raw_batches: list[list[dict]] = []
    normalized_rows: list[dict] = []
    deduplicated_rows: list[dict] = []

    for snapshot_index, captured_at in enumerate(CAPTURE_TIMES):
        batch = [make_record(index, snapshot_index) for index in range(20)]
        if snapshot_index == 2:
            duplicate = dict(batch[-1])
            duplicate["url"] += "&utm_campaign=duplicate-check"
            batch.append(duplicate)
        raw_batches.append(batch)

        normalized = [
            normalize_items.normalize_record(
                record,
                source="synthetic_fixture",
                market="DE",
                language="de",
                captured_at=captured_at,
                index=index,
            )
            for index, record in enumerate(batch)
        ]
        normalized_rows.extend(normalized)
        deduplicated_rows.extend(deduplicate.deduplicate(normalized))

    write_json(RUN_DIR / "raw-batches.json", raw_batches)
    write_jsonl(RUN_DIR / "normalized.jsonl", normalized_rows)
    write_jsonl(RUN_DIR / "deduplicated.jsonl", deduplicated_rows)

    with closing(sqlite3.connect(db_path)) as connection:
        upsert_snapshots.init_db(connection)
        item_upsert_count, snapshot_count = upsert_snapshots.upsert_envelopes(connection, deduplicated_rows)
        unique_item_count = connection.execute("SELECT COUNT(*) FROM content_items").fetchone()[0]

    velocities = calculate_velocity.calculate_all(calculate_velocity.load_db(str(db_path)))
    write_jsonl(RUN_DIR / "velocities.jsonl", velocities)

    features: list[dict] = []
    for index, velocity in enumerate(velocities):
        feature = dict(velocity)
        feature.update(
            {
                "cohort": COHORT,
                "account_baseline_outlier": round(1.0 + index * 0.08, 2),
                "cross_market_replication": 1 + min(index // 5, 3),
                "paid_or_pinned_penalty": 0,
                "data_freshness_penalty": 0,
            }
        )
        if index == 19:
            feature["account_baseline_outlier"] = 4.8
            feature["cross_market_replication"] = 4
        features.append(feature)

    write_jsonl(RUN_DIR / "score-features.jsonl", features)
    assessments = calculate_viral_score.calculate_all(features)
    write_jsonl(RUN_DIR / "assessments.jsonl", assessments)

    item_by_id = {row["content_item"]["id"]: row["content_item"] for row in deduplicated_rows}
    velocity_by_id = {row["item_id"]: row for row in velocities}
    ranked = sorted(assessments, key=lambda row: row["viral_score"], reverse=True)
    winner = ranked[0]
    winner_item = item_by_id[winner["item_id"]]
    winner_velocity = velocity_by_id[winner["item_id"]]

    source_run = {
        "run_id": "synthetic-2026-09-16",
        "source": "synthetic_fixture",
        "route": "local_fixture",
        "platform": "youtube",
        "market": "DE",
        "language": "de",
        "topic": "blackout-test",
        "query": "synthetic fixture; no external query",
        "window": "2026-09-16T08:00:00Z/2026-09-16T10:00:00Z",
        "started_at": CAPTURE_TIMES[0],
        "finished_at": CAPTURE_TIMES[-1],
        "records_received": sum(len(batch) for batch in raw_batches),
        "records_valid": len(deduplicated_rows),
        "unique_items": unique_item_count,
        "item_upsert_operations": item_upsert_count,
        "snapshots_persisted": snapshot_count,
        "status": "success",
        "error_code": None,
        "external_calls": 0,
        "config_version": "0.1",
        "algorithm_version": "0.1",
        "disclaimer": "All records and metrics are synthetic and must not be treated as market evidence.",
    }
    write_json(RUN_DIR / "source-run.json", source_run)

    report = f"""# Viral Video Detector — 虚拟数据演练

> **数据声明：** 本报告完全由 `synthetic_fixture` 生成，外部调用为 0；它只验证流程，不代表真实市场表现。

## 运行结果

- 市场 / 语言：DE / de
- 平台 / 主题：YouTube / `blackout-test`
- 原始记录：{source_run['records_received']}（含 1 条重复记录）
- 唯一内容：{source_run['unique_items']}
- 有效快照：{source_run['snapshots_persisted']}
- 评分模型：0.1
- 最高告警等级：`{winner['alert_tier']}`

## 候选卡片

- 虚拟来源 URL：{winner_item['canonical_url']}
- 市场 / 平台：DE / YouTube
- 爆款分：{winner['viral_score']}
- 置信度：`{winner['confidence']}`
- 增长证据：最近 1 小时播放增速 {winner_velocity['view_velocity']:.0f}/小时；点赞增速 {winner_velocity['like_velocity']:.0f}/小时；评论增速 {winner_velocity['comment_velocity']:.0f}/小时；加速度 {winner_velocity['acceleration']:.2f}×
- 队列：`{winner['cohort']}`，样本数 {winner['cohort_count']}
- 可复用结构假设：3 秒内拉下总闸 → 灯不闪 / 时钟不重置 → 展示电池接管证据 → 邀请观众提出下一项压力测试
- 市场匹配假设：德国用户对备电连续性与安装质量有潜在兴趣
- 数据缺口：无真实来源、无评论语义、无账号历史基线、无跨市场真实复现证据
- 风险：涉及停电、备电和安全演示，正式改编前必须进行人工合规与技术审核
- 模式状态：`single_example`（虚拟同构样本不能作为真实 `reusable_pattern` 证据）
- 下一步：账户激活后用相同配置采集真实公开数据，再确认是否进入选题池

## 结论

虚拟数据已跑通归一化、批内去重、SQLite 快照持久化、增速 / 加速度计算、同队列百分位评分和告警分层。当前 `immediate` 结果只是测试断言，不是市场结论。
"""
    (RUN_DIR / "report.md").write_text(report, encoding="utf-8")

    print(json.dumps({
        "status": "success",
        "external_calls": 0,
        "unique_items": unique_item_count,
        "snapshots": snapshot_count,
        "top_score": winner["viral_score"],
        "top_confidence": winner["confidence"],
        "top_alert_tier": winner["alert_tier"],
        "report": str(RUN_DIR / "report.md"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
