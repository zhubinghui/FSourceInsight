# M3.3c general holdout inventories (local only, not deployed)

Branch `m3-company-refresh`. No schema change: the new rules are a versioned protocol stored in the existing
validation record. Learning stays disabled in production. Nothing was committed, deployed or sent to a provider.

## Problem

`holdout-validation.v1` accepted only one non-paginated HTML list. RSS, several lists and pagination were always
`unsupported_sampling_inventory`. The exposure check also split pages by the recipe's static list URLs. A second
pagination page or an RSS feed URL was therefore treated as a detail page and compared against training URLs.
Because those URLs repeat by design, such holdouts would have been rejected as previously seen even with new
content.

## Change

New freezes use `holdout-validation.v2`:

- The base recipe, with detail templates removed, is replayed on the pinned capture. Its article URLs are the
  detail pages; every other retained document is an inventory page (list, pagination page or feed).
- Inventory pages must have unseen raw bytes and normalized text. Detail pages must also have unseen and
  mutually distinct URLs. Before replay only bytes and text are checked. The full check runs once roles are known.
  A seen detail URL found then is reported as `previously_seen_evidence`.
- Each list or feed the candidate declares must contribute an article. A list with pagination must contribute
  from page 2 or later. Otherwise the result is `insufficient_list_coverage`.
- Bodies taken directly from a feed are `feed_content_not_independently_sampled`. Feed windows overlap between
  captures, so single items cannot be shown to be independent.
- Results add `inventory`, the sorted snapshot ids of inventory pages, and `lists` is its size. A recorded pass is
  re-checked with those roles when viewed.

Records frozen under v1 keep the v1 rules and result keys. The authority check originally accepted only the
current format, which would have turned every v1 record stale after an upgrade. The compatibility test caught it
and both known formats are now accepted.

The existing limit of 6 retained documents still applies, so one holdout holds at most 3 inventory pages plus 3
details.

## Evidence

Real Admin HTTP flow: learning, freeze, new capture, validation. Only the network, broker and provider are
synthetic.

| Scenario | Before | After |
|---|---|---|
| Pagination, page-2 URL also seen in training | inconclusive, previously seen | passed, 2 lists, 3 details |
| Pagination declared but not exercised | inconclusive, unsupported | inconclusive, insufficient list coverage |
| Two list pages | inconclusive | passed, 2 lists, 3 details |
| RSS feed with detail pages | inconclusive | passed, 1 list, 3 details |
| RSS bodies from the feed only | inconclusive, previously seen | inconclusive, feed content not sampled |
| v1-frozen record | not applicable | still single-list rules, no `inventory` key |

The first five failed on the old code. The v1 test failed against the first v2 draft. The existing test for
unexercised candidate branches kept its inconclusive status; only its reason changed, as planned. Full suite: 1138 passed, 23 dedicated-MySQL skipped, 0 failed (654 s, `~/.cache/m33c-full-01.log`).

## Not done

- Holdouts larger than the 6-document evidence limit.
- Certifying feed-supplied bodies.
- System-wide exposure coverage outside the controlled learning workflow.
- Real worker, broker and MySQL gates. Learning remains disabled; its enablement is still blocked by the billing
  ceiling question.
