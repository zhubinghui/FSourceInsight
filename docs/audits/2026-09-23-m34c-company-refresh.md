# M3.4c company refresh jobs (local only, not deployed)

Branch `m3-company-refresh` from master `c5d0b0a`. Production was `a93beb8` / schema `c7f21a9d680e` and was not
touched. No SSH, real crawl, paid model call, email, commit or deployment in this slice.

## Defects in the previous paths

1. *AI Refresh* queued a message on every POST. Double clicks and the task's own Celery retries paid again, up to
   two retries of three provider attempts each.
2. The task read the company, called the model for up to about three minutes, then merged onto its stale copy.
   A manual edit or a concurrent refresh in that window was silently overwritten.
3. `process_article_llm` called the model inline for every linked company with an analysis. A batch of articles
   about one company paid for one refresh per article and blocked the llm worker meanwhile.

## Change

Both triggers now create a `company_refresh_job`. The operational contract is in `docs/ops/company-refresh.md`.
Migration `d3e7a1c95b28` adds one table and `llm_reservation.company_refresh_id`. It is expand-only and creates
no jobs. The generation is pinned at claim rather than at creation: an edit made while the job is queued is read
by the refresh, and only a change after the claim discards the result. Model-supplied websites now pass the
discovery website check before they become the next fetch target.

## Evidence

Red first, through admin HTTP and the public task methods with only SDK, broker, network and time replaced.
Before the implementation, 7 of the 9 new behaviour tests failed for missing behaviour. The results showed the
duplicate dispatch, the missing job state, inline article payment, and a legacy message that paid. The non-admin
test and the untracked-company test already passed and are kept as guards, not claimed as red. The website-check regression was added after the
implementation. A temporary mutation that removed the check made it fail. The migration test was also written
after the migration, so it is a regression check, not a red-first test.

| Check | Result |
|---|---|
| New behaviour tests | 10 passed |
| Related LLM, startup, refresh and ops suites | 314 passed |
| Full offline suite (rebuilt venv, 629 s) | 1125 passed / 23 dedicated-MySQL skipped / 0 failed |
| AST files / Jinja templates | 258 / 51 |
| flake8 E9,F on changed files | clean except 2 pre-existing F401 in untouched lines |

Test-environment deviations:
- The company page's weekly trend uses MySQL `YEARWEEK`. The new fixture registers a SQLite function of that name
  on its own connections. Product queries are unchanged.
- The first full run crossed local midnight while the venv lived in `/tmp`. macOS temporary cleanup emptied its
  site-packages mid-run. That run reported 204 failures, all in tests that start the fetch helper subprocess, and
  pytest could no longer start afterwards. The venv was rebuilt at `~/.cache/fsourceinsight-m3-venv` with the same
  115 package versions recovered from the old venv, including LiteLLM 1.101.0 and OpenAI 2.54.0. The failing log
  is kept as `m34c-full-01.log` and the passing one as `m34c-full-02.log`, both copied to `~/.cache/`, and is not counted as evidence either way.

The new MySQL assertion (no refresh jobs after upgrade, head `d3e7a1c95b28`) was added but not run. There is no
local Docker socket or mysqld.

## Follow-up fix: lost JSON history (2026-09-24)

Two admin paths appended to a JSON list loaded from the database and then assigned an equal list back. The column
is a plain JSON type, so SQLAlchemy saw no change and emitted no UPDATE.

- **Revision history.** A company with fewer than ten revisions lost every further revision entry. The analysis
  itself was saved. This affected manual edits, initial discovery analysis and refreshes.
- **Duplicate merge aliases.** Merging into a company that already had aliases dropped the duplicate's name and
  aliases. Later discovery and NER could then recreate the duplicate.

Both now copy the list before appending. Two real-HTTP regressions failed before the change and pass after it. A
scan of the other JSON columns found no other in-place writes. Entries already lost are not recoverable.

## Not done

- Real MySQL, broker, worker-kill and capacity gates.
- A refresh-frequency policy. Every processed article may still request a refresh; coalescing only limits
  concurrency to one job per company.
- A failure between claim and admission caused by a company edit is reported as `not_admitted`, not `stale`.
- Deployment. It needs a drained llm queue, a backup, the migration, and all paid workers switched together.
