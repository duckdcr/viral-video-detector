---
name: viral-video-detector
description: Monitor and explain unusually fast-growing energy-storage social content across configured markets using Bright Data-backed public data. Use for trend scans, viral-candidate alerts, candidate explanation, reviewer feedback, and score calibration; not for publishing content or claiming full-web coverage.
metadata:
  short-description: Cross-market energy content radar
---

# Viral Video Detector

Find early, explainable social-content outliers that can become energy-storage topics or scripts. Treat Bright Data as the collection layer and this skill as the evidence, scoring, and routing layer.

## Activation boundary

Run Bright Data collection only when the user explicitly invokes `$viral-video-detector` or explicitly asks to scan, refresh, or collect viral-content data. Explaining saved candidates, reviewing feedback, editing configuration, and testing local fixtures do not authorize a new external collection run. Never create a background schedule unless the user separately requests one.

## Route the request

- **Scan:** discover or ingest candidates, normalize, deduplicate, snapshot, score, and route alerts.
- **Explain:** inspect one candidate's evidence, structure, market fit, and risks.
- **Review:** record a human decision and stable reason codes.
- **Calibrate:** summarize feedback and propose threshold or weight changes. Keep production changes pending human approval.

## Evidence invariants

1. A velocity claim requires at least two valid snapshots with positive elapsed time. Otherwise label the item `potential_candidate`.
2. Compare within a peer cohort: platform, market/language, topic, account-size band, and content-age band.
3. Preserve missing metrics as `null`. Re-normalize available score weights and lower confidence.
4. Keep raw metrics, collection timestamps, source, cohort, and algorithm version beside every score.
5. Mark paid, pinned, duplicated, stale, or event-driven signals explicitly; apply penalties only with evidence.
6. Promote a structure to `reusable_pattern` only after at least three comparable examples support it.
7. Route competitor, certification, subsidy, safety, and return-on-investment claims to human compliance review.
8. Collection permission covers only the authorized data operation. Treat download, retention, redistribution, and publishing as separate permissions.

## Scan

1. Read [market configuration](references/market-config.md) and [energy taxonomy](references/energy-taxonomy.md). Resolve markets, languages, platforms, topics, accounts, and time window. Completion: every query has a market, language, topic, and source route.
2. Read [Bright Data routing](references/brightdata-routing.md). Discover URLs first, then prefer a verified structured pipeline over generic scraping. Completion: each source run records its route, collection time, and gaps.
3. Read [canonical schema](references/canonical-schema.md). Normalize with `scripts/normalize_items.py`, deduplicate with `scripts/deduplicate.py`, and persist with `scripts/upsert_snapshots.py`. Completion: valid rows have stable item IDs and snapshots never replace missing values with zero.
4. Compute features with `scripts/calculate_velocity.py`; score with `scripts/calculate_viral_score.py` using [score model](references/score-model.md). Completion: every assessment is reproducible from saved inputs.
5. Deep-analyze only the highest-signal candidates. Produce hook, evidence, trust, interaction, CTA, replicability, and risk fields from observable material.
6. Merge repeated stories into one trend cluster. Send high-score/high-confidence candidates as immediate alerts; place medium candidates in the dated digest; retain low candidates only for baselines and deduplication.

If all primary sources fail or data is too stale for the configured market, emit a run failure and no new viral alert.

## Explain

Load the candidate, its snapshots, peer cohort, assessment, and source URL. Separate observed facts from interpretation. State why it scored, which data is missing, why it is relevant to the target market, which structure is reusable, and which claims require review.

Read [compliance policy](references/compliance-policy.md) whenever the content includes competitor comparison, certification, subsidy, safety, savings, or payback claims.

## Review

Record one decision: `worth_replicating`, `watch`, `false_positive`, or `non_compliant`. Add stable reason codes, target market, reviewer, timestamp, and whether the candidate entered the topic or script pool. Preserve the original assessment.

## Calibrate

Use reviewed candidates and downstream publishing results. Report performance by market, platform, topic, score band, confidence, and reason code. Propose one versioned change set at a time. Do not overwrite historical assessments or activate new weights without human approval.

## Outputs

Each candidate card must include source URL, market/platform, score, confidence, observed growth evidence, cohort context, reusable structure, market fit, gaps, risks, and next action. Date-stamp digests and list platforms or queries that returned no usable data.
