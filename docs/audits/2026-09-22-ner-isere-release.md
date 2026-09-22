# NER Isère candidates into the review queue (2026-09-22 06:33 UTC)

Owner-authorized. Application `927dfe9` → `a93beb8`; schema unchanged (`c7f21a9d680e`). First release in this series that
rebuilds the paid LLM worker, because the change lives in `app/llm/{prompts,contracts,pipeline}.py`.

## Change
NER may return an optional `location` (`city`, `postcode`, `in_isere`). The prompt requires the article to state the place and
forbids guessing from the topic. A **new** company with `in_isere` true is created `is_grenoble=True, review_status='pending'`,
so it reaches `/admin/companies?review=pending` and never the public map; city and postcode are stored as review evidence.
Existing companies are untouched — rejected entries are not revived and operator map decisions are not overwritten.
`location` is optional in the contract, so cached and fallback replies remain valid. `PROMPT_VERSION` 2026-09-06.2 → 2026-09-22.1
and `CONTRACT_VERSION` 1 → 2, which invalidates cached NER responses; already-processed articles are not re-run.

## Evidence
Local 1113 passed / 23 skipped; CI 35668119145 succeeded including the disposable-MySQL tests. Four new tests cover contract
acceptance/rejection, the prompt wording and version, pending creation, and that existing review decisions survive.

## Procedure
Backup `~/fsourceinsight-backups/ner-20260922063300/database.sql.gz` (0600, verified). Reservation states and today's usage rows
were captured before and after. All four images rebuilt while the old containers ran; the new pin layer copies the previous one and
replaces only the images — a scripted check asserted every service's pinned command is byte-identical. Beat was stopped first, the
llm worker reported 0 active tasks before a 180s-grace stop, then web. Candidate reported `c7f21a9d680e (head)`; no migration.

## Post-deploy
Health ok locally and publicly (map 200, anonymous `/admin/` redirects). All four services recreated, restarts 0, memory limits and
worker argv unchanged (`-Q llm -c 2 --pool=prefork --max-tasks-per-child=50 --max-memory-per-child=393216`); the private evidence
volume is still mounted read-write on web only and absent from workers and beat. The llm worker logged "ready" and registers
`process_article_llm` and `refresh_company_analysis` (the in-script check printed 0 because the worker had just started; re-checked
afterwards with a longer timeout). No errors in beat logs. **Ledger identical before and after the restart** — no reservation moved
and no usage row was created by the deployment.

## Watch next
Isère candidates will now accumulate in the review queue and need periodic triage. Cached NER responses are invalidated, so the next
articles cost real calls again. Not done: MySQL/broker gates inside the candidate images; browser check; no production article has
yet exercised the new prompt end to end.
