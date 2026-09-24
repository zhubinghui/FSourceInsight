# Company AI Refresh jobs (M3.4c)

Existing company analyses are refreshed through durable jobs in `company_refresh_job`, consumed by
`app.llm.refresh_tasks.refresh` on the `llm` queue. This replaces the old best-effort paths.

## What triggers a refresh

- **Manual**: an admin presses *AI Refresh* on a company page.
- **Article**: after `process_article_llm` applies an article, each linked company that already has an
  analysis gets a refresh request. The article task never calls the model for company analysis.

A company has at most one queued or running job. Further requests while one is active are absorbed:
the page says the refresh is already queued, and a burst of articles costs one refresh at a time.

## Execution

1. **Claim** pins the company's `analysis_generation` and the five latest headlines.
2. The homepage excerpt is fetched through SafeFetcher outside any transaction.
3. **Prepare** stores the hash of the exact prompt. Each paid attempt and each cache hit must match
   the current claim, the prompt hash and the pinned generation.
4. **Finish** applies the merge only if the generation is unchanged. A manual edit, another refresh or
   a change to company fields during the run closes the job as `stale` and writes nothing.

Model-supplied websites are stored only if they pass the discovery website check, because the stored
website is the next refresh's fetch target.

## Limits and failure handling

| Limit | Value |
|---|---|
| Queue lifetime | 24 hours |
| Execution after claim | 180 seconds, checked cooperatively |
| Provider attempts per job | 3, distinct configs, stopped by any unknown cost |
| Minimum redispatch interval | 120 seconds |
| Jobs per recovery scan | 50, every 60 seconds |

A failure closes the job as `blocked`. There is no automatic Celery retry that pays again; an admin
can request a new refresh. Recovery redispatches due queued jobs and blocks running jobs past their
deadline without paying again.

The company page shows admins the latest job, its trigger and its state. Reasons are fixed codes,
never provider or exception text.

## Deployment notes

- Migration `d3e7a1c95b28` adds one table and the nullable `llm_reservation.company_refresh_id`. It
  creates no jobs for existing companies.
- The retired task `app.llm.tasks.refresh_company_analysis` stays registered only to drain messages
  from the previous release. It logs and returns without paying. Drain the `llm` queue before the
  switch, then ask admins to re-request any refresh they were waiting for.
- Mixed old and new paid workers are not supported: old workers still pay inline after articles.
