# Viral score model

Use this reference for feature computation, cohort selection, confidence, penalties, and calibration.

## Algorithm 0.1

```text
ViralScore =
  0.30 × ViewVelocityPercentile
+ 0.20 × ShareVelocityPercentile
+ 0.15 × CommentVelocityPercentile
+ 0.10 × LikeVelocityPercentile
+ 0.10 × AccelerationPercentile
+ 0.10 × AccountBaselineOutlierPercentile
+ 0.05 × CrossMarketReplicationPercentile
- PaidOrPinnedPenalty
- DataFreshnessPenalty
```

Percentiles are 0–1. The final score is 0–100. Penalties are score points. When a feature is unavailable, exclude its weight and divide by the remaining weight sum.

## Cohort

Use the narrowest cohort with sufficient samples, then back off in this order:

1. platform + market + language + topic + account band + content-age band;
2. platform + market + topic + account band + content-age band;
3. platform + language + topic + account band + content-age band;
4. platform + topic + account band + content-age band.

Record the final cohort and sample count. A cohort under 20 items is exploratory and caps confidence at medium.

Suggested account bands: `<10k`, `10k–50k`, `50k–250k`, `250k–1m`, `>1m`.  
Suggested age bands: `0–6h`, `6–24h`, `1–3d`, `3–7d`, `7–30d`.

## Feature rules

- Velocity is non-negative metric change divided by positive elapsed hours.
- A decreasing public counter yields null for that metric and a warning; it is not negative engagement.
- Acceleration requires three snapshots and compares the latest window with the previous window. When the previous velocity is zero and current velocity is positive, cap the raw ratio at the configured maximum before percentile ranking.
- Account baseline outlier compares the item to that account's recent content at equivalent content age.
- Cross-market replication counts distinct markets/accounts showing the same topic-structure cluster.

## Penalties

- `paid_or_pinned_penalty`: 0–20 points, applied only with a platform flag or documented evidence.
- `data_freshness_penalty`: 0–15 points, based on market-configured freshness thresholds.
- Never invent a penalty to make a score look plausible.

## Confidence

- **High:** at least three snapshots, at least 85% of base weight available, high field confidence, cohort ≥20.
- **Medium:** at least two snapshots and at least 65% of base weight available.
- **Low:** otherwise. Low-confidence results may enter a watch list but not a high-priority alert.

## Calibration

Keep every algorithm version immutable. Evaluate candidate precision, selection rate, script conversion, publishing performance, and business outcome by market and platform. Propose weight changes from reviewed samples; activate only after human approval and backtesting.

