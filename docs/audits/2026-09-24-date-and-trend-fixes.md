# Date filter and weekly sentiment trend fixes (local only)

Two items from the 2026-09-18 remaining-work list, section 4. They are independent of M3 and touch only the
files named below. Nothing was committed or deployed.

## Date filter end day

The news page and `/api/v1/news` compared `published_at <= date_to 00:00`. Filtering for one day returned only
articles stamped exactly at midnight and dropped the rest of that day. Both now use an exclusive bound at the
next midnight. `date_from` is unchanged. Timezone meaning is unchanged: stored times are naive and compared as
calendar dates.

Files: `app/web/views/news.py`, `app/api/v1/routes.py`, `tests/test_web/test_date_filters.py`.

## Company weekly sentiment trend

`_get_sentiment_trend` grouped by MySQL `YEARWEEK` and sentiment, then used each group's earliest date as the key.
Three defects followed:
- Sentiments in the same week often had different earliest dates, so one week showed as several bars.
- `YEARWEEK` mode 0 starts weeks on Sunday, so a Sunday fell into a different week than the Monday before it.
- Keys were sorted as `MM/DD` strings, so January came before the previous December, and the "last 12 weeks"
  cut was wrong across a year boundary.

The query now counts per `DATE()` and sentiment, which works on MySQL and SQLite. Python buckets the days into
Monday-start weeks, sorts by the real date and keeps the latest 12 weeks with data. Labels stay `MM/DD` of the
Monday. The page no longer depends on a MySQL-only function.

Files: `app/web/views/company.py`, `tests/test_web/test_company_trend.py`.

## Evidence

All four HTTP regressions failed before their fix and passed after it. For the trend, the old code showed three
bars for one week and put `01/05` before `12/29`. The trend test registers a SQLite `yearweek` function only so
the old query could run for that check; the new code does not use it. Full-suite results are in `progress.md`.
MySQL `DATE()` returning a `date` object was not run against a real MySQL server.
