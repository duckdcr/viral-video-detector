# Market configuration

Use a versioned config outside `SKILL.md`. The initial markets below are hypotheses for MVP validation; market owners must approve localized terms, competitors, thresholds, and claims.

## Config shape

```yaml
version: "0.1"
markets:
  DE:
    languages: ["de", "en"]
    timezone: "Europe/Berlin"
    platforms: ["youtube", "instagram", "tiktok"]
    topics: ["blackout-test", "bill-before-after", "installation-record"]
    query_terms: []
    monitored_accounts: []
    approved_competitors: []
    freshness:
      high_minutes: 120
      stale_minutes: 720
    alert_thresholds:
      immediate_score: 80
      digest_score: 60
  GB: {}
  AU: {}
```

## Initial market hypotheses

### Germany

- Need angles: electricity prices, self-consumption, dynamic tariffs, backup resilience, installation quality.
- Languages: German first; English secondary for global creators.
- Compliance review: savings, subsidy eligibility, grid-service claims, certification.

### United Kingdom

- Need angles: time-of-use tariffs, solar self-consumption, outage resilience, installer guidance.
- Languages: English.
- Compliance review: tariff assumptions, payback estimates, comparative claims.

### Australia

- Need angles: high solar penetration, export limits, heat, remote resilience, electricity prices.
- Languages: English; add local variants only with market review.
- Compliance review: rebates by state, heat and safety claims, installer requirements.

## Query construction

Combine one term from each applicable dimension:

```text
market need/event + product/category + content form + platform/site constraint
```

Keep brand monitoring and category discovery separate. Category discovery finds high-performing content that may contain no brand name.

## Change control

Record config version on every source run. Market owners approve changes to competitors, subsidies, certifications, safety terminology, and high-priority alert thresholds.

