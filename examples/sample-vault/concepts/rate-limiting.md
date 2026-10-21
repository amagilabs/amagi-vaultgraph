---
title: Rate Limiting
type: concept
---

# Rate Limiting
Token bucket per API key. Return 429 with Retry-After (see [[http-status-codes]]). Clients should back off, see [[retry-with-backoff]].
