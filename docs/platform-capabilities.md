# Platform Capability Ledger

Last reviewed: 2026-08-11

This ledger is the gate for M7 integrations. A platform adapter may only expose
an operation after its current official documentation, authentication model,
required scopes, rate limits, review requirements, and confirmation semantics
have been recorded here.

## Status

No external platform capability has been verified yet. M7 remains blocked by
design; development and tests use mock adapters until a capability is verified.

## Verification rules

- Use official provider documentation as the primary source.
- Record the verification date and a direct documentation URL.
- Distinguish read, draft, publish, analytics, messaging, and deletion scopes.
- Record whether access requires app review, partnership, or a paid tier.
- Record the provider response that confirms a side effect actually succeeded.
- Treat undocumented browser automation, private endpoints, scraped session
  cookies, CAPTCHA bypass, and rate-limit circumvention as unsupported.
- Re-check an entry before implementation if it is more than 90 days old or the
  provider announces a relevant API or policy change.

## Capability matrix

| Platform | Capability | Status | Verified | Official source | Notes |
|---|---|---|---|---|---|
| LinkedIn | Unspecified | Not verified | — | — | No adapter work authorized |
| X | Unspecified | Not verified | — | — | No adapter work authorized |
| Job boards | Unspecified | Not verified | — | — | Public ATS feeds are assessed in M5 |
