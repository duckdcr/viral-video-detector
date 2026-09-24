# Bright Data routing

Use this reference for collection, route selection, setup checks, and source failures.

## Setup gate

Use an already configured Bright Data MCP server or authenticated `bdata` CLI. Never place tokens in prompts, source files, logs, or output datasets.

If neither is available, accept a user-supplied Bright Data JSON/JSONL export and run the local processing pipeline. Label that run `offline_import`; do not claim live monitoring.

## Discovery and collection

1. Discover candidate URLs with Bright Data search or Discover using localized queries from `market-config.md` and `energy-taxonomy.md`.
2. For a supported social platform, prefer a structured data pipeline over generic scraping.
3. Confirm available pipeline names at runtime. Bright Data changes names and supported inputs; `bdata pipelines list` or MCP tool discovery is the source of truth.
4. Use generic scrape only when no structured pipeline supports the target URL.
5. Use browser automation only when the authorized page genuinely requires interaction. Treat it as a fragile fallback, not the monitoring backbone.

Official Bright Data skills currently describe structured routes for Instagram posts/reels/comments, TikTok posts/comments/profiles, YouTube videos/comments/profiles, Reddit posts, X posts, and Facebook posts. Availability and fields still require runtime verification.

## Query families

Create bounded queries across these families:

- category and product terms;
- local demand events such as outages, weather, tariffs, and subsidies;
- content forms such as installation, blackout test, bill comparison, teardown, review, and payback explainer;
- approved competitors and monitored accounts;
- URLs from a rising trend cluster that need metric refresh.

Every query record must contain `market`, `language`, `platform`, `topic`, `window`, `route`, and `requested_at`.

## Source-run contract

Record:

```json
{
  "run_id": "...",
  "source": "brightdata",
  "route": "pipeline|search|discover|scrape|offline_import",
  "platform": "youtube",
  "market": "DE",
  "query": "...",
  "started_at": "...",
  "finished_at": "...",
  "records_received": 0,
  "records_valid": 0,
  "status": "success|partial|failed",
  "error_code": null
}
```

## Failure policy

- A record-level error is partial failure; retain valid records and report the rejected count.
- A route failure preserves historical snapshots and tries an authorized fallback.
- Missing engagement fields remain null and lower confidence.
- A stale result receives a freshness penalty.
- When every primary route fails, end the run without new alerts.

## Cost control

- Discover URLs once; refresh only retained candidates.
- Increase refresh frequency only for high-potential or accelerating items.
- Run comment collection and deep content analysis only for Top N candidates.
- Report calls, records, bytes when available, and estimated cost per accepted candidate.

## Primary sources

- Bright Data skills: https://github.com/brightdata/skills
- Bright Data MCP: https://github.com/brightdata/brightdata-mcp
- MCP overview: https://docs.brightdata.com/ai/mcp-server/overview

