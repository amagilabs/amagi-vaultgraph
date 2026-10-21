---
title: Retry with Backoff
type: concept
---

# Retry with Backoff
Exponential backoff with jitter, capped at 30s. Only retry idempotent calls, see [[idempotency-keys]]. Respect [[rate-limitting]] headers.
