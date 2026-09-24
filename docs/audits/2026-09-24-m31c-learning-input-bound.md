# M3.1c learning input byte bound (local only, not deployed)

Approved by the user on 2026-09-24 ("OK，继续") after the proposal to give learning its own small reviewed input
ceiling, enforced by the application. No commit, deployment, configuration change or provider call was made.

## Problem

Learning admits a round only if the cumulative input and output ceilings stay within 20,000 tokens and the
reservation fits the $0.20 session budget. The only reviewed production configs have a 400,000-token input
ceiling, so learning can never be admitted. The earlier rule forbade guessing a smaller ceiling, because nothing
guaranteed that the prompt would stay under it.

## Change

- **Bound.** For a byte-level BPE tokenizer every billed token covers at least one UTF-8 byte, so text tokens never
  exceed bytes. The bound is the bytes of each message's content and role, plus 8 per message, plus 64 overall
  for chat formatting.
- **Declared providers.** The bound is used only for providers listed in `CRAWL_LEARNING_BYTE_BOUND_PROVIDERS`,
  default `openai`. Operators declare this, like prices and ceilings.
- **Claim.** The prompt is sized to the smallest input ceiling among active, explicitly assigned primary or
  fallback `crawl_schema` configs of declared providers. The largest excerpt is cropped until the bound fits.
  The session is blocked without payment if no such config exists, or if the instructions and recipe alone do
  not fit.
- **Admission.** Inside the global admission transaction, each paid attempt re-checks that the provider is
  declared and that the bound is within that config's reviewed input ceiling.

Other learning limits are unchanged.

## Operating it

Create a config assigned only to `crawl_schema`, with reviewed prices and small ceilings. The reservation
`input ceiling × input price + output ceiling × output price` must fit $0.20, and three rounds must fit 20,000
tokens. For example, with the reviewed gpt-5.4-mini prices ($0.00075 / $0.0045 per 1k tokens), ceilings of 5,000
input and 1,500 output reserve about $0.0105 per round, and three rounds use at most 19,500 tokens. Ordinary task configs keep their 400,000 ceilings. A provider that bills beyond the bound is still caught
by the existing overrun detection and reconciliation.

## Evidence

Three real Admin learning tests failed on the old code and pass now:

| Scenario | Old code | New code |
|---|---|---|
| Ceiling 2,500 | bound of 3,271 sent and paid | cropped to within 2,500, one call |
| Ceiling 300 | paid call | blocked with no call; reason names the input ceiling |
| Provider not declared | paid call | blocked with no call |

The shared learning fixture now declares its synthetic provider. Its ceilings are 7,168 input and 1,024 output,
with `max_tokens` 1,024, which keeps the historical $0.092160 reservation that existing tests assert. Two earlier
choices were wrong and are recorded here:
- 15,000 input exceeded the $0.20 session reservation. One new test passed for the wrong reason; this was
  noticed before implementation.
- 11,000 input broke 9 existing tests whose amounts derive from the old reservation. Their assertions were kept
  and the ceilings were chosen to preserve the amounts instead.

The MySQL fixture was updated the same way but not run.
Full suite: 1141 passed, 23 dedicated-MySQL skipped, 0 failed (666 s, `~/.cache/m31c-full-02.log`). The previous run with the 11,000 fixture had 9 failures, kept as `m31c-full-01.log`.

## Not done

- Enabling learning in production. It still needs the new config reviewed and saved, the flag turned on, and the
  dedicated worker validated.
- Providers whose tokenizer is not byte-level; they stay undeclared.
